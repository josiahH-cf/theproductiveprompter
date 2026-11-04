"""External revision export/intake keeps real source identity and author input."""
from __future__ import annotations

import argparse
import json
from unittest import mock

from test_article_flow_v3 import TemporaryRuntime, af, call
import external_revision as external
import revision_sources as sources


class ExternalRevisionSourceTests(TemporaryRuntime):
    def setUp(self):
        super().setUp()
        self.repo = self.root / "publication"
        self.repo.mkdir()
        af.git(["init"], cwd=self.repo)
        af.git(["config", "user.name", "Revision test"], cwd=self.repo)
        af.git(["config", "user.email", "test@example.invalid"], cwd=self.repo)
        self.slug = "source-one"
        self.url = f"https://theproductiveprompter.com/docs/{self.slug}.html"
        self.stamp = "2026-09-15T09:04:24Z"
        self.markdown = "A concrete explanation with [its source](https://example.com/reference).\n\n## Next step\n\nKeep the useful parts.\n"
        self.pages = {}
        self.write_page(self.slug, self.markdown)
        self.write_page("older-article", "A deliberately older article.\n\nIt remains available for explicit selection.\n")
        blog = (f'<article class="article-card"><h3><a class="article-card__link" href="{self.slug}.html">Latest</a></h3></article>'
                '<article class="article-card"><h3><a class="article-card__link" href="older-article.html">Older</a></h3></article>').encode()
        (self.repo / "docs/blog.html").write_bytes(blog)
        self.pages[external.BLOG_URL] = blog
        self.commit()
        self.root_patch = mock.patch.object(af, "publication_repo_root", return_value=self.repo)
        self.fetch_patch = mock.patch.object(af, "fetch_url", side_effect=lambda url, timeout=30: (200, self.pages.get(url, b""), {}))
        self.root_patch.start(); self.fetch_patch.start()
        self.addCleanup(self.root_patch.stop); self.addCleanup(self.fetch_patch.stop)
        self.feedback = self.root / "feedback.md"
        self.feedback.write_bytes("Keep it direct\nI mean how this actually feels, not a formula.\n".encode())
        self.candidate = self.root / "candidate.md"
        self.candidate.write_bytes(self.markdown.replace("concrete explanation", "clearer explanation").encode())
        self.envelope = self.root / "source.json"
        self.envelope.write_text(json.dumps(self.identity()), encoding="utf-8")

    def write_page(self, slug, markdown):
        canonical = f"https://theproductiveprompter.com/docs/{slug}.html"
        post = {"@type": "BlogPosting", "headline": "Original title", "datePublished": self.stamp}
        value = (f'<html><head><link rel="canonical" href="{canonical}"><meta name="description" content="Description">'
                 f'<meta name="article-flow-revision" content="{sources.digest(markdown)}">'
                 f'<script type="application/ld+json">{json.dumps(post)}</script></head><body>'
                 + external.START + af.markdown_to_html(markdown) + external.END + '</body></html>').encode()
        path = self.repo / f"docs/{slug}.html"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(value)
        self.pages[canonical] = value

    def commit(self):
        af.git(["add", "."], cwd=self.repo)
        af.git(["commit", "-m", "Published source"], cwd=self.repo)

    def identity(self):
        snapshot = sources.checked_snapshot(af, self.slug)
        markdown, _ = external.material(af, snapshot)
        return external.identity(snapshot, markdown)

    def args(self, **kw):
        values = {"source_file": str(self.envelope), "candidate_file": str(self.candidate),
                  "request_file": str(self.feedback), "source_run_id": None, "published_slug": None,
                  "expected_source_sha256": None}
        values.update(kw)
        return argparse.Namespace(**values)

    def test_intake_preserves_exact_feedback_and_separates_generated_candidate(self):
        before = sorted(af.runs_root().glob("*/run.json"))
        source = external.prepare(af, self.args())
        self.assertEqual(source["request"], self.feedback.read_bytes())
        self.assertEqual(source["candidate"], self.candidate.read_bytes())
        self.assertNotIn(self.feedback.read_bytes(), source["candidate"])
        self.assertEqual(source["snapshot"]["metadata"]["date_iso"], self.stamp)
        self.assertEqual(sorted(af.runs_root().glob("*/run.json")), before)

    def test_latest_selection_uses_published_index_order_and_old_override(self):
        self.assertEqual(external.latest_slug(af), self.slug)
        out = self.root / "older-export"
        result = call(lambda args: external.export(af, args), published_slug="older-article", output_dir=str(out), json=True)
        self.assertEqual(result[0], af.EXIT_OK)
        self.assertEqual(json.loads((out / "source.json").read_text())["slug"], "older-article")
        self.assertIn("deliberately older", (out / "article.md").read_text())

    def test_export_is_read_only_and_reuses_identical_material(self):
        out = self.root / "export"
        args = argparse.Namespace(published_slug=None, output_dir=str(out), json=True)
        with mock.patch.object(af, "emit"):
            self.assertEqual(external.export(af, args), af.EXIT_OK)
            original = (out / "source.json").read_bytes()
            self.assertEqual(external.export(af, args), af.EXIT_OK)
        self.assertEqual((out / "source.json").read_bytes(), original)
        self.assertEqual(af.git(["status", "--porcelain"], cwd=self.repo).strip(), "")

    def test_stale_html_refuses_before_run_creation(self):
        self.write_page(self.slug, self.markdown + "\nA newly published correction.\n")
        self.commit()
        with self.assertRaisesRegex(af.FlowError, "baseline hash"):
            external.prepare(af, self.args())
        self.assertEqual(list(af.runs_root().glob("*/run.json")), [])

    def test_identity_is_strict_and_does_not_accept_fabricated_fields(self):
        identity = json.loads(self.envelope.read_text())
        identity["author_approved"] = True
        self.envelope.write_text(json.dumps(identity))
        with self.assertRaisesRegex(af.FlowError, "identity fields"):
            external.prepare(af, self.args())

    def test_identity_cannot_select_a_different_title_or_date(self):
        original = self.identity()
        for key, value in (("title", "Different article"), ("original_published_timestamp", "2026-10-01T12:00:00Z")):
            changed = {**original, key: value}
            self.envelope.write_text(json.dumps(changed))
            with self.assertRaisesRegex(af.FlowError, "identity no longer matches"):
                external.prepare(af, self.args())

    def test_candidate_and_author_feedback_cannot_be_the_same_file(self):
        with self.assertRaisesRegex(af.FlowError, "separate files"):
            external.prepare(af, self.args(request_file=str(self.candidate)))

    def test_public_source_wrapper_has_verified_original_markdown(self):
        identity = self.identity()
        identity["source_commit"] = None
        markdown, _ = external.material(af, sources.checked_snapshot(af, self.slug))
        self.envelope.write_text(json.dumps({"source": identity, "article_markdown": markdown.decode()}))
        self.assertEqual(external.prepare(af, self.args())["external_source"]["source_commit"], None)
        value = json.loads(self.envelope.read_text())
        value["article_markdown"] += "Changed source"
        self.envelope.write_text(json.dumps(value))
        with self.assertRaisesRegex(af.FlowError, "bound digest"):
            external.prepare(af, self.args())

    def test_public_wrapper_requires_digest_in_actual_html_not_only_envelope(self):
        identity = self.identity()
        changed = self.markdown + "An invented original sentence.\n"
        identity["source_markdown_sha256"] = sources.digest(changed)
        self.envelope.write_text(json.dumps({"source": identity, "article_markdown": changed}))
        with self.assertRaisesRegex(af.FlowError, "verified HTML revision metadata"):
            external.prepare(af, self.args())

    def test_public_export_omits_unknown_hidden_frontmatter_from_retained_source(self):
        raw = ('---\ntitle: "A visible title"\ninternal_pipeline_note: "DO NOT EXPOSE THIS PRIVATE VALUE"\n'
               'unrecognized_future_key: "ALSO PRIVATE"\n---\n\n' + self.markdown).encode()
        self.write_page(self.slug, raw.decode())
        self.commit()
        projected = external.public_markdown(af, raw)
        self.assertEqual(af.markdown_to_html(raw.decode()), af.markdown_to_html(projected.decode()))
        out = self.root / "safe-export"
        with mock.patch.object(external, "current_run", return_value=(self.root, {"state": "COMPLETE"}, raw)), mock.patch.object(af, "emit"):
            external.export(af, argparse.Namespace(published_slug=self.slug, output_dir=str(out), json=True))
        self.assertEqual((out / "article.md").read_bytes(), projected)
        self.assertNotIn(b"PRIVATE", (out / "article.md").read_bytes())
        self.assertNotIn(b"unrecognized_future_key", (out / "source.json").read_bytes())
        self.assertEqual(json.loads((out / "source.json").read_text())["source_markdown_sha256"], sources.digest(projected))

    def test_projected_public_wrapper_uses_dedicated_source_digest(self):
        raw = ('---\ntitle: "A title"\nprivate_key: "Do not publish"\n---\n\n' + self.markdown).encode()
        self.write_page(self.slug, raw.decode())
        projected = external.public_markdown(af, raw)
        page = self.pages[self.url].replace(b"</head>", f'<meta name="article-flow-revision-source-sha256" content="{sources.digest(projected)}"></head>'.encode())
        self.pages[self.url] = page
        (self.repo / f"docs/{self.slug}.html").write_bytes(page)
        self.commit()
        snapshot = sources.checked_snapshot(af, self.slug)
        identity = external.identity(snapshot, projected)
        self.envelope.write_text(json.dumps({"source": identity, "article_markdown": projected.decode()}))
        self.assertEqual(external.prepare(af, self.args())["original_markdown"], projected)
        wrong = page.replace(sources.digest(projected).encode(), b"f" * 64)
        self.pages[self.url] = wrong
        (self.repo / f"docs/{self.slug}.html").write_bytes(wrong)
        self.commit()
        identity = external.identity(sources.checked_snapshot(af, self.slug), projected)
        self.envelope.write_text(json.dumps({"source": identity, "article_markdown": projected.decode()}))
        with self.assertRaisesRegex(af.FlowError, "verified HTML revision metadata"):
            external.prepare(af, self.args())

    def test_owned_footers_do_not_become_article_links(self):
        snapshot = sources.checked_snapshot(af, self.slug)
        footer = ('<footer class="article-model-attribution" data-style-policy-sha256="' + 'a' * 64
                  + '"><p>Drafting model: Supplied candidate</p></footer>'
                  '<footer class="article-external-revision-attribution"><p>Revision text supplied in GPT; exact model unverified.</p></footer>'
                  '<footer class="article-revision-handoff"><p><a href="source-one.revision.json">Article revision source (Markdown)</a></p></footer>')
        snapshot["bytes"] = snapshot["bytes"].replace(external.END.encode(), footer.encode() + external.END.encode())
        body = external.body_html(af, snapshot["bytes"])
        self.assertNotIn("article-model-attribution", body)
        self.assertNotIn("revision.json", body)
        self.assertEqual(external.convert_markdown(af, snapshot), self.markdown.encode())

    def test_lossless_fallback_supports_lists_quotes_and_literal_code(self):
        markdown = ('An introduction.\n\n- First useful step\n- Keep [the source](https://example.com/one)\n\n'
                    '## A sequence\n\n1. First task\n2. Next task\n\n'
                    '> Exact quoted evidence.\n\n```python\nprint("literal <tag>")\n\nprint("two lines")\n```\n')
        snapshot = sources.checked_snapshot(af, self.slug)
        snapshot["bytes"] = (external.START + af.markdown_to_html(markdown) + external.END).encode()
        converted = external.convert_markdown(af, snapshot)
        self.assertEqual(af.markdown_to_html(converted.decode()), af.markdown_to_html(markdown))

    def test_retained_markdown_requires_intact_package_and_exact_public_html(self):
        snapshot = sources.checked_snapshot(af, self.slug)
        directory = af.runs_root() / "mock-run"
        (directory / "package/public").mkdir(parents=True)
        (directory / "package/site/docs").mkdir(parents=True)
        (directory / "run.json").write_text("{}")
        article = directory / "package/public/article.md"
        article.write_bytes(self.markdown.encode())
        page = directory / "package/site" / snapshot["path"]
        page.write_bytes(snapshot["bytes"])
        package = {"public_files": [{"path": "public/article.md", "sha256": sources.digest(self.markdown)},
                                    {"path": "site/" + snapshot["path"], "sha256": snapshot["sha256"]}]}
        package_path = directory / "package/package.json"
        package_path.write_text(json.dumps(package))
        run = {"state": "COMPLETE", "run_id": "mock-run", "artifact_index": [{"type": "package", "path": "package/package.json", "sha256": af.sha256_path(package_path)}]}
        with mock.patch.object(af, "load_run", return_value=(directory, run)):
            self.assertEqual(external.current_run(af, snapshot)[2], self.markdown.encode())
            article.write_bytes(b"tampered Markdown")
            self.assertIsNone(external.current_run(af, snapshot))

    def test_results_panel_links_are_preserved_by_exact_owned_bytes(self):
        panel = (sources.RESULTS_START + '\n<section id="model-experiment-results" aria-label="Model experiment results">'
                 '<h2>The experiment runs</h2><p><a href="/docs/model-release-experiment/index.html">Explore runs</a></p></section>\n'
                 + sources.RESULTS_END)
        source = self.pages[self.url].replace(external.END.encode(), panel.encode() + external.END.encode())
        self.pages[self.url] = source
        (self.repo / f"docs/{self.slug}.html").write_bytes(source)
        self.commit()
        identity = external.identity(sources.checked_snapshot(af, self.slug), self.markdown.encode())
        self.envelope.write_text(json.dumps({"source": identity, "article_markdown": self.markdown}))
        self.candidate.write_bytes((self.markdown + "\n" + panel + "\n").encode())
        self.assertEqual(external.prepare(af, self.args())["candidate"], self.candidate.read_bytes())
        self.candidate.write_bytes((self.markdown + "\n" + panel.replace("Explore runs", "Different text") + "\n").encode())
        with self.assertRaisesRegex(af.FlowError, "source-owned results panel"):
            external.prepare(af, self.args())

    def test_source_bound_quote_and_code_cannot_be_silently_polished(self):
        markdown = self.markdown + '\n> Exact source quotation.\n\n```python\nprint("exact code")\n```\n'
        self.write_page(self.slug, markdown)
        self.commit()
        self.envelope.write_text(json.dumps(self.identity()))
        self.candidate.write_text(markdown)
        self.assertEqual(external.prepare(af, self.args())["candidate"], self.candidate.read_bytes())
        self.candidate.write_text(markdown.replace("Exact source quotation.", "Polished source quotation."))
        with self.assertRaisesRegex(af.FlowError, "source-bound quotation/code"):
            external.prepare(af, self.args())

    def test_removing_or_retargeting_source_link_is_material_conflict(self):
        self.candidate.write_text(self.markdown.replace("https://example.com/reference", "https://other.example/reference"))
        with self.assertRaisesRegex(af.FlowError, "source citation/link"):
            external.prepare(af, self.args())

    def test_html_webpage_and_enclosing_markdown_fences_are_rejected(self):
        for value in ("<html><body>A full page</body></html>", "```markdown\n" + self.markdown + "```\n"):
            self.candidate.write_text(value)
            with self.assertRaisesRegex(af.FlowError, "complete article Markdown"):
                external.prepare(af, self.args())

    def test_unsupported_lossy_legacy_html_stays_blocked(self):
        snapshot = sources.checked_snapshot(af, self.slug)
        snapshot["bytes"] = snapshot["bytes"].replace(b"<p>", b"<aside>").replace(b"</p>", b"</aside>")
        with self.assertRaisesRegex(af.FlowError, "losslessly export"):
            external.convert_markdown(af, snapshot)

    def test_changed_asset_or_removed_alt_text_is_rejected(self):
        image = b'<svg xmlns="http://www.w3.org/2000/svg"><title>Bound diagram</title></svg>'
        path = self.repo / "assets/articles/source-one/diagram.svg"
        path.parent.mkdir(parents=True)
        path.write_bytes(image)
        self.pages["https://theproductiveprompter.com/assets/articles/source-one/diagram.svg"] = image
        self.markdown += "\n![Exact alt](/assets/articles/source-one/diagram.svg)\n"
        self.write_page(self.slug, self.markdown)
        self.commit()
        self.envelope.write_text(json.dumps(self.identity()))
        self.candidate.write_text(self.markdown)
        result = external.prepare(af, self.args())
        self.assertEqual(result["assets"][0]["bytes"], image)
        self.candidate.write_text(self.markdown.replace("Exact alt", "Changed alt"))
        with self.assertRaisesRegex(af.FlowError, "alt text"):
            external.prepare(af, self.args())
        self.candidate.write_text(self.markdown)
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(af.FlowError, "matching Git, worktree and live"):
            external.prepare(af, self.args())

    def test_unbound_external_or_local_image_is_rejected_before_fetch_or_run(self):
        for target in ("https://external.example/missing-404.png", "/assets/articles/source-one/new-unverified.png"):
            self.candidate.write_bytes((self.markdown + f"\n![An unbound image]({target})\n").encode())
            with self.subTest(target=target), mock.patch.object(af, "fetch_url", wraps=af.fetch_url) as fetch:
                with self.assertRaisesRegex(af.FlowError, "new assets require a separately verified import"):
                    external.prepare(af, self.args())
                self.assertNotIn(target, [item.args[0] for item in fetch.call_args_list])
                self.assertEqual(list(af.runs_root().glob("*/run.json")), [])

    def test_duplicate_existing_image_is_a_material_change(self):
        image = b'<svg xmlns="http://www.w3.org/2000/svg"><title>Bound diagram</title></svg>'
        path = self.repo / "assets/articles/source-one/diagram.svg"
        path.parent.mkdir(parents=True)
        path.write_bytes(image)
        self.pages["https://theproductiveprompter.com/assets/articles/source-one/diagram.svg"] = image
        original = self.markdown + "\n![Exact alt](/assets/articles/source-one/diagram.svg)\n"
        self.write_page(self.slug, original)
        self.commit()
        self.envelope.write_text(json.dumps(self.identity()))
        self.candidate.write_bytes((original + "\n![Exact alt](/assets/articles/source-one/diagram.svg)\n").encode())
        with self.assertRaisesRegex(af.FlowError, "duplicates or changes a source image"):
            external.prepare(af, self.args())
        self.assertEqual(list(af.runs_root().glob("*/run.json")), [])
