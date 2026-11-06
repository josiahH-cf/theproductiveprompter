"""Read-only export and typed intake of externally edited article Markdown.

The source envelope is a comparison token, never permission to publish or proof
of which model wrote the supplied candidate. All public baselines are observed
again through the existing revision owner before a run can be created.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

import revision_sources as sources


SOURCE_KEYS = {
    "revision_source_version", "canonical_url", "slug", "title",
    "original_published_timestamp", "source_html_sha256", "source_commit",
    "source_observed_at", "source_markdown_sha256",
}
START = "<!-- GENERATED_ARTICLE_START -->"
END = "<!-- GENERATED_ARTICLE_END -->"
BLOG_URL = "https://theproductiveprompter.com/docs/blog.html"


def fail(af: Any, message: str, *, usage: bool = False) -> None:
    raise af.FlowError(message, af.EXIT_USAGE if usage else af.EXIT_INTEGRITY)


def body_html(af: Any, data: bytes) -> str:
    text = data.decode("utf-8")
    if text.count(START) != 1 or text.count(END) != 1:
        fail(af, "Published article has no unique generated body; an explicit source recovery is required")
    start, end = text.index(START) + len(START), text.index(END)
    if end < start:
        fail(af, "Published article body markers are reversed")
    body = text[start:end].strip()
    # These two exact controller-owned suffixes are outside article prose.
    # Do not strip arbitrary footers, links or user-authored body regions.
    body = re.sub(r'\s*<footer class="article-revision-handoff"><p><a href="[a-z0-9]+(?:-[a-z0-9]+)*\.revision\.json">Article revision source \(Markdown\)</a></p></footer>\s*$', "", body)
    body = re.sub(r'\s*<footer class="article-external-revision-attribution"><p>Revision text supplied in GPT; exact model unverified\.</p></footer>\s*$', "", body)
    body = re.sub(r'\s*<footer class="article-model-attribution" data-style-policy-sha256="[0-9a-f]{64}"><p>Drafting model: [^<>]+</p></footer>\s*$', "", body)
    return body.strip()


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.images: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        if tag == "a" and fields.get("href"):
            self.links.append(str(fields["href"]))
        if tag == "img" and fields.get("src"):
            self.images.append({"src": str(fields["src"]), "alt": str(fields.get("alt", ""))})


class Blog(HTMLParser):
    """Choose the first article card title link in actual published order."""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.cards: list[str] = []
        self.inert = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        if tag in {"template", "noscript"}:
            self.inert += 1
        if self.inert:
            return
        if tag == "article":
            self.depth += 1
        if tag == "a" and self.depth and "article-card__link" in str(fields.get("class", "")).split():
            self.cards.append(str(fields.get("href", "")))

    def handle_endtag(self, tag: str) -> None:
        if tag in {"template", "noscript"}:
            self.inert = max(0, self.inert - 1)
        if self.inert:
            return
        if tag == "article":
            self.depth = max(0, self.depth - 1)


def latest_slug(af: Any) -> str:
    repo = af.publication_repo_root(required=True)
    path = repo / "docs/blog.html"
    committed = af.git(["show", "HEAD:docs/blog.html"], cwd=repo, binary=True)
    if not path.is_file() or path.read_bytes() != committed:
        fail(af, "Blog index differs from committed repository bytes")
    status, live, _ = af.fetch_url(BLOG_URL)
    if status != 200 or live != committed:
        fail(af, "Selecting the latest article requires exact matching live blog index bytes")
    page = Blog()
    page.feed(committed.decode("utf-8"))
    if not page.cards:
        fail(af, "Published blog index has no article title link")
    url = urlsplit(urljoin(BLOG_URL, page.cards[0]))
    match = re.fullmatch(r"/docs/([a-z0-9]+(?:-[a-z0-9]+)*)\.html", url.path)
    if url.scheme != "https" or url.netloc != "theproductiveprompter.com" or url.query or url.fragment or not match:
        fail(af, "Latest blog card does not identify an allowlisted canonical article")
    return match.group(1)


def current_run(af: Any, snapshot: dict) -> tuple[Path, dict, bytes] | None:
    """Recover Markdown only from an intact package of these exact public bytes."""
    for path in sorted(af.runs_root().glob("*/run.json"), reverse=True):
        try:
            directory, run = af.load_run(path.parent.name)
            if run.get("state") != "COMPLETE":
                continue
            item = af.artifact(run, "package")
            if not item:
                continue
            package_path = (directory / item["path"]).resolve()
            if not package_path.is_relative_to(directory.resolve()):
                continue
            if af.sha256_path(package_path) != item["sha256"]:
                continue
            package = af.load_json(package_path)
            files = {entry["path"]: entry["sha256"] for entry in package["public_files"]}
            site = "site/" + snapshot["path"]
            markdown = directory / "package/public/article.md"
            page = directory / "package" / site
            if files.get(site) != snapshot["sha256"] or not page.is_file() or page.read_bytes() != snapshot["bytes"]:
                continue
            if not markdown.is_file() or af.sha256_path(markdown) != files.get("public/article.md"):
                continue
            return directory, run, markdown.read_bytes()
        except (af.FlowError, OSError, KeyError, TypeError, ValueError):
            continue
    return None


class Node:
    def __init__(self, tag: str = "", attrs: list | None = None):
        self.tag = tag
        self.attrs = dict(attrs or [])
        self.children: list[Node | str] = []


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {"img", "br", "hr"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        if len(self.stack) == 1 or self.stack[-1].tag != tag:
            raise ValueError("Unbalanced article HTML")
        self.stack.pop()

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in {"img", "br", "hr"}:
            self.handle_endtag(tag)

    def handle_data(self, value):
        self.stack[-1].children.append(value)

    def handle_comment(self, value):
        raise ValueError("Owned HTML panels require their original packaged Markdown")


def convert_markdown(af: Any, snapshot: dict) -> bytes:
    """Support ordinary renderer output; decline lossy or unfamiliar legacy HTML."""
    original = body_html(af, snapshot["bytes"])
    tree = Tree()

    def render(node: Node | str, *, literal: bool = False) -> str:
        if isinstance(node, str):
            return node if literal else node.replace("\n", " ")
        content = "".join(render(child, literal=literal or node.tag == "pre") for child in node.children
                          if not (node.tag in {"", "blockquote"} and isinstance(child, str) and not child.strip()))
        if node.tag == "":
            return content
        if node.tag == "li":
            return content
        if node.tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6"}:
            prefix = "#" * int(node.tag[1]) + " " if node.tag.startswith("h") else ""
            return prefix + content.strip() + "\n\n"
        if node.tag in {"strong", "b", "em", "i"}:
            mark = "**" if node.tag in {"strong", "b"} else "*"
            return mark + content + mark
        if node.tag == "a":
            return f"[{content}]({node.attrs['href']})"
        if node.tag == "img":
            return f"![{node.attrs.get('alt', '')}]({node.attrs['src']})"
        if node.tag == "code":
            return content if literal else "`" + content + "`"
        if node.tag == "pre":
            if "```" in content:
                raise ValueError("Code fence collision")
            code = next((c for c in node.children if isinstance(c, Node) and c.tag == "code"), None)
            language = str(code.attrs.get("class", "")).removeprefix("language-") if code else ""
            return "```" + language + "\n" + content.strip("\n") + "\n```\n\n"
        if node.tag == "blockquote":
            return "\n".join("> " + line for line in content.strip().splitlines()) + "\n\n"
        if node.tag in {"ul", "ol"}:
            children = [c for c in node.children if isinstance(c, Node)]
            if any(c.tag != "li" for c in children):
                raise ValueError("Unsupported list")
            return "\n".join(("- " if node.tag == "ul" else f"{i}. ") + "".join(render(c) for c in child.children).strip() for i, child in enumerate(children, 1)) + "\n\n"
        if node.tag == "br":
            return "  \n"
        raise ValueError(f"Unsupported article HTML: {node.tag}")

    try:
        tree.feed(original)
        if len(tree.stack) != 1:
            raise ValueError("Unclosed article HTML")
        markdown = render(tree.root).strip() + "\n"
        # Same visible text, link targets, code, emphasis and element structure.
        # Whitespace between block tags is immaterial; inside code it is not.
        def normalized(value: str) -> str:
            value = re.sub(r">\s+<", "><", value.strip())
            return value.replace("<b>", "<strong>").replace("</b>", "</strong>").replace("<i>", "<em>").replace("</i>", "</em>")
        if normalized(af.markdown_to_html(markdown)) != normalized(original):
            raise ValueError("Markdown conversion would change rendered source")
        return markdown.encode("utf-8")
    except (ValueError, KeyError) as exc:
        fail(af, f"Cannot losslessly export this published HTML as supported Markdown: {exc}")


def public_markdown(af: Any, data: bytes) -> bytes:
    """Expose only the renderer's public body, never hidden frontmatter keys."""
    try:
        text = data.decode("utf-8")
    except UnicodeError as exc:
        fail(af, f"Public revision Markdown is not valid UTF-8: {exc}")
    return text[af.markdown_body_start(text):].encode("utf-8")


