"""Regression coverage for the signed-out GitHub profile calendar refresh."""

from __future__ import annotations

import contextlib
import copy
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "github_refresh", ROOT / ".github/scripts/refresh_pinned_projects.py"
)
refresh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refresh)
UTC = dt.timezone.utc
AS_OF = dt.datetime(2026, 10, 16, 19, 0, tzinfo=UTC)
START = dt.date(2025, 10, 12)
END = AS_OF.date()
SHELL = (
    "prefix sentinel\n<!-- PINNED_PROJECTS_START -->\nold pins\n"
    "<!-- PINNED_PROJECTS_END -->\nbetween sentinel\n"
    "<!-- GITHUB_ACTIVITY_START -->\nlast good snapshot\n"
    "<!-- GITHUB_ACTIVITY_END -->\nsuffix sentinel\n"
)


def public_fixture(
    start: dt.date = START,
    end: dt.date = END,
    counts: dict[dt.date, int] | None = None,
    *,
    row_major: bool = True,
) -> str:
    """Small synthetic copy of GitHub's actual table/tooltip wire format."""
    if counts is None:
        counts = {
            start: 2, start + dt.timedelta(days=1): 1,
            end - dt.timedelta(days=2): 4, end - dt.timedelta(days=1): 5, end: 7,
        }
    days = [
        start + dt.timedelta(days=i)
        for i in range((end - start).days + 1)
    ]
    if row_major:
        days.sort(key=lambda date: ((date.weekday() + 1) % 7, date))
    total = sum(counts.get(date, 0) for date in days)
    parts = [
        '<div class="js-yearly-contributions">',
        '<h2 id="js-contribution-activity-description">'
        f'{total:,} contributions in the last year</h2>',
        '<div class="ContributionCalendar" '
        'data-graph-url="/users/josiahH-cf/contributions" data-url="/josiahH-cf" '
        f'data-from="{start} 00:00:00 UTC" data-to="{end} 23:59:59 UTC" data-org="">',
        '<table><tbody>',
    ]
    for date in days:
        count = counts.get(date, 0)
        level = min(4, count)
        cell_id = f"day-{date}"
        count_label = (
            "No contributions" if not count
            else f'{count:,} contribution{"s" if count != 1 else ""}'
        )
        parts.append(
            '<tr><td class="ContributionCalendar-day" '
            f'id="{cell_id}" data-date="{date}" data-level="{level}"></td>'
            f'<tool-tip for="{cell_id}">{count_label} on '
            f'{refresh.MONTHS[date.month - 1]} {date.day}, {date.year}.</tool-tip></tr>'
        )
    parts.extend([
        '<tr><td class="ContributionCalendar-day"></td></tr>',
        '</tbody></table></div></div>',
    ])
    return "\n".join(parts)


class PublicCalendarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = public_fixture()

    def parse(self, source: str | None = None, as_of: dt.datetime = AS_OF):
        return refresh.parse_public_calendar(
            self.source if source is None else source, "josiahH-cf", as_of
        )

    def test_profile_window_and_sorted_daily_counts_reconcile(self):
        result = self.parse()
        self.assertEqual(result["start_date"], START)
        self.assertEqual(result["end_date"], END)
        self.assertEqual(len(result["calendar_days"]), 370)
        self.assertEqual(result["total_contributions"], 19)
        self.assertEqual(result["active_days"], 5)
        self.assertEqual(result["longest_streak"], 3)
        self.assertEqual(result["calendar_days"][0]["date"], START)
        self.assertEqual(result["calendar_days"][-1]["date"], END)
        self.assertEqual(
            sum(day["count"] for day in result["calendar_days"]), 19
        )
        self.assertEqual(result["fetched_at"], AS_OF)

    def test_leap_day_and_new_year_keep_the_actual_rolling_window(self):
        for end, start in (
            (dt.date(2024, 3, 1), dt.date(2023, 2, 26)),
            (dt.date(2025, 1, 1), dt.date(2023, 12, 31)),
            (dt.date(2025, 3, 1), dt.date(2024, 2, 25)),
        ):
            with self.subTest(end=end):
                as_of = dt.datetime.combine(end, dt.time(12), UTC)
                result = self.parse(public_fixture(start, end), as_of)
                self.assertEqual(result["start_date"], start)
                self.assertEqual(result["end_date"], end)
                dates = [day["date"] for day in result["calendar_days"]]
                self.assertIn(dt.date(2024, 2, 29), dates)
                self.assertEqual(len(dates), (end - start).days + 1)

    def test_empty_but_complete_zero_calendar_is_truthful(self):
        result = self.parse(public_fixture(counts={}))
        self.assertEqual(result["total_contributions"], 0)
        self.assertEqual(result["active_days"], 0)
        self.assertEqual(result["longest_streak"], 0)
        self.assertEqual(len(result["calendar_days"]), 370)

    def test_actual_github_ordinal_labels_without_year_are_supported(self):
        source = self.source.replace(
            "October 12, 2025.", "October 12th."
        ).replace("October 13, 2025.", "October 13th.")
        self.assertEqual(self.parse(source)["total_contributions"], 19)

    def test_duplicate_date_is_rejected(self):
        with self.assertRaises(refresh.RefreshError):
            self.parse(self.source.replace('data-date="2025-10-13"', 'data-date="2025-10-12"'))

    def test_missing_day_is_rejected(self):
        source = "\n".join(
            line for line in self.source.splitlines()
            if 'data-date="2025-10-13"' not in line
        )
        with self.assertRaises(refresh.RefreshError):
            self.parse(source)

    def test_missing_or_duplicate_tooltip_is_rejected(self):
        for source in (
            self.source.replace('for="day-2025-10-13"', 'for="unmatched"'),
            self.source.replace('for="day-2025-10-13"', 'for="day-2025-10-12"'),
        ):
            with self.subTest(source=source[:20]), self.assertRaises(refresh.RefreshError):
                self.parse(source)

    def test_wrong_tooltip_date_or_year_is_rejected(self):
        for source in (
            self.source.replace("October 12, 2025.", "October 13, 2025."),
            self.source.replace("October 12, 2025.", "October 12, 2026."),
        ):
            with self.assertRaises(refresh.RefreshError):
                self.parse(source)

    def test_total_mismatch_is_rejected(self):
        with self.assertRaises(refresh.RefreshError):
            self.parse(self.source.replace("19 contributions in", "20 contributions in"))

    def test_negative_count_and_invalid_level_are_rejected(self):
        for source in (
            self.source.replace("2 contributions on", "-2 contributions on"),
            self.source.replace('data-level="2"', 'data-level="5"'),
            self.source.replace('data-level="2"', 'data-level="0"'),
            self.source.replace('data-level="0"', 'data-level="4"'),
            self.source.replace('data-date="2025-10-12"', 'data-date="2025-10-12" data-count="99"'),
        ):
            with self.assertRaises(refresh.RefreshError):
                self.parse(source)

    def test_wrong_owner_and_filtered_calendar_are_rejected(self):
        for source in (
            self.source.replace('data-url="/josiahH-cf"', 'data-url="/another-user"'),
            self.source.replace('/users/josiahH-cf/', '/users/another-user/'),
            self.source.replace('data-org=""', 'data-org="private-org"'),
        ):
            with self.assertRaises(refresh.RefreshError):
                self.parse(source)

    def test_stale_and_future_snapshots_are_rejected(self):
        for as_of in (AS_OF - dt.timedelta(days=1), AS_OF + dt.timedelta(days=1)):
            with self.assertRaises(refresh.RefreshError):
                self.parse(as_of=as_of)

    def test_future_day_is_rejected_even_if_zero(self):
        with self.assertRaises(refresh.RefreshError):
            self.parse(self.source.replace('data-date="2026-10-16"', 'data-date="2026-10-17"'))

    def test_truncation_login_page_and_unexpected_window_fail_closed(self):
        for source in (
            "", "<html>Sign in</html>",
            self.source.rsplit("</div>", 2)[0],
            self.source.replace("in the last year", "in 2026"),
            self.source.replace("2025-10-12 00:00:00 UTC", "2026-01-01 00:00:00 UTC"),
            self.source.replace("2025-10-12 00:00:00 UTC", "2025-10-13 00:00:00 UTC"),
            self.source.replace("2026-10-16 23:59:59 UTC", "2026-10-16 19:00:00 UTC"),
            self.source.replace('data-org=""', 'data-org="" data-org="hidden"'),
            self.source.replace("</table>", "</table>" + self.source),
        ):
            with self.assertRaises(refresh.RefreshError):
                self.parse(source)

    def test_http_request_cannot_inherit_authenticated_visibility(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = refresh.PUBLIC_CALENDAR_URL
        response.headers.get_content_type.return_value = "text/html"
        response.read.return_value = self.source.encode()
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(refresh.urllib.request, "build_opener", return_value=opener):
            with mock.patch.dict(refresh.os.environ, {"GITHUB_TOKEN": "secret-test-value"}):
                result = refresh.request_public_calendar("josiahH-cf", AS_OF)
        request = opener.open.call_args.args[0]
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertNotIn("authorization", headers)
        self.assertNotIn("cookie", headers)
        self.assertIsNone(request.data)
        self.assertEqual(request.full_url, refresh.PUBLIC_CALENDAR_URL)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 30)
        self.assertEqual(response.read.call_args.args, (refresh.MAX_PROFILE_BYTES + 1,))
        self.assertNotIn("secret-test-value", json.dumps(result, default=str))

    def test_http_error_redirect_type_and_size_are_rejected(self):
        for failure in ("network", "redirect", "content-type", "size"):
            with self.subTest(failure=failure):
                response = mock.MagicMock()
                response.__enter__.return_value = response
                response.geturl.return_value = refresh.PUBLIC_CALENDAR_URL
                response.headers.get_content_type.return_value = "text/html"
                response.read.return_value = self.source.encode()
                opener = mock.Mock()
                opener.open.return_value = response
                if failure == "network":
                    opener.open.side_effect = urllib.error.URLError("offline")
                elif failure == "redirect":
                    response.geturl.return_value = "https://github.com/login"
                elif failure == "content-type":
                    response.headers.get_content_type.return_value = "application/json"
                else:
                    response.read.return_value = b"x" * (refresh.MAX_PROFILE_BYTES + 1)
                with mock.patch.object(refresh.urllib.request, "build_opener", return_value=opener):
                    with self.assertRaises(refresh.RefreshError):
                        refresh.request_public_calendar("josiahH-cf", AS_OF)


class RefreshIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.pins = json.loads(
            (ROOT / "tests/fixtures/pinned_projects_graphql.json").read_text(encoding="utf-8")
        )
        self.source = public_fixture()

    def run_fixture(self, target: Path, source: str | None = None, pins=None, as_of=None):
        pins_path = target.parent / "pins.json"
        profile_path = target.parent / "profile.html"
        pins_path.write_text(json.dumps(self.pins if pins is None else pins), encoding="utf-8")
        profile_path.write_text(self.source if source is None else source, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(ROOT / ".github/scripts/refresh_pinned_projects.py"),
             "--response-file", str(pins_path), "--profile-file", str(profile_path),
             "--target", str(target), "--as-of", as_of or refresh.github_datetime(AS_OF),
             "--json"],
            capture_output=True, text=True, cwd=ROOT, timeout=10,
        )

    def test_cli_preserves_outside_bytes_escaping_and_idempotence(self):
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=repr(newline)), tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / "projects.html"
                original = SHELL.replace("\n", newline).encode()
                target.write_bytes(original)
                result = self.run_fixture(target)
                self.assertEqual(result.returncode, 0, result.stderr)
                rendered = target.read_bytes()
                self.assertTrue(rendered.startswith(("prefix sentinel" + newline + refresh.DEFAULT_START_MARKER).encode()))
                self.assertIn((refresh.DEFAULT_END_MARKER + newline + "between sentinel" + newline + refresh.DEFAULT_ACTIVITY_START_MARKER).encode(), rendered)
                self.assertTrue(rendered.endswith((refresh.DEFAULT_ACTIVITY_END_MARKER + newline + "suffix sentinel" + newline).encode()))
                text = rendered.decode()
                self.assertEqual(text.count('<article class="project-card '), 4)
                self.assertIn("&lt;script&gt;", text)
                self.assertNotIn("<script>window.fixturePwned", text)
                self.assertIn("No description provided.", text)
                self.assertIn("Not specified", text)
                self.assertEqual(text.count('<rect class="github-activity-day '), 370)
                self.assertIn("October 12, 2025", text)
                self.assertIn("October 16, 2026", text)
                self.assertNotIn("Year-to-date", text)
                self.assertNotIn('data-github-metric="commits"', text)
                self.assertIn('data-github-metric="active-days"', text)
                self.assertIn('data-github-metric="longest-streak"', text)
                self.assertIn("Snapshot updated", text)
                self.assertIn('datetime="2026-10-16T19:00:00Z"', text)
                self.assertIn("Signed-in totals may differ", text)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["activity_total"], 19)
                self.assertEqual(payload["activity_from"], str(START))
                self.assertEqual(payload["activity_to"], str(END))
                self.assertEqual(payload["activity_source"], refresh.PUBLIC_CALENDAR_URL)
                repeat = self.run_fixture(target)
                self.assertEqual(repeat.returncode, 0, repeat.stderr)
                self.assertEqual(target.read_bytes(), rendered)
                self.assertFalse(json.loads(repeat.stdout)["changed"])

    def test_bad_public_data_never_replaces_last_good_pins_or_activity(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "projects.html"
            target.write_text(SHELL, encoding="utf-8")
            valid = self.run_fixture(target)
            self.assertEqual(valid.returncode, 0, valid.stderr)
            last_good = target.read_bytes()
            for source in ("", self.source.replace("19 contributions in", "20 contributions in")):
                result = self.run_fixture(target, source=source)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(target.read_bytes(), last_good)

    def test_bad_pin_data_never_replaces_last_good_activity(self):
        variants = {}
        for label in ("errors", "null-user", "three", "five", "partial", "count-type",
                      "duplicate", "url", "name-url", "dot-path", "negative", "timestamp",
                      "private", "missing-visibility"):
            variants[label] = copy.deepcopy(self.pins)
        variants["errors"]["errors"] = [{"message": "unsafe partial response"}]
        variants["null-user"]["data"]["user"] = None
        for label in ("three", "five", "partial", "count-type", "duplicate", "url",
                      "name-url", "dot-path", "negative", "timestamp", "private", "missing-visibility"):
            pinned = variants[label]["data"]["user"]["pinnedItems"]
            nodes = pinned["nodes"]
            if label == "three":
                pinned["totalCount"] = 3
                pinned["nodes"] = nodes[:3]
            elif label == "five":
                pinned["totalCount"] = 5
                nodes.append(copy.deepcopy(nodes[0]))
            elif label == "partial":
                pinned["nodes"] = nodes[:3]
            elif label == "count-type":
                pinned["totalCount"] = "4"
            elif label == "duplicate":
                nodes[-1] = copy.deepcopy(nodes[0])
            elif label == "url":
                nodes[0]["url"] = "javascript:alert(1)"
            elif label == "name-url":
                nodes[0]["name"] = "different-name"
            elif label == "dot-path":
                nodes[0]["name"] = ".."
                nodes[0]["url"] = "https://github.com/josiahH-cf/.."
            elif label == "negative":
                nodes[0]["forkCount"] = -1
            elif label == "timestamp":
                nodes[0]["updatedAt"] = "yesterday"
            elif label == "private":
                nodes[0]["isPrivate"] = True
            elif label == "missing-visibility":
                nodes[0].pop("isPrivate")
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "projects.html"
            for label, pins in variants.items():
                with self.subTest(label=label):
                    target.write_bytes(SHELL.encode())
                    result = self.run_fixture(target, pins=pins)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(target.read_bytes(), SHELL.encode())

    def test_invalid_marker_layouts_are_atomic(self):
        project_start = refresh.DEFAULT_START_MARKER
        project_end = refresh.DEFAULT_END_MARKER
        activity_start = refresh.DEFAULT_ACTIVITY_START_MARKER
        activity_end = refresh.DEFAULT_ACTIVITY_END_MARKER
        layouts = [
            f"{project_end}\n{project_start}\n{activity_start}\n{activity_end}",
            f"{project_start}\n{project_start}\n{project_end}\n{activity_start}\n{activity_end}",
            f"{project_start}\n{project_end}\n{activity_end}\n{activity_start}",
            f"{project_start}\n{project_end}",
            f"{project_start}\n{activity_start}\n{project_end}\n{activity_end}",
            f"{activity_start}\n{activity_end}\n{project_start}\n{project_end}",
            f"{project_start}\n{project_end}\n{activity_start}\n{activity_end}\n{activity_end}",
        ]
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "projects.html"
            for layout in layouts:
                target.write_bytes(layout.encode())
                result = self.run_fixture(target)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(target.read_bytes(), layout.encode())

    def test_fixture_mode_cannot_accidentally_fetch_live_or_accept_bad_time(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "projects.html"
            target.write_bytes(SHELL.encode())
            for as_of in ("today", "2026-10-16T20:00:00+01:00", "2026-10-15T19:00:00Z"):
                result = self.run_fixture(target, as_of=as_of)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(target.read_bytes(), SHELL.encode())
            result = subprocess.run(
                [sys.executable, str(ROOT / ".github/scripts/refresh_pinned_projects.py"),
                 "--response-file", str(target.parent / "pins.json"),
                 "--target", str(target), "--json"],
                capture_output=True, cwd=ROOT, timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_bytes(), SHELL.encode())

    def test_acquisition_failure_preserves_last_good_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "projects.html"
            target.write_bytes(SHELL.encode())
            with mock.patch.object(sys, "argv", ["refresh", "--target", str(target), "--json"]):
                with mock.patch.object(refresh, "request_github_data", return_value=self.pins):
                    with mock.patch.object(refresh, "request_public_calendar", side_effect=refresh.RefreshError("offline")):
                        with contextlib.redirect_stderr(io.StringIO()):
                            code = refresh.main()
            self.assertEqual(code, 1)
            self.assertEqual(target.read_bytes(), SHELL.encode())


if __name__ == "__main__":
    unittest.main()
