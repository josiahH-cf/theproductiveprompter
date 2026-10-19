#!/usr/bin/env python3
"""Render a manually verified signed-in GitHub profile total, without credentials.

The caller must have checked the owner's signed-in profile calendar. Only its
combined anonymous total, exact bounds and check time are accepted. This never
subtracts the separately timed public/API calendar to invent a private-only count.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

SPEC = importlib.util.spec_from_file_location(
    "github_aggregate_evidence", Path(__file__).with_name("refresh_github_account_snapshot.py")
)
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)
public = evidence.public

START = "<!-- GITHUB_PROFILE_SNAPSHOT_START -->"
END = "<!-- GITHUB_PROFILE_SNAPSHOT_END -->"
DATA_ID = "github-profile-snapshot-data"
LIVE_URL = "https://theproductiveprompter.com/projects.html"
FIELDS = {
    "schema_version", "source", "source_url", "owner", "from_bound", "to_bound",
    "checked_at", "total_contributions", "includes_private_activity",
}
DISPATCH_FIELDS = (
    "PROFILE_SNAPSHOT_VERIFIED", "PROFILE_SNAPSHOT_TOTAL", "PROFILE_SNAPSHOT_FROM",
    "PROFILE_SNAPSHOT_TO", "PROFILE_SNAPSHOT_CHECKED_AT",
)


def validate_reference(value, *, fresh=True, now=None):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise evidence.SnapshotError("Profile reference failed the exact-field allowlist.")
    if (
        type(value["schema_version"]) is not int or value["schema_version"] != 1
        or value["source"] != "github-signed-in-profile"
        or value["source_url"] != public.DEFAULT_PROFILE_URL
        or value["owner"] != public.DEFAULT_OWNER
        or value["includes_private_activity"] is not True
    ):
        raise evidence.SnapshotError("Profile reference is not explicitly verified for the owner.")
    evidence.count(value["total_contributions"])
    try:
        first = dt.datetime.strptime(value["from_bound"], "%Y-%m-%d %H:%M:%S %z")
        last = dt.datetime.strptime(value["to_bound"], "%Y-%m-%d %H:%M:%S %z")
        stamp = public.parse_as_of(value["checked_at"])
    except Exception:
        raise evidence.SnapshotError("Profile reference has invalid bounds or timestamp.") from None
    current = now or evidence.utc_now()
    if (
        first.strftime("%Y-%m-%d %H:%M:%S %z") != value["from_bound"]
        or last.strftime("%Y-%m-%d %H:%M:%S %z") != value["to_bound"]
        or public.github_datetime(stamp) != value["checked_at"]
        or first.time() != dt.time(0)
        or last.time() != dt.time(23, 59, 59)
        or first.date().weekday() != 6
        or not 365 <= (last.date() - first.date()).days + 1 <= 372
        or last.date() != stamp.astimezone(last.tzinfo).date()
        or stamp > current
        or (fresh and current - stamp > dt.timedelta(hours=24))
    ):
        raise evidence.SnapshotError("Profile reference window/freshness is invalid.")
    return value


def dispatch_reference():
    values = {key: os.environ.get(key, "") for key in DISPATCH_FIELDS}
    if not any(values.values()) or (
        values["PROFILE_SNAPSHOT_VERIFIED"] in {"", "false"}
        and not any(values[key] for key in DISPATCH_FIELDS[1:])
    ):
        return None
    if values["PROFILE_SNAPSHOT_VERIFIED"] != "true" or not all(values.values()):
        raise evidence.SnapshotError("A dispatch reference must be explicitly confirmed and complete.")
    number = values["PROFILE_SNAPSHOT_TOTAL"]
    if not re.fullmatch(r"0|[1-9]\d{0,8}", number):
        raise evidence.SnapshotError("Dispatch total must be an integer.")
    return validate_reference({
        "schema_version": 1, "source": "github-signed-in-profile",
        "source_url": public.DEFAULT_PROFILE_URL, "owner": public.DEFAULT_OWNER,
        "from_bound": values["PROFILE_SNAPSHOT_FROM"], "to_bound": values["PROFILE_SNAPSHOT_TO"],
        "checked_at": values["PROFILE_SNAPSHOT_CHECKED_AT"],
        "total_contributions": int(number), "includes_private_activity": True,
    })


def date_label(value):
    return f"{public.MONTHS[value.month - 1]} {value.day}, {value.year}"


def render_reference(value, indent="", newline="\n"):
    validate_reference(value, fresh=False)
    first = dt.datetime.strptime(value["from_bound"], "%Y-%m-%d %H:%M:%S %z")
    last = dt.datetime.strptime(value["to_bound"], "%Y-%m-%d %H:%M:%S %z")
    checked = public.parse_as_of(value["checked_at"])
    offsets = [bound.strftime("%z") for bound in (first, last)]
    offsets = [f"UTC{offset[:3]}:{offset[3:]}" for offset in offsets]
    timezone_label = offsets[0] if offsets[0] == offsets[1] else f"{offsets[0]} / {offsets[1]} at bounds"
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).replace("<", "\\u003c")
    lines = [
        '<section class="github-profile-snapshot" aria-labelledby="github-profile-snapshot-title">',
        '  <div class="github-profile-snapshot__total">',
        f'    <data value="{value["total_contributions"]}" class="github-profile-snapshot__number">{value["total_contributions"]:,}</data>',
        '    <span>Contributions including private activity</span>',
        '  </div>',
        '  <div class="github-profile-snapshot__context">',
        '    <h2 id="github-profile-snapshot-title">The fuller picture</h2>',
        f'    <p class="github-profile-snapshot__window"><time datetime="{first.isoformat()}">{date_label(first)}</time> – <time datetime="{last.isoformat()}">{date_label(last)}</time></p>',
        f'    <p>GitHub profile time ({timezone_label}). Combined public and private contributions; anonymous totals only.</p>',
        f'    <p class="github-profile-snapshot__freshness">Verified against the signed-in <a href="{public.DEFAULT_PROFILE_URL}" target="_blank" rel="noopener noreferrer">GitHub profile</a> on <time datetime="{value["checked_at"]}">{date_label(checked)} at {checked:%H:%M} UTC</time>. This dated snapshot is refreshed on demand. The public calendar above refreshes daily.</p>',
        '  </div>',
        f'  <script type="application/json" id="{DATA_ID}">{encoded}</script>',
        '</section>',
    ]
    return newline.join(indent + line for line in lines)


def read_reference(source):
    matches = re.findall(r'<script type="application/json" id="' + DATA_ID + r'">([^<]*)</script>', source)
    if len(matches) != 1 or source.count('id="' + DATA_ID + '"') != 1:
        raise evidence.SnapshotError("Expected one profile aggregate data block.")
    reference = validate_reference(evidence.strict_json(matches[0]), fresh=False)
    validate_layout(source)
    newline = "\r\n" if "\r\n" in source else "\n"
    indent = public.marker_indent(source, source.index(START))
    expected = render_reference(reference, indent, newline)
    rendered = source[source.index(START) + len(START):source.index(END)]
    if rendered != newline + expected + newline + indent:
        raise evidence.SnapshotError("Displayed aggregate does not match its verified reference.")
    return reference


def validate_layout(source):
    public.validate_marker_layout(source, (
        (public.DEFAULT_START_MARKER, public.DEFAULT_END_MARKER, "public pins"),
        (public.DEFAULT_ACTIVITY_START_MARKER, public.DEFAULT_ACTIVITY_END_MARKER, "public calendar"),
        (START, END, "verified profile snapshot"),
    ))


def live_source():
    request = urllib.request.Request(LIVE_URL, headers={"Accept": "text/html", "Cache-Control": "no-cache"})
    with urllib.request.build_opener().open(request, timeout=30) as response:
        if response.geturl() != LIVE_URL or response.headers.get_content_type() != "text/html":
            raise evidence.SnapshotError("Unexpected live response.")
        content = response.read(public.MAX_PROFILE_BYTES + 1)
    if len(content) > public.MAX_PROFILE_BYTES:
        raise evidence.SnapshotError("Live response exceeds its size limit.")
    return content.decode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--reference", type=Path, help="Explicitly verified aggregate reference; never a credential file")
    mode.add_argument("--dispatch-env", action="store_true", help="Use allowlisted, manually confirmed workflow inputs")
    mode.add_argument("--check", action="store_true", help="Check local display/reference consistency without changing it")
    mode.add_argument("--check-live", action="store_true", help="Check the deployed dated snapshot, without credentials")
    parser.add_argument("--target", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.check_live and args.target:
            raise evidence.SnapshotError("Live checks use only the fixed production URL.")
        target = args.target or Path(__file__).resolve().parents[2] / "projects.html"
        if args.dispatch_env:
            reference = dispatch_reference()
            if reference is None:
                print(json.dumps({"status": "skipped", "reason": "No manually verified profile reference supplied."}))
                return 0
        elif args.reference:
            content = args.reference.read_bytes()
            if len(content) > 20_000:
                raise evidence.SnapshotError("Reference exceeds size limit.")
            reference = validate_reference(evidence.strict_json(content.decode("utf-8")))
        source = live_source() if args.check_live else target.read_bytes().decode("utf-8")
        changed = False
        if args.check or args.check_live:
            reference = read_reference(source)
        else:
            validate_layout(source)
            newline = "\r\n" if "\r\n" in source else "\n"
            block = render_reference(reference, public.marker_indent(source, source.index(START)), newline)
            updated = public.replace_marker_region(source, START, END, block)
            changed = public.atomic_write(target, updated.encode("utf-8"))
        print(json.dumps({
            "status": "ok", "changed": changed, "total_contributions": reference["total_contributions"],
            "from_bound": reference["from_bound"], "to_bound": reference["to_bound"],
            "checked_at": reference["checked_at"], "includes_private_activity": True,
            "source": reference["source"], "mode": "check" if args.check or args.check_live else "render",
        }, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"status": "error", "message": "Profile aggregate failed safely; no raw reference, response or credential details emitted."}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
