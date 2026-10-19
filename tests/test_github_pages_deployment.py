"""Adversarial checks for stale legacy Pages status and replacement runs."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pages_deployment", ROOT / ".github/scripts/check_github_pages_deployment.py"
)
pages = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pages)
COMMIT = "a" * 40
RUN = {"id": 20, "head_sha": COMMIT, "head_branch": "main", "path": pages.PAGES_PATH,
       "event": "dynamic", "status": "completed", "conclusion": "success"}


class PagesDeploymentTests(unittest.TestCase):
    def state(self, *runs):
        return pages.deployment_state({"workflow_runs": list(runs)}, COMMIT)

    def test_cancelled_legacy_handoff_waits_then_accepts_exact_replacement(self):
        cancelled = dict(RUN, id=19, conclusion="cancelled")
        self.assertEqual(self.state(cancelled), ("pending", 19))
        self.assertEqual(self.state(cancelled, dict(RUN, status="in_progress", conclusion=None)), ("pending", 20))
        self.assertEqual(self.state(cancelled, RUN), ("success", 20))

    def test_wrong_commit_branch_workflow_event_and_invalid_id_cannot_prove_success(self):
        for field, value in (("head_sha", "b" * 40), ("head_branch", "other"),
                             ("path", ".github/workflows/unrelated.yml"), ("event", "push"),
                             ("id", True), ("id", -1)):
            with self.subTest(field=field, value=value):
                self.assertEqual(self.state(dict(RUN, **{field: value})), ("pending", None))

    def test_newest_run_wins_even_when_api_order_changes(self):
        queued = dict(RUN, id=21, status="queued", conclusion=None)
        self.assertEqual(self.state(RUN, queued), ("pending", 21))
        self.assertEqual(self.state(queued, RUN), ("pending", 21))

    def test_actual_terminal_failures_fail_and_unknown_results_never_pass(self):
        for conclusion in ("failure", "timed_out", "action_required"):
            self.assertEqual(self.state(dict(RUN, conclusion=conclusion)), ("failure", 20))
        for conclusion in ("cancelled", "skipped", "neutral", None, "unexpected"):
            self.assertEqual(self.state(dict(RUN, conclusion=conclusion)), ("pending", 20))
        self.assertEqual(self.state(), ("pending", None))

    def test_invalid_response_or_commit_is_rejected(self):
        for payload in (None, [], {}, {"workflow_runs": None}):
            with self.assertRaises(ValueError):
                pages.deployment_state(payload, COMMIT)
        with self.assertRaises(ValueError):
            pages.deployment_state({"workflow_runs": []}, "main; echo SYNTHETIC")

    def test_probe_is_bounded_fixed_repository_read_only_and_noninteractive(self):
        result = types.SimpleNamespace(returncode=0, stdout=json.dumps({"workflow_runs": [RUN]}))
        with mock.patch.object(pages.subprocess, "run", return_value=result) as execute:
            self.assertEqual(pages.probe(COMMIT), ("success", 20))
        args, options = execute.call_args
        command = args[0]
        self.assertIn(f"repos/{pages.REPOSITORY}/actions/runs?head_sha={COMMIT}&event=dynamic&per_page=30", command)
        self.assertIn("github.com", command)
        self.assertNotIn("POST", command)
        self.assertNotIn("--method", command)
        self.assertEqual(options["timeout"], 30)
        self.assertEqual(options["env"]["GH_DEBUG"], "")
        self.assertEqual(options["env"]["GH_PROMPT_DISABLED"], "1")

    def test_transport_errors_timeouts_and_response_details_are_sanitized(self):
        failures = [ValueError("SYNTHETIC-PRIVATE-DETAIL"),
                    subprocess.TimeoutExpired("SYNTHETIC-CREDENTIAL", 30)]
        for failure in failures:
            output = io.StringIO()
            with mock.patch.object(pages, "probe", side_effect=failure), contextlib.redirect_stdout(output):
                self.assertEqual(pages.main(["--commit", COMMIT]), 1)
            self.assertNotIn("SYNTHETIC", output.getvalue())
        for result in (types.SimpleNamespace(returncode=1, stdout="SYNTHETIC"),
                       types.SimpleNamespace(returncode=0, stdout="x" * 250_001)):
            with mock.patch.object(pages.subprocess, "run", return_value=result), self.assertRaises(ValueError):
                pages.probe(COMMIT)

    def test_cli_codes_and_existing_workflow_guards_remain_bounded(self):
        for status, code in (("success", 0), ("pending", 1), ("failure", 2)):
            with mock.patch.object(pages, "probe", return_value=(status, 20)), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(pages.main(["--commit", COMMIT]), code)
        workflow = (ROOT / ".github/workflows/refresh-pinned-projects.yml").read_text(encoding="utf-8")
        error_branch = workflow.split('"$latest_status" == "errored"', 1)[1].split("fi", 1)[0]
        self.assertNotIn("exit 1", error_branch)
        for guard in ("deadline=$((SECONDS + 1500))", "timeout-minutes: 35", "sleep 15",
                      "origin/main moved", "git add -- projects.html", "cancel-in-progress: false"):
            self.assertIn(guard, workflow)
        self.assertIn("python3 .github/scripts/check_github_pages_deployment.py", workflow)
        self.assertNotIn("actions: read", workflow)


if __name__ == "__main__":
    unittest.main()
