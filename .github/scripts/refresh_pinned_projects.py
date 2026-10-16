#!/usr/bin/env python3
"""Refresh public pinned projects and GitHub's public profile contribution calendar.

The token is used only for pinned repositories. Activity comes from a separate,
unauthenticated profile request, so a privileged CI token cannot publish activity
that an anonymous profile visitor cannot see. Both sources are validated before
one atomic replacement of the configured regions in projects.html.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


GRAPHQL_URL = "https://api.github.com/graphql"
CONFIG_PATH = Path("Article-Spec-Pack-v1/publication/theproductiveprompter.json")
DEFAULT_OWNER = "josiahH-cf"
DEFAULT_COUNT = 4
MAX_PINNED_ITEMS = 6
DEFAULT_START_MARKER = "<!-- PINNED_PROJECTS_START -->"
DEFAULT_END_MARKER = "<!-- PINNED_PROJECTS_END -->"
DEFAULT_ACTIVITY_START_MARKER = "<!-- GITHUB_ACTIVITY_START -->"
DEFAULT_ACTIVITY_END_MARKER = "<!-- GITHUB_ACTIVITY_END -->"
DEFAULT_PROFILE_URL = "https://github.com/josiahH-cf"
PUBLIC_CALENDAR_URL = "https://github.com/users/josiahH-cf/contributions"
MAX_PROFILE_BYTES = 2_000_000
DEFAULT_FALLBACKS = {
    "description": "No description provided.",
    "language": "Not specified",
    "updated": "Update date unavailable",
}
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

ACTIVITY_METRICS = (
    ("contributions", "Contributions", "total_contributions"),
    ("active-days", "Active days", "active_days"),
    ("longest-streak", "Longest streak (days)", "longest_streak"),
)

QUERY = """
query PinnedProjects($login: String!, $limit: Int!) {
  user(login: $login) {
    pinnedItems(first: $limit, types: [REPOSITORY]) {
      totalCount
      nodes {
        ... on Repository {
          __typename
          isPrivate
          name
          description
          url
          primaryLanguage { name }
          stargazerCount
          forkCount
          updatedAt
        }
      }
    }
  }
}
""".strip()


class RefreshError(RuntimeError):
    """A safe, user-actionable refresh failure."""


def load_config(repository: Path) -> dict[str, Any]:
    path = repository / CONFIG_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RefreshError(f"Could not read publication config at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RefreshError("Publication config must contain a JSON object")
    return value


def request_github_data(owner: str, token: str) -> dict[str, Any]:
    if not token:
        raise RefreshError("GITHUB_TOKEN is required when --response-file is not used")
    body = json.dumps(
        {
            "query": QUERY,
            "variables": {
                "login": owner,
                "limit": MAX_PINNED_ITEMS,
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "theproductiveprompter-github-activity/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, UnicodeError) as exc:
        raise RefreshError(f"GitHub GraphQL request failed: {exc}") from exc
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RefreshError("GitHub GraphQL returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise RefreshError("GitHub GraphQL response must be a JSON object")
    return value


def load_response(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RefreshError(f"Could not read GraphQL response at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RefreshError("GraphQL response must be a JSON object")
    return value


def required_text(node: dict[str, Any], key: str, index: int) -> str:
    value = node.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RefreshError(f"Pinned item {index} has an invalid {key}")
    return value


def required_count(node: dict[str, Any], key: str, index: int) -> int:
    value = node.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RefreshError(f"Pinned item {index} has an invalid {key}")
    return value


def github_url(value: str, owner: str, name: str, index: int) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise RefreshError(f"Pinned item {index} has an invalid GitHub repository URL") from exc
    expected_path = f"/{owner}/{name}"
    if (
        parsed.scheme != "https"
        or hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != expected_path
    ):
        raise RefreshError(f"Pinned item {index} has an invalid GitHub repository URL")
    return value


def utc_timestamp(value: str, index: int) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RefreshError(f"Pinned item {index} has an invalid updatedAt") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise RefreshError(f"Pinned item {index} updatedAt must identify UTC")
    return parsed.astimezone(dt.timezone.utc)


def parse_as_of(value: str | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise RefreshError("--as-of must be an ISO 8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise RefreshError("--as-of must identify UTC")
    parsed = parsed.astimezone(dt.timezone.utc).replace(microsecond=0)
    if not 1970 <= parsed.year <= 9998:
        raise RefreshError("--as-of year is outside the supported range")
    return parsed


def github_datetime(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def calendar_date(value: object, field: str) -> dt.date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise RefreshError(f"Public profile calendar has an invalid {field}")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise RefreshError(f"Public profile calendar has an invalid {field}") from exc


class ProfileCalendarParser(HTMLParser):
    """Read only GitHub's calendar bounds, daily cells and their count labels."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.graphs: list[dict[str, str | None]] = []
        self.cells: list[dict[str, str | None]] = []
        self.tooltips: list[tuple[str, str]] = []
        self.headings: list[str] = []
        self.graph_depth = 0
        self.capture_tag: str | None = None
        self.capture_id = ""
        self.capture_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        relevant = (
            (tag == "div" and "data-graph-url" in values)
            or (tag == "td" and "ContributionCalendar-day" in classes)
            or (tag == "tool-tip" and self.graph_depth)
            or values.get("id") == "js-contribution-activity-description"
        )
        if relevant and len(values) != len(attrs):
            raise RefreshError("Public profile calendar contains duplicate attributes")
        if tag == "div":
            if "data-graph-url" in values:
                if self.graph_depth:
                    raise RefreshError("Public profile calendar has nested graphs")
                self.graphs.append(values)
                self.graph_depth = 1
            elif self.graph_depth:
                self.graph_depth += 1
        if tag == "td" and self.graph_depth and "ContributionCalendar-day" in classes:
            # GitHub uses undated placeholders for the rest of the current week.
            if "data-date" in values:
                self.cells.append(values)
        if (
            (tag == "h2" and values.get("id") == "js-contribution-activity-description")
            or (tag == "tool-tip" and self.graph_depth)
        ):
            if self.capture_tag:
                raise RefreshError("Public profile calendar has overlapping count labels")
            self.capture_tag = tag
            self.capture_id = values.get("for") or ""
            self.capture_text = []

    def handle_data(self, data: str) -> None:
        if self.capture_tag:
            self.capture_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self.capture_tag:
            text = " ".join("".join(self.capture_text).split())
            if tag == "h2":
                self.headings.append(text)
            else:
                self.tooltips.append((self.capture_id, text))
            self.capture_tag = None
        if tag == "div" and self.graph_depth:
            self.graph_depth -= 1


