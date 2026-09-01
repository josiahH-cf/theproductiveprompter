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
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

try:
    from codex_exec_adapter import CodexExecError, codex_cli_version, execute_task_packet
except ModuleNotFoundError:  # Supports importlib-based conformance tests.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from codex_exec_adapter import CodexExecError, codex_cli_version, execute_task_packet


CONTROLLER_VERSION = "3.0.0"
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
        "start_command": ["article-flow", "capture", "<verbatim operator seed>", "--auto", "--json"],
        "protocol": [
            "Preserve the operator's seed verbatim when replacing the placeholder in start_command.",
            "Run only exact command arrays returned by the controller in next_command, command, submission_command, or approval_command fields.",
            "For perform_task, read only task_packet, create only expected_output, then run submission_command.",
            "For human_decision, show the controller's three voice choices and wait; never run selection_command without the operator's confirmed choice.",
            "For human_action, show the controller's single handoff and wait for the operator or a credentialed host to complete it.",
            "For run_command, run the exact command array returned by the controller. Use advance for active-session automation and safe resumption.",
            "Stop on complete, terminal, or an unresolved capability or decision.",
        ],
        "capability_requirement": "This interface requires local command execution. A cloud-only chat without access to this machine cannot run it.",
    }
REVIEW_STATES = {"INTENT_REVIEW", "ARTICLE_RECIPE", "VOICE_PROBE", "EDITORIAL_QA"}
AUTO_REVIEW_STATES = {"INTENT_REVIEW", "ARTICLE_RECIPE", "EDITORIAL_QA"}
DETERMINISTIC_STATES = {"VOICE_LEARNING", "PACKAGE", "PUBLISH_APPROVAL", "PUBLISH", "LIVE_VERIFICATION", "COMPLETE"}
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
LEGACY_WORKFLOW_VERSION = "2.0.0"
V3_WRITING_STATES = {"DRAFT", "VOICE_PROBE", "EDIT"}
DEFAULT_DRAFT_MODEL_POOL = ["gpt-5.5", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_WAITING = 10
EXIT_INTEGRITY = 20
EXIT_APPROVAL = 30

SURFACE_PROSE_PATTERNS = (
    "not a magic spell",
    "at its core",
    "here's the thing",
    "the key takeaway",
    "it's important to note",
    "it's worth noting",
    "in today's world",
    "in an ever-evolving",
    "let's unpack",
    "let's explore",
    "delve into",
    "dive into",
    "game-changer",
    "unlock the power",
    "harness the power",
    "seamless",
    "robust and scalable",
    "holistic approach",
    "actionable insights",
    "now more than ever",
    "the possibilities are endless",
    "at the end of the day",
    "in conclusion",
    "the bottom line",
)

FORBIDDEN_PUBLIC_PROSE_CHARACTERS = {
    "\u2014": {"name": "em dash", "codepoint": "U+2014"},
}


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


@functools.lru_cache(maxsize=8)
def workflow_for_version(version: str) -> dict[str, Any]:
    """Load the immutable authority recorded by a run instead of reinterpreting it."""
    current = workflow()
    if version == current.get("workflow_version"):
        return current
    archived = SPEC_ROOT / "workflow" / f"workflow.v{version}.json"
    if archived.is_file():
        value = load_json(archived)
        if value.get("workflow_version") != version:
            raise FlowError(f"Archived workflow {archived.name} declares the wrong version", EXIT_INTEGRITY)
        return value
    raise FlowError(f"No compatible workflow authority is installed for run version {version}", EXIT_INTEGRITY)


def workflow_for_run(run: dict[str, Any]) -> dict[str, Any]:
    return workflow_for_version(str(run.get("workflow_version")))


def policy() -> dict[str, Any]:
    return load_json(POLICY_PATH)


def state_definition(state_id: str, run: dict[str, Any] | None = None) -> dict[str, Any]:
    authority = workflow_for_run(run) if run is not None else workflow()
    for item in authority["states"]:
        if item["id"] == state_id:
            return item
    raise FlowError(f"Unknown workflow state: {state_id}")


def is_v3_run(run: dict[str, Any]) -> bool:
    return str(run.get("workflow_version", "")).split(".", 1)[0] == "3"


def automation_enabled(run: dict[str, Any]) -> bool:
    return is_v3_run(run) and run.get("run_overrides", {}).get("automation_mode") == "active_session"


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
    configured = os.environ.get("ARTICLE_FLOW_RUNS_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    recorded = installation_record().get("captured_material_root")
    if recorded:
        return Path(str(recorded)).expanduser().resolve()
    return runtime_home() / "runs"


def shared_state_root() -> Path:
    """Return the cross-host state root shared by Windows and WSL runs."""
    return runs_root().parent


def model_state_root() -> Path:
    return shared_state_root() / "models"


def voice_state_root() -> Path:
    return shared_state_root() / "voice"


def process_is_alive(pid: int) -> bool:
    """Probe a lock owner's PID without emitting a Windows console event."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        error_invalid_parameter = 87
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            # Invalid PID proves absence. Access-denied and unfamiliar failures
            # are treated conservatively so a live owner's lock is not stolen.
            return ctypes.get_last_error() != error_invalid_parameter
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@contextlib.contextmanager
def shared_lock(path: Path, *, stale_seconds: int = 3600, wait_seconds: float = 15.0) -> Iterator[None]:
    """Cross-host, crash-recoverable lock for rotation and voice state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    deadline = time.monotonic() + wait_seconds
    while descriptor is None:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            try:
                value = load_json(path)
            except FlowError:
                value = {}
            created = value.get("created_at")
            try:
                age = (dt.datetime.now(dt.timezone.utc) - parse_time(str(created))).total_seconds() if created else time.time() - path.stat().st_mtime
            except (OSError, ValueError):
                age = 0
            same_namespace = value.get("namespace") == lock_namespace()
            alive = False
            if same_namespace and int(value.get("pid", -1)) > 0:
                alive = process_is_alive(int(value["pid"]))
            has_owner = bool(value.get("namespace") and int(value.get("pid", -1)) > 0)
            fresh_unknown_owner = not has_owner and age <= min(stale_seconds, 2)
            cross_host_fresh = has_owner and not same_namespace and age <= stale_seconds
            if alive or fresh_unknown_owner or cross_host_fresh:
                if time.monotonic() >= deadline:
                    raise FlowError(f"Timed out waiting for shared Article Flow state: {path}") from exc
                time.sleep(0.02)
                continue
            recovered = path.with_name(f"{path.name}.recovered-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
            try:
                path.replace(recovered)
            except FileNotFoundError:
                continue
    try:
        os.write(descriptor, canonical_json({"pid": os.getpid(), "namespace": lock_namespace(), "created_at": utc_now()}))
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        path.unlink(missing_ok=True)


def public_model_name(model_id: str) -> str:
    names = {
        "gpt-5.5": "GPT-5.5",
        "gpt-5.6-sol": "GPT-5.6 Sol",
        "gpt-5.6-terra": "GPT-5.6 Terra",
        "gpt-5.6-luna": "GPT-5.6 Luna",
    }
    return names.get(model_id, model_id)


def writing_model_policy() -> dict[str, Any]:
    configured = policy().get("routing", {}).get("writing_model_rotation", {})
    raw_models = configured.get("ordered_models") if isinstance(configured, dict) else None
    if not isinstance(raw_models, list) or not raw_models:
        raw_models = DEFAULT_DRAFT_MODEL_POOL
    models: list[str] = []
    display_names: dict[str, str] = {}
    for item in raw_models:
        if isinstance(item, dict):
            model_id = str(item.get("model_id") or "")
            if not model_id:
                continue
            display_names[model_id] = str(item.get("public_display_name") or public_model_name(model_id))
        else:
            model_id = str(item)
            display_names[model_id] = public_model_name(model_id)
        models.append(model_id)
    if not models:
        models = list(DEFAULT_DRAFT_MODEL_POOL)
        display_names = {item: public_model_name(item) for item in models}
    return {
        "pool_id": str(configured.get("pool_id", "codex-writing-v1")) if isinstance(configured, dict) else "codex-writing-v1",
        "pool_version": str(configured.get("pool_version", "1.0.0")) if isinstance(configured, dict) else "1.0.0",
        "provider_id": str(configured.get("provider_id", "codex-cli")) if isinstance(configured, dict) else "codex-cli",
        "ordered_models": models,
        "display_names": display_names,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FlowError(f"Invalid JSONL state: {path}: {exc}", EXIT_INTEGRITY) from exc
        if not isinstance(item, dict):
            raise FlowError(f"Invalid non-object JSONL state: {path}", EXIT_INTEGRITY)
        values.append(item)
    return values


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def reserve_draft_model(run_id: str, override: str | None = None) -> dict[str, Any]:
    """Reserve one stable writing model without races across local hosts."""
    config = writing_model_policy()
    models = config["ordered_models"]
    if override and override not in models:
        raise FlowError(f"Draft model is not in the configured experiment pool: {override}", EXIT_USAGE, {"allowed": models})
    root = model_state_root()
    ledger = root / "assignments.jsonl"
    with shared_lock(root / ".lock"):
        history = _read_jsonl(ledger)
        existing = next((item for item in history if item.get("run_id") == run_id), None)
        if existing:
            if override and existing.get("assigned_model_id") != override:
                raise FlowError("Run already has a different immutable draft-model assignment", EXIT_INTEGRITY, existing)
            return existing
        consumes = override is None
        consumed = sum(1 for item in history if item.get("consumes_rotation"))
        rotation_index = consumed % len(models) if consumes else None
        model_id = override or models[int(rotation_index)]
        assignment = {
            "model_assignment_schema_version": "1.0.0",
            "run_id": run_id,
            "pool_id": config["pool_id"],
            "pool_version": config["pool_version"],
            "rotation_index": rotation_index,
            "provider_id": config["provider_id"],
            "assigned_model_id": model_id,
            "public_display_name": config["display_names"].get(model_id, public_model_name(model_id)),
            "selection_reason": "operator_override" if override else "round_robin",
            "override": bool(override),
            "consumes_rotation": consumes,
            "status": "assigned",
            "actual_models": [],
            "contaminated": False,
            "created_at": utc_now(),
        }
        errors = validate_instance_schema(assignment, "model-assignment.schema.json")
        if errors:
            raise FlowError("Controller generated an invalid model assignment", EXIT_INTEGRITY, errors)
        _append_jsonl(ledger, assignment)
        return assignment


def model_history() -> dict[str, Any]:
    assignments = _read_jsonl(model_state_root() / "assignments.jsonl")
    durable_history = {
        str(item.get("run_id")): item
        for item in _read_jsonl(model_state_root() / "history.jsonl")
        if item.get("run_id")
    }
    runs: list[dict[str, Any]] = []
    for assignment in assignments:
        durable = durable_history.get(str(assignment.get("run_id")), {})
        try:
            directory, run = load_run(str(assignment.get("run_id")))
        except FlowError:
            directory = None
            run = {}
        metadata = json_artifact(directory, run, "brief") if directory else None
        live = json_artifact(directory, run, "live-verification") if directory else None
        experiment = run.get("model_experiment", {}) if isinstance(run, dict) else {}
        experiment_summary = summarize_model_experiment(directory, run, assignment) if directory else {}
        actual_model = durable.get("actual_model_id") or experiment_summary.get("actual_model_id") or experiment.get("active_model_id")
        actual_models = durable.get("actual_models") or experiment.get("actual_models") or ([actual_model] if actual_model else [])
        runs.append({
            **assignment,
            **experiment_summary,
            **{key: value for key, value in durable.items() if key not in {"run_id", "assignment_sha256", "recorded_at"}},
            "actual_models": actual_models,
            "contaminated": bool(durable.get("contaminated", experiment.get("contaminated", assignment.get("contaminated", False)))),
            "active_model_id": actual_model or assignment.get("assigned_model_id"),
            "stage_routes": durable.get("stage_routes", experiment.get("stage_routes", {})),
            "state": run.get("state") or ("COMPLETE" if durable else None),
            "title": durable.get("title") or (metadata or {}).get("title"),
            "live_url": durable.get("article_url") or (live or {}).get("url"),
            "recorded_at": durable.get("recorded_at"),
        })
    return {"ok": True, "pool": writing_model_policy(), "count": len(runs), "runs": runs}


def summarize_model_experiment(directory: Path, run: dict[str, Any], assignment: dict[str, Any] | None = None) -> dict[str, Any]:
    assignment = assignment or json_artifact(directory, run, "model-assignment") or {}
    experiment = run.get("model_experiment", {})
    receipts: list[dict[str, Any]] = []
    for item in run.get("artifact_index", []):
        artifact_type = str(item.get("type", ""))
        if not any(artifact_type.startswith(f"model-call:{stage}:") for stage in V3_WRITING_STATES):
            continue
        path = directory / str(item.get("path"))
        if path.is_file():
            receipts.append(load_json(path))
    elapsed = sum(int((receipt.get("route") or {}).get("elapsed_ms") or 0) for receipt in receipts)
    usage: dict[str, int] = {}
    cli_versions: list[str] = []
    for receipt in receipts:
        transport = (receipt.get("route") or {}).get("transport") or {}
        if transport.get("cli_version"):
            cli_versions.append(str(transport["cli_version"]))
        raw_usage = transport.get("usage")
        if isinstance(raw_usage, dict):
            for key, value in raw_usage.items():
                if isinstance(value, int):
                    usage[key] = usage.get(key, 0) + value
    stage_routes = experiment.get("stage_routes", {})
    fallbacks = [
        {"stage": stage, **route}
        for stage, route in stage_routes.items()
        if isinstance(route, dict) and route.get("fallback")
    ]
    retries = sum(max(0, int(run.get("attempts", {}).get(stage, 0)) - 1) for stage in V3_WRITING_STATES)
    editorial = json_artifact(directory, run, "editorial-qa") or {}
    return {
        "requested_model_id": assignment.get("assigned_model_id"),
        "actual_model_id": experiment.get("active_model_id") or assignment.get("assigned_model_id"),
        "provider_id": experiment.get("provider_id") or assignment.get("provider_id"),
        "cli_version": cli_versions[-1] if cli_versions else "unknown",
        "writing_stages": sorted(stage_routes),
        "elapsed_milliseconds": elapsed,
        "token_usage": usage,
        "cost": {"status": "unknown_not_claimed", "currency": None, "amount": None},
        "retries": retries,
        "fallbacks": fallbacks,
        "qa_results": {
            "outcome": editorial.get("outcome"),
            "dimensions": editorial.get("dimensions", {}),
            "finding_count": len(editorial.get("findings", [])) if isinstance(editorial.get("findings"), list) else None,
        },
    }


def record_experiment_outcome(directory: Path, run: dict[str, Any]) -> dict[str, Any] | None:
    if not is_v3_run(run):
        return None
    assignment_path = artifact_path(directory, run, "model-assignment")
    assignment = json_artifact(directory, run, "model-assignment")
    if not assignment_path or not assignment:
        raise FlowError("Cannot record model experiment without its assignment", EXIT_INTEGRITY)
    summary = summarize_model_experiment(directory, run, assignment)
    live = json_artifact(directory, run, "live-verification") or {}
    entry = {
        "run_id": run["run_id"],
        "assignment_sha256": sha256_path(assignment_path),
        **summary,
        "actual_models": list(run.get("model_experiment", {}).get("actual_models", [])),
        "stage_routes": dict(run.get("model_experiment", {}).get("stage_routes", {})),
        "contaminated": bool(run.get("model_experiment", {}).get("contaminated", False)),
        "title": (json_artifact(directory, run, "brief") or {}).get("title"),
        "article_url": live.get("url"),
        "recorded_at": utc_now(),
    }
    errors = validate_instance_schema({"experiment_history_schema_version": "1.0.0", "entries": [entry]}, "experiment-history.schema.json")
    if errors:
        raise FlowError("Controller generated invalid model-experiment history", EXIT_INTEGRITY, errors)
    root = model_state_root()
    with shared_lock(root / ".lock"):
        existing = _read_jsonl(root / "history.jsonl")
        prior = next((item for item in existing if item.get("run_id") == run["run_id"]), None)
        if prior:
            return prior
        _append_jsonl(root / "history.jsonl", entry)
    return entry


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
            transition_payload = event.get("payload", {})
            if transition_payload.get("from") != derived_state:
                return False, f"state transition source mismatch at sequence {expected_sequence}", derived_state
            derived_state = str(transition_payload.get("to", derived_state))
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


def lock_namespace() -> str:
    return f"{'windows' if os.name == 'nt' else 'posix'}:{platform.node() or 'unknown-host'}"


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
        prior_namespace = str(lock.get("namespace", ""))
        current_namespace = lock_namespace()
        same_namespace = prior_namespace == current_namespace
        alive = False
        if same_namespace and pid > 0:
            alive = process_is_alive(pid)
        try:
            age_seconds = (dt.datetime.now(dt.timezone.utc) - parse_time(str(created))).total_seconds() if created else (time.time() - lock_path.stat().st_mtime)
        except (OSError, ValueError):
            age_seconds = 0
        old = age_seconds > 3600
        if alive or (not same_namespace and not old):
            raise FlowError(f"Run is already locked: {run['run_id']}") from exc
        recovered = directory / f".lock.recovered-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        lock_path.replace(recovered)
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        append_event(directory, run, "LOCK_RECOVERED", "controller", {"stale_lock": recovered.name, "prior": lock})
    try:
        os.write(descriptor, canonical_json({"pid": os.getpid(), "namespace": lock_namespace(), "created_at": utc_now()}))
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


def validate_schema_value(value: Any, schema: Any, schemas: dict[str, dict[str, Any]], path: str = "$") -> list[str]:
    if schema is True:
        return []
    if schema is False:
        return [f"{path}: value is forbidden by the schema"]
    if not isinstance(schema, dict):
        return [f"{path}: invalid schema node {schema!r}"]
    if "$ref" in schema:
        reference = str(schema["$ref"]).rsplit("/", 1)[-1]
        target = schemas.get(reference)
        if target is None:
            return [f"{path}: unresolved schema reference {schema['$ref']}"]
        return validate_schema_value(value, target, schemas, path)
    errors: list[str] = []
    if "allOf" in schema:
        for candidate in schema["allOf"]:
            errors.extend(validate_schema_value(value, candidate, schemas, path))
    if "anyOf" in schema:
        results = [validate_schema_value(value, candidate, schemas, path) for candidate in schema["anyOf"]]
        if not any(not result for result in results):
            errors.append(f"{path}: expected at least one anyOf branch to match")
    if "oneOf" in schema:
        results = [validate_schema_value(value, candidate, schemas, path) for candidate in schema["oneOf"]]
        passing = sum(not errors for errors in results)
        if passing != 1:
            return [f"{path}: expected exactly one oneOf branch to match; matched {passing}"]
    if "not" in schema and not validate_schema_value(value, schema["not"], schemas, path):
        errors.append(f"{path}: value matches a forbidden schema")
    if "if" in schema:
        branch = schema.get("then") if not validate_schema_value(value, schema["if"], schemas, path) else schema.get("else")
        if branch is not None:
            errors.extend(validate_schema_value(value, branch, schemas, path))
    if "const" in schema and canonical_json(value) != canonical_json(schema["const"]):
        errors.append(f"{path}: value does not equal required constant {schema['const']!r}")
    if "enum" in schema and not any(canonical_json(value) == canonical_json(candidate) for candidate in schema["enum"]):
        errors.append(f"{path}: value {value!r} is not in the allowed enum")

    declared_type = schema.get("type")
    expected_types = [declared_type] if isinstance(declared_type, str) else list(declared_type or [])
    if expected_types and not any(json_type_matches(value, item) for item in expected_types):
        errors.append(f"{path}: expected type {' | '.join(expected_types)}, got {type(value).__name__}")
        return errors

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
    if isinstance(schema, bool):
        return []
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
    for keyword in ("oneOf", "anyOf", "allOf"):
        if keyword not in schema:
            continue
        if not isinstance(schema[keyword], list) or not schema[keyword]:
            errors.append(f"{path}: {keyword} must contain at least one schema")
        else:
            for index, child in enumerate(schema[keyword]):
                errors.extend(schema_definition_errors(child, schemas, f"{path}.{keyword}[{index}]"))
    for keyword in ("if", "then", "else", "not"):
        if keyword in schema:
            errors.extend(schema_definition_errors(schema[keyword], schemas, f"{path}.{keyword}"))
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


@functools.lru_cache(maxsize=8)
def inspected_codex_cli_version(executable: str) -> str | None:
    try:
        return codex_cli_version(executable)
    except CodexExecError:
        return None


def evidenced_codex_canary_status(provider: dict[str, Any], model: dict[str, Any]) -> str:
    declared = str(model.get("canary_status", "not-declared"))
    if declared != "passed":
        return declared
    model_id = str(model.get("model_id") or "")
    expected_hash = str(model.get("canary_receipt_sha256") or "")
    receipt_path = shared_state_root() / "canaries" / f"{model_id}.receipt.json"
    if not expected_hash or not receipt_path.is_file() or sha256_path(receipt_path) != expected_hash:
        return "invalid-evidence"
    try:
        receipt = load_json(receipt_path)
    except FlowError:
        return "invalid-evidence"
    executable = str(provider.get("executable", "codex"))
    transport = receipt.get("transport", {}) if isinstance(receipt.get("transport"), dict) else {}
    if not (
        receipt.get("requested_model") == model_id
        and receipt.get("exit_code") == 0
        and receipt.get("cli_version") == inspected_codex_cli_version(executable)
        and transport.get("host_tool_access") == "disabled"
        and transport.get("host_file_access") == "none_via_model_tools"
        and transport.get("web_search_mode") == "disabled"
    ):
        return "invalid-evidence"
    return "passed"


def route_candidates(stage: str, excluded_routes: set[str] | None = None) -> dict[str, Any]:
    if stage not in MODEL_STATES:
        return {"stage": stage, "required_capabilities": [], "candidates": [], "chosen": None, "reason": "deterministic stage; no model route permitted"}
    capabilities = capability_registry()
    score_map = promoted_evaluation_scores()
    required = STAGE_CAPABILITIES.get(stage, set())
    excluded_routes = excluded_routes or set()
    require_local = os.environ.get("ARTICLE_FLOW_REQUIRE_LOCAL", "").lower() in {"1", "true", "yes"}
    require_canary = bool(
        load_json(SPEC_ROOT / "evaluations" / "evaluation-registry.json")
        .get("promotion_policy", {})
        .get("require_provider_version_canary", False)
    )
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
            if kind in {"command", "codex-cli"}:
                command = provider.get("command", [])
                executable = (
                    str(provider.get("executable", "codex"))
                    if kind == "codex-cli"
                    else str(command[0]) if isinstance(command, list) and command else ""
                )
                if not executable or not (Path(executable).exists() or shutil.which(executable)):
                    eligible = False
                    exclusions.append("command unavailable")
            if kind not in {"agent-hosted", "command", "codex-cli"} and not resolved_provider_endpoint(provider):
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
            canary_status = evidenced_codex_canary_status(provider, model) if kind == "codex-cli" else str(model.get("canary_status", "not-declared"))
            if require_canary and kind != "agent-hosted" and canary_status != "passed":
                eligible = False
                exclusions.append(f"canary {canary_status}")
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
                "canary_status": canary_status,
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


def pin_writing_route(run: dict[str, Any], stage: str, routes: dict[str, Any]) -> dict[str, Any]:
    """Keep the assigned writing model pinned across draft, probe, and rewrite."""
    if not is_v3_run(run) or stage not in V3_WRITING_STATES:
        return routes
    experiment = run.get("model_experiment", {})
    provider_id = str(experiment.get("provider_id") or "")
    active_model = str(experiment.get("active_model_id") or experiment.get("assigned_model_id") or "")
    if not provider_id or not active_model:
        return {**routes, "chosen": None, "fallbacks": [], "reason": "the run has no immutable writing-model assignment"}
    eligible = [item for item in routes.get("candidates", []) if item.get("eligible")]
    chosen = next(
        (item for item in eligible if item.get("provider") == provider_id and item.get("model") == active_model),
        None,
    )
    if chosen is None:
        unavailable = next(
            (item for item in routes.get("candidates", []) if item.get("provider") == provider_id and item.get("model") == active_model),
            None,
        )
        reason = f"assigned writing route {provider_id}:{active_model} is unavailable"
        if unavailable and unavailable.get("exclusion_reason"):
            reason += f": {unavailable['exclusion_reason']}"
        ordered_models = writing_model_policy()["ordered_models"]
        fallbacks = [
            candidate
            for model_id in ordered_models
            for candidate in eligible
            if candidate.get("provider") == provider_id and candidate.get("model") == model_id and model_id != active_model
        ]
        if not fallbacks:
            return {**routes, "chosen": None, "fallbacks": [], "reason": reason, "assigned_route": unavailable}
        fallback = fallbacks[0]
        return {
            **routes,
            "chosen": fallback,
            "fallbacks": fallbacks[1:],
            "reason": reason + f"; selected experiment-pool fallback {provider_id}:{fallback['model']}",
            "assigned_route": unavailable,
            "assignment_fallback": True,
        }
    ordered_models = writing_model_policy()["ordered_models"]
    fallbacks: list[dict[str, Any]] = []
    for model_id in ordered_models:
        if model_id == active_model:
            continue
        candidate = next(
            (item for item in eligible if item.get("provider") == provider_id and item.get("model") == model_id),
            None,
        )
        if candidate:
            fallbacks.append(candidate)
    return {
        **routes,
        "chosen": chosen,
        "fallbacks": fallbacks,
        "reason": (
            f"workflow 3 writing experiment pinned this run to {provider_id}:{active_model}; "
            "fallbacks remain inside the declared experiment pool"
        ),
        "assignment": {
            "pool_id": experiment.get("pool_id"),
            "assigned_model_id": experiment.get("assigned_model_id"),
            "active_model_id": active_model,
        },
    }


def prefer_controller_route(run: dict[str, Any], stage: str, routes: dict[str, Any]) -> dict[str, Any]:
    if not automation_enabled(run) or stage in V3_WRITING_STATES:
        return routes
    eligible = [
        item for item in routes.get("candidates", [])
        if item.get("eligible") and item.get("kind") != "agent-hosted"
    ]
    if not eligible:
        return routes
    evaluated = [item for item in eligible if item.get("evaluation_score") is not None]
    chosen = sorted(
        evaluated or eligible,
        key=lambda item: (-(float(item.get("evaluation_score") or 0)), str(item.get("provider")), str(item.get("model"))),
    )[0]
    fallbacks = [item for item in eligible if (item.get("provider"), item.get("model")) != (chosen.get("provider"), chosen.get("model"))]
    return {
        **routes,
        "chosen": chosen,
        "fallbacks": fallbacks,
        "reason": routes.get("reason", "") + "; active-session automation selected an eligible controller-hosted route",
    }


def packet_inputs(directory: Path, run: dict[str, Any], state: str) -> list[dict[str, str]]:
    required = set(str(item) for item in state_definition(state, run).get("required_inputs", []))
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


def task_packet(
    directory: Path,
    run: dict[str, Any],
    *,
    requested_route: str | None = None,
    allow_canary: bool = False,
) -> tuple[Path, dict[str, Any]]:
    state = run["state"]
    definition = state_definition(state, run)
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
    route = prefer_controller_route(run, state, route)
    route = pin_writing_route(run, state, route)
    if state in {"CLAIM_VERIFICATION", "POST_EDIT_CLAIM_VERIFICATION", "EDITORIAL_QA"} and route.get("chosen"):
        source_type = "draft" if state == "CLAIM_VERIFICATION" else "article"
        source_item = artifact(run, source_type) or {}
        prior_route = source_item.get("producer", {}).get("route") if isinstance(source_item.get("producer"), dict) else None
        if prior_route:
            prior_key = (prior_route.get("provider"), prior_route.get("model"))
            alternatives = [
                item for item in route.get("candidates", [])
                if item.get("eligible")
                and (not automation_enabled(run) or item.get("kind") != "agent-hosted")
                and (item.get("provider"), item.get("model")) != prior_key
            ]
            if alternatives and (route["chosen"].get("provider"), route["chosen"].get("model")) == prior_key:
                evaluated = [item for item in alternatives if item.get("evaluation_score") is not None]
                replacement = sorted(evaluated or alternatives, key=lambda item: (-(item.get("evaluation_score") or 0), item["provider"], item["model"]))[0]
                prior_chosen = route["chosen"]
                route["chosen"] = replacement
                route["fallbacks"] = [prior_chosen, *[item for item in route.get("fallbacks", []) if (item.get("provider"), item.get("model")) != (replacement.get("provider"), replacement.get("model"))]]
                route["reason"] += "; selected an eligible route independent from the producer of the artifact being verified"
            elif not alternatives and (route["chosen"].get("provider"), route["chosen"].get("model")) == prior_key:
                route["independence_waiver"] = {
                    "required": True,
                    "reason": "No second eligible route is available; repeat verification on the only route and disclose that limitation.",
                }
                route["reason"] += "; only-route verification is allowed with an explicit independence waiver"
    if route.get("chosen") is None and excluded and state in {"CLAIM_VERIFICATION", "POST_EDIT_CLAIM_VERIFICATION"}:
        unrestricted = route_candidates(state)
        if unrestricted.get("chosen"):
            route = unrestricted
            route["independence_waiver"] = {
                "required": True,
                "reason": "Every configured route reached the retry threshold; the only available route may retry with the limitation disclosed.",
            }
            route["reason"] += "; exhausted-route retry is allowed with an explicit independence waiver"
    if requested_route:
        provider_id, separator, model_id = requested_route.partition(":")
        if not separator:
            raise FlowError("--route must be PROVIDER:MODEL", EXIT_USAGE)
        selected = next(
            (
                item for item in route.get("candidates", [])
                if item.get("provider") == provider_id and item.get("model") == model_id
            ),
            None,
        )
        exclusions = [part.strip() for part in str((selected or {}).get("exclusion_reason") or "").split(";") if part.strip()]
        canary_only = bool(exclusions) and all(item.startswith("canary ") for item in exclusions)
        if not selected or (not selected.get("eligible") and not (allow_canary and canary_only)):
            raise FlowError("Requested route is absent or ineligible", EXIT_USAGE, selected)
        if is_v3_run(run) and state in V3_WRITING_STATES:
            experiment = run.get("model_experiment", {})
            pinned_key = (str(experiment.get("provider_id") or ""), str(experiment.get("active_model_id") or ""))
            requested_key = (provider_id, model_id)
            chosen = route.get("chosen") or {}
            chosen_key = (str(chosen.get("provider") or ""), str(chosen.get("model") or ""))
            if allow_canary:
                if requested_key != pinned_key:
                    raise FlowError("A writing-stage canary must use the run's pinned experiment route", EXIT_APPROVAL, selected)
            elif requested_key != chosen_key:
                raise FlowError("An explicit writing route cannot bypass the run's pinned experiment route", EXIT_APPROVAL, selected)
        route = {
            **route,
            "chosen": {**selected, "eligible": True, "exclusion_reason": None, "canary_execution": bool(allow_canary)},
            "fallbacks": [],
            "reason": f"operator requested exact {'canary ' if allow_canary else ''}route {requested_route}",
        }
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
    rule_map = {item["id"]: item["text"] for item in workflow_for_run(run)["rules"]}
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
    if is_v3_run(run) and output_schema_name == "voice-probe.schema.json" and isinstance(output_schema, dict):
        output_schema = next(
            (
                branch for branch in output_schema.get("oneOf", [])
                if isinstance(branch, dict)
                and branch.get("properties", {}).get("voice_probe_schema_version", {}).get("const") == "2.0.0"
            ),
            output_schema,
        )
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
    packet_workflow = workflow_for_version(str(packet.get("workflow_version")))
    timeout = int(next(
        item for item in packet_workflow["states"] if item.get("id") == packet["stage"]
    ).get("timeout_seconds", 900))
    started = time.monotonic()
    if kind == "codex-cli":
        try:
            result = execute_task_packet(
                packet_path,
                None,
                model=str(route["model"]),
                timeout_seconds=timeout,
                executable=str(provider.get("executable", "codex")),
                reasoning_effort=str(provider.get("reasoning_effort", "high")),
            )
        except CodexExecError as exc:
            raise FlowError(f"Codex CLI provider failed: {exc}", EXIT_FAILED, exc.details) from exc
        raw = result.output_text
        transport = {"kind": kind, **result.receipt}
    elif kind == "command":
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


def current_packet(
    directory: Path,
    run: dict[str, Any],
    *,
    requested_route: str | None = None,
    allow_canary: bool = False,
) -> tuple[Path, dict[str, Any]]:
    prefix = f"task-packet:{run['state']}:"
    item = next((entry for entry in reversed(run.get("artifact_index", [])) if str(entry.get("type", "")).startswith(prefix)), None)
    if item:
        path = directory / item["path"]
        packet = load_json(path)
        if not requested_route:
            return path, packet
        chosen = packet.get("selected_route", {}).get("chosen") or {}
        chosen_key = f"{chosen.get('provider')}:{chosen.get('model')}"
        if chosen_key == requested_route and bool(chosen.get("canary_execution")) == bool(allow_canary):
            return path, packet
    return task_packet(directory, run, requested_route=requested_route, allow_canary=allow_canary)


def latest_model_call_route(directory: Path, run: dict[str, Any], stage: str, attempt: int) -> dict[str, Any] | None:
    expected_type = f"model-call:{stage}:{attempt}"
    item = next((entry for entry in reversed(run.get("artifact_index", [])) if entry.get("type") == expected_type), None)
    if not item:
        return None
    value = load_json(directory / item["path"])
    route = value.get("route")
    return route if isinstance(route, dict) else None


def update_writing_provenance(
    directory: Path,
    run: dict[str, Any],
    stage: str,
    route: dict[str, Any] | None,
) -> None:
    if not is_v3_run(run) or stage not in V3_WRITING_STATES or not route:
        return
    experiment = run.setdefault("model_experiment", {})
    assigned = str(experiment.get("assigned_model_id") or "")
    actual_model = str(route.get("model") or route.get("model_id") or route.get("requested_model") or "")
    actual_provider = str(route.get("provider") or route.get("provider_id") or experiment.get("provider_id") or "")
    if not actual_model:
        raise FlowError(f"Accepted {stage} output lacks exact model provenance", EXIT_INTEGRITY, route)
    actual_models = experiment.setdefault("actual_models", [])
    if actual_model not in actual_models:
        actual_models.append(actual_model)
    contaminated = bool(experiment.get("contaminated") or (assigned and actual_model != assigned) or len(actual_models) > 1)
    experiment["active_model_id"] = actual_model
    experiment["contaminated"] = contaminated
    experiment.setdefault("stage_routes", {})[stage] = {
        "provider_id": actual_provider,
        "assigned_model_id": assigned,
        "actual_model_id": actual_model,
        "public_display_name": writing_model_policy()["display_names"].get(actual_model, public_model_name(actual_model)),
        "fallback": bool(assigned and actual_model != assigned),
        "accepted_at": utc_now(),
    }
    append_event(directory, run, "WRITING_MODEL_ACCEPTED", "controller", {
        "stage": stage,
        "assigned_model_id": assigned,
        "actual_model_id": actual_model,
        "provider_id": actual_provider,
        "contaminated": contaminated,
    })
    save_run(directory, run)


def command_execute_stage(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    if run["state"] not in MODEL_STATES:
        raise FlowError(f"State {run['state']} is deterministic or complete and cannot invoke a model")
    if args.canary and not args.route:
        raise FlowError("--canary requires an exact --route PROVIDER:MODEL", EXIT_USAGE)
    packet_path, packet = current_packet(
        directory,
        run,
        requested_route=args.route,
        allow_canary=bool(args.canary),
    )
    route_set = packet["selected_route"]
    routes = [route_set.get("chosen"), *route_set.get("fallbacks", [])]
    routes = [item for item in routes if isinstance(item, dict)]
    if args.route:
        chosen = route_set.get("chosen") or {}
        chosen_key = f"{chosen.get('provider')}:{chosen.get('model')}"
        if chosen_key != args.route:
            raise FlowError("Hash-bound task packet does not select the requested route", EXIT_INTEGRITY, route_set)
        routes = [chosen]
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
                "canary_execution": bool(route.get("canary_execution")),
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
            key = f"{route.get('provider')}:{route.get('model')}"
            stage_failures = run.setdefault("route_failures", {}).setdefault(run["state"], {})
            stage_failures[key] = int(stage_failures.get(key, 0)) + 1
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
                        if not (200 <= status < 400 or status in {0, 401, 403, 429, 999}):
                            findings.append({"criterion": "source_resolution", "artifact": str(submission), "location": str(claim.get("claim_id")), "finding": f"Source URL did not resolve during independent verification (HTTP {status}).", "repair_instruction": "Repair the source, use another direct source, qualify/omit, or escalate."})
        if state == "VOICE_PROBE":
            candidates = [str(item.get("candidate_id")) for item in value.get("candidates", []) if isinstance(item, dict)]
            orders = value.get("comparison_orders", [])
            if len(candidates) >= 2 and not any(list(order) == list(reversed(candidates)) for order in orders if isinstance(order, list)):
                findings.append({"criterion": "order_reversal", "artifact": str(submission), "location": "comparison_orders", "finding": "The voice comparison does not include a reversed candidate order.", "repair_instruction": "Include both forward and reversed comparison orders to expose position bias."})
            if is_v3_run(run):
                if value.get("operator_selection") is not None:
                    findings.append({"criterion": "operator_selection_authority", "artifact": str(submission), "location": "operator_selection", "finding": "A model-authored voice probe attempted to pre-fill the operator's choice.", "repair_instruction": "Return operator_selection as null; only choose-voice may record this decision."})
                draft_path = artifact_path(directory, run, "draft")
                ledger_path = artifact_path(directory, run, "verified-claim-ledger")
                profile_path = artifact_path(directory, run, "voice-profile")
                assignment_path = artifact_path(directory, run, "model-assignment")
                bindings = {
                    "rough_draft_sha256": draft_path,
                    "claim_ledger_sha256": ledger_path,
                    "voice_profile_sha256": profile_path,
                    "model_assignment_sha256": assignment_path,
                }
                for field, bound_path in bindings.items():
                    if field in value and (not bound_path or value.get(field) != sha256_path(bound_path)):
                        findings.append({"criterion": "voice_probe_binding", "artifact": str(submission), "location": field, "finding": f"{field} does not match the current run artifact.", "repair_instruction": "Regenerate the probe from the exact task-packet inputs."})
                source_anchor = value.get("source_anchor", {})
                source_passage = str(source_anchor.get("source_passage") or "") if isinstance(source_anchor, dict) else ""
                if source_passage and source_anchor.get("source_passage_sha256") != sha256_bytes(source_passage.encode("utf-8")):
                    findings.append({"criterion": "source_anchor_hash", "artifact": str(submission), "location": "source_anchor.source_passage_sha256", "finding": "Source passage hash is incorrect.", "repair_instruction": "Hash the exact UTF-8 source passage."})
                if draft_path and source_passage not in draft_path.read_text(encoding="utf-8"):
                    findings.append({"criterion": "source_anchor", "artifact": str(submission), "location": "source_anchor.source_passage", "finding": "The quoted source passage is not present in the bound rough draft.", "repair_instruction": "Select one exact rough-draft passage and preserve its verified meaning."})
                raw_candidates = [item for item in value.get("candidates", []) if isinstance(item, dict)]
                candidate_ids = [str(item.get("candidate_id")) for item in raw_candidates]
                if len(raw_candidates) != 3 or len(set(candidate_ids)) != 3:
                    findings.append({"criterion": "exactly_three_voice_variants", "artifact": str(submission), "location": "candidates", "finding": "Voice probe must contain exactly three uniquely identified candidates.", "repair_instruction": "Return exactly three one-paragraph variants."})
                claim_sets = []
                for item in raw_candidates:
                    passage = str(item.get("passage") or "")
                    if item.get("passage_sha256") != sha256_bytes(passage.encode("utf-8")):
                        findings.append({"criterion": "candidate_hash", "artifact": str(submission), "location": str(item.get("candidate_id")), "finding": "Candidate passage hash is incorrect.", "repair_instruction": "Hash the exact UTF-8 candidate passage."})
                    paragraphs = [part for part in re.split(r"\n\s*\n", passage.strip()) if part.strip()]
                    if len(paragraphs) != 1:
                        findings.append({"criterion": "one_paragraph_variant", "artifact": str(submission), "location": str(item.get("candidate_id")), "finding": "A voice candidate is not exactly one paragraph.", "repair_instruction": "Return one paragraph per candidate."})
                    claim_sets.append(tuple(sorted(str(claim) for claim in item.get("preserved_claim_ids", []))))
                if claim_sets and len(set(claim_sets)) != 1:
                    findings.append({"criterion": "shared_verified_meaning", "artifact": str(submission), "location": "candidates.preserved_claim_ids", "finding": "Candidates do not preserve the same verified claim set.", "repair_instruction": "Hold meaning and claims constant; vary only the declared voice dimensions."})
                if len(orders) != 2 or any(set(order) != set(candidate_ids) for order in orders if isinstance(order, list)) or (len(orders) == 2 and list(orders[1]) != list(reversed(orders[0]))):
                    findings.append({"criterion": "balanced_comparison_orders", "artifact": str(submission), "location": "comparison_orders", "finding": "Comparison orders must contain the same three IDs in forward and reverse order.", "repair_instruction": "Provide one order and its exact reverse."})
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
        for finding in forbidden_public_prose_character_findings(text):
            findings.append({**finding, "artifact": str(submission)})
        findings.extend(style_phrase_findings(text, str(submission)))
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


def baseline_voice_profile_path() -> Path:
    return SPEC_ROOT / "profiles" / "voice-profile.v1.json"


def _voice_profile_path_for_version(version: str) -> Path | None:
    root = voice_state_root() / "profiles"
    for candidate in sorted(root.glob("*.json")) if root.is_dir() else []:
        try:
            if load_json(candidate).get("version") == version:
                return candidate
        except FlowError:
            continue
    return None


def _initialize_voice_runtime_locked() -> tuple[dict[str, Any], Path, dict[str, Any]]:
    """Load a verified current profile, seeding it from the protected baseline once."""
    root = voice_state_root()
    profiles = root / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    baseline_path = baseline_voice_profile_path()
    baseline = load_json(baseline_path)
    baseline_hash = sha256_path(baseline_path)
    current_path = root / "current.json"
    if not current_path.is_file():
        stored_baseline = profiles / f"baseline-{baseline_hash[:16]}.json"
        if not stored_baseline.is_file():
            write_json(stored_baseline, baseline)
        pointer = {
            "voice_profile_pointer_schema_version": "1.0.0",
            "profile_id": baseline["profile_id"],
            "current_version": baseline["version"],
            "profile_sha256": sha256_path(stored_baseline),
            "updated_at": utc_now(),
            "source_learning_record_id": None,
            "previous_version": None,
        }
        write_json(current_path, pointer)
    pointer = load_json(current_path)
    pointer_errors = validate_instance_schema(pointer, "voice-profile-pointer.schema.json")
    if pointer_errors:
        raise FlowError("The runtime voice-profile pointer is invalid", EXIT_INTEGRITY, pointer_errors)
    profile_path = _voice_profile_path_for_version(str(pointer.get("current_version")))
    if not profile_path:
        raise FlowError("The active runtime voice-profile pointer names a missing version", EXIT_INTEGRITY, pointer)
    if pointer.get("profile_sha256") != sha256_path(profile_path):
        raise FlowError("The active runtime voice profile changed after activation", EXIT_INTEGRITY, pointer)
    profile = load_json(profile_path)
    errors = validate_instance_schema(profile, "voice-profile.schema.json")
    if errors:
        raise FlowError("The active runtime voice profile is invalid", EXIT_INTEGRITY, errors)
    if profile.get("profile_id") != baseline.get("profile_id") or profile.get("profile_id") != pointer.get("profile_id") or profile.get("version") != pointer.get("current_version"):
        raise FlowError("The active runtime voice profile identity does not match its pointer", EXIT_INTEGRITY, pointer)
    return profile, profile_path, pointer


def active_voice_profile() -> tuple[dict[str, Any], Path, dict[str, Any]]:
    with shared_lock(voice_state_root() / ".lock"):
        return _initialize_voice_runtime_locked()


def snapshot_voice_profile(
    directory: Path,
    run: dict[str, Any],
    profile: dict[str, Any],
    *,
    source: str,
    inputs: Iterable[str] = (),
) -> Path:
    version = str(profile.get("version") or "unknown")
    destination = directory / "artifacts" / f"voice-profile-{slugify(version, 80)}.json"
    write_json(destination, profile)
    record_artifact(
        directory,
        run,
        destination,
        "voice-profile",
        {"actor": "controller", "source": source, "version": CONTROLLER_VERSION},
        inputs=inputs,
    )
    return destination


def voice_history() -> dict[str, Any]:
    root = voice_state_root()
    pointer = load_json(root / "current.json") if (root / "current.json").is_file() else None
    profiles = []
    for path in sorted((root / "profiles").glob("*.json")) if (root / "profiles").is_dir() else []:
        value = load_json(path)
        profiles.append({
            "version": value.get("version"),
            "status": value.get("status"),
            "sha256": sha256_path(path),
            "path": str(path),
            "active": bool(pointer and pointer.get("profile_sha256") == sha256_path(path)),
            "source_learning_record_id": value.get("source_learning_record_id"),
        })
    evidence = _read_jsonl(root / "evidence.jsonl")
    rollbacks = _read_jsonl(root / "rollbacks.jsonl")
    return {
        "ok": True,
        "current_version": pointer.get("current_version") if pointer else None,
        "current": pointer,
        "profiles": profiles,
        "evidence_count": len(evidence),
        "evidence": evidence,
        "rollbacks": rollbacks,
    }


def rollback_voice_profile(version: str) -> dict[str, Any]:
    root = voice_state_root()
    with shared_lock(root / ".lock"):
        _, _, prior_pointer = _initialize_voice_runtime_locked()
        destination = _voice_profile_path_for_version(version)
        if not destination:
            raise FlowError(f"Unknown runtime voice-profile version: {version}", EXIT_USAGE)
        profile = load_json(destination)
        pointer = {
            "voice_profile_pointer_schema_version": "1.0.0",
            "profile_id": profile["profile_id"],
            "current_version": profile["version"],
            "profile_sha256": sha256_path(destination),
            "updated_at": utc_now(),
            "source_learning_record_id": profile.get("source_learning_record_id"),
            "previous_version": prior_pointer.get("current_version"),
        }
        write_json(root / "current.json", pointer)
        rollback = {
            "rollback_id": f"VR-{secrets.token_hex(8)}",
            "from_version": prior_pointer.get("current_version"),
            "to_version": version,
            "created_at": utc_now(),
        }
        _append_jsonl(root / "rollbacks.jsonl", rollback)
    return {"ok": True, "current_version": version, "prior_version": prior_pointer.get("current_version"), "rollback": rollback}


def _learning_candidate(candidate: dict[str, Any]) -> dict[str, str]:
    passage = str(candidate.get("passage") or "")
    passage_hash = str(candidate.get("passage_sha256") or "")
    if sha256_bytes(passage.encode("utf-8")) != passage_hash:
        raise FlowError("A voice-probe candidate passage does not match its recorded hash", EXIT_INTEGRITY, candidate.get("candidate_id"))
    return {
        "candidate_id": str(candidate.get("candidate_id")),
        "passage": passage,
        "passage_sha256": passage_hash,
    }


def apply_voice_learning(directory: Path, run: dict[str, Any]) -> dict[str, Any]:
    """Promote one operator selection into a reversible provisional runtime overlay."""
    if not is_v3_run(run) or run.get("state") != "VOICE_LEARNING":
        raise FlowError("Voice learning requires a workflow 3 run in VOICE_LEARNING", EXIT_USAGE)
    probe_path = artifact_path(directory, run, "voice-probe")
    draft_path = artifact_path(directory, run, "draft")
    ledger_path = artifact_path(directory, run, "verified-claim-ledger")
    prior_run_profile_path = artifact_path(directory, run, "voice-profile")
    if not all((probe_path, draft_path, ledger_path, prior_run_profile_path)):
        raise FlowError("Voice learning is missing its probe, rough draft, verified claims, or prior profile", EXIT_INTEGRITY)
    probe = load_json(probe_path)
    if probe.get("voice_probe_schema_version") != "2.0.0":
        raise FlowError("Workflow 3 voice learning requires a bound version 2 voice probe", EXIT_INTEGRITY)
    selection = probe.get("operator_selection")
    if not isinstance(selection, dict) or not selection.get("candidate_id"):
        raise FlowError("Voice learning requires the operator's selected candidate", EXIT_APPROVAL)
    if probe.get("rough_draft_sha256") != sha256_path(draft_path):
        raise FlowError("The voice probe is not bound to the current rough draft", EXIT_INTEGRITY)
    if probe.get("claim_ledger_sha256") != sha256_path(ledger_path):
        raise FlowError("The voice probe is not bound to the current verified claim ledger", EXIT_INTEGRITY)
    candidates = [item for item in probe.get("candidates", []) if isinstance(item, dict)]
    selected_raw = next((item for item in candidates if item.get("candidate_id") == selection.get("candidate_id")), None)
    rejected_raw = [item for item in candidates if item.get("candidate_id") != selection.get("candidate_id")]
    if selected_raw is None or len(candidates) != 3 or len(rejected_raw) != 2:
        raise FlowError("Voice learning requires one selection from exactly three candidates", EXIT_INTEGRITY)
    selected = _learning_candidate(selected_raw)
    rejected = [_learning_candidate(item) for item in rejected_raw]
    controlled_dimensions = sorted({
        str(dimension)
        for item in candidates
        for dimension in item.get("intended_dimensions", [])
        if str(dimension)
    })
    if not controlled_dimensions:
        raise FlowError("Voice probe did not declare controlled dimensions", EXIT_INTEGRITY)
    voice_probe_hash = sha256_path(probe_path)
    idempotency_key = sha256_bytes(canonical_json({
        "run_id": run["run_id"],
        "voice_probe_sha256": voice_probe_hash,
        "operator_selection": selection,
    }))
    root = voice_state_root()
    idempotent = False
    with shared_lock(root / ".lock"):
        prior_profile, _, pointer = _initialize_voice_runtime_locked()
        evidence = _read_jsonl(root / "evidence.jsonl")
        existing = next((item for item in evidence if item.get("idempotency_key") == idempotency_key), None)
        if existing:
            learning = existing
            profile_path = _voice_profile_path_for_version(str(learning.get("new_profile_version")))
            if not profile_path:
                raise FlowError("Voice-learning evidence names a missing immutable profile", EXIT_INTEGRITY, learning)
            profile = load_json(profile_path)
            if pointer.get("current_version") != profile.get("version"):
                resumed_pointer = {
                    "voice_profile_pointer_schema_version": "1.0.0",
                    "profile_id": profile["profile_id"],
                    "current_version": profile["version"],
                    "profile_sha256": sha256_path(profile_path),
                    "updated_at": utc_now(),
                    "source_learning_record_id": learning["record_id"],
                    "previous_version": pointer.get("current_version"),
                }
                write_json(root / "current.json", resumed_pointer)
            idempotent = True
        else:
            record_id = f"VL-{idempotency_key[:20]}"
            new_version = f"runtime-{len(evidence) + 1:06d}-{idempotency_key[:10]}"
            pair_ids = [f"VP-{idempotency_key[:10]}-{index}" for index in range(1, 3)]
            positive_id = f"VE-{idempotency_key[:16]}"
            guidance_id = f"VG-{idempotency_key[:16]}"
            feedback = selection.get("feedback")
            dimension_text = ", ".join(controlled_dimensions)
            guidance_text = (
                f"For similar passages controlling {dimension_text}, prefer the selected example over its two rejected alternatives. "
                + (f"Operator note: {feedback}" if feedback else "Treat this as local provisional evidence, not a global voice trait.")
            )
            created_at = utc_now()
            experiment = run.get("model_experiment", {})
            stage_route = experiment.get("stage_routes", {}).get("VOICE_PROBE", {})
            writing_model_id = str(stage_route.get("actual_model_id") or experiment.get("active_model_id") or experiment.get("assigned_model_id") or "")
            provider_id = str(stage_route.get("provider_id") or experiment.get("provider_id") or "")
            if not writing_model_id or not provider_id:
                raise FlowError("Voice learning lacks exact writing-model provenance", EXIT_INTEGRITY)
            learning = {
                "voice_learning_schema_version": "1.0.0",
                "record_id": record_id,
                "run_id": run["run_id"],
                "idempotency_key": idempotency_key,
                "created_at": created_at,
                "voice_probe_sha256": voice_probe_hash,
                "rough_draft_sha256": sha256_path(draft_path),
                "claim_ledger_sha256": sha256_path(ledger_path),
                "prior_profile_version": prior_profile["version"],
                "new_profile_version": new_version,
                "selected_candidate": selected,
                "rejected_candidates": rejected,
                "controlled_dimensions": controlled_dimensions,
                "operator_feedback": feedback if isinstance(feedback, str) else None,
                "writing_model": {
                    "provider_id": provider_id,
                    "model_id": writing_model_id,
                    "public_display_name": writing_model_policy()["display_names"].get(writing_model_id, public_model_name(writing_model_id)),
                },
                "profile_update": {
                    "status": "provisional",
                    "activated": True,
                    "guidance_added": [guidance_id],
                    "guidance_refined": [],
                    "runtime_guidance_retired": [],
                    "positive_example_ids": [positive_id],
                    "pair_ids": pair_ids,
                },
            }
            learning_errors = validate_instance_schema(learning, "voice-learning.schema.json")
            if learning_errors:
                raise FlowError("Controller generated an invalid voice-learning record", EXIT_INTEGRITY, learning_errors)
            profile = json.loads(json.dumps(prior_profile))
            profile["version"] = new_version
            profile["status"] = "provisional"
            profile["parent_version"] = prior_profile["version"]
            profile["base_profile_sha256"] = sha256_path(baseline_voice_profile_path())
            profile["source_learning_record_id"] = record_id
            profile.setdefault("provisional_guidance", []).append({
                "guidance_id": guidance_id,
                "text": guidance_text,
                "status": "provisional",
                "source_record_id": record_id,
                "created_at": created_at,
                "dimensions": controlled_dimensions,
            })
            profile.setdefault("positive_examples", []).append({
                "example_id": positive_id,
                "status": "operator_selected_voice_probe_provisional",
                "run_id": run["run_id"],
                "candidate_id": selected["candidate_id"],
                "passage": selected["passage"],
                "source_record_id": record_id,
                "operator_confirmation": True,
            })
            for pair_id, rejected_candidate in zip(pair_ids, rejected):
                profile.setdefault("accepted_rejected_pairs", []).append({
                    "pair_id": pair_id,
                    "status": "operator_selected_provisional",
                    "run_id": run["run_id"],
                    "accepted_candidate": selected,
                    "rejected_candidate": rejected_candidate,
                    "operator_feedback": learning["operator_feedback"],
                    "source_record_id": record_id,
                })
            profile.setdefault("change_history", []).append({
                "version": new_version,
                "date": dt.date.today().isoformat(),
                "status": "provisional",
                "reason": f"Immediate runtime overlay from operator voice selection {record_id}; protected baseline remains unchanged.",
            })
            profile_errors = validate_instance_schema(profile, "voice-profile.schema.json")
            if profile_errors:
                raise FlowError("Controller generated an invalid runtime voice profile", EXIT_INTEGRITY, profile_errors)
            profile_path = root / "profiles" / f"{slugify(new_version, 80)}-{sha256_bytes(canonical_json(profile))[:12]}.json"
            write_json(profile_path, profile)
            _append_jsonl(root / "evidence.jsonl", learning)
            new_pointer = {
                "voice_profile_pointer_schema_version": "1.0.0",
                "profile_id": profile["profile_id"],
                "current_version": new_version,
                "profile_sha256": sha256_path(profile_path),
                "updated_at": utc_now(),
                "source_learning_record_id": record_id,
                "previous_version": prior_profile["version"],
            }
            pointer_errors = validate_instance_schema(new_pointer, "voice-profile-pointer.schema.json")
            if pointer_errors:
                raise FlowError("Controller generated an invalid voice-profile pointer", EXIT_INTEGRITY, pointer_errors)
            write_json(root / "current.json", new_pointer)
    learning_path = directory / "artifacts" / "voice-learning.json"
    write_json(learning_path, learning)
    learning_artifact = record_artifact(
        directory,
        run,
        learning_path,
        "voice-learning",
        {"actor": "controller", "version": CONTROLLER_VERSION, "idempotent": idempotent},
        inputs=[item["artifact_id"] for item in run.get("artifact_index", []) if item.get("type") in {"voice-probe", "draft", "verified-claim-ledger", "voice-profile"}],
    )
    snapshot_voice_profile(directory, run, profile, source=str(profile_path), inputs=[learning_artifact["artifact_id"]])
    write_gate_receipt(directory, run, "G-VOICE-LEARNING", "PASS", [], {"type": "code", "version": CONTROLLER_VERSION})
    append_event(directory, run, "VOICE_LEARNING_APPLIED", "controller", {
        "record_id": learning["record_id"],
        "idempotency_key": learning["idempotency_key"],
        "new_profile_version": learning["new_profile_version"],
        "idempotent": idempotent,
    })
    transition(directory, run, "EDIT", "controller", "Selected voice evidence activated as a provisional runtime profile")
    return {"ok": True, "idempotent": idempotent, "learning": learning, "profile_path": str(profile_path), "state": run["state"]}


def record_static_controls(directory: Path, run: dict[str, Any]) -> None:
    controls = [(SPEC_ROOT / "10-Final-Prose-Naturalization" / "Final-Prose-Naturalization-Directive.md", "naturalization-directive")]
    if is_v3_run(run):
        profile, source_path, _ = active_voice_profile()
        snapshot_voice_profile(directory, run, profile, source=str(source_path))
    else:
        controls.insert(0, (baseline_voice_profile_path(), "voice-profile"))
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
    if is_v3_run(run):
        style_value = policy().get("style_gate", {})
        style_path = directory / "artifacts" / "style-policy.json"
        write_json(style_path, {
            "style_policy_schema_version": "1.0.0",
            "policy_sha256": sha256_bytes(canonical_json(style_value)),
            "policy": style_value,
        })
        record_artifact(directory, run, style_path, "style-policy", {"actor": "controller", "version": CONTROLLER_VERSION})
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
    if run.get("status") == "BLOCKED":
        definition = state_definition(state, run)
        return {"action": "repair_required", "run_id": run["run_id"], "state": state, "gate": definition.get("gate"), "command": ["article-flow", "repair", run["run_id"], definition.get("gate")]}
    review_artifact = {
        "INTENT_REVIEW": "intent-candidate",
        "ARTICLE_RECIPE": "article-recipe",
        "VOICE_PROBE": "voice-probe",
        "EDITORIAL_QA": "editorial-qa",
    }
    if state in REVIEW_STATES and artifact(run, review_artifact[state]):
        if is_v3_run(run) and state == "VOICE_PROBE":
            probe = json_artifact(directory, run, "voice-probe") or {}
            candidates = [
                {
                    "candidate_id": item.get("candidate_id"),
                    "passage": item.get("passage"),
                    "controlled_dimensions": item.get("controlled_dimensions") or item.get("intended_dimensions"),
                }
                for item in probe.get("candidates", [])
                if isinstance(item, dict)
            ]
            run["status"] = "WAITING_HUMAN"
            save_run(directory, run)
            return {
                "action": "human_decision",
                "run_id": run["run_id"],
                "state": state,
                "question": "Which one of these three paragraphs sounds most like you? You may add a short reason, but it is optional.",
                "candidates": candidates,
                "selection_commands": {
                    str(item["candidate_id"]): ["article-flow", "choose-voice", run["run_id"], str(item["candidate_id"]), "--auto"]
                    for item in candidates
                },
            }
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
            "approval_command": ["article-flow", "gate", run["run_id"], state_definition(state, run)["gate"], "--outcome", "PASS"],
        }
    if state == "VOICE_LEARNING":
        return {"action": "run_command", "run_id": run["run_id"], "state": state, "command": ["article-flow", "voice", "apply", run["run_id"]]}
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
        approval = json_artifact(directory, run, "publish-approval")
        if approval and parse_time(approval["expires_at"]) <= dt.datetime.now(dt.timezone.utc):
            run["status"] = "WAITING_HUMAN"
            save_run(directory, run)
            return {
                "action": "human_decision",
                "run_id": run["run_id"],
                "state": state,
                "question": "The unchanged scoped publication approval expired. Renew this exact target, package revision, and plan before retrying or attesting deployment?",
                "expired_approval_id": approval.get("approval_id"),
                "plan": str(directory / "publication" / "plan.json"),
                "approval_command": ["article-flow", "publish", "--renew-approval", run["run_id"]],
            }
        handoff = artifact_path(directory, run, "publication-handoff")
        if handoff and handoff.is_file():
            handoff_value = load_json(handoff)
            run["status"] = "WAITING_HUMAN"
            save_run(directory, run)
            return {
                "action": "human_action",
                "run_id": run["run_id"],
                "state": state,
                "question": "Publishing needs a credentialed local host. Complete the one handoff, then run the attestation command.",
                "handoff": str(handoff),
                "retry_command": handoff_value["retry_command"],
                "attestation_command": handoff_value["attestation_command"],
            }
        return {"action": "run_command", "run_id": run["run_id"], "state": state, "command": ["article-flow", "publish", "--execute", run["run_id"], "--approval", "APPROVAL_ID", "--commit", "--push"]}
    if state == "LIVE_VERIFICATION":
        return {"action": "run_command", "run_id": run["run_id"], "state": state, "command": ["article-flow", "verify-live", run["run_id"]]}
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
    default_mode = str(policy().get("automation", {}).get("default_mode", "active_session"))
    automation_mode = "active_session" if bool(getattr(args, "auto", False)) or default_mode == "active_session" else "manual"
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
        "run_overrides": {
            "intent_approval": "policy",
            "recipe_approval": "policy",
            "voice_probe_approval": "required",
            "editorial_approval": "policy",
            "automation_mode": automation_mode,
            "auto_publish": not bool(getattr(args, "hold_before_publish", False)),
        },
        "publication": {},
        "route_failures": {},
    }
    save_run(directory, run)
    append_event(directory, run, "RUN_CREATED", "controller", {"workflow_version": run["workflow_version"], "controller_version": CONTROLLER_VERSION})
    assignment = reserve_draft_model(run_id, getattr(args, "draft_model", None)) if is_v3_run(run) else None
    if assignment:
        assignment_path = directory / "artifacts" / "model-assignment.json"
        write_json(assignment_path, assignment)
        record_artifact(
            directory,
            run,
            assignment_path,
            "model-assignment",
            {"actor": "controller", "version": CONTROLLER_VERSION},
        )
        run["model_experiment"] = {
            "pool_id": assignment["pool_id"],
            "pool_version": assignment["pool_version"],
            "provider_id": assignment["provider_id"],
            "assigned_model_id": assignment["assigned_model_id"],
            "active_model_id": assignment["assigned_model_id"],
            "public_display_name": assignment["public_display_name"],
            "actual_models": [],
            "stage_routes": {},
            "contaminated": False,
        }
        append_event(directory, run, "MODEL_ASSIGNED", "controller", {
            "pool_id": assignment["pool_id"],
            "rotation_index": assignment["rotation_index"],
            "provider_id": assignment["provider_id"],
            "model_id": assignment["assigned_model_id"],
            "override": assignment["override"],
        })
        save_run(directory, run)
    seed_path = directory / "artifacts" / "seed.txt"
    atomic_write(seed_path, seed.encode("utf-8"))
    record_artifact(directory, run, seed_path, "seed", {"actor": "operator", "preserved_verbatim": True})
    record_static_controls(directory, run)
    transition(directory, run, "INTAKE", "controller", "Run identity and event chain created")
    write_gate_receipt(directory, run, "G-SEED-PRESERVED", "PASS", [], {"type": "code", "version": CONTROLLER_VERSION})
    transition(directory, run, "RESEARCH_PLAN", "controller", "Seed bytes recorded verbatim")
    next_command = ["article-flow", "advance", run_id] if automation_enabled(run) else ["article-flow", "next", run_id]
    payload = {
        "ok": True,
        "run_id": run_id,
        "state": run["state"],
        "run_directory": str(directory),
        "draft_model": assignment["assigned_model_id"] if assignment else None,
        "next_command": next_command,
    }
    if bool(getattr(args, "auto", False)):
        return command_advance(argparse.Namespace(run_id=run_id, max_steps=100, json=args.json))
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


def run_summary(directory: Path, run: dict[str, Any]) -> dict[str, Any]:
    seed_path = artifact_path(directory, run, "seed")
    seed = seed_path.read_text(encoding="utf-8") if seed_path and seed_path.is_file() else ""
    live = json_artifact(directory, run, "live-verification") or {}
    return {
        "run_id": run["run_id"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
        "state": run["state"],
        "status": run["status"],
        "seed_preview": re.sub(r"\s+", " ", seed).strip()[:180],
        "live_url": live.get("url"),
        "run_directory": str(directory),
    }


def command_list(args: argparse.Namespace) -> int:
    summaries = []
    for path in sorted(runs_root().glob("AF-*"), key=lambda item: (item.stat().st_mtime_ns, item.name), reverse=True):
        if not path.is_dir() or not (path / "run.json").is_file():
            continue
        try:
            directory, run = load_run(path.name)
        except FlowError:
            continue
        summaries.append(run_summary(directory, run))
    payload = {
        "ok": True,
        "count": len(summaries),
        "process_root": str(SPEC_ROOT),
        "captured_material_root": str(runs_root()),
        "published_material_root": str((publication_repo_root() or REPO_ROOT) / "docs"),
        "runs": summaries,
    }
    emit(payload, args.json)
    return EXIT_OK


def command_status(args: argparse.Namespace) -> int:
    selected_run_id = args.run_id or latest_run_id()
    directory, run = load_run(selected_run_id)
    compatibility_warning = None
    if run.get("controller_version") != CONTROLLER_VERSION:
        compatibility_warning = (
            f"Run was created by article-flow {run.get('controller_version')}; "
            f"the active controller is {CONTROLLER_VERSION}. Continue only through commands returned by the active controller."
        )
    payload = {
        **run,
        "run_directory": str(directory),
        "event_log_integrity": True,
        "derived_state": run["state"],
        "compatibility_warning": compatibility_warning,
    }
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


def approve_review_artifact(directory: Path, run: dict[str, Any], state: str, *, actor: str) -> Path:
    type_map = {
        "INTENT_REVIEW": ("intent-candidate", "intent"),
        "ARTICLE_RECIPE": ("article-recipe", "article-recipe"),
        "VOICE_PROBE": ("voice-probe", "voice-probe"),
        "EDITORIAL_QA": ("editorial-qa", "editorial-qa"),
    }
    candidate_type, approved_type = type_map[state]
    candidate_path = artifact_path(directory, run, candidate_type)
    if not candidate_path or not candidate_path.is_file():
        raise FlowError(f"Candidate artifact is missing for {state}", EXIT_INTEGRITY)
    approved_path = directory / "artifacts" / f"approved-{approved_type}{candidate_path.suffix}"
    if candidate_path.resolve() != approved_path.resolve():
        shutil.copy2(candidate_path, approved_path)
    record_artifact(
        directory,
        run,
        approved_path,
        approved_type,
        {"actor": actor, "decision": "policy_validated" if actor == "policy" else "confirmed"},
        inputs=[artifact(run, candidate_type)["artifact_id"]] if artifact(run, candidate_type) else [],
    )
    return approved_path


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
        packet_route = latest_model_call_route(directory, run, args.stage, attempt)
        if packet_route is None and packet_item:
            packet_route = packet_value.get("selected_route", {}).get("chosen")
        record_artifact(directory, run, destination, artifact_type, {"actor": "model_or_host", "route": packet_route}, inputs=[item["artifact_id"] for item in run["artifact_index"]])
        if args.stage == "CLAIM_VERIFICATION" and outcome == "PASS":
            lock_verified_fields(directory, run, destination)
        definition = state_definition(args.stage, run)
        policy_review = outcome == "PASS" and automation_enabled(run) and args.stage in AUTO_REVIEW_STATES
        human_review = outcome == "PASS" and args.stage in REVIEW_STATES and not policy_review
        recorded_outcome = "ESCALATE" if human_review else outcome
        review_findings = findings
        if recorded_outcome == "ESCALATE" and not review_findings:
            review_findings = [{
                "criterion": "operator_owned_judgment",
                "artifact": str(destination),
                "location": None,
                "finding": "Mechanical validation passed; the controlling editorial judgment has not been inferred.",
                "repair_instruction": "Ask the operator the controller-supplied decision question.",
            }]
        evaluator = (
            {"type": "policy", "version": CONTROLLER_VERSION, "basis": "schema_and_code_validation"}
            if policy_review
            else {"type": "code", "version": CONTROLLER_VERSION}
        )
        write_gate_receipt(directory, run, definition["gate"], recorded_outcome, review_findings, evaluator, definition.get("repair_state"))
        if outcome != "PASS":
            if packet_route:
                key = f"{packet_route.get('provider')}:{packet_route.get('model')}"
                stage_failures = run.setdefault("route_failures", {}).setdefault(args.stage, {})
                stage_failures[key] = int(stage_failures.get(key, 0)) + 1
                append_event(directory, run, "MODEL_OUTPUT_REJECTED", "controller", {"state": args.stage, "route": packet_route, "failure_count": stage_failures[key], "findings": findings})
            attempts_used = int(run.get("attempts", {}).get(args.stage, 0))
            maximum = int(definition.get("max_attempts", 1))
            if automation_enabled(run) and attempts_used < maximum and definition.get("repair_state") in MODEL_STATES:
                append_event(directory, run, "REPAIR", "controller", {
                    "gate_id": definition["gate"],
                    "findings": findings,
                    "repair_state": definition["repair_state"],
                    "attempt": attempts_used,
                    "maximum": maximum,
                })
                transition(directory, run, definition["repair_state"], "controller", f"Automatic targeted repair after {definition['gate']}")
                payload = {
                    "ok": False,
                    "outcome": outcome,
                    "state": run["state"],
                    "findings": findings,
                    "next_command": ["article-flow", "advance", run["run_id"]],
                }
                emit(payload, args.json)
                return EXIT_OK
            run["status"] = "BLOCKED"
            save_run(directory, run)
            payload = {"ok": False, "outcome": outcome, "state": run["state"], "findings": findings, "repair_command": ["article-flow", "repair", run["run_id"], definition["gate"]]}
            emit(payload, args.json)
            return EXIT_FAILED
        if packet_route:
            key = f"{packet_route.get('provider')}:{packet_route.get('model')}"
            stage_failures = run.setdefault("route_failures", {}).setdefault(args.stage, {})
            prior_failures = int(stage_failures.pop(key, 0))
            if prior_failures:
                append_event(directory, run, "MODEL_ROUTE_RECOVERED", "controller", {
                    "state": args.stage,
                    "route": packet_route,
                    "cleared_failure_count": prior_failures,
                })
        update_writing_provenance(directory, run, args.stage, packet_route)
        if policy_review:
            approve_review_artifact(directory, run, args.stage, actor="policy")
            transition(directory, run, definition["next_on_pass"], "policy", f"Policy approved validated {args.stage} artifact")
            payload = {"ok": True, "outcome": "PASS", "state": run["state"], "next_command": ["article-flow", "advance", run["run_id"]]}
        elif args.stage in REVIEW_STATES:
            run["status"] = "WAITING_HUMAN"
            save_run(directory, run)
            payload = next_state_payload(directory, run)
        else:
            transition(directory, run, definition["next_on_pass"], "controller", f"{definition['gate']} passed")
            payload = {"ok": True, "outcome": "PASS", "state": run["state"], "next_command": ["article-flow", "next", run["run_id"]]}
    emit(payload, args.json)
    return EXIT_WAITING if payload.get("action") == "human_decision" else EXIT_OK


def create_publish_approval(
    directory: Path,
    run: dict[str, Any],
    plan: dict[str, Any],
    *,
    renewed_from: str | None = None,
    actor: str = "operator",
) -> tuple[str, Path]:
    plan_path = directory / "publication" / "plan.json"
    ttl = int(policy()["publication"]["approval_ttl_minutes"])
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=ttl)
    approval_id = f"AP-{secrets.token_hex(12)}"
    checks: list[dict[str, Any]] = [{"plan_sha256": sha256_path(plan_path)}]
    if is_v3_run(run):
        target_config = load_json(SPEC_ROOT / "publication" / "theproductiveprompter.json")
        allowlisted = policy().get("publication", {}).get("allowlisted_automatic_targets", [])
        expected_policy_hash = style_policy_sha256()
        if actor == "policy" and "publication/theproductiveprompter.json" not in allowlisted:
            raise FlowError("Automatic publication target is not allowlisted", EXIT_APPROVAL, allowlisted)
        if plan.get("target") != target_config.get("target_id"):
            raise FlowError("Publication plan target does not match the configured Productive Prompter target", EXIT_APPROVAL)
        if plan.get("style_policy_sha256") != expected_policy_hash:
            raise FlowError("Style policy changed after packaging; rebuild before approval", EXIT_APPROVAL)
        checks.append({
            "approval_actor": actor,
            "allowlisted_target": "publication/theproductiveprompter.json",
            "style_policy_sha256": expected_policy_hash,
            "package_revision": plan.get("package_revision"),
        })
    if renewed_from:
        checks.append({"renewed_from": renewed_from, "scope_unchanged": True})
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
        "checks": checks,
        "created_at": utc_now(),
    }
    approval_path = directory / "approvals" / f"{approval_id}.json"
    write_json(approval_path, approval)
    errors = validate_json_schema(approval_path, "publication-receipt.schema.json")
    if errors:
        raise FlowError("Controller generated an invalid publication approval", EXIT_INTEGRITY, errors)
    record_artifact(directory, run, approval_path, "publish-approval", {"actor": actor, "renewed_from": renewed_from})
    append_event(directory, run, "POLICY_APPROVAL" if actor == "policy" else "APPROVAL", actor, {
        "approval_id": approval_id,
        "target": plan["target"],
        "package_revision": plan["package_revision"],
        "renewed_from": renewed_from,
        "style_policy_sha256": plan.get("style_policy_sha256"),
    })
    return approval_id, approval_path


def command_gate(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    loaded_state = run["state"]
    definition = state_definition(run["state"], run)
    expected_gate = definition.get("gate")
    args.gate_id = args.gate_id or expected_gate
    if not args.gate_id:
        raise FlowError(f"State {run['state']} has no operator-owned gate", EXIT_USAGE)
    if args.gate_id != expected_gate:
        raise FlowError(f"Gate {args.gate_id} does not control current state {run['state']} (expected {expected_gate})")
    if args.outcome not in workflow_for_run(run)["gate_outcomes"]:
        raise FlowError(f"Invalid gate outcome: {args.outcome}")
    if gate_class(args.gate_id) == "hard" and args.gate_id != "G-PUBLISH-APPROVAL" and args.outcome != "TERMINAL":
        raise FlowError(f"Hard gate {args.gate_id} is code-owned and cannot be manually passed")
    with run_lock(directory, run):
        _, current_run = load_run(args.run_id)
        if current_run["state"] != loaded_state:
            raise FlowError(
                f"Gate state changed concurrently from {loaded_state} to {current_run['state']}; reload before deciding",
                EXIT_WAITING,
            )
        run = current_run
        definition = state_definition(run["state"], run)
        if args.gate_id != definition.get("gate"):
            raise FlowError(f"Gate {args.gate_id} no longer controls current state {run['state']}", EXIT_WAITING)
        findings = []
        if args.finding:
            findings.append({"criterion": "operator_review", "artifact": args.artifact or "current", "location": None, "finding": args.finding, "repair_instruction": args.finding})
        if args.gate_id == "G-PUBLISH-APPROVAL" and args.outcome == "PASS":
            plan_path = directory / "publication" / "plan.json"
            if not plan_path.is_file():
                raise FlowError("Publication plan is missing")
            plan = load_json(plan_path)
            approval_id, _ = create_publish_approval(directory, run, plan)
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
            if run["state"] == "VOICE_PROBE" and is_v3_run(run):
                recorded_item = artifact(run, candidate_type)
                recorded_path = artifact_path(directory, run, candidate_type)
                if not recorded_item or not recorded_path or candidate_path.resolve() != recorded_path.resolve():
                    raise FlowError("Voice selection must use the controller-recorded probe artifact", EXIT_APPROVAL)
                if sha256_path(recorded_path) != recorded_item.get("sha256"):
                    raise FlowError("Recorded voice probe changed after validation", EXIT_INTEGRITY)
                probe_outcome, probe_findings = automatic_gate(directory, run, "VOICE_PROBE", recorded_path)
                if probe_outcome != "PASS":
                    raise FlowError("Recorded voice probe no longer passes its code-owned checks", EXIT_INTEGRITY, probe_findings)
            approved_path = directory / "artifacts" / f"approved-{approved_type}{candidate_path.suffix}"
            if run["state"] == "VOICE_PROBE":
                if not args.selection or (not is_v3_run(run) and not args.feedback):
                    requirement = "--selection CANDIDATE_ID" if is_v3_run(run) else "--selection CANDIDATE_ID and --feedback"
                    raise FlowError(f"Voice-probe approval requires {requirement}", EXIT_APPROVAL)
                value = load_json(candidate_path)
                candidate_ids = {str(item.get("candidate_id")) for item in value.get("candidates", []) if isinstance(item, dict)}
                if args.selection not in candidate_ids:
                    raise FlowError(f"Unknown voice candidate: {args.selection}", EXIT_APPROVAL)
                if is_v3_run(run):
                    value["operator_selection"] = {"candidate_id": args.selection, "selected_at": utc_now(), "feedback": args.feedback or None}
                else:
                    value["operator_selection"] = {"candidate_id": args.selection, "reason": args.feedback, "confirmed_at": utc_now()}
                write_json(approved_path, value)
                selection_errors = validate_json_schema(approved_path, "voice-probe.schema.json")
                if selection_errors:
                    raise FlowError("Selected voice probe is invalid", EXIT_INTEGRITY, selection_errors)
            else:
                same_file = candidate_path.resolve() == approved_path.resolve()
                if not same_file and approved_path.exists():
                    try:
                        same_file = candidate_path.samefile(approved_path)
                    except OSError:
                        same_file = False
                if not same_file:
                    shutil.copy2(candidate_path, approved_path)
            record_artifact(directory, run, approved_path, approved_type, {"actor": "operator", "decision": "confirmed"})
            if run["state"] == "VOICE_PROBE" and is_v3_run(run):
                append_event(directory, run, "VOICE_SELECTION_RECORDED", "operator", {
                    "candidate_id": args.selection,
                    "feedback_present": bool(args.feedback),
                    "voice_probe_sha256": sha256_path(approved_path),
                })
        write_gate_receipt(directory, run, args.gate_id, args.outcome, findings, {"type": "human", "identity": "operator"}, definition.get("repair_state"))
        if args.outcome == "PASS":
            transition(directory, run, definition["next_on_pass"], "operator", f"Operator confirmed {args.gate_id}")
        elif args.outcome == "REPAIR":
            repair_state = definition["repair_state"]
            run.setdefault("attempts", {})[repair_state] = 0
            run.setdefault("route_failures", {}).pop(repair_state, None)
            transition(directory, run, repair_state, "operator", args.finding or "Operator requested repair")
        elif args.outcome == "TERMINAL":
            transition(directory, run, "TERMINAL", "operator", args.finding or "Operator ended run")
        else:
            run["status"] = "WAITING_HUMAN" if args.outcome == "ESCALATE" else "ACTIVE"
            save_run(directory, run)
        next_command = ["article-flow", "advance", run["run_id"]] if automation_enabled(run) else ["article-flow", "next", run["run_id"]]
        payload = {"ok": True, "outcome": args.outcome, "state": run["state"], "approval_id": locals().get("approval_id"), "next_command": next_command}
    emit(payload, args.json)
    return EXIT_OK


def command_repair(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    definition = state_definition(run["state"], run)
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
        run.setdefault("attempts", {})[repair_state] = 0
        run.setdefault("route_failures", {}).pop(repair_state, None)
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
        stripped = line.strip()
        if stripped in {"<details>", "</details>"} or (stripped.startswith("<summary>") and stripped.endswith("</summary>") and "<" not in stripped[len("<summary>"):-len("</summary>")]):
            # Narrow allowlist: pass native disclosure wrappers through so evidence
            # dropdowns render; all other raw HTML remains escaped as before.
            flush_paragraph()
            close_list()
            if stripped.startswith("<summary>"):
                inner = stripped[len("<summary>"):-len("</summary>")]
                output.append(f"<summary>{markdown_inline(inner)}</summary>")
            else:
                output.append(stripped)
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
    experiment = run.get("model_experiment", {})
    actual_models = [str(item) for item in experiment.get("actual_models", []) if str(item)]
    if is_v3_run(run) and not actual_models:
        raise FlowError("Workflow 3 packaging requires exact accepted writing-model provenance", EXIT_INTEGRITY)
    display_names = writing_model_policy()["display_names"]
    drafting_models = [
        {"model_id": model_id, "public_display_name": display_names.get(model_id, public_model_name(model_id))}
        for model_id in actual_models
    ]
    effective_profile = json_artifact(directory, run, "voice-profile") or load_json(baseline_voice_profile_path())
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
        "voice_profile_version": effective_profile["version"],
        "drafting_models": drafting_models,
        "model_experiment_contaminated": bool(experiment.get("contaminated", False)),
        "style_policy_sha256": style_policy_sha256(),
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
    drafting_models = metadata.get("drafting_models", [])
    if is_v3_run(run) and not drafting_models:
        raise FlowError("Cannot render a workflow 3 article without drafting-model disclosure", EXIT_INTEGRITY)
    if drafting_models:
        names = [str(item.get("public_display_name")) for item in drafting_models if isinstance(item, dict)]
        body += (
            "\n<footer class=\"article-model-attribution\" "
            f"data-style-policy-sha256=\"{html.escape(metadata['style_policy_sha256'], quote=True)}\">"
            f"<p>Drafting model: {html.escape(', '.join(names))}</p></footer>"
        )
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
    if drafting_models:
        model_ids = [str(item.get("model_id")) for item in drafting_models if isinstance(item, dict)]
        disclosure_meta = (
            f'<meta name="article-flow-drafting-models" content="{html.escape(json.dumps(model_ids, separators=(",", ":")), quote=True)}">\n'
            f'<meta name="article-flow-style-policy-sha256" content="{html.escape(metadata["style_policy_sha256"], quote=True)}">'
        )
        if "</head>" not in rendered:
            raise FlowError("Article publication template has no </head> marker for provenance metadata", EXIT_INTEGRITY)
        rendered = rendered.replace("</head>", disclosure_meta + "\n</head>", 1)
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


def style_policy_sha256() -> str:
    return sha256_bytes(canonical_json(policy().get("style_gate", {})))


def phrase_scan_text(value: str) -> str:
    """Normalize public prose while excluding code, URLs, and attributed quotations."""
    def attributed_quote(value: str) -> bool:
        plain = re.sub(r"<[^>]+>", " ", value)
        return bool(re.search(
            r"(?:\b(?:said|wrote|asked|replied|according\s+to)\s+[A-Z]|"
            r"\b[A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,4}\s+(?:said|wrote|asked|replied)\b|"
            r"(?:^|\n)\s*[—-]\s*[A-Z])",
            plain,
            flags=re.IGNORECASE,
        ))

    def html_blockquote(match: re.Match[str]) -> str:
        block = match.group(0)
        if re.search(r"<(?:cite)\b|class=[\"'][^\"']*attribution", block, flags=re.IGNORECASE) or attributed_quote(block):
            return " "
        return " " + re.sub(r"<[^>]+>", " ", block) + " "

    def markdown_blockquote(match: re.Match[str]) -> str:
        block = match.group(0)
        plain = re.sub(r"(?m)^\s*>\s?", "", block)
        return " " if attributed_quote(plain) else " " + plain + " "

    normalized = unicodedata.normalize("NFKC", html.unescape(value)).replace("’", "'")
    normalized = re.sub(r"```.*?```", " ", normalized, flags=re.DOTALL)
    normalized = re.sub(r"`[^`\n]*`", " ", normalized)
    normalized = re.sub(r"<(?:pre|code)\b[^>]*>.*?</(?:pre|code)>", " ", normalized, flags=re.IGNORECASE | re.DOTALL)
    normalized = re.sub(r"<blockquote\b[^>]*>.*?</blockquote>", html_blockquote, normalized, flags=re.IGNORECASE | re.DOTALL)
    normalized = re.sub(r"(?m)(?:^\s*>.*(?:\n|$))+", markdown_blockquote, normalized)
    normalized = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", normalized)
    normalized = re.sub(r"https?://[^\s<>'\")\]]+", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(
        r"(?:\"[^\"\n]+\"|“[^”\n]+”)\s*,?\s*(?:(?:said|wrote|asked|replied|according\s+to)\b[^\n]*|"
        r"[A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,4}\s+(?:said|wrote|asked|replied)\b[^\n]*|[—-]\s*[A-Z][^\n]*)",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"<[^>]+>", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def surface_prose_hits(value: str) -> list[str]:
    normalized = phrase_scan_text(value)
    configured = policy().get("style_gate", {}).get("high_confidence_phrases", SURFACE_PROSE_PATTERNS)
    phrases = [str(item) for item in configured] if isinstance(configured, list) else list(SURFACE_PROSE_PATTERNS)
    return [phrase for phrase in phrases if phrase_scan_text(phrase) in normalized]


def style_phrase_findings(value: str, artifact: str = "current") -> list[dict[str, Any]]:
    return [
        {
            "criterion": "high_confidence_cliche",
            "artifact": artifact,
            "location": None,
            "finding": f"Public prose contains the high-confidence formulaic phrase {phrase!r}.",
            "repair_instruction": "Rewrite only the affected passage in concrete, article-specific language, then rescan it.",
        }
        for phrase in surface_prose_hits(value)
    ]


def forbidden_public_prose_character_findings(value: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    decoded_value = unicodedata.normalize("NFKC", html.unescape(value))
    for character, policy_value in FORBIDDEN_PUBLIC_PROSE_CHARACTERS.items():
        count = decoded_value.count(character)
        if not count:
            continue
        locations: list[str] = []
        for line_number, line in enumerate(decoded_value.splitlines(), start=1):
            start = 0
            while len(locations) < 5:
                column = line.find(character, start)
                if column < 0:
                    break
                locations.append(f"line {line_number}, column {column + 1}")
                start = column + len(character)
            if len(locations) == 5:
                break
        findings.append({
            "criterion": "forbidden_public_prose_character",
            "location": "; ".join(locations),
            "finding": (
                f"Public prose contains {count} forbidden {policy_value['name']} "
                f"character(s) ({policy_value['codepoint']})."
            ),
            "repair_instruction": (
                "Replace each occurrence with a comma, colon, parentheses, or separate "
                "sentences as the meaning requires. Do not alter locked quotations or code; "
                "reopen the affected evidence decision if one contains the character."
            ),
        })
    return findings


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
    for field in ("title", "description"):
        for phrase in surface_prose_hits(str(metadata.get(field) or "")):
            findings.append({
                "criterion": "public_surface_voice",
                "path": f"metadata.{field}",
                "finding": f"Public-facing {field} still contains the formulaic phrase {phrase!r}.",
                "repair_instruction": "Rewrite the display text directly, preserving the article's meaning, then package again.",
            })
        for finding in forbidden_public_prose_character_findings(str(metadata.get(field) or "")):
            findings.append({**finding, "path": f"metadata.{field}"})
    if article_markdown.is_file():
        article_text = article_markdown.read_text(encoding="utf-8", errors="replace")
        findings.extend(style_phrase_findings(article_text, str(article_markdown)))
        for finding in forbidden_public_prose_character_findings(article_text):
            findings.append({**finding, "path": str(article_markdown)})
    rendered_surfaces = [article_html, site_root / "docs" / "blog.html", site_root / "index.html", site_root / "feed.xml"]
    for surface in rendered_surfaces:
        if not surface.is_file():
            continue
        surface_text = surface.read_text(encoding="utf-8", errors="replace")
        scan_text = surface_text
        if surface.name in {"blog.html", "index.html"}:
            card = re.search(
                rf'<article\b[^>]*data-article-flow-slug="{re.escape(str(metadata["slug"]))}"[^>]*>.*?</article>',
                surface_text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if card:
                scan_text = card.group(0)
        elif surface.name == "feed.xml":
            item = next(
                (match.group(0) for match in re.finditer(r"<item\b[^>]*>.*?</item>", surface_text, flags=re.IGNORECASE | re.DOTALL) if str(metadata["slug"]) in match.group(0)),
                None,
            )
            if item:
                scan_text = item
        for finding in style_phrase_findings(scan_text, str(surface)):
            findings.append({**finding, "path": str(surface)})
        for finding in forbidden_public_prose_character_findings(scan_text):
            findings.append({**finding, "path": str(surface)})
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
        drafting_models = metadata.get("drafting_models", [])
        if drafting_models:
            model_names = ", ".join(str(item.get("public_display_name")) for item in drafting_models if isinstance(item, dict))
            required_provenance = {
                "model_footer": f"Drafting model: {html.escape(model_names)}",
                "model_meta": '<meta name="article-flow-drafting-models"',
                "style_policy_meta": f'<meta name="article-flow-style-policy-sha256" content="{metadata.get("style_policy_sha256")}">',
                "style_policy_footer": f'data-style-policy-sha256="{metadata.get("style_policy_sha256")}"',
            }
            for name, required_text in required_provenance.items():
                if required_text not in text:
                    findings.append({"criterion": name, "path": str(article_html), "finding": f"Missing or incorrect {name}."})
        for attribute, target in re.findall(r"\b(href|src)=\"([^\"]+)\"", text):
            if target.startswith(("http://", "https://", "mailto:", "#", "data:")):
                continue
            relative = target.split("#", 1)[0].split("?", 1)[0]
            if not relative:
                continue
            if relative.startswith("/"):
                site_relative = relative.lstrip("/")
                packaged_target = (site_root / site_relative).resolve()
                repository_target = (repository / site_relative).resolve() if repository else Path("/__article_flow_unavailable__")
            else:
                packaged_target = (article_html.parent / relative).resolve()
                repository_target = (repository / "docs" / relative).resolve() if repository else Path("/__article_flow_unavailable__")
            try:
                packaged_target.relative_to(site_root.resolve())
            except ValueError:
                packaged_target = Path("/__outside_package__")
            if repository:
                try:
                    repository_target.relative_to(repository.resolve())
                except ValueError:
                    repository_target = Path("/__outside_repository__")
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


def command_amend(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    if run["state"] not in {"PACKAGE", "PUBLISH_APPROVAL"}:
        raise FlowError(f"Amend requires PACKAGE or PUBLISH_APPROVAL, current state is {run['state']}")
    article_argument = getattr(args, "article", None)
    if args.title is None and args.description is None and article_argument is None:
        raise FlowError("Amend requires --title, --description, and/or --article", EXIT_USAGE)
    brief_path = artifact_path(directory, run, "brief")
    if not brief_path:
        raise FlowError("Approved brief is missing", EXIT_INTEGRITY)
    brief = load_json(brief_path)
    changed: dict[str, str] = {}
    if args.title is not None:
        if not args.title.strip():
            raise FlowError("Title cannot be empty", EXIT_USAGE)
        brief["title"] = args.title.strip()
        changed["title"] = brief["title"]
    if args.description is not None:
        if not args.description.strip():
            raise FlowError("Description cannot be empty", EXIT_USAGE)
        brief["description"] = args.description.strip()
        changed["description"] = brief["description"]

    display_findings: list[dict[str, Any]] = []
    for field, value in changed.items():
        for phrase in surface_prose_hits(value):
            display_findings.append({
                "criterion": "public_surface_voice",
                "path": f"metadata.{field}",
                "finding": f"Public-facing {field} still contains the formulaic phrase {phrase!r}.",
                "repair_instruction": "Rewrite the display text directly while preserving the article's meaning.",
            })
        for finding in forbidden_public_prose_character_findings(value):
            display_findings.append({**finding, "path": f"metadata.{field}"})
    if display_findings:
        raise FlowError("Amended public display text failed deterministic validation", EXIT_INTEGRITY, display_findings)

    article_source: Path | None = None
    article_changed = False
    if article_argument is not None:
        article_source = Path(article_argument).expanduser().resolve()
        if not article_source.is_file() or article_source.stat().st_size == 0:
            raise FlowError(f"Amended article does not exist or is empty: {article_source}", EXIT_USAGE)
        outcome, article_findings = automatic_gate(directory, run, "EDIT", article_source)
        if outcome != "PASS":
            raise FlowError("Amended article failed deterministic naturalization validation", EXIT_INTEGRITY, article_findings)
        current_article = artifact_path(directory, run, "article")
        if not current_article:
            raise FlowError("Current article artifact is missing", EXIT_INTEGRITY)
        article_changed = sha256_path(article_source) != sha256_path(current_article)

    with run_lock(directory, run):
        if changed:
            amended_path = directory / "artifacts" / f"amended-brief-{secrets.token_hex(4)}.json"
            write_json(amended_path, brief)
            errors = validate_json_schema(amended_path, "brief.schema.json")
            if errors:
                amended_path.unlink(missing_ok=True)
                raise FlowError("Amended brief is invalid", EXIT_INTEGRITY, errors)
            record_artifact(directory, run, amended_path, "brief", {"actor": "operator", "decision": "display-text-amendment"})
            append_event(directory, run, "PUBLIC_DISPLAY_TEXT_AMENDED", "operator", {"changed_fields": sorted(changed)})
        if article_source is not None and article_changed:
            amended_article = directory / "artifacts" / f"amended-article-{secrets.token_hex(4)}.md"
            shutil.copy2(article_source, amended_article)
            record_artifact(directory, run, amended_article, "article", {"actor": "operator", "decision": "bounded-naturalization-amendment"})
            append_event(directory, run, "PUBLIC_ARTICLE_AMENDED", "operator", {"source_sha256": sha256_path(article_source)})
            write_gate_receipt(directory, run, "G-NATURALIZATION", "PASS", [], {"type": "code", "version": CONTROLLER_VERSION})
            transition(directory, run, "POST_EDIT_CLAIM_VERIFICATION", "operator", "Article prose changed; reverify post-edit claims and editorial QA")
        elif changed and run["state"] != "PACKAGE":
            transition(directory, run, "PACKAGE", "operator", "Public display text changed; rebuild the package")
        else:
            save_run(directory, run)
    if run["state"] == "POST_EDIT_CLAIM_VERIFICATION":
        next_command = ["article-flow", "next", run["run_id"]]
    elif run["state"] == "PACKAGE":
        next_command = ["article-flow", "package", run["run_id"]]
    else:
        next_command = ["article-flow", "publish", "--plan", run["run_id"]]
    emit({"ok": True, "changed": changed, "article_changed": article_changed, "state": run["state"], "next_command": next_command}, args.json)
    return EXIT_OK


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
        if is_v3_run(run):
            assignment_value = json_artifact(directory, run, "model-assignment")
            if not assignment_value:
                raise FlowError("Workflow 3 package is missing its model assignment", EXIT_INTEGRITY)
            receipt_hashes = sorted({
                str(item.get("sha256"))
                for item in run.get("artifact_index", [])
                if str(item.get("type", "")).startswith("model-call:")
                and any(f"model-call:{stage}:" in str(item.get("type")) for stage in V3_WRITING_STATES)
                and item.get("sha256")
            })
            if not receipt_hashes:
                raise FlowError("Workflow 3 package lacks writing-model call receipts", EXIT_INTEGRITY)
            model_names = [str(item["public_display_name"]) for item in metadata["drafting_models"]]
            experiment = run.get("model_experiment", {})
            package.update({
                "automation_mode": str(run.get("run_overrides", {}).get("automation_mode", "manual")),
                "effective_voice_profile_version": metadata["voice_profile_version"],
                "model_assignment": assignment_value,
                "model_attribution": {
                    "public_display_name": ", ".join(model_names),
                    "footer_text": f"Drafting model: {', '.join(model_names)}",
                    "source_receipt_hashes": receipt_hashes,
                },
                "style_policy_sha256": metadata["style_policy_sha256"],
                "writing_model_fallback_status": "contaminated" if experiment.get("contaminated") else "none",
            })
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
        if existing.get("package_revision") == package.get("package_revision") and existing.get("base_commit") == str(git(["rev-parse", "HEAD"], cwd=repository)).strip() and existing.get("target") == target.get("target_id") and (not is_v3_run(run) or existing.get("style_policy_sha256") == package.get("style_policy_sha256") == style_policy_sha256()):
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
        "style_policy_sha256": package.get("style_policy_sha256") if is_v3_run(run) else None,
        "changes": changes,
        "push_requires_explicit_flag": True,
        "created_at": utc_now(),
    }
    write_json(plan_path, plan)
    record_artifact(directory, run, plan_path, "publish-plan", {"actor": "controller", "version": CONTROLLER_VERSION})
    emit({"ok": True, "dry_run": True, "plan": str(plan_path), **plan, "approval_command": ["article-flow", "gate", run["run_id"], "G-PUBLISH-APPROVAL", "--outcome", "PASS"]}, args.json)
    return EXIT_OK


def command_publish_renew_approval(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    if run["state"] != "PUBLISH":
        raise FlowError(f"Publication approval renewal requires PUBLISH, current state is {run['state']}")
    plan_path = directory / "publication" / "plan.json"
    package_path = directory / "package" / "package.json"
    if not plan_path.is_file() or not package_path.is_file():
        raise FlowError("Publication plan or package is missing", EXIT_INTEGRITY)
    plan = load_json(plan_path)
    package = load_json(package_path)
    prior = json_artifact(directory, run, "publish-approval")
    if not prior:
        raise FlowError("No prior scoped publication approval is available to renew", EXIT_APPROVAL)
    if prior.get("target") != plan.get("target") or prior.get("package_revision") != plan.get("package_revision"):
        raise FlowError("Prior approval does not match the current publication scope", EXIT_APPROVAL)
    if prior.get("plan_sha256") != sha256_path(plan_path) or package.get("package_revision") != plan.get("package_revision"):
        raise FlowError("Publication scope changed; return to planning instead of renewing approval", EXIT_APPROVAL)
    if parse_time(prior["expires_at"]) > dt.datetime.now(dt.timezone.utc):
        emit({
            "ok": True,
            "idempotent": True,
            "approval_id": prior.get("approval_id"),
            "expires_at": prior.get("expires_at"),
            "state": run["state"],
        }, args.json)
        return EXIT_OK
    prior_handoff_path = artifact_path(directory, run, "publication-handoff")
    prior_handoff = load_json(prior_handoff_path) if prior_handoff_path and prior_handoff_path.is_file() else None
    with run_lock(directory, run):
        approval_id, approval_path = create_publish_approval(directory, run, plan, renewed_from=str(prior.get("approval_id")))
        renewed_handoff_path = None
        if prior_handoff:
            renewed_handoff_path = create_publication_handoff(
                directory,
                run,
                plan,
                approval_id,
                f"Scoped approval renewed for the existing deployment handoff: {prior_handoff.get('reason', 'credentialed deployment is still required')}",
                commit=prior_handoff.get("created_commit"),
            )
        run["status"] = "WAITING_HUMAN" if renewed_handoff_path else "ACTIVE"
        save_run(directory, run)
    renewed = load_json(approval_path)
    emit({
        "ok": True,
        "approval_id": approval_id,
        "renewed_from": prior.get("approval_id"),
        "expires_at": renewed["expires_at"],
        "state": run["state"],
        "handoff": str(renewed_handoff_path) if renewed_handoff_path else None,
        "retry_command": ["article-flow", "publish", "--execute", run["run_id"], "--approval", approval_id, "--commit", "--push"],
        "attestation_command": ["article-flow", "deployment-attest", run["run_id"], "--remote-rev", "REMOTE_COMMIT"],
    }, args.json)
    return EXIT_OK


def publication_push_preflight(repository: Path, target: dict[str, Any]) -> dict[str, Any]:
    command = [
        "git",
        "-C",
        str(repository),
        "push",
        "--dry-run",
        str(target["deployment"]["remote"]),
        f"HEAD:{target['publication_branch']}",
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=45)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": str(exc), "command": command}
    return {
        "ok": result.returncode == 0,
        "exit_code": result.returncode,
        "reason": (result.stderr or result.stdout).strip()[-2000:],
        "command": command,
    }


def create_publication_handoff(
    directory: Path,
    run: dict[str, Any],
    plan: dict[str, Any],
    approval_id: str,
    reason: str,
    *,
    commit: str | None = None,
) -> Path:
    retry_command = [
        "article-flow",
        "publish",
        "--execute",
        run["run_id"],
        "--approval",
        approval_id,
        "--commit",
        "--push",
    ]
    attestation_command = ["article-flow", "deployment-attest", run["run_id"], "--remote-rev", "REMOTE_COMMIT"]
    handoff = {
        "handoff_schema_version": "1.0.0",
        "status": "AWAITING_OPERATOR_DEPLOY",
        "run_id": run["run_id"],
        "package_revision": plan["package_revision"],
        "reason": reason,
        "created_commit": commit,
        "changed_paths": [item["path"] for item in plan["changes"]],
        "retry_command": retry_command,
        "attestation_command": attestation_command,
        "instructions": [
            "Run retry_command from a credentialed local host that can access this runtime and repository.",
            "If the exact planned files were deployed another way, fetch that revision and run attestation_command with its commit.",
        ],
        "created_at": utc_now(),
    }
    path = directory / "publication" / f"handoff-{slugify(approval_id, 80)}.json"
    write_json(path, handoff)
    record_artifact(directory, run, path, "publication-handoff", {"actor": "controller", "version": CONTROLLER_VERSION})
    append_event(directory, run, "PUBLICATION_HANDOFF", "controller", {"reason": reason, "commit": commit, "package_revision": plan["package_revision"]})
    run["status"] = "WAITING_HUMAN"
    save_run(directory, run)
    return path


def command_publish_execute(args: argparse.Namespace) -> int:
    if os.environ.get("ARTICLE_FLOW_TEST_NO_PUBLISH") == "1":
        raise FlowError("Publication execution is disabled inside smoke/conformance tests", EXIT_APPROVAL)
    directory, run = load_run(args.run_id)
    if run["state"] != "PUBLISH":
        raise FlowError(f"Publication execution requires PUBLISH, current state is {run['state']}")
    if args.push and not args.commit:
        raise FlowError("--push requires --commit", EXIT_USAGE)
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
    incomplete_path = directory / "publication" / "incomplete.json"
    incomplete = load_json(incomplete_path) if incomplete_path.is_file() else {}
    resumed_own_commit = bool(
        incomplete.get("package_revision") == plan.get("package_revision")
        and incomplete.get("commit") == current_commit
    )
    if current_commit != plan.get("base_commit") and not resumed_own_commit:
        raise FlowError("Repository HEAD changed after publication planning; create and approve a new plan", EXIT_INTEGRITY, {"planned": plan.get("base_commit"), "actual": current_commit})
    package = load_json(directory / "package" / "package.json")
    if package.get("package_revision") != plan.get("package_revision"):
        raise FlowError("Package revision changed after publication planning", EXIT_INTEGRITY)
    if is_v3_run(run):
        current_style_hash = style_policy_sha256()
        if package.get("style_policy_sha256") != current_style_hash or plan.get("style_policy_sha256") != current_style_hash:
            raise FlowError("Style policy changed after package approval", EXIT_INTEGRITY)
        findings = validate_public_package(directory / "package", load_json(directory / "package" / "public" / "metadata.json"))
        if findings:
            raise FlowError("Approved package no longer passes public-prose validation", EXIT_INTEGRITY, findings)
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
    target = load_json(SPEC_ROOT / "publication" / "theproductiveprompter.json")
    preflight = {"ok": True, "reason": "push not requested"}
    if args.push:
        preflight = publication_push_preflight(repository, target)
        if not preflight["ok"]:
            with run_lock(directory, run):
                handoff_path = create_publication_handoff(
                    directory,
                    run,
                    plan,
                    approval["approval_id"],
                    f"Push capability preflight failed: {preflight.get('reason') or 'credentialed push unavailable'}",
                    commit=current_commit if resumed_own_commit else None,
                )
            emit({
                "ok": False,
                "action": "human_action",
                "state": run["state"],
                "handoff": str(handoff_path),
                "reason": preflight.get("reason"),
                "retry_command": load_json(handoff_path)["retry_command"],
                "attestation_command": load_json(handoff_path)["attestation_command"],
            }, args.json)
            return EXIT_WAITING
    with run_lock(directory, run):
        append_event(directory, run, "PUBLISH_ATTEMPT", "controller", {
            "package_revision": plan["package_revision"],
            "base_commit": plan["base_commit"],
            "resuming_commit": current_commit if resumed_own_commit else None,
            "push_preflight": preflight,
        })
        site_root = directory / "package" / "site"
        changed_paths = [safe_relative(change["path"]).as_posix() for change in plan["changes"]]
        commit = current_commit if resumed_own_commit else None
        if not resumed_own_commit:
            for change in plan["changes"]:
                rel = safe_relative(change["path"])
                source = site_root / rel
                destination = repository / rel
                current_hash = sha256_path(destination) if destination.is_file() else None
                if current_hash != change["current_sha256"]:
                    raise FlowError(f"Publication target changed after planning: {rel}", EXIT_INTEGRITY)
                atomic_write(destination, source.read_bytes())
            git(["add", "--", *changed_paths], cwd=repository)
            if args.commit:
                git(["commit", "-m", f"Publish {run['run_id']} ({plan['package_revision'][:12]})", "--", *changed_paths], cwd=repository)
                commit = str(git(["rev-parse", "HEAD"], cwd=repository)).strip()
        pushed = False
        if args.push:
            try:
                git(["push", target["deployment"]["remote"], f"HEAD:{target['publication_branch']}"], cwd=repository)
            except FlowError as exc:
                incomplete = {
                    "publication_receipt_schema_version": "1.0.0",
                    "run_id": run["run_id"],
                    "target": plan["target"],
                    "package_revision": plan["package_revision"],
                    "approval_id": approval["approval_id"],
                    "expires_at": approval["expires_at"],
                    "status": "FAILED",
                    "commit": commit,
                    "url": None,
                    "checks": [{"changed_paths": changed_paths, "push_error": str(exc)}],
                    "created_at": utc_now(),
                }
                write_json(incomplete_path, incomplete)
                record_artifact(directory, run, incomplete_path, "publication-incomplete", {"actor": "controller", "version": CONTROLLER_VERSION})
                append_event(directory, run, "PUBLISH_INCOMPLETE", "controller", {"commit": commit, "error": str(exc), "package_revision": plan["package_revision"]})
                handoff_path = create_publication_handoff(directory, run, plan, approval["approval_id"], str(exc), commit=commit)
                emit({
                    "ok": False,
                    "action": "human_action",
                    "state": run["state"],
                    "commit": commit,
                    "handoff": str(handoff_path),
                    "retry_command": load_json(handoff_path)["retry_command"],
                    "attestation_command": load_json(handoff_path)["attestation_command"],
                }, args.json)
                return EXIT_WAITING
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
            "checks": [{"changed_paths": changed_paths, "push_preflight": preflight}],
            "created_at": utc_now(),
        }
        write_json(existing, receipt)
        record_artifact(directory, run, existing, "publication", {"actor": "controller", "version": CONTROLLER_VERSION})
        append_event(directory, run, "PUBLICATION", "controller", {"status": receipt["status"], "commit": commit, "package_revision": plan["package_revision"]})
        write_gate_receipt(directory, run, "G-PUBLISH-REVISION", "PASS", [], {"type": "code", "version": CONTROLLER_VERSION})
        transition(directory, run, "LIVE_VERIFICATION", "controller", "Approved publication plan applied once")
    emit({"ok": True, "status": receipt["status"], "commit": commit, "pushed": pushed, "state": run["state"], "next_command": ["article-flow", "verify-live", run["run_id"]]}, args.json)
    return EXIT_OK


def command_deployment_attest(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    if run["state"] != "PUBLISH":
        raise FlowError(f"Deployment attestation requires PUBLISH, current state is {run['state']}")
    repository = publication_repo_root(required=True)
    plan = load_json(directory / "publication" / "plan.json")
    package = load_json(directory / "package" / "package.json")
    approval = json_artifact(directory, run, "publish-approval")
    if not approval or approval.get("package_revision") != plan.get("package_revision") or approval.get("target") != plan.get("target"):
        raise FlowError("Deployment attestation requires the matching scoped publication approval", EXIT_APPROVAL)
    if approval.get("plan_sha256") != sha256_path(directory / "publication" / "plan.json"):
        raise FlowError("Publication plan changed after approval", EXIT_APPROVAL)
    if parse_time(approval["expires_at"]) <= dt.datetime.now(dt.timezone.utc):
        raise FlowError("Publication approval has expired", EXIT_APPROVAL)
    target = load_json(SPEC_ROOT / "publication" / "theproductiveprompter.json")
    git(["fetch", target["deployment"]["remote"], target["publication_branch"]], cwd=repository)
    remote_head = str(git(["rev-parse", "--verify", "FETCH_HEAD^{commit}"], cwd=repository)).strip()
    resolved = str(git(["rev-parse", "--verify", f"{args.remote_rev}^{{commit}}"], cwd=repository)).strip()
    if resolved != remote_head:
        raise FlowError(
            "Deployment attestation must name the current remote publication-branch commit",
            EXIT_INTEGRITY,
            {"requested": resolved, "remote_head": remote_head, "branch": target["publication_branch"]},
        )
    checks = []
    failures = []
    for change in plan["changes"]:
        rel = safe_relative(change["path"]).as_posix()
        try:
            deployed = git(["show", f"{resolved}:{rel}"], cwd=repository, binary=True)
            actual_hash = sha256_bytes(deployed if isinstance(deployed, bytes) else deployed.encode("utf-8"))
        except FlowError:
            actual_hash = None
        check = {"path": rel, "expected_sha256": change["planned_sha256"], "actual_sha256": actual_hash, "ok": actual_hash == change["planned_sha256"]}
        checks.append(check)
        if not check["ok"]:
            failures.append(check)
    if package.get("package_revision") != plan.get("package_revision") or failures:
        raise FlowError("Remote deployment does not match the approved package", EXIT_INTEGRITY, failures)
    receipt = {
        "publication_receipt_schema_version": "1.0.0",
        "run_id": run["run_id"],
        "target": plan["target"],
        "package_revision": plan["package_revision"],
        "approval_id": approval.get("approval_id"),
        "expires_at": approval.get("expires_at"),
        "status": "APPLIED",
        "commit": resolved,
        "url": None,
        "checks": [{"deployment_method": "operator_attested", "remote_revision": resolved, "remote_branch_head": remote_head}, *checks],
        "created_at": utc_now(),
    }
    receipt_path = directory / "receipts" / "publication.json"
    with run_lock(directory, run):
        write_json(receipt_path, receipt)
        errors = validate_json_schema(receipt_path, "publication-receipt.schema.json")
        if errors:
            raise FlowError("Controller generated an invalid attested publication receipt", EXIT_INTEGRITY, errors)
        record_artifact(directory, run, receipt_path, "publication", {"actor": "controller", "version": CONTROLLER_VERSION, "method": "operator-attested"})
        append_event(directory, run, "DEPLOYMENT_ATTESTED", "controller", {"commit": resolved, "package_revision": plan["package_revision"], "checks": checks})
        write_gate_receipt(directory, run, "G-PUBLISH-REVISION", "PASS", [], {"type": "code", "version": CONTROLLER_VERSION})
        transition(directory, run, "LIVE_VERIFICATION", "controller", "Operator-deployed revision matched every approved publication blob")
    emit({"ok": True, "commit": resolved, "state": run["state"], "next_command": ["article-flow", "verify-live", run["run_id"]]}, args.json)
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
    record_experiment_outcome(directory, run)
    transition(directory, run, "COMPLETE", "controller", "Exact rendered revision and required discovery surfaces verified")
    emit({"ok": True, "url": receipt["url"], "receipt": str(receipt_path), "state": run["state"], "indexing": "unknown_not_claimed"}, args.json)
    return EXIT_OK


def _silent_command(function: Any, args: argparse.Namespace) -> tuple[int, dict[str, Any] | None]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = int(function(args))
    rendered = buffer.getvalue().strip()
    if not rendered:
        return code, None
    try:
        value = json.loads(rendered)
    except json.JSONDecodeError:
        value = {"output": rendered}
    return code, value if isinstance(value, dict) else {"output": value}


def simulate_no_publish(directory: Path, run: dict[str, Any]) -> dict[str, Any]:
    """Complete deterministic publication states without git, network, or public writes."""
    if os.environ.get("ARTICLE_FLOW_TEST_NO_PUBLISH") != "1":
        raise FlowError("No-publish simulation is available only in the explicit test environment", EXIT_APPROVAL)
    package = load_json(directory / "package" / "package.json")
    plan = load_json(directory / "publication" / "plan.json")
    approval = json_artifact(directory, run, "publish-approval") or {}
    if run["state"] == "PUBLISH":
        receipt = {
            "publication_receipt_schema_version": "1.0.0",
            "run_id": run["run_id"],
            "target": plan["target"],
            "package_revision": package["package_revision"],
            "approval_id": approval.get("approval_id"),
            "expires_at": approval.get("expires_at"),
            "status": "APPLIED",
            "commit": None,
            "url": None,
            "checks": [{"test_no_publish": True, "git_write": False, "network_write": False}],
            "created_at": utc_now(),
        }
        path = directory / "receipts" / "publication.json"
        write_json(path, receipt)
        errors = validate_json_schema(path, "publication-receipt.schema.json")
        if errors:
            raise FlowError("Controller generated an invalid no-publish receipt", EXIT_INTEGRITY, errors)
        record_artifact(directory, run, path, "publication", {"actor": "controller", "version": CONTROLLER_VERSION, "simulation": True})
        append_event(directory, run, "PUBLICATION", "controller", {"status": "TEST_NO_PUBLISH", "package_revision": plan["package_revision"]})
        write_gate_receipt(directory, run, "G-PUBLISH-REVISION", "PASS", [], {"type": "code", "version": CONTROLLER_VERSION, "simulation": True})
        transition(directory, run, "LIVE_VERIFICATION", "controller", "Explicit no-publish test simulated an applied revision without external writes")
    if run["state"] == "LIVE_VERIFICATION":
        receipt = {
            "publication_receipt_schema_version": "1.0.0",
            "run_id": run["run_id"],
            "target": plan["target"],
            "package_revision": package["package_revision"],
            "approval_id": approval.get("approval_id"),
            "expires_at": None,
            "status": "VERIFIED",
            "commit": None,
            "url": None,
            "checks": [{"test_no_publish": True, "live_network_check_skipped": True}],
            "accessibility_proved": False,
            "represented_for_discovery": False,
            "indexing": "unknown_not_claimed",
            "created_at": utc_now(),
        }
        path = directory / "receipts" / "live-verification.json"
        write_json(path, receipt)
        errors = validate_json_schema(path, "publication-receipt.schema.json")
        if errors:
            raise FlowError("Controller generated an invalid simulated verification receipt", EXIT_INTEGRITY, errors)
        record_artifact(directory, run, path, "live-verification", {"actor": "controller", "version": CONTROLLER_VERSION, "simulation": True})
        append_event(directory, run, "VERIFICATION", "controller", {"ok": True, "test_no_publish": True, "url": None})
        write_gate_receipt(directory, run, "G-LIVE-REVISION", "PASS", [], {"type": "code", "version": CONTROLLER_VERSION, "simulation": True})
        record_experiment_outcome(directory, run)
        transition(directory, run, "COMPLETE", "controller", "No-publish conformance path completed without external writes")
    return {"ok": True, "test_no_publish": True, "state": run["state"]}


def command_advance(args: argparse.Namespace) -> int:
    """Continue a workflow-3 run synchronously until its sole routine human choice or completion."""
    progress: list[dict[str, Any]] = []
    maximum = int(getattr(args, "max_steps", 100))
    for _ in range(maximum):
        directory, run = load_run(args.run_id)
        state = run["state"]
        if state in {"COMPLETE", "TERMINAL"}:
            payload = {"ok": state == "COMPLETE", "action": state.lower(), "run_id": run["run_id"], "state": state, "progress": progress}
            emit(payload, args.json)
            return EXIT_OK if state == "COMPLETE" else EXIT_FAILED
        if run.get("status") == "BLOCKED":
            payload = {**next_state_payload(directory, run), "ok": False, "progress": progress}
            emit(payload, args.json)
            return EXIT_WAITING
        if state == "VOICE_PROBE" and artifact(run, "voice-probe"):
            payload = {**next_state_payload(directory, run), "ok": True, "progress": progress}
            emit(payload, args.json)
            return EXIT_WAITING
        if state in MODEL_STATES:
            code, result = _silent_command(command_execute_stage, argparse.Namespace(
                run_id=run["run_id"], route=None, canary=False, json=True,
            ))
            progress.append({"state": state, "command": "execute-stage", "exit_code": code, "result": result})
            if code == EXIT_WAITING:
                directory, run = load_run(args.run_id)
                payload = {**next_state_payload(directory, run), "ok": False, "progress": progress}
                emit(payload, args.json)
                return EXIT_WAITING
            if code not in {EXIT_OK}:
                directory, run = load_run(args.run_id)
                payload = {"ok": False, "action": "blocked", "run_id": run["run_id"], "state": run["state"], "progress": progress, "result": result}
                emit(payload, args.json)
                return code
            continue
        if state == "VOICE_LEARNING":
            with run_lock(directory, run):
                result = apply_voice_learning(directory, run)
            progress.append({"state": state, "command": "voice-apply", "result": result})
            continue
        if state == "PACKAGE":
            code, result = _silent_command(command_package, argparse.Namespace(run_id=run["run_id"], json=True))
            progress.append({"state": state, "command": "package", "exit_code": code, "result": result})
            if code != EXIT_OK:
                emit({"ok": False, "action": "blocked", "run_id": run["run_id"], "state": state, "progress": progress}, args.json)
                return code
            continue
        if state == "PUBLISH_APPROVAL":
            plan_path = directory / "publication" / "plan.json"
            if not plan_path.is_file():
                code, result = _silent_command(command_publish_plan, argparse.Namespace(run_id=run["run_id"], json=True))
                progress.append({"state": state, "command": "publish-plan", "exit_code": code, "result": result})
                if code != EXIT_OK:
                    emit({"ok": False, "action": "blocked", "run_id": run["run_id"], "state": state, "progress": progress}, args.json)
                    return code
                continue
            if not run.get("run_overrides", {}).get("auto_publish", False):
                run["status"] = "WAITING_HUMAN"
                save_run(directory, run)
                payload = {"ok": True, "action": "publication_hold", "run_id": run["run_id"], "state": state, "plan": str(plan_path), "progress": progress}
                emit(payload, args.json)
                return EXIT_WAITING
            with run_lock(directory, run):
                approval_id, _ = create_publish_approval(directory, run, load_json(plan_path), actor="policy")
                transition(directory, run, "PUBLISH", "policy", "Hash-bound policy approval issued for the allowlisted production target")
            progress.append({"state": state, "command": "policy-approval", "approval_id": approval_id})
            continue
        if state == "PUBLISH":
            if os.environ.get("ARTICLE_FLOW_TEST_NO_PUBLISH") == "1":
                with run_lock(directory, run):
                    result = simulate_no_publish(directory, run)
                progress.append({"state": state, "command": "test-no-publish", "result": result})
                continue
            approval = json_artifact(directory, run, "publish-approval")
            if not approval:
                raise FlowError("Automatic publish reached PUBLISH without a scoped approval", EXIT_APPROVAL)
            if parse_time(str(approval["expires_at"])) <= dt.datetime.now(dt.timezone.utc):
                with run_lock(directory, run):
                    approval_id, _ = create_publish_approval(
                        directory,
                        run,
                        load_json(directory / "publication" / "plan.json"),
                        renewed_from=str(approval.get("approval_id")),
                        actor="policy",
                    )
            else:
                approval_id = str(approval["approval_id"])
            code, result = _silent_command(command_publish_execute, argparse.Namespace(
                run_id=run["run_id"], approval=approval_id, commit=True, push=True, json=True,
            ))
            progress.append({"state": state, "command": "publish-execute", "exit_code": code, "result": result})
            if code == EXIT_WAITING:
                directory, run = load_run(args.run_id)
                payload = {**next_state_payload(directory, run), "ok": False, "progress": progress}
                emit(payload, args.json)
                return EXIT_WAITING
            if code != EXIT_OK:
                emit({"ok": False, "action": "blocked", "run_id": run["run_id"], "state": state, "progress": progress}, args.json)
                return code
            continue
        if state == "LIVE_VERIFICATION":
            if os.environ.get("ARTICLE_FLOW_TEST_NO_PUBLISH") == "1":
                with run_lock(directory, run):
                    result = simulate_no_publish(directory, run)
                progress.append({"state": state, "command": "test-live-verification", "result": result})
                continue
            code, result = _silent_command(command_verify_live, argparse.Namespace(run_id=run["run_id"], json=True))
            progress.append({"state": state, "command": "verify-live", "exit_code": code, "result": result})
            if code != EXIT_OK:
                emit({"ok": False, "action": "live_verification_failed", "run_id": run["run_id"], "state": state, "progress": progress}, args.json)
                return EXIT_WAITING
            continue
        raise FlowError(f"Advance has no deterministic handler for state {state}", EXIT_INTEGRITY)
    directory, run = load_run(args.run_id)
    emit({"ok": False, "action": "step_limit", "run_id": run["run_id"], "state": run["state"], "progress": progress}, args.json)
    return EXIT_WAITING


def command_choose_voice(args: argparse.Namespace) -> int:
    gate_args = argparse.Namespace(
        run_id=args.run_id,
        gate_id="G-VOICE-PROBE",
        outcome="PASS",
        finding=None,
        artifact=None,
        selection=args.candidate_id,
        feedback=args.feedback,
        json=True,
    )
    code, result = _silent_command(command_gate, gate_args)
    if code != EXIT_OK:
        emit(result or {"ok": False}, args.json)
        return code
    if args.auto:
        return command_advance(argparse.Namespace(run_id=args.run_id, max_steps=100, json=args.json))
    directory, run = load_run(args.run_id)
    emit({"ok": True, "selection": args.candidate_id, "state": run["state"], "next_command": ["article-flow", "advance", run["run_id"]]}, args.json)
    return EXIT_OK


def command_voice_apply(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    with run_lock(directory, run):
        result = apply_voice_learning(directory, run)
    result["next_command"] = ["article-flow", "advance", run["run_id"]]
    emit(result, args.json)
    return EXIT_OK


def command_voice_history(args: argparse.Namespace) -> int:
    emit(voice_history(), args.json)
    return EXIT_OK


def command_voice_rollback(args: argparse.Namespace) -> int:
    emit(rollback_voice_profile(args.version), args.json)
    return EXIT_OK


def command_models_history(args: argparse.Namespace) -> int:
    emit(model_history(), args.json)
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


def record_linked_checkout(
    home: Path,
    *,
    host: str,
    development: bool,
    publication_repository: str,
    captured_material_root: str,
) -> None:
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
        "development": development,
        "linked_checkout": True,
        "publication_repo_root": publication_repository,
        "captured_material_root": captured_material_root,
        "source_commit": source_commit,
    }
    prior_without_timestamp = {key: value for key, value in current.items() if key != "installed_at"}
    current_value["installed_at"] = (current.get("installed_at") or utc_now()) if prior_without_timestamp == current_value else utc_now()
    if current != current_value:
        write_json(current_path, current_value)


def validate_managed_release_copies(home: Path) -> Path | None:
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
    return releases


def remove_managed_release_copies(home: Path) -> str | None:
    releases = validate_managed_release_copies(home)
    if releases is None:
        return None
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
    if not args.development:
        integrity = check_manifest("worktree")
        if not integrity["ok"]:
            raise FlowError("Cannot install an unmanifested workflow", EXIT_INTEGRITY, integrity)
    user_root = windows_user_root()
    publication_repository = publication_repo_root(required=True)
    shared_runs_root = (user_root / ".article-flow" / "runs").resolve() if user_root else (runtime_home() / "runs").resolve()
    wsl_home = runtime_home() if os.environ.get("ARTICLE_FLOW_HOME") else Path.home() / ".local" / "share" / "article-flow"
    wsl_wrapper = Path.home() / ".local" / "bin" / "article-flow"
    windows_home: Path | None = None
    windows_bin_dir: Path | None = None
    windows_python: Path | None = None
    windows_legacy_launchers: tuple[Path, ...] = ()
    if "wsl" in hosts:
        require_managed_legacy_skill_adapters(wsl_legacy_skill_targets())
        validate_managed_release_copies(wsl_home.resolve())
        if wsl_wrapper.is_file() and "article-flow managed launcher" not in wsl_wrapper.read_text(encoding="utf-8", errors="ignore"):
            raise FlowError(f"Refusing to overwrite an unmanaged launcher: {wsl_wrapper}")
    if "windows" in hosts:
        if not user_root:
            raise FlowError("Cannot resolve the Windows user profile; set ARTICLE_FLOW_WINDOWS_USER_ROOT")
        require_managed_legacy_skill_adapters(windows_legacy_skill_targets(user_root))
        windows_bin_dir = user_root / "AppData" / "Local" / "Microsoft" / "WindowsApps"
        windows_home = user_root / ".article-flow"
        validate_managed_release_copies(windows_home)
        windows_legacy_launchers = (
            user_root / ".local" / "bin" / "article-flow.cmd",
            user_root / ".local" / "bin" / "article-flow.ps1",
            windows_bin_dir / "article-flow.ps1",
        )
        for legacy in windows_legacy_launchers:
            if legacy.is_file() and "article-flow managed launcher" not in legacy.read_text(encoding="utf-8", errors="ignore"):
                raise FlowError(f"Refusing to remove an unmanaged launcher: {legacy}")
        python_candidates = [
            user_root / "AppData" / "Local" / "Programs" / "Python" / "Python312" / "python.exe",
            user_root / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "python.exe",
        ]
        windows_python = next((item for item in python_candidates if item.exists()), None)
        if not windows_python:
            raise FlowError("Native Windows Python was not found")
        windows_command = windows_bin_dir / "article-flow.cmd"
        if windows_command.is_file() and "article-flow managed launcher" not in windows_command.read_text(encoding="utf-8", errors="ignore"):
            raise FlowError(f"Refusing to overwrite an unmanaged launcher: {windows_command}")
    shared_runs_root.mkdir(parents=True, exist_ok=True)
    installed: list[dict[str, Any]] = []
    if "wsl" in hosts:
        home = wsl_home
        record_linked_checkout(
            home.resolve(),
            host="wsl",
            development=args.development,
            publication_repository=str(publication_repository),
            captured_material_root=str(shared_runs_root),
        )
        wrapper = wsl_wrapper
        wrapper.parent.mkdir(parents=True, exist_ok=True)
        wrapper_text = (
            f"#!/usr/bin/env sh\n# article-flow managed launcher {CONTROLLER_VERSION}\n"
            f"export ARTICLE_FLOW_HOME={shlex.quote(str(home.resolve()))}\n"
            f"export ARTICLE_FLOW_RUNS_ROOT={shlex.quote(str(shared_runs_root))}\n"
            f"export ARTICLE_FLOW_REPO_ROOT={shlex.quote(str(publication_repository))}\n"
            f"exec python3 {shlex.quote(str(SCRIPT_PATH.resolve()))} \"$@\"\n"
        )
        write_if_changed(wrapper, wrapper_text.encode("utf-8"), mode=0o755)
        retired = retire_managed_skill_adapters(wsl_legacy_skill_targets(), home.resolve())
        removed_releases = remove_managed_release_copies(home.resolve())
        installed.append({"host": "wsl", "home": str(home.resolve()), "captured_material_root": str(shared_runs_root), "publication_repo_root": str(publication_repository), "command": str(wrapper), "source_checkout": str(REPO_ROOT.resolve()), "retired_skill_adapters": retired, "removed_release_copies": removed_releases})
    if "windows" in hosts:
        assert user_root is not None and windows_home is not None and windows_bin_dir is not None and windows_python is not None
        bin_dir = windows_bin_dir
        legacy_launchers = windows_legacy_launchers
        home = windows_home
        record_linked_checkout(
            home,
            host="windows",
            development=args.development,
            publication_repository=windows_path(publication_repository),
            captured_material_root=windows_path(shared_runs_root),
        )
        python_exe = windows_python
        bin_dir.mkdir(parents=True, exist_ok=True)
        cmd_text = f"@echo off\r\nrem article-flow managed launcher {CONTROLLER_VERSION}\r\nset \"ARTICLE_FLOW_HOME={windows_path(home)}\"\r\nset \"ARTICLE_FLOW_RUNS_ROOT={windows_path(shared_runs_root)}\"\r\nset \"ARTICLE_FLOW_REPO_ROOT={windows_path(publication_repository)}\"\r\n\"{windows_path(python_exe)}\" \"{windows_path(SCRIPT_PATH)}\" %*\r\n"
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
        installed.append({"host": "windows", "home": str(home), "captured_material_root": windows_path(shared_runs_root), "publication_repo_root": windows_path(publication_repository), "command": str(command), "source_checkout": windows_path(REPO_ROOT), "retired_launchers": retired_launchers, "retired_skill_adapters": retired, "removed_release_copies": removed_releases, "python": str(python_exe)})
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
            "endpoint_present": resolved_provider_endpoint(provider) is not None or provider.get("kind") in {"agent-hosted", "command", "codex-cli"},
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
    if os.name == "nt":
        windows_root = windows_user_root()
        checks = [
            {"host": "native-windows", **conformance_health(windows_root / ".article-flow", "native-windows")}
            if windows_root
            else {"host": "native-windows", "ok": False, "receipt": None, "reason": "Windows user root is unresolved"}
        ]
    else:
        checks = [{"host": "wsl", **conformance_health(Path.home() / ".local" / "share" / "article-flow", "wsl")}]
    return {"ok": all(item["ok"] for item in checks), "checks": checks}


def installation_health() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    if os.name == "nt":
        windows_root = windows_user_root()
        candidates = [("windows", windows_root / ".article-flow" / "current.json")] if windows_root else []
    else:
        candidates = [("wsl", Path.home() / ".local" / "share" / "article-flow" / "current.json")]
        windows_root = windows_user_root()
        if windows_root:
            candidates.append(("windows", windows_root / ".article-flow" / "current.json"))
    for host, path in candidates:
        record = load_json(path) if path.is_file() else {}
        expected_spec_root = windows_path(SPEC_ROOT) if host == "windows" else str(SPEC_ROOT.resolve())
        expected_source_checkout = windows_path(REPO_ROOT) if host == "windows" else str(REPO_ROOT.resolve())
        expected_script_path = windows_path(SCRIPT_PATH) if host == "windows" else str(SCRIPT_PATH.resolve())
        expected_runs_root = windows_path(runs_root()) if host == "windows" else str(runs_root().resolve())
        publication_root = publication_repo_root()
        expected_publication_root = (
            windows_path(publication_root) if host == "windows" and publication_root
            else str(publication_root.resolve()) if publication_root
            else None
        )
        if host == "windows" and windows_root:
            launcher_path = windows_root / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "article-flow.cmd"
            python_candidates = [
                windows_root / "AppData" / "Local" / "Programs" / "Python" / "Python312" / "python.exe",
                windows_root / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "python.exe",
            ]
            python_exe = next((item for item in python_candidates if item.exists()), None)
            expected_launcher = (
                f"@echo off\r\nrem article-flow managed launcher {CONTROLLER_VERSION}\r\n"
                f"set \"ARTICLE_FLOW_HOME={windows_path(path.parent)}\"\r\n"
                f"set \"ARTICLE_FLOW_RUNS_ROOT={expected_runs_root}\"\r\n"
                f"set \"ARTICLE_FLOW_REPO_ROOT={expected_publication_root}\"\r\n"
                f"\"{windows_path(python_exe)}\" \"{expected_script_path}\" %*\r\n"
            ) if python_exe and expected_publication_root else ""
        else:
            launcher_path = Path.home() / ".local" / "bin" / "article-flow"
            expected_launcher = (
                f"#!/usr/bin/env sh\n# article-flow managed launcher {CONTROLLER_VERSION}\n"
                f"export ARTICLE_FLOW_HOME={shlex.quote(str(path.parent.resolve()))}\n"
                f"export ARTICLE_FLOW_RUNS_ROOT={shlex.quote(expected_runs_root)}\n"
                f"export ARTICLE_FLOW_REPO_ROOT={shlex.quote(str(expected_publication_root))}\n"
                f"exec python3 {shlex.quote(expected_script_path)} \"$@\"\n"
            ) if expected_publication_root else ""
        launcher_agrees = bool(
            expected_launcher
            and launcher_path.is_file()
            and launcher_path.read_bytes() == expected_launcher.encode("utf-8")
        )
        ok = bool(
            record.get("controller_version") == CONTROLLER_VERSION
            and record.get("workflow_version") == workflow()["workflow_version"]
            and record.get("development") is False
            and record.get("linked_checkout") is True
            and record.get("spec_root") == expected_spec_root
            and record.get("source_checkout") == expected_source_checkout
            and record.get("publication_repo_root") == expected_publication_root
            and record.get("captured_material_root") == expected_runs_root
            and record.get("source_commit") == release_source_commit()
            and launcher_agrees
        )
        checks.append({"host": host, "path": str(path), "ok": ok, "controller_version": record.get("controller_version"), "workflow_version": record.get("workflow_version"), "development": record.get("development"), "linked_checkout": record.get("linked_checkout"), "spec_root": record.get("spec_root"), "source_checkout": record.get("source_checkout"), "publication_repo_root": record.get("publication_repo_root"), "captured_material_root": record.get("captured_material_root"), "source_commit": record.get("source_commit"), "launcher": str(launcher_path), "launcher_agrees": launcher_agrees})
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
        "conformance_receipt_schema_version": "1.2.0",
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
                "captured_material_root_match": False,
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
        captured_material_root_match = Path(str(context.get("captured_material_root", ""))).resolve() == runs_root().resolve()
    except (OSError, RuntimeError):
        spec_root_match = False
        runtime_home_match = False
        captured_material_root_match = False
    ok = bool(
        result.returncode == 0
        and context.get("controller_version") == CONTROLLER_VERSION
        and context.get("workflow_version") == workflow()["workflow_version"]
        and spec_root_match
        and runtime_home_match
        and captured_material_root_match
        and bootstrap_result.returncode == 0
        and bootstrap.get("interface") == "local-global-command"
        and bootstrap.get("command") == "article-flow"
        and bootstrap.get("start_command", [])[:2] == ["article-flow", "capture"]
    )
    return {
        "ok": ok,
        "launcher": str(launcher),
        "return_code": result.returncode,
        "controller_version": str(context.get("controller_version", "")),
        "workflow_version": str(context.get("workflow_version", "")),
        "spec_root_match": spec_root_match,
        "runtime_home_match": runtime_home_match,
        "captured_material_root_match": captured_material_root_match,
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
    start.add_argument("--auto", action="store_true", help="Continue synchronously until the voice choice, a blocker, or completion.")
    start.add_argument("--draft-model", choices=DEFAULT_DRAFT_MODEL_POOL, help="Override the next round-robin writing-model assignment without consuming a rotation slot.")
    start.add_argument("--hold-before-publish", action="store_true", help="Stop after publication planning instead of issuing policy approval.")
    add_json(start)

    capture = sub.add_parser("capture", help="Capture one raw article idea verbatim and begin its run.")
    capture_group = capture.add_mutually_exclusive_group()
    capture_group.add_argument("seed", nargs="?")
    capture_group.add_argument("--seed-file")
    capture.add_argument("--slug")
    capture.add_argument("--auto", action="store_true", help="Continue synchronously until the voice choice, a blocker, or completion.")
    capture.add_argument("--draft-model", choices=DEFAULT_DRAFT_MODEL_POOL, help="Override the next round-robin writing-model assignment without consuming a rotation slot.")
    capture.add_argument("--hold-before-publish", action="store_true", help="Stop after publication planning instead of issuing policy approval.")
    add_json(capture)

    advance = sub.add_parser("advance", help="Continue an active-session run until its voice choice, a blocker, or completion.")
    advance.add_argument("run_id")
    advance.add_argument("--max-steps", type=int, default=100)
    add_json(advance)

    choose_voice = sub.add_parser("choose-voice", help="Select one of the three voice paragraphs and optionally continue automatically.")
    choose_voice.add_argument("run_id")
    choose_voice.add_argument("candidate_id")
    choose_voice.add_argument("--feedback")
    choose_voice.add_argument("--auto", action="store_true")
    add_json(choose_voice)

    models = sub.add_parser("models", help="Inspect the immutable writing-model experiment ledger.")
    models_sub = models.add_subparsers(dest="models_command", required=True)
    models_history_parser = models_sub.add_parser("history")
    add_json(models_history_parser)

    voice = sub.add_parser("voice", help="Apply, inspect, or roll back provisional runtime voice learning.")
    voice_sub = voice.add_subparsers(dest="voice_command", required=True)
    voice_apply = voice_sub.add_parser("apply")
    voice_apply.add_argument("run_id")
    add_json(voice_apply)
    voice_history_parser = voice_sub.add_parser("history")
    add_json(voice_history_parser)
    voice_rollback = voice_sub.add_parser("rollback")
    voice_rollback.add_argument("version")
    add_json(voice_rollback)

    listing = sub.add_parser("list", help="List captured ideas, active runs, and returned live links.")
    add_json(listing)

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

    amend = sub.add_parser("amend", help="Change public display text or submit a bounded article naturalization repair.")
    amend.add_argument("run_id")
    amend.add_argument("--title")
    amend.add_argument("--description")
    amend.add_argument("--article", help="Revised Markdown article; deterministic naturalization checks run before downstream reverification.")
    add_json(amend)

    publish = sub.add_parser("publish", help="Plan, renew approval for, or execute one scoped publication revision.")
    mode = publish.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--renew-approval", action="store_true")
    publish.add_argument("run_id")
    publish.add_argument("--approval")
    publish.add_argument("--commit", action="store_true")
    publish.add_argument("--push", action="store_true")
    add_json(publish)

    verify = sub.add_parser("verify-live", help="Verify the exact rendered revision and discovery surfaces.")
    verify.add_argument("run_id")
    add_json(verify)

    attest = sub.add_parser("deployment-attest", help="Accept an operator-deployed commit only when every planned publication blob matches.")
    attest.add_argument("run_id")
    attest.add_argument("--remote-rev", required=True)
    add_json(attest)

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
            emit({"controller_version": CONTROLLER_VERSION, "workflow_version": workflow()["workflow_version"], "interface": "local-global-command", "command": "article-flow", "spec_root": str(SPEC_ROOT), "source_tree_root": str(REPO_ROOT), "publication_repo_root": str(publication_repo_root()) if publication_repo_root() else None, "runtime_home": str(runtime_home()), "captured_material_root": str(runs_root()), "precedence": workflow()["precedence"]}, args.json)
            return EXIT_OK
        if args.command == "install":
            return command_install(args)
        if args.command == "doctor":
            return command_doctor(args)
        if args.command == "start":
            return command_start(args)
        if args.command == "capture":
            return command_start(args)
        if args.command == "advance":
            return command_advance(args)
        if args.command == "choose-voice":
            return command_choose_voice(args)
        if args.command == "models" and args.models_command == "history":
            return command_models_history(args)
        if args.command == "voice":
            if args.voice_command == "apply":
                return command_voice_apply(args)
            if args.voice_command == "history":
                return command_voice_history(args)
            return command_voice_rollback(args)
        if args.command == "list":
            return command_list(args)
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
        if args.command == "amend":
            return command_amend(args)
        if args.command == "publish":
            if args.plan:
                return command_publish_plan(args)
            if args.renew_approval:
                return command_publish_renew_approval(args)
            if not args.approval:
                raise FlowError("--execute requires --approval APPROVAL_ID", EXIT_APPROVAL)
            return command_publish_execute(args)
        if args.command == "verify-live":
            return command_verify_live(args)
        if args.command == "deployment-attest":
            return command_deployment_attest(args)
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
