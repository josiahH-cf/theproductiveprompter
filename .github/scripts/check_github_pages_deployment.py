#!/usr/bin/env python3
"""Probe the exact public Pages deployment when legacy build status is stale.

This is one bounded, read-only probe, not another watcher or build request. The
calling workflow retains its existing 25-minute deadline and credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

REPOSITORY = "josiahH-cf/theproductiveprompter"
PAGES_PATH = "dynamic/pages/pages-build-deployment"
RUN_FIELDS = "{id,head_sha,head_branch,path,event,status,conclusion}"


def deployment_state(payload, commit):
    """Only the newest matching main-branch Pages run can confirm deployment."""
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid commit")
    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
        raise ValueError("Invalid workflow response")
    matching = [run for run in payload["workflow_runs"] if (
        isinstance(run, dict)
        and type(run.get("id")) is int and run["id"] > 0
        and run.get("head_sha") == commit
        and run.get("head_branch") == "main"
        and run.get("path") == PAGES_PATH
        and run.get("event") == "dynamic"
    )]
    if not matching:
        return "pending", None
    latest = max(matching, key=lambda run: run["id"])
    if latest.get("status") != "completed":
        return "pending", latest["id"]
    if latest.get("conclusion") == "success":
        return "success", latest["id"]
    if latest.get("conclusion") in {"failure", "timed_out", "action_required"}:
        return "failure", latest["id"]
    # Cancellation can be a normal handoff to a replacement that is not listed
    # yet. It never proves success, and the caller's deadline still bounds it.
    return "pending", latest["id"]


def probe(commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid commit")
    environment = dict(os.environ)
    environment.update(GH_DEBUG="", GH_PROMPT_DISABLED="1", GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(
        ["gh", "api", "--hostname", "github.com", "-H", "X-GitHub-Api-Version: 2026-03-10",
         f"repos/{REPOSITORY}/actions/runs?head_sha={commit}&event=dynamic&per_page=30",
         "--jq", "{workflow_runs: [.workflow_runs[] | " + RUN_FIELDS + "]}"],
        capture_output=True, text=True, timeout=30, check=False, env=environment,
    )
    if result.returncode != 0 or len(result.stdout) > 250_000:
        raise ValueError("Workflow status unavailable")
    return deployment_state(json.loads(result.stdout), commit)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        print("Invalid Pages commit.", file=sys.stderr)
        return 2
    try:
        status, run_id = probe(args.commit)
    except Exception:
        print("Pages workflow status unavailable; retrying within the existing deadline.")
        return 1
    print(f"Exact-commit Pages workflow: {status} (commit={args.commit}, run={run_id}).")
    return {"success": 0, "pending": 1, "failure": 2}[status]


if __name__ == "__main__":
    raise SystemExit(main())