def parse_public_calendar(
    source: str, owner: str, as_of: dt.datetime
) -> dict[str, Any]:
    parser = ProfileCalendarParser()
    try:
        parser.feed(source)
        parser.close()
    except (ValueError, AssertionError) as exc:
        raise RefreshError("Could not parse GitHub's public profile calendar") from exc
    if parser.capture_tag or parser.graph_depth or len(parser.graphs) != 1:
        raise RefreshError("Public profile response lacks one complete calendar")
    graph = parser.graphs[0]
    if (
        graph.get("data-graph-url") != f"/users/{owner}/contributions"
        or graph.get("data-url") != f"/{owner}"
        or graph.get("data-org") != ""
        or "ContributionCalendar" not in (graph.get("class") or "").split()
    ):
        raise RefreshError("Public profile calendar owner or organization scope does not match")
    try:
        start = dt.datetime.strptime(str(graph.get("data-from")), "%Y-%m-%d %H:%M:%S UTC")
        end = dt.datetime.strptime(str(graph.get("data-to")), "%Y-%m-%d %H:%M:%S UTC")
    except ValueError as exc:
        raise RefreshError("Public profile calendar has invalid UTC bounds") from exc
    start_date, end_date = start.date(), end.date()
    day_count = (end_date - start_date).days + 1
    if (
        start.time() != dt.time(0)
        or end.time() != dt.time(23, 59, 59)
        or start_date.weekday() != 6
        or not 365 <= day_count <= 372
    ):
        raise RefreshError("Public profile calendar is not a complete last-year window")
    if end_date != as_of.date():
        raise RefreshError("Public profile calendar is stale or contains future dates")
    if len(parser.headings) != 1:
        raise RefreshError("Public profile calendar lacks one total")
    heading = re.fullmatch(r"([\d,]+) contributions? in the last year", parser.headings[0])
    if not heading or not re.fullmatch(r"(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)", heading[1]):
        raise RefreshError("Public profile calendar total or last-year label is invalid")
    total = int(heading[1].replace(",", ""))

    tooltips: dict[str, str] = {}
    for cell_id, text in parser.tooltips:
        if not cell_id or cell_id in tooltips:
            raise RefreshError("Public profile calendar has duplicate or invalid count labels")
        tooltips[cell_id] = text
    seen_dates: set[dt.date] = set()
    seen_ids: set[str] = set()
    days = []
    for raw in parser.cells:
        date_value = calendar_date(raw.get("data-date"), "day date")
        cell_id = raw.get("id")
        level_text = raw.get("data-level")
        if not cell_id or cell_id in seen_ids or date_value in seen_dates:
            raise RefreshError("Public profile calendar has duplicate or invalid days")
        if not start_date <= date_value <= end_date:
            raise RefreshError("Public profile calendar has an out-of-window or future day")
        if level_text not in {"0", "1", "2", "3", "4"}:
            raise RefreshError("Public profile calendar has an invalid contribution level")
        label = tooltips.get(cell_id, "")
        match = re.fullmatch(
            r"(No|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+) contributions? on "
            r"(" + "|".join(MONTHS) + r") (\d{1,2})(?:st|nd|rd|th)?(?:,? (\d{4}))?\.",
            label,
        )
        if not match:
            raise RefreshError("Public profile calendar has a missing or invalid daily count label")
        if (
            MONTHS.index(match[2]) + 1 != date_value.month
            or int(match[3]) != date_value.day
            or (match[4] and int(match[4]) != date_value.year)
        ):
            raise RefreshError("Public profile calendar label does not match its day")
        count = 0 if match[1] == "No" else int(match[1].replace(",", ""))
        level = int(level_text)
        if (count == 0) != (level == 0):
            raise RefreshError("Public profile calendar count and intensity disagree")
        if "data-count" in raw and raw["data-count"] != str(count):
            raise RefreshError("Public profile calendar count attributes disagree")
        seen_dates.add(date_value)
        seen_ids.add(cell_id)
        days.append({
            "date": date_value, "date_text": date_value.isoformat(),
            "count": count, "level": level, "weekday": (date_value.weekday() + 1) % 7,
        })
    expected_dates = [start_date + dt.timedelta(days=offset) for offset in range(day_count)]
    days.sort(key=lambda day: day["date"])
    if [day["date"] for day in days] != expected_dates or set(tooltips) != seen_ids:
        raise RefreshError("Public profile calendar is incomplete or has unmatched count labels")
    if sum(day["count"] for day in days) != total:
        raise RefreshError("Public profile calendar daily counts do not match its total")
    active_days, longest_streak, streak = 0, 0, 0
    for day in days:
        streak = streak + 1 if day["count"] else 0
        active_days += bool(day["count"])
        longest_streak = max(longest_streak, streak)
    return {
        "start_date": start_date, "end_date": end_date,
        "fetched_at": as_of, "source_url": PUBLIC_CALENDAR_URL,
        "total_contributions": total, "calendar_days": days,
        "active_days": active_days, "longest_streak": longest_streak,
    }


