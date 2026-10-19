"""Verified profile snapshots: privacy, timezone, freshness and publication guards."""
from __future__ import annotations
import contextlib
import copy
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import test_github_profile_history as fixtures

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("profile_snapshot", ROOT / ".github/scripts/refresh_github_profile_snapshot.py")
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)
NOW = dt.datetime(2026, 10, 19, 9, 29, 4, tzinfo=dt.timezone.utc)
REFERENCE = {
    "schema_version": 1, "source": "github-signed-in-profile",
    "source_url": "https://github.com/josiahH-cf", "owner": "josiahH-cf",
    "from_bound": "2025-10-19 00:00:00 -0500",
    "to_bound": "2026-10-19 23:59:59 -0500",
    "checked_at": "2026-10-19T09:29:04Z", "total_contributions": 12345,
    "includes_private_activity": True,
}
SHELL = fixtures.SHELL + "\n" + profile.START + "\nold profile\n" + profile.END + "\nfinal sentinel\n"


class ProfileReferenceTests(unittest.TestCase):
    def test_exact_local_bounds_survive_without_utc_date_substitution(self):
        self.assertEqual(profile.validate_reference(REFERENCE, now=NOW), REFERENCE)
        block = profile.render_reference(REFERENCE)
        self.assertIn('datetime="2025-10-19T00:00:00-05:00"', block)
        self.assertIn('datetime="2026-10-19T23:59:59-05:00"', block)
        self.assertIn("UTC-05:00", block)
        self.assertIn("12,345", block)
        self.assertNotIn("Private contribution total", block)
        self.assertNotIn("Not separately verified", block)

    def test_unknown_missing_sensitive_fields_and_wrong_owner_source_are_rejected(self):
        for key, value in (
            ("owner", "another-owner"), ("source", "graphql"),
            ("source_url", "https://github.com/josiahH-cf?credential=SYNTHETIC"),
            ("token", "SYNTHETIC"), ("repository", "SYNTHETIC"),
            ("includes_private_activity", False), ("includes_private_activity", 1),
            ("schema_version", True),
        ):
            altered = dict(REFERENCE)
            altered[key] = value
            with self.subTest(key=key), self.assertRaises(profile.evidence.SnapshotError):
                profile.validate_reference(altered, now=NOW)
        altered = dict(REFERENCE)
        del altered["checked_at"]
        with self.assertRaises(profile.evidence.SnapshotError):
            profile.validate_reference(altered, now=NOW)

    def test_invalid_numeric_values_never_reach_public_html(self):
        for value in (True, "12345", -1, 1.5, None, 100_000_001):
            altered = dict(REFERENCE, total_contributions=value)
            with self.subTest(value=value), self.assertRaises(profile.evidence.SnapshotError):
                profile.validate_reference(altered, now=NOW)

    def test_stale_new_reference_rejected_but_dated_existing_snapshot_remains_honest(self):
        later = NOW + dt.timedelta(days=2)
        with self.assertRaises(profile.evidence.SnapshotError):
            profile.validate_reference(REFERENCE, now=later)
        self.assertEqual(profile.validate_reference(REFERENCE, fresh=False, now=later), REFERENCE)
        self.assertIn("refreshed on demand", profile.render_reference(REFERENCE))
        self.assertIn("public calendar above refreshes daily", profile.render_reference(REFERENCE))

    def test_future_time_bad_date_window_and_noncanonical_offsets_are_rejected(self):
        changes = (
            {"checked_at": "2099-10-19T09:29:04Z"},
            {"from_bound": "2026-10-18 00:00:00 -0500"},
            {"from_bound": "2025-10-20 00:00:00 -0500"},
            {"from_bound": "2025-10-19 01:00:00 -0500"},
            {"to_bound": "2026-10-20 23:59:59 -0500"},
            {"to_bound": "2026-10-19 23:59:59 UTC"},
            {"checked_at": "2026-10-19T09:29:04+00:00"},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(profile.evidence.SnapshotError):
                profile.validate_reference(dict(REFERENCE, **change), now=NOW)

    def test_absent_dispatch_data_preserves_daily_public_only_behavior(self):
        for verified in ("", "false"):
            with mock.patch.dict(os.environ, {key: "" for key in profile.DISPATCH_FIELDS}), \
                 mock.patch.dict(os.environ, {"PROFILE_SNAPSHOT_VERIFIED": verified}), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(profile.dispatch_reference())
                self.assertEqual(profile.main(["--dispatch-env"]), 0)

    def test_dispatch_is_explicit_complete_numeric_and_not_shell_interpolated(self):
        env = {
            "PROFILE_SNAPSHOT_VERIFIED": "true", "PROFILE_SNAPSHOT_TOTAL": "12345",
            "PROFILE_SNAPSHOT_FROM": REFERENCE["from_bound"], "PROFILE_SNAPSHOT_TO": REFERENCE["to_bound"],
            "PROFILE_SNAPSHOT_CHECKED_AT": REFERENCE["checked_at"],
        }
        with mock.patch.dict(os.environ, env), mock.patch.object(profile.evidence, "utc_now", return_value=NOW):
            self.assertEqual(profile.dispatch_reference(), REFERENCE)
        for field, value in (
            ("PROFILE_SNAPSHOT_VERIFIED", "false"), ("PROFILE_SNAPSHOT_TOTAL", ""),
            ("PROFILE_SNAPSHOT_TOTAL", "1e5"), ("PROFILE_SNAPSHOT_TOTAL", "1; echo SYNTHETIC"),
            ("PROFILE_SNAPSHOT_CHECKED_AT", ""),
        ):
            with mock.patch.dict(os.environ, dict(env, **{field: value})), \
                 self.assertRaises(profile.evidence.SnapshotError):
                profile.dispatch_reference()
        workflow = (ROOT / ".github/workflows/refresh-pinned-projects.yml").read_text(encoding="utf-8")
        self.assertIn("PROFILE_SNAPSHOT_TOTAL: ${{ inputs.profile_snapshot_total }}", workflow)
        self.assertNotIn('run: ${{', workflow)
        self.assertIn('cron: "17 6 * * *"', workflow)
        self.assertIn("origin/main moved during the refresh", workflow)

    def render_cli(self, root, reference=None, shell=SHELL):
        page, input_file = root / "page.html", root / "reference.json"
        page.write_bytes(shell.encode("utf-8"))
        input_file.write_text(json.dumps(reference or REFERENCE), encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(profile.evidence, "utc_now", return_value=NOW), \
             mock.patch.object(profile.evidence, "query_aggregates") as auth, \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = profile.main(["--reference", str(input_file), "--target", str(page)])
        auth.assert_not_called()
        return code, page, stdout.getvalue(), stderr.getvalue()

    def test_atomic_region_only_replacement_and_idempotence_lf_crlf(self):
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=repr(newline)), tempfile.TemporaryDirectory() as folder:
                original = SHELL.replace("\n", newline)
                code, page, out, error = self.render_cli(Path(folder), shell=original)
                self.assertEqual(code, 0, error)
                updated = page.read_bytes().decode("utf-8")
                self.assertEqual(original.split(profile.START)[0], updated.split(profile.START)[0])
                self.assertEqual(original.split(profile.END)[1], updated.split(profile.END)[1])
                self.assertEqual(profile.read_reference(updated), REFERENCE)
                code, page, out, error = self.render_cli(Path(folder), shell=updated)
                self.assertEqual(code, 0, error)
                self.assertFalse(json.loads(out)["changed"])

    def test_failure_retains_previous_page_and_sanitizes_errors(self):
        for reference, shell in (
            (dict(REFERENCE, token="SYNTHETIC"), SHELL),
            (dict(REFERENCE, includes_private_activity=False), SHELL),
            (REFERENCE, SHELL + profile.START),
            (REFERENCE, SHELL.replace(profile.END, "")),
        ):
            with tempfile.TemporaryDirectory() as folder:
                code, page, out, error = self.render_cli(Path(folder), reference, shell)
                self.assertEqual(code, 1)
                self.assertEqual(page.read_bytes(), shell.encode("utf-8"))
                self.assertNotIn("SYNTHETIC", error)
                self.assertEqual(out, "")

    def test_display_tampering_duplicate_json_and_marker_overlap_fail_closed(self):
        block = profile.render_reference(REFERENCE)
        source = SHELL.replace("\nold profile\n", "\n" + block + "\n")
        self.assertEqual(profile.read_reference(source), REFERENCE)
        for altered in (
            source.replace(">12,345</data>", ">12,344</data>"),
            source + '<script type="application/json" id="github-profile-snapshot-data">{}</script>',
            source.replace('"schema_version":1', '"schema_version":1,"schema_version":1'),
        ):
            with self.assertRaises(Exception):
                profile.read_reference(altered)

    def test_existing_public_refresh_preserves_the_private_snapshot_exactly(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = SHELL.replace("\nold profile\n", "\n" + profile.render_reference(REFERENCE) + "\n")
            page, calendar = root / "page.html", root / "calendar.html"
            page.write_text(source, encoding="utf-8")
            calendar.write_text(fixtures.public_fixture(), encoding="utf-8")
            argv = [
                "refresh", "--response-file", str(ROOT / "tests/fixtures/pinned_projects_graphql.json"),
                "--profile-file", str(calendar), "--as-of", fixtures.AS_OF.isoformat(),
                "--target", str(page), "--json",
            ]
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(profile.public.main(), 0)
            result = page.read_text(encoding="utf-8")
            self.assertEqual(source.split(profile.START)[1], result.split(profile.START)[1])

    def test_live_transport_is_unauthenticated_bounded_and_fixed_source(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def geturl(self): return profile.LIVE_URL
            headers = mock.Mock()
            def read(self, size):
                self.read_size = size
                return b"safe page"
        response = Response()
        response.headers.get_content_type.return_value = "text/html"
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(profile.urllib.request, "build_opener", return_value=opener):
            self.assertEqual(profile.live_source(), "safe page")
        request = opener.open.call_args.args[0]
        self.assertFalse(request.has_header("Authorization"))
        self.assertFalse(request.has_header("Cookie"))
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 30)
        self.assertEqual(response.read_size, profile.public.MAX_PROFILE_BYTES + 1)


if __name__ == "__main__":
    unittest.main()