def material(af: Any, snapshot: dict) -> tuple[bytes, tuple | None]:
    found = current_run(af, snapshot)
    return (public_markdown(af, found[2]), found) if found else (public_markdown(af, convert_markdown(af, snapshot)), None)


def identity(snapshot: dict, markdown: bytes) -> dict:
    metadata = snapshot["metadata"]
    return {"revision_source_version": "1.0.0", "canonical_url": metadata["canonical_url"],
            "slug": metadata["slug"], "title": metadata["title"],
            "original_published_timestamp": metadata["date_iso"],
            "source_html_sha256": snapshot["sha256"], "source_commit": snapshot["commit"],
            "source_observed_at": snapshot["observed_at"], "source_markdown_sha256": sources.digest(markdown)}


def export(af: Any, args: Any) -> int:
    slug = getattr(args, "published_slug", None) or latest_slug(af)
    snapshot = sources.checked_snapshot(af, slug)
    markdown, _ = material(af, snapshot)
    envelope = identity(snapshot, markdown)
    destination = Path(args.output_dir).expanduser().resolve()
    # Export cannot clobber another draft, private source or installed runtime.
    for root in (af.SPEC_ROOT, af.runs_root(), af.publication_repo_root(required=True)):
        if destination.is_relative_to(root.resolve()):
            fail(af, "Revision export requires a private directory outside runtime, runs and publication repository", usage=True)
    data = (json.dumps(envelope, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if destination.exists() and not destination.is_dir():
        fail(af, "Revision export destination is not a directory", usage=True)
    if destination.exists() and any(destination.iterdir()):
        try:
            old = json.loads((destination / "source.json").read_bytes())
            same = (set(old) == SOURCE_KEYS and all(old[k] == envelope[k] for k in SOURCE_KEYS - {"source_commit", "source_observed_at"})
                    and (destination / "article.md").read_bytes() == markdown)
        except (ValueError, OSError, TypeError, KeyError):
            same = False
        if not same:
            fail(af, "Revision export directory already contains different material", usage=True)
        data = (destination / "source.json").read_bytes()
        envelope = old
    destination.mkdir(parents=True, exist_ok=True)
    af.immutable_write(destination / "article.md", markdown)
    af.immutable_write(destination / "source.json", data)
    af.emit({"ok": True, "action": "revision_exported", "source": envelope,
             "article_file": str(destination / "article.md"), "source_file": str(destination / "source.json"),
             "execution_started": False, "publication_started": False}, args.json)
    return af.EXIT_OK


def read_utf8(af: Any, value: str, label: str) -> bytes:
    try:
        data = Path(value).expanduser().resolve().read_bytes()
        text = data.decode("utf-8")
    except (OSError, UnicodeError, TypeError) as exc:
        fail(af, f"{label} must be a readable UTF-8 file: {exc}", usage=True)
    if not text.strip() or "\x00" in text:
        fail(af, f"{label} is empty or contains NUL", usage=True)
    return data


def asset_registry(af: Any, snapshot: dict) -> list[dict]:
    page = Links(); page.feed(body_html(af, snapshot["bytes"]))
    repo = af.publication_repo_root(required=True)
    result = []
    for image in page.images:
        url = urljoin(snapshot["metadata"]["canonical_url"], image["src"])
        parsed = urlsplit(url)
        if parsed.netloc != "theproductiveprompter.com":
            fail(af, "External article images require a separately verified asset import")
        if parsed.scheme != "https" or parsed.query or parsed.fragment:
            fail(af, "Article asset URL is not a plain allowlisted HTTPS resource")
        relative = parsed.path.lstrip("/")
        path = (repo / relative).resolve()
        if not relative.startswith("assets/") or not path.is_relative_to(repo.resolve()) or not path.is_file():
            fail(af, "Article image is outside the publication asset directory")
        data = af.git(["show", f"HEAD:{relative}"], cwd=repo, binary=True)
        status, live, _ = af.fetch_url(url)
        if data != path.read_bytes() or status != 200 or live != data:
            fail(af, "Article asset requires exact matching Git, worktree and live bytes")
        result.append({**image, "public_path": parsed.path, "sha256": sources.digest(data), "bytes": data})
    return result


def prepare(af: Any, args: Any) -> dict:
    """Validate all caller-controlled material before reserving or creating work."""
    if any(getattr(args, field, None) for field in ("source_run_id", "published_slug", "expected_source_sha256")):
        fail(af, "External candidate identity comes only from --source-file; do not combine source selectors", usage=True)
    if not getattr(args, "source_file", None) or not getattr(args, "candidate_file", None):
        fail(af, "External revision requires --source-file and --candidate-file", usage=True)
    paths = [Path(value).expanduser().resolve() for value in (args.source_file, args.candidate_file, args.request_file)]
    if len(set(paths)) != 3 or any(a.is_file() and b.is_file() and a.samefile(b) for i, a in enumerate(paths) for b in paths[i + 1:]):
        fail(af, "Source identity, generated candidate and exact author feedback require separate files", usage=True)
    envelope_bytes = read_utf8(af, args.source_file, "Revision source envelope")
    candidate = read_utf8(af, args.candidate_file, "Revision candidate")
    request = read_utf8(af, args.request_file, "Exact author feedback")
    try:
        def pairs(items):
            value = {}
            for key, item in items:
                if key in value:
                    raise ValueError("duplicate field")
                value[key] = item
            return value
        envelope = json.loads(envelope_bytes, object_pairs_hook=pairs)
        provided_markdown = None
        provided_visuals = None
        if isinstance(envelope, dict) and set(envelope) in ({"source", "article_markdown"}, {"source", "article_markdown", "visuals"}):
            if not isinstance(envelope["article_markdown"], str):
                raise ValueError("public source Markdown must be a string")
            provided_markdown = envelope["article_markdown"].encode("utf-8")
            provided_visuals = envelope.get("visuals")
            envelope = envelope["source"]
        if not isinstance(envelope, dict) or set(envelope) != SOURCE_KEYS or any(not isinstance(v, str) or not v for k, v in envelope.items() if k != "source_commit"):
            raise ValueError("unexpected, missing or non-string identity fields")
        if envelope["revision_source_version"] != "1.0.0":
            raise ValueError("unsupported source version")
        for key in ("source_html_sha256", "source_markdown_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", envelope[key]):
                raise ValueError("invalid source digest")
        if envelope["source_commit"] is not None and (not isinstance(envelope["source_commit"], str) or not re.fullmatch(r"[0-9a-f]{40,64}", envelope["source_commit"])):
            raise ValueError("invalid source commit")
        for key in ("original_published_timestamp", "source_observed_at"):
            if dt.datetime.fromisoformat(envelope[key].replace("Z", "+00:00")).tzinfo is None:
                raise ValueError("source times require a timezone")
    except (ValueError, TypeError, KeyError) as exc:
        fail(af, f"Invalid revision source envelope: {exc}", usage=True)
    snapshot = sources.checked_snapshot(af, envelope["slug"], envelope["source_html_sha256"])
    if envelope["source_commit"] is not None:
        try:
            committed = af.git(["show", f"{envelope['source_commit']}:{snapshot['path']}"],
                               cwd=af.publication_repo_root(required=True), binary=True)
        except af.FlowError as exc:
            fail(af, f"Revision source commit cannot be verified: {exc}")
        if committed != snapshot["bytes"]:
            fail(af, "Revision source commit does not contain the bound published article")
    if provided_markdown is not None and sources.digest(provided_markdown) != envelope["source_markdown_sha256"]:
        fail(af, "Public source Markdown no longer matches its bound digest")
    if provided_markdown is not None:
        class RevisionMeta(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.digests = []
                self.source_digests = []
            def handle_starttag(self, tag, attrs):
                fields = dict(attrs)
                if tag == "meta" and fields.get("name") == "article-flow-revision":
                    self.digests.append(fields.get("content"))
                if tag == "meta" and fields.get("name") == "article-flow-revision-source-sha256":
                    self.source_digests.append(fields.get("content"))
        meta = RevisionMeta(); meta.feed(snapshot["bytes"].decode("utf-8"))
        if provided_visuals is not None:
            if not isinstance(provided_visuals, list):
                fail(af, "Public diagram definitions must be a list")
            expected_meta = f'<meta name="article-flow-revision-visuals-sha256" content="{af.sha256_bytes(af.canonical_json(provided_visuals))}">'
            if expected_meta not in snapshot["bytes"].decode("utf-8"):
                fail(af, "Public diagram definitions are not bound by the verified HTML")
        bound = meta.source_digests if meta.source_digests else meta.digests
        if bound != [sources.digest(provided_markdown)]:
            fail(af, "Public source Markdown is not bound by the verified HTML revision metadata")
        found = current_run(af, snapshot)
        markdown = public_markdown(af, provided_markdown)
        if found and public_markdown(af, found[2]) != markdown:
            fail(af, "Public source Markdown differs from its intact completed package")
    else:
        markdown, found = material(af, snapshot)
    actual = identity(snapshot, markdown)
    for key in SOURCE_KEYS - {"source_commit", "source_observed_at"}:
        if envelope[key] != actual[key]:
            fail(af, f"Revision source identity no longer matches: {key}")
    text = candidate.decode("utf-8")
    if re.search(r"(?is)<\s*(?:!doctype|html|head|body|script)\b", text) or text.lstrip().startswith("```markdown"):
        fail(af, "Candidate must be complete article Markdown, without a webpage or enclosing code fence", usage=True)
    if len(text[af.markdown_body_start(text):].strip()) < 20:
        fail(af, "Candidate has no substantial article body", usage=True)
    source_text = snapshot["bytes"].decode("utf-8")
    panel = ""
    if sources.RESULTS_START in source_text or sources.RESULTS_END in source_text:
        if source_text.count(sources.RESULTS_START) != 1 or source_text.count(sources.RESULTS_END) != 1:
            fail(af, "Published results panel has ambiguous ownership markers")
        start, end = source_text.index(sources.RESULTS_START), source_text.index(sources.RESULTS_END)
        if end < start:
            fail(af, "Published results panel has reversed ownership markers")
        panel = source_text[start:end + len(sources.RESULTS_END)]
        if not sources.intact_owned_panel(text, panel):
            fail(af, "External revision changes or removes its source-owned results panel")
    # The ordinary renderer reinserts this exact allowlisted owned HTML block;
    # arbitrary HTML is escaped. Its links are already protected by byte match.
    source_body = body_html(af, snapshot["bytes"])
    source_links = Links(); source_links.feed(source_body.replace(panel, "") if panel else source_body)
    edited_links = Links(); edited_links.feed(af.markdown_to_html(text.replace(panel, "") if panel else text))
    canonical = snapshot["metadata"]["canonical_url"]
    target_links = {urljoin(canonical, link) for link in edited_links.links}
    if any(urljoin(canonical, link) not in target_links for link in source_links.links):
        fail(af, "External revision removes or changes a source citation/link; resolve this material conflict explicitly")
    source_images = Counter((urljoin(canonical, image["src"]), image["alt"]) for image in source_links.images)
    target_images = Counter((urljoin(canonical, image["src"]), image["alt"]) for image in edited_links.images)
    visual_plan, visual_plan_bytes = af.revision_handoff.visual_plan(af, args, candidate, envelope["slug"])
    replacements = visual_plan["replace_assets"] if visual_plan else []
    all_assets = asset_registry(af, snapshot)
    source_paths = {item["public_path"] for item in all_assets}
    if set(replacements) - source_paths:
        fail(af, "A diagram replacement does not identify an existing verified source asset")
    planned_paths = {f"/assets/articles/{envelope['slug']}/{item['visual_id']}.svg" for item in visual_plan["visuals"]} if visual_plan else set()
    if (planned_paths & source_paths) - set(replacements):
        fail(af, "A new diagram would overwrite a retained source asset; declare its replacement explicitly")
    expected_images = Counter({key: count for key, count in source_images.items()
                               if key[0] not in {urljoin(canonical, path) for path in replacements}})
    imported_images, image_plan_bytes = af.revision_images.prepare(af, args, candidate, envelope['slug'])
    if {item['public_path'] for item in imported_images} & (source_paths | planned_paths):
        fail(af, "A new capture conflicts with a source image or planned diagram")
    expected_images.update((urljoin(canonical, item['public_path']), item['alt']) for item in imported_images)
    if target_images != expected_images:
        fail(af, "External revision adds, removes, duplicates or changes a source image or its alt text; new assets require a separately verified import")
    source_args = argparse.Namespace(request_file=args.request_file, source_run_id=found[1]["run_id"] if found else None,
                                     published_slug=None if found else envelope["slug"], expected_source_sha256=envelope["source_html_sha256"])
    source = sources.prepare(af, source_args)
    # Snapshot author input once. Later source file mutation cannot change intake.
    source.update(request=request, candidate=candidate, external_source=envelope, external_source_bytes=envelope_bytes,
                  original_markdown=markdown, assets=all_assets + imported_images,
                  image_plan_bytes=image_plan_bytes, visual_plan=visual_plan, visual_plan_bytes=visual_plan_bytes,
                  public_visuals=provided_visuals if provided_visuals is not None else
                      (af.revision_handoff.public_visuals(af, found[0], found[1]) if found else []))
    # Evidence checks use the same proven snapshot as an ordinary revision.
    protected = sources.Page(); protected.feed(snapshot["bytes"].decode("utf-8"))
    # Markdown rendering normalizes line endings. Preserve the submitted file
    # bytes for provenance while comparing the code/quote payload it renders.
    candidate_regions = {(kind, payload) for _, _, kind, payload in sources.regions(text.replace("\r\n", "\n"))}
    if any((kind, payload) not in candidate_regions for kind, payload in protected.regions):
        fail(af, "External revision changes or removes source-bound quotation/code evidence")
    return source