def request_public_calendar(owner: str, as_of: dt.datetime) -> dict[str, Any]:
    if owner != DEFAULT_OWNER:
        raise RefreshError("Unexpected public profile owner")
    request = urllib.request.Request(
        PUBLIC_CALENDAR_URL,
        headers={
            "Accept": "text/html", "Accept-Language": "en-US",
            "Cache-Control": "no-cache",
            "User-Agent": "theproductiveprompter-public-calendar/1.0",
        },
    )
    try:
        # A fresh opener has no authenticated session or cookie jar. Never add
        # the GraphQL token or reuse a signed-in browser for this public source.
        with urllib.request.build_opener().open(request, timeout=30) as response:
            if response.geturl() != PUBLIC_CALENDAR_URL:
                raise RefreshError("Public profile response redirected away from its source")
            if response.headers.get_content_type() != "text/html":
                raise RefreshError("Public profile response is not HTML")
            payload = response.read(MAX_PROFILE_BYTES + 1)
        if len(payload) > MAX_PROFILE_BYTES:
            raise RefreshError("Public profile response exceeds its size limit")
        source = payload.decode("utf-8")
    except (urllib.error.URLError, TimeoutError, UnicodeError) as exc:
        raise RefreshError("Could not fetch GitHub's public profile calendar") from exc
    return parse_public_calendar(source, owner, as_of)


