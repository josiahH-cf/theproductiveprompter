#!/usr/bin/env python3
"""Internal-only aggregate evidence prototype using existing GitHub CLI auth.

No website writer, public renderer, automatic credential route, or private-zero
inference exists here. A successful response is evidence of what this credential
can see, not proof that all private contributions have been included.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

SPEC = importlib.util.spec_from_file_location(
    "public_github_calendar", Path(__file__).with_name("refresh_pinned_projects.py")
)
public = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(public)

SOURCE = "authenticated-github-graphql"
FIELDS = {
    "schema_version", "owner", "from", "to", "checked_at", "authenticated_total",
    "public_total", "private_total", "private_total_status", "source",
    "refresh_mode", "window_mode", "publication_eligible",
}


class SnapshotError(RuntimeError):
    """Only fixed, privacy-safe messages may cross this boundary."""


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def strict_json(source):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise SnapshotError("Duplicate JSON fields rejected.")
            result[key] = value
        return result
    try:
        return json.loads(source, object_pairs_hook=unique)
    except (ValueError, TypeError):
        raise SnapshotError("Invalid aggregate JSON; response suppressed.") from None


def count(value):
    if type(value) is not int or not 0 <= value <= 100_000_000:
        raise SnapshotError("Aggregate count failed numeric validation.")
    return value


def date(value):
    try:
        return public.calendar_date(value, "snapshot date")
    except Exception:
        raise SnapshotError("Invalid snapshot date.") from None


def query_aggregates(start, end):
    """Only an identity and contiguous, year-bounded numeric aggregates."""
    if start > end or (end - start).days > 371:
        raise SnapshotError("Invalid aggregate request window.")
    ranges = []
    cursor = start
    while cursor <= end:
        last = min(dt.date(cursor.year, 12, 31), end)
        ranges.append((f"{cursor}T00:00:00Z", f"{last}T23:59:59Z"))
        cursor = last + dt.timedelta(days=1)
    declarations, fields, variables = [], [], {}
    for index, (first, last) in enumerate(ranges):
        declarations.extend([f"$from{index}:DateTime!", f"$to{index}:DateTime!"])
        variables[f"from{index}"], variables[f"to{index}"] = first, last
        fields.append(
            f"chunk{index}:contributionsCollection(from:$from{index},to:$to{index})"
            "{startedAt endedAt contributionCalendar{totalContributions}}"
        )
    query = "query(" + ",".join(declarations) + "){viewer{login " + " ".join(fields) + "}}"
    command = ["gh", "api", "graphql", "--include", "--hostname", "github.com", "-f", "query=" + query]
    for key, value in variables.items():
        command.extend(["-f", f"{key}={value}"])
    environment = dict(os.environ, GH_PROMPT_DISABLED="1", GH_DEBUG="")
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            timeout=40, check=False, env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        raise SnapshotError("Existing-account aggregate request failed; details suppressed.") from None
    if result.returncode or len(result.stdout) > 20_000:
        raise SnapshotError("Existing-account aggregate request failed; details suppressed.")
    headers, separator, body = result.stdout.replace("\r\n", "\n").partition("\n\n")
    if not separator or not re.fullmatch(r"HTTP/\S+ 200(?: [^\n]*)?", headers.splitlines()[0]):
        raise SnapshotError("Aggregate request did not return HTTP 200; details suppressed.")
    response = strict_json(body)
    if not isinstance(response, dict) or set(response) != {"data"}:
        raise SnapshotError("Aggregate response failed field validation; details suppressed.")
    data = response["data"]
    if not isinstance(data, dict) or set(data) != {"viewer"}:
        raise SnapshotError("Aggregate response failed field validation; details suppressed.")
    viewer = data["viewer"]
    expected = {"login", *(f"chunk{i}" for i in range(len(ranges)))}
    if not isinstance(viewer, dict) or set(viewer) != expected or viewer["login"] != public.DEFAULT_OWNER:
        raise SnapshotError("Aggregate response failed identity validation; details suppressed.")
    total = 0
    for index, (first, last) in enumerate(ranges):
        chunk = viewer[f"chunk{index}"]
        if not isinstance(chunk, dict) or set(chunk) != {"startedAt", "endedAt", "contributionCalendar"}:
            raise SnapshotError("Aggregate response failed collection validation.")
        if chunk["startedAt"] != first or chunk["endedAt"] != last:
            raise SnapshotError("Aggregate source returned a different date window.")
        calendar = chunk["contributionCalendar"]
        if not isinstance(calendar, dict) or set(calendar) != {"totalContributions"}:
            raise SnapshotError("Aggregate response failed calendar validation.")
        total += count(calendar["totalContributions"])
    return count(total)



def validate_snapshot(value, now=None):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise SnapshotError("Snapshot failed the exact-field allowlist.")
    if (
        type(value["schema_version"]) is not int or value["schema_version"] != 1
        or value["owner"] != public.DEFAULT_OWNER or value["source"] != SOURCE
        or value["refresh_mode"] != "manual" or value["window_mode"] != "completed-utc-days"
        or value["private_total"] is not None
        or value["private_total_status"] != "not_separately_verified"
        or value["publication_eligible"] is not False
    ):
        raise SnapshotError("Internal evidence visibility contract is invalid.")
    first, last = date(value["from"]), date(value["to"])
    try:
        stamp = public.parse_as_of(value["checked_at"])
    except Exception:
        raise SnapshotError("Snapshot timestamp is invalid.") from None
    if public.github_datetime(stamp) != value["checked_at"]:
        raise SnapshotError("Snapshot timestamp must be canonical UTC.")
    if (
        not 364 <= (last - first).days + 1 <= 371
        or first.weekday() != 6 or last >= stamp.date()
        or stamp > (now or utc_now())
    ):
        raise SnapshotError("Snapshot window or freshness semantics are invalid.")
    if count(value["authenticated_total"]) < count(value["public_total"]):
        raise SnapshotError("Authenticated total is below its public comparison.")
    return value


def make_snapshot(activity, authenticated_total, now):
    first = activity["start_date"]
    last = activity["end_date"] - dt.timedelta(days=1)
    baseline = sum(day["count"] for day in activity["calendar_days"] if first <= day["date"] <= last)
    return validate_snapshot({
        "schema_version": 1, "owner": public.DEFAULT_OWNER, "from": first.isoformat(),
        "to": last.isoformat(), "checked_at": public.github_datetime(now),
        "authenticated_total": authenticated_total, "public_total": baseline,
        "private_total": None, "private_total_status": "not_separately_verified",
        "source": SOURCE, "refresh_mode": "manual", "window_mode": "completed-utc-days",
        "publication_eligible": False,
    }, now)


def verify_snapshot(value):
    validate_snapshot(value)
    first, last = date(value["from"]), date(value["to"])
    observed = query_aggregates(first, last)
    if observed != value["authenticated_total"]:
        raise SnapshotError("Dated authenticated total changed; evidence needs review.")
    activity = public.request_public_calendar(public.DEFAULT_OWNER, utc_now())
    covered = activity["start_date"] <= first <= last <= activity["end_date"]
    if covered:
        current_public = sum(day["count"] for day in activity["calendar_days"] if first <= day["date"] <= last)
        if current_public != value["public_total"]:
            raise SnapshotError("Dated public comparison changed; evidence needs review.")
    return {
        "status": "needs-private-inclusion-evidence", "mode": "verify",
        "from": value["from"], "to": value["to"], "authenticated_total": observed,
        "public_total": value["public_total"], "private_total": None,
        "private_total_status": value["private_total_status"], "publication_eligible": False,
        "authenticated_same_window_matches": True,
        "public_same_window_matches": True if covered else None,
        "public_window_covered": covered, "snapshot_checked_at": value["checked_at"],
        "http_status": 200, "process_exit_code": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-snapshot", type=Path, help="Compare an INTERNAL dated evidence JSON file to fresh same-window sources")
    args = parser.parse_args(argv)
    try:
        if args.check_snapshot:
            content = args.check_snapshot.read_bytes()
            if len(content) > 20_000:
                raise SnapshotError("Internal evidence file exceeds its size limit.")
            result = verify_snapshot(validate_snapshot(strict_json(content.decode("utf-8"))))
        else:
            now = utc_now()
            activity = public.request_public_calendar(public.DEFAULT_OWNER, now)
            first, last = activity["start_date"], activity["end_date"] - dt.timedelta(days=1)
            value = make_snapshot(activity, query_aggregates(first, last), now)
            result = {
                "status": "needs-private-inclusion-evidence", "mode": "capture",
                "http_status": 200, "process_exit_code": 0, "snapshot": value,
            }
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        # Never interpolate raw CLI, API, parse, or filesystem errors. This
        # helper performs no writes, including on a failed/partial response.
        print(json.dumps({"status": "error", "message": "Aggregate evidence failed safely; no source response or credential details emitted."}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
