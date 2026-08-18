#!/usr/bin/env python3
"""Provider-neutral controller for The Productive Prompter article workflow."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import functools
import hashlib
import html
import io
import json
import os
import platform
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence


CONTROLLER_VERSION = "2.0.8"
SCRIPT_PATH = Path(__file__).resolve()
SPEC_ROOT = SCRIPT_PATH.parent.parent
REPO_ROOT = SPEC_ROOT.parent
MANIFEST_PATH = SPEC_ROOT / "manifest.json"
WORKFLOW_PATH = SPEC_ROOT / "workflow" / "workflow.json"
POLICY_PATH = SPEC_ROOT / "workflow" / "house-policy.json"
PROTECTED_PATHS_PATH = SPEC_ROOT / "workflow" / "protected-paths.json"
SEED_QUESTION = (
    "In one paragraph or less, what feels like it could be a good article? "
    "Write it naturally; you do not need to structure or polish it."
)


def bootstrap_payload() -> dict[str, Any]:
    """Return the complete host-neutral contract for a fresh local session."""
    return {
        "ok": True,
        "interface": "local-global-command",
        "command": "article-flow",
        "controller_version": CONTROLLER_VERSION,
        "workflow_version": workflow()["workflow_version"],
        "action": "request_seed",
        "question": SEED_QUESTION,
        "start_command": ["article-flow", "start", "--seed", "<verbatim operator seed>", "--json"],
        "protocol": [
            "Preserve the operator's seed verbatim when replacing the placeholder in start_command.",
            "Run only exact command arrays returned by the controller in next_command, command, submission_command, or approval_command fields.",
            "For perform_task, read only task_packet, create only expected_output, then run submission_command.",
            "For human_decision, show the controller's question and wait; never run approval_command without the operator's confirmed answer.",
            "Stop on complete, terminal, or an unresolved capability or decision.",
        ],
        "capability_requirement": "This interface requires local command execution. A cloud-only chat without access to this machine cannot run it.",
    }
REVIEW_STATES = {"INTENT_REVIEW", "ARTICLE_RECIPE", "VOICE_PROBE", "EDITORIAL_QA"}
DETERMINISTIC_STATES = {"PACKAGE", "PUBLISH_APPROVAL", "PUBLISH", "LIVE_VERIFICATION", "COMPLETE"}
MODEL_STATES = {
    "RESEARCH_PLAN",
    "RESEARCH",
    "INTENT_REVIEW",
    "ARTICLE_RECIPE",
    "BRIEF",
    "VOICE_PROBE",
    "DRAFT",
    "CLAIM_VERIFICATION",
    "EDIT",
    "POST_EDIT_CLAIM_VERIFICATION",
    "EDITORIAL_QA",
}
STAGE_CAPABILITIES = {
    "RESEARCH_PLAN": {"structured-output"},
    "RESEARCH": {"structured-output", "research"},
    "INTENT_REVIEW": {"structured-output"},
    "ARTICLE_RECIPE": {"structured-output"},
    "BRIEF": {"structured-output"},
    "VOICE_PROBE": {"structured-output"},
    "DRAFT": {"long-form"},
    "CLAIM_VERIFICATION": {"structured-output", "research"},
    "EDIT": {"long-form"},
    "POST_EDIT_CLAIM_VERIFICATION": {"structured-output", "research"},
    "EDITORIAL_QA": {"structured-output"},
}
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_WAITING = 10
EXIT_INTEGRITY = 20
EXIT_APPROVAL = 30


class FlowError(RuntimeError):
    """Expected workflow failure with a stable exit code."""

    def __init__(self, message: str, code: int = EXIT_FAILED, details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FlowError(f"Cannot read valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FlowError(f"Expected a JSON object: {path}")
    return value


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    temp_path.replace(path)


def write_if_changed(path: Path, data: bytes, *, mode: int | None = None) -> bool:
    if path.is_file() and path.read_bytes() == data:
        if mode is not None:
            path.chmod(mode)
        return False
    atomic_write(path, data)
    if mode is not None:
        path.chmod(mode)
    return True


def write_json(path: Path, value: Any) -> None:
    atomic_write(path, (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def safe_relative(value: str) -> Path:
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise FlowError(f"Unsafe repository-relative path: {value}", EXIT_INTEGRITY)
    return path


def git(args: Sequence[str], *, cwd: Path | None = None, check: bool = True, binary: bool = False) -> bytes | str:
    cwd = cwd or REPO_ROOT
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=check,
            capture_output=True,
            text=not binary,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        if check:
            stderr = getattr(exc, "stderr", "")
            raise FlowError(f"Git command failed: {' '.join(args)}: {stderr}") from exc
        return b"" if binary else ""
    return result.stdout


def workflow() -> dict[str, Any]:
    return load_json(WORKFLOW_PATH)


def policy() -> dict[str, Any]:
    return load_json(POLICY_PATH)


def state_definition(state_id: str) -> dict[str, Any]:
    for item in workflow()["states"]:
        if item["id"] == state_id:
            return item
    raise FlowError(f"Unknown workflow state: {state_id}")


def spec_repo_path(path: str) -> str:
    return (SPEC_ROOT.relative_to(REPO_ROOT) / safe_relative(path)).as_posix()


def source_bytes(path: str, source: str, scope: str = "spec") -> bytes:
    if scope not in {"spec", "repository"}:
        raise FlowError(f"Unknown protected path scope: {scope}", EXIT_INTEGRITY)
    rel = spec_repo_path(path) if scope == "spec" else safe_relative(path).as_posix()
    if source == "worktree":
        target_root = SPEC_ROOT if scope == "spec" else (publication_repo_root() or REPO_ROOT)
        target = target_root / safe_relative(path)
        if not target.is_file():
            raise FlowError(f"Protected file is missing: {path}", EXIT_INTEGRITY)
        return target.read_bytes()
    spec = f":{rel}" if source == "index" else f"HEAD:{rel}"
    try:
        return git(["show", spec], binary=True)  # type: ignore[return-value]
    except FlowError as exc:
        raise FlowError(f"Protected file is missing from {source}: {path}", EXIT_INTEGRITY) from exc


def source_json(path: str, source: str, scope: str = "spec") -> dict[str, Any]:
    try:
        value = json.loads(source_bytes(path, source, scope).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlowError(f"Invalid JSON in {source}: {path}: {exc}", EXIT_INTEGRITY) from exc
    if not isinstance(value, dict):
        raise FlowError(f"Expected JSON object in {source}: {path}", EXIT_INTEGRITY)
    return value


def protected_config(source: str = "worktree") -> dict[str, Any]:
    if source == "worktree":
        return load_json(PROTECTED_PATHS_PATH)
    return source_json("workflow/protected-paths.json", source)


def protected_entries(source: str = "worktree") -> list[dict[str, str]]:
    entries = protected_config(source).get("entries", [])
    if not isinstance(entries, list):
        raise FlowError("protected-paths.json entries must be an array", EXIT_INTEGRITY)
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in entries:
        if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
            raise FlowError("Invalid protected path entry", EXIT_INTEGRITY)
        path = safe_relative(raw["path"]).as_posix()
        scope = str(raw.get("scope", "spec"))
        if scope not in {"spec", "repository"}:
            raise FlowError(f"Invalid protected path scope: {scope}", EXIT_INTEGRITY)
        key = f"{scope}:{path}"
        if key in seen:
            raise FlowError(f"Duplicate protected path: {key}", EXIT_INTEGRITY)
        seen.add(key)
        result.append({
            "path": path,
            "scope": scope,
            "role": str(raw.get("role", "runtime")),
            "rule_set": str(raw.get("rule_set", "unspecified")),
        })
    return sorted(result, key=lambda item: (item["scope"], item["path"]))


def watched_files(source: str = "worktree") -> set[str]:
    config = protected_config(source)
    roots = [safe_relative(str(item)).as_posix() for item in config.get("watched_roots", [])]
    ignored_names = {"__pycache__", ".DS_Store", ".pytest_cache"}
    paths: set[str] = set()
    if source == "worktree":
        for root in roots:
            root_path = SPEC_ROOT / root
            if not root_path.exists():
                continue
            for path in root_path.rglob("*"):
                if path.is_file() and not any(part in ignored_names for part in path.parts):
                    paths.add(path.relative_to(SPEC_ROOT).as_posix())
        return paths
    tree = "--cached" if source == "index" else "HEAD"
    if source == "index":
        output = git(["ls-files", "--cached", "--", SPEC_ROOT.relative_to(REPO_ROOT).as_posix()])
    else:
        output = git(["ls-tree", "-r", "--name-only", tree, "--", SPEC_ROOT.relative_to(REPO_ROOT).as_posix()])
    prefix = SPEC_ROOT.relative_to(REPO_ROOT).as_posix() + "/"
    for line in str(output).splitlines():
        if not line.startswith(prefix):
            continue
        rel = line[len(prefix):]
        if any(rel == root or rel.startswith(root + "/") for root in roots):
            if not any(part in ignored_names for part in Path(rel).parts):
                paths.add(rel)
    return paths


def manifest_payload_from_index() -> dict[str, Any]:
    config = protected_config("index")
    entries = protected_entries("index")
    expected = {item["path"] for item in entries if item["scope"] == "spec"}
    unexpected = sorted(watched_files("index") - expected)
    if unexpected:
        raise FlowError(
            "Unregistered active controls are staged: " + ", ".join(unexpected),
            EXIT_INTEGRITY,
        )
    files = []
    for entry in entries:
        data = source_bytes(entry["path"], "index", entry["scope"])
        files.append({**entry, "sha256": sha256_bytes(data), "byte_size": len(data)})
    return {
        "manifest_schema_version": "2.0.0",
        "workflow_version": str(config["workflow_version"]),
        "hash_algorithm": "sha256",
        "generator_name_and_version": f"article-flow {CONTROLLER_VERSION}",
        "generated_at": utc_now(),
        "generated_from": "index",
        "files": files,
    }


def read_manifest(source: str) -> dict[str, Any]:
    if source == "worktree":
        return load_json(MANIFEST_PATH)
    return source_json("manifest.json", source)


def check_manifest(source: str, *, allow_unavailable_repository: bool = False) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    try:
        manifest = read_manifest(source)
        entries = protected_entries(source)
    except FlowError as exc:
        return {"ok": False, "source": source, "failures": [{"kind": "manifest", "message": str(exc)}]}
    version = manifest.get("manifest_schema_version")
    for error in validate_instance_schema(manifest, "manifest.schema.json"):
        failures.append({"kind": "manifest_schema", "message": error})
    if version != "2.0.0":
        failures.append({"kind": "schema", "expected": "2.0.0", "actual": version})
    if manifest.get("hash_algorithm") != "sha256":
        failures.append({"kind": "hash_algorithm", "expected": "sha256", "actual": manifest.get("hash_algorithm")})
    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, list):
        manifest_files = []
        failures.append({"kind": "schema", "message": "files must be an array"})
    manifest_map: dict[tuple[str, str], dict[str, Any]] = {}
    for item in manifest_files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        scope = str(item.get("scope", "spec"))
        try:
            path = safe_relative(str(item["path"])).as_posix()
        except FlowError as exc:
            failures.append({"kind": "unsafe_manifest_path", "path": item.get("path"), "message": str(exc)})
            continue
        key = (scope, path)
        if key in manifest_map:
            failures.append({"kind": "duplicate_manifest_entry", "scope": scope, "path": path})
        manifest_map[key] = item
    expected_map = {(item["scope"], item["path"]): item for item in entries}
    config_version = protected_config(source).get("workflow_version")
    if manifest.get("workflow_version") != config_version:
        failures.append({"kind": "workflow_version", "expected": config_version, "actual": manifest.get("workflow_version")})
    watched = watched_files(source)
    registered_spec_paths = {path for (scope, path) in expected_map if scope == "spec"}
    for path in sorted(watched - registered_spec_paths):
        failures.append({"kind": "unexpected_protected_file", "path": path, "safe_to_auto_repair": False})
    for scope, path in sorted(set(expected_map) - set(manifest_map)):
        failures.append({"kind": "missing_manifest_entry", "scope": scope, "path": path, "safe_to_auto_repair": False})
    for scope, path in sorted(set(manifest_map) - set(expected_map)):
        failures.append({"kind": "unexpected_manifest_entry", "scope": scope, "path": path, "safe_to_auto_repair": False})
    for (scope, path), expected_meta in expected_map.items():
        recorded = manifest_map.get((scope, path))
        if not recorded:
            continue
        if source == "worktree" and scope == "repository" and publication_repo_root() is None and allow_unavailable_repository:
            deferred.append({"scope": scope, "path": path, "reason": "publication repository unavailable; check required before package or release"})
            continue
        try:
            data = source_bytes(path, source, scope)
        except FlowError:
            failures.append({"kind": "missing_file", "scope": scope, "path": path, "safe_to_auto_repair": False})
            continue
        actual_hash = sha256_bytes(data)
        if recorded.get("sha256") != actual_hash or recorded.get("byte_size") != len(data):
            failures.append({
                "kind": "hash_mismatch",
                "scope": scope,
                "path": path,
                "expected_hash": recorded.get("sha256"),
                "actual_hash": actual_hash,
                "expected_byte_size": recorded.get("byte_size"),
                "actual_byte_size": len(data),
                "manifest_version": version,
                "repair_command": "Review and stage the intended change, then run article-flow manifest build --from-index.",
                "safe_to_auto_repair": False,
            })
        if recorded.get("role") != expected_meta["role"] or recorded.get("rule_set") != expected_meta["rule_set"]:
            failures.append({"kind": "metadata_mismatch", "scope": scope, "path": path, "safe_to_auto_repair": False})
    return {
        "ok": not failures,
        "source": source,
        "manifest_schema_version": version,
        "workflow_version": manifest.get("workflow_version"),
        "protected_file_count": len(expected_map),
        "failures": failures,
        "deferred": deferred,
    }


def runtime_home() -> Path:
    configured = os.environ.get("ARTICLE_FLOW_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        return (base / "ArticleFlow").resolve()
    return (Path.home() / ".local" / "share" / "article-flow").resolve()


def installation_record() -> dict[str, Any]:
    path = runtime_home() / "current.json"
    return load_json(path) if path.is_file() else {}


def release_source_commit() -> str:
    if (REPO_ROOT / ".git").exists():
        return str(git(["rev-parse", "HEAD"], cwd=REPO_ROOT)).strip()
    metadata_path = SPEC_ROOT / ".article-flow-release.json"
    if metadata_path.is_file():
        metadata = load_json(metadata_path)
        if metadata.get("source_commit"):
            return str(metadata["source_commit"])
    installed = installation_record()
    if installed.get("source_commit"):
        return str(installed["source_commit"])
    repository = publication_repo_root()
    if repository and (repository / ".git").exists():
        return str(git(["rev-parse", "HEAD"], cwd=repository)).strip()
    raise FlowError("Cannot determine the source commit for this controller", EXIT_INTEGRITY)


def publication_repo_root(*, required: bool = False) -> Path | None:
    override = os.environ.get("ARTICLE_FLOW_REPO_ROOT")
    candidates = [Path(override).expanduser() if override else None]
    configured = installation_record().get("publication_repo_root")
    if configured:
        candidates.append(Path(str(configured)))
    candidates.append(REPO_ROOT)
    for candidate in candidates:
        if candidate and candidate.is_dir() and (candidate / "index.html").is_file() and (candidate / "docs").is_dir():
            return candidate.resolve()
    if required:
        raise FlowError("The publication repository is unavailable; set ARTICLE_FLOW_REPO_ROOT to its current checkout", EXIT_INTEGRITY)
    return None


def runs_root() -> Path:
    return runtime_home() / "runs"


def slugify(value: str, limit: int = 48) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return (value[:limit].rstrip("-") or "article")


def run_dir(run_id: str) -> Path:
    if not re.fullmatch(r"AF-[0-9]{8}T[0-9]{6}Z-[a-z0-9-]+-[0-9a-f]{8}", run_id):
        raise FlowError(f"Invalid run ID: {run_id}", EXIT_USAGE)
    return runs_root() / run_id


def append_event(directory: Path, run: dict[str, Any], event_type: str, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
    log_path = directory / run["event_log"]
    sequence = 1
    previous_hash: str | None = None
    if log_path.exists():
        lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            previous = json.loads(lines[-1])
            sequence = int(previous["sequence"]) + 1
            previous_hash = str(previous["event_hash"])
    event = {
        "event_schema_version": "1.0.0",
        "event_id": f"EV-{sequence:06d}-{secrets.token_hex(4)}",
        "run_id": run["run_id"],
        "sequence": sequence,
        "timestamp": utc_now(),
        "type": event_type,
        "state": run["state"],
        "actor": actor,
        "payload": payload,
        "previous_event_hash": previous_hash,
    }
    event["event_hash"] = sha256_bytes((previous_hash or "").encode("ascii") + canonical_json(event))
    errors = validate_instance_schema(event, "event.schema.json")
    if errors:
        raise FlowError("Controller generated an invalid event", EXIT_INTEGRITY, errors)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return event


def verify_event_log(directory: Path, run: dict[str, Any]) -> tuple[bool, str | None, str]:
    log_path = directory / run["event_log"]
    if not log_path.is_file():
        return False, "event log missing", "NEW"
    previous_hash: str | None = None
    derived_state = "NEW"
    for expected_sequence, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            return False, f"invalid event JSON: {exc}", derived_state
        schema_errors = validate_instance_schema(event, "event.schema.json")
        if schema_errors:
            return False, f"event schema mismatch at sequence {expected_sequence}: {schema_errors[0]}", derived_state
        recorded_hash = event.pop("event_hash", None)
        if event.get("sequence") != expected_sequence or event.get("previous_event_hash") != previous_hash:
            return False, f"event chain mismatch at sequence {expected_sequence}", derived_state
        actual_hash = sha256_bytes((previous_hash or "").encode("ascii") + canonical_json(event))
        if recorded_hash != actual_hash:
            return False, f"event hash mismatch at sequence {expected_sequence}", derived_state
        previous_hash = str(recorded_hash)
        if event.get("type") == "STATE_TRANSITION":
            derived_state = str(event.get("payload", {}).get("to", derived_state))
    return True, None, derived_state


def load_run(run_id: str) -> tuple[Path, dict[str, Any]]:
    directory = run_dir(run_id)
    path = directory / "run.json"
    if not path.is_file():
        raise FlowError(f"Run not found: {run_id}")
    run = load_json(path)
    errors = validate_instance_schema(run, "run.schema.json")
    if errors:
        raise FlowError(f"Run schema failed: {errors[0]}", EXIT_INTEGRITY, errors)
    ok, error, derived_state = verify_event_log(directory, run)
    if not ok:
        raise FlowError(f"Run event log failed integrity: {error}", EXIT_INTEGRITY)
    if run.get("state") != derived_state:
        raise FlowError(f"run.json state {run.get('state')} disagrees with event log state {derived_state}", EXIT_INTEGRITY)
    return directory, run


def save_run(directory: Path, run: dict[str, Any]) -> None:
    run["updated_at"] = utc_now()
    errors = validate_instance_schema(run, "run.schema.json")
    if errors:
        raise FlowError("Controller generated an invalid run", EXIT_INTEGRITY, errors)
    write_json(directory / "run.json", run)


@contextlib.contextmanager
def run_lock(directory: Path, run: dict[str, Any]) -> Iterator[None]:
    lock_path = directory / ".lock"
    recovered = None
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        try:
            lock = load_json(lock_path)
        except FlowError:
            lock = {}
        pid = int(lock.get("pid", -1))
        created = lock.get("created_at")
        alive = False
        if pid > 0:
            try:
                os.kill(pid, 0)
                alive = True
            except (OSError, ProcessLookupError):
                alive = False
        old = bool(created and (dt.datetime.now(dt.timezone.utc) - parse_time(str(created))).total_seconds() > 3600)
        if alive and not old:
            raise FlowError(f"Run is already locked: {run['run_id']}") from exc
        recovered = directory / f".lock.recovered-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        lock_path.replace(recovered)
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        append_event(directory, run, "LOCK_RECOVERED", "controller", {"stale_lock": recovered.name, "prior": lock})
    try:
        os.write(descriptor, canonical_json({"pid": os.getpid(), "created_at": utc_now()}))
        os.close(descriptor)
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def transition(directory: Path, run: dict[str, Any], new_state: str, actor: str, reason: str) -> None:
    old_state = run["state"]
    append_event(directory, run, "STATE_TRANSITION", actor, {"from": old_state, "to": new_state, "reason": reason})
    run["state"] = new_state
    run["status"] = "COMPLETE" if new_state == "COMPLETE" else "TERMINAL" if new_state == "TERMINAL" else "ACTIVE"
    save_run(directory, run)


def record_artifact(directory: Path, run: dict[str, Any], path: Path, artifact_type: str, producer: dict[str, Any], visibility: str = "private", inputs: Iterable[str] = ()) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(directory.resolve()).as_posix()
    except ValueError as exc:
        raise FlowError(f"Artifact must live inside its run: {path}") from exc
    data = resolved.read_bytes()
    artifact = {
        "artifact_schema_version": "1.0.0",
        "artifact_id": f"AR-{artifact_type}-{secrets.token_hex(4)}",
        "type": artifact_type,
        "path": relative,
        "sha256": sha256_bytes(data),
        "byte_size": len(data),
        "producer": producer,
        "inputs": list(inputs),
        "derived_from": list(inputs),
        "visibility": visibility,
        "created_at": utc_now(),
    }
    errors = validate_instance_schema(artifact, "artifact.schema.json")
    if errors:
        raise FlowError("Controller generated an invalid artifact record", EXIT_INTEGRITY, errors)
    run["artifact_index"] = [item for item in run["artifact_index"] if item.get("type") != artifact_type]
    run["artifact_index"].append(artifact)
    append_event(directory, run, "ARTIFACT_RECORDED", producer.get("actor", "code"), {"artifact": artifact})
    save_run(directory, run)
    return artifact


def artifact(run: dict[str, Any], artifact_type: str) -> dict[str, Any] | None:
    for item in reversed(run.get("artifact_index", [])):
        if item.get("type") == artifact_type:
            return item
    return None


def artifact_path(directory: Path, run: dict[str, Any], artifact_type: str) -> Path | None:
    item = artifact(run, artifact_type)
    return directory / item["path"] if item else None


@functools.lru_cache(maxsize=8)
def schema_bundle(root_value: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    root = Path(root_value)
    schemas_by_name: dict[str, dict[str, Any]] = {}
    store: dict[str, Any] = {}
    for path in (root / "schemas").glob("*.json"):
        candidate = load_json(path)
        schemas_by_name[path.name] = candidate
        store[path.as_uri()] = candidate
        store[(root / "schemas").as_uri() + "/" + path.name] = candidate
        if candidate.get("$id"):
            store[str(candidate["$id"])] = candidate
    return schemas_by_name, store


def json_type_matches(value: Any, expected: str) -> bool:
    return {
        "null": value is None,
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "string": isinstance(value, str),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
    }.get(expected, False)


def validate_schema_value(value: Any, schema: dict[str, Any], schemas: dict[str, dict[str, Any]], path: str = "$") -> list[str]:
    if "$ref" in schema:
        reference = str(schema["$ref"]).rsplit("/", 1)[-1]
        target = schemas.get(reference)
        if target is None:
            return [f"{path}: unresolved schema reference {schema['$ref']}"]
        return validate_schema_value(value, target, schemas, path)
    if "oneOf" in schema:
        results = [validate_schema_value(value, candidate, schemas, path) for candidate in schema["oneOf"]]
        passing = sum(not errors for errors in results)
        if passing != 1:
            return [f"{path}: expected exactly one oneOf branch to match; matched {passing}"]
    if "const" in schema and canonical_json(value) != canonical_json(schema["const"]):
        return [f"{path}: value does not equal required constant {schema['const']!r}"]
    if "enum" in schema and not any(canonical_json(value) == canonical_json(candidate) for candidate in schema["enum"]):
        return [f"{path}: value {value!r} is not in the allowed enum"]

    declared_type = schema.get("type")
    expected_types = [declared_type] if isinstance(declared_type, str) else list(declared_type or [])
    if expected_types and not any(json_type_matches(value, item) for item in expected_types):
        return [f"{path}: expected type {' | '.join(expected_types)}, got {type(value).__name__}"]

    errors: list[str] = []
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            errors.append(f"{path}: string is shorter than minLength {schema['minLength']}")
        if schema.get("pattern") and re.search(str(schema["pattern"]), value) is None:
            errors.append(f"{path}: string does not match pattern {schema['pattern']}")
        if schema.get("format") == "date-time":
            try:
                parse_time(value)
            except (TypeError, ValueError):
                errors.append(f"{path}: value is not a valid date-time")
        elif schema.get("format") == "date":
            try:
                dt.date.fromisoformat(value)
            except ValueError:
                errors.append(f"{path}: value is not a valid date")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: value is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: value is above maximum {schema['maximum']}")
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            errors.append(f"{path}: array has fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            errors.append(f"{path}: array has more than {schema['maxItems']} items")
        if schema.get("uniqueItems"):
            encoded = [canonical_json(item) for item in value]
            if len(encoded) != len(set(encoded)):
                errors.append(f"{path}: array items are not unique")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                errors.extend(validate_schema_value(item, schema["items"], schemas, f"{path}[{index}]"))
    if isinstance(value, dict):
        required = schema.get("required", [])
        for name in required:
            if name not in value:
                errors.append(f"{path}: required property {name!r} is missing")
        properties = schema.get("properties", {})
        for name, item in value.items():
            if name in properties:
                errors.extend(validate_schema_value(item, properties[name], schemas, f"{path}.{name}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: additional property {name!r} is not allowed")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(validate_schema_value(item, schema["additionalProperties"], schemas, f"{path}.{name}"))
    return errors


def schema_definition_errors(schema: Any, schemas: dict[str, dict[str, Any]], path: str = "$") -> list[str]:
    if not isinstance(schema, dict):
        return [f"{path}: schema must be an object"]
    errors: list[str] = []
    allowed_types = {"null", "boolean", "integer", "number", "string", "array", "object"}
    declared = schema.get("type")
    declared_types = [declared] if isinstance(declared, str) else declared if isinstance(declared, list) else []
    if declared is not None and (not declared_types or any(item not in allowed_types for item in declared_types)):
        errors.append(f"{path}: unsupported type declaration {declared!r}")
    if "$ref" in schema and str(schema["$ref"]).rsplit("/", 1)[-1] not in schemas:
        errors.append(f"{path}: unresolved schema reference {schema['$ref']}")
    if "required" in schema and (not isinstance(schema["required"], list) or any(not isinstance(item, str) for item in schema["required"])):
        errors.append(f"{path}: required must be an array of strings")
    if "properties" in schema:
        if not isinstance(schema["properties"], dict):
            errors.append(f"{path}: properties must be an object")
        else:
            for name, child in schema["properties"].items():
                errors.extend(schema_definition_errors(child, schemas, f"{path}.properties.{name}"))
    if "items" in schema:
        errors.extend(schema_definition_errors(schema["items"], schemas, f"{path}.items"))
    if isinstance(schema.get("additionalProperties"), dict):
        errors.extend(schema_definition_errors(schema["additionalProperties"], schemas, f"{path}.additionalProperties"))
    if "oneOf" in schema:
        if not isinstance(schema["oneOf"], list) or not schema["oneOf"]:
            errors.append(f"{path}: oneOf must contain at least one schema")
        else:
            for index, child in enumerate(schema["oneOf"]):
                errors.extend(schema_definition_errors(child, schemas, f"{path}.oneOf[{index}]"))
    if schema.get("format") not in {None, "date", "date-time"}:
        errors.append(f"{path}: unsupported format {schema['format']!r}")
    return errors


def validate_instance_schema(instance: Any, schema_name: str) -> list[str]:
    schemas, _ = schema_bundle(str(SPEC_ROOT))
    schema = schemas.get(schema_name)
    if schema is None:
        return [f"Schema does not exist: {schema_name}"]
    return validate_schema_value(instance, schema, schemas)


def validate_json_schema(instance_path: Path, schema_name: str) -> list[str]:
    try:
        instance = json.loads(instance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [str(exc)]
    return validate_instance_schema(instance, schema_name)


def gate_class(gate_id: str) -> str:
    gates = workflow()["gates"]
    return "hard" if gate_id in gates["hard"] else "soft"


def write_gate_receipt(directory: Path, run: dict[str, Any], gate_id: str, outcome: str, findings: list[dict[str, Any]], evaluator: dict[str, Any], repair_state: str | None = None) -> Path:
    normalized_findings = []
    for finding in findings:
        normalized = dict(finding)
        normalized.setdefault("criterion", "unspecified")
        normalized.setdefault("artifact", normalized.pop("path", "current"))
        normalized.setdefault("location", None)
        normalized.setdefault("finding", "Gate criterion failed.")
        normalized.setdefault("repair_instruction", "Repair the affected artifact at the declared repair state.")
        normalized_findings.append(normalized)
    findings = normalized_findings
    receipt = {
        "gate_receipt_schema_version": "1.0.0",
        "run_id": run["run_id"],
        "gate_id": gate_id,
        "gate_class": gate_class(gate_id),
        "artifact_hashes": {item["type"]: item["sha256"] for item in run.get("artifact_index", [])},
        "outcome": outcome,
        "criteria": [],
        "findings": findings,
        "repair_state": repair_state,
        "evaluator": evaluator,
        "created_at": utc_now(),
    }
    errors = validate_instance_schema(receipt, "gate-receipt.schema.json")
    if errors:
        raise FlowError("Controller generated an invalid gate receipt", EXIT_INTEGRITY, errors)
    path = directory / "receipts" / f"{gate_id.lower()}-{len(list((directory / 'receipts').glob('*.json'))) + 1}.json"
    write_json(path, receipt)
    record_artifact(directory, run, path, f"gate-receipt:{gate_id}", {"actor": evaluator.get("type", "code")})
    append_event(directory, run, "GATE_RECORDED", evaluator.get("type", "code"), {"gate_id": gate_id, "outcome": outcome, "findings": findings})
    return path


def provider_config_path() -> Path:
    override = os.environ.get("ARTICLE_FLOW_PROVIDER_CONFIG")
    return Path(override).expanduser().resolve() if override else runtime_home() / "config" / "providers.json"


def capability_registry() -> dict[str, Any]:
    """Merge release defaults with an optional private runtime provider configuration."""
    base = load_json(SPEC_ROOT / "evaluations" / "capability-registry.json")
    providers = {str(item["provider_id"]): dict(item) for item in base.get("providers", [])}
    config_path = provider_config_path()
    if config_path.is_file():
        config_errors = validate_json_schema(config_path, "provider-config.schema.json")
        if config_errors:
            raise FlowError(f"Invalid private provider configuration: {config_path}", EXIT_INTEGRITY, config_errors)
        private = load_json(config_path)
        for raw in private.get("providers", []):
            if not isinstance(raw, dict) or not raw.get("provider_id"):
                raise FlowError(f"Invalid provider in {config_path}")
            provider_id = str(raw["provider_id"])
            merged = dict(providers.get(provider_id, {}))
            merged.update(raw)
            providers[provider_id] = merged
    return {
        "registry_schema_version": base.get("registry_schema_version", "1.0.0"),
        "workflow_version": base.get("workflow_version", workflow()["workflow_version"]),
        "configuration_path": str(config_path),
        "providers": [providers[key] for key in sorted(providers)],
    }


def promoted_evaluation_scores() -> dict[tuple[str, str, str], float]:
    registry = load_json(SPEC_ROOT / "evaluations" / "evaluation-registry.json")
    scores: dict[tuple[str, str, str], list[float]] = {}
    for item in registry.get("stage_scores", []):
        if isinstance(item, dict):
            key = (str(item.get("provider")), str(item.get("model")), str(item.get("stage")))
            scores.setdefault(key, []).append(float(item.get("score", 0)))
    runtime_evaluations = runtime_home() / "evaluations"
    if runtime_evaluations.is_dir():
        for path in sorted(runtime_evaluations.glob("*.json")):
            try:
                item = load_json(path)
            except FlowError:
                continue
            if item.get("promotion_status") != "promoted" or not item.get("human_calibration"):
                continue
            metrics = item.get("metrics", {})
            if not isinstance(metrics, dict) or not metrics:
                continue
            score = float(metrics.get("overall", sum(float(value) for value in metrics.values()) / len(metrics)))
            key = (str(item.get("provider")), str(item.get("model")), str(item.get("stage")))
            scores.setdefault(key, []).append(score)
    return {key: sum(values) / len(values) for key, values in scores.items()}


def resolved_provider_endpoint(provider: dict[str, Any]) -> str | None:
    variable = provider.get("base_url_environment_variable")
    if variable:
        return os.environ.get(str(variable))
    value = provider.get("base_url")
    return str(value).rstrip("/") if value else None


def route_candidates(stage: str, excluded_routes: set[str] | None = None) -> dict[str, Any]:
    if stage not in MODEL_STATES:
        return {"stage": stage, "required_capabilities": [], "candidates": [], "chosen": None, "reason": "deterministic stage; no model route permitted"}
    capabilities = capability_registry()
    score_map = promoted_evaluation_scores()
    required = STAGE_CAPABILITIES.get(stage, set())
    excluded_routes = excluded_routes or set()
    require_local = os.environ.get("ARTICLE_FLOW_REQUIRE_LOCAL", "").lower() in {"1", "true", "yes"}
    scored: list[dict[str, Any]] = []
    private_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for provider in capabilities.get("providers", []):
        provider_id = str(provider.get("provider_id"))
        models = provider.get("models", [])
        if not isinstance(models, list):
            models = []
        for model in models:
            if not isinstance(model, dict):
                continue
            model_id = str(model.get("model_id"))
            eligible = bool(provider.get("enabled", False) and model.get("enabled", True))
            exclusions: list[str] = []
            if not provider.get("enabled", False):
                exclusions.append("provider disabled")
            credential = provider.get("credential_environment_variable")
            if credential and not os.environ.get(str(credential)):
                eligible = False
                exclusions.append(f"missing {credential}")
            kind = str(provider.get("kind", "unknown"))
            if kind == "command":
                command = provider.get("command", [])
                executable = str(command[0]) if isinstance(command, list) and command else ""
                if not executable or not (Path(executable).exists() or shutil.which(executable)):
                    eligible = False
                    exclusions.append("command unavailable")
            if kind not in {"agent-hosted", "command"} and not resolved_provider_endpoint(provider):
                eligible = False
                exclusions.append("endpoint unavailable")
            stages = set(str(item) for item in model.get("stages", []))
            if stages and stage not in stages:
                eligible = False
                exclusions.append("stage not configured")
            model_capabilities = set(str(item) for item in model.get("capabilities", []))
            assumptions: list[str] = []
            if provider_id == "active-host":
                assumptions = sorted(required)
            else:
                missing = sorted(required - model_capabilities)
                if missing:
                    eligible = False
                    exclusions.append("missing capabilities: " + ", ".join(missing))
            if require_local and str(model.get("locality", provider.get("locality", "remote"))) != "local":
                eligible = False
                exclusions.append("operator requires a local route")
            if model.get("canary_status") in {"required", "failed"}:
                eligible = False
                exclusions.append(f"canary {model.get('canary_status')}")
            route_key = f"{provider_id}:{model_id}"
            if route_key in excluded_routes:
                eligible = False
                exclusions.append("prior gate failures exhausted this route for the current stage")
            public = {
                "provider": provider_id,
                "model": model_id,
                "model_version": model.get("version"),
                "eligible": eligible,
                "exclusion_reason": "; ".join(exclusions) if exclusions else None,
                "capability_assumptions": assumptions,
                "evaluation_score": score_map.get((provider_id, model_id, stage)),
                "kind": kind,
                "privacy": model.get("privacy", provider.get("privacy", "unknown")),
                "locality": model.get("locality", provider.get("locality", "unknown")),
                "cost_class": model.get("cost_class", "unknown"),
                "latency_class": model.get("latency_class", "unknown"),
                "canary_status": model.get("canary_status", "not-declared"),
            }
            scored.append(public)
            private_by_key[(provider_id, model_id)] = provider
    eligible_routes = [item for item in scored if item["eligible"]]
    evaluated = [item for item in eligible_routes if item["evaluation_score"] is not None]
    if evaluated:
        chosen = sorted(
            evaluated,
            key=lambda item: (-float(item["evaluation_score"]), item["provider"], item["model"]),
        )[0]
        reason = "highest promoted task-specific evaluation score among routes that meet the current constraints"
    else:
        chosen = next((item for item in eligible_routes if item["provider"] == "active-host"), None)
        if chosen:
            reason = "evaluation registry is uncalibrated; use the active capable host without claiming it is best"
        elif eligible_routes:
            chosen = sorted(eligible_routes, key=lambda item: (item["provider"], item["model"]))[0]
            reason = "no calibrated score and no active-host route; deterministic first eligible fallback, explicitly unranked"
        else:
            chosen = None
            reason = "no configured route meets the stage capabilities and operator constraints"
    fallbacks = [item for item in eligible_routes if chosen is None or (item["provider"], item["model"]) != (chosen["provider"], chosen["model"])]
    return {
        "stage": stage,
        "required_capabilities": sorted(required),
        "candidates": scored,
        "chosen": chosen,
        "fallbacks": fallbacks,
        "reason": reason,
        "configuration_path": capabilities["configuration_path"],
    }


def packet_inputs(directory: Path, run: dict[str, Any], state: str) -> list[dict[str, str]]:
    required = set(str(item) for item in state_definition(state).get("required_inputs", []))
    latest = {str(item["type"]): item for item in run.get("artifact_index", [])}
    missing = sorted(required - set(latest))
    if missing:
        raise FlowError(f"Cannot dispatch {state}; required artifacts are missing: {', '.join(missing)}", EXIT_INTEGRITY)
    result = []
    for artifact_type in sorted(required):
        item = latest[artifact_type]
        path = (directory / item["path"]).resolve()
        if not path.is_file():
            raise FlowError(f"Cannot dispatch {state}; artifact file is missing: {artifact_type}", EXIT_INTEGRITY)
        actual = sha256_path(path)
        if actual != item["sha256"]:
            raise FlowError(
                f"Cannot dispatch {state}; artifact hash changed: {artifact_type}",
                EXIT_INTEGRITY,
                {"expected_sha256": item["sha256"], "actual_sha256": actual, "path": str(path)},
            )
        result.append({"id": artifact_type, "path": str(path), "sha256": actual})
    return result


def json_artifact(directory: Path, run: dict[str, Any], artifact_type: str) -> dict[str, Any] | None:
    path = artifact_path(directory, run, artifact_type)
    if not path or path.suffix.lower() != ".json":
        return None
    try:
        return load_json(path)
    except FlowError:
        return None


def stage_output(state: str) -> tuple[str, str]:
    mapping = {
        "RESEARCH_PLAN": ("research-plan", "research-plan.json"),
        "RESEARCH": ("claim-ledger", "claim-ledger.json"),
        "INTENT_REVIEW": ("intent-candidate", "intent-candidate.json"),
        "ARTICLE_RECIPE": ("article-recipe", "article-recipe.json"),
        "BRIEF": ("brief", "brief.json"),
        "VOICE_PROBE": ("voice-probe", "voice-probe.json"),
        "DRAFT": ("draft", "draft.md"),
        "CLAIM_VERIFICATION": ("verified-claim-ledger", "verified-claim-ledger.json"),
        "EDIT": ("article", "article.md"),
        "POST_EDIT_CLAIM_VERIFICATION": ("post-edit-claim-ledger", "post-edit-claim-ledger.json"),
        "EDITORIAL_QA": ("editorial-qa", "editorial-qa.json"),
    }
    if state not in mapping:
        raise FlowError(f"State does not dispatch a model task: {state}")
    return mapping[state]


def task_packet(directory: Path, run: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    state = run["state"]
    definition = state_definition(state)
    artifact_type, filename = stage_output(state)
    attempt = int(run["attempts"].get(state, 0)) + 1
    if attempt > int(definition.get("max_attempts", 1)):
        run["status"] = "WAITING_HUMAN"
        append_event(directory, run, "ESCALATION", "controller", {
            "state": state,
            "attempts": attempt - 1,
            "maximum": definition.get("max_attempts"),
            "question": "Should this run stop, change route, or receive an operator-approved exception?",
        })
        save_run(directory, run)
        raise FlowError(f"{state} exhausted its bounded attempts and requires an operator decision", EXIT_WAITING)
    failures_for_state = run.get("route_failures", {}).get(state, {})
    fallback_threshold = max(1, int(definition.get("max_attempts", 1)) - 1)
    excluded = {key for key, count in failures_for_state.items() if int(count) >= fallback_threshold}
    route = route_candidates(state, excluded)
    if state in {"CLAIM_VERIFICATION", "POST_EDIT_CLAIM_VERIFICATION"} and route.get("chosen"):
        source_type = "draft" if state == "CLAIM_VERIFICATION" else "article"
        source_item = artifact(run, source_type) or {}
        prior_route = source_item.get("producer", {}).get("route") if isinstance(source_item.get("producer"), dict) else None
        if prior_route:
            prior_key = (prior_route.get("provider"), prior_route.get("model"))
            alternatives = [item for item in route.get("candidates", []) if item.get("eligible") and (item.get("provider"), item.get("model")) != prior_key]
            if alternatives and (route["chosen"].get("provider"), route["chosen"].get("model")) == prior_key:
                evaluated = [item for item in alternatives if item.get("evaluation_score") is not None]
                replacement = sorted(evaluated or alternatives, key=lambda item: (-(item.get("evaluation_score") or 0), item["provider"], item["model"]))[0]
                prior_chosen = route["chosen"]
                route["chosen"] = replacement
                route["fallbacks"] = [prior_chosen, *[item for item in route.get("fallbacks", []) if (item.get("provider"), item.get("model")) != (replacement.get("provider"), replacement.get("model"))]]
                route["reason"] += "; selected an eligible route independent from the producer of the artifact being verified"
    if route.get("chosen") is None:
        run["status"] = "BLOCKED"
        append_event(directory, run, "ESCALATION", "controller", {
            "state": state,
            "question": "Which configured model route or missing capability should be added for this stage?",
            "routing": route,
        })
        save_run(directory, run)
        raise FlowError(f"No eligible model route is available for {state}", EXIT_WAITING, route)
    recipe = json_artifact(directory, run, "article-recipe")
    intent = json_artifact(directory, run, "intent") or json_artifact(directory, run, "intent-candidate")
    reader_job = None
    if recipe:
        reader_job = recipe.get("reader_job")
    elif intent:
        reader_job = intent.get("reader_job")
    rule_map = {item["id"]: item["text"] for item in workflow()["rules"]}
    stage_rules = {
        "RESEARCH_PLAN": ["AF-EVIDENCE-001"],
        "RESEARCH": ["AF-CITATION-001", "AF-EVIDENCE-001"],
        "INTENT_REVIEW": ["AF-PREC-001"],
        "ARTICLE_RECIPE": ["AF-PERSON-001", "AF-LENGTH-001", "AF-SHAPE-001", "AF-END-001"],
        "BRIEF": ["AF-PREC-001", "AF-LENGTH-001"],
        "VOICE_PROBE": ["AF-VOICE-001"],
        "DRAFT": ["AF-SHAPE-001", "AF-CITATION-001", "AF-EVIDENCE-001", "AF-VOICE-001"],
        "CLAIM_VERIFICATION": ["AF-EVIDENCE-001", "AF-CITATION-001", "AF-VERIFY-001"],
        "EDIT": ["AF-NATURALIZE-001", "AF-VOICE-001"],
        "POST_EDIT_CLAIM_VERIFICATION": ["AF-EVIDENCE-001", "AF-CITATION-001", "AF-NATURALIZE-001", "AF-VERIFY-001"],
        "EDITORIAL_QA": ["AF-REPAIR-001", "AF-MATURITY-001"],
    }
    allowed_tools = ["read_run_artifacts", "write_requested_output"]
    if state in {"RESEARCH_PLAN", "RESEARCH", "CLAIM_VERIFICATION", "POST_EDIT_CLAIM_VERIFICATION"}:
        allowed_tools += ["web_or_approved_local_corpus", "direct_source_retrieval"]
    output_path = directory / "submissions" / f"{attempt:02d}-{filename}"
    output_schema_name = definition.get("output_schema") if output_path.suffix.lower() == ".json" else None
    output_schema = load_json(SPEC_ROOT / "schemas" / output_schema_name) if output_schema_name else None
    packet = {
        "task_packet_schema_version": "1.0.0",
        "workflow_version": run["workflow_version"],
        "run_id": run["run_id"],
        "stage": state,
        "attempt": attempt,
        "objective": definition["objective"],
        "inputs": packet_inputs(directory, run, state),
        "reader_job": reader_job,
        "article_recipe": recipe,
        "allowed_tools": allowed_tools,
        "side_effect_policy": definition["side_effect_class"],
        "constraints": [rule_map[item] for item in stage_rules.get(state, [])],
        "expected_outputs": [{
            "artifact_type": artifact_type,
            "path": str(output_path),
            "format": output_path.suffix.lstrip("."),
            "schema_name": output_schema_name,
            "schema": output_schema,
        }],
        "success_criteria": [f"Pass {definition['gate']} with observable evidence", "Return only the requested artifact; do not self-advance the run"],
        "non_authorities": ["9-Archive", "6-Completed-Articles examples", "CHANGELOG history", "prior conversation not listed as an input"],
        "stop_conditions": ["A required input is absent or hash-mismatched", "A material operator decision would be inferred", "A required source cannot be verified", "The requested side effect is not allowed"],
        "escalation_question": "What is the smallest operator decision or missing capability needed to complete this stage without guessing?",
        "selected_route": route,
    }
    path = directory / "tasks" / f"{state.lower()}-{attempt:02d}.json"
    write_json(path, packet)
    errors = validate_json_schema(path, "task-packet.schema.json")
    if errors:
        path.unlink(missing_ok=True)
        raise FlowError("Controller generated an invalid task packet", EXIT_INTEGRITY, errors)
    record_artifact(directory, run, path, f"task-packet:{state}:{attempt}", {"actor": "controller", "version": CONTROLLER_VERSION})
    run["attempts"][state] = attempt
    run["status"] = "WAITING_MODEL"
    append_event(directory, run, "TASK_DISPATCHED", "controller", {"state": state, "attempt": attempt, "packet": path.relative_to(directory).as_posix(), "route": route})
    save_run(directory, run)
    return path, packet


def provider_for_route(route: dict[str, Any]) -> dict[str, Any]:
    provider_id = str(route.get("provider"))
    for provider in capability_registry().get("providers", []):
        if str(provider.get("provider_id")) == provider_id:
            return provider
    raise FlowError(f"Provider route is no longer configured: {provider_id}")


def model_prompt(packet: dict[str, Any]) -> str:
    sections = [
        "You are performing one bounded stage in a provider-neutral article workflow.",
        "The controller, not you, owns state transitions and gate outcomes.",
        "Return only the requested artifact. Do not wrap it in a Markdown fence and do not add commentary.",
        "If a stop condition is met, return the smallest schema-valid artifact that records the unresolved condition; never invent evidence or operator intent.",
        "",
        "TASK PACKET",
        json.dumps(packet, indent=2, ensure_ascii=False),
    ]
    for item in packet.get("inputs", []):
        path = Path(item["path"])
        data = path.read_bytes()
        if sha256_bytes(data) != item["sha256"]:
            raise FlowError(f"Task input changed before provider invocation: {item['id']}", EXIT_INTEGRITY)
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FlowError(f"Task input is not UTF-8 text: {item['id']}") from exc
        sections += ["", f"INPUT {item['id']} sha256={item['sha256']}", content]
    return "\n".join(sections)


def post_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=canonical_json(body),
        headers={"Content-Type": "application/json", "User-Agent": f"article-flow/{CONTROLLER_VERSION}", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        diagnostic = exc.read().decode("utf-8", errors="replace")[:2000]
        raise FlowError(f"Provider HTTP error {exc.code}", EXIT_FAILED, {"body": diagnostic}) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise FlowError(f"Provider request failed: {exc}") from exc
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise FlowError("Provider returned non-JSON transport output", EXIT_FAILED, payload[:1000].decode("utf-8", errors="replace")) from exc
    if not isinstance(value, dict):
        raise FlowError("Provider returned a non-object transport response")
    return value


def output_text_from_response(kind: str, response: dict[str, Any]) -> str:
    if kind == "openai-responses":
        if isinstance(response.get("output_text"), str):
            return str(response["output_text"])
        texts = []
        for output in response.get("output", []):
            if not isinstance(output, dict):
                continue
            for content in output.get("content", []):
                if isinstance(content, dict) and content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                    texts.append(content["text"])
        if texts:
            return "\n".join(texts)
    if kind == "anthropic-messages":
        texts = [item.get("text") for item in response.get("content", []) if isinstance(item, dict) and item.get("type") == "text"]
        if texts:
            return "\n".join(str(item) for item in texts)
    if kind == "google-generative-language":
        texts = []
        for candidate in response.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []) if isinstance(candidate, dict) else []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    texts.append(part["text"])
        if texts:
            return "\n".join(texts)
    if kind == "openai-compatible":
        choices = response.get("choices", [])
        if choices and isinstance(choices[0], dict):
            content = choices[0].get("message", {}).get("content")
            if isinstance(content, str):
                return content
    raise FlowError(f"Could not locate text output in {kind} response", EXIT_FAILED, {"response_keys": sorted(response)})


def clean_model_output(text_value: str, expected_format: str) -> str:
    value = text_value.strip()
    if value.startswith("```") and value.endswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```") and lines[-1].strip() == "```":
            value = "\n".join(lines[1:-1]).strip()
    if expected_format == "json":
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise FlowError(f"Provider did not return the requested JSON artifact: {exc}") from exc
        value = json.dumps(parsed, indent=2, ensure_ascii=False)
    return value + "\n"


def invoke_route(route: dict[str, Any], packet_path: Path, packet: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    provider = provider_for_route(route)
    kind = str(route.get("kind"))
    if kind == "agent-hosted":
        raise FlowError("The active-host route is executed by the calling session; use the task packet and submission command", EXIT_WAITING)
    expected = packet["expected_outputs"][0]
    output_path = Path(expected["path"])
    timeout = int(state_definition(packet["stage"]).get("timeout_seconds", 900))
    started = time.monotonic()
    if kind == "command":
        template = provider.get("command", [])
        if not isinstance(template, list) or not template:
            raise FlowError("Command provider has no command template")
        replacements = {
            "{packet}": str(packet_path),
            "{output}": str(output_path),
            "{stage}": str(packet["stage"]),
            "{model}": str(route["model"]),
        }
        command = []
        for token in template:
            value = str(token)
            for marker, replacement in replacements.items():
                value = value.replace(marker, replacement)
            command.append(value)
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise FlowError("Command provider failed", EXIT_FAILED, {"exit_code": result.returncode, "stderr": result.stderr[-2000:]})
        raw = output_path.read_text(encoding="utf-8") if output_path.is_file() else result.stdout
        transport = {"kind": kind, "command": [command[0], "<arguments-redacted>"], "stderr": result.stderr[-1000:]}
    else:
        prompt = model_prompt(packet)
        endpoint = resolved_provider_endpoint(provider)
        if not endpoint:
            raise FlowError("Provider endpoint is not configured")
        credential_name = provider.get("credential_environment_variable")
        credential = os.environ.get(str(credential_name)) if credential_name else None
        model = str(route["model"])
        if kind == "openai-responses":
            url = endpoint if endpoint.endswith("/responses") else endpoint.rstrip("/") + "/responses"
            response = post_json(url, {"model": model, "input": prompt}, {"Authorization": f"Bearer {credential}"}, timeout)
        elif kind == "anthropic-messages":
            url = endpoint if endpoint.endswith("/messages") else endpoint.rstrip("/") + "/messages"
            response = post_json(url, {"model": model, "max_tokens": int(provider.get("max_output_tokens", 12000)), "messages": [{"role": "user", "content": prompt}]}, {"x-api-key": str(credential), "anthropic-version": str(provider.get("api_version", "2023-06-01"))}, timeout)
        elif kind == "google-generative-language":
            url = endpoint.rstrip("/") + f"/models/{urllib.parse.quote(model, safe='')}:generateContent?key={urllib.parse.quote(str(credential), safe='')}"
            response = post_json(url, {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}, {}, timeout)
        elif kind == "openai-compatible":
            url = endpoint if endpoint.endswith("/chat/completions") else endpoint.rstrip("/") + "/chat/completions"
            headers = {"Authorization": f"Bearer {credential}"} if credential else {}
            response = post_json(url, {"model": model, "messages": [{"role": "user", "content": prompt}]}, headers, timeout)
        else:
            raise FlowError(f"Unsupported provider kind: {kind}")
        raw = output_text_from_response(kind, response)
        transport = {"kind": kind, "response_id": response.get("id"), "usage": response.get("usage") or response.get("usageMetadata")}
    cleaned = clean_model_output(raw, str(expected.get("format")))
    elapsed_ms = round((time.monotonic() - started) * 1000)
    return cleaned, {"provider": route["provider"], "model": route["model"], "model_version": route.get("model_version"), "elapsed_ms": elapsed_ms, "transport": transport}


def current_packet(directory: Path, run: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    prefix = f"task-packet:{run['state']}:"
    item = next((entry for entry in reversed(run.get("artifact_index", [])) if str(entry.get("type", "")).startswith(prefix)), None)
    if item:
        path = directory / item["path"]
        return path, load_json(path)
    return task_packet(directory, run)


def command_execute_stage(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    if run["state"] not in MODEL_STATES:
        raise FlowError(f"State {run['state']} is deterministic or complete and cannot invoke a model")
    packet_path, packet = current_packet(directory, run)
    route_set = packet["selected_route"]
    routes = [route_set.get("chosen"), *route_set.get("fallbacks", [])]
    routes = [item for item in routes if isinstance(item, dict)]
    if args.route:
        provider_id, separator, model_id = args.route.partition(":")
        if not separator:
            raise FlowError("--route must be PROVIDER:MODEL", EXIT_USAGE)
        selected = next((item for item in route_set.get("candidates", []) if item.get("provider") == provider_id and item.get("model") == model_id), None)
        canary_only = bool(selected and selected.get("exclusion_reason") and all(part.strip().startswith("canary ") for part in str(selected.get("exclusion_reason")).split(";")))
        if not selected or (not selected.get("eligible") and not (args.canary and canary_only)):
            raise FlowError("Requested route is absent or ineligible", EXIT_USAGE, selected)
        if args.canary and canary_only:
            selected = {**selected, "eligible": True, "exclusion_reason": None, "canary_execution": True}
        routes = [selected]
    controller_routes = [item for item in routes if item.get("kind") != "agent-hosted"]
    if not controller_routes:
        raise FlowError("No controller-hosted route is eligible; the active host must perform the task packet", EXIT_WAITING, {"task_packet": str(packet_path), "submission_command": ["article-flow", "submit", run["run_id"], "--stage", run["state"], "--file", packet["expected_outputs"][0]["path"]]})
    failures = []
    for route in controller_routes:
        try:
            output, call = invoke_route(route, packet_path, packet)
            output_path = Path(packet["expected_outputs"][0]["path"])
            atomic_write(output_path, output.encode("utf-8"))
            receipt = {
                "model_call_receipt_schema_version": "1.0.0",
                "run_id": run["run_id"],
                "stage": run["state"],
                "attempt": packet["attempt"],
                "packet_sha256": sha256_path(packet_path),
                "output_sha256": sha256_path(output_path),
                "selection_reason": route_set.get("reason"),
                "route": call,
                "canary_execution": bool(args.canary),
                "created_at": utc_now(),
            }
            receipt_path = directory / "receipts" / f"model-call-{run['state'].lower()}-{packet['attempt']:02d}.json"
            write_json(receipt_path, receipt)
            record_artifact(directory, run, receipt_path, f"model-call:{run['state']}:{packet['attempt']}", {"actor": "controller", "version": CONTROLLER_VERSION})
            command = [sys.executable, str(SCRIPT_PATH), "submit", run["run_id"], "--stage", run["state"], "--file", str(output_path), "--json"]
            result = subprocess.run(command, capture_output=True, text=True)
            try:
                submission = json.loads(result.stdout)
            except json.JSONDecodeError:
                submission = {"raw_stdout": result.stdout, "stderr": result.stderr}
            emit({"ok": result.returncode in {EXIT_OK, EXIT_WAITING}, "model_call": receipt, "submission": submission}, args.json)
            return result.returncode
        except FlowError as exc:
            failures.append({"provider": route.get("provider"), "model": route.get("model"), "error": str(exc), "details": exc.details})
            append_event(directory, run, "MODEL_ROUTE_FAILURE", "controller", failures[-1])
    save_run(directory, run)
    raise FlowError("Every eligible controller-hosted route failed", EXIT_FAILED, failures)


def find_locked_tokens(text: str) -> dict[str, list[str]]:
    patterns = {
        "urls": r"https?://[^\s)\]>'\"]+",
        "numbers": r"(?<![A-Za-z])\d+(?:[.,]\d+)*(?:%|\b)",
        "dates": r"\b(?:19|20)\d{2}(?:-\d{2}-\d{2})?\b",
        "inline_code": r"`[^`\n]+`",
        "markdown_links": r"\[[^\]]+\]\([^)]+\)",
        "code_blocks": r"```[^\n]*\n.*?```",
        "direct_quotes": r"(?:^|\n)>[^\n]+",
    }
    return {name: sorted(re.findall(pattern, text, flags=re.MULTILINE | re.DOTALL)) for name, pattern in patterns.items()}


def lock_verified_fields(directory: Path, run: dict[str, Any], ledger_path: Path) -> None:
    draft = artifact_path(directory, run, "draft")
    if not draft:
        raise FlowError("Cannot lock verified fields without the draft", EXIT_INTEGRITY)
    ledger = load_json(ledger_path)
    claims = []
    for claim in ledger.get("claims", []):
        if claim.get("disposition") not in {"use", "qualify"}:
            continue
        claims.append({
            "claim_id": claim.get("claim_id"),
            "risk": claim.get("risk"),
            "allowed_wording": claim.get("allowed_wording"),
            "source_url_or_local_id": claim.get("source_url_or_local_id"),
            "checked_at": claim.get("checked_at"),
        })
    value = {
        "locked_fields_schema_version": "1.0.0",
        "run_id": run["run_id"],
        "source_sha256": sha256_path(draft),
        "tokens": find_locked_tokens(draft.read_text(encoding="utf-8")),
        "claims": claims,
    }
    path = directory / "artifacts" / "locked-fields.json"
    write_json(path, value)
    errors = validate_json_schema(path, "locked-fields.schema.json")
    if errors:
        raise FlowError("Controller generated invalid locked fields", EXIT_INTEGRITY, errors)
    record_artifact(directory, run, path, "locked-fields", {"actor": "controller", "version": CONTROLLER_VERSION}, inputs=[artifact(run, "draft")["artifact_id"], artifact(run, "verified-claim-ledger")["artifact_id"]])


def automatic_gate(directory: Path, run: dict[str, Any], state: str, submission: Path) -> tuple[str, list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    if not submission.is_file() or submission.stat().st_size == 0:
        findings.append({"criterion": "artifact_present", "artifact": str(submission), "location": None, "finding": "Requested output is missing or empty.", "repair_instruction": "Create the requested observable artifact."})
        return "REPAIR", findings
    if submission.suffix == ".json":
        try:
            value = load_json(submission)
        except FlowError as exc:
            findings.append({"criterion": "valid_json", "artifact": str(submission), "location": None, "finding": str(exc), "repair_instruction": "Return valid JSON matching the task packet."})
            return "REPAIR", findings
        schema_by_state = {
            "RESEARCH_PLAN": "research-plan.schema.json",
            "RESEARCH": "claim-ledger.schema.json",
            "INTENT_REVIEW": "intent.schema.json",
            "ARTICLE_RECIPE": "article-recipe.schema.json",
            "BRIEF": "brief.schema.json",
            "VOICE_PROBE": "voice-probe.schema.json",
            "CLAIM_VERIFICATION": "claim-ledger.schema.json",
            "POST_EDIT_CLAIM_VERIFICATION": "claim-ledger.schema.json",
            "EDITORIAL_QA": "editorial-assessment.schema.json",
        }
        schema = schema_by_state.get(state)
        if schema:
            for error in validate_json_schema(submission, schema):
                findings.append({"criterion": "schema", "artifact": str(submission), "location": None, "finding": error, "repair_instruction": f"Conform to {schema}."})
        if "run_id" in value and value.get("run_id") != run["run_id"]:
            findings.append({"criterion": "run_identity", "artifact": str(submission), "location": "run_id", "finding": "Artifact belongs to a different run.", "repair_instruction": "Use the run_id in the current task packet."})
        if state in {"RESEARCH", "CLAIM_VERIFICATION", "POST_EDIT_CLAIM_VERIFICATION"}:
            for claim in value.get("claims", []):
                if claim.get("risk") in {"medium", "high"} and claim.get("disposition") in {"use", "qualify"}:
                    if not claim.get("source_url_or_local_id") or not claim.get("exact_locator_or_supporting_excerpt"):
                        findings.append({"criterion": "claim_evidence", "artifact": str(submission), "location": str(claim.get("claim_id")), "finding": "Medium/high-risk used claim lacks traceable support.", "repair_instruction": "Add direct support, qualify/omit the claim, or escalate."})
                    if str(claim.get("source_url_or_local_id", "")).lower() in {"model-memory", "training-data", "memory"}:
                        findings.append({"criterion": "no_memory_citations", "artifact": str(submission), "location": str(claim.get("claim_id")), "finding": "Model memory is not an evidence source.", "repair_instruction": "Use an approved source/corpus, generalize or omit, or escalate."})
                    if not claim.get("checked_at") or not claim.get("freshness_horizon"):
                        findings.append({"criterion": "freshness", "artifact": str(submission), "location": str(claim.get("claim_id")), "finding": "Medium/high-risk used claim lacks a checked date or freshness horizon.", "repair_instruction": "Record when the source was checked and why it remains current enough."})
                    if claim.get("contradiction_status") == "unresolved":
                        findings.append({"criterion": "source_disagreement", "artifact": str(submission), "location": str(claim.get("claim_id")), "finding": "A claim with unresolved source disagreement cannot be used without escalation.", "repair_instruction": "Represent the disagreement, qualify/omit the claim, or escalate."})
                    source = str(claim.get("source_url_or_local_id") or "")
                    if state in {"CLAIM_VERIFICATION", "POST_EDIT_CLAIM_VERIFICATION"} and source.startswith(("http://", "https://")):
                        status, _, _ = fetch_url(source, timeout=15)
                        if not (200 <= status < 400 or status in {401, 403, 429, 999}):
                            findings.append({"criterion": "source_resolution", "artifact": str(submission), "location": str(claim.get("claim_id")), "finding": f"Source URL did not resolve during independent verification (HTTP {status}).", "repair_instruction": "Repair the source, use another direct source, qualify/omit, or escalate."})
        if state == "VOICE_PROBE":
            candidates = [str(item.get("candidate_id")) for item in value.get("candidates", []) if isinstance(item, dict)]
            orders = value.get("comparison_orders", [])
            if len(candidates) >= 2 and not any(list(order) == list(reversed(candidates)) for order in orders if isinstance(order, list)):
                findings.append({"criterion": "order_reversal", "artifact": str(submission), "location": "comparison_orders", "finding": "The voice comparison does not include a reversed candidate order.", "repair_instruction": "Include both forward and reversed comparison orders to expose position bias."})
        if state == "ARTICLE_RECIPE":
            if len(value.get("outline_candidates", [])) < 2:
                findings.append({"criterion": "shape_candidates", "artifact": str(submission), "location": "outline_candidates", "finding": "Fewer than two meaningfully different shapes were considered.", "repair_instruction": "Compare at least two shapes against the reader job and available evidence."})
            if not value.get("selection_reason"):
                findings.append({"criterion": "shape_reason", "artifact": str(submission), "location": "selection_reason", "finding": "The selected form has no recorded reason.", "repair_instruction": "Explain why this form best serves the reader job."})
            if value.get("variation_budget", {}).get("recent_post_comparison") and not value.get("recent_post_comparison"):
                findings.append({"criterion": "recent_post_comparison", "artifact": str(submission), "location": "recent_post_comparison", "finding": "The recipe requests a recent-post comparison but does not record one.", "repair_instruction": "Compare observable recent patterns; leave unavailable fields unknown rather than inferring them."})
            dimensions = value.get("variation_budget", {}).get("macro_dimensions")
            count = len(dimensions) if isinstance(dimensions, list) else int(dimensions or 0)
            if count < 2 or count > 3:
                findings.append({"criterion": "variation_budget", "artifact": str(submission), "location": "variation_budget.macro_dimensions", "finding": "A normal recipe should vary two or three macro dimensions.", "repair_instruction": "Choose two or three useful macro dimensions; do not create decorative randomness."})
        if state == "EDITORIAL_QA" and value.get("outcome") != "PASS":
            supplied = value.get("findings", [])
            if supplied:
                findings.extend(supplied)
            else:
                findings.append({"criterion": "editorial_outcome", "artifact": str(submission), "location": None, "finding": f"Editorial assessment returned {value.get('outcome')}.", "repair_instruction": "Return a passage-specific finding and repair destination."})
    if state == "EDIT":
        locked_path = artifact_path(directory, run, "locked-fields")
        if locked_path:
            before = load_json(locked_path).get("tokens", {})
            after = find_locked_tokens(submission.read_text(encoding="utf-8"))
            for category in before:
                if before[category] != after[category]:
                    findings.append({"criterion": "locked_fields", "artifact": str(submission), "location": category, "finding": f"Naturalization changed locked {category}.", "repair_instruction": "Restore the locked values or reopen claim verification."})
            recipe = json_artifact(directory, run, "article-recipe") or {}
            if recipe.get("citation_mode") == "links":
                article_text = submission.read_text(encoding="utf-8")
                for claim in load_json(locked_path).get("claims", []):
                    source = claim.get("source_url_or_local_id")
                    if claim.get("risk") in {"medium", "high"} and isinstance(source, str) and source.startswith("http") and source not in article_text:
                        findings.append({"criterion": "claim_citation_mapping", "artifact": str(submission), "location": str(claim.get("claim_id")), "finding": "A used medium/high-risk claim lost its source link.", "repair_instruction": "Restore the verified source link or reopen claim verification."})
    if state in {"DRAFT", "EDIT"}:
        text = submission.read_text(encoding="utf-8")
        for pattern in (r"\[Writer to research[^\]]*\]", r"\bTODO\b", r"/mnt/[a-z]/Users/", r"[A-Z]:\\Users\\"):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                findings.append({"criterion": "no_placeholders_or_private_paths", "artifact": str(submission), "location": match.group(0), "finding": "Public-candidate text contains a placeholder or private local path.", "repair_instruction": "Resolve or remove the private/internal text."})
    return ("PASS" if not findings else "REPAIR"), findings


def recent_article_history(limit: int | None = None) -> dict[str, Any]:
    """Read only observable publication metadata; unknown recipe fields stay unknown."""
    if limit is None:
        limit = int(policy()["editorial_defaults"].get("recent_post_window", 5))
    articles: list[dict[str, Any]] = []
    repository = publication_repo_root()
    docs = repository / "docs" if repository else Path("/__article_flow_unavailable__")
    for path in docs.glob("*.html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        published = re.search(r'<meta\s+property="article:published_time"\s+content="([^"]+)"', text)
        canonical = re.search(r'<link\s+rel="canonical"\s+href="([^"]+)"', text)
        title = re.search(r"<title>(.*?)</title>", text, flags=re.DOTALL)
        if not published or not canonical or not title:
            continue
        recipe_meta: dict[str, Any] = {}
        encoded = re.search(r'<meta\s+name="article-flow-recipe"\s+content="([^"]*)"', text)
        if encoded:
            try:
                recipe_meta = json.loads(html.unescape(encoded.group(1)))
            except json.JSONDecodeError:
                recipe_meta = {"parse_status": "invalid"}
        articles.append({
            "path": path.relative_to(repository).as_posix() if repository else path.name,
            "title": html.unescape(re.sub(r"\s+", " ", title.group(1))).removesuffix(" | Josiah Hunter"),
            "published_at": published.group(1),
            "canonical_url": canonical.group(1),
            "article_revision": (re.search(r'<meta\s+name="article-flow-revision"\s+content="([^"]+)"', text) or [None, None])[1],
            "recipe": recipe_meta or {
                "archetype": "unknown",
                "opening": "unknown",
                "ending": "unknown",
                "summary": "unknown",
                "narrative_person": "unknown",
                "section_count": len(re.findall(r"<h[2-6]\b", text)),
                "list_count": len(re.findall(r"<(?:ul|ol)\b", text)),
                "diagram": "unknown",
            },
        })
    articles.sort(key=lambda item: (item["published_at"], item["canonical_url"]), reverse=True)
    return {
        "recent_article_history_schema_version": "1.0.0",
        "generated_at": utc_now(),
        "window": limit,
        "articles": articles[:limit],
        "publication_repository_available": repository is not None,
        "unknown_fields_are_not_inferred": True,
    }


def record_static_controls(directory: Path, run: dict[str, Any]) -> None:
    controls = [
        (SPEC_ROOT / "profiles" / "voice-profile.v1.json", "voice-profile"),
        (SPEC_ROOT / "10-Final-Prose-Naturalization" / "Final-Prose-Naturalization-Directive.md", "naturalization-directive"),
    ]
    for source, artifact_type in controls:
        destination = directory / "artifacts" / source.name
        shutil.copy2(source, destination)
        record_artifact(
            directory,
            run,
            destination,
            artifact_type,
            {"actor": "controller", "source": source.relative_to(SPEC_ROOT).as_posix(), "version": CONTROLLER_VERSION},
        )
    history_path = directory / "artifacts" / "recent-article-history.json"
    write_json(history_path, recent_article_history())
    record_artifact(directory, run, history_path, "recent-article-history", {"actor": "controller", "version": CONTROLLER_VERSION})
    environment = {
        "environment_receipt_schema_version": "1.0.0",
        "created_at": utc_now(),
        "controller_version": CONTROLLER_VERSION,
        "workflow_version": run["workflow_version"],
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "repository_commit": release_source_commit(),
        "provider_configuration": str(provider_config_path()),
        "provider_configuration_present": provider_config_path().is_file(),
    }
    environment_path = directory / "artifacts" / "environment.json"
    write_json(environment_path, environment)
    record_artifact(directory, run, environment_path, "environment", {"actor": "controller", "version": CONTROLLER_VERSION})


def next_state_payload(directory: Path, run: dict[str, Any]) -> dict[str, Any]:
    state = run["state"]
    if state in {"COMPLETE", "TERMINAL"}:
        return {"action": state.lower(), "run_id": run["run_id"], "state": state}
    review_artifact = {
        "INTENT_REVIEW": "intent-candidate",
        "ARTICLE_RECIPE": "article-recipe",
        "VOICE_PROBE": "voice-probe",
        "EDITORIAL_QA": "editorial-qa",
    }
    if state in REVIEW_STATES and artifact(run, review_artifact[state]):
        question = {
            "INTENT_REVIEW": "Does this candidate intent match what you want the article to accomplish? Confirm it or give the smallest correction.",
            "ARTICLE_RECIPE": "Does this article recipe choose the right form for the reader job? Confirm it or identify the choice to change.",
            "VOICE_PROBE": "Which short passage is closest to your voice, and what is the most important mismatch in the others?",
            "EDITORIAL_QA": "After proofreading the article and its passage-specific assessment, is this exact revision ready to package? Confirm it or identify the smallest required repair.",
        }[state]
        run["status"] = "WAITING_HUMAN"
        save_run(directory, run)
        return {
            "action": "human_decision",
            "run_id": run["run_id"],
            "state": state,
            "question": question,
            "approval_command": ["article-flow", "gate", run["run_id"], state_definition(state)["gate"], "--outcome", "PASS"],
        }
    if state == "PACKAGE":
        return {"action": "run_command", "run_id": run["run_id"], "state": state, "command": ["article-flow", "package", run["run_id"]]}
    if state == "PUBLISH_APPROVAL":
        plan = directory / "publication" / "plan.json"
        if not plan.exists():
            return {"action": "run_command", "run_id": run["run_id"], "state": state, "command": ["article-flow", "publish", "--plan", run["run_id"]]}
        run["status"] = "WAITING_HUMAN"
        save_run(directory, run)
        return {"action": "human_decision", "run_id": run["run_id"], "state": state, "question": "Approve this exact publication target and package revision before execution?", "plan": str(plan), "approval_command": ["article-flow", "gate", run["run_id"], "G-PUBLISH-APPROVAL", "--outcome", "PASS"]}
    if state == "PUBLISH":
        return {"action": "run_command", "run_id": run["run_id"], "state": state, "command": ["article-flow", "publish", "--execute", run["run_id"], "--approval", "APPROVAL_ID", "--commit", "--push"]}
    if state == "LIVE_VERIFICATION":
        return {"action": "run_command", "run_id": run["run_id"], "state": state, "command": ["article-flow", "verify-live", run["run_id"]]}
    if run.get("status") == "BLOCKED":
        definition = state_definition(state)
        return {"action": "repair_required", "run_id": run["run_id"], "state": state, "gate": definition.get("gate"), "command": ["article-flow", "repair", run["run_id"], definition.get("gate")]}
    if run.get("status") == "WAITING_MODEL":
        packet_path, packet = current_packet(directory, run)
    else:
        packet_path, packet = task_packet(directory, run)
    expected = packet["expected_outputs"][0]
    return {
        "action": "perform_task",
        "run_id": run["run_id"],
        "state": state,
        "task_packet": str(packet_path),
        "selected_route": packet["selected_route"],
        "expected_output": expected,
        "submission_command": ["article-flow", "submit", run["run_id"], "--stage", state, "--file", expected["path"]],
    }


def command_start(args: argparse.Namespace) -> int:
    integrity = check_manifest("worktree", allow_unavailable_repository=True)
    if not integrity["ok"]:
        raise FlowError(
            "Authoring cannot start because the protected workflow does not match its release manifest",
            EXIT_INTEGRITY,
            integrity,
        )
    seed = args.seed
    if args.seed_file:
        seed = Path(args.seed_file).read_text(encoding="utf-8")
    if seed is None:
        payload = bootstrap_payload()
        emit(payload, args.json)
        return EXIT_WAITING
    if not seed.strip():
        raise FlowError("Seed cannot be empty", EXIT_USAGE)
    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    run_id = f"AF-{stamp}-{slugify(args.slug or seed)}-{secrets.token_hex(4)}"
    directory = run_dir(run_id)
    directory.mkdir(parents=True, exist_ok=False)
    for name in ("artifacts", "tasks", "submissions", "receipts", "approvals", "package", "publication"):
        (directory / name).mkdir()
    run = {
        "run_schema_version": "1.0.0",
        "run_id": run_id,
        "workflow_version": workflow()["workflow_version"],
        "controller_version": CONTROLLER_VERSION,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "state": "NEW",
        "status": "ACTIVE",
        "event_log": "events.jsonl",
        "artifact_index": [],
        "attempts": {},
        "lock": None,
        "run_overrides": {"intent_approval": "required", "recipe_approval": "required", "voice_probe_approval": "required"},
        "publication": {},
        "route_failures": {},
    }
    save_run(directory, run)
    append_event(directory, run, "RUN_CREATED", "controller", {"workflow_version": run["workflow_version"], "controller_version": CONTROLLER_VERSION})
    seed_path = directory / "artifacts" / "seed.txt"
    atomic_write(seed_path, seed.encode("utf-8"))
    record_artifact(directory, run, seed_path, "seed", {"actor": "operator", "preserved_verbatim": True})
    record_static_controls(directory, run)
    transition(directory, run, "INTAKE", "controller", "Run identity and event chain created")
    write_gate_receipt(directory, run, "G-SEED-PRESERVED", "PASS", [], {"type": "code", "version": CONTROLLER_VERSION})
    transition(directory, run, "RESEARCH_PLAN", "controller", "Seed bytes recorded verbatim")
    payload = {"ok": True, "run_id": run_id, "state": run["state"], "run_directory": str(directory), "next_command": ["article-flow", "next", run_id]}
    emit(payload, args.json)
    return EXIT_OK


def latest_run_id() -> str:
    candidates = sorted(
        (path for path in runs_root().glob("AF-*") if path.is_dir() and (path / "run.json").is_file()),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    if not candidates:
        raise FlowError("No article runs exist yet; start one with article-flow start", EXIT_USAGE)
    return candidates[0].name


def command_status(args: argparse.Namespace) -> int:
    selected_run_id = args.run_id or latest_run_id()
    directory, run = load_run(selected_run_id)
    payload = {**run, "run_directory": str(directory), "event_log_integrity": True, "derived_state": run["state"]}
    emit(payload, args.json)
    return EXIT_OK


def command_next(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    with run_lock(directory, run):
        payload = next_state_payload(directory, run)
    emit(payload, args.json)
    return EXIT_WAITING if payload["action"] in {"human_decision", "perform_task", "repair_required"} else EXIT_OK


def command_resume(args: argparse.Namespace) -> int:
    return command_next(args)


def command_submit(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    if run["state"] != args.stage:
        raise FlowError(f"Submission stage {args.stage} does not match current state {run['state']}")
    source = Path(args.file).expanduser().resolve()
    if not source.is_file():
        raise FlowError(f"Submission file does not exist: {source}")
    artifact_type, filename = stage_output(args.stage)
    attempt = int(run["attempts"].get(args.stage, 1))
    destination = directory / "artifacts" / f"{attempt:02d}-{filename}"
    with run_lock(directory, run):
        packet_item = next((item for item in reversed(run["artifact_index"]) if item["type"].startswith(f"task-packet:{args.stage}:")), None)
        if not packet_item:
            raise FlowError(f"No dispatched task packet exists for {args.stage}", EXIT_INTEGRITY)
        packet_value = load_json(directory / packet_item["path"])
        for item in packet_value.get("inputs", []):
            input_path = Path(item["path"])
            actual_hash = sha256_path(input_path) if input_path.is_file() else None
            if actual_hash != item["sha256"]:
                raise FlowError(f"Task input changed before submission: {item['id']}", EXIT_INTEGRITY, {"expected_sha256": item["sha256"], "actual_sha256": actual_hash, "path": str(input_path)})
        if source != destination.resolve():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        outcome, findings = automatic_gate(directory, run, args.stage, destination)
        packet_route = None
        if packet_item:
            packet_route = packet_value.get("selected_route", {}).get("chosen")
        record_artifact(directory, run, destination, artifact_type, {"actor": "model_or_host", "route": packet_route}, inputs=[item["artifact_id"] for item in run["artifact_index"]])
        if args.stage == "CLAIM_VERIFICATION" and outcome == "PASS":
            lock_verified_fields(directory, run, destination)
        definition = state_definition(args.stage)
        recorded_outcome = "ESCALATE" if outcome == "PASS" and args.stage in REVIEW_STATES else outcome
        review_findings = findings
        if recorded_outcome == "ESCALATE" and not review_findings:
            review_findings = [{
                "criterion": "operator_owned_judgment",
                "artifact": str(destination),
                "location": None,
                "finding": "Mechanical validation passed; the controlling editorial judgment has not been inferred.",
                "repair_instruction": "Ask the operator the controller-supplied decision question.",
            }]
        write_gate_receipt(directory, run, definition["gate"], recorded_outcome, review_findings, {"type": "code", "version": CONTROLLER_VERSION}, definition.get("repair_state"))
        if outcome != "PASS":
            if packet_route:
                key = f"{packet_route.get('provider')}:{packet_route.get('model')}"
                stage_failures = run.setdefault("route_failures", {}).setdefault(args.stage, {})
                stage_failures[key] = int(stage_failures.get(key, 0)) + 1
                append_event(directory, run, "MODEL_OUTPUT_REJECTED", "controller", {"state": args.stage, "route": packet_route, "failure_count": stage_failures[key], "findings": findings})
            run["status"] = "BLOCKED"
            save_run(directory, run)
            payload = {"ok": False, "outcome": outcome, "state": run["state"], "findings": findings, "repair_command": ["article-flow", "repair", run["run_id"], definition["gate"]]}
            emit(payload, args.json)
            return EXIT_FAILED
        if args.stage in REVIEW_STATES:
            run["status"] = "WAITING_HUMAN"
            save_run(directory, run)
            payload = next_state_payload(directory, run)
        else:
            transition(directory, run, definition["next_on_pass"], "controller", f"{definition['gate']} passed")
            payload = {"ok": True, "outcome": "PASS", "state": run["state"], "next_command": ["article-flow", "next", run["run_id"]]}
    emit(payload, args.json)
    return EXIT_WAITING if payload.get("action") == "human_decision" else EXIT_OK


def command_gate(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    definition = state_definition(run["state"])
    expected_gate = definition.get("gate")
    args.gate_id = args.gate_id or expected_gate
    if not args.gate_id:
        raise FlowError(f"State {run['state']} has no operator-owned gate", EXIT_USAGE)
    if args.gate_id != expected_gate:
        raise FlowError(f"Gate {args.gate_id} does not control current state {run['state']} (expected {expected_gate})")
    if args.outcome not in workflow()["gate_outcomes"]:
        raise FlowError(f"Invalid gate outcome: {args.outcome}")
    if gate_class(args.gate_id) == "hard" and args.gate_id != "G-PUBLISH-APPROVAL":
        raise FlowError(f"Hard gate {args.gate_id} is code-owned and cannot be manually passed")
    with run_lock(directory, run):
        findings = []
        if args.finding:
            findings.append({"criterion": "operator_review", "artifact": args.artifact or "current", "location": None, "finding": args.finding, "repair_instruction": args.finding})
        if args.gate_id == "G-PUBLISH-APPROVAL" and args.outcome == "PASS":
            plan_path = directory / "publication" / "plan.json"
            if not plan_path.is_file():
                raise FlowError("Publication plan is missing")
            plan = load_json(plan_path)
            ttl = int(policy()["publication"]["approval_ttl_minutes"])
            expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=ttl)
            approval_id = f"AP-{secrets.token_hex(12)}"
            approval = {
                "publication_receipt_schema_version": "1.0.0",
                "run_id": run["run_id"],
                "target": plan["target"],
                "package_revision": plan["package_revision"],
                "approval_id": approval_id,
                "plan_sha256": sha256_path(plan_path),
                "expires_at": expires.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "status": "APPROVED",
                "commit": None,
                "url": None,
                "checks": [{"plan_sha256": sha256_path(plan_path)}],
                "created_at": utc_now(),
            }
            approval_path = directory / "approvals" / f"{approval_id}.json"
            write_json(approval_path, approval)
            record_artifact(directory, run, approval_path, "publish-approval", {"actor": "operator"})
            append_event(directory, run, "APPROVAL", "operator", {"approval_id": approval_id, "target": plan["target"], "package_revision": plan["package_revision"]})
        elif run["state"] in REVIEW_STATES and args.outcome == "PASS":
            type_map = {
                "INTENT_REVIEW": ("intent-candidate", "intent"),
                "ARTICLE_RECIPE": ("article-recipe", "article-recipe"),
                "VOICE_PROBE": ("voice-probe", "voice-probe"),
                "EDITORIAL_QA": ("editorial-qa", "editorial-qa"),
            }
            candidate_type, approved_type = type_map[run["state"]]
            candidate_path = Path(args.artifact).resolve() if args.artifact else artifact_path(directory, run, candidate_type)
            if not candidate_path or not candidate_path.is_file():
                raise FlowError(f"Candidate artifact is missing for {run['state']}")
            approved_path = directory / "artifacts" / f"approved-{approved_type}{candidate_path.suffix}"
            if run["state"] == "VOICE_PROBE":
                if not args.selection or not args.feedback:
                    raise FlowError("Voice-probe approval requires --selection CANDIDATE_ID and --feedback with the operator's most important reason", EXIT_APPROVAL)
                value = load_json(candidate_path)
                candidate_ids = {str(item.get("candidate_id")) for item in value.get("candidates", []) if isinstance(item, dict)}
                if args.selection not in candidate_ids:
                    raise FlowError(f"Unknown voice candidate: {args.selection}", EXIT_APPROVAL)
                value["operator_selection"] = {"candidate_id": args.selection, "reason": args.feedback, "confirmed_at": utc_now()}
                write_json(approved_path, value)
            else:
                shutil.copy2(candidate_path, approved_path)
            record_artifact(directory, run, approved_path, approved_type, {"actor": "operator", "decision": "confirmed"})
        write_gate_receipt(directory, run, args.gate_id, args.outcome, findings, {"type": "human", "identity": "operator"}, definition.get("repair_state"))
        if args.outcome == "PASS":
            transition(directory, run, definition["next_on_pass"], "operator", f"Operator confirmed {args.gate_id}")
        elif args.outcome == "REPAIR":
            transition(directory, run, definition["repair_state"], "operator", args.finding or "Operator requested repair")
        elif args.outcome == "TERMINAL":
            transition(directory, run, "TERMINAL", "operator", args.finding or "Operator ended run")
        else:
            run["status"] = "WAITING_HUMAN" if args.outcome == "ESCALATE" else "ACTIVE"
            save_run(directory, run)
        payload = {"ok": True, "outcome": args.outcome, "state": run["state"], "approval_id": locals().get("approval_id"), "next_command": ["article-flow", "next", run["run_id"]]}
    emit(payload, args.json)
    return EXIT_OK


def command_repair(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    definition = state_definition(run["state"])
    args.gate_id = args.gate_id or definition.get("gate")
    if not args.gate_id:
        raise FlowError(f"State {run['state']} has no repairable gate", EXIT_USAGE)
    if args.gate_id != definition.get("gate"):
        raise FlowError(f"Gate {args.gate_id} does not control current state {run['state']}")
    repair_state = definition.get("repair_state")
    if not repair_state:
        raise FlowError(f"No repair state declared for {run['state']}")
    with run_lock(directory, run):
        append_event(directory, run, "REPAIR", "operator_or_controller", {"gate_id": args.gate_id, "finding": args.finding, "repair_state": repair_state})
        transition(directory, run, repair_state, "controller", args.finding or f"Repair requested by {args.gate_id}")
    emit({"ok": True, "state": run["state"], "next_command": ["article-flow", "next", run["run_id"]]}, args.json)
    return EXIT_OK


def markdown_inline(value: str) -> str:
    placeholders: dict[str, str] = {}
    def hold(rendered: str) -> str:
        key = f"@@AF{len(placeholders)}@@"
        placeholders[key] = rendered
        return key
    value = re.sub(r"`([^`]+)`", lambda match: hold(f"<code>{html.escape(match.group(1))}</code>"), value)
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+|[^)]+)\)", lambda match: hold(f'<a href="{html.escape(match.group(2), quote=True)}">{html.escape(match.group(1))}</a>'), value)
    value = html.escape(value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", value)
    for key, rendered in placeholders.items():
        value = value.replace(key, rendered)
    return value


def markdown_to_html(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").split("\n")
    output: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    in_code = False
    code_lines: list[str] = []
    code_language = ""
    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{markdown_inline(' '.join(item.strip() for item in paragraph))}</p>")
            paragraph.clear()
    def close_list() -> None:
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = None
    for line in lines:
        if line.startswith("```"):
            flush_paragraph()
            close_list()
            if not in_code:
                in_code = True
                code_language = line[3:].strip()
                code_lines = []
            else:
                language_class = f' class="language-{html.escape(code_language)}"' if code_language else ""
                output.append(f"<pre><code{language_class}>{html.escape(chr(10).join(code_lines))}</code></pre>")
                in_code = False
            continue
        if in_code:
            code_lines.append(line)
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            if level == 1 and not output:
                continue
            output.append(f"<h{level}>{markdown_inline(heading.group(2))}</h{level}>")
            continue
        bullet = re.match(r"^\s*[-*+]\s+(.+)$", line)
        number = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if bullet or number:
            flush_paragraph()
            desired = "ul" if bullet else "ol"
            if list_type != desired:
                close_list()
                list_type = desired
                output.append(f"<{desired}>")
            output.append(f"<li>{markdown_inline((bullet or number).group(1))}</li>")
            continue
        if line.startswith("> "):
            flush_paragraph()
            close_list()
            output.append(f"<blockquote><p>{markdown_inline(line[2:])}</p></blockquote>")
            continue
        if not line.strip():
            flush_paragraph()
            close_list()
        else:
            paragraph.append(line)
    flush_paragraph()
    close_list()
    if in_code:
        output.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(output)


def package_metadata(directory: Path, run: dict[str, Any]) -> dict[str, Any]:
    brief = json_artifact(directory, run, "brief") or {}
    recipe = json_artifact(directory, run, "article-recipe") or {}
    title = str(brief.get("title") or "Untitled article")
    slug = slugify(str(brief.get("slug") or title), 80)
    date_value = str(brief.get("date") or dt.date.today().isoformat())
    description = str(brief.get("description") or brief.get("reader_job") or title)
    tags = brief.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    return {
        "title": title,
        "slug": slug,
        "description": description,
        "reader_job": brief.get("reader_job"),
        "date": date_value,
        "date_iso": date_value if "T" in date_value else f"{date_value}T12:00:00-05:00",
        "author": "Josiah Hunter",
        "tags": tags,
        "archetype": recipe.get("archetype"),
        "opening": (recipe.get("opening") or {}).get("strategy") if isinstance(recipe.get("opening"), dict) else None,
        "ending": (recipe.get("ending") or {}).get("strategy") if isinstance(recipe.get("ending"), dict) else None,
        "summary": (recipe.get("summary") or {}).get("policy") if isinstance(recipe.get("summary"), dict) else None,
        "narrative_person": recipe.get("narrative_person"),
        "workflow_version": run["workflow_version"],
        "voice_profile_version": load_json(SPEC_ROOT / "profiles" / "voice-profile.v1.json")["version"],
    }


def replace_marked(content: str, start: str, end: str, replacement: str) -> str:
    start_index = content.find(start)
    end_index = content.find(end)
    if start_index < 0 or end_index < 0 or end_index < start_index:
        raise FlowError(f"Required publication markers are missing: {start} / {end}")
    return content[:start_index] + start + "\n" + replacement.rstrip() + "\n" + content[end_index:]


def prepend_marked(content: str, start: str, end: str, replacement: str, *, unique_token: str, transform_existing: Any | None = None) -> str:
    start_index = content.find(start)
    end_index = content.find(end)
    if start_index < 0 or end_index < 0 or end_index < start_index:
        raise FlowError(f"Required publication markers are missing: {start} / {end}")
    if unique_token in content:
        raise FlowError(f"Publication surface already contains {unique_token}; use an explicit correction or lifecycle revision instead of duplicating the article")
    block_start = start_index + len(start)
    existing = content[block_start:end_index].strip()
    if transform_existing:
        existing = transform_existing(existing)
    combined = replacement.rstrip() + ("\n" + existing if existing else "")
    return content[:start_index] + start + "\n" + combined + "\n" + content[end_index:]


def demote_latest_cards(value: str) -> str:
    value = value.replace("article-card article-card--featured", "article-card")
    value = re.sub(r'\s*<span class="article-card__badge">Latest</span>', "", value)
    return value


def render_publication_files(directory: Path, run: dict[str, Any], package_root: Path, metadata: dict[str, Any]) -> list[Path]:
    article_path = artifact_path(directory, run, "article")
    if not article_path:
        raise FlowError("Approved article artifact is missing")
    target = load_json(SPEC_ROOT / "publication" / "theproductiveprompter.json")
    repository = publication_repo_root(required=True)
    template = (SPEC_ROOT / target["article_template"]).read_text(encoding="utf-8")
    body = markdown_to_html(article_path.read_text(encoding="utf-8"))
    canonical = target["canonical_url"].format(slug=metadata["slug"])
    words = len(re.findall(r"\b\w+\b", article_path.read_text(encoding="utf-8")))
    reading_minutes = max(1, round(words / 230))
    replacements = {
        "{{TITLE}}": html.escape(metadata["title"]),
        "{{DESCRIPTION}}": html.escape(metadata["description"], quote=True),
        "{{CANONICAL_URL}}": html.escape(canonical, quote=True),
        "{{DATE_ISO}}": html.escape(metadata["date_iso"], quote=True),
        "{{DATE_DISPLAY}}": html.escape(dt.date.fromisoformat(metadata["date"][:10]).strftime("%B %d, %Y").replace(" 0", " ")),
        "{{WORD_COUNT}}": str(words),
        "{{READING_MINUTES}}": str(reading_minutes),
        "{{TAGS_JSON}}": json.dumps(metadata["tags"]),
        "{{RECIPE_JSON}}": html.escape(json.dumps({
            "archetype": metadata.get("archetype"),
            "opening": metadata.get("opening"),
            "ending": metadata.get("ending"),
            "summary": metadata.get("summary"),
            "narrative_person": metadata.get("narrative_person"),
        }, separators=(",", ":")), quote=True),
        "{{ARTICLE_BODY}}": body,
        "{{ARTICLE_REVISION}}": sha256_path(article_path),
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    site_root = package_root / "site"
    article_output = site_root / "docs" / f"{metadata['slug']}.html"
    atomic_write(article_output, rendered.encode("utf-8"))
    card_blog = textwrap.dedent(f"""\
        <article class="article-card article-card--featured" data-article-flow-slug="{html.escape(metadata['slug'])}">
            <span class="article-card__badge">Latest</span>
            <div class="article-card__content">
                <div class="article-card__meta"><time class="article-card__date" datetime="{metadata['date']}">{dt.date.fromisoformat(metadata['date'][:10]).strftime('%B %d, %Y').replace(' 0', ' ')}</time><span class="article-card__separator">•</span><span class="article-card__reading-time">{reading_minutes} min read</span></div>
                <h3 class="article-card__title"><a href="{metadata['slug']}.html" class="article-card__link">{html.escape(metadata['title'])}</a></h3>
                <p class="article-card__summary">{html.escape(metadata['description'])}</p>
                <a href="{metadata['slug']}.html" class="article-card__cta">Read the article →</a>
            </div>
        </article>""")
    card_home = card_blog.replace(f'href="{metadata["slug"]}.html"', f'href="docs/{metadata["slug"]}.html"')
    for source_rel, replacement in (("docs/blog.html", card_blog), ("index.html", card_home)):
        source = repository / source_rel
        updated = prepend_marked(
            source.read_text(encoding="utf-8"),
            target["latest_card_start_marker"],
            target["latest_card_end_marker"],
            replacement,
            unique_token=f"{metadata['slug']}.html",
            transform_existing=demote_latest_cards,
        )
        output = site_root / source_rel
        atomic_write(output, updated.encode("utf-8"))
    feed_source = (repository / target["feed_file"]).read_text(encoding="utf-8")
    feed_item = textwrap.dedent(f"""\
        <item>
          <title>{html.escape(metadata['title'])}</title>
          <link>{canonical}</link>
          <guid isPermaLink="true">{canonical}</guid>
          <pubDate>{dt.datetime.fromisoformat(metadata['date_iso']).strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>
          <description>{html.escape(metadata['description'])}</description>
        </item>""")
    feed_updated = prepend_marked(feed_source, "<!-- ARTICLE_FLOW_FEED_START -->", "<!-- ARTICLE_FLOW_FEED_END -->", feed_item, unique_token=canonical)
    feed_updated = re.sub(
        r"<lastBuildDate>.*?</lastBuildDate>",
        f"<lastBuildDate>{dt.datetime.fromisoformat(metadata['date_iso']).strftime('%a, %d %b %Y %H:%M:%S %z')}</lastBuildDate>",
        feed_updated,
        count=1,
    )
    feed_output = site_root / target["feed_file"]
    atomic_write(feed_output, feed_updated.encode("utf-8"))
    sitemap_source = (repository / target["sitemap_file"]).read_text(encoding="utf-8")
    sitemap_item = f"  <url>\n    <loc>{canonical}</loc>\n    <lastmod>{metadata['date'][:10]}</lastmod>\n  </url>"
    sitemap_updated = prepend_marked(sitemap_source, "<!-- ARTICLE_FLOW_SITEMAP_START -->", "<!-- ARTICLE_FLOW_SITEMAP_END -->", sitemap_item, unique_token=canonical)
    sitemap_output = site_root / target["sitemap_file"]
    atomic_write(sitemap_output, sitemap_updated.encode("utf-8"))
    return sorted([path for path in site_root.rglob("*") if path.is_file()])


def package_revision(files: Iterable[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_path(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def validate_public_package(package_root: Path, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    public_root = package_root / "public"
    site_root = package_root / "site"
    repository = publication_repo_root()
    article_markdown = public_root / "article.md"
    article_html = site_root / "docs" / f"{metadata['slug']}.html"
    required = [
        article_markdown,
        public_root / "metadata.json",
        public_root / "references.json",
        public_root / "assets.json",
        article_html,
        site_root / "docs" / "blog.html",
        site_root / "index.html",
        site_root / "feed.xml",
        site_root / "sitemap.xml",
    ]
    for path in required:
        if not path.is_file() or path.stat().st_size == 0:
            findings.append({"criterion": "required_public_artifact", "path": str(path), "finding": "Missing or empty public artifact."})
    for path in [item for item in required if item.is_file()]:
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in (r"/mnt/[a-z]/Users/", r"[A-Z]:\\Users\\", r"/runs/AF-[0-9]{8}", r"\{\{[A-Z_]+\}\}"):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                findings.append({"criterion": "public_private_boundary", "path": str(path), "finding": f"Private/internal token leaked: {match.group(0)}"})
    for xml_name in ("feed.xml", "sitemap.xml"):
        path = site_root / xml_name
        if path.is_file():
            try:
                ET.parse(path)
            except ET.ParseError as exc:
                findings.append({"criterion": "valid_xml", "path": str(path), "finding": str(exc)})
    if article_html.is_file():
        text = article_html.read_text(encoding="utf-8")
        canonical = load_json(SPEC_ROOT / "publication" / "theproductiveprompter.json")["canonical_url"].format(slug=metadata["slug"])
        for name, required_text in {
            "title": metadata["title"],
            "canonical": f'<link rel="canonical" href="{canonical}">',
            "revision": '<meta name="article-flow-revision"',
            "structured_data": '"@type": "BlogPosting"',
        }.items():
            if required_text not in text:
                findings.append({"criterion": name, "path": str(article_html), "finding": f"Missing {name}."})
        for attribute, target in re.findall(r"\b(href|src)=\"([^\"]+)\"", text):
            if target.startswith(("http://", "https://", "mailto:", "#", "data:")):
                continue
            relative = target.split("#", 1)[0].split("?", 1)[0]
            if not relative:
                continue
            packaged_target = (article_html.parent / relative).resolve()
            try:
                packaged_target.relative_to(site_root.resolve())
            except ValueError:
                packaged_target = Path("/__outside_package__")
            repository_target = (repository / "docs" / relative).resolve() if repository else Path("/__article_flow_unavailable__")
            if not packaged_target.exists() and not repository_target.exists():
                findings.append({"criterion": "internal_link_or_asset", "path": str(article_html), "finding": f"Missing local {attribute} target: {target}"})
    return findings


def copy_private_run_archive(directory: Path, private_root: Path) -> dict[str, Any]:
    archive_root = private_root / "run"
    include = [directory / "run.json", directory / "events.jsonl", directory / "artifacts", directory / "tasks", directory / "receipts", directory / "approvals", directory / "publication"]
    for source in include:
        if not source.exists():
            continue
        destination = archive_root / source.relative_to(directory)
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    files = sorted(path for path in archive_root.rglob("*") if path.is_file())
    return {
        "run_id": directory.name,
        "files": [{"path": path.relative_to(private_root).as_posix(), "sha256": sha256_path(path), "byte_size": path.stat().st_size} for path in files],
        "artifact_count": len(files),
    }


def command_package(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    if run["state"] != "PACKAGE":
        raise FlowError(f"Package requires state PACKAGE, current state is {run['state']}")
    article_path = artifact_path(directory, run, "article")
    if not article_path:
        raise FlowError("Article artifact is missing")
    integrity = check_manifest("worktree")
    if not integrity["ok"]:
        raise FlowError("Protected workflow bytes changed; packaging is blocked until the reviewed manifest matches", EXIT_INTEGRITY, integrity)
    with run_lock(directory, run):
        package_root = directory / "package"
        if package_root.exists():
            for child in package_root.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        public_root = package_root / "public"
        private_root = package_root / "private"
        public_root.mkdir(parents=True, exist_ok=True)
        private_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(article_path, public_root / "article.md")
        metadata = package_metadata(directory, run)
        write_json(public_root / "metadata.json", metadata)
        claim_path = artifact_path(directory, run, "post-edit-claim-ledger") or artifact_path(directory, run, "verified-claim-ledger")
        references = {"sources": []}
        if claim_path:
            ledger = load_json(claim_path)
            references["sources"] = sorted({claim.get("source_url_or_local_id") for claim in ledger.get("claims", []) if claim.get("source_url_or_local_id")})
        write_json(public_root / "references.json", references)
        write_json(public_root / "assets.json", {"assets": []})
        site_files = render_publication_files(directory, run, package_root, metadata)
        private_index = copy_private_run_archive(directory, private_root)
        write_json(private_root / "archive-index.json", private_index)
        findings = validate_public_package(package_root, metadata)
        if findings:
            write_gate_receipt(directory, run, "G-PACKAGE-INTEGRITY", "REPAIR", findings, {"type": "code", "version": CONTROLLER_VERSION}, "PACKAGE")
            raise FlowError("Public package failed deterministic validation", EXIT_INTEGRITY, findings)
        all_files = [path for path in package_root.rglob("*") if path.is_file() and path.name != "package.json"]
        revision = package_revision(all_files, package_root)
        package = {
            "package_schema_version": "1.0.0",
            "run_id": run["run_id"],
            "workflow_version": run["workflow_version"],
            "package_revision": revision,
            "canonical_article_file": "public/article.md",
            "public_files": [{"path": path.relative_to(package_root).as_posix(), "sha256": sha256_path(path), "byte_size": path.stat().st_size} for path in sorted([*public_root.rglob("*"), *site_files]) if path.is_file()],
            "private_archive": "private/archive-index.json",
            "created_at": utc_now(),
        }
        package_path = package_root / "package.json"
        write_json(package_path, package)
        errors = validate_json_schema(package_path, "package.schema.json")
        if errors:
            raise FlowError("Controller generated an invalid package manifest", EXIT_INTEGRITY, errors)
        record_artifact(directory, run, package_path, "package", {"actor": "controller", "version": CONTROLLER_VERSION})
        write_gate_receipt(directory, run, "G-PACKAGE-INTEGRITY", "PASS", [], {"type": "code", "version": CONTROLLER_VERSION})
        transition(directory, run, "PUBLISH_APPROVAL", "controller", "Public/private package boundary and hashes validated")
    emit({"ok": True, "package_revision": revision, "package": str(package_path), "site_files": [path.relative_to(package_root).as_posix() for path in site_files], "state": run["state"], "next_command": ["article-flow", "publish", "--plan", run["run_id"]]}, args.json)
    return EXIT_OK


def command_publish_plan(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    if run["state"] != "PUBLISH_APPROVAL":
        raise FlowError(f"Publication planning requires PUBLISH_APPROVAL, current state is {run['state']}")
    package = load_json(directory / "package" / "package.json")
    target = load_json(SPEC_ROOT / "publication" / "theproductiveprompter.json")
    repository = publication_repo_root(required=True)
    plan_path = directory / "publication" / "plan.json"
    if plan_path.is_file():
        existing = load_json(plan_path)
        if existing.get("package_revision") == package.get("package_revision") and existing.get("base_commit") == str(git(["rev-parse", "HEAD"], cwd=repository)).strip() and existing.get("target") == target.get("target_id"):
            emit({"ok": True, "dry_run": True, "idempotent": True, "plan": str(plan_path), **existing, "approval_command": ["article-flow", "gate", run["run_id"], "G-PUBLISH-APPROVAL", "--outcome", "PASS"]}, args.json)
            return EXIT_OK
    site_root = directory / "package" / "site"
    changes = []
    for source in sorted(path for path in site_root.rglob("*") if path.is_file()):
        rel = source.relative_to(site_root).as_posix()
        destination = repository / rel
        changes.append({
            "path": rel,
            "current_sha256": sha256_path(destination) if destination.is_file() else None,
            "planned_sha256": sha256_path(source),
            "action": "modify" if destination.exists() else "add",
        })
    plan = {
        "plan_schema_version": "1.0.0",
        "run_id": run["run_id"],
        "target": target["target_id"],
        "base_commit": str(git(["rev-parse", "HEAD"], cwd=repository)).strip(),
        "package_revision": package["package_revision"],
        "changes": changes,
        "push_requires_explicit_flag": True,
        "created_at": utc_now(),
    }
    write_json(plan_path, plan)
    record_artifact(directory, run, plan_path, "publish-plan", {"actor": "controller", "version": CONTROLLER_VERSION})
    emit({"ok": True, "dry_run": True, "plan": str(plan_path), **plan, "approval_command": ["article-flow", "gate", run["run_id"], "G-PUBLISH-APPROVAL", "--outcome", "PASS"]}, args.json)
    return EXIT_OK


def command_publish_execute(args: argparse.Namespace) -> int:
    if os.environ.get("ARTICLE_FLOW_TEST_NO_PUBLISH") == "1":
        raise FlowError("Publication execution is disabled inside smoke/conformance tests", EXIT_APPROVAL)
    directory, run = load_run(args.run_id)
    if run["state"] != "PUBLISH":
        raise FlowError(f"Publication execution requires PUBLISH, current state is {run['state']}")
    approval_path = directory / "approvals" / f"{args.approval}.json"
    repository = publication_repo_root(required=True)
    if not approval_path.is_file():
        raise FlowError("Scoped publication approval not found", EXIT_APPROVAL)
    approval = load_json(approval_path)
    plan = load_json(directory / "publication" / "plan.json")
    if approval["package_revision"] != plan["package_revision"] or approval["target"] != plan["target"]:
        raise FlowError("Approval does not match this target and package revision", EXIT_APPROVAL)
    if approval.get("plan_sha256") != sha256_path(directory / "publication" / "plan.json"):
        raise FlowError("Publication plan changed after approval", EXIT_APPROVAL)
    if parse_time(approval["expires_at"]) <= dt.datetime.now(dt.timezone.utc):
        raise FlowError("Publication approval has expired", EXIT_APPROVAL)
    current_commit = str(git(["rev-parse", "HEAD"], cwd=repository)).strip()
    if current_commit != plan.get("base_commit"):
        raise FlowError("Repository HEAD changed after publication planning; create and approve a new plan", EXIT_INTEGRITY, {"planned": plan.get("base_commit"), "actual": current_commit})
    package = load_json(directory / "package" / "package.json")
    if package.get("package_revision") != plan.get("package_revision"):
        raise FlowError("Package revision changed after publication planning", EXIT_INTEGRITY)
    for item in package.get("public_files", []):
        path = directory / "package" / safe_relative(str(item["path"]))
        if not path.is_file() or sha256_path(path) != item.get("sha256"):
            raise FlowError(f"Packaged public file changed after approval: {item.get('path')}", EXIT_INTEGRITY)
    existing = directory / "receipts" / "publication.json"
    if existing.is_file():
        prior = load_json(existing)
        if prior.get("package_revision") == plan["package_revision"]:
            emit({"ok": True, "idempotent": True, "receipt": str(existing), "status": prior.get("status")}, args.json)
            return EXIT_OK
    status = str(git(["status", "--porcelain=v1", "-uall"], cwd=repository)).splitlines()
    if status:
        raise FlowError("Publication execution requires a clean approved checkout; use a separate clean worktree", EXIT_INTEGRITY, status)
    with run_lock(directory, run):
        site_root = directory / "package" / "site"
        changed_paths = []
        for change in plan["changes"]:
            rel = safe_relative(change["path"])
            source = site_root / rel
            destination = repository / rel
            current_hash = sha256_path(destination) if destination.is_file() else None
            if current_hash != change["current_sha256"]:
                raise FlowError(f"Publication target changed after planning: {rel}", EXIT_INTEGRITY)
            atomic_write(destination, source.read_bytes())
            changed_paths.append(rel.as_posix())
        git(["add", "--", *changed_paths], cwd=repository)
        commit = None
        pushed = False
        if args.commit:
            git(["commit", "-m", f"Publish {run['run_id']} ({plan['package_revision'][:12]})", "--", *changed_paths], cwd=repository)
            commit = str(git(["rev-parse", "HEAD"], cwd=repository)).strip()
        if args.push:
            if not args.commit:
                raise FlowError("--push requires --commit", EXIT_USAGE)
            target = load_json(SPEC_ROOT / "publication" / "theproductiveprompter.json")
            git(["push", target["deployment"]["remote"], f"HEAD:{target['publication_branch']}"], cwd=repository)
            pushed = True
        receipt = {
            "publication_receipt_schema_version": "1.0.0",
            "run_id": run["run_id"],
            "target": plan["target"],
            "package_revision": plan["package_revision"],
            "approval_id": approval["approval_id"],
            "expires_at": approval["expires_at"],
            "status": "PUSHED" if pushed else "APPLIED",
            "commit": commit,
            "url": None,
            "checks": [{"changed_paths": changed_paths}],
            "created_at": utc_now(),
        }
        write_json(existing, receipt)
        record_artifact(directory, run, existing, "publication", {"actor": "controller", "version": CONTROLLER_VERSION})
        append_event(directory, run, "PUBLICATION", "controller", {"status": receipt["status"], "commit": commit, "package_revision": plan["package_revision"]})
        write_gate_receipt(directory, run, "G-PUBLISH-REVISION", "PASS", [], {"type": "code", "version": CONTROLLER_VERSION})
        transition(directory, run, "LIVE_VERIFICATION", "controller", "Approved publication plan applied once")
    emit({"ok": True, "status": receipt["status"], "commit": commit, "pushed": pushed, "state": run["state"], "next_command": ["article-flow", "verify-live", run["run_id"]]}, args.json)
    return EXIT_OK


def fetch_url(url: str, timeout: int = 30) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": f"article-flow/{CONTROLLER_VERSION}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read(), {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(), {key.lower(): value for key, value in exc.headers.items()}
    except (urllib.error.URLError, TimeoutError):
        return 0, b"", {}


def command_verify_live(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    if run["state"] != "LIVE_VERIFICATION":
        raise FlowError(f"Live verification requires LIVE_VERIFICATION, current state is {run['state']}")
    package = load_json(directory / "package" / "package.json")
    metadata = load_json(directory / "package" / "public" / "metadata.json")
    target = load_json(SPEC_ROOT / "publication" / "theproductiveprompter.json")
    urls = {
        "article": target["canonical_url"].format(slug=metadata["slug"]),
        "blog": target["blog_url"],
        "homepage": target["homepage_url"],
        "feed": target["feed_url"],
        "sitemap": target["sitemap_url"],
    }
    expected_article = directory / "package" / "site" / "docs" / f"{metadata['slug']}.html"
    checks = []
    article_status, article_body, headers = fetch_url(urls["article"])
    checks.append({"name": "article_http", "ok": article_status == 200, "status": article_status})
    checks.append({"name": "article_revision", "ok": sha256_bytes(article_body) == sha256_path(expected_article), "expected_sha256": sha256_path(expected_article), "actual_sha256": sha256_bytes(article_body)})
    article_text = article_body.decode("utf-8", errors="replace")
    checks.append({"name": "canonical", "ok": f'<link rel="canonical" href="{urls["article"]}">' in article_text})
    checks.append({"name": "title", "ok": metadata["title"] in article_text})
    checks.append({"name": "open_graph_url", "ok": f'<meta property="og:url" content="{urls["article"]}">' in article_text})
    checks.append({"name": "structured_data", "ok": '"@type": "BlogPosting"' in article_text and f'"url": "{urls["article"]}"' in article_text})
    article_markdown = directory / "package" / "public" / "article.md"
    checks.append({"name": "embedded_article_revision", "ok": f'<meta name="article-flow-revision" content="{sha256_path(article_markdown)}">' in article_text})
    for surface in ("blog", "homepage", "feed", "sitemap"):
        status, body, _ = fetch_url(urls[surface])
        decoded = body.decode("utf-8", errors="replace")
        checks.append({"name": f"{surface}_http", "ok": status == 200, "status": status})
        checks.append({"name": f"{surface}_links_article", "ok": urls["article"] in decoded or f"{metadata['slug']}.html" in decoded})
    external_links = sorted(set(re.findall(r'href="(https?://[^"]+)"', article_text)) - set(urls.values()))
    link_results = []
    for link in external_links:
        status, _, _ = fetch_url(html.unescape(link), timeout=15)
        classification = "resolved" if 200 <= status < 400 else "inconclusive_access_control" if status in {401, 403, 429, 999} else "failed"
        link_results.append({"url": html.unescape(link), "status": status, "classification": classification})
        checks.append({"name": "external_link", "url": html.unescape(link), "status": status, "classification": classification, "ok": classification != "failed"})
    ok = all(item["ok"] for item in checks)
    receipt = {
        "publication_receipt_schema_version": "1.0.0",
        "run_id": run["run_id"],
        "target": target["target_id"],
        "package_revision": package["package_revision"],
        "approval_id": (json_artifact(directory, run, "publish-approval") or {}).get("approval_id"),
        "expires_at": None,
        "status": "VERIFIED" if ok else "FAILED",
        "commit": (json_artifact(directory, run, "publication") or {}).get("commit"),
        "url": urls["article"] if ok else None,
        "checks": checks,
        "accessibility_proved": ok,
        "represented_for_discovery": all(item["ok"] for item in checks if item["name"].startswith(("blog_", "homepage_", "feed_", "sitemap_"))),
        "indexing": "unknown_not_claimed",
        "response_headers": headers,
        "external_links": link_results,
        "created_at": utc_now(),
    }
    receipt_path = directory / "receipts" / "live-verification.json"
    write_json(receipt_path, receipt)
    record_artifact(directory, run, receipt_path, "live-verification", {"actor": "controller", "version": CONTROLLER_VERSION})
    append_event(directory, run, "VERIFICATION", "controller", {"ok": ok, "url": receipt["url"], "checks": checks})
    if not ok:
        write_gate_receipt(directory, run, "G-LIVE-REVISION", "RETRY", [
            {"criterion": item["name"], "artifact": urls["article"], "location": None, "finding": json.dumps(item), "repair_instruction": "Wait for deployment/cache propagation or return to the declared publication repair state."}
            for item in checks if not item["ok"]
        ], {"type": "code", "version": CONTROLLER_VERSION}, "PUBLISH")
        emit({"ok": False, "receipt": str(receipt_path), "checks": checks, "indexing": "unknown_not_claimed"}, args.json)
        return EXIT_FAILED
    write_gate_receipt(directory, run, "G-LIVE-REVISION", "PASS", [], {"type": "code", "version": CONTROLLER_VERSION})
    transition(directory, run, "COMPLETE", "controller", "Exact rendered revision and required discovery surfaces verified")
    emit({"ok": True, "url": receipt["url"], "receipt": str(receipt_path), "state": run["state"], "indexing": "unknown_not_claimed"}, args.json)
    return EXIT_OK


def windows_user_root() -> Path | None:
    override = os.environ.get("ARTICLE_FLOW_WINDOWS_USER_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    match = re.match(r"^/mnt/([a-zA-Z])/Users/([^/]+)", str(SPEC_ROOT))
    if match:
        return Path(f"/mnt/{match.group(1).lower()}/Users/{match.group(2)}")
    profile = os.environ.get("USERPROFILE")
    if profile:
        windows_match = re.match(r"^([a-zA-Z]):[\\/](.*)$", profile)
        if windows_match and os.name != "nt":
            candidate = Path(f"/mnt/{windows_match.group(1).lower()}/{windows_match.group(2).replace(chr(92), '/')}")
        else:
            candidate = Path(profile)
        if candidate.is_dir():
            return candidate.resolve()
    if os.name != "nt":
        candidate = Path("/mnt/c/Users") / Path.home().name
        if candidate.is_dir():
            return candidate.resolve()
    return None


def windows_path(path: Path) -> str:
    value = str(path.resolve())
    match = re.match(r"^/mnt/([a-zA-Z])/(.*)$", value)
    if match:
        return f"{match.group(1).upper()}:\\{match.group(2).replace('/', chr(92))}"
    return value


def record_linked_checkout(home: Path, *, host: str, development: bool, publication_repository: str) -> None:
    if not development:
        integrity = check_manifest("worktree")
        if not integrity["ok"]:
            raise FlowError("Cannot install an unmanifested workflow", EXIT_INTEGRITY, integrity)
    source_commit = release_source_commit()
    spec_root_value = windows_path(SPEC_ROOT) if host == "windows" else str(SPEC_ROOT.resolve())
    source_checkout_value = windows_path(REPO_ROOT) if host == "windows" else str(REPO_ROOT.resolve())
    current_path = home / "current.json"
    current = load_json(current_path) if current_path.is_file() else {}
    current_value = {
        "controller_version": CONTROLLER_VERSION,
        "workflow_version": workflow()["workflow_version"],
        "spec_root": spec_root_value,
        "source_checkout": source_checkout_value,
        "installed_at": current.get("installed_at") or utc_now(),
        "development": development,
        "linked_checkout": True,
        "publication_repo_root": publication_repository,
        "source_commit": source_commit,
    }
    if current != current_value:
        write_json(current_path, current_value)


def remove_managed_release_copies(home: Path) -> str | None:
    releases = home / "releases"
    if not releases.is_dir():
        return None
    for candidate in releases.iterdir():
        if not candidate.is_dir():
            raise FlowError(f"Refusing to remove an unexpected file from managed releases: {candidate}")
        spec = candidate / "Article-Spec-Pack-v1"
        metadata = spec / ".article-flow-release.json"
        recognized = metadata.is_file()
        if not recognized and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", candidate.name):
            manifest_path = spec / "manifest.json"
            script_path = spec / "scripts" / "article_flow.py"
            if manifest_path.is_file() and script_path.is_file():
                manifest = load_json(manifest_path)
                version_match = re.search(r'^CONTROLLER_VERSION\s*=\s*"([^"]+)"', script_path.read_text(encoding="utf-8", errors="ignore"), re.MULTILINE)
                recognized = bool(
                    manifest.get("generator_name_and_version") == f"article-flow {candidate.name}"
                    and version_match
                    and version_match.group(1) == candidate.name
                )
        if not recognized:
            raise FlowError(f"Refusing to remove an unrecognized release directory: {candidate}")
    shutil.rmtree(releases)
    return str(releases)


def wsl_legacy_skill_targets() -> list[tuple[str, Path]]:
    return [
        ("wsl-agents", Path.home() / ".agents" / "skills" / "start-article"),
        ("wsl-claude", Path.home() / ".claude" / "skills" / "start-article"),
    ]


def windows_legacy_skill_targets(user_root: Path) -> list[tuple[str, Path]]:
    return [
        ("windows-agents", user_root / ".agents" / "skills" / "start-article"),
        ("windows-codex", user_root / ".codex" / "skills" / "start-article"),
        ("windows-claude", user_root / ".claude" / "skills" / "start-article"),
    ]


def require_managed_legacy_skill_adapters(targets: Sequence[tuple[str, Path]]) -> None:
    for _, target in targets:
        if not (target.exists() or target.is_symlink()):
            continue
        if not target.is_dir() or not (target / ".article-flow-adapter.json").is_file():
            raise FlowError(f"Refusing to remove an unmanaged legacy skill path: {target}")


def retire_managed_skill_adapters(targets: Sequence[tuple[str, Path]], home: Path) -> list[dict[str, str]]:
    """Move controller-owned legacy skills out of host discovery paths.

    The sentinel proves that Article Flow created the directory. An unmarked
    directory is preserved and blocks installation rather than being deleted.
    """
    retired: list[dict[str, str]] = []
    stamp = slugify(utc_now(), 40)
    retirement_root = home / "retired-skill-adapters"
    for label, target in targets:
        if not (target.exists() or target.is_symlink()):
            continue
        sentinel = target / ".article-flow-adapter.json"
        if not target.is_dir() or not sentinel.is_file():
            raise FlowError(f"Refusing to remove an unmanaged legacy skill path: {target}")
        retirement_root.mkdir(parents=True, exist_ok=True)
        destination = retirement_root / f"{stamp}-{label}"
        suffix = 2
        while destination.exists():
            destination = retirement_root / f"{stamp}-{label}-{suffix}"
            suffix += 1
        shutil.move(str(target), str(destination))
        retired.append({"from": str(target), "to": str(destination)})
    return retired


def remove_managed_launcher(path: Path) -> bool:
    if not path.is_file():
        return False
    if "article-flow managed launcher" not in path.read_text(encoding="utf-8", errors="ignore"):
        raise FlowError(f"Refusing to remove an unmanaged launcher: {path}")
    path.unlink()
    return True


def command_install(args: argparse.Namespace) -> int:
    hosts = {item.strip().lower() for item in args.hosts.split(",") if item.strip()}
    invalid = hosts - {"windows", "wsl"}
    if invalid:
        raise FlowError(f"Unsupported hosts: {', '.join(sorted(invalid))}", EXIT_USAGE)
    installed: list[dict[str, Any]] = []
    if "wsl" in hosts:
        require_managed_legacy_skill_adapters(wsl_legacy_skill_targets())
        home = runtime_home() if os.environ.get("ARTICLE_FLOW_HOME") else Path.home() / ".local" / "share" / "article-flow"
        record_linked_checkout(home.resolve(), host="wsl", development=args.development, publication_repository=str(publication_repo_root() or REPO_ROOT))
        wrapper = Path.home() / ".local" / "bin" / "article-flow"
        wrapper.parent.mkdir(parents=True, exist_ok=True)
        wrapper_text = f"#!/usr/bin/env sh\n# article-flow managed launcher {CONTROLLER_VERSION}\nexport ARTICLE_FLOW_HOME='{home.resolve()}'\nexport ARTICLE_FLOW_REPO_ROOT='{REPO_ROOT.resolve()}'\nexec python3 '{SCRIPT_PATH.resolve()}' \"$@\"\n"
        write_if_changed(wrapper, wrapper_text.encode("utf-8"), mode=0o755)
        retired = retire_managed_skill_adapters(wsl_legacy_skill_targets(), home.resolve())
        removed_releases = remove_managed_release_copies(home.resolve())
        installed.append({"host": "wsl", "home": str(home.resolve()), "command": str(wrapper), "source_checkout": str(REPO_ROOT.resolve()), "retired_skill_adapters": retired, "removed_release_copies": removed_releases})
    if "windows" in hosts:
        user_root = windows_user_root()
        if not user_root:
            raise FlowError("Cannot resolve the Windows user profile; set ARTICLE_FLOW_WINDOWS_USER_ROOT")
        require_managed_legacy_skill_adapters(windows_legacy_skill_targets(user_root))
        bin_dir = user_root / "AppData" / "Local" / "Microsoft" / "WindowsApps"
        legacy_launchers = (
            user_root / ".local" / "bin" / "article-flow.cmd",
            user_root / ".local" / "bin" / "article-flow.ps1",
            bin_dir / "article-flow.ps1",
        )
        for legacy in legacy_launchers:
            if legacy.is_file() and "article-flow managed launcher" not in legacy.read_text(encoding="utf-8", errors="ignore"):
                raise FlowError(f"Refusing to remove an unmanaged launcher: {legacy}")
        home = user_root / ".article-flow"
        record_linked_checkout(home, host="windows", development=args.development, publication_repository=windows_path(publication_repo_root() or REPO_ROOT))
        python_candidates = [
            user_root / "AppData" / "Local" / "Programs" / "Python" / "Python312" / "python.exe",
            user_root / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "python.exe",
        ]
        python_exe = next((item for item in python_candidates if item.exists()), None)
        if not python_exe:
            raise FlowError("Native Windows Python was not found")
        bin_dir.mkdir(parents=True, exist_ok=True)
        cmd_text = f"@echo off\r\nrem article-flow managed launcher {CONTROLLER_VERSION}\r\nset \"ARTICLE_FLOW_HOME={windows_path(home)}\"\r\nset \"ARTICLE_FLOW_REPO_ROOT={windows_path(REPO_ROOT)}\"\r\n\"{windows_path(python_exe)}\" \"{windows_path(SCRIPT_PATH)}\" %*\r\n"
        command = bin_dir / "article-flow.cmd"
        if command.is_file() and "article-flow managed launcher" not in command.read_text(encoding="utf-8", errors="ignore"):
            raise FlowError(f"Refusing to overwrite an unmanaged launcher: {command}")
        write_if_changed(command, cmd_text.encode("utf-8"))
        retired_launchers = []
        for legacy in legacy_launchers:
            if remove_managed_launcher(legacy):
                retired_launchers.append(str(legacy))
        retired = retire_managed_skill_adapters(windows_legacy_skill_targets(user_root), home)
        removed_releases = remove_managed_release_copies(home)
        installed.append({"host": "windows", "home": str(home), "command": str(command), "source_checkout": windows_path(REPO_ROOT), "retired_launchers": retired_launchers, "retired_skill_adapters": retired, "removed_release_copies": removed_releases, "python": str(python_exe)})
    emit({"ok": True, "controller_version": CONTROLLER_VERSION, "workflow_version": workflow()["workflow_version"], "installed": installed, "idempotent": True}, args.json)
    return EXIT_OK


def global_command_targets() -> list[tuple[str, Path]]:
    targets: list[tuple[str, Path]] = []
    if os.name != "nt":
        targets.append(("wsl", Path.home() / ".local" / "bin" / "article-flow"))
    user_root = windows_user_root()
    if user_root:
        targets.append(("windows", user_root / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "article-flow.cmd"))
    return targets


def global_command_health() -> dict[str, Any]:
    checks = []
    for host, path in global_command_targets():
        content = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
        ok = path.is_file() and f"article-flow managed launcher {CONTROLLER_VERSION}" in content
        checks.append({
            "host": host,
            "path": str(path),
            "ok": ok,
            "controller_version": CONTROLLER_VERSION if ok else None,
            "repair_command": None if ok else "article-flow install --hosts windows,wsl",
        })
    legacy = []
    if os.name != "nt":
        legacy.extend(wsl_legacy_skill_targets())
    user_root = windows_user_root()
    if user_root:
        legacy.extend(windows_legacy_skill_targets(user_root))
    for label, path in legacy:
        absent = not (path.exists() or path.is_symlink())
        checks.append({"host": label, "path": str(path), "kind": "retired_skill_path", "ok": absent, "repair_command": None if absent else "article-flow install --hosts windows,wsl"})
    return {"ok": bool(checks) and all(item["ok"] for item in checks), "checks": checks}


def command_providers_list(args: argparse.Namespace) -> int:
    registry = capability_registry()
    providers = []
    for provider in registry.get("providers", []):
        providers.append({
            "provider_id": provider.get("provider_id"),
            "kind": provider.get("kind"),
            "enabled": provider.get("enabled", False),
            "credential_environment_variable": provider.get("credential_environment_variable"),
            "credential_present": bool(os.environ.get(str(provider.get("credential_environment_variable")))) if provider.get("credential_environment_variable") else None,
            "endpoint_present": resolved_provider_endpoint(provider) is not None or provider.get("kind") in {"agent-hosted", "command"},
            "models": [{key: model.get(key) for key in ("model_id", "version", "capabilities", "stages", "canary_status")} for model in provider.get("models", []) if isinstance(model, dict)],
        })
    emit({"ok": True, "configuration_path": registry["configuration_path"], "providers": providers}, args.json)
    return EXIT_OK


def command_route(args: argparse.Namespace) -> int:
    payload = route_candidates(args.stage)
    emit(payload, args.json)
    return EXIT_OK if payload.get("chosen") else EXIT_FAILED


def runtime_evaluation_files() -> list[Path]:
    root = runtime_home() / "evaluations"
    return sorted(root.glob("*.json")) if root.is_dir() else []


def command_evaluation_record(args: argparse.Namespace) -> int:
    source = Path(args.file).expanduser().resolve()
    if not source.is_file():
        raise FlowError(f"Evaluation file does not exist: {source}")
    errors = validate_json_schema(source, "evaluation.schema.json")
    if errors:
        raise FlowError("Evaluation does not conform to evaluation.schema.json", EXIT_INTEGRITY, errors)
    value = load_json(source)
    if value.get("workflow_version") != workflow()["workflow_version"]:
        raise FlowError("Evaluation workflow version does not match the installed workflow", EXIT_INTEGRITY)
    root = runtime_home() / "evaluations"
    root.mkdir(parents=True, exist_ok=True)
    existing_values = []
    for path in runtime_evaluation_files():
        try:
            existing_values.append(load_json(path))
        except FlowError:
            continue
    if value.get("promotion_status") == "promoted":
        promotion = load_json(SPEC_ROOT / "evaluations" / "evaluation-registry.json")["promotion_policy"]
        if promotion.get("require_human_calibration") and not value.get("human_calibration"):
            raise FlowError("Promoted evaluation requires recorded human calibration")
        if promotion.get("require_order_reversal") and not value.get("grader", {}).get("order_reversal_passed"):
            raise FlowError("Promoted evaluation requires a passed order-reversal check")
        if promotion.get("require_provider_version_canary") and value.get("canary", {}).get("status") != "passed":
            raise FlowError("Promoted evaluation requires a passed provider/version canary")
        comparable = {
            str(item.get("fixture_id"))
            for item in [*existing_values, value]
            if item.get("provider") == value.get("provider") and item.get("model") == value.get("model") and item.get("stage") == value.get("stage") and item.get("human_calibration")
        }
        minimum = int(promotion.get("minimum_fixture_count_per_stage", 3))
        if len(comparable) < minimum:
            raise FlowError(f"Promotion requires {minimum} distinct calibrated fixtures for this stage; found {len(comparable)}")
    destination = root / f"{slugify(str(value['evaluation_id']), 100)}.json"
    if destination.is_file() and sha256_path(destination) == sha256_path(source):
        emit({"ok": True, "idempotent": True, "path": str(destination)}, args.json)
        return EXIT_OK
    write_json(destination, value)
    emit({"ok": True, "path": str(destination), "promotion_status": value.get("promotion_status", "candidate"), "routing_changed": value.get("promotion_status") == "promoted"}, args.json)
    return EXIT_OK


def command_evaluation_summarize(args: argparse.Namespace) -> int:
    groups: dict[str, dict[str, Any]] = {}
    invalid = []
    for path in runtime_evaluation_files():
        errors = validate_json_schema(path, "evaluation.schema.json")
        if errors:
            invalid.append({"path": str(path), "errors": errors})
            continue
        value = load_json(path)
        key = f"{value['provider']}:{value['model']}:{value['stage']}"
        group = groups.setdefault(key, {"provider": value["provider"], "model": value["model"], "stage": value["stage"], "fixtures": set(), "promoted": 0, "human_calibrated": 0, "scores": []})
        group["fixtures"].add(value["fixture_id"])
        group["promoted"] += int(value.get("promotion_status") == "promoted")
        group["human_calibrated"] += int(bool(value.get("human_calibration")))
        metrics = value.get("metrics", {})
        if metrics:
            group["scores"].append(float(metrics.get("overall", sum(metrics.values()) / len(metrics))))
    result = []
    for key in sorted(groups):
        group = groups[key]
        result.append({
            "provider": group["provider"],
            "model": group["model"],
            "stage": group["stage"],
            "fixture_count": len(group["fixtures"]),
            "promoted_count": group["promoted"],
            "human_calibrated_count": group["human_calibrated"],
            "mean_score": sum(group["scores"]) / len(group["scores"]) if group["scores"] else None,
        })
    emit({"ok": not invalid, "groups": result, "invalid": invalid, "routing_status": "calibrated" if promoted_evaluation_scores() else "uncalibrated_active_host_default"}, args.json)
    return EXIT_OK if not invalid else EXIT_FAILED


def dirty_classification() -> dict[str, Any]:
    if not (REPO_ROOT / ".git").exists():
        return {"protected_changes": [], "unrelated_changes": [], "protected_unstaged": [], "protected_staged": [], "clean": False, "repository_available": False}
    protected = {spec_repo_path(item["path"]) if item["scope"] == "spec" else item["path"] for item in protected_entries("worktree")}
    raw = str(git(["status", "--porcelain=v1", "-uall"])).splitlines()
    protected_changes = []
    unrelated_changes = []
    for line in raw:
        path = line[3:].split(" -> ")[-1]
        (protected_changes if path in protected else unrelated_changes).append(line)
    unstaged_paths = set(str(git(["diff", "--name-only"])).splitlines())
    staged_paths = set(str(git(["diff", "--cached", "--name-only"])).splitlines())
    return {
        "protected_changes": protected_changes,
        "unrelated_changes": unrelated_changes,
        "protected_unstaged": sorted(protected & unstaged_paths),
        "protected_staged": sorted(protected & staged_paths),
        "clean": not raw,
        "repository_available": True,
    }


def normative_lint() -> dict[str, Any]:
    registry = load_json(SPEC_ROOT / "workflow" / "document-registry.json")
    current_workflow = workflow()
    defaults = load_json(SPEC_ROOT / "workflow" / "article-recipe.defaults.json")
    current_policy = policy()
    publication = load_json(SPEC_ROOT / "publication" / "theproductiveprompter.json")
    issues: list[dict[str, Any]] = []

    authoritative = registry.get("authoritative_controls", [])
    non_authoritative = [item.get("path") for item in registry.get("non_authoritative_documents", [])]
    for path in authoritative:
        if not (SPEC_ROOT / safe_relative(str(path))).is_file():
            issues.append({"criterion": "authority_exists", "path": path, "finding": "Authoritative control is missing."})
    overlap = sorted(set(authoritative) & set(non_authoritative))
    if overlap:
        issues.append({"criterion": "authority_disjoint", "paths": overlap, "finding": "A document is both authoritative and non-authoritative."})

    expected_precedence = ["run_overrides", "approved_article_recipe", "workflow_schema", "house_policy", "examples"]
    if current_workflow.get("precedence") != expected_precedence:
        issues.append({"criterion": "precedence", "finding": "The controlling precedence chain differs from the published contract."})
    rules = current_workflow.get("rules", [])
    rule_ids = [item.get("id") for item in rules]
    if len(rule_ids) != len(set(rule_ids)):
        issues.append({"criterion": "stable_rule_ids", "finding": "Normative rule identifiers are not unique."})
    required_rules = {
        "AF-PERSON-001", "AF-LENGTH-001", "AF-SHAPE-001", "AF-CITATION-001", "AF-PACKAGE-001",
        "AF-REPAIR-001", "AF-END-001", "AF-MATURITY-001", "AF-EVIDENCE-001", "AF-NATURALIZE-001",
        "AF-VOICE-001", "AF-ROUTING-001", "AF-PUBLISH-001", "AF-INDEXING-001", "AF-EVAL-001", "AF-LIFECYCLE-001",
    }
    missing_rules = sorted(required_rules - set(rule_ids))
    if missing_rules:
        issues.append({"criterion": "conflict_resolutions", "missing_rule_ids": missing_rules, "finding": "A required conflict resolution has no stable normative rule."})

    default_pairs = [
        ("narrative_person", defaults.get("narrative_person"), current_policy.get("editorial_defaults", {}).get("narrative_person")),
        ("citation_mode", defaults.get("citation_mode"), current_policy.get("editorial_defaults", {}).get("citation_mode")),
        ("summary_policy", defaults.get("summary", {}).get("policy"), current_policy.get("editorial_defaults", {}).get("summary_policy")),
        ("activation_header", defaults.get("components", {}).get("activation_header"), current_policy.get("editorial_defaults", {}).get("activation_header")),
        ("workflow_count", defaults.get("components", {}).get("workflow_count"), current_policy.get("editorial_defaults", {}).get("components", {}).get("workflow_count")),
    ]
    for field, recipe_value, policy_value in default_pairs:
        if recipe_value != policy_value:
            issues.append({"criterion": "default_alignment", "field": field, "recipe": recipe_value, "house_policy": policy_value, "finding": "Recipe and house-policy defaults disagree."})
    if defaults.get("length", {}).get("mode") != "auto" or current_policy.get("editorial_defaults", {}).get("length", {}).get("mode") != "auto":
        issues.append({"criterion": "length_resolution", "finding": "Length defaults must remain content-complete auto guidance rather than a universal pass/fail band."})
    if publication.get("canonical_article_file") != "docs/{slug}.html":
        issues.append({"criterion": "public_article_identity", "finding": "The publication target has no single canonical public filename."})

    return {
        "ok": not issues,
        "authority": "workflow/workflow.json",
        "precedence": current_workflow.get("precedence"),
        "normative_rule_count": len(rule_ids),
        "conflicting_normative_statement_count": len(issues),
        "issues": issues,
    }


def schema_health() -> dict[str, Any]:
    checks = []
    instances = [
        (WORKFLOW_PATH, "workflow.schema.json"),
        (POLICY_PATH, "house-policy.schema.json"),
        (SPEC_ROOT / "workflow" / "article-recipe.defaults.json", "article-recipe.schema.json"),
        (SPEC_ROOT / "workflow" / "document-registry.json", "document-registry.schema.json"),
        (PROTECTED_PATHS_PATH, "protected-paths.schema.json"),
        (SPEC_ROOT / "profiles" / "voice-profile.v1.json", "voice-profile.schema.json"),
        (SPEC_ROOT / "evaluations" / "provider-config.example.json", "provider-config.schema.json"),
    ]
    for instance, schema in instances:
        errors = validate_json_schema(instance, schema)
        checks.append({"instance": instance.relative_to(SPEC_ROOT).as_posix(), "schema": schema, "ok": not errors, "errors": errors})
    schemas, _ = schema_bundle(str(SPEC_ROOT))
    for path in sorted((SPEC_ROOT / "schemas").glob("*.json")):
        schema = schemas[path.name]
        errors = schema_definition_errors(schema, schemas, path.name)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            errors.append(f"{path.name}: $schema must declare JSON Schema Draft 2020-12")
        checks.append({"schema": path.name, "ok": not errors, "errors": errors})
    docs = subprocess.run([sys.executable, str(SPEC_ROOT / "scripts" / "render_workflow_docs.py"), "--check"], cwd=SPEC_ROOT, capture_output=True, text=True)
    checks.append({"generated_docs": "1-Master/Article-Workflow-v2.md", "ok": docs.returncode == 0, "errors": [docs.stderr.strip()] if docs.returncode else []})
    lint = normative_lint()
    checks.append({"normative_lint": "workflow precedence and resolved conflicts", "ok": lint["ok"], "errors": lint["issues"], "result": lint})
    return {"ok": all(item["ok"] for item in checks), "checks": checks}


def conformance_health(home: Path | None = None, expected_host: str | None = None) -> dict[str, Any]:
    selected_home = home or runtime_home()
    path = selected_home / "conformance" / "latest.json"
    if not path.is_file():
        return {"ok": False, "receipt": str(path), "reason": "conformance has not been run for this installation"}
    try:
        receipt = load_json(path)
    except FlowError as exc:
        return {"ok": False, "receipt": str(path), "reason": str(exc)}
    current_path = selected_home / "current.json"
    installed = load_json(current_path) if current_path.is_file() else {}
    current_commit = installed.get("source_commit") or (str(git(["rev-parse", "HEAD"], cwd=REPO_ROOT)).strip() if (REPO_ROOT / ".git").exists() else None)
    ok = bool(
        receipt.get("ok")
        and receipt.get("commit") == current_commit
        and receipt.get("controller_version") == CONTROLLER_VERSION
        and receipt.get("workflow_version") == workflow()["workflow_version"]
        and receipt.get("smoke_tests_publish") is False
        and (expected_host is None or receipt.get("host_kind") == expected_host)
    )
    return {"ok": ok, "receipt": str(path), "record": receipt, "reason": None if ok else "receipt does not prove this exact commit/controller/workflow"}


def host_conformance_health() -> dict[str, Any]:
    checks = [
        {"host": "wsl", **conformance_health(Path.home() / ".local" / "share" / "article-flow", "wsl")},
    ]
    windows_root = windows_user_root()
    if windows_root:
        checks.append({"host": "native-windows", **conformance_health(windows_root / ".article-flow", "native-windows")})
    else:
        checks.append({"host": "native-windows", "ok": False, "receipt": None, "reason": "Windows user root is unresolved"})
    return {"ok": all(item["ok"] for item in checks), "checks": checks}


def installation_health() -> dict[str, Any]:
    checks = []
    wsl_current = (Path.home() / ".local" / "share" / "article-flow" / "current.json")
    windows_root = windows_user_root()
    candidates = [("wsl", wsl_current)]
    if windows_root:
        candidates.append(("windows", windows_root / ".article-flow" / "current.json"))
    for host, path in candidates:
        record = load_json(path) if path.is_file() else {}
        ok = bool(
            record.get("controller_version") == CONTROLLER_VERSION
            and record.get("workflow_version") == workflow()["workflow_version"]
            and record.get("development") is False
            and record.get("linked_checkout") is True
            and record.get("source_commit") == release_source_commit()
        )
        checks.append({"host": host, "path": str(path), "ok": ok, "controller_version": record.get("controller_version"), "workflow_version": record.get("workflow_version"), "development": record.get("development"), "linked_checkout": record.get("linked_checkout"), "source_commit": record.get("source_commit")})
    return {"ok": bool(checks) and all(item["ok"] for item in checks), "checks": checks}


def doctor_payload(scope: str) -> dict[str, Any]:
    launcher = {
        "ok": SCRIPT_PATH.is_file() and SPEC_ROOT.is_dir() and WORKFLOW_PATH.is_file(),
        "controller_version": CONTROLLER_VERSION,
        "spec_root": str(SPEC_ROOT),
        "runtime_home": str(runtime_home()),
    }
    manifest_integrity = check_manifest("worktree", allow_unavailable_repository=True)
    schemas = schema_health()
    integrity = {"ok": manifest_integrity["ok"] and schemas["ok"], "manifest": manifest_integrity, "schemas_and_documents": schemas}
    commands = global_command_health()
    routes = route_candidates("RESEARCH_PLAN")
    dirty = dirty_classification()
    authoring = {
        "ok": launcher["ok"] and integrity["ok"] and routes.get("chosen") is not None and not dirty["protected_unstaged"],
        "spec_integrity": integrity,
        "route_available": routes.get("chosen") is not None,
        "protected_worktree_state": "VERIFIED" if integrity["ok"] and not dirty["protected_unstaged"] else "UNVERIFIED",
        "dirty_state": dirty,
    }
    head_integrity = check_manifest("head")
    installations = installation_health()
    conformance = host_conformance_health()
    release = {
        "ok": launcher["ok"] and head_integrity["ok"] and schemas["ok"] and dirty["clean"] and commands["ok"] and installations["ok"] and conformance["ok"],
        "head_integrity": head_integrity,
        "schemas_and_documents": schemas,
        "clean_checkout": dirty["clean"],
        "global_command_discovery": commands,
        "installations": installations,
        "host_conformance": conformance,
        "publication_target_present": (SPEC_ROOT / "publication" / "theproductiveprompter.json").is_file(),
    }
    scopes = {"launcher_access": launcher, "spec_integrity": integrity, "global_command_discovery": commands, "authoring_ready": authoring, "release_ready": release}
    requested = {
        "launcher": launcher["ok"],
        "authoring": authoring["ok"],
        "release": release["ok"],
        "all": launcher["ok"] and authoring["ok"] and release["ok"],
    }[scope]
    return {"ok": requested, "requested_scope": scope, "scopes": scopes}


def command_doctor(args: argparse.Namespace) -> int:
    scope = "all" if args.all else args.scope
    payload = doctor_payload(scope)
    emit(payload, args.json)
    return EXIT_OK if payload["ok"] else EXIT_FAILED


def command_manifest_build(args: argparse.Namespace) -> int:
    if not args.from_index:
        raise FlowError("Manifest builds are allowed only from the reviewed Git index", EXIT_USAGE)
    payload = manifest_payload_from_index()
    errors = validate_instance_schema(payload, "manifest.schema.json")
    if errors:
        raise FlowError("Generated manifest does not conform to manifest.schema.json", EXIT_INTEGRITY, errors)
    write_json(MANIFEST_PATH, payload)
    emit({"ok": True, "manifest": str(MANIFEST_PATH), "protected_file_count": len(payload["files"]), "generated_from": "index", "next": "Stage manifest.json explicitly, then run article-flow manifest check --against-index."}, args.json)
    return EXIT_OK


def command_manifest_check(args: argparse.Namespace) -> int:
    source = "worktree" if args.against_worktree else "index" if args.against_index else "head"
    payload = check_manifest(source)
    emit(payload, args.json)
    return EXIT_OK if payload["ok"] else EXIT_INTEGRITY


def command_manifest_explain(args: argparse.Namespace) -> int:
    scope = "repository" if args.path.startswith("repo:") else "spec"
    raw_path = args.path[5:] if scope == "repository" else args.path
    rel = safe_relative(raw_path).as_posix()
    entry = next((item for item in protected_entries("worktree") if item["path"] == rel and item["scope"] == scope), None)
    manifest = load_json(MANIFEST_PATH) if MANIFEST_PATH.is_file() else {"files": []}
    recorded = next((item for item in manifest.get("files", []) if item.get("path") == rel and item.get("scope", "spec") == scope), None)
    target = (SPEC_ROOT if scope == "spec" else (publication_repo_root() or REPO_ROOT)) / rel
    payload = {"scope": scope, "path": rel, "protected": entry is not None, "registration": entry, "manifest_entry": recorded, "worktree_sha256": sha256_path(target) if target.is_file() else None}
    emit(payload, args.json)
    return EXIT_OK if entry else EXIT_FAILED


def command_conformance(args: argparse.Namespace) -> int:
    tests_root = SPEC_ROOT / "tests"
    tests_path = tests_root / "test_article_flow.py"
    if not tests_path.is_file():
        raise FlowError("Conformance suite is missing")
    command = [sys.executable, "-m", "unittest", "discover", "-s", str(tests_root), "-p", "test_*.py", "-v"]
    environment = os.environ.copy()
    environment["ARTICLE_FLOW_TEST_NO_PUBLISH"] = "1"
    repository = publication_repo_root()
    if repository:
        environment["ARTICLE_FLOW_REPO_ROOT"] = str(repository)
    result = subprocess.run(command, cwd=SPEC_ROOT, capture_output=True, text=True, env=environment)
    launcher_smoke = installed_launcher_smoke()
    test_files = sorted(path for path in tests_root.rglob("test_*.py") if path.is_file())
    receipt = {
        "conformance_receipt_schema_version": "1.1.0",
        "ok": result.returncode == 0 and launcher_smoke["ok"],
        "host_kind": "native-windows" if os.name == "nt" else "wsl",
        "platform": sys.platform,
        "python_executable": sys.executable,
        "controller_version": CONTROLLER_VERSION,
        "workflow_version": workflow()["workflow_version"],
        "commit": release_source_commit(),
        "test_suite_revision": package_revision([SCRIPT_PATH, *test_files], SPEC_ROOT),
        "test_count_files": len(test_files),
        "smoke_tests_publish": False,
        "launcher_smoke": launcher_smoke,
        "created_at": utc_now(),
    }
    errors = validate_instance_schema(receipt, "conformance-receipt.schema.json")
    if errors:
        raise FlowError("Controller generated an invalid conformance receipt", EXIT_INTEGRITY, errors)
    conformance_root = runtime_home() / "conformance"
    receipt_path = conformance_root / "latest.json"
    history_root = conformance_root / "history"
    history_root.mkdir(parents=True, exist_ok=True)
    if receipt_path.is_file():
        prior = load_json(receipt_path)
        prior_stamp = slugify(str(prior.get("created_at", "unknown")), 40)
        prior_path = history_root / f"{prior_stamp}-{prior.get('controller_version', 'unknown')}-{prior.get('host_kind', 'unknown')}.json"
        if not prior_path.is_file():
            write_json(prior_path, prior)
    stamp = slugify(receipt["created_at"], 40)
    history_path = history_root / f"{stamp}-{CONTROLLER_VERSION}-{receipt['host_kind']}.json"
    write_json(history_path, receipt)
    write_json(receipt_path, receipt)
    payload = {**receipt, "receipt": str(receipt_path), "command": command, "stdout": result.stdout, "stderr": result.stderr}
    emit(payload, args.json)
    return EXIT_OK if receipt["ok"] else EXIT_FAILED


def installed_launcher_smoke() -> dict[str, Any]:
    """Exercise the user-facing launcher from an unrelated directory.

    This runs after the suite so a test that accidentally rewrites the launcher
    cannot leave behind a green conformance receipt.
    """
    if os.name == "nt":
        user_root = windows_user_root()
        launcher = user_root / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "article-flow.cmd" if user_root else Path("article-flow.cmd")
        command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(launcher), "context", "--json"]
        bootstrap_command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(launcher)]
    else:
        launcher = Path.home() / ".local" / "bin" / "article-flow"
        command = [str(launcher), "context", "--json"]
        bootstrap_command = [str(launcher)]
    with tempfile.TemporaryDirectory() as unrelated:
        try:
            result = subprocess.run(command, cwd=unrelated, capture_output=True, text=True, timeout=30)
            bootstrap_result = subprocess.run(bootstrap_command, cwd=unrelated, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            return {
                "ok": False,
                "launcher": str(launcher),
                "return_code": -1,
                "controller_version": "",
                "workflow_version": "",
                "spec_root_match": False,
                "runtime_home_match": False,
                "bootstrap_ok": False,
                "unrelated_cwd": True,
                "error": str(exc),
            }
    try:
        context = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        context = {}
    try:
        bootstrap = json.loads(bootstrap_result.stdout)
    except (json.JSONDecodeError, TypeError):
        bootstrap = {}
    try:
        spec_root_match = Path(str(context.get("spec_root", ""))).resolve() == SPEC_ROOT.resolve()
        runtime_home_match = Path(str(context.get("runtime_home", ""))).resolve() == runtime_home().resolve()
    except (OSError, RuntimeError):
        spec_root_match = False
        runtime_home_match = False
    ok = bool(
        result.returncode == 0
        and context.get("controller_version") == CONTROLLER_VERSION
        and context.get("workflow_version") == workflow()["workflow_version"]
        and spec_root_match
        and runtime_home_match
        and bootstrap_result.returncode == 0
        and bootstrap.get("interface") == "local-global-command"
        and bootstrap.get("command") == "article-flow"
        and bootstrap.get("start_command", [])[:2] == ["article-flow", "start"]
    )
    return {
        "ok": ok,
        "launcher": str(launcher),
        "return_code": result.returncode,
        "controller_version": str(context.get("controller_version", "")),
        "workflow_version": str(context.get("workflow_version", "")),
        "spec_root_match": spec_root_match,
        "runtime_home_match": runtime_home_match,
        "bootstrap_ok": bool(bootstrap_result.returncode == 0 and bootstrap.get("interface") == "local-global-command" and bootstrap.get("command") == "article-flow"),
        "unrelated_cwd": True,
        "error": "" if ok else (result.stderr.strip() or bootstrap_result.stderr.strip() or "launcher context or bootstrap did not match the installed controller"),
    }


def command_lifecycle(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    if run["state"] != "COMPLETE":
        raise FlowError("Post-publication lifecycle planning requires a completed, live-verified run")
    if args.action in {"supersede", "archive"} and not args.redirect_to:
        raise FlowError(f"{args.action} requires --redirect-to so URL behavior is not inferred", EXIT_APPROVAL)
    live = json_artifact(directory, run, "live-verification") or {}
    event = {
        "lifecycle_request_schema_version": "1.0.0",
        "request_id": f"LC-{secrets.token_hex(8)}",
        "run_id": run["run_id"],
        "state": {"correction": "CORRECTION", "refresh": "REFRESH", "supersede": "SUPERSESSION", "archive": "ARCHIVAL"}[args.action],
        "action": args.action,
        "reason": args.reason,
        "current_url": live.get("url"),
        "current_package_revision": live.get("package_revision"),
        "redirect_to": args.redirect_to,
        "required_checks": ["prior revision retained", "canonical URL decision explicit", "redirect verified when applicable", "navigation history preserved", "feed and sitemap intentional", "new scoped approval"],
        "status": "PLANNED_NOT_APPLIED",
        "created_at": utc_now(),
    }
    path = directory / "publication" / f"{event['request_id']}.json"
    write_json(path, event)
    record_artifact(directory, run, path, f"lifecycle-request:{event['request_id']}", {"actor": "operator"})
    append_event(directory, run, "LIFECYCLE_REQUEST", "operator", {"lifecycle": event})
    save_run(directory, run)
    emit({"ok": True, "run_id": run["run_id"], "lifecycle": event, "next": "Create a new revision/package and an exact publication plan; this request performed no public change."}, args.json)
    return EXIT_OK


def mcp_tools() -> list[dict[str, Any]]:
    return [
        {"name": "start", "description": "Start an article run or return the seed question", "inputSchema": {"type": "object", "properties": {"seed": {"type": "string"}}, "additionalProperties": False}},
        {"name": "status", "description": "Read a run", "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"]}},
        {"name": "next", "description": "Get the next controller action", "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"]}},
        {"name": "resume", "description": "Resume from the last valid event", "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"]}},
        {
            "name": "gate",
            "description": "Record an explicit operator-owned soft-gate decision or scoped publication approval",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "gate_id": {"type": "string"},
                    "outcome": {"enum": ["PASS", "REPAIR", "RETRY", "ESCALATE", "TERMINAL"]},
                    "finding": {"type": "string"},
                    "artifact": {"type": "string"},
                    "selection": {"type": "string"},
                    "feedback": {"type": "string"}
                },
                "required": ["run_id", "gate_id", "outcome"],
                "additionalProperties": False
            }
        },
    ]


def command_mcp(_: argparse.Namespace) -> int:
    for line in sys.stdin:
        request: Any = None
        try:
            request = json.loads(line)
            method = request.get("method")
            request_id = request.get("id")
            if method == "initialize":
                result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "article-flow", "version": CONTROLLER_VERSION}}
            elif method == "tools/list":
                result = {"tools": mcp_tools()}
            elif method == "tools/call":
                params = request.get("params", {})
                name = params.get("name")
                arguments = params.get("arguments", {})
                if name == "start":
                    namespace = argparse.Namespace(seed=arguments.get("seed"), seed_file=None, slug=None, json=True)
                    buffer = io.StringIO()
                    with contextlib.redirect_stdout(buffer):
                        code = command_start(namespace)
                    payload = json.loads(buffer.getvalue())
                    payload["exit_code"] = code
                elif name in {"status", "next", "resume"}:
                    directory, run = load_run(arguments["run_id"])
                    if name == "status":
                        payload = {**run, "run_directory": str(directory)}
                    else:
                        with run_lock(directory, run):
                            payload = next_state_payload(directory, run)
                elif name == "gate":
                    namespace = argparse.Namespace(
                        run_id=arguments["run_id"],
                        gate_id=arguments["gate_id"],
                        outcome=arguments["outcome"],
                        finding=arguments.get("finding"),
                        artifact=arguments.get("artifact"),
                        selection=arguments.get("selection"),
                        feedback=arguments.get("feedback"),
                        json=True,
                    )
                    buffer = io.StringIO()
                    with contextlib.redirect_stdout(buffer):
                        code = command_gate(namespace)
                    payload = json.loads(buffer.getvalue())
                    payload["exit_code"] = code
                else:
                    raise FlowError(f"Unknown MCP tool: {name}")
                result = {"content": [{"type": "text", "text": json.dumps(payload)}]}
            elif method and method.startswith("notifications/"):
                continue
            else:
                raise FlowError(f"Unsupported MCP method: {method}")
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None, "error": {"code": -32000, "message": str(exc)}}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
    return EXIT_OK


def emit(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if isinstance(payload, dict):
        if payload.get("question") and payload.get("action") == "request_seed":
            print(payload["question"])
            return
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(payload)


def add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="article-flow", description="Provider-neutral, resumable article workflow controller.")
    parser.add_argument("--version", action="version", version=f"article-flow {CONTROLLER_VERSION}")
    sub = parser.add_subparsers(dest="command", required=False)

    where = sub.add_parser("where", help="Print the canonical specification root.")
    add_json(where)
    context = sub.add_parser("context", help="Show controller, workflow, and runtime paths.")
    add_json(context)

    install = sub.add_parser("install", help="Link the global WSL and Windows commands to this checkout.")
    install.add_argument("--user", action="store_true", default=True)
    install.add_argument("--providers", default="auto")
    install.add_argument("--hosts", default="windows,wsl")
    install.add_argument("--development", action="store_true", help="Install unmanifested development bytes; never release from this mode.")
    add_json(install)

    doctor = sub.add_parser("doctor", help="Report launcher, integrity, global-command, authoring, and release health separately.")
    doctor.add_argument("--scope", choices=["launcher", "authoring", "release", "all"], default="launcher")
    doctor.add_argument("--all", action="store_true")
    add_json(doctor)

    start = sub.add_parser("start", help="Start a collision-safe article run from a verbatim seed.")
    seed_group = start.add_mutually_exclusive_group()
    seed_group.add_argument("--seed")
    seed_group.add_argument("--seed-file")
    start.add_argument("--slug")
    add_json(start)

    for name, help_text in (("status", "Show run state and artifacts."), ("next", "Return the next complete controller action."), ("resume", "Resume from the last valid event.")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("run_id", nargs="?" if name == "status" else None)
        add_json(command)

    submit = sub.add_parser("submit", help="Submit one stage artifact for code-owned validation.")
    submit.add_argument("run_id")
    submit.add_argument("--stage", required=True)
    submit.add_argument("--file", required=True)
    add_json(submit)

    execute = sub.add_parser("execute-stage", help="Invoke the current task through an eligible controller-hosted provider adapter.")
    execute.add_argument("run_id")
    execute.add_argument("--route", help="Use one eligible PROVIDER:MODEL route for this attempt.")
    execute.add_argument("--canary", action="store_true", help="Allow a route whose only exclusion is a required canary; does not promote it.")
    add_json(execute)

    gate = sub.add_parser("gate", help="Record an operator-owned soft gate or scoped publication approval.")
    gate.add_argument("run_id")
    gate.add_argument("gate_id", nargs="?")
    gate.add_argument("--outcome", choices=["PASS", "REPAIR", "RETRY", "ESCALATE", "TERMINAL"], required=True)
    gate.add_argument("--finding")
    gate.add_argument("--artifact")
    gate.add_argument("--selection")
    gate.add_argument("--feedback")
    add_json(gate)

    repair = sub.add_parser("repair", help="Return a failed gate to its declared repair state.")
    repair.add_argument("run_id")
    repair.add_argument("gate_id", nargs="?")
    repair.add_argument("--finding")
    add_json(repair)

    package = sub.add_parser("package", help="Create hashed public and private packages.")
    package.add_argument("run_id")
    add_json(package)

    publish = sub.add_parser("publish", help="Plan or execute one scoped publication revision.")
    mode = publish.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--execute", action="store_true")
    publish.add_argument("run_id")
    publish.add_argument("--approval")
    publish.add_argument("--commit", action="store_true")
    publish.add_argument("--push", action="store_true")
    add_json(publish)

    verify = sub.add_parser("verify-live", help="Verify the exact rendered revision and discovery surfaces.")
    verify.add_argument("run_id")
    add_json(verify)

    providers = sub.add_parser("providers", help="Inspect private provider configuration without exposing credentials.")
    providers_sub = providers.add_subparsers(dest="provider_command", required=True)
    providers_list = providers_sub.add_parser("list")
    add_json(providers_list)

    route = sub.add_parser("route", help="Show eligibility, evidence, selection reason, and fallbacks for one stage.")
    route.add_argument("stage", choices=sorted(MODEL_STATES))
    add_json(route)

    evaluation = sub.add_parser("evaluation", help="Record or summarize fixture-backed routing evidence.")
    evaluation_sub = evaluation.add_subparsers(dest="evaluation_command", required=True)
    evaluation_record = evaluation_sub.add_parser("record")
    evaluation_record.add_argument("--file", required=True)
    add_json(evaluation_record)
    evaluation_summary = evaluation_sub.add_parser("summarize")
    add_json(evaluation_summary)

    manifest = sub.add_parser("manifest", help="Build, check, or explain the SHA-256 release manifest.")
    manifest_sub = manifest.add_subparsers(dest="manifest_command", required=True)
    manifest_build = manifest_sub.add_parser("build")
    manifest_build.add_argument("--from-index", action="store_true", required=True)
    add_json(manifest_build)
    manifest_check = manifest_sub.add_parser("check")
    source = manifest_check.add_mutually_exclusive_group(required=True)
    source.add_argument("--against-worktree", action="store_true")
    source.add_argument("--against-index", action="store_true")
    source.add_argument("--against-head", action="store_true")
    add_json(manifest_check)
    manifest_explain = manifest_sub.add_parser("explain")
    manifest_explain.add_argument("path")
    add_json(manifest_explain)

    conformance = sub.add_parser("conformance", help="Run the non-publishing regression and portability suite.")
    add_json(conformance)
    lifecycle = sub.add_parser("lifecycle", help="Record correction, refresh, supersession, or archival intent.")
    lifecycle.add_argument("run_id")
    lifecycle.add_argument("action", choices=["correction", "refresh", "supersede", "archive"])
    lifecycle.add_argument("--reason", required=True)
    lifecycle.add_argument("--redirect-to")
    add_json(lifecycle)
    sub.add_parser("mcp", help="Run the optional local stdio MCP adapter.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command is None:
            print(json.dumps(bootstrap_payload(), indent=2, ensure_ascii=False))
            return EXIT_OK
        if args.command == "where":
            emit({"spec_root": str(SPEC_ROOT)} if args.json else str(SPEC_ROOT), args.json)
            return EXIT_OK
        if args.command == "context":
            emit({"controller_version": CONTROLLER_VERSION, "workflow_version": workflow()["workflow_version"], "interface": "local-global-command", "command": "article-flow", "spec_root": str(SPEC_ROOT), "source_tree_root": str(REPO_ROOT), "publication_repo_root": str(publication_repo_root()) if publication_repo_root() else None, "runtime_home": str(runtime_home()), "precedence": workflow()["precedence"]}, args.json)
            return EXIT_OK
        if args.command == "install":
            return command_install(args)
        if args.command == "doctor":
            return command_doctor(args)
        if args.command == "start":
            return command_start(args)
        if args.command == "status":
            return command_status(args)
        if args.command == "next":
            return command_next(args)
        if args.command == "resume":
            return command_resume(args)
        if args.command == "submit":
            return command_submit(args)
        if args.command == "execute-stage":
            return command_execute_stage(args)
        if args.command == "gate":
            return command_gate(args)
        if args.command == "repair":
            return command_repair(args)
        if args.command == "package":
            return command_package(args)
        if args.command == "publish":
            if args.plan:
                return command_publish_plan(args)
            if not args.approval:
                raise FlowError("--execute requires --approval APPROVAL_ID", EXIT_APPROVAL)
            return command_publish_execute(args)
        if args.command == "verify-live":
            return command_verify_live(args)
        if args.command == "providers" and args.provider_command == "list":
            return command_providers_list(args)
        if args.command == "route":
            return command_route(args)
        if args.command == "evaluation":
            if args.evaluation_command == "record":
                return command_evaluation_record(args)
            return command_evaluation_summarize(args)
        if args.command == "manifest":
            if args.manifest_command == "build":
                return command_manifest_build(args)
            if args.manifest_command == "check":
                return command_manifest_check(args)
            return command_manifest_explain(args)
        if args.command == "conformance":
            return command_conformance(args)
        if args.command == "lifecycle":
            return command_lifecycle(args)
        if args.command == "mcp":
            return command_mcp(args)
        parser.error(f"Unknown command: {args.command}")
        return EXIT_USAGE
    except FlowError as exc:
        payload = {"ok": False, "error": str(exc), "details": exc.details, "exit_code": exc.code}
        as_json = bool(getattr(args, "json", False))
        if as_json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(str(exc), file=sys.stderr)
            if exc.details is not None:
                print(json.dumps(exc.details, indent=2, ensure_ascii=False), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
