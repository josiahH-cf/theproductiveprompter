#!/usr/bin/env python3
"""Publish due Article Flow packages held in private draft releases.

The draft release is repository-owned staging. Its manifest pins the Article
Flow run, package, publication plan, repository revision, URL, and earliest
publication instant. This runner never regenerates article content and never
publishes before that instant.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request


TAG_PREFIX = "scheduled-article-"
MANIFEST_ASSET = "scheduled-release.json"
BUNDLE_ASSET = "article-flow-run.tar.gz"
LOOKAHEAD_SECONDS = 5 * 60
VERIFY_TIMEOUT_SECONDS = 25 * 60
RUN_ID_RE = re.compile(r"AF-[0-9]{8}T[0-9]{6}Z-[a-z0-9-]+-[0-9a-f]{8}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")


class ScheduledReleaseError(RuntimeError):
    pass


def command(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    if check and result.returncode != 0:
        raise ScheduledReleaseError(
            f"Command failed with exit {result.returncode}: {' '.join(argv)}"
        )
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScheduledReleaseError(f"Invalid JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ScheduledReleaseError(f"Expected a JSON object at {path}")
    return value


def parse_utc(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScheduledReleaseError(f"Invalid UTC timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise ScheduledReleaseError(f"Timestamp must identify UTC exactly: {value}")
    return parsed.astimezone(dt.timezone.utc)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_text(value: dt.datetime | None = None) -> str:
    current = value or utc_now()
    return current.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def release_view(tag: str) -> dict[str, Any]:
    result = command(
        ["gh", "release", "view", tag, "--json", "tagName,name,isDraft,assets"]
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ScheduledReleaseError(f"Could not parse draft release {tag}") from exc
    if not value.get("isDraft"):
        raise ScheduledReleaseError(f"Scheduled release {tag} must remain a draft")
    return value


def asset_names(release: dict[str, Any]) -> set[str]:
    return {
        str(item.get("name"))
        for item in release.get("assets", [])
        if isinstance(item, dict) and item.get("name")
    }


def release_tags(requested: str | None) -> list[str]:
    if requested:
        if not requested.startswith(TAG_PREFIX):
            raise ScheduledReleaseError(
                f"Requested release tag must start with {TAG_PREFIX}"
            )
        return [requested]
    result = command(
        [
            "gh",
            "release",
            "list",
            "--limit",
            "100",
            "--json",
            "tagName,isDraft",
            "--jq",
            f'.[] | select(.isDraft and (.tagName | startswith("{TAG_PREFIX}"))) | .tagName',
        ]
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def download_asset(tag: str, name: str, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    command(
        [
            "gh",
            "release",
            "download",
            tag,
            "--pattern",
            name,
            "--dir",
            str(destination),
        ]
    )
    path = destination / name
    if not path.is_file():
        raise ScheduledReleaseError(f"Draft release {tag} is missing {name}")
    return path


def validate_manifest(manifest: dict[str, Any], tag: str) -> None:
    expected_scalars = {
        "schema_version": "1.0.0",
        "status": "SCHEDULED",
        "release_tag": tag,
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "bundle_asset": BUNDLE_ASSET,
    }
    for key, expected in expected_scalars.items():
        if manifest.get(key) != expected:
            raise ScheduledReleaseError(
                f"Manifest {key} mismatch: expected {expected!r}, got {manifest.get(key)!r}"
            )
    if not RUN_ID_RE.fullmatch(str(manifest.get("run_id", ""))):
        raise ScheduledReleaseError("Manifest run_id is invalid")
    for key in (
        "package_revision",
        "package_manifest_sha256",
        "article_sha256",
        "publication_plan_sha256",
        "bundle_sha256",
    ):
        if not SHA256_RE.fullmatch(str(manifest.get(key, ""))):
            raise ScheduledReleaseError(f"Manifest {key} is not a SHA-256 digest")
    if not COMMIT_RE.fullmatch(str(manifest.get("expected_base_commit", ""))):
        raise ScheduledReleaseError("Manifest expected_base_commit is invalid")
    article_path = Path(str(manifest.get("article_relative_path", "")))
    if article_path.is_absolute() or ".." in article_path.parts:
        raise ScheduledReleaseError("Manifest article_relative_path is unsafe")
    parse_utc(str(manifest.get("not_before_utc", "")))
    if not str(manifest.get("intended_url", "")).startswith(
        "https://theproductiveprompter.com/docs/"
    ):
        raise ScheduledReleaseError("Manifest intended_url is outside the publication target")
    if manifest.get("authority", {}).get("scope") != "exact_pinned_release":
        raise ScheduledReleaseError("Manifest lacks exact scoped publication authority")


def safe_extract(bundle: Path, destination: Path, run_id: str) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(bundle, "r:gz") as archive:
        members = archive.getmembers()
        if not members:
            raise ScheduledReleaseError("Scheduled run bundle is empty")
        for member in members:
            candidate = Path(member.name)
            if (
                candidate.is_absolute()
                or ".." in candidate.parts
                or not candidate.parts
                or candidate.parts[0] != run_id
                or member.issym()
                or member.islnk()
            ):
                raise ScheduledReleaseError(
                    f"Unsafe path in scheduled run bundle: {member.name}"
                )
        archive.extractall(destination, filter="data")
    run_directory = destination / run_id
    if not (run_directory / "run.json").is_file():
        raise ScheduledReleaseError("Scheduled run bundle is missing run.json")
    return run_directory


def exact_repo_state(repository: Path, expected: str) -> None:
    command(["git", "fetch", "origin", "main"], cwd=repository)
    head = command(["git", "rev-parse", "HEAD"], cwd=repository).stdout.strip()
    remote = command(["git", "rev-parse", "origin/main"], cwd=repository).stdout.strip()
    dirty = command(["git", "status", "--porcelain=v1", "-uall"], cwd=repository).stdout
    if head != expected or remote != expected:
        raise ScheduledReleaseError(
            f"Repository revision changed: expected {expected}, local {head}, origin/main {remote}"
        )
    if dirty.strip():
        raise ScheduledReleaseError(f"Publication checkout is not clean:\n{dirty.rstrip()}")


def article_flow_environment(repository: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["ARTICLE_FLOW_REPO_ROOT"] = str(repository)
    return environment


def article_flow_command(
    executable: Path,
    args: list[str],
    *,
    repository: Path,
    environment: dict[str, str],
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return command(
        [str(executable), *args],
        cwd=repository,
        env=environment,
        check=check,
    )


def parse_command_json(result: subprocess.CompletedProcess[str], label: str) -> dict[str, Any]:
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ScheduledReleaseError(f"{label} did not return JSON") from exc
    if not isinstance(value, dict):
        raise ScheduledReleaseError(f"{label} did not return an object")
    return value


def validate_hidden_state(manifest: dict[str, Any]) -> dict[str, Any]:
    slug = str(manifest["slug"])
    urls = {
        "article": str(manifest["intended_url"]),
        "homepage": "https://theproductiveprompter.com/",
        "blog": "https://theproductiveprompter.com/docs/blog.html",
        "feed": "https://theproductiveprompter.com/feed.xml",
        "sitemap": "https://theproductiveprompter.com/sitemap.xml",
    }
    evidence: dict[str, Any] = {"checked_at": utc_text(), "surfaces": {}}
    for name, url in urls.items():
        request = urllib.request.Request(url, headers={"User-Agent": "scheduled-article-validator/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = int(response.status)
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            body = exc.read().decode("utf-8", errors="replace")
        count = body.count(slug)
        evidence["surfaces"][name] = {"url": url, "status": status, "slug_count": count}
    article = evidence["surfaces"]["article"]
    discovery = [
        evidence["surfaces"][name]
        for name in ("homepage", "blog", "feed", "sitemap")
    ]
    evidence["ok"] = (
        article["status"] == 404
        and all(item["status"] == 200 and item["slug_count"] == 0 for item in discovery)
    )
    return evidence


def upload_evidence(tag: str, paths: list[Path]) -> None:
    command(["gh", "release", "upload", tag, *[str(path) for path in paths]])


def request_and_wait_for_pages_build(commit_sha: str) -> dict[str, Any]:
    repository_name = str(os.environ["GITHUB_REPOSITORY"])
    command(["gh", "api", "--method", "POST", f"repos/{repository_name}/pages/builds"])
    deadline = time.monotonic() + VERIFY_TIMEOUT_SECONDS
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        result = command(
            ["gh", "api", f"repos/{repository_name}/pages/builds/latest"],
            check=False,
        )
        if result.returncode == 0:
            try:
                candidate = json.loads(result.stdout)
            except json.JSONDecodeError:
                candidate = {}
            if isinstance(candidate, dict):
                latest = candidate
                if candidate.get("commit") == commit_sha and candidate.get("status") == "built":
                    return candidate
                if candidate.get("commit") == commit_sha and candidate.get("status") == "errored":
                    raise ScheduledReleaseError(
                        f"GitHub Pages build failed: {candidate.get('error')}"
                    )
        time.sleep(15)
    raise ScheduledReleaseError(
        f"GitHub Pages did not finish the publication commit within 25 minutes: {latest}"
    )


def write_summary(lines: list[str]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def process_release(
    tag: str,
    manifest: dict[str, Any],
    bundle: Path,
    *,
    validate_only: bool,
) -> None:
    repository = Path(os.environ.get("GITHUB_WORKSPACE", Path.cwd())).resolve()
    exact_repo_state(repository, str(manifest["expected_base_commit"]))
    if sha256(bundle) != manifest["bundle_sha256"]:
        raise ScheduledReleaseError("Scheduled run bundle hash does not match the manifest")

    runtime_runs = Path.home() / ".local" / "share" / "article-flow" / "runs"
    run_directory = safe_extract(bundle, runtime_runs, str(manifest["run_id"]))
    package_path = run_directory / "package" / "package.json"
    plan_path = run_directory / "publication" / "plan.json"
    article_path = run_directory / str(manifest["article_relative_path"])
    package = read_json(package_path)
    plan = read_json(plan_path)
    if package.get("package_revision") != manifest["package_revision"]:
        raise ScheduledReleaseError("Package revision does not match the scheduled manifest")
    pinned_hashes = {
        package_path: manifest["package_manifest_sha256"],
        article_path: manifest["article_sha256"],
        plan_path: manifest["publication_plan_sha256"],
    }
    for path, expected in pinned_hashes.items():
        if not path.is_file() or sha256(path) != expected:
            raise ScheduledReleaseError(f"Pinned file changed: {path.relative_to(run_directory)}")
    if plan.get("base_commit") != manifest["expected_base_commit"]:
        raise ScheduledReleaseError("Publication plan base does not match the scheduled repository revision")

    environment = article_flow_environment(repository)
    controller_source = repository / "Article-Spec-Pack-v1" / "scripts" / "article_flow.py"
    command(
        ["python3", str(controller_source), "install", "--hosts", "wsl", "--json"],
        cwd=repository,
        env=environment,
    )
    executable = Path.home() / ".local" / "bin" / "article-flow"
    article_flow_command(
        executable,
        ["conformance", "--json"],
        repository=repository,
        environment=environment,
    )
    doctor = parse_command_json(
        article_flow_command(
            executable,
            ["doctor", "--scope", "all", "--json"],
            repository=repository,
            environment=environment,
        ),
        "Article Flow doctor",
    )
    if not doctor.get("ok"):
        raise ScheduledReleaseError("Article Flow full readiness did not pass")
    status = parse_command_json(
        article_flow_command(
            executable,
            ["status", str(manifest["run_id"]), "--json"],
            repository=repository,
            environment=environment,
        ),
        "Article Flow status",
    )
    if status.get("state") != "PUBLISH_APPROVAL":
        raise ScheduledReleaseError(
            f"Scheduled run is in {status.get('state')}, not PUBLISH_APPROVAL"
        )
    fresh_plan = parse_command_json(
        article_flow_command(
            executable,
            ["publish", "--plan", str(manifest["run_id"]), "--json"],
            repository=repository,
            environment=environment,
        ),
        "Article Flow publication plan",
    )
    if (
        fresh_plan.get("base_commit") != manifest["expected_base_commit"]
        or fresh_plan.get("package_revision") != manifest["package_revision"]
        or sha256(plan_path) != manifest["publication_plan_sha256"]
    ):
        raise ScheduledReleaseError("Fresh Article Flow plan differs from the pinned plan")

    if validate_only:
        hidden = validate_hidden_state(manifest)
        if not hidden["ok"]:
            raise ScheduledReleaseError("Article is not fully hidden during schedule validation")
        evidence = {
            "status": "VALIDATED",
            "release_tag": tag,
            "run_id": manifest["run_id"],
            "package_revision": manifest["package_revision"],
            "expected_base_commit": manifest["expected_base_commit"],
            "not_before_utc": manifest["not_before_utc"],
            "doctor_ok": True,
            "plan_sha256": sha256(plan_path),
            "hidden_state": hidden,
            "validated_at": utc_text(),
        }
        path = bundle.parent / f"validation-{utc_now().strftime('%Y%m%dT%H%M%SZ')}.json"
        path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        upload_evidence(tag, [path])
        write_summary(
            [
                "## Scheduled article validation: PASS",
                "",
                f"- Run: `{manifest['run_id']}`",
                f"- Earliest publication: `{manifest['not_before_utc']}`",
                f"- Package: `{manifest['package_revision']}`",
                "- Current article response: `404`; discovery slug count: `0` on all four surfaces",
            ]
        )
        return

    if utc_now() < parse_utc(str(manifest["not_before_utc"])):
        raise ScheduledReleaseError("Early-publication guard stopped the release")
    gate = parse_command_json(
        article_flow_command(
            executable,
            [
                "gate",
                str(manifest["run_id"]),
                "G-PUBLISH-APPROVAL",
                "--outcome",
                "PASS",
                "--json",
            ],
            repository=repository,
            environment=environment,
        ),
        "Article Flow publication approval",
    )
    approval_id = gate.get("approval_id")
    if not approval_id:
        raise ScheduledReleaseError("Controller did not return a scoped approval ID")
    publication = parse_command_json(
        article_flow_command(
            executable,
            [
                "publish",
                "--execute",
                str(manifest["run_id"]),
                "--approval",
                str(approval_id),
                "--commit",
                "--push",
                "--json",
            ],
            repository=repository,
            environment=environment,
        ),
        "Article Flow publication execution",
    )
    commit_sha = publication.get("commit")
    if not publication.get("ok") or not COMMIT_RE.fullmatch(str(commit_sha or "")):
        raise ScheduledReleaseError("Controller publication did not return a pushed commit")

    pages_build = request_and_wait_for_pages_build(str(commit_sha))
    deadline = time.monotonic() + VERIFY_TIMEOUT_SECONDS
    verification: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        result = article_flow_command(
            executable,
            ["verify-live", str(manifest["run_id"]), "--json"],
            repository=repository,
            environment=environment,
            check=False,
        )
        try:
            candidate = json.loads(result.stdout)
        except json.JSONDecodeError:
            candidate = {}
        if result.returncode == 0 and candidate.get("ok"):
            verification = candidate
            break
        time.sleep(30)
    if not verification:
        raise ScheduledReleaseError(
            "Publication was pushed, but exact live verification did not pass within 25 minutes"
        )

    publication_receipt = run_directory / "receipts" / "publication.json"
    live_receipt = run_directory / "receipts" / "live-verification.json"
    completed = {
        "status": "VERIFIED",
        "release_tag": tag,
        "run_id": manifest["run_id"],
        "package_revision": manifest["package_revision"],
        "scheduled_not_before_utc": manifest["not_before_utc"],
        "commit": commit_sha,
        "pages_build_url": pages_build.get("url"),
        "pages_build_status": pages_build.get("status"),
        "url": verification.get("url"),
        "verified_at": utc_text(),
    }
    completed_path = bundle.parent / "completed.json"
    completed_path.write_text(
        json.dumps(completed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    upload_evidence(tag, [completed_path, publication_receipt, live_receipt])
    write_summary(
        [
            "## Scheduled article publication: PASS",
            "",
            f"- URL: {verification.get('url')}",
            f"- Commit: `{commit_sha}`",
            f"- Package: `{manifest['package_revision']}`",
            f"- Earliest permitted publication: `{manifest['not_before_utc']}`",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-tag")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    repository_name = os.environ.get("GITHUB_REPOSITORY")
    if not repository_name:
        raise ScheduledReleaseError("GITHUB_REPOSITORY is required")
    tags = release_tags(args.release_tag)
    if not tags:
        print("No scheduled Article Flow draft releases are present.")
        return 0

    candidates: list[tuple[dt.datetime, str, dict[str, Any], Path, tempfile.TemporaryDirectory[str]]] = []
    now = utc_now()
    for tag in tags:
        release = release_view(tag)
        names = asset_names(release)
        if "completed.json" in names or any(name.startswith("blocked-") for name in names):
            print(f"Skipping terminal scheduled release {tag}.")
            continue
        if MANIFEST_ASSET not in names or BUNDLE_ASSET not in names:
            raise ScheduledReleaseError(f"Draft release {tag} lacks its manifest or run bundle")
        temporary = tempfile.TemporaryDirectory(prefix="scheduled-article-")
        work = Path(temporary.name)
        manifest_path = download_asset(tag, MANIFEST_ASSET, work)
        manifest = read_json(manifest_path)
        validate_manifest(manifest, tag)
        due = parse_utc(str(manifest["not_before_utc"]))
        if not args.validate_only and due > now + dt.timedelta(seconds=LOOKAHEAD_SECONDS):
            print(f"Scheduled release {tag} is not due within five minutes ({utc_text(due)}).")
            temporary.cleanup()
            continue
        bundle = download_asset(tag, BUNDLE_ASSET, work)
        candidates.append((due, tag, manifest, bundle, temporary))

    if not candidates:
        print("No scheduled Article Flow release is due.")
        return 0
    candidates.sort(key=lambda item: item[0])

    for due, tag, manifest, bundle, temporary in candidates:
        try:
            if not args.validate_only:
                delay = (due - utc_now()).total_seconds()
                if delay > 0:
                    print(f"Waiting {int(delay)} seconds for the exact publication boundary {utc_text(due)}.")
                    time.sleep(delay)
            process_release(tag, manifest, bundle, validate_only=args.validate_only)
        except Exception as exc:
            blocked_path = Path(temporary.name) / f"blocked-{utc_now().strftime('%Y%m%dT%H%M%SZ')}.json"
            blocked_path.write_text(
                json.dumps(
                    {
                        "status": "BLOCKED",
                        "release_tag": tag,
                        "run_id": manifest.get("run_id"),
                        "not_before_utc": manifest.get("not_before_utc"),
                        "error": str(exc),
                        "recorded_at": utc_text(),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            try:
                upload_evidence(tag, [blocked_path])
            except Exception as upload_error:
                print(f"Could not upload blocker evidence: {upload_error}", file=sys.stderr)
            raise
        finally:
            temporary.cleanup()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScheduledReleaseError as exc:
        print(f"Scheduled release blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)
