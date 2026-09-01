#!/usr/bin/env python3
"""Deterministic acceptance runner for the multi-page site change.

Run every outcome with ``python tests/run_checks.py``.  Use ``--suite`` to run
architecture, behavior, or preservation independently.  The runner intentionally
uses only the Python standard library; observable browser checks are delegated to
``tests/browser_checks.mjs`` and folded into the same named report.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable
from urllib.parse import parse_qs, unquote, urlsplit
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
TEMPLATE = ROOT / "Article-Spec-Pack-v1/publication/templates/article.html"
CONFIG = ROOT / "Article-Spec-Pack-v1/publication/theproductiveprompter.json"
PROJECT_FIXTURE = TESTS / "fixtures/pinned_projects_graphql.json"
PRESERVATION_FIXTURE = TESTS / "fixtures/preservation_baseline.json"
PROJECT_START = "<!-- PINNED_PROJECTS_START -->"
PROJECT_END = "<!-- PINNED_PROJECTS_END -->"
ARTICLE_MARKERS = (
    "<!-- ARTICLE_FLOW_LATEST_START -->",
    "<!-- ARTICLE_FLOW_LATEST_END -->",
    "<!-- ARTICLE_FLOW_SITEMAP_START -->",
    "<!-- ARTICLE_FLOW_SITEMAP_END -->",
    "<!-- ARTICLE_FLOW_FEED_START -->",
    "<!-- ARTICLE_FLOW_FEED_END -->",
)
EXPECTED_NAV = (
    ("Blog", "/docs/blog.html"),
    ("Projects", "/projects.html"),
    ("Reach Out", "/reach-out.html"),
    ("Agent Telemetry", "https://josiahh-cf.github.io/agent-telemetry/"),
)
BRAND = "🔐Security | ☁️Cloud | 🧠AI"
ABOUT = (
    "I'm a senior security engineer at Coalfire shifting into full time AI engineering, "
    "and I've spent years building secure cloud and AI systems on AWS, GCP, and Azure. "
    "I love talking about AI, security, cloud, or just human stuff, so let's grab a "
    "coffee and chat."
)
# Kept in pieces so this check does not itself reintroduce the forbidden literal.
PROHIBITED_CREDIT = "Built with HTML, " + "CSS, and JavaScript."
REMOVED_CLASSES = (
    "hero__description",
    "blog-section-intro",
    "contact__text",
    "blog-page__subtitle",
    "blog-section-note",
    "days-page__subtitle",
    "days-page__archive-note",
    "campaign-banner__desc",
    "campaign-banner__description",
)
REMOVED_BLURB_PREFIXES = (
    "New standalone writing first",
    "Writing projects, completed series",
    "A completed December 2025 writing project",
    "The December 2025 project is complete",
    "Completed means shelved together",
    "This archive is a visible home",
)


@dataclass
class Element:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list[Element | str] = field(default_factory=list)


class TreeParser(HTMLParser):
    VOID = {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("#document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Element(tag.lower(), {key.lower(): value for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag.lower() not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


@dataclass
class Result:
    id: str
    suite: str
    title: str
    status: str
    detail: str
    expected: str = ""
    actual: str = ""


class CheckFailure(AssertionError):
    def __init__(self, expected: str, actual: str, detail: str = "") -> None:
        super().__init__(detail or actual)
        self.expected = expected
        self.actual = actual
        self.detail = detail


def fail(expected: str, actual: str, detail: str = "") -> None:
    raise CheckFailure(expected, actual, detail)


def require_no_issues(expected: str, issues: Iterable[str], detail: str = "") -> None:
    found = list(issues)
    if found:
        fail(expected, "; ".join(found), detail)


def normalized(value: str) -> str:
    return " ".join(value.split())


def parse_html_text(text: str) -> Element:
    parser = TreeParser()
    parser.feed(text)
    parser.close()
    return parser.root


def parse_html(path: Path) -> Element:
    return parse_html_text(path.read_text(encoding="utf-8"))


def walk(node: Element) -> Iterable[Element]:
    yield node
    for child in node.children:
        if isinstance(child, Element):
            yield from walk(child)


def elements(node: Element, *, tag: str | None = None, cls: str | None = None) -> list[Element]:
    output = []
    for item in walk(node):
        if tag is not None and item.tag != tag:
            continue
        if cls is not None and cls not in (item.attrs.get("class") or "").split():
            continue
        output.append(item)
    return output


def text_content(node: Element) -> str:
    chunks: list[str] = []
    for child in node.children:
        chunks.append(text_content(child) if isinstance(child, Element) else child)
    return normalized(" ".join(chunks))


def first_by_id(node: Element, value: str) -> Element | None:
    return next((item for item in walk(node) if item.attrs.get("id") == value), None)


def public_html_paths() -> list[Path]:
    paths = list(ROOT.glob("*.html"))
    docs = ROOT / "docs"
    if docs.is_dir():
        paths.extend(docs.rglob("*.html"))
    return sorted((path for path in paths if path.is_file()), key=lambda p: p.relative_to(ROOT).as_posix())


def nav_paths() -> list[Path]:
    paths = public_html_paths()
    if TEMPLATE.is_file():
        paths.append(TEMPLATE)
    return paths


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def fingerprint(node: Element) -> tuple:
    children = []
    for child in node.children:
        if isinstance(child, Element):
            children.append(fingerprint(child))
        else:
            value = normalized(child)
            if value:
                children.append(("#text", value))
    return (node.tag, tuple(sorted(node.attrs.items())), tuple(children))


def marker_region(text: str, start: str, end: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        fail(f"one ordered {start}/{end} marker pair", f"counts {text.count(start)}/{text.count(end)}")
    left = text.index(start) + len(start)
    right = text.index(end)
    if left >= right:
        fail("start marker before end marker", f"offsets {left}/{right}")
    return text[left:right]


def check_arch_1() -> str:
    paths = nav_paths()
    required = {"index.html", "projects.html", "reach-out.html", "Article-Spec-Pack-v1/publication/templates/article.html"}
    missing_required = sorted(required - {rel(path) for path in paths})
    issues = [f"missing required nav surface {item}" for item in missing_required]
    fingerprints: list[tuple[str, tuple]] = []
    for path in paths:
        tree = parse_html(path)
        navs = elements(tree, tag="nav", cls="nav")
        if len(navs) != 1:
            issues.append(f"{rel(path)} has {len(navs)} primary navs")
            continue
        nav = navs[0]
        logos = elements(nav, tag="a", cls="nav__logo")
        if len(logos) != 1 or logos[0].attrs.get("href") != "/" or text_content(logos[0]) != "JH":
            issues.append(f"{rel(path)} logo is not JH -> /")
        links = elements(nav, tag="a", cls="nav__link")
        if len(links) != 4:
            issues.append(f"{rel(path)} has {len(links)} nav items")
        else:
            for number, (anchor, (label, href)) in enumerate(zip(links, EXPECTED_NAV), 1):
                if anchor.attrs.get("href") != href:
                    issues.append(f"{rel(path)} {label} href={anchor.attrs.get('href')!r}")
                if label not in text_content(anchor):
                    issues.append(f"{rel(path)} item {number} lacks label {label!r}")
                nums = elements(anchor, tag="span", cls="nav__number")
                if len(nums) != 1 or text_content(nums[0]) != f"{number:02d}.":
                    issues.append(f"{rel(path)} {label} number is not {number:02d}.")
        fingerprints.append((rel(path), fingerprint(nav)))
    if fingerprints:
        canonical_name, canonical = fingerprints[0]
        for name, candidate in fingerprints[1:]:
            if candidate != canonical:
                issues.append(f"{name} nav differs structurally from {canonical_name}")
    require_no_issues("identical canonical four-item nav on every discovered public HTML file and template", issues)
    return f"{len(paths)} dynamically discovered nav surfaces match the canonical block"


def check_arch_2() -> str:
    issues = []
    for path in nav_paths():
        tree = parse_html(path)
        navs = elements(tree, tag="nav", cls="nav")
        matches = ([item for item in elements(navs[0], tag="a") if item.attrs.get("href") == EXPECTED_NAV[-1][1]]
                   if len(navs) == 1 else [])
        if len(matches) != 1:
            issues.append(f"{rel(path)} has {len(matches)} Agent Telemetry nav anchors")
            continue
        anchor = matches[0]
        rel_tokens = set((anchor.attrs.get("rel") or "").split())
        if anchor.attrs.get("target") != "_blank" or not {"noopener", "noreferrer"}.issubset(rel_tokens):
            issues.append(f"{rel(path)} lacks target/rel protection")
        accessible = normalized((anchor.attrs.get("aria-label") or "") + " " + text_content(anchor)).lower()
        if "new tab" not in accessible and "external" not in accessible and "↗" not in accessible:
            issues.append(f"{rel(path)} lacks a marked external/new-tab indicator")
    for path in public_html_paths() + [TEMPLATE]:
        for item in walk(parse_html(path)):
            if item.tag in {"div", "span"} and item.attrs.get("aria-label") and not item.attrs.get("role"):
                issues.append(f"{rel(path)} names a generic {item.tag} without a conforming role")
    require_no_issues("protected new-tab attributes and an external indicator on every copy", issues)
    return f"Agent Telemetry is protected and marked on {len(nav_paths())} surfaces"


def check_arch_3() -> str:
    project = ROOT / "projects.html"
    generator = ROOT / ".github/scripts/refresh_pinned_projects.py"
    workflow = ROOT / ".github/workflows/refresh-pinned-projects.yml"
    issues = []
    for path in (project, generator, workflow, CONFIG):
        if not path.is_file():
            issues.append(f"missing {rel(path)}")
    if project.is_file():
        text = project.read_text(encoding="utf-8")
        if text.count(PROJECT_START) != 1 or text.count(PROJECT_END) != 1 or text.index(PROJECT_START) >= text.index(PROJECT_END):
            issues.append("projects.html lacks one ordered pinned-project marker pair")
        else:
            project_tree = parse_html_text(marker_region(text, PROJECT_START, PROJECT_END))
            project_cards = elements(project_tree, cls="project-card")
            if len(project_cards) != 6:
                issues.append(f"projects.html marker region renders {len(project_cards)} cards instead of 6")
            for index, card in enumerate(project_cards, start=1):
                classes = (card.attrs.get("class") or "").split()
                anchors = elements(card, tag="a")
                if "reveal-on-scroll" not in classes or not elements(card, cls="project-card__content") or not elements(card, cls="project-card__footer") or not elements(card, cls="project-stats"):
                    issues.append(f"projects.html card {index} is not aligned with the generated styled structure")
                stat_groups = [item for item in elements(card, cls="project-stats") if item.attrs.get("role") == "group" and item.attrs.get("aria-label")]
                named_stats = [item for item in elements(card, cls="project-stat") if item.attrs.get("role") == "img" and item.attrs.get("aria-label")]
                if len(stat_groups) != 1 or len(named_stats) != 2:
                    issues.append(f"projects.html card {index} has nonconforming ARIA statistics")
                if not any((anchor.attrs.get("href") or "").startswith("https://github.com/josiahH-cf/") for anchor in anchors):
                    issues.append(f"projects.html card {index} lacks an explicit owner repository link")
    if CONFIG.is_file():
        try:
            config = json.loads(CONFIG.read_text(encoding="utf-8"))
            expected = {
                "target_schema_version": "1.1.0",
                "pinned_projects_file": "projects.html",
                "pinned_projects_start_marker": PROJECT_START,
                "pinned_projects_end_marker": PROJECT_END,
            }
            for key, value in expected.items():
                if config.get(key) != value:
                    issues.append(f"config {key}={config.get(key)!r}, expected {value!r}")
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"publication config unreadable: {exc}")
    generator_text = generator.read_text(encoding="utf-8") if generator.is_file() else ""
    for token in (
        "GITHUB_TOKEN", "api.github.com/graphql", "josiahH-cf", "pinnedItems", "name",
        "description", "url", "primaryLanguage", "stargazerCount", "forkCount", "updatedAt",
        "--response-file", "--target", "--json",
    ):
        if token not in generator_text:
            issues.append(f"generator lacks {token!r}")
    workflow_text = workflow.read_text(encoding="utf-8") if workflow.is_file() else ""
    workflow_expectations = {
        "daily cron 06:17 UTC": re.search(r"cron\s*:\s*[\"']?17\s+6\s+\*\s+\*\s+\*", workflow_text),
        "workflow_dispatch": "workflow_dispatch" in workflow_text,
        "contents write permission": bool(re.search(r"contents\s*:\s*write", workflow_text)),
        "Pages build permission": bool(re.search(r"pages\s*:\s*write", workflow_text)),
        "checkout v7": "actions/checkout@v7" in workflow_text,
        "refresh concurrency": "refresh-pinned-projects" in workflow_text and bool(re.search(r"cancel-in-progress\s*:\s*false", workflow_text)),
        "secret token mapping": "GITHUB_TOKEN" in workflow_text and "secrets.GITHUB_TOKEN" in workflow_text,
        "generator invocation": "refresh_pinned_projects.py" in workflow_text,
        "fail-closed shell guard": "set -euo pipefail" in workflow_text and "release_names=\"$(" in workflow_text and "asset_names=\"$(" in workflow_text,
        "stale checkout guard": "git rev-parse origin/main" in workflow_text and "origin/main moved" in workflow_text,
        "explicit Pages build and verification": "--method POST" in workflow_text and "pages/builds" in workflow_text and "pages/builds/latest" in workflow_text and 'latest_status" == "built"' in workflow_text and 'latest_status" == "errored"' in workflow_text,
    }
    for label, present in workflow_expectations.items():
        if not present:
            issues.append(f"workflow lacks {label}")
    client_files = public_html_paths() + [ROOT / "script.js"]
    leaked = [rel(path) for path in client_files if path.is_file() and "GITHUB_TOKEN" in path.read_text(encoding="utf-8")]
    if leaked:
        issues.append(f"client token reference in {', '.join(leaked)}")
    require_no_issues("marker-driven GraphQL generator and isolated scheduled workflow", issues)
    return "projects markers, schema 1.1.0 generator contract, fail-closed schedule, token isolation, and verified Pages build are present"


def reach_out_issues() -> list[str]:
    path = ROOT / "reach-out.html"
    if not path.is_file():
        return ["reach-out.html is missing"]
    tree = parse_html(path)
    whole_text = text_content(tree)
    issues = []
    if normalized(ABOUT) not in whole_text:
        issues.append("exact two-sentence About is absent")
    details = {
        "Role": "Senior Security Engineer at Coalfire",
        "Focus": "AI Systems, Cloud Security, DevSecOps",
        "Platforms": "AWS, GCP, Azure",
        "Expertise": "Python, Terraform, LLM APIs, RAG",
    }
    for label, value in details.items():
        if label not in whole_text or value not in whole_text:
            issues.append(f"missing {label} detail/value")
    role_links = [item for item in elements(tree, tag="a") if item.attrs.get("href") == "https://www.coalfire.com/"]
    if len(role_links) != 1 or text_content(role_links[0]) != details["Role"]:
        issues.append("Role value is not the Coalfire link")
    elif role_links[0].attrs.get("target") != "_blank" or not {"noopener", "noreferrer"}.issubset(set((role_links[0].attrs.get("rel") or "").split())):
        issues.append("Coalfire Role link lacks protected new-tab attributes")
    elif "opens in a new tab" not in (role_links[0].attrs.get("aria-label") or "") or "detail-card__external-link" not in (role_links[0].attrs.get("class") or "").split():
        issues.append("Coalfire Role link lacks a visible/accessibly named external marker")
    form = first_by_id(tree, "contactForm")
    if form is None or form.tag != "form":
        issues.append("form#contactForm is absent")
    else:
        controls = {item.attrs.get("name"): item for item in walk(form) if item.tag in {"input", "textarea"}}
        for name in ("name", "email", "message"):
            if name not in controls or "required" not in controls[name].attrs:
                issues.append(f"required {name} field is absent")
            labels = [item for item in elements(form, tag="label") if item.attrs.get("for") == controls.get(name, Element("", {})).attrs.get("id")]
            if not labels or "required" not in text_content(labels[0]).casefold():
                issues.append(f"{name} field is not visibly marked required")
        submits = [item for item in elements(form, tag="button") if item.attrs.get("type") == "submit"]
        if len(submits) != 1 or "disabled" not in submits[0].attrs:
            issues.append("submit button does not ship disabled for the placeholder endpoint")
    hrefs = {item.attrs.get("href") for item in elements(tree, tag="a")}
    for href in ("mailto:josiah.hunter.it@gmail.com", "https://github.com/josiahH-cf", "https://www.linkedin.com/in/josiahhunter/"):
        if href not in hrefs:
            issues.append(f"missing direct contact link {href}")
    direct_groups = [item for item in elements(tree, cls="contact__links") if item.attrs.get("role") == "group" and item.attrs.get("aria-label")]
    if len(direct_groups) != 1:
        issues.append("direct contact links lack a valid named group role")
    if "The contact form is not configured yet. Email me directly instead." not in whole_text:
        issues.append("honest unconfigured fallback is not initially visible")
    return issues


def check_arch_4() -> str:
    issues = reach_out_issues()
    sources = [path for path in public_html_paths() if path.name == "reach-out.html"]
    sources.extend(path for path in ROOT.glob("*.js") if path.is_file())
    joined = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    declarations = re.findall(r"\bconst\s+CONTACT_FORM_ENDPOINT\s*=", joined)
    if len(declarations) != 1:
        issues.append(f"found {len(declarations)} CONTACT_FORM_ENDPOINT const declarations")
    if "PASTE_FORM_FORWARDING_ENDPOINT_HERE" not in joined:
        issues.append("endpoint placeholder is absent")
    require_no_issues("exact About/details/Role/contact form with one safe endpoint constant", issues)
    return "Reach Out contains the exact About, four details, protected Role link, direct links, and safe form"


def resolve_site_link(source: Path, href: str) -> tuple[str | None, str | None]:
    """Return a repository-relative target and fragment, or (None, None) externally."""
    parts = urlsplit(href)
    if parts.scheme in {"mailto", "tel"}:
        return None, None
    if parts.scheme in {"http", "https"} and parts.hostname != "theproductiveprompter.com":
        return None, None
    if parts.scheme and parts.scheme not in {"http", "https"}:
        return "!unsupported", parts.fragment
    raw_path = unquote(parts.path)
    if parts.netloc or raw_path.startswith("/"):
        target = raw_path.lstrip("/")
    elif raw_path:
        target = (PurePosixPath(rel(source)).parent / raw_path).as_posix()
    else:
        target = rel(source)
    target = os.path.normpath(target).replace("\\", "/")
    if target in {"", "."} or raw_path.endswith("/"):
        target = f"{target.rstrip('/') + '/' if target not in {'', '.'} else ''}index.html"
    return target, unquote(parts.fragment)


def broken_internal_links() -> list[str]:
    issues = []
    trees = {rel(path): parse_html(path) for path in public_html_paths()}
    for path in public_html_paths():
        for anchor in elements(trees[rel(path)], tag="a"):
            href = anchor.attrs.get("href")
            if href is None or not href.strip():
                issues.append(f"{rel(path)} has an empty anchor href")
                continue
            target, fragment = resolve_site_link(path, href)
            if target is None:
                continue
            if target == "!unsupported" or target.startswith("../") or not (ROOT / target).is_file():
                issues.append(f"{rel(path)} -> {href!r} resolves to missing {target}")
                continue
            if target.endswith(".html") and fragment:
                target_tree = trees.get(target) or parse_html(ROOT / target)
                if first_by_id(target_tree, fragment) is None:
                    issues.append(f"{rel(path)} -> {href!r} has missing fragment #{fragment}")
            parts = urlsplit(href)
            if target == "docs/article.html" and "post" in parse_qs(parts.query):
                for post in parse_qs(parts.query)["post"]:
                    if not (ROOT / "docs" / post).is_file():
                        issues.append(f"{rel(path)} -> {href!r} references missing post {post}")
    return issues


def check_arch_5() -> str:
    index = ROOT / "index.html"
    tree = parse_html(index)
    issues = []
    for removed_id in ("about", "contact", "projects"):
        if first_by_id(tree, removed_id) is not None:
            issues.append(f"index still contains id={removed_id!r}")
    for path in public_html_paths():
        for anchor in elements(parse_html(path), tag="a"):
            href = anchor.attrs.get("href") or ""
            if urlsplit(href).fragment in {"about", "contact", "projects"}:
                issues.append(f"{rel(path)} retains removed fragment link {href!r}")
    hero_ctas = elements(tree, tag="a", cls="hero__cta")
    if not any(item.attrs.get("href") == "/docs/blog.html" for item in hero_ctas):
        issues.append("home Blog hero CTA does not route to /docs/blog.html")
    if not any(item.attrs.get("href") == "/projects.html" for item in hero_ctas):
        issues.append("home Projects hero CTA does not route to /projects.html")
    split_links = elements(tree, tag="a", cls="split-card__side")
    if {item.attrs.get("href") for item in split_links} != {"/docs/blog.html", "/projects.html"}:
        issues.append("home split card does not route to Blog and Projects documents")
    issues.extend(broken_internal_links())
    require_no_issues("home decomposition and a fully resolving same-origin link graph", issues)
    return f"removed home sections/anchors are absent and {len(public_html_paths())} pages have resolving links"


def check_arch_6() -> str:
    matches = []
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [name for name in dirs if name not in {".git", "__pycache__", "node_modules"}]
        for name in names:
            path = Path(base) / name
            try:
                if PROHIBITED_CREDIT.encode() in path.read_bytes():
                    matches.append(rel(path))
            except OSError:
                pass
    require_no_issues("zero repository occurrences of the legacy footer credit", matches)
    return "legacy footer credit occurs zero times"


def check_arch_7() -> str:
    issues = []
    surfaces = public_html_paths() + [ROOT / "styles.css"]
    for path in surfaces:
        content = path.read_text(encoding="utf-8")
        for css_class in REMOVED_CLASSES:
            if css_class in content:
                issues.append(f"{rel(path)} retains {css_class}")
    tree = parse_html(ROOT / "index.html")
    titles = elements(tree, tag="title")
    if len(titles) != 1 or text_content(titles[0]) != f"Josiah Hunter | {BRAND}":
        issues.append("home title does not exactly match LinkedIn branding")
    taglines = elements(tree, cls="hero__tagline")
    if len(taglines) != 1 or text_content(taglines[0]) != BRAND:
        issues.append("hero tagline does not exactly match branding")
    descriptions = [item for item in elements(tree, tag="meta") if (item.attrs.get("name") or "").lower() == "description"]
    if len(descriptions) != 1 or descriptions[0].attrs.get("content") != f"Josiah Hunter | {BRAND}":
        issues.append("home meta description does not exactly match branding")
    require_no_issues("exact branding and no enumerated subtext elements or styles", issues)
    return "title/meta/tagline match and all enumerated declutter classes are absent"


def parse_xml(path: Path) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        fail(f"valid XML in {rel(path)}", str(exc))


def check_arch_8() -> str:
    sitemap_path, feed_path = ROOT / "sitemap.xml", ROOT / "feed.xml"
    sitemap = parse_xml(sitemap_path)
    feed = parse_xml(feed_path)
    locs = [normalized(item.text or "") for item in sitemap.findall("{*}url/{*}loc")]
    expected = {
        "https://theproductiveprompter.com/projects.html",
        "https://theproductiveprompter.com/reach-out.html",
    }
    issues = [f"sitemap missing {url}" for url in sorted(expected - set(locs))]
    sitemap_text = sitemap_path.read_text(encoding="utf-8")
    region = marker_region(sitemap_text, ARTICLE_MARKERS[2], ARTICLE_MARKERS[3])
    for url in expected:
        if url in region:
            issues.append(f"{url} was inserted inside protected Article Flow markers")
    if any(urlsplit(url).fragment in {"about", "contact", "projects"} for url in locs):
        issues.append("sitemap retains a removed section URL")
    if feed.tag != "rss" or feed.find("channel") is None:
        issues.append("feed root/channel is not RSS")
    require_no_issues("valid sitemap/feed with both new URLs outside Article Flow markers", issues)
    return f"valid XML; sitemap has {len(locs)} URLs including both new pages"


def run_generator(response: Path, target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / ".github/scripts/refresh_pinned_projects.py"),
         "--response-file", str(response), "--target", str(target), "--json"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )


def check_beh_4() -> str:
    generator = ROOT / ".github/scripts/refresh_pinned_projects.py"
    if not generator.is_file():
        fail("runnable pinned-project generator", "generator is missing")
    fixture = json.loads(PROJECT_FIXTURE.read_text(encoding="utf-8"))
    nodes = fixture["data"]["user"]["pinnedItems"]["nodes"]
    shell = "prefix sentinel\n" + PROJECT_START + "\nold cards\n" + PROJECT_END + "\nsuffix sentinel\n"
    issues = []
    with tempfile.TemporaryDirectory(prefix="pinned-project-check-") as tmp:
        target = Path(tmp) / "projects.html"
        target.write_bytes(shell.encode("utf-8"))
        completed = run_generator(PROJECT_FIXTURE, target)
        if completed.returncode != 0:
            fail("generator exit 0 for fixed six-node fixture", f"exit {completed.returncode}", completed.stderr or completed.stdout)
        output = target.read_text(encoding="utf-8")
        if not output.startswith("prefix sentinel\n" + PROJECT_START) or not output.endswith(PROJECT_END + "\nsuffix sentinel\n"):
            issues.append("generator changed bytes outside the marker region")
        region = marker_region(output, PROJECT_START, PROJECT_END)
        tree = parse_html_text(region)
        cards = elements(tree, cls="project-card")
        if len(cards) != 6:
            issues.append(f"generated {len(cards)} project cards")
        for index, card in enumerate(cards, start=1):
            required_classes = (
                "project-card__content", "project-card__header", "project-card__title",
                "project-card__description", "project-card__footer", "project-stats",
                "project-card__links",
            )
            missing_classes = [name for name in required_classes if not elements(card, cls=name)]
            if missing_classes:
                issues.append(f"generated card {index} lacks styled structure {missing_classes}")
            stat_groups = [item for item in elements(card, cls="project-stats") if item.attrs.get("role") == "group" and item.attrs.get("aria-label")]
            stats = [item for item in elements(card, cls="project-stat") if item.attrs.get("role") == "img" and item.attrs.get("aria-label")]
            if len(stat_groups) != 1 or len(stats) != 2:
                issues.append(f"generated card {index} lacks conforming named statistics")
        names = [node["name"] for node in nodes]
        positions = [region.find(name) for name in names]
        if any(index < 0 for index in positions) or positions != sorted(positions):
            issues.append("repository order differs from the GraphQL response")
        hrefs = {item.attrs.get("href") for item in elements(tree, tag="a")}
        missing = [node["url"] for node in nodes if node["url"] not in hrefs]
        if missing:
            issues.append(f"missing repository links {missing}")
        if "<script>window.fixturePwned" in region or "&lt;script&gt;" not in region:
            issues.append("adversarial description was not HTML-escaped")
        if "No description provided." not in text_content(tree) or "Not specified" not in text_content(tree):
            issues.append("null description/language fallbacks are absent")
        crlf_shell = (
            b"prefix sentinel\r\n" + PROJECT_START.encode() + b"\r\nold cards\r\n"
            + PROJECT_END.encode() + b"\r\nsuffix sentinel\r\n"
        )
        target.write_bytes(crlf_shell)
        crlf_run = run_generator(PROJECT_FIXTURE, target)
        crlf_output = target.read_bytes()
        expected_prefix = b"prefix sentinel\r\n" + PROJECT_START.encode()
        expected_suffix = PROJECT_END.encode() + b"\r\nsuffix sentinel\r\n"
        if crlf_run.returncode != 0 or not crlf_output.startswith(expected_prefix) or not crlf_output.endswith(expected_suffix):
            issues.append("CRLF bytes outside the marker region were not preserved")
        target.write_bytes(shell.encode("utf-8"))
        completed = run_generator(PROJECT_FIXTURE, target)
        if completed.returncode != 0:
            issues.append("generator could not restore the LF idempotence target")
        before = target.read_bytes()
        rerun = run_generator(PROJECT_FIXTURE, target)
        if rerun.returncode != 0 or target.read_bytes() != before:
            issues.append("identical input did not produce byte-stable output")
        invalid_cases = []
        variants = {
            "GraphQL errors": {"errors": [{"message": "fixture rejection"}]},
            "five nodes": copy.deepcopy(fixture),
            "duplicate node": copy.deepcopy(fixture),
            "malformed URL": copy.deepcopy(fixture),
            "name URL mismatch": copy.deepcopy(fixture),
            "dot-segment repository": copy.deepcopy(fixture),
            "negative count": copy.deepcopy(fixture),
            "malformed timestamp": copy.deepcopy(fixture),
        }
        variants["five nodes"]["data"]["user"]["pinnedItems"]["nodes"] = copy.deepcopy(nodes[:5])
        variants["duplicate node"]["data"]["user"]["pinnedItems"]["nodes"][5] = copy.deepcopy(nodes[0])
        variants["malformed URL"]["data"]["user"]["pinnedItems"]["nodes"][0]["url"] = "javascript:alert(1)"
        variants["name URL mismatch"]["data"]["user"]["pinnedItems"]["nodes"][0]["name"] = "different-name"
        variants["dot-segment repository"]["data"]["user"]["pinnedItems"]["nodes"][0]["name"] = ".."
        variants["dot-segment repository"]["data"]["user"]["pinnedItems"]["nodes"][0]["url"] = "https://github.com/josiahH-cf/.."
        variants["negative count"]["data"]["user"]["pinnedItems"]["nodes"][0]["forkCount"] = -1
        variants["malformed timestamp"]["data"]["user"]["pinnedItems"]["nodes"][0]["updatedAt"] = "yesterday"
        for label, payload in variants.items():
            response = Path(tmp) / f"invalid-{len(invalid_cases)}.json"
            response.write_text(json.dumps(payload), encoding="utf-8")
            target.write_bytes(shell.encode("utf-8"))
            rejected = run_generator(response, target)
            if rejected.returncode == 0 or target.read_bytes() != shell.encode("utf-8"):
                invalid_cases.append(label)
        if invalid_cases:
            issues.append(f"invalid input accepted or rewrote target: {', '.join(invalid_cases)}")
        invalid_targets = []
        marker_variants = {
            "out-of-order markers": "prefix\n" + PROJECT_END + "\nold\n" + PROJECT_START + "\nsuffix\n",
            "duplicate start marker": "prefix\n" + PROJECT_START + "\n" + PROJECT_START + "\n" + PROJECT_END + "\nsuffix\n",
        }
        for label, malformed_target in marker_variants.items():
            original = malformed_target.encode("utf-8")
            target.write_bytes(original)
            rejected = run_generator(PROJECT_FIXTURE, target)
            if rejected.returncode == 0 or target.read_bytes() != original:
                invalid_targets.append(label)
        if invalid_targets:
            issues.append(f"invalid marker layouts accepted or rewritten: {', '.join(invalid_targets)}")
    require_no_issues("six ordered escaped styled cards, exact outside bytes, and atomic hostile-input rejection", issues)
    return "hostile fixture generated six styled cards; CRLF/LF bytes were stable and ten invalid cases were rejected atomically"


def check_beh_5() -> str:
    issues = reach_out_issues()
    require_no_issues("renderable exact About/details and protected Coalfire Role link", issues)
    return "Reach Out's visible content and Role-link contract are present"


def check_beh_7() -> str:
    issues = []
    for path in public_html_paths():
        content = path.read_text(encoding="utf-8")
        visible = text_content(parse_html_text(content))
        if PROHIBITED_CREDIT in visible:
            issues.append(f"{rel(path)} renders the legacy credit")
        for phrase in REMOVED_BLURB_PREFIXES:
            if phrase in visible:
                issues.append(f"{rel(path)} renders removed blurb beginning {phrase!r}")
    require_no_issues("no removed credit or explanatory blurbs in rendered output", issues)
    return f"{len(public_html_paths())} public documents contain none of the removed visible copy"


def check_pres_1() -> str:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    start, end = config["latest_card_start_marker"], config["latest_card_end_marker"]
    issues = []
    link_sets = []
    for name in ("index.html", "docs/blog.html"):
        content = (ROOT / name).read_text(encoding="utf-8")
        region = marker_region(content, start, end)
        tree = parse_html_text(region)
        cards = elements(tree, cls="article-card")
        links = [item.attrs.get("href") for item in elements(tree, tag="a", cls="article-card__link")]
        if not cards or len(links) != len(cards):
            issues.append(f"{name} marker region has {len(cards)} cards and {len(links)} title links")
        resolved_targets = []
        for href in links:
            target, _ = resolve_site_link(ROOT / name, href or "")
            if not target or not (ROOT / target).is_file():
                issues.append(f"{name} article card target {href!r} does not open")
            else:
                resolved_targets.append(target)
        link_sets.append((name, resolved_targets))
    if len(link_sets) == 2 and link_sets[0][1] != link_sets[1][1]:
        issues.append("home and Blog Article Flow card sequences diverge")
    require_no_issues("matching, nonempty Article Flow marker cards whose pages exist", issues)
    return f"home and Blog preserve {len(link_sets[0][1]) if link_sets else 0} generated article cards and targets"


def check_pres_2() -> str:
    workflow = ROOT / ".github/workflows/publish-scheduled-articles.yml"
    script = ROOT / ".github/scripts/publish_scheduled_articles.py"
    issues = []
    if not workflow.is_file() or not script.is_file():
        issues.append("scheduled-article workflow/script is missing")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "index.html", ROOT / "docs/blog.html", ROOT / "sitemap.xml", ROOT / "feed.xml"))
    for marker in ARTICLE_MARKERS:
        expected_count = 2 if "LATEST" in marker else 1
        if combined.count(marker) != expected_count:
            issues.append(f"Article Flow marker {marker} occurs {combined.count(marker)} times; expected {expected_count}")
    if PROJECT_START in ARTICLE_MARKERS or PROJECT_END in ARTICLE_MARKERS:
        issues.append("pinned-project markers collide with Article Flow markers")
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "Article-Spec-Pack-v1/tests", "-p", "test_article_flow.py"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180,
    )
    if completed.returncode != 0:
        issues.append("Article Flow test suite failed: " + normalized(completed.stdout)[-800:])
    match = re.search(r"Ran\s+(\d+)\s+tests?", completed.stdout)
    if not match or int(match.group(1)) < 33:
        issues.append(f"Article Flow baseline did not report at least 33 tests: {normalized(completed.stdout)[-300:]}")
    require_no_issues("scheduled publication intact, disjoint markers, and all 33+ Article Flow tests passing", issues)
    return f"scheduled publisher/markers are intact; Article Flow reports {match.group(1)} passing tests"


def all_hrefs(path: Path) -> set[str]:
    return {item.attrs["href"] for item in walk(parse_html(path)) if item.attrs.get("href")}


def check_pres_7() -> str:
    baseline = json.loads(PRESERVATION_FIXTURE.read_text(encoding="utf-8"))
    issues = broken_internal_links()
    preserved = 0
    for source, expected in baseline["external_links"].items():
        path = ROOT / source
        if not path.is_file():
            issues.append(f"baseline source removed: {source}")
            continue
        hrefs = all_hrefs(path)
        for href in expected:
            parts = urlsplit(href)
            if parts.scheme not in {"http", "https"} or not parts.netloc:
                issues.append(f"invalid baseline URL: {href}")
            elif href not in hrefs:
                issues.append(f"{source} dropped preserved external link {href}")
            else:
                preserved += 1
    require_no_issues("all current internal links resolve and every non-excluded external baseline link remains", issues)
    return f"internal graph resolves and {preserved} baseline external source/link pairs remain"


def check_pres_8() -> str:
    baseline = json.loads(PRESERVATION_FIXTURE.read_text(encoding="utf-8"))
    feed_path, sitemap_path = ROOT / "feed.xml", ROOT / "sitemap.xml"
    parse_xml(feed_path)
    sitemap = parse_xml(sitemap_path)
    digest = hashlib.sha256(feed_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    issues = []
    if digest != baseline["feed_sha256_lf"]:
        issues.append(f"feed content hash changed from {baseline['feed_sha256_lf']} to {digest}")
    for marker in ARTICLE_MARKERS[2:]:
        surface = sitemap_path if "SITEMAP" in marker else feed_path
        count = surface.read_text(encoding="utf-8").count(marker)
        if count != 1:
            issues.append(f"{rel(surface)} marker {marker} count is {count}")
    for loc in sitemap.findall("{*}url/{*}loc"):
        url = normalized(loc.text or "")
        target, _ = resolve_site_link(ROOT / "index.html", url)
        if target and not (ROOT / target).is_file():
            issues.append(f"sitemap URL {url} targets missing {target}")
    require_no_issues("valid XML, byte-preserved feed, intact XML markers, and resolving sitemap targets", issues)
    return "feed is content-identical to baseline; sitemap/feed markers and targets are valid"


STATIC_CHECKS: dict[str, tuple[str, str, Callable[[], str]]] = {
    "ARCH-1": ("architecture", "Canonical navigation", check_arch_1),
    "ARCH-2": ("architecture", "External nav safety", check_arch_2),
    "ARCH-3": ("architecture", "Pinned-project automation", check_arch_3),
    "ARCH-4": ("architecture", "Reach Out structure", check_arch_4),
    "ARCH-5": ("architecture", "Home decomposition and links", check_arch_5),
    "ARCH-6": ("architecture", "Footer credit removed", check_arch_6),
    "ARCH-7": ("architecture", "Branding and declutter", check_arch_7),
    "ARCH-8": ("architecture", "Discoverability XML", check_arch_8),
    "BEH-4": ("behavior", "Deterministic project generation", check_beh_4),
    "BEH-5": ("behavior", "Reach Out visible contract", check_beh_5),
    "BEH-7": ("behavior", "Removed copy absent", check_beh_7),
    "PRES-1": ("preservation", "Article cards and targets", check_pres_1),
    "PRES-2": ("preservation", "Scheduled Article Flow", check_pres_2),
    "PRES-7": ("preservation", "Preserved link graph", check_pres_7),
    "PRES-8": ("preservation", "Feed and sitemap", check_pres_8),
}
BROWSER_IDS = {
    "BEH-1": ("behavior", "Nav remains visible"),
    "BEH-2": ("behavior", "Internal nav changes documents"),
    "BEH-3": ("behavior", "Telemetry opens a new tab"),
    "BEH-6": ("behavior", "Contact delivery states"),
    "PRES-3": ("preservation", "31 Days fixed-clock reveal"),
    "PRES-4": ("preservation", "Mobile menu"),
    "PRES-5": ("preservation", "Reveal and reduced motion"),
    "PRES-6": ("preservation", "Social sidebar and clipboard"),
}


def execute_static(check_id: str) -> Result:
    suite, title, function = STATIC_CHECKS[check_id]
    try:
        detail = function()
        return Result(check_id, suite, title, "PASS", detail)
    except CheckFailure as exc:
        return Result(check_id, suite, title, "FAIL", exc.detail, exc.expected, exc.actual)
    except Exception as exc:  # A crashed gate is a failed gate, never a silent skip.
        return Result(check_id, suite, title, "FAIL", f"check raised {type(exc).__name__}: {exc}", "check completes", "exception")


def execute_browser() -> list[Result]:
    harness = TESTS / "browser_checks.mjs"
    if not harness.is_file() or shutil.which("node") is None:
        reason = "browser harness missing" if not harness.is_file() else "node executable unavailable"
        results = [Result(check_id, suite, title, "FAIL", reason, "observable browser check passes", reason)
                   for check_id, (suite, title) in BROWSER_IDS.items()]
        results.append(Result("BEH-8", "behavior", "Preserved browser behaviors", "FAIL", reason,
                              "PRES-3 through PRES-6 pass", reason))
        return results
    completed = subprocess.run(
        ["node", str(harness), "--root", str(ROOT), "--json"], cwd=ROOT,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
    )
    try:
        payload = json.loads(completed.stdout)
        incoming = {item["id"]: item for item in payload["results"]}
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        detail = f"invalid browser JSON ({exc}): {normalized(completed.stderr or completed.stdout)[-500:]}"
        results = [Result(check_id, suite, title, "FAIL", detail, "valid JSON result", "unparseable output")
                   for check_id, (suite, title) in BROWSER_IDS.items()]
        results.append(Result("BEH-8", "behavior", "Preserved browser behaviors", "FAIL", detail,
                              "PRES-3 through PRES-6 pass", "browser output unavailable"))
        return results
    output = []
    for check_id, (suite, title) in BROWSER_IDS.items():
        item = incoming.get(check_id)
        if item is None:
            output.append(Result(check_id, suite, title, "FAIL", "browser harness omitted this required ID", "named result", "missing"))
            continue
        status = str(item.get("status", "FAIL")).upper()
        if status != "PASS":
            status = "FAIL"
        output.append(Result(check_id, suite, title, status, str(item.get("detail", "")),
                             str(item.get("expected", "")), str(item.get("actual", ""))))
    preserved = [item for item in output if item.id in {"PRES-3", "PRES-4", "PRES-5", "PRES-6"}]
    preserved_ok = len(preserved) == 4 and all(item.status == "PASS" for item in preserved)
    output.append(Result(
        "BEH-8", "behavior", "Preserved browser behaviors", "PASS" if preserved_ok else "FAIL",
        "PRES-3 through PRES-6 all pass" if preserved_ok else "one or more browser preservation checks failed",
        "PRES-3 through PRES-6 pass", ", ".join(f"{item.id}={item.status}" for item in preserved),
    ))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("all", "architecture", "behavior", "preservation"), default="all")
    parser.add_argument("--json", action="store_true", help="emit the complete report as JSON")
    args = parser.parse_args()
    wanted = {"architecture", "behavior", "preservation"} if args.suite == "all" else {args.suite}
    results = [execute_static(check_id) for check_id, (suite, _, _) in STATIC_CHECKS.items() if suite in wanted]
    if wanted & {"behavior", "preservation"}:
        results.extend(result for result in execute_browser() if result.suite in wanted)
    order = {"architecture": 0, "behavior": 1, "preservation": 2}
    results.sort(key=lambda item: (order[item.suite], int(item.id.split("-")[1])))
    if args.json:
        print(json.dumps({"ok": all(item.status == "PASS" for item in results), "results": [item.__dict__ for item in results]}, indent=2))
    else:
        for suite in ("architecture", "behavior", "preservation"):
            selected = [item for item in results if item.suite == suite]
            if not selected:
                continue
            print(f"\n{suite.upper()} ({sum(item.status == 'PASS' for item in selected)}/{len(selected)} PASS)")
            for item in selected:
                print(f"  [{item.status}] {item.id} {item.title}: {item.detail}")
                if item.status != "PASS":
                    print(f"         expected: {item.expected}")
                    print(f"         actual:   {item.actual}")
        print("\nOVERALL: " + ("PASS" if all(item.status == "PASS" for item in results) else "FAIL"))
    return 0 if all(item.status == "PASS" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
