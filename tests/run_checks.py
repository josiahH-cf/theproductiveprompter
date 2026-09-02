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
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable
from urllib.parse import parse_qs, unquote, urlsplit
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
TEMPLATE = ROOT / "Article-Spec-Pack-v1/publication/templates/article.html"
CONFIG = ROOT / "Article-Spec-Pack-v1/publication/theproductiveprompter.json"
PROJECT_FIXTURE = TESTS / "fixtures/pinned_projects_graphql.json"
PROJECT_LIVE_SNAPSHOT = TESTS / "fixtures/pinned_projects_start_snapshot.json"
PRESERVATION_FIXTURE = TESTS / "fixtures/preservation_baseline.json"
PROJECT_START = "<!-- PINNED_PROJECTS_START -->"
PROJECT_END = "<!-- PINNED_PROJECTS_END -->"
ACTIVITY_START = "<!-- GITHUB_ACTIVITY_START -->"
ACTIVITY_END = "<!-- GITHUB_ACTIVITY_END -->"
ACTIVITY_AS_OF = "2026-09-01T13:02:35Z"
ACTIVITY_FROM = "2026-01-01T00:00:00Z"
ACTIVITY_TO = "2026-12-31T23:59:59Z"
DASHBOARD_URL = "https://github.com/josiahH-cf"
EXPECTED_PROJECT_COUNT = 4
EXPECTED_ACTIVITY = {
    "contributions": 1485,
    "commits": 1343,
    "pull-requests": 125,
}
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
INTRO_PROMPT = "I love to chat about..."
INTRO_TOPICS = (("🔐", "Security"), ("☁️", "Cloud"), ("🧠", "AI"))
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
        full_tree = parse_html_text(text)
        page_headers = elements(full_tree, tag="header", cls="page-header")
        if len(page_headers) != 1:
            issues.append("projects.html lacks one page header")
        else:
            header_children = [
                child for child in page_headers[0].children if isinstance(child, Element)
            ]
            h1_index = next(
                (index for index, child in enumerate(header_children) if child.tag == "h1"),
                -1,
            )
            subtitles = elements(page_headers[0], cls="projects-page__subtitle")
            if (
                len(subtitles) != 1
                or text_content(subtitles[0]) != "top projects"
                or h1_index < 0
                or h1_index + 1 >= len(header_children)
                or header_children[h1_index + 1] is not subtitles[0]
            ):
                issues.append("projects.html lacks the exact 'top projects' subtitle directly after its h1")
        if text.count(PROJECT_START) != 1 or text.count(PROJECT_END) != 1 or text.index(PROJECT_START) >= text.index(PROJECT_END):
            issues.append("projects.html lacks one ordered pinned-project marker pair")
        else:
            project_tree = parse_html_text(marker_region(text, PROJECT_START, PROJECT_END))
            project_cards = elements(project_tree, cls="project-card")
            rendered_projects = []
            if len(project_cards) != EXPECTED_PROJECT_COUNT:
                issues.append(
                    f"projects.html marker region renders {len(project_cards)} cards "
                    f"instead of {EXPECTED_PROJECT_COUNT}"
                )
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
                title_links = [
                    anchor
                    for title in elements(card, cls="project-card__title")
                    for anchor in elements(title, tag="a")
                ]
                if len(title_links) == 1:
                    rendered_projects.append(
                        {
                            "name": normalized(text_content(title_links[0])).removesuffix("↗").strip(),
                            "url": title_links[0].attrs.get("href"),
                        }
                    )
                else:
                    issues.append(f"projects.html card {index} lacks one title link")
            try:
                live_snapshot = json.loads(PROJECT_LIVE_SNAPSHOT.read_text(encoding="utf-8"))
                pinned_items = live_snapshot["data"]["user"]["pinnedItems"]
                expected_projects = [
                    {"name": node["name"], "url": node["url"]}
                    for node in pinned_items["nodes"]
                ]
                if pinned_items.get("totalCount") != EXPECTED_PROJECT_COUNT:
                    issues.append("authenticated pin snapshot does not report four projects")
                if rendered_projects != expected_projects:
                    issues.append(
                        f"projects.html order/content {rendered_projects!r} differs from authenticated snapshot {expected_projects!r}"
                    )
            except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
                issues.append(f"authenticated pin snapshot is unreadable: {exc}")
        if text.count(ACTIVITY_START) != 1 or text.count(ACTIVITY_END) != 1 or text.index(ACTIVITY_START) >= text.index(ACTIVITY_END):
            issues.append("projects.html lacks one ordered GitHub-activity marker pair")
        else:
            activity_tree = parse_html_text(marker_region(text, ACTIVITY_START, ACTIVITY_END))
            headings = elements(activity_tree, tag="h2", cls="github-activity__title")
            years = elements(activity_tree, tag="time", cls="github-activity__year")
            statuses = elements(activity_tree, cls="github-activity__status")
            stat_lists = elements(activity_tree, tag="dl", cls="github-activity__highlights")
            metrics = elements(activity_tree, cls="github-activity-highlight")
            metric_keys = [item.attrs.get("data-github-metric") for item in metrics]
            rendered_year = years[0].attrs.get("datetime") if len(years) == 1 else ""
            if not re.fullmatch(r"\d{4}", rendered_year or "") or len(headings) != 1 or text_content(headings[0]) != f"{rendered_year} GitHub activity":
                issues.append("projects.html lacks a coherent generated current-year activity heading")
            else:
                now = datetime.now(timezone.utc)
                allowed_years = {now.year}
                if now.month == 1 and now.day == 1:
                    allowed_years.add(now.year - 1)
                if int(rendered_year) not in allowed_years:
                    issues.append(
                        f"projects.html activity year {rendered_year} is outside the daily rollover window"
                    )
            if len(statuses) != 1 or "year-to-date public contribution totals" not in text_content(statuses[0]).casefold() or "refreshed daily" not in text_content(statuses[0]).casefold():
                issues.append("projects.html lacks the year-to-date public scope and daily refresh cadence")
            if len(stat_lists) != 1 or len(metrics) != len(EXPECTED_ACTIVITY) or metric_keys != list(EXPECTED_ACTIVITY):
                issues.append("projects.html lacks the three ordered high-signal GitHub activity metrics")
            else:
                for metric in EXPECTED_ACTIVITY:
                    item = metrics[metric_keys.index(metric)]
                    values = elements(item, tag="dd", cls="github-activity-highlight__value")
                    labels = elements(item, tag="dt", cls="github-activity-highlight__label")
                    if len(values) != 1 or not re.fullmatch(r"\d{1,3}(?:,\d{3})*", normalized(text_content(values[0]))) or len(labels) != 1:
                        issues.append(f"projects.html has an invalid {metric} activity metric")
            figures = elements(activity_tree, tag="figure", cls="github-activity__rhythm")
            calendars = elements(activity_tree, tag="svg", cls="github-activity-calendar")
            days = elements(activity_tree, tag="rect", cls="github-activity-day")
            legends = elements(activity_tree, cls="github-activity__legend")
            if len(figures) != 1 or len(calendars) != 1:
                issues.append("projects.html lacks one contribution-rhythm figure and SVG calendar")
            else:
                captions = elements(figures[0], tag="figcaption")
                labelledby = (calendars[0].attrs.get("aria-labelledby") or "").split()
                title_ids = {
                    item.attrs.get("id") for item in elements(calendars[0], tag="title")
                    if item.attrs.get("id")
                }
                desc_ids = {
                    item.attrs.get("id") for item in elements(calendars[0], tag="desc")
                    if item.attrs.get("id")
                }
                caption_ids = {item.attrs.get("id") for item in captions if item.attrs.get("id")}
                if (
                    len(captions) != 1
                    or calendars[0].attrs.get("role") != "img"
                    or not caption_ids
                    or not title_ids
                    or not desc_ids
                    or not title_ids.issubset(set(labelledby))
                    or not desc_ids.issubset(set(labelledby))
                ):
                    issues.append("GitHub rhythm figure/SVG lacks a complete accessible label contract")
            expected_year = int(rendered_year) if re.fullmatch(r"\d{4}", rendered_year or "") else None
            seen_dates: list[str] = []
            day_total = 0
            for day in days:
                date_value = day.attrs.get("data-date") or ""
                count_value = day.attrs.get("data-count") or ""
                level_value = day.attrs.get("data-level") or ""
                titles = elements(day, tag="title")
                if (
                    not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value)
                    or not re.fullmatch(r"\d+", count_value)
                    or level_value not in {"0", "1", "2", "3", "4"}
                    or f"github-activity-day--level-{level_value}" not in (day.attrs.get("class") or "").split()
                    or len(titles) != 1
                ):
                    issues.append("GitHub activity calendar contains a malformed contribution day")
                    continue
                if expected_year is not None and not date_value.startswith(f"{expected_year:04d}-"):
                    issues.append(f"GitHub activity calendar renders an out-of-year day {date_value}")
                seen_dates.append(date_value)
                day_total += int(count_value)
            if not days or seen_dates != sorted(seen_dates) or len(seen_dates) != len(set(seen_dates)):
                issues.append("GitHub activity calendar days are absent, duplicated, or out of order")
            contribution_values = [
                normalized(text_content(value)).replace(",", "")
                for item in metrics if item.attrs.get("data-github-metric") == "contributions"
                for value in elements(item, tag="dd", cls="github-activity-highlight__value")
            ]
            if len(contribution_values) == 1 and contribution_values[0].isdigit() and day_total != int(contribution_values[0]):
                issues.append("GitHub activity calendar day counts do not reconcile to contributions")
            legend_levels = {
                item.attrs.get("data-level")
                for legend in legends
                for item in walk(legend)
                if item.attrs.get("data-level") is not None
            }
            if len(legends) != 1 or legend_levels != {"0", "1", "2", "3", "4"}:
                issues.append("GitHub activity calendar lacks a five-level legend")
        dashboard_links = [
            item for item in elements(full_tree, tag="a", cls="github-dashboard-cta")
            if item.attrs.get("href") == DASHBOARD_URL
        ]
        if len(dashboard_links) != 1:
            issues.append("projects.html lacks one exact full GitHub dashboard CTA")
        else:
            dashboard = dashboard_links[0]
            rel_tokens = set((dashboard.attrs.get("rel") or "").split())
            accessible = normalized((dashboard.attrs.get("aria-label") or "") + " " + text_content(dashboard)).casefold()
            if dashboard.attrs.get("target") != "_blank" or not {"noopener", "noreferrer"}.issubset(rel_tokens):
                issues.append("GitHub dashboard CTA lacks protected new-tab attributes")
            if "github activity dashboard" not in accessible or "new tab" not in accessible:
                issues.append("GitHub dashboard CTA lacks descriptive new-tab text")
    if CONFIG.is_file():
        try:
            config = json.loads(CONFIG.read_text(encoding="utf-8"))
            expected = {
                "target_schema_version": "1.2.0",
                "pinned_projects_count": EXPECTED_PROJECT_COUNT,
                "pinned_projects_file": "projects.html",
                "pinned_projects_start_marker": PROJECT_START,
                "pinned_projects_end_marker": PROJECT_END,
                "github_activity_start_marker": ACTIVITY_START,
                "github_activity_end_marker": ACTIVITY_END,
                "github_activity_profile_url": DASHBOARD_URL,
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
        "totalCount", "contributionsCollection", "totalContributions", "totalCommitContributions",
        "totalIssueContributions", "totalPullRequestContributions",
        "totalPullRequestReviewContributions", "totalRepositoriesWithContributedCommits",
        "weeks", "firstDay", "contributionDays", "contributionCount", "contributionLevel",
        "github-activity__highlights", "github-activity__rhythm", "github-activity-calendar",
        "MAX_PINNED_ITEMS = 6", "--response-file", "--target", "--as-of", "--json",
    ):
        if token not in generator_text:
            issues.append(f"generator lacks {token!r}")
    if generator_text.count("atomic_write(target, updated.encode") != 1:
        issues.append("generator does not have exactly one final atomic target write")
    workflow_text = workflow.read_text(encoding="utf-8") if workflow.is_file() else ""
    workflow_expectations = {
        "daily cron 06:17 UTC": re.search(r"cron\s*:\s*[\"']?17\s+6\s+\*\s+\*\s+\*", workflow_text),
        "workflow_dispatch": "workflow_dispatch" in workflow_text,
        "contents write permission": bool(re.search(r"contents\s*:\s*write", workflow_text)),
        "Pages build permission": bool(re.search(r"pages\s*:\s*write", workflow_text)),
        "checkout v7": "actions/checkout@v7" in workflow_text,
        "refresh concurrency": "refresh-pinned-projects" in workflow_text and bool(re.search(r"cancel-in-progress\s*:\s*false", workflow_text)),
        "secret token mapping": "GITHUB_TOKEN" in workflow_text and "secrets.GITHUB_TOKEN" in workflow_text,
        "single generator invocation": workflow_text.count("python3 .github/scripts/refresh_pinned_projects.py --json") == 1,
        "single-page staging scope": "git add -- projects.html" in workflow_text,
        "activity refresh naming": "GitHub projects and activity" in workflow_text,
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
    require_no_issues("marker-driven GitHub pins/activity generator and isolated scheduled workflow", issues)
    return (
        f"project/activity markers, schema 1.2.0 four-project, three-highlight, and rhythm-graph contract, "
        "fail-closed schedule, token isolation, and verified Pages build are present"
    )


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
        expected_lengths = {"name": "100", "email": "254", "message": "1500"}
        for name in ("name", "email", "message"):
            if name not in controls or "required" not in controls[name].attrs:
                issues.append(f"required {name} field is absent")
            elif controls[name].attrs.get("maxlength") != expected_lengths[name]:
                issues.append(f"{name} maxlength is not {expected_lengths[name]}")
            labels = [item for item in elements(form, tag="label") if item.attrs.get("for") == controls.get(name, Element("", {})).attrs.get("id")]
            if not labels or "required" not in text_content(labels[0]).casefold():
                issues.append(f"{name} field is not visibly marked required")
        submits = [item for item in elements(form, tag="button") if item.attrs.get("type") == "submit"]
        if len(submits) != 1 or "disabled" not in submits[0].attrs or text_content(submits[0]) != "Open Email Draft":
            issues.append("email-draft submit does not ship disabled with exact progressive-enhancement copy")
        helpers = elements(form, cls="contact-form__help")
        if len(helpers) != 1 or "nothing is sent until you press send" not in text_content(helpers[0]).casefold():
            issues.append("form lacks the truthful press-Send delivery boundary")
        statuses = [
            item for item in elements(form, cls="contact-form__status")
            if item.attrs.get("role") == "status"
            and item.attrs.get("aria-live") == "polite"
            and item.attrs.get("aria-atomic") == "true"
        ]
        if len(statuses) != 1:
            issues.append("contact form lacks one polite atomic live status")
        retry_links = [
            item for item in elements(form, tag="a")
            if item.attrs.get("id") == "contactDraftLink"
            and item.attrs.get("href") == "mailto:josiah.hunter.it@gmail.com"
            and "hidden" in item.attrs
        ]
        if len(retry_links) != 1:
            issues.append("contact form lacks an initially hidden email-draft retry link")
    hrefs = {item.attrs.get("href") for item in elements(tree, tag="a")}
    for href in ("mailto:josiah.hunter.it@gmail.com", "https://github.com/josiahH-cf", "https://www.linkedin.com/in/josiahhunter/"):
        if href not in hrefs:
            issues.append(f"missing direct contact link {href}")
    direct_groups = [item for item in elements(tree, cls="contact__links") if item.attrs.get("role") == "group" and item.attrs.get("aria-label")]
    if len(direct_groups) != 1:
        issues.append("direct contact links lack a valid named group role")
    direct_email = first_by_id(tree, "contactEmailLink")
    if (
        direct_email is None
        or direct_email.tag != "a"
        or direct_email.attrs.get("href") != "mailto:josiah.hunter.it@gmail.com"
        or text_content(direct_email) != "josiah.hunter.it@gmail.com"
    ):
        issues.append("literal direct email address is not visibly usable without JavaScript")
    copy_buttons = [
        item for item in elements(tree, tag="button")
        if item.attrs.get("id") == "copyEmailButton" and item.attrs.get("type") == "button"
    ]
    if len(copy_buttons) != 1 or "disabled" not in copy_buttons[0].attrs or text_content(copy_buttons[0]) != "Copy email address":
        issues.append("separate copy-email control does not ship safely disabled")
    return issues


def check_arch_4() -> str:
    issues = reach_out_issues()
    script_text = (ROOT / "script.js").read_text(encoding="utf-8")
    forbidden = {
        "forwarding endpoint placeholder": "PASTE_FORM_FORWARDING_ENDPOINT_HERE",
        "legacy endpoint constant": "CONTACT_FORM_ENDPOINT",
        "network contact submission": "fetch(contactEndpoint",
        "false delivery claim": "Your message was sent",
        "legacy email-link interception": "getElementById('emailLink')",
    }
    for label, token in forbidden.items():
        if token in script_text:
            issues.append(f"script.js retains {label}")
    required = (
        "const CONTACT_EMAIL = 'josiah.hunter.it@gmail.com'",
        "buildContactDraftHref",
        "sanitizeContactSubjectName",
        "encodeURIComponent(subject)",
        "encodeURIComponent(body)",
        "navigator.clipboard.writeText(CONTACT_EMAIL)",
    )
    for token in required:
        if token not in script_text:
            issues.append(f"script.js lacks stable contact-handoff token {token!r}")
    require_no_issues("exact About/details plus a dependency-free, honest email-draft handoff", issues)
    return "Reach Out contains exact profile content, direct links, an encoded draft handoff, and explicit copy fallback"


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
    home = ROOT / "index.html"
    home_source = home.read_text(encoding="utf-8")
    tree = parse_html(home)
    titles = elements(tree, tag="title")
    if len(titles) != 1 or text_content(titles[0]) != f"Josiah Hunter | {BRAND}":
        issues.append("home title does not exactly match LinkedIn branding")
    names = elements(tree, tag="h1", cls="hero__name")
    if len(names) != 1 or text_content(names[0]) != "Josiah Hunter":
        issues.append("hero name is not exactly 'Josiah Hunter' without punctuation")
    prompts = elements(tree, tag="p", cls="hero__conversation-prompt")
    if len(prompts) != 1 or text_content(prompts[0]) != INTRO_PROMPT:
        issues.append("hero conversation prompt is absent or inexact")
    topic_lists = elements(tree, tag="ul", cls="hero__topics")
    topics = elements(topic_lists[0], tag="li", cls="hero__topic") if len(topic_lists) == 1 else []
    rendered_topics = []
    for topic in topics:
        emojis = elements(topic, cls="hero__topic-emoji")
        labels = elements(topic, cls="hero__topic-label")
        rendered_topics.append((text_content(emojis[0]) if len(emojis) == 1 else "", text_content(labels[0]) if len(labels) == 1 else ""))
        if len(emojis) != 1 or emojis[0].attrs.get("aria-hidden") != "true":
            issues.append("hero topic emoji is not decorative")
        interactive_descendants = [
            item for item in walk(topic)
            if item is not topic and item.tag in {"a", "button", "input", "select", "textarea"}
        ]
        if (
            interactive_descendants
            or topic.attrs.get("role")
            or topic.attrs.get("tabindex") is not None
            or topic.attrs.get("data-href")
        ):
            issues.append("hero topic is exposed as an interactive control")
    if rendered_topics != list(INTRO_TOPICS):
        issues.append(f"hero topics {rendered_topics!r} do not match the requested ordered tags")
    ordered_classes = (
        "hero__greeting", "hero__name", "hero__conversation-prompt",
        "hero__topics", "hero__cta-group", "hero__social",
    )
    positions = [home_source.find(f'class="{css_class}') for css_class in ordered_classes]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        issues.append("hero greeting, name, prompt, topics, actions, and social links are out of order")
    descriptions = [item for item in elements(tree, tag="meta") if (item.attrs.get("name") or "").lower() == "description"]
    if len(descriptions) != 1 or descriptions[0].attrs.get("content") != f"Josiah Hunter | {BRAND}":
        issues.append("home meta description does not exactly match branding")
    require_no_issues("natural ordered hero intro, exact metadata branding, and no removed subtext", issues)
    return "name/prompt/topic tags are ordered, metadata branding matches, and removed blurbs remain absent"


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


def run_generator(
    response: Path, target: Path, as_of: str = ACTIVITY_AS_OF
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / ".github/scripts/refresh_pinned_projects.py"),
         "--response-file", str(response), "--target", str(target),
         "--as-of", as_of, "--json"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )


def check_beh_4() -> str:
    generator = ROOT / ".github/scripts/refresh_pinned_projects.py"
    if not generator.is_file():
        fail("runnable pinned-project generator", "generator is missing")
    fixture = json.loads(PROJECT_FIXTURE.read_text(encoding="utf-8"))
    nodes = fixture["data"]["user"]["pinnedItems"]["nodes"]
    shell = (
        "prefix sentinel\n" + PROJECT_START + "\nold cards\n" + PROJECT_END
        + "\nbetween sentinel\n" + ACTIVITY_START + "\nold activity\n"
        + ACTIVITY_END + "\nsuffix sentinel\n"
    )
    issues = []
    with tempfile.TemporaryDirectory(prefix="pinned-project-check-") as tmp:
        target = Path(tmp) / "projects.html"
        target.write_bytes(shell.encode("utf-8"))
        completed = run_generator(PROJECT_FIXTURE, target)
        if completed.returncode != 0:
            fail(
                f"generator exit 0 for fixed {EXPECTED_PROJECT_COUNT}-node fixture",
                f"exit {completed.returncode}",
                completed.stderr or completed.stdout,
            )
        output = target.read_text(encoding="utf-8")
        if (
            not output.startswith("prefix sentinel\n" + PROJECT_START)
            or PROJECT_END + "\nbetween sentinel\n" + ACTIVITY_START not in output
            or not output.endswith(ACTIVITY_END + "\nsuffix sentinel\n")
        ):
            issues.append("generator changed bytes outside the two marker regions")
        region = marker_region(output, PROJECT_START, PROJECT_END)
        tree = parse_html_text(region)
        cards = elements(tree, cls="project-card")
        if len(cards) != EXPECTED_PROJECT_COUNT:
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
        activity_region = marker_region(output, ACTIVITY_START, ACTIVITY_END)
        activity_tree = parse_html_text(activity_region)
        activity_headings = elements(activity_tree, tag="h2", cls="github-activity__title")
        activity_years = elements(activity_tree, tag="time", cls="github-activity__year")
        activity_statuses = elements(activity_tree, cls="github-activity__status")
        activity_metrics = elements(activity_tree, cls="github-activity-highlight")
        if len(activity_headings) != 1 or text_content(activity_headings[0]) != "2026 GitHub activity":
            issues.append("generated activity heading does not use the fixture year")
        if len(activity_years) != 1 or activity_years[0].attrs.get("datetime") != "2026":
            issues.append("generated activity year does not match --as-of")
        if len(activity_statuses) != 1 or "year-to-date public contribution totals" not in text_content(activity_statuses[0]).casefold() or "refreshed daily" not in text_content(activity_statuses[0]).casefold():
            issues.append("generated activity scope/cadence status is absent")
        actual_activity = {}
        for item in activity_metrics:
            key = item.attrs.get("data-github-metric")
            values = elements(item, tag="dd", cls="github-activity-highlight__value")
            if key and len(values) == 1:
                actual_activity[key] = normalized(text_content(values[0]))
        expected_activity = {key: f"{value:,}" for key, value in EXPECTED_ACTIVITY.items()}
        if actual_activity != expected_activity:
            issues.append(f"generated activity values {actual_activity!r} differ from {expected_activity!r}")
        figures = elements(activity_tree, tag="figure", cls="github-activity__rhythm")
        calendars = elements(activity_tree, tag="svg", cls="github-activity-calendar")
        days = elements(activity_tree, tag="rect", cls="github-activity-day")
        if len(figures) != 1 or len(calendars) != 1 or len(days) != 365:
            issues.append(
                f"generated contribution rhythm is incomplete: figures={len(figures)}, "
                f"calendars={len(calendars)}, days={len(days)}"
            )
        generated_dates = [item.attrs.get("data-date") for item in days]
        generated_total = sum(
            int(item.attrs.get("data-count") or "-1")
            for item in days
            if re.fullmatch(r"\d+", item.attrs.get("data-count") or "")
        )
        if (
            generated_dates != sorted(generated_dates)
            or len(generated_dates) != len(set(generated_dates))
            or any(not (value or "").startswith("2026-") for value in generated_dates)
            or generated_total != EXPECTED_ACTIVITY["contributions"]
        ):
            issues.append("generated contribution days are unordered, duplicated, out-of-year, or unreconciled")
        legend_levels = {
            item.attrs.get("data-level")
            for legend in elements(activity_tree, cls="github-activity__legend")
            for item in walk(legend)
            if item.attrs.get("data-level") is not None
        }
        if legend_levels != {"0", "1", "2", "3", "4"}:
            issues.append("generated contribution rhythm lacks the five intensity levels")
        try:
            result_payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            result_payload = {}
        if result_payload.get("activity_year") != 2026 or result_payload.get("activity_total") != EXPECTED_ACTIVITY["contributions"]:
            issues.append("machine-readable generator result lacks activity year/total")
        crlf_shell = (
            b"prefix sentinel\r\n" + PROJECT_START.encode() + b"\r\nold cards\r\n"
            + PROJECT_END.encode() + b"\r\nbetween sentinel\r\n" + ACTIVITY_START.encode()
            + b"\r\nold activity\r\n" + ACTIVITY_END.encode() + b"\r\nsuffix sentinel\r\n"
        )
        target.write_bytes(crlf_shell)
        crlf_run = run_generator(PROJECT_FIXTURE, target)
        crlf_output = target.read_bytes()
        expected_prefix = b"prefix sentinel\r\n" + PROJECT_START.encode()
        expected_middle = PROJECT_END.encode() + b"\r\nbetween sentinel\r\n" + ACTIVITY_START.encode()
        expected_suffix = ACTIVITY_END.encode() + b"\r\nsuffix sentinel\r\n"
        if crlf_run.returncode != 0 or not crlf_output.startswith(expected_prefix) or expected_middle not in crlf_output or not crlf_output.endswith(expected_suffix):
            issues.append("CRLF bytes outside the marker regions were not preserved")
        target.write_bytes(shell.encode("utf-8"))
        completed = run_generator(PROJECT_FIXTURE, target)
        if completed.returncode != 0:
            issues.append("generator could not restore the LF idempotence target")
        before = target.read_bytes()
        rerun = run_generator(PROJECT_FIXTURE, target)
        if rerun.returncode != 0 or target.read_bytes() != before:
            issues.append("identical input did not produce byte-stable output")
        same_year_rerun = run_generator(
            PROJECT_FIXTURE, target, "2026-12-30T23:59:58Z"
        )
        if same_year_rerun.returncode != 0 or target.read_bytes() != before:
            issues.append("a different --as-of time in the same year changed generated bytes")
        rollover = copy.deepcopy(fixture)
        rollover_activity = rollover["data"]["user"]["contributionsCollection"]
        rollover_activity["startedAt"] = "2027-01-01T00:00:00Z"
        rollover_activity["endedAt"] = "2027-12-31T23:59:59Z"
        rollover_activity["contributionCalendar"]["totalContributions"] = 0
        rollover_weeks: list[dict[str, object]] = []
        rollover_days: list[dict[str, object]] = []
        rollover_cursor = datetime(2027, 1, 1).date()
        rollover_end = datetime(2027, 12, 31).date()
        while rollover_cursor <= rollover_end:
            if rollover_cursor.weekday() == 6 and rollover_days:
                rollover_weeks.append(
                    {"firstDay": rollover_days[0]["date"], "contributionDays": rollover_days}
                )
                rollover_days = []
            rollover_days.append(
                {
                    "contributionCount": 0,
                    "contributionLevel": "NONE",
                    "date": rollover_cursor.isoformat(),
                    "weekday": (rollover_cursor.weekday() + 1) % 7,
                }
            )
            rollover_cursor += timedelta(days=1)
        if rollover_days:
            rollover_weeks.append(
                {"firstDay": rollover_days[0]["date"], "contributionDays": rollover_days}
            )
        rollover_activity["contributionCalendar"]["weeks"] = rollover_weeks
        for key in (
            "totalCommitContributions", "totalIssueContributions",
            "totalPullRequestContributions", "totalPullRequestReviewContributions",
            "totalRepositoriesWithContributedCommits",
        ):
            rollover_activity[key] = 0
        rollover_response = Path(tmp) / "rollover.json"
        rollover_response.write_text(json.dumps(rollover), encoding="utf-8")
        target.write_bytes(shell.encode("utf-8"))
        rollover_run = run_generator(rollover_response, target, "2027-01-01T00:01:00Z")
        rollover_output = target.read_text(encoding="utf-8")
        rollover_region = marker_region(rollover_output, ACTIVITY_START, ACTIVITY_END)
        rollover_headings = elements(
            parse_html_text(rollover_region), tag="h2", cls="github-activity__title"
        )
        if rollover_run.returncode != 0 or len(rollover_headings) != 1 or text_content(rollover_headings[0]) != "2027 GitHub activity":
            issues.append(
                "January 1 rollover did not switch the activity year deterministically: "
                + normalized(rollover_run.stderr or rollover_run.stdout)[-300:]
            )
        invalid_cases = []
        variants = {
            "GraphQL errors": {"errors": [{"message": "fixture rejection"}]},
            "partial GraphQL errors": copy.deepcopy(fixture),
            "null user": {"data": {"user": None}},
            "three nodes": copy.deepcopy(fixture),
            "five nodes": copy.deepcopy(fixture),
            "totalCount mismatch": copy.deepcopy(fixture),
            "non-integer totalCount": copy.deepcopy(fixture),
            "duplicate node": copy.deepcopy(fixture),
            "malformed URL": copy.deepcopy(fixture),
            "name URL mismatch": copy.deepcopy(fixture),
            "dot-segment repository": copy.deepcopy(fixture),
            "negative count": copy.deepcopy(fixture),
            "malformed timestamp": copy.deepcopy(fixture),
            "missing activity collection": copy.deepcopy(fixture),
            "missing contribution calendar": copy.deepcopy(fixture),
            "missing calendar weeks": copy.deepcopy(fixture),
            "empty calendar weeks": copy.deepcopy(fixture),
            "calendar coverage gap": copy.deepcopy(fixture),
            "duplicate calendar day": copy.deepcopy(fixture),
            "unordered calendar weeks": copy.deepcopy(fixture),
            "negative calendar day": copy.deepcopy(fixture),
            "invalid calendar level": copy.deepcopy(fixture),
            "invalid calendar weekday": copy.deepcopy(fixture),
            "calendar total mismatch": copy.deepcopy(fixture),
            "negative activity total": copy.deepcopy(fixture),
            "boolean commit total": copy.deepcopy(fixture),
            "malformed activity start": copy.deepcopy(fixture),
            "wrong activity year start": copy.deepcopy(fixture),
            "mismatched activity end": copy.deepcopy(fixture),
            "non-UTC activity start": copy.deepcopy(fixture),
            "string review total": copy.deepcopy(fixture),
            "missing repository total": copy.deepcopy(fixture),
        }
        variants["partial GraphQL errors"]["errors"] = [{"message": "partial data is unsafe"}]
        variants["three nodes"]["data"]["user"]["pinnedItems"]["totalCount"] = 3
        variants["three nodes"]["data"]["user"]["pinnedItems"]["nodes"] = copy.deepcopy(nodes[:3])
        fifth = copy.deepcopy(nodes[0])
        fifth["name"] = "epsilon-overflow"
        fifth["url"] = "https://github.com/josiahH-cf/epsilon-overflow"
        variants["five nodes"]["data"]["user"]["pinnedItems"]["totalCount"] = 5
        variants["five nodes"]["data"]["user"]["pinnedItems"]["nodes"].append(fifth)
        variants["totalCount mismatch"]["data"]["user"]["pinnedItems"]["nodes"] = copy.deepcopy(nodes[:3])
        variants["non-integer totalCount"]["data"]["user"]["pinnedItems"]["totalCount"] = "4"
        variants["duplicate node"]["data"]["user"]["pinnedItems"]["nodes"][EXPECTED_PROJECT_COUNT - 1] = copy.deepcopy(nodes[0])
        variants["malformed URL"]["data"]["user"]["pinnedItems"]["nodes"][0]["url"] = "javascript:alert(1)"
        variants["name URL mismatch"]["data"]["user"]["pinnedItems"]["nodes"][0]["name"] = "different-name"
        variants["dot-segment repository"]["data"]["user"]["pinnedItems"]["nodes"][0]["name"] = ".."
        variants["dot-segment repository"]["data"]["user"]["pinnedItems"]["nodes"][0]["url"] = "https://github.com/josiahH-cf/.."
        variants["negative count"]["data"]["user"]["pinnedItems"]["nodes"][0]["forkCount"] = -1
        variants["malformed timestamp"]["data"]["user"]["pinnedItems"]["nodes"][0]["updatedAt"] = "yesterday"
        variants["missing activity collection"]["data"]["user"].pop("contributionsCollection")
        variants["missing contribution calendar"]["data"]["user"]["contributionsCollection"].pop("contributionCalendar")
        variants["missing calendar weeks"]["data"]["user"]["contributionsCollection"]["contributionCalendar"].pop("weeks")
        variants["empty calendar weeks"]["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"] = []
        coverage_weeks = variants["calendar coverage gap"]["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        coverage_days = next(
            week["contributionDays"]
            for week in coverage_weeks
            if any(day.get("date") == "2026-12-31" for day in week["contributionDays"])
        )
        coverage_days[:] = [day for day in coverage_days if day.get("date") != "2026-12-31"]
        duplicate_days = variants["duplicate calendar day"]["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"][0]["contributionDays"]
        duplicate_days[1]["date"] = duplicate_days[0]["date"]
        variants["unordered calendar weeks"]["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"].reverse()
        variants["negative calendar day"]["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"][0]["contributionDays"][0]["contributionCount"] = -1
        variants["invalid calendar level"]["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"][0]["contributionDays"][0]["contributionLevel"] = "MAXIMUM"
        variants["invalid calendar weekday"]["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"][0]["contributionDays"][0]["weekday"] = 9
        variants["calendar total mismatch"]["data"]["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"] += 1
        variants["negative activity total"]["data"]["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"] = -1
        variants["boolean commit total"]["data"]["user"]["contributionsCollection"]["totalCommitContributions"] = True
        variants["malformed activity start"]["data"]["user"]["contributionsCollection"]["startedAt"] = "this year"
        variants["wrong activity year start"]["data"]["user"]["contributionsCollection"]["startedAt"] = "2025-01-01T00:00:00Z"
        variants["mismatched activity end"]["data"]["user"]["contributionsCollection"]["endedAt"] = "2026-12-31T23:59:58Z"
        variants["non-UTC activity start"]["data"]["user"]["contributionsCollection"]["startedAt"] = "2026-01-01T01:00:00+01:00"
        variants["string review total"]["data"]["user"]["contributionsCollection"]["totalPullRequestReviewContributions"] = "0"
        variants["missing repository total"]["data"]["user"]["contributionsCollection"].pop("totalRepositoriesWithContributedCommits")
        for label, payload in variants.items():
            response = Path(tmp) / f"invalid-{len(invalid_cases)}.json"
            response.write_text(json.dumps(payload), encoding="utf-8")
            target.write_bytes(shell.encode("utf-8"))
            rejected = run_generator(response, target)
            if rejected.returncode == 0 or target.read_bytes() != shell.encode("utf-8"):
                invalid_cases.append(label)
        if invalid_cases:
            issues.append(f"invalid input accepted or rewrote target: {', '.join(invalid_cases)}")
        invalid_as_of = []
        for label, value in {
            "malformed --as-of": "today",
            "non-UTC --as-of": "2026-09-01T14:02:35+01:00",
        }.items():
            target.write_bytes(shell.encode("utf-8"))
            rejected = run_generator(PROJECT_FIXTURE, target, value)
            if rejected.returncode == 0 or target.read_bytes() != shell.encode("utf-8"):
                invalid_as_of.append(label)
        if invalid_as_of:
            issues.append(f"invalid time controls accepted or rewrote target: {', '.join(invalid_as_of)}")
        invalid_targets = []
        marker_variants = {
            "out-of-order project markers": (
                "prefix\n" + PROJECT_END + "\nold\n" + PROJECT_START + "\n"
                + ACTIVITY_START + "\nold\n" + ACTIVITY_END + "\nsuffix\n"
            ),
            "duplicate project start marker": (
                "prefix\n" + PROJECT_START + "\n" + PROJECT_START + "\n" + PROJECT_END
                + "\n" + ACTIVITY_START + "\nold\n" + ACTIVITY_END + "\nsuffix\n"
            ),
            "out-of-order activity markers": (
                "prefix\n" + PROJECT_START + "\nold\n" + PROJECT_END + "\n"
                + ACTIVITY_END + "\nold\n" + ACTIVITY_START + "\nsuffix\n"
            ),
            "duplicate activity start marker": (
                "prefix\n" + PROJECT_START + "\nold\n" + PROJECT_END + "\n"
                + ACTIVITY_START + "\n" + ACTIVITY_START + "\n" + ACTIVITY_END + "\nsuffix\n"
            ),
            "missing activity markers": (
                "prefix\n" + PROJECT_START + "\nold\n" + PROJECT_END + "\nsuffix\n"
            ),
            "nested marker regions": (
                "prefix\n" + PROJECT_START + "\n" + ACTIVITY_START + "\nold\n"
                + PROJECT_END + "\n" + ACTIVITY_END + "\nsuffix\n"
            ),
            "activity region before projects": (
                "prefix\n" + ACTIVITY_START + "\nold\n" + ACTIVITY_END + "\n"
                + PROJECT_START + "\nold\n" + PROJECT_END + "\nsuffix\n"
            ),
            "duplicate activity end marker": (
                "prefix\n" + PROJECT_START + "\nold\n" + PROJECT_END + "\n"
                + ACTIVITY_START + "\nold\n" + ACTIVITY_END + "\n" + ACTIVITY_END + "\nsuffix\n"
            ),
        }
        for label, malformed_target in marker_variants.items():
            original = malformed_target.encode("utf-8")
            target.write_bytes(original)
            rejected = run_generator(PROJECT_FIXTURE, target)
            if rejected.returncode == 0 or target.read_bytes() != original:
                invalid_targets.append(label)
        if invalid_targets:
            issues.append(f"invalid marker layouts accepted or rewritten: {', '.join(invalid_targets)}")
    require_no_issues(
        f"{EXPECTED_PROJECT_COUNT} ordered escaped cards plus current-year activity, exact outside bytes, and atomic hostile-input rejection",
        issues,
    )
    return (
        f"hostile fixture generated {EXPECTED_PROJECT_COUNT} styled cards, three headline metrics, "
        "and a reconciled daily calendar; CRLF/LF bytes, idempotence, year rollover, and "
        "invalid-input atomicity passed"
    )


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
    home_tree = parse_html(ROOT / "index.html")
    home_sections = elements(home_tree, tag="section", cls="articles--home")
    if len(home_sections) != 1:
        issues.append("home lacks one lightweight Blog section")
    else:
        intro = elements(home_sections[0], cls="home-blog__intro")
        if (
            len(intro) != 1
            or text_content(intro[0]) != "Ideas, experiments, and the occasional useful rabbit hole."
            or "reveal-on-scroll" not in (intro[0].attrs.get("class") or "").split()
        ):
            issues.append("home Blog lacks the exact light introduction and reveal behavior")
        all_links = [
            item for item in elements(home_sections[0], tag="a", cls="home-blog__all-link")
            if item.attrs.get("href") == "/docs/blog.html" and text_content(item) == "See all writing →"
        ]
        series_links = [
            item for item in elements(home_sections[0], tag="a", cls="home-series-link")
            if item.attrs.get("href") == "/docs/31-days-of-ai.html"
            and text_content(item) == "A completed side quest: 31 Days of AI — 31 entries →"
        ]
        if len(all_links) != 1:
            issues.append("home Blog lacks one exact full-writing link")
        nested_series_links = (
            [item for item in walk(series_links[0]) if item is not series_links[0] and item.tag == "a"]
            if len(series_links) == 1 else []
        )
        if len(series_links) != 1 or nested_series_links:
            issues.append("home Blog lacks one simple non-nested completed-series link")
        if elements(home_sections[0], cls="campaign-banner"):
            issues.append("home Blog retains the heavy campaign banner")
    require_no_issues("matching live Article Flow card sequences plus a lightweight home-only presentation", issues)
    return (
        f"home and Blog expose the same {len(link_sets[0][1]) if link_sets else 0} generated cards; "
        "home adds only a light intro and two hub links outside the markers"
    )


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
    if any(marker in ARTICLE_MARKERS for marker in (PROJECT_START, PROJECT_END, ACTIVITY_START, ACTIVITY_END)):
        issues.append("GitHub refresh markers collide with Article Flow markers")
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
    "BEH-6": ("behavior", "Contact email-draft handoff"),
    "BEH-9": ("behavior", "Hero fits the viewport"),
    "BEH-10": ("behavior", "GitHub activity and dashboard CTA"),
    "PRES-3": ("preservation", "31 Days fixed-clock reveal"),
    "PRES-4": ("preservation", "Mobile menu"),
    "PRES-5": ("preservation", "Reveal and reduced motion"),
    "PRES-6": ("preservation", "Social links and explicit copy control"),
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