def validate_response(
    response: dict[str, Any], owner: str, count: int,
) -> list[dict[str, Any]]:
    errors = response.get("errors")
    if errors:
        raise RefreshError("GitHub GraphQL returned one or more errors")
    try:
        user = response["data"]["user"]
        pinned_items = user["pinnedItems"]
        total_count = pinned_items["totalCount"]
        nodes = pinned_items["nodes"]
    except (KeyError, TypeError) as exc:
        raise RefreshError("GraphQL response lacks complete data.user.pinnedItems fields") from exc
    if isinstance(total_count, bool) or not isinstance(total_count, int) or total_count < 0:
        raise RefreshError("GraphQL response has an invalid pinnedItems.totalCount")
    if total_count != count:
        raise RefreshError(
            f"Expected exactly {count} pinned repositories; GitHub reports {total_count}"
        )
    if not isinstance(nodes, list) or len(nodes) != total_count:
        actual = len(nodes) if isinstance(nodes, list) else "non-list"
        raise RefreshError(
            f"GitHub reported {total_count} pinned repositories but returned {actual} nodes"
        )

    projects: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_urls: set[str] = set()
    for index, node in enumerate(nodes, start=1):
        if not isinstance(node, dict) or node.get("__typename") != "Repository":
            raise RefreshError(f"Pinned item {index} is not a Repository")
        if node.get("isPrivate") is not False:
            raise RefreshError(f"Pinned item {index} must be explicitly public")
        name = required_text(node, "name", index)
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name) or name in {".", ".."}:
            raise RefreshError(f"Pinned item {index} has an invalid repository name")
        url = github_url(required_text(node, "url", index), owner, name, index)
        description = node.get("description")
        if description is not None and not isinstance(description, str):
            raise RefreshError(f"Pinned item {index} has an invalid description")
        language_value = node.get("primaryLanguage")
        if language_value is None:
            language = None
        elif isinstance(language_value, dict):
            language = required_text(language_value, "name", index)
        else:
            raise RefreshError(f"Pinned item {index} has an invalid primaryLanguage")
        updated_raw = required_text(node, "updatedAt", index)
        updated = utc_timestamp(updated_raw, index)
        name_key = name.casefold()
        url_key = url.casefold()
        if name_key in seen_names or url_key in seen_urls:
            raise RefreshError(f"Pinned item {index} duplicates another repository")
        seen_names.add(name_key)
        seen_urls.add(url_key)
        projects.append(
            {
                "name": name,
                "description": description,
                "url": url,
                "language": language,
                "stars": required_count(node, "stargazerCount", index),
                "forks": required_count(node, "forkCount", index),
                "updated_raw": updated_raw,
                "updated": updated,
            }
        )
    return projects


