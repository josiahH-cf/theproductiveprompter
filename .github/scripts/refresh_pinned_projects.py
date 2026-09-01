#!/usr/bin/env python3
"""Refresh public pinned projects and current-year GitHub activity.

The browser never receives a GitHub token. CI fetches both datasets in one
GraphQL request, validates the complete response and both marker pairs, then
atomically replaces only the configured regions in projects.html.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
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
    ("commits", "Commits", "commits"),
    ("pull-requests", "Pull requests", "pull_requests"),
    ("issues", "Issues", "issues"),
    ("code-reviews", "Code reviews", "reviews"),
    ("repositories", "Repositories with commits", "repositories"),
)

QUERY = """
query ProjectsAndActivity($login: String!, $limit: Int!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    pinnedItems(first: $limit, types: [REPOSITORY]) {
      totalCount
      nodes {
        ... on Repository {
          __typename
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
    contributionsCollection(from: $from, to: $to) {
      startedAt
      endedAt
      contributionCalendar { totalContributions }
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalRepositoriesWithContributedCommits
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


def request_github_data(
    owner: str, token: str, activity_start: str, activity_end: str
) -> dict[str, Any]:
    if not token:
        raise RefreshError("GITHUB_TOKEN is required when --response-file is not used")
    body = json.dumps(
        {
            "query": QUERY,
            "variables": {
                "login": owner,
                "limit": MAX_PINNED_ITEMS,
                "from": activity_start,
                "to": activity_end,
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


def activity_bounds(as_of: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime(as_of.year, 1, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(as_of.year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc)
    return start, end


def activity_timestamp(value: object, field: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise RefreshError(f"GitHub activity has an invalid {field}")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RefreshError(f"GitHub activity has an invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise RefreshError(f"GitHub activity {field} must identify UTC")
    return parsed.astimezone(dt.timezone.utc)


def activity_count(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RefreshError(f"GitHub activity has an invalid {field}")
    return value


def validate_activity(
    user: dict[str, Any], expected_start: dt.datetime, expected_end: dt.datetime
) -> dict[str, Any]:
    collection = user.get("contributionsCollection")
    if not isinstance(collection, dict):
        raise RefreshError("GraphQL response lacks data.user.contributionsCollection")
    calendar = collection.get("contributionCalendar")
    if not isinstance(calendar, dict):
        raise RefreshError("GraphQL response lacks the GitHub contribution calendar")
    started_at = activity_timestamp(collection.get("startedAt"), "startedAt")
    ended_at = activity_timestamp(collection.get("endedAt"), "endedAt")
    if started_at != expected_start or ended_at != expected_end:
        raise RefreshError("GitHub activity boundaries do not match the requested UTC year")
    return {
        "year": expected_start.year,
        "total_contributions": activity_count(
            calendar.get("totalContributions"), "contributionCalendar.totalContributions"
        ),
        "commits": activity_count(
            collection.get("totalCommitContributions"), "totalCommitContributions"
        ),
        "issues": activity_count(
            collection.get("totalIssueContributions"), "totalIssueContributions"
        ),
        "pull_requests": activity_count(
            collection.get("totalPullRequestContributions"), "totalPullRequestContributions"
        ),
        "reviews": activity_count(
            collection.get("totalPullRequestReviewContributions"),
            "totalPullRequestReviewContributions",
        ),
        "repositories": activity_count(
            collection.get("totalRepositoriesWithContributedCommits"),
            "totalRepositoriesWithContributedCommits",
        ),
    }


def validate_response(
    response: dict[str, Any], owner: str, count: int,
    activity_start: dt.datetime, activity_end: dt.datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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
    activity = validate_activity(user, activity_start, activity_end)
    return projects, activity


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
    year = int(activity["year"])
    lines = [
        f'{indent}<div class="github-activity__header">',
        f'{child}<h2 class="github-activity__title" id="github-activity-title"><time class="github-activity__year" datetime="{year}">{year}</time> GitHub activity</h2>',
        f'{child}<p class="github-activity__status">Year-to-date public contribution totals <span aria-hidden="true">·</span> Refreshed daily</p>',
        f"{indent}</div>",
        f'{indent}<dl class="github-activity__stats" aria-label="Public GitHub activity statistics for {year}">',
    ]
    for key, label, value_key in ACTIVITY_METRICS:
        value = int(activity[value_key])
        lines.extend(
            [
                f'{child}<div class="github-activity-stat" data-github-metric="{key}">',
                f'{grandchild}<dt class="github-activity-stat__label">{label}</dt>',
                f'{grandchild}<dd class="github-activity-stat__value">{value:,}</dd>',
                f"{child}</div>",
            ]
        )
    lines.append(f"{indent}</dl>")
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
    parser.add_argument("--target", type=Path, help="Override the configured HTML target")
    parser.add_argument(
        "--as-of",
        help="Select the UTC calendar year from a fixed ISO timestamp (defaults to now)",
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
        activity_start, activity_end = activity_bounds(as_of)
        if args.response_file:
            response = load_response(args.response_file.resolve())
        else:
            response = request_github_data(
                owner,
                os.environ.get("GITHUB_TOKEN", ""),
                github_datetime(activity_start),
                github_datetime(activity_end),
            )
        projects, activity = validate_response(
            response, owner, count, activity_start, activity_end
        )

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
            "activity_year": activity["year"],
            "activity_total": activity["total_contributions"],
            "target": str(target),
        }
        print(json.dumps(result, sort_keys=True) if args.json else (
            f"Refreshed {len(projects)} pinned projects and {activity['year']} activity in {target}"
            + ("" if changed else " (unchanged)")
        ))
        return 0
    except (RefreshError, OSError) as exc:
        result = {"status": "error", "message": str(exc)}
        print(json.dumps(result, sort_keys=True) if args.json else f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
