"""Privacy and correctness checks for the internal-only account aggregate prototype."""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import test_github_profile_history as fixtures

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "account_snapshot", ROOT / ".github/scripts/refresh_github_account_snapshot.py",
)
snapshot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshot)
NOW, FIRST = fixtures.AS_OF, fixtures.START
LAST = fixtures.END - snapshot.dt.timedelta(days=1)


def response(total=30):
    return {
        "data": {"viewer": {
            "login": "josiahH-cf",
            "chunk0": {
                "startedAt": f"{FIRST}T00:00:00Z",
                "endedAt": "2025-12-31T23:59:59Z",
                "contributionCalendar": {"totalContributions": 7},
            },
            "chunk1": {
                "startedAt": "2026-01-01T00:00:00Z",
                "endedAt": f"{LAST}T23:59:59Z",
                "contributionCalendar": {"totalContributions": total - 7},
            },
        }},
    }


def completed(value=None, *, body=None, code=0, http=200):
    payload = json.dumps(response() if value is None else value) if body is None else body
    # Scope metadata is deliberately not treated as a permission verdict.
    return subprocess.CompletedProcess(
        ["gh"], code,
        f"HTTP/2.0 {http} OK\nX-OAuth-Scopes: repo\n\n{payload}",
        "SYNTHETIC_SENSITIVE_ERROR",
    )


class AggregateRequestTests(unittest.TestCase):
    def query(self, value=None, **kwargs):
        with mock.patch.object(snapshot.subprocess, "run", return_value=completed(value, **kwargs)):
            return snapshot.query_aggregates(FIRST, LAST)

    def test_success_with_repo_scope_metadata_is_not_a_denial(self):
        self.assertEqual(self.query(), 30)

    def test_query_is_aggregate_only_noninteractive_bounded_and_year_split(self):
        with mock.patch.object(snapshot.subprocess, "run", return_value=completed()) as run:
            self.assertEqual(snapshot.query_aggregates(FIRST, LAST), 30)
        command = run.call_args.args[0]
        query = next(value for value in command if value.startswith("query="))
        for forbidden in ("repository", "repositories", "nodes", "events", "restrictedContributionsCount", "auth token"):
            self.assertNotIn(forbidden, query)
        self.assertIn("viewer{login", query)
        self.assertIn("totalContributions", query)
        self.assertIn("from0=2025-10-12T00:00:00Z", command)
        self.assertIn("to0=2025-12-31T23:59:59Z", command)
        self.assertIn("from1=2026-01-01T00:00:00Z", command)
        self.assertIn("to1=2026-10-15T23:59:59Z", command)
        self.assertEqual(run.call_args.kwargs["timeout"], 40)
        self.assertEqual(run.call_args.kwargs["env"]["GH_PROMPT_DISABLED"], "1")
        self.assertEqual(run.call_args.kwargs["env"]["GH_DEBUG"], "")
        self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_unknown_fields_and_graphql_errors_are_rejected(self):
        mutations = [
            lambda v: v.update(errors=[{"message": "SYNTHETIC_SENSITIVE_ERROR"}]),
            lambda v: v["data"]["viewer"].update(repository="SYNTHETIC_PRIVATE_DETAIL"),
            lambda v: v["data"]["viewer"]["chunk0"].update(events=[]),
            lambda v: v["data"]["viewer"]["chunk1"]["contributionCalendar"].update(extra=1),
        ]
        for mutate in mutations:
            value = response()
            mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(snapshot.SnapshotError) as error:
                self.query(value)
            self.assertNotIn("SYNTHETIC", str(error.exception))

    def test_wrong_owner_missing_chunk_and_wrong_bounds_are_rejected(self):
        for key in ("owner", "chunk", "start", "end"):
            value = response()
            if key == "owner":
                value["data"]["viewer"]["login"] = "another-user"
            elif key == "chunk":
                del value["data"]["viewer"]["chunk1"]
            elif key == "start":
                value["data"]["viewer"]["chunk1"]["startedAt"] = "2025-12-31T00:00:00Z"
            else:
                value["data"]["viewer"]["chunk0"]["endedAt"] = "2026-01-01T23:59:59Z"
            with self.subTest(key=key), self.assertRaises(snapshot.SnapshotError):
                self.query(value)

    def test_noninteger_negative_and_excessive_counts_are_rejected(self):
        for count in (True, "7", None, -1, 1.5, 100_000_001):
            value = response()
            value["data"]["viewer"]["chunk0"]["contributionCalendar"]["totalContributions"] = count
            with self.subTest(count=count), self.assertRaises(snapshot.SnapshotError):
                self.query(value)

    def test_duplicate_json_invalid_json_and_wrong_root_are_rejected(self):
        for body in ('{"data":{},"data":{}}', "not-json", "[]", "null"):
            with self.subTest(body=body), self.assertRaises(snapshot.SnapshotError):
                self.query(body=body)

    def test_http_and_process_failures_are_sanitized(self):
        for kwargs in ({"code": 1}, {"http": 403}, {"body": "x" * 20_001}):
            with self.subTest(kwargs=list(kwargs)), self.assertRaises(snapshot.SnapshotError) as error:
                self.query(**kwargs)
            self.assertNotIn("SYNTHETIC", str(error.exception))

    def test_timeout_and_missing_cli_are_sanitized(self):
        for error in (subprocess.TimeoutExpired("SYNTHETIC", 40), OSError("SYNTHETIC")):
            with mock.patch.object(snapshot.subprocess, "run", side_effect=error):
                with self.assertRaises(snapshot.SnapshotError) as raised:
                    snapshot.query_aggregates(FIRST, LAST)
                self.assertNotIn("SYNTHETIC", str(raised.exception))

    def test_leap_year_and_three_calendar_year_chunks_are_contiguous(self):
        first = snapshot.dt.date(2023, 12, 31)
        last = snapshot.dt.date(2025, 1, 2)
        value = {"data": {"viewer": {"login": "josiahH-cf"}}}
        for index, (start, end) in enumerate((
            ("2023-12-31", "2023-12-31"),
            ("2024-01-01", "2024-12-31"),
            ("2025-01-01", "2025-01-02"),
        )):
            value["data"]["viewer"][f"chunk{index}"] = {
                "startedAt": start + "T00:00:00Z", "endedAt": end + "T23:59:59Z",
                "contributionCalendar": {"totalContributions": index},
            }
        with mock.patch.object(snapshot.subprocess, "run", return_value=completed(value)):
            self.assertEqual(snapshot.query_aggregates(first, last), 3)


class SnapshotSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.activity = snapshot.public.parse_public_calendar(fixtures.public_fixture(), "josiahH-cf", NOW)
        self.value = snapshot.make_snapshot(self.activity, 30, NOW)

    def test_completed_day_cutoff_uses_the_identical_public_and_auth_window(self):
        self.assertEqual(self.value["from"], str(FIRST))
        self.assertEqual(self.value["to"], str(LAST))
        self.assertEqual(self.value["public_total"], 12)
        self.assertEqual(self.activity["total_contributions"], 19)

    def test_equal_greater_and_zero_totals_never_imply_private_zero_or_publication(self):
        for total in (12, 30):
            value = snapshot.make_snapshot(self.activity, total, NOW)
            self.assertIsNone(value["private_total"])
            self.assertIs(value["publication_eligible"], False)
        zero_activity = snapshot.public.parse_public_calendar(
            fixtures.public_fixture(counts={}), "josiahH-cf", NOW,
        )
        zero = snapshot.make_snapshot(zero_activity, 0, NOW)
        self.assertIsNone(zero["private_total"])
        self.assertEqual(zero["private_total_status"], "not_separately_verified")

    def test_private_zero_claim_and_unverified_publication_flag_are_rejected(self):
        for key, value in (("private_total", 0), ("private_total", 1), ("publication_eligible", True),
                           ("private_total_status", "verified"), ("schema_version", True),
                           ("source", "another-source"), ("refresh_mode", "daily")):
            altered = copy.deepcopy(self.value)
            altered[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(snapshot.SnapshotError):
                snapshot.validate_snapshot(altered, NOW)

    def test_unknown_fields_missing_fields_future_time_and_bad_windows_are_rejected(self):
        changes = (
            lambda v: v.update(extra="SYNTHETIC"),
            lambda v: v.pop("public_total"),
            lambda v: v.update(checked_at="2099-01-01T00:00:00Z"),
            lambda v: v.update(to=str(fixtures.END)),
            lambda v: v.update(**{"from": "2025-10-13"}),
            lambda v: v.update(**{"from": "2024-01-01"}),
            lambda v: v.update(authenticated_total=11),
            lambda v: v.update(checked_at="2026-10-16T19:00:00+00:00"),
        )
        for change in changes:
            altered = copy.deepcopy(self.value)
            change(altered)
            with self.subTest(change=change), self.assertRaises(snapshot.SnapshotError):
                snapshot.validate_snapshot(altered, NOW)

    def test_same_window_verification_is_explicitly_not_private_verification(self):
        with mock.patch.object(snapshot, "query_aggregates", return_value=30) as query, \
             mock.patch.object(snapshot.public, "request_public_calendar", return_value=self.activity):
            result = snapshot.verify_snapshot(self.value)
        query.assert_called_once_with(FIRST, LAST)
        self.assertTrue(result["authenticated_same_window_matches"])
        self.assertTrue(result["public_same_window_matches"])
        self.assertFalse(result["publication_eligible"])
        self.assertIsNone(result["private_total"])

    def test_changed_totals_fail_instead_of_claiming_current(self):
        with mock.patch.object(snapshot, "query_aggregates", return_value=31):
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.verify_snapshot(self.value)
        changed = copy.deepcopy(self.activity)
        changed["calendar_days"][0]["count"] += 1
        with mock.patch.object(snapshot, "query_aggregates", return_value=30), \
             mock.patch.object(snapshot.public, "request_public_calendar", return_value=changed):
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.verify_snapshot(self.value)

    def test_old_snapshot_outside_public_window_cannot_claim_public_match(self):
        later = copy.deepcopy(self.activity)
        later["start_date"] = FIRST + snapshot.dt.timedelta(days=7)
        with mock.patch.object(snapshot, "query_aggregates", return_value=30), \
             mock.patch.object(snapshot.public, "request_public_calendar", return_value=later):
            result = snapshot.verify_snapshot(self.value)
        self.assertFalse(result["public_window_covered"])
        self.assertIsNone(result["public_same_window_matches"])

    def test_cli_capture_writes_no_website_or_credentials(self):
        stdout = io.StringIO()
        before = (ROOT / "projects.html").read_bytes()
        with mock.patch.object(snapshot, "utc_now", return_value=NOW), \
             mock.patch.object(snapshot.public, "request_public_calendar", return_value=self.activity), \
             mock.patch.object(snapshot, "query_aggregates", return_value=30), \
             mock.patch.object(snapshot.public, "atomic_write") as write, \
             contextlib.redirect_stdout(stdout):
            self.assertEqual(snapshot.main([]), 0)
        write.assert_not_called()
        result = json.loads(stdout.getvalue())
        self.assertFalse(result["snapshot"]["publication_eligible"])
        self.assertEqual(before, (ROOT / "projects.html").read_bytes())

    def test_cli_failure_never_emits_raw_error_or_response(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(snapshot.public, "request_public_calendar", side_effect=RuntimeError("SYNTHETIC_PRIVATE")), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(snapshot.main([]), 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn("SYNTHETIC", stderr.getvalue())
        self.assertEqual(json.loads(stderr.getvalue())["status"], "error")

    def test_cli_check_reads_dated_evidence_only_and_does_not_mutate_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "internal.json"
            content = json.dumps(self.value).encode("utf-8")
            path.write_bytes(content)
            stdout = io.StringIO()
            with mock.patch.object(snapshot, "query_aggregates", return_value=30), \
                 mock.patch.object(snapshot.public, "request_public_calendar", return_value=self.activity), \
                 contextlib.redirect_stdout(stdout):
                self.assertEqual(snapshot.main(["--check-snapshot", str(path)]), 0)
            self.assertEqual(path.read_bytes(), content)
            self.assertFalse(json.loads(stdout.getvalue())["publication_eligible"])


if __name__ == "__main__":
    unittest.main()