def escaped(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_cards(
    projects: list[dict[str, Any]], fallbacks: dict[str, str], indent: str, newline: str
) -> str:
    blocks: list[str] = []
    child = indent + "  "
    grandchild = child + "  "
    great_grandchild = grandchild + "  "
    for index, project in enumerate(projects):
        name = escaped(project["name"])
        url = escaped(project["url"])
        description = escaped(project["description"] or fallbacks["description"])
        language = escaped(project["language"] or fallbacks["language"])
        language_key = str(project["language"] or "").casefold()
        language_class = {
            "javascript": " language-dot--javascript",
            "typescript": " language-dot--typescript",
            "python": " language-dot--python",
        }.get(language_key, "")
        updated: dt.datetime = project["updated"]
        updated_label = f"{MONTHS[updated.month - 1]} {updated.day}, {updated.year}"
        block = newline.join(
            [
                f'{indent}<article class="project-card reveal-on-scroll" data-delay="{index * 75}">',
                f'{child}<div class="project-card__content">',
                f'{grandchild}<div class="project-card__header">',
                f'{great_grandchild}<span class="project-card__language"><span class="language-dot{language_class}" aria-hidden="true"></span><span class="language-name">{language}</span></span>',
                f'{great_grandchild}<time class="project-card__updated" datetime="{escaped(project["updated_raw"])}">Updated {updated_label}</time>',
                f"{grandchild}</div>",
                f'{grandchild}<h2 class="project-card__title"><a href="{url}" target="_blank" rel="noopener noreferrer" aria-label="Open {name} on GitHub (opens in a new tab)">{name} <span aria-hidden="true">↗</span></a></h2>',
                f'{grandchild}<p class="project-card__description">{description}</p>',
                f'{grandchild}<div class="project-card__footer">',
                f'{great_grandchild}<div class="project-stats" role="group" aria-label="GitHub repository statistics">',
                f'{great_grandchild}  <span class="project-stat" role="img" aria-label="{project["stars"]} stars"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.193a.75.75 0 0 1-1.088.79L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.211-.611L7.327.668A.75.75 0 0 1 8 .25Z"/></svg><span class="project-stat__count">{project["stars"]}</span></span>',
                f'{great_grandchild}  <span class="project-stat" role="img" aria-label="{project["forks"]} forks"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 5.372v.878c0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75v-.878a2.25 2.25 0 1 1 1.5 0v.878a2.25 2.25 0 0 1-2.25 2.25h-1.5v2.128a2.251 2.251 0 1 1-1.5 0V8.5h-1.5A2.25 2.25 0 0 1 3 6.25v-.878a2.25 2.25 0 1 1 1.5 0zM5 3.25a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0zm6.75.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5zm-3 8.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5z"/></svg><span class="project-stat__count">{project["forks"]}</span></span>',
                f"{great_grandchild}</div>",
                f'{great_grandchild}<div class="project-card__links"><a class="project-card__link project-card__link--primary" href="{url}" target="_blank" rel="noopener noreferrer" aria-label="View {name} on GitHub (opens in a new tab)">View on GitHub <span aria-hidden="true">↗</span></a></div>',
                f"{grandchild}</div>",
                f"{child}</div>",
                f"{indent}</article>",
            ]
        )
        blocks.append(block)
    return (newline + newline).join(blocks)


def render_activity(activity: dict[str, Any], indent: str, newline: str) -> str:
    child = indent + "  "
    grandchild = child + "  "
    great_grandchild = grandchild + "  "
    days: list[dict[str, Any]] = activity["calendar_days"]
    start_date: dt.date = activity["start_date"]
    end_date: dt.date = activity["end_date"]
    fetched_at: dt.datetime = activity["fetched_at"]
    calendar_origin = start_date
    week_count = ((end_date - calendar_origin).days // 7) + 1
    label_width = 34
    grid_top = 20
    cell_step = 14
    cell_size = 10
    chart_width = label_width + week_count * cell_step
    chart_height = grid_top + 7 * cell_step

    lines = [
        f'{indent}<div class="github-activity__header">',
        f'{child}<h2 class="github-activity__title" id="github-activity-title">GitHub activity</h2>',
        f'{child}<p class="github-activity__status">Last year <span aria-hidden="true">·</span> Public profile</p>',
        f"{indent}</div>",
        f'{indent}<p class="github-activity__window"><time datetime="{start_date.isoformat()}">{MONTHS[start_date.month - 1]} {start_date.day}, {start_date.year}</time> – <time datetime="{end_date.isoformat()}">{MONTHS[end_date.month - 1]} {end_date.day}, {end_date.year}</time> (UTC)</p>',
        f'{indent}<dl class="github-activity__highlights" aria-label="GitHub public profile summaries for the displayed date range">',
    ]
    for key, label, value_key in ACTIVITY_METRICS:
        value = int(activity[value_key])
        lines.extend(
            [
                f'{child}<div class="github-activity-highlight" data-github-metric="{key}">',
                f'{grandchild}<dt class="github-activity-highlight__label">{label}</dt>',
                f'{grandchild}<dd class="github-activity-highlight__value">{value:,}</dd>',
                f"{child}</div>",
            ]
        )
    lines.extend(
        [
            f"{indent}</dl>",
            f'{indent}<figure class="github-activity__rhythm" aria-labelledby="github-activity-rhythm-caption" data-from="{start_date.isoformat()}" data-to="{end_date.isoformat()}">',
            f'{child}<figcaption class="github-activity__rhythm-caption" id="github-activity-rhythm-caption">',
            f'{grandchild}<span class="github-activity__rhythm-title">Contribution rhythm</span>',
            f'{grandchild}<span class="github-activity__rhythm-summary">Daily contributions · UTC</span>',
            f"{child}</figcaption>",
            f'{child}<div class="github-activity__calendar-frame" tabindex="0" role="group" aria-label="Daily GitHub contributions; scroll horizontally to explore the full date range">',
            f'{grandchild}<svg class="github-activity-calendar" viewBox="0 0 {chart_width} {chart_height}" role="img" aria-labelledby="github-activity-calendar-title github-activity-calendar-description" focusable="false" xmlns="http://www.w3.org/2000/svg">',
            f'{great_grandchild}<title id="github-activity-calendar-title">Public GitHub contribution rhythm, {start_date.isoformat()} to {end_date.isoformat()}</title>',
            f'{great_grandchild}<desc id="github-activity-calendar-description">Each square is a day in the displayed GitHub profile window. Brighter cells represent more contributions. Active days and the longest streak use this same window.</desc>',
        ]
    )

    last_label_x = -100
    for day in days:
        date_value = day["date"]
        if date_value != start_date and date_value.day != 1:
            continue
        month_week = (date_value - calendar_origin).days // 7
        month_x = label_width + month_week * cell_step
        if month_x - last_label_x < 28:
            continue
        last_label_x = month_x
        lines.append(
            f'{great_grandchild}<text class="github-activity-calendar__month" x="{month_x}" y="11">{MONTHS[date_value.month - 1][:3]}</text>'
        )
    for weekday, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        label_y = grid_top + weekday * cell_step + cell_size - 1
        lines.append(
            f'{great_grandchild}<text class="github-activity-calendar__weekday" x="0" y="{label_y}">{label}</text>'
        )
    for day in days:
        date_value: dt.date = day["date"]
        week_index = (date_value - calendar_origin).days // 7
        x_value = label_width + week_index * cell_step
        y_value = grid_top + int(day["weekday"]) * cell_step
        count = int(day["count"])
        level = int(day["level"])
        contribution_word = "contribution" if count == 1 else "contributions"
        day_label = f"{MONTHS[date_value.month - 1]} {date_value.day}, {date_value.year}: {count} {contribution_word}"
        lines.extend(
            [
                f'{great_grandchild}<rect class="github-activity-day github-activity-day--level-{level}" x="{x_value}" y="{y_value}" width="{cell_size}" height="{cell_size}" rx="2" data-date="{day["date_text"]}" data-count="{count}" data-level="{level}">',
                f"{great_grandchild}  <title>{escaped(day_label)}</title>",
                f"{great_grandchild}</rect>",
            ]
        )
    lines.extend(
        [
            f"{grandchild}</svg>",
            f"{child}</div>",
            f'{child}<div class="github-activity__legend" aria-hidden="true">',
            f'{grandchild}<span class="github-activity__legend-label">Less</span>',
        ]
    )
    for level in range(5):
        lines.append(
            f'{grandchild}<span class="github-activity__legend-swatch github-activity-day--level-{level}" data-level="{level}"></span>'
        )
    lines.extend(
        [
            f'{grandchild}<span class="github-activity__legend-label">More</span>',
            f"{child}</div>",
            f"{indent}</figure>",
            f'{indent}<p class="github-activity__provenance">Source: <a href="{DEFAULT_PROFILE_URL}" target="_blank" rel="noopener noreferrer" aria-label="GitHub public profile (opens in a new tab)">GitHub public profile</a>. Snapshot updated <time class="github-activity__updated" datetime="{github_datetime(fetched_at)}">{MONTHS[fetched_at.month - 1]} {fetched_at.day}, {fetched_at.year} at {fetched_at:%H:%M} UTC</time>. Refresh scheduled daily.</p>',
            f'{indent}<p class="github-activity__visibility">Only activity visible on the public profile is shown, including private contribution counts if shared publicly on GitHub. Signed-in totals may differ.</p>',
        ]
    )
    return newline.join(lines)


def marker_indent(source: str, marker_index: int) -> str:
    line_start = max(source.rfind("\n", 0, marker_index), source.rfind("\r", 0, marker_index)) + 1
    candidate = source[line_start:marker_index]
    return candidate if candidate.strip() == "" else ""


def validate_marker_layout(
    source: str, regions: tuple[tuple[str, str, str], ...]
) -> None:
    all_markers = [marker for start, end, _label in regions for marker in (start, end)]
    if any(not marker for marker in all_markers) or len(set(all_markers)) != len(all_markers):
        raise RefreshError("Generated-region markers must be distinct non-empty text")
    previous_end = -1
    for start_marker, end_marker, label in regions:
        if source.count(start_marker) != 1 or source.count(end_marker) != 1:
            raise RefreshError(f"Target must contain exactly one {label} marker pair")
        start = source.index(start_marker)
        end = source.index(end_marker)
        if start >= end:
            raise RefreshError(f"{label.capitalize()} markers are out of order")
        if start <= previous_end:
            raise RefreshError("Generated-region marker pairs must be ordered and disjoint")
        previous_end = end + len(end_marker) - 1


def replace_marker_region(
    source: str, start_marker: str, end_marker: str, rendered: str
) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker)
    content_start = start + len(start_marker)
    newline = "\r\n" if "\r\n" in source else "\n"
    indent = marker_indent(source, start)
    return source[:content_start] + newline + rendered + newline + indent + source[end:]


def atomic_write(path: Path, content: bytes) -> bool:
    original = path.read_bytes()
    if original == content:
        return False
    mode = stat.S_IMODE(path.stat().st_mode)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass
    return True


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response-file", type=Path, help="Read a fixed GraphQL JSON response")
    parser.add_argument("--profile-file", type=Path, help="Read a fixed signed-out GitHub contribution calendar HTML response")
    parser.add_argument("--target", type=Path, help="Override the configured HTML target")
    parser.add_argument(
        "--as-of",
        help="Use a fixed UTC snapshot timestamp and validate calendar freshness (defaults to now)",
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable result")
    args = parser.parse_args()

    try:
        repository = repository_root()
        config = load_config(repository)
        owner = str(config.get("pinned_projects_owner", DEFAULT_OWNER))
        if owner != DEFAULT_OWNER:
            raise RefreshError(f"pinned_projects_owner must be {DEFAULT_OWNER}")
        count = config.get("pinned_projects_count", DEFAULT_COUNT)
        if isinstance(count, bool) or not isinstance(count, int) or count != DEFAULT_COUNT:
            raise RefreshError(f"pinned_projects_count must be exactly {DEFAULT_COUNT}")
        start_marker = str(config.get("pinned_projects_start_marker", DEFAULT_START_MARKER))
        end_marker = str(config.get("pinned_projects_end_marker", DEFAULT_END_MARKER))
        activity_start_marker = str(
            config.get("github_activity_start_marker", DEFAULT_ACTIVITY_START_MARKER)
        )
        activity_end_marker = str(
            config.get("github_activity_end_marker", DEFAULT_ACTIVITY_END_MARKER)
        )
        profile_url = str(config.get("github_activity_profile_url", DEFAULT_PROFILE_URL))
        if profile_url != DEFAULT_PROFILE_URL:
            raise RefreshError(f"github_activity_profile_url must be {DEFAULT_PROFILE_URL}")
        markers = (start_marker, end_marker, activity_start_marker, activity_end_marker)
        if any(not marker for marker in markers) or len(set(markers)) != len(markers):
            raise RefreshError("GitHub refresh markers must be distinct non-empty text")
        configured_fallbacks = config.get("pinned_projects_fallbacks", {})
        if not isinstance(configured_fallbacks, dict):
            raise RefreshError("pinned_projects_fallbacks must be an object")
        fallbacks = {
            key: configured_fallbacks.get(key, value)
            for key, value in DEFAULT_FALLBACKS.items()
        }
        if any(not isinstance(value, str) or not value for value in fallbacks.values()):
            raise RefreshError("Every pinned-project fallback must be non-empty text")

        as_of = parse_as_of(args.as_of)
        if bool(args.response_file) != bool(args.profile_file) or (args.profile_file and not args.as_of):
            raise RefreshError("Fixture mode requires --response-file, --profile-file and --as-of together")
        if args.response_file:
            response = load_response(args.response_file.resolve())
            profile_bytes = args.profile_file.read_bytes()
            if len(profile_bytes) > MAX_PROFILE_BYTES:
                raise RefreshError("Public profile fixture exceeds its size limit")
            try:
                profile_source = profile_bytes.decode("utf-8")
            except UnicodeError as exc:
                raise RefreshError("Public profile fixture is not UTF-8") from exc
            activity = parse_public_calendar(profile_source, owner, as_of)
        else:
            response = request_github_data(owner, os.environ.get("GITHUB_TOKEN", ""))
            activity = request_public_calendar(owner, as_of)
        projects = validate_response(response, owner, count)

        configured_target = Path(str(config.get("pinned_projects_file", "projects.html")))
        target = args.target.resolve() if args.target else repository / configured_target
        if not target.is_file():
            raise RefreshError(f"Target does not exist: {target}")
        try:
            with target.open("r", encoding="utf-8", newline="") as handle:
                source = handle.read()
        except (OSError, UnicodeError) as exc:
            raise RefreshError(f"Could not read target {target}: {exc}") from exc
        regions = (
            (start_marker, end_marker, "pinned-project"),
            (activity_start_marker, activity_end_marker, "GitHub-activity"),
        )
        validate_marker_layout(source, regions)
        newline = "\r\n" if "\r\n" in source else "\n"
        cards = render_cards(
            projects, fallbacks, marker_indent(source, source.index(start_marker)), newline
        )
        activity_block = render_activity(
            activity,
            marker_indent(source, source.index(activity_start_marker)),
            newline,
        )
        updated = replace_marker_region(source, start_marker, end_marker, cards)
        updated = replace_marker_region(
            updated, activity_start_marker, activity_end_marker, activity_block
        )
        changed = atomic_write(target, updated.encode("utf-8"))
        result = {
            "status": "ok",
            "changed": changed,
            "owner": owner,
            "project_count": len(projects),
            "activity_from": activity["start_date"].isoformat(),
            "activity_to": activity["end_date"].isoformat(),
            "activity_source": activity["source_url"],
            "activity_visibility": "signed-out public profile",
            "fetched_at": github_datetime(activity["fetched_at"]),
            "activity_total": activity["total_contributions"],
            "target": str(target),
        }
        print(json.dumps(result, sort_keys=True) if args.json else (
            f"Refreshed {len(projects)} pinned projects and public profile activity in {target}"
            + ("" if changed else " (unchanged)")
        ))
        return 0
    except (RefreshError, OSError) as exc:
        result = {"status": "error", "message": str(exc)}
        print(json.dumps(result, sort_keys=True) if args.json else f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
