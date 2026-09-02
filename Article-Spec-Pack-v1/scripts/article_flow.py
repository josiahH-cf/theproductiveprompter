#!/usr/bin/env python3
"""Provider-neutral controller for The Productive Prompter article workflow."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import difflib
import errno
import functools
import hashlib
import html
import http.client
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


CONTROLLER_VERSION = "3.1.0"
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
            "For the normal human_decision, show the controller's three voice choices plus its regeneration option and wait; never choose or reject the set without the operator's decision.",
            "For human_action, show the controller's single handoff and wait for the operator or a credentialed host to complete it.",
            "For run_command, run the exact command array returned by the controller. Use advance for active-session automation and safe resumption.",
            "Stop on complete, terminal, or an unresolved capability or decision.",
        ],
        "capability_requirement": "This interface requires local command execution. A cloud-only chat without access to this machine cannot run it.",
    }
REVIEW_STATES = {"INTENT_REVIEW", "ARTICLE_RECIPE", "VOICE_PROBE", "EDITORIAL_QA"}
AUTO_REVIEW_STATES = {"INTENT_REVIEW", "ARTICLE_RECIPE", "EDITORIAL_QA"}
DETERMINISTIC_STATES = {"VISUAL_RENDER", "VOICE_LEARNING", "PACKAGE", "PUBLISH_APPROVAL", "PUBLISH", "LIVE_VERIFICATION", "COMPLETE"}
MODEL_STATES = {
    "RESEARCH_PLAN",
    "RESEARCH",
    "INTENT_REVIEW",
    "ARTICLE_RECIPE",
    "BRIEF",
    "VISUAL_PLAN",
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
    "VISUAL_PLAN": {"structured-output"},
    "VOICE_PROBE": {"structured-output"},
    "DRAFT": {"long-form"},
    "CLAIM_VERIFICATION": {"structured-output", "research"},
    "EDIT": {"long-form"},
    "POST_EDIT_CLAIM_VERIFICATION": {"structured-output", "research"},
    "EDITORIAL_QA": {"structured-output"},
}
LEGACY_WORKFLOW_VERSION = "2.0.0"
V3_WRITING_STATES = {"DRAFT", "VOICE_PROBE", "EDIT"}
# A human-authored article may be amended at editorial QA when a scoped finding
# needs a direct correction, and after packaging while publication is held. The
# brief's public display text has no owning stage after BRIEF, so it stays
# correctable for as long as the article is under review.
ARTICLE_AMENDABLE_STATES = {"EDITORIAL_QA", "PACKAGE", "PUBLISH_APPROVAL"}
DISPLAY_TEXT_AMENDABLE_STATES = {
    "EDIT",
    "POST_EDIT_CLAIM_VERIFICATION",
    "EDITORIAL_QA",
    "PACKAGE",
    "PUBLISH_APPROVAL",
}
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


def immutable_write(path: Path, data: bytes) -> bool:
    """Create attempt-scoped evidence once; accept only an identical replay."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        if path.is_file() and path.read_bytes() == data:
            return False
        raise FlowError(
            f"Immutable attempt artifact already exists with different bytes: {path}",
            EXIT_INTEGRITY,
            {"path": str(path), "existing_sha256": sha256_path(path) if path.is_file() else None, "new_sha256": sha256_bytes(data)},
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        # Preserve a partial create as crash evidence; future recovery must not
        # overwrite it or mistake it for a completed immutable artifact.
        raise
    return True


def write_json_immutable(path: Path, value: Any) -> bool:
    return immutable_write(path, (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


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


def is_v31_run(run: dict[str, Any]) -> bool:
    parts = str(run.get("workflow_version", "0.0.0")).split(".")
    try:
        return (int(parts[0]), int(parts[1])) >= (3, 1)
    except (IndexError, ValueError):
        return False


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


def release_lock_file(path: Path, *, wait_seconds: float = 1.0) -> None:
    """Remove an owned lock after transient Windows reader handles close."""
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)


def valid_lock_owner(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    pid = value.get("pid")
    token = value.get("token")
    namespace = value.get("namespace")
    created_at = value.get("created_at")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    if not isinstance(namespace, str) or not namespace:
        return False
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
        return False
    if not isinstance(created_at, str):
        return False
    try:
        parse_time(created_at)
    except ValueError:
        return False
    return True


def read_lock_owner(path: Path) -> tuple[str, dict[str, Any] | None]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return "missing", None
    except OSError:
        return "unreadable", None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "malformed", None
    if not valid_lock_owner(value):
        return "malformed", value if isinstance(value, dict) else None
    return "valid", value


def publish_lock_owner(path: Path, owner: dict[str, Any]) -> bool:
    """Atomically expose a fully written owner record without replacing a lock."""
    if not valid_lock_owner(owner):
        raise FlowError("Refusing to publish an invalid lock owner record", EXIT_INTEGRITY, owner)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return False
    descriptor, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.owner-")
    temp_path = Path(temp_name)
    try:
        handle = os.fdopen(descriptor, "wb")
        descriptor = -1
        with handle:
            handle.write(canonical_json(owner))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            # A same-directory hard link is an atomic no-replace publication on
            # both NTFS/Windows and POSIX filesystems. Contenders can therefore
            # observe either no owner or one complete owner, never partial bytes.
            os.link(temp_path, path)
        except OSError as exc:
            if isinstance(exc, FileExistsError) or exc.errno == errno.EEXIST or getattr(exc, "winerror", None) == 183:
                return False
            raise FlowError(f"Cannot atomically publish shared lock owner: {path}: {exc}", EXIT_INTEGRITY) from exc
        return True
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        release_lock_file(temp_path)


def release_owned_lock_file(path: Path, token: str, *, wait_seconds: float = 1.0) -> bool:
    """Release only the lock that still contains this acquisition's token."""
    deadline = time.monotonic() + wait_seconds
    while True:
        status, owner = read_lock_owner(path)
        if status != "valid" or owner is None or owner.get("token") != token:
            return False
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)


def recover_dead_same_namespace_lock(path: Path, owner: dict[str, Any], deadline: float) -> bool:
    """Elect one contender to recover an owner whose local PID is proven dead."""
    prior_token = str(owner["token"])
    recovery_path = path.with_name(f".{path.name}.recover-{prior_token}")
    recovery_token = secrets.token_hex(16)
    recovery_owner = {
        "pid": os.getpid(),
        "namespace": lock_namespace(),
        "created_at": utc_now(),
        "token": recovery_token,
    }
    if not publish_lock_owner(recovery_path, recovery_owner):
        if time.monotonic() >= deadline:
            raise FlowError(
                f"Timed out waiting for shared Article Flow lock recovery: {path}",
                details={"lock": str(path), "recovery_lock": str(recovery_path)},
            )
        return False
    try:
        status, current = read_lock_owner(path)
        if status != "valid" or current is None or current.get("token") != prior_token:
            return True
        if current.get("namespace") != lock_namespace() or process_is_alive(int(current["pid"])):
            return True
        recovered = path.with_name(f"{path.name}.recovered-{prior_token}")
        try:
            path.replace(recovered)
        except FileNotFoundError:
            pass
        return True
    finally:
        if not release_owned_lock_file(recovery_path, recovery_token):
            raise FlowError("Shared lock recovery ownership changed unexpectedly", EXIT_INTEGRITY, {"lock": str(recovery_path)})


@contextlib.contextmanager
def shared_lock(path: Path, *, stale_seconds: int | None = None, wait_seconds: float = 15.0) -> Iterator[None]:
    """Cross-host lock with conservative recovery and token-checked release."""
    del stale_seconds  # Kept as a source-compatible argument; age never proves ownership loss.
    token = secrets.token_hex(16)
    owner = {
        "pid": os.getpid(),
        "namespace": lock_namespace(),
        "created_at": utc_now(),
        "token": token,
    }
    deadline = time.monotonic() + wait_seconds
    while not publish_lock_owner(path, owner):
        status, current = read_lock_owner(path)
        reason = "owner record is incomplete or malformed and requires manual recovery"
        if status == "missing":
            continue
        if status == "valid" and current is not None:
            if current["namespace"] != lock_namespace():
                reason = "cross-host ownership cannot be proven dead and requires manual recovery"
            elif process_is_alive(int(current["pid"])):
                reason = "the owning process is still alive"
            else:
                if recover_dead_same_namespace_lock(path, current, deadline):
                    continue
                reason = "another process is recovering the proven-dead owner"
        if time.monotonic() >= deadline:
            raise FlowError(
                f"Timed out waiting for shared Article Flow state: {path}; {reason}",
                details={"lock": str(path), "reason": reason, "owner": current},
            )
        time.sleep(0.02)
    try:
        yield
    finally:
        if not release_owned_lock_file(path, token):
            raise FlowError("Shared lock ownership changed before release; successor was preserved", EXIT_INTEGRITY, {"lock": str(path), "token": token})


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
    # This head lives only in the caller's in-memory projection until
    # save_run commits the corresponding cache mutations.  A crash therefore
    # leaves run.json pointing at the preceding applied head, and load_run can
    # fold exactly the verified tail after it.
    run["applied_event_head"] = {
        "sequence": sequence,
        "event_hash": event["event_hash"],
    }
    return event


def verify_event_log(
    directory: Path,
    run: dict[str, Any],
) -> tuple[bool, str | None, str, list[dict[str, Any]]]:
    """Verify one immutable in-memory snapshot of the event log.

    Observers must never verify one version of ``events.jsonl`` and then fold a
    newer, possibly partial version.  Returning the parsed snapshot keeps
    validation and recovery on the same hash-chained head.
    """
    log_path = directory / run["event_log"]
    if not log_path.is_file():
        return False, "event log missing", "NEW", []
    previous_hash: str | None = None
    derived_state = "NEW"
    events: list[dict[str, Any]] = []
    snapshot = log_path.read_text(encoding="utf-8")
    for expected_sequence, line in enumerate(snapshot.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            return False, f"invalid event JSON: {exc}", derived_state, events
        schema_errors = validate_instance_schema(event, "event.schema.json")
        if schema_errors:
            return False, f"event schema mismatch at sequence {expected_sequence}: {schema_errors[0]}", derived_state, events
        hash_input = dict(event)
        recorded_hash = hash_input.pop("event_hash", None)
        if hash_input.get("sequence") != expected_sequence or hash_input.get("previous_event_hash") != previous_hash:
            return False, f"event chain mismatch at sequence {expected_sequence}", derived_state, events
        actual_hash = sha256_bytes((previous_hash or "").encode("ascii") + canonical_json(hash_input))
        if recorded_hash != actual_hash:
            return False, f"event hash mismatch at sequence {expected_sequence}", derived_state, events
        previous_hash = str(recorded_hash)
        if event.get("type") == "STATE_TRANSITION":
            transition_payload = event.get("payload", {})
            if transition_payload.get("from") != derived_state:
                return False, f"state transition source mismatch at sequence {expected_sequence}", derived_state, events
            derived_state = str(transition_payload.get("to", derived_state))
        events.append(event)
    return True, None, derived_state, events


def roll_forward_run_cache(
    directory: Path,
    run: dict[str, Any],
    derived_state: str,
    events: list[dict[str, Any]],
) -> bool:
    """Recover deterministic run.json fields from the verified event-log WAL.

    ``run.json`` is a cache.  Artifact records, dispatch ordinals, and state
    transitions are committed to the hash-chained event log before that cache
    is rewritten, so a process death in that window must roll the cache forward
    instead of making the run permanently unloadable.  Only fields whose value
    is completely determined by verified events are recovered here.
    """
    changed = False
    cached_state = str(run.get("state") or "NEW")
    cached_status = str(run.get("status") or "ACTIVE")
    cached_head = run.get("applied_event_head")
    legacy_without_head = not isinstance(cached_head, dict)
    cached_sequence = 0
    if isinstance(cached_head, dict):
        try:
            cached_sequence = int(cached_head.get("sequence", 0))
        except (TypeError, ValueError) as exc:
            raise FlowError("Run cache has an invalid applied event head", EXIT_INTEGRITY, cached_head) from exc
        if cached_sequence < 1 or cached_sequence > len(events):
            raise FlowError("Run cache applied event head is outside the verified event log", EXIT_INTEGRITY, cached_head)
        applied_event = events[cached_sequence - 1]
        if cached_head.get("event_hash") != applied_event.get("event_hash"):
            raise FlowError("Run cache applied event head does not match the verified event log", EXIT_INTEGRITY, cached_head)
    # Old released runs predate the head marker.  Their cache-only phases
    # (especially WAITING_HUMAN) are authoritative and must not be recomputed
    # from historical events.  The in-memory projection is migrated to the
    # verified head; the first mutation under run_lock persists it before any
    # subsequent event can be appended.
    tail_events = [] if legacy_without_head else events[cached_sequence:]

    recovered_artifacts: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "ARTIFACT_RECORDED":
            continue
        payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
        item = payload.get("artifact")
        if not isinstance(item, dict):
            raise FlowError("Artifact event lacks an artifact record", EXIT_INTEGRITY, event.get("sequence"))
        artifact_errors = validate_instance_schema(item, "artifact.schema.json")
        if artifact_errors:
            raise FlowError("Artifact event contains an invalid record", EXIT_INTEGRITY, artifact_errors)
        recovered_artifacts = [prior for prior in recovered_artifacts if prior.get("type") != item.get("type")]
        recovered_artifacts.append(item)

    cached_artifacts = run.get("artifact_index", [])
    newly_recovered = [item for item in recovered_artifacts if item not in cached_artifacts]
    # Validate only records being rolled forward into the cache.  Normal
    # operation validates an artifact at its point of use (notably task packets
    # in ``current_packet``), which lets that path persist an explicit BLOCKED
    # integrity state rather than making load itself mutate state.
    for item in newly_recovered:
        try:
            artifact_path_value = (directory / safe_relative(str(item.get("path", "")))).resolve()
            artifact_path_value.relative_to(directory.resolve())
        except (FlowError, ValueError) as exc:
            raise FlowError("Artifact event names an unsafe path", EXIT_INTEGRITY, item) from exc
        if not artifact_path_value.is_file():
            raise FlowError("Artifact recorded by the event log is missing", EXIT_INTEGRITY, item)
        actual_hash = sha256_path(artifact_path_value)
        if actual_hash != item.get("sha256"):
            raise FlowError(
                "Artifact recorded by the event log changed",
                EXIT_INTEGRITY,
                {"path": str(artifact_path_value), "expected_sha256": item.get("sha256"), "actual_sha256": actual_hash},
            )
    if cached_artifacts != recovered_artifacts:
        run["artifact_index"] = recovered_artifacts
        changed = True

    recovered_attempts = {str(state): int(value) for state, value in run.get("attempts", {}).items()}
    # Route state is a cache baseline plus an exact post-head tail.  Released
    # logs predate explicit repair-clear semantics, so replaying their whole
    # history can both erase live failure counts and resurrect failures that a
    # human repair already cleared.  A headless legacy cache therefore remains
    # authoritative; after migration, only verified events beyond its saved
    # head are applied here.
    recovered_route_failures: dict[str, dict[str, int]] = {
        str(state): {str(key): int(value) for key, value in failures.items()}
        for state, failures in run.get("route_failures", {}).items()
        if isinstance(failures, dict)
    }
    recovered_route_retry_candidates: dict[str, list[dict[str, Any]]] = {
        str(state): [json.loads(json.dumps(item)) for item in candidates if isinstance(item, dict)]
        for state, candidates in run.get("route_retry_candidates", {}).items()
        if isinstance(candidates, list)
    }
    recovered_baselines = {
        str(state): int(value)
        for state, value in run.get("attempt_baselines", {}).items()
    }
    latest_dispatch: dict[str, dict[str, Any]] = {}
    active_repair_context = run.get("pending_repair") if isinstance(run.get("pending_repair"), dict) else None
    repair_recovery_error: dict[str, Any] | None = None
    latest_transition_sequence = 0
    for event in events:
        payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
        sequence = int(event.get("sequence", 0))
        route_event_is_tail = not legacy_without_head and sequence > cached_sequence
        if event.get("type") == "TASK_DISPATCHED":
            state = str(payload.get("state") or "")
            try:
                attempt = int(payload.get("attempt", 0))
            except (TypeError, ValueError):
                attempt = 0
            if not state or attempt < 1:
                raise FlowError("Task dispatch event has an invalid identity", EXIT_INTEGRITY, event.get("sequence"))
            recovered_attempts[state] = max(int(recovered_attempts.get(state, 0)), attempt)
            latest_dispatch[state] = {
                "sequence": sequence,
                "attempt": attempt,
                "task_packet_sha256": str(payload.get("task_packet_sha256") or ""),
            }
            if route_event_is_tail:
                recovered_route_retry_candidates.pop(state, None)
        elif event.get("type") == "ARTIFACT_RECORDED":
            item = payload.get("artifact", {}) if isinstance(payload.get("artifact"), dict) else {}
            artifact_type = str(item.get("type", ""))
            packet_match = re.fullmatch(r"task-packet:([^:]+):(\d+)", artifact_type)
            receipt_match = re.fullmatch(r"model-call:([^:]+):(\d+)", artifact_type)
            match = packet_match or receipt_match
            if match:
                state = match.group(1)
                recovered_attempts[state] = max(int(recovered_attempts.get(state, 0)), int(match.group(2)))
        elif event.get("type") in {"MODEL_EXECUTION_STARTED", "MODEL_ROUTE_FAILURE", "MODEL_OUTPUT_REJECTED"}:
            identity = event_task_identity(event)
            if identity:
                state, attempt, _ = identity
                recovered_attempts[state] = max(int(recovered_attempts.get(state, 0)), attempt)
            else:
                state = str(payload.get("state") or event.get("state") or "")
            if route_event_is_tail and event.get("type") == "MODEL_ROUTE_FAILURE" and state:
                route = payload.get("route") if isinstance(payload.get("route"), dict) else payload
                provider = str(route.get("provider") or "")
                model = str(route.get("model") or "")
                if provider and model:
                    key = f"{provider}:{model}"
                    failures = recovered_route_failures.setdefault(state, {})
                    failures[key] = int(failures.get(key, 0)) + 1
            if route_event_is_tail and event.get("type") == "MODEL_ROUTE_FAILURE" and state:
                remaining = payload.get("remaining_routes")
                if isinstance(remaining, list):
                    recovered_route_retry_candidates[state] = [
                        json.loads(json.dumps(item))
                        for item in remaining
                        if isinstance(item, dict)
                    ]
        elif event.get("type") == "MODEL_ROUTE_RECOVERED" and route_event_is_tail:
            state = str(payload.get("state") or event.get("state") or "")
            route = payload.get("route") if isinstance(payload.get("route"), dict) else {}
            key = f"{route.get('provider')}:{route.get('model')}"
            recovered_route_failures.setdefault(state, {}).pop(key, None)
        elif event.get("type") == "REPAIR":
            source_state = str(payload.get("source_state") or event.get("state") or "")
            repair_state = str(payload.get("repair_state") or "")
            context = payload.get("repair_context")
            if route_event_is_tail and payload.get("clear_route_failures", True) and repair_state:
                recovered_route_failures.pop(repair_state, None)
            if route_event_is_tail and repair_state:
                recovered_route_retry_candidates.pop(repair_state, None)
            if repair_state and payload.get("execution_count_baseline") is not None:
                try:
                    recovered_baselines[repair_state] = int(payload["execution_count_baseline"])
                except (TypeError, ValueError) as exc:
                    raise FlowError("Repair event has an invalid execution baseline", EXIT_INTEGRITY, sequence) from exc
            if isinstance(context, dict):
                context_source = str(context.get("source_stage") or "")
                context_repair = str(context.get("repair_state") or "")
                normalized_context = json.loads(json.dumps(context))
                legacy_directed_context = False
                if context_source == source_state and context_repair != repair_state:
                    try:
                        source_definition = state_definition(source_state, run)
                        legacy_directed_context = (
                            context_repair == str(source_definition.get("repair_state") or "")
                            and repair_state
                            == str(effective_repair_state(source_definition, context.get("findings") or []) or "")
                        )
                    except FlowError:
                        legacy_directed_context = False
                    if legacy_directed_context:
                        normalized_context["repair_state"] = repair_state
                if context_source != source_state or (context_repair != repair_state and not legacy_directed_context):
                    repair_recovery_error = {
                        "reason": "repair_event_context_identity_mismatch",
                        "sequence": sequence,
                    }
                    active_repair_context = None
                else:
                    active_repair_context = normalized_context
                    repair_recovery_error = None
            elif bool(payload.get("repair_context_required")):
                repair_recovery_error = {
                    "reason": "repair_event_lacks_required_context",
                    "sequence": sequence,
                    "source_state": source_state,
                    "repair_state": repair_state,
                }
                active_repair_context = None
        elif event.get("type") == "GATE_RECORDED" and active_repair_context:
            if (
                payload.get("state") == active_repair_context.get("repair_state")
                and payload.get("outcome") == "PASS"
            ):
                active_repair_context = None
                repair_recovery_error = None
        if event.get("type") == "STATE_TRANSITION":
            transition_payload = payload
            if transition_payload.get("to") == derived_state:
                latest_transition_sequence = sequence
            if active_repair_context and (
                transition_payload.get("from") == active_repair_context.get("repair_state")
                and transition_payload.get("to") != active_repair_context.get("repair_state")
            ):
                active_repair_context = None
                repair_recovery_error = None
    if run.get("attempts") != recovered_attempts:
        run["attempts"] = recovered_attempts
        changed = True
    recovered_route_failures = {
        state: failures for state, failures in recovered_route_failures.items() if failures
    }
    if run.get("route_failures", {}) != recovered_route_failures:
        run["route_failures"] = recovered_route_failures
        changed = True
    recovered_route_retry_candidates = {
        state: candidates
        for state, candidates in recovered_route_retry_candidates.items()
        if candidates
    }
    if run.get("route_retry_candidates", {}) != recovered_route_retry_candidates:
        run["route_retry_candidates"] = recovered_route_retry_candidates
        changed = True
    if run.get("attempt_baselines", {}) != recovered_baselines:
        run["attempt_baselines"] = recovered_baselines
        changed = True
    if active_repair_context is not None:
        if run.get("pending_repair") != active_repair_context:
            run["pending_repair"] = active_repair_context
            changed = True
    elif "pending_repair" in run:
        run.pop("pending_repair", None)
        changed = True
    if repair_recovery_error is not None:
        if run.get("repair_recovery_error") != repair_recovery_error:
            run["repair_recovery_error"] = repair_recovery_error
            changed = True
    elif "repair_recovery_error" in run:
        run.pop("repair_recovery_error", None)
        changed = True

    state_changed = cached_state != derived_state
    if run.get("state") != derived_state:
        run["state"] = derived_state
        run["status"] = "COMPLETE" if derived_state == "COMPLETE" else "TERMINAL" if derived_state == "TERMINAL" else "ACTIVE"
        changed = True

    # Derive the phase after the latest transition into the current state.  A
    # same-state repair transition is a real boundary even though ``state`` did
    # not change in run.json.
    dispatch = latest_dispatch.get(derived_state)
    if run.get("status") not in {"COMPLETE", "TERMINAL"}:
        recovered_status: str | None = None
        if repair_recovery_error is not None:
            recovered_status = "BLOCKED"
        tail_transition_sequence = max(
            (
                int(event.get("sequence", 0))
                for event in tail_events
                if event.get("type") == "STATE_TRANSITION"
                and (event.get("payload") or {}).get("to") == derived_state
            ),
            default=0,
        )
        trailing_escalation = any(
            event.get("type") == "ESCALATION"
            and event.get("state") == derived_state
            and int(event.get("sequence", 0)) > tail_transition_sequence
            for event in tail_events
        )
        if trailing_escalation:
            recovered_status = "BLOCKED"
        elif tail_events and dispatch and dispatch["sequence"] > latest_transition_sequence:
            exact_later = []
            blocking_escalation = False
            for event in events:
                if int(event.get("sequence", 0)) <= dispatch["sequence"]:
                    continue
                identity = event_task_identity(event)
                if identity and identity == (
                    derived_state,
                    int(dispatch["attempt"]),
                    str(dispatch["task_packet_sha256"]),
                ):
                    exact_later.append(event)
                if event.get("type") == "ESCALATION" and (
                    identity == (
                        derived_state,
                        int(dispatch["attempt"]),
                        str(dispatch["task_packet_sha256"]),
                    )
                    or (identity is None and event.get("state") == derived_state)
                ):
                    # New escalations bind the exact attempt.  Legacy events
                    # did not carry that identity, so a post-dispatch
                    # escalation in the current state is the conservative
                    # lower-bound authority for BLOCKED.
                    blocking_escalation = True
            tail_exact = [
                event for event in exact_later
                if int(event.get("sequence", 0)) > cached_sequence
            ]
            later_types = {str(event.get("type")) for event in tail_exact}
            gate_receipt_committed = any(
                event.get("type") == "ARTIFACT_RECORDED"
                and str((event.get("payload") or {}).get("artifact", {}).get("type", "")).startswith("gate-receipt:")
                for event in tail_events
                if int(event.get("sequence", 0)) > dispatch["sequence"]
            )
            if blocking_escalation:
                recovered_status = "BLOCKED"
            elif "GATE_RECORDED" in later_types:
                gate_event = next(
                    event for event in reversed(tail_exact)
                    if event.get("type") == "GATE_RECORDED"
                )
                gate_outcome = str((gate_event.get("payload") or {}).get("outcome") or "")
                if (
                    derived_state in REVIEW_STATES
                    and (
                        gate_outcome == "ESCALATE"
                        or (gate_outcome == "PASS" and not automation_enabled(run))
                    )
                ):
                    recovered_status = "WAITING_HUMAN"
                else:
                    recovered_status = "BLOCKED"
            elif gate_receipt_committed:
                # ARTIFACT_RECORDED is the durable receipt commit.  Until the
                # task-bound GATE_RECORDED/follow-on phase is present, replay
                # must fail closed.
                recovered_status = "BLOCKED"
            elif "RETRY" in later_types:
                model_receipt_exists = any(
                    event.get("type") == "ARTIFACT_RECORDED"
                    and (event.get("payload") or {}).get("artifact", {}).get("type")
                    == f"model-call:{derived_state}:{dispatch['attempt']}"
                    for event in events
                )
                recovered_status = "WAITING_MODEL" if model_receipt_exists else "ACTIVE"
            elif "MODEL_ROUTE_FAILURE" in later_types:
                # The failure consumes the execution claim, but only RETRY
                # durably abandons its dispatched packet.  Keep it current so
                # current_packet can append that exact retry before minting a
                # successor.
                recovered_status = "WAITING_MODEL"
            elif "MODEL_EXECUTION_STARTED" in later_types:
                # A durable claim with no terminal evidence is recovered by
                # current_packet, which records one RETRY before minting a new
                # ordinal.  Keep the packet discoverable until then.
                recovered_status = "WAITING_MODEL"
            elif dispatch["sequence"] > cached_sequence:
                recovered_status = "WAITING_MODEL"
        elif (
            legacy_without_head
            and cached_status == "ACTIVE"
            and dispatch
            and dispatch["sequence"] > latest_transition_sequence
        ):
            later_decision = any(
                int(event.get("sequence", 0)) > dispatch["sequence"]
                and event.get("type") in {
                    "GATE_RECORDED",
                    "MODEL_OUTPUT_REJECTED",
                    "RETRY",
                    "ESCALATION",
                    "STATE_TRANSITION",
                    "TERMINAL",
                }
                and (
                    event.get("state") == derived_state
                    or (event.get("payload") or {}).get("state") == derived_state
                )
                for event in events
            )
            if not later_decision:
                # Released headless caches still need the old WAL guarantee:
                # a durable dispatch whose final cache save was interrupted is
                # pending.  Restrict this migration rule to stale ACTIVE so
                # stable BLOCKED/WAITING_HUMAN legacy phases remain untouched.
                recovered_status = "WAITING_MODEL"
        elif state_changed or tail_transition_sequence:
            recovered_status = "ACTIVE"
        if recovered_status is not None and run.get("status") != recovered_status:
            run["status"] = recovered_status
            changed = True

    if events:
        verified_head = {
            "sequence": int(events[-1]["sequence"]),
            "event_hash": str(events[-1]["event_hash"]),
        }
        if run.get("applied_event_head") != verified_head:
            run["applied_event_head"] = verified_head
            changed = True

    if changed:
        errors = validate_instance_schema(run, "run.schema.json")
        if errors:
            raise FlowError("Recovered run cache is invalid", EXIT_INTEGRITY, errors)
    return changed


def load_run(run_id: str) -> tuple[Path, dict[str, Any]]:
    directory = run_dir(run_id)
    path = directory / "run.json"
    if not path.is_file():
        raise FlowError(f"Run not found: {run_id}")
    run = load_json(path)
    errors = validate_instance_schema(run, "run.schema.json")
    if errors:
        raise FlowError(f"Run schema failed: {errors[0]}", EXIT_INTEGRITY, errors)
    ok, error, derived_state, events = verify_event_log(directory, run)
    if not ok:
        raise FlowError(f"Run event log failed integrity: {error}", EXIT_INTEGRITY)
    # Recovery is deliberately observer-pure.  A status/watch call may run
    # while another process owns the mutation lock; it must not overwrite the
    # writer's richer cache with a stale projection.
    roll_forward_run_cache(directory, run, derived_state, events)
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
    persisted_cache = load_json(directory / "run.json")
    migrate_event_head = not isinstance(persisted_cache.get("applied_event_head"), dict)
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
        # The caller's pre-lock snapshot is advisory only.  Refresh it in
        # place after ownership so every mutation starts from one freshly
        # verified, event-folded view without breaking references held by the
        # caller.
        fresh_directory, fresh_run = load_run(str(run["run_id"]))
        if fresh_directory.resolve() != directory.resolve():
            raise FlowError("Run lock resolved a different run directory", EXIT_INTEGRITY)
        run.clear()
        run.update(fresh_run)
        if migrate_event_head and run.get("applied_event_head"):
            # Establish the exact legacy baseline before permitting a new WAL
            # append.  If the process dies after the next append, recovery can
            # distinguish that unapplied tail from historical events whose
            # cache-only phases must be preserved.
            save_run(directory, run)
        yield
    finally:
        release_lock_file(lock_path)


def persist_recovered_cache(directory: Path, run: dict[str, Any]) -> None:
    """Serialize persistence of an observer-pure recovered run projection."""
    lock_path = directory / ".lock"
    owns_lock = False
    if lock_path.is_file():
        try:
            lock = load_json(lock_path)
            owns_lock = (
                int(lock.get("pid", -1)) == os.getpid()
                and str(lock.get("namespace", "")) == lock_namespace()
            )
        except (FlowError, TypeError, ValueError):
            owns_lock = False
    if owns_lock:
        save_run(directory, run)
        return
    with run_lock(directory, run):
        save_run(directory, run)


def transition(directory: Path, run: dict[str, Any], new_state: str, actor: str, reason: str) -> None:
    old_state = run["state"]
    append_event(directory, run, "STATE_TRANSITION", actor, {"from": old_state, "to": new_state, "reason": reason})
    run["state"] = new_state
    run["status"] = "COMPLETE" if new_state == "COMPLETE" else "TERMINAL" if new_state == "TERMINAL" else "ACTIVE"
    save_run(directory, run)


def record_artifact(
    directory: Path,
    run: dict[str, Any],
    path: Path,
    artifact_type: str,
    producer: dict[str, Any],
    visibility: str = "private",
    inputs: Iterable[str] = (),
    *,
    expected_bytes: bytes | None = None,
) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(directory.resolve()).as_posix()
    except ValueError as exc:
        raise FlowError(f"Artifact must live inside its run: {path}") from exc
    data = resolved.read_bytes()
    if expected_bytes is not None:
        if data != expected_bytes:
            raise FlowError(
                "Artifact bytes changed before their immutable record was committed",
                EXIT_INTEGRITY,
                {
                    "path": str(resolved),
                    "expected_sha256": sha256_bytes(expected_bytes),
                    "actual_sha256": sha256_bytes(data),
                },
            )
        # Build the evidence record from the already accepted snapshot, not a
        # later independent read that could attest different bytes.
        data = expected_bytes
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


VERIFICATION_OWN_OUTPUT_CRITERIA = frozenset({
    "valid_json",
    "schema",
    "run_identity",
    "claim_evidence",
    "no_memory_citations",
    "freshness",
    "source_disagreement",
    "source_resolution",
})


def effective_repair_state(definition: dict[str, Any], findings: list[dict[str, Any]]) -> str | None:
    """Route a repair by what its findings are about.

    A stage declares one repair state, but a gate rejects for two different
    reasons: the artifact just submitted is itself wrong, or the upstream work
    it describes is. POST_EDIT_CLAIM_VERIFICATION declares EDIT because a claim
    that cannot be verified means the article must change, yet every code-owned
    check at that gate validates the ledger it just produced. A malformed
    source URL therefore rewrote the article instead of the record naming it,
    and the rewrite could regress work the ledger had already accepted.

    The gate-receipt and task-packet schemas already carry `repair_state` on
    each finding, so honour it when the findings agree and fall back to the
    stage's declaration otherwise. An operator repair after the window is spent
    still uses the declared state, which keeps the escalation path to EDIT for
    a claim that genuinely cannot be verified.
    """
    # A finding may only redirect between the two stages already implicated:
    # the one that produced the rejected artifact and the one the workflow
    # declares. Anything else is not a routing decision the controller made.
    routable = {str(definition.get("id") or ""), str(definition.get("repair_state") or "")} - {""}
    directed = {
        str(item.get("repair_state"))
        for item in findings
        if isinstance(item, dict) and str(item.get("repair_state") or "") in routable
    }
    if len(directed) == 1:
        return directed.pop()
    declared = definition.get("repair_state")
    state_id = str(definition.get("id") or "")
    if (
        not directed
        and state_id in {"CLAIM_VERIFICATION", "POST_EDIT_CLAIM_VERIFICATION"}
        and findings
        and all(
            str(item.get("criterion")) in VERIFICATION_OWN_OUTPUT_CRITERIA
            for item in findings
            if isinstance(item, dict)
        )
    ):
        # Receipts written before findings carried a destination still name
        # criteria that only validate the ledger the stage produced, so the
        # direction is recoverable rather than lost.  Runs recorded before this
        # change therefore route their repairs correctly too.
        return state_id
    return str(declared) if declared else None


def write_gate_receipt(
    directory: Path,
    run: dict[str, Any],
    gate_id: str,
    outcome: str,
    findings: list[dict[str, Any]],
    evaluator: dict[str, Any],
    repair_state: str | None = None,
    *,
    task_state: str | None = None,
    task_attempt: int | None = None,
    task_packet_sha256: str | None = None,
) -> Path:
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
    task_binding = None
    if task_state is not None or task_attempt is not None or task_packet_sha256 is not None:
        if task_state is None or task_attempt is None or task_packet_sha256 is None:
            raise FlowError("Task-bound gate receipts require the complete task identity", EXIT_INTEGRITY)
        task_binding = {
            "state": task_state,
            "attempt": task_attempt,
            "task_packet_sha256": task_packet_sha256,
        }
    receipt = {
        "gate_receipt_schema_version": "1.1.0" if task_binding else "1.0.0",
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
    if task_binding:
        receipt["task_binding"] = task_binding
    errors = validate_instance_schema(receipt, "gate-receipt.schema.json")
    if errors:
        raise FlowError("Controller generated an invalid gate receipt", EXIT_INTEGRITY, errors)
    path = directory / "receipts" / f"{gate_id.lower()}-{len(list((directory / 'receipts').glob('*.json'))) + 1}.json"
    receipt_bytes = (json.dumps(receipt, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    receipt_hash = sha256_bytes(receipt_bytes)
    if task_binding:
        # ARTIFACT_RECORDED is the gate decision's durable commit.  Persist a
        # fail-closed phase with that artifact so a crash before GATE_RECORDED
        # cannot leave the cache advertising a replayable model task.
        run["status"] = "BLOCKED"
    try:
        immutable_write(path, receipt_bytes)
        if not path.is_file() or sha256_path(path) != receipt_hash:
            raise FlowError("Gate receipt changed after immutable creation", EXIT_INTEGRITY)
        record_artifact(
            directory,
            run,
            path,
            f"gate-receipt:{gate_id}",
            {"actor": evaluator.get("type", "code")},
            expected_bytes=receipt_bytes,
        )
        if not path.is_file() or sha256_path(path) != receipt_hash:
            raise FlowError("Gate receipt changed after artifact recording", EXIT_INTEGRITY)
    except (FlowError, OSError) as exc:
        try:
            actual_hash = sha256_path(path) if path.is_file() else None
        except OSError:
            actual_hash = None
        issue = {
            "reason": "gate_receipt_evidence_changed_during_commit",
            "gate_id": gate_id,
            "path": str(path),
            "expected_sha256": receipt_hash,
            "actual_sha256": actual_hash,
            "error": str(exc),
        }
        if task_binding:
            block_attempt_reconciliation(
                directory,
                run,
                str(task_binding["state"]),
                int(task_binding["attempt"]),
                str(task_binding["task_packet_sha256"]),
                issue,
            )
        else:
            run["status"] = "BLOCKED"
            append_event(directory, run, "ESCALATION", "controller", {"state": run["state"], **issue})
            save_run(directory, run)
        raise FlowError("Gate receipt evidence changed during commit", EXIT_INTEGRITY, issue) from exc
    event_payload = {"gate_id": gate_id, "outcome": outcome, "findings": findings}
    if task_binding:
        event_payload.update(task_binding)
    append_event(directory, run, "GATE_RECORDED", evaluator.get("type", "code"), event_payload)
    try:
        committed_hash = sha256_path(path) if path.is_file() else None
    except OSError:
        committed_hash = None
    if committed_hash != receipt_hash:
        issue = {
            "reason": "gate_receipt_changed_after_gate_event",
            "gate_id": gate_id,
            "path": str(path),
            "expected_sha256": receipt_hash,
            "actual_sha256": committed_hash,
        }
        if task_binding:
            block_attempt_reconciliation(
                directory,
                run,
                str(task_binding["state"]),
                int(task_binding["attempt"]),
                str(task_binding["task_packet_sha256"]),
                issue,
            )
        else:
            run["status"] = "BLOCKED"
            append_event(directory, run, "ESCALATION", "controller", {"state": run["state"], **issue})
            save_run(directory, run)
        raise FlowError("Gate receipt changed after gate event", EXIT_INTEGRITY, issue)
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
        if is_v31_run(run) and stage == "EDIT" and artifact(run, "voice-learning"):
            return {
                **routes,
                "chosen": None,
                "fallbacks": [],
                "reason": reason + "; fallback is closed after the operator's voice choice so another model cannot silently replace the selected register",
                "assigned_route": unavailable,
            }
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


def automated_route_health() -> dict[str, Any]:
    """Prove that every model stage has at least one executable automation route."""
    checks: list[dict[str, Any]] = []
    for stage in sorted(MODEL_STATES):
        routes = route_candidates(stage)
        eligible = [
            item for item in routes.get("candidates", [])
            if item.get("eligible") and item.get("kind") != "agent-hosted"
        ]
        checks.append({
            "stage": stage,
            "ok": bool(eligible),
            "eligible_controller_routes": [
                f"{item.get('provider')}:{item.get('model')}" for item in eligible
            ],
            "reason": None if eligible else "no eligible controller-hosted route",
        })
    return {
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
        "configuration_path": str(provider_config_path()),
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


def ensure_voice_anchor(directory: Path, run: dict[str, Any]) -> dict[str, str]:
    """Select and bind an early opening/thesis paragraph without model-authored IDs or hashes."""
    draft_path = artifact_path(directory, run, "draft")
    if not draft_path or not draft_path.is_file():
        raise FlowError("Voice probing requires the recorded rough draft", EXIT_INTEGRITY)
    text = draft_path.read_text(encoding="utf-8")
    candidates: list[tuple[int, str]] = []
    for match in re.finditer(r"(?:\A|\n\s*\n)([^\n].*?)(?=\n\s*\n|\Z)", text, flags=re.DOTALL):
        passage = re.sub(r"\s+", " ", match.group(1)).strip()
        if (
            len(passage) >= 50
            and not passage.startswith(("#", "- ", "* ", "> ", "|"))
            and match.start(1) <= max(1, len(text) // 3)
        ):
            candidates.append((match.start(1), passage))
    if not candidates:
        raise FlowError("The rough draft has no substantial opening or thesis paragraph for the voice gate", EXIT_INTEGRITY)
    offset, passage = candidates[0]
    line = text[:offset].count("\n") + 1
    value = {
        "voice_anchor_schema_version": "1.0.0",
        "run_id": run["run_id"],
        "locator": f"rough draft opening, line {line}",
        "source_passage": passage,
        "source_passage_sha256": sha256_bytes(passage.encode("utf-8")),
        "rough_draft_sha256": sha256_path(draft_path),
    }
    path = directory / "artifacts" / "voice-anchor.json"
    data = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if path.exists() and path.read_bytes() != data:
        raise FlowError("The controller-owned voice anchor disagrees with the current rough draft", EXIT_INTEGRITY)
    if not path.exists():
        immutable_write(path, data)
        record_artifact(
            directory,
            run,
            path,
            "voice-anchor",
            {"actor": "controller", "version": CONTROLLER_VERSION},
            inputs=[artifact(run, "draft")["artifact_id"]] if artifact(run, "draft") else [],
            expected_bytes=data,
        )
    return {"id": "voice-anchor", "path": str(path), "sha256": sha256_path(path)}


def revision_task_input(directory: Path, run: dict[str, Any]) -> dict[str, str] | None:
    if not isinstance(run.get("revision"), dict):
        return None
    item = artifact(run, "revision-request")
    path = artifact_path(directory, run, "revision-request")
    if not item or not path or not path.is_file() or sha256_path(path) != item.get("sha256"):
        raise FlowError("Revision run is missing its hash-bound correction request", EXIT_INTEGRITY)
    return {"id": "revision-request", "path": str(path), "sha256": str(item["sha256"])}


def json_artifact(directory: Path, run: dict[str, Any], artifact_type: str) -> dict[str, Any] | None:
    path = artifact_path(directory, run, artifact_type)
    if not path or path.suffix.lower() != ".json":
        return None
    try:
        return load_json(path)
    except FlowError:
        return None


def stage_output(state: str, run: dict[str, Any] | None = None) -> tuple[str, str]:
    mapping = {
        "RESEARCH_PLAN": ("research-plan", "research-plan.json"),
        "RESEARCH": ("claim-ledger", "claim-ledger.json"),
        "INTENT_REVIEW": ("intent-candidate", "intent-candidate.json"),
        "ARTICLE_RECIPE": ("article-recipe", "article-recipe.json"),
        "BRIEF": ("brief", "brief.json"),
        "VISUAL_PLAN": ("visual-plan", "visual-plan.json"),
        "VOICE_PROBE": (
            ("voice-candidates", "voice-candidates.json")
            if run is not None and is_v31_run(run)
            else ("voice-probe", "voice-probe.json")
        ),
        "DRAFT": ("draft", "draft.md"),
        "CLAIM_VERIFICATION": ("verified-claim-ledger", "verified-claim-ledger.json"),
        "EDIT": ("article", "article.md"),
        "POST_EDIT_CLAIM_VERIFICATION": ("post-edit-claim-ledger", "post-edit-claim-ledger.json"),
        "EDITORIAL_QA": ("editorial-qa", "editorial-qa.json"),
    }
    if state not in mapping:
        raise FlowError(f"State does not dispatch a model task: {state}")
    return mapping[state]


def task_identity_payload(state: str, attempt: int, packet_sha256: str) -> dict[str, Any]:
    return {
        "state": state,
        "attempt": attempt,
        "task_packet_sha256": packet_sha256,
    }


def event_task_identity(event: dict[str, Any]) -> tuple[str, int, str] | None:
    payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
    state = str(payload.get("state") or "")
    packet_hash = str(payload.get("task_packet_sha256") or "")
    try:
        attempt = int(payload.get("attempt", 0))
    except (TypeError, ValueError):
        attempt = 0
    if not state or attempt < 1 or not re.fullmatch(r"[0-9a-f]{64}", packet_hash):
        return None
    return state, attempt, packet_hash


def stage_attempt_evidence(directory: Path, run: dict[str, Any], state: str) -> dict[str, int]:
    """Derive a monotonic attempt ordinal from durable execution evidence.

    Older controllers could reuse one task packet after a same-state repair, so
    ``run.attempts`` and the packet suffix alone are not sufficient evidence of
    how many model executions occurred.  Count durable dispatches, model-call
    receipts, and gate rejections as independent lower bounds and use the
    greatest value.  This both repairs stale counters and keeps future artifact
    paths monotonic.
    """
    recorded_packet_attempts: list[int] = []
    dispatched_attempts: list[int] = []
    receipt_attempts: set[int] = set()
    execution_attempts: set[int] = set()
    rejection_attempts: set[int] = set()
    provider_failure_attempts: set[int] = set()
    legacy_rejections = 0
    durable_execution_numbers: set[int] = set()
    # Executions already closed out by a non-rejecting gate for this stage.
    # The stored baseline only advances for a repair_state, so a stage that
    # repairs elsewhere never had its own window closed and would exhaust by
    # succeeding.  Deriving it here also heals runs recorded before that fix.
    settled_attempt = 0
    try:
        stage_gate = str(state_definition(state, run).get("gate") or "")
    except FlowError:
        stage_gate = ""
    packet_pattern = re.compile(rf"^task-packet:{re.escape(state)}:(\d+)$")
    receipt_pattern = re.compile(rf"^model-call:{re.escape(state)}:(\d+)$")
    for event in _read_jsonl(directory / str(run["event_log"])):
        payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
        if event.get("type") == "TASK_DISPATCHED" and payload.get("state") == state:
            try:
                dispatched_attempts.append(int(payload.get("attempt", 0)))
            except (TypeError, ValueError):
                continue
        elif event.get("type") == "ARTIFACT_RECORDED":
            recorded = payload.get("artifact", {}) if isinstance(payload.get("artifact"), dict) else {}
            artifact_type = str(recorded.get("type", ""))
            packet_match = packet_pattern.fullmatch(artifact_type)
            receipt_match = receipt_pattern.fullmatch(artifact_type)
            if packet_match:
                recorded_packet_attempts.append(int(packet_match.group(1)))
            elif receipt_match:
                attempt = int(receipt_match.group(1))
                receipt_attempts.add(attempt)
                execution_attempts.add(attempt)
        elif (
            event.get("type") == "GATE_RECORDED"
            and stage_gate
            and payload.get("gate_id") == stage_gate
            and payload.get("outcome") in {"PASS", "ESCALATE"}
        ):
            # ESCALATE is what a review stage records when its mechanical
            # checks passed and only the human decision remains.  Key off the
            # receipt's bound attempt rather than the executions seen so far,
            # because execution evidence is also recovered from files after
            # this scan finishes.
            try:
                settled_attempt = max(settled_attempt, int(payload.get("attempt", 0)))
            except (TypeError, ValueError):
                pass
        elif event.get("type") == "MODEL_EXECUTION_STARTED":
            identity = event_task_identity(event)
            if identity and identity[0] == state:
                execution_attempts.add(identity[1])
                try:
                    execution_number = int(payload.get("execution_number", 0))
                except (TypeError, ValueError):
                    execution_number = 0
                if execution_number > 0:
                    durable_execution_numbers.add(execution_number)
        elif event.get("type") == "MODEL_ROUTE_FAILURE":
            identity = event_task_identity(event)
            if identity and identity[0] == state:
                execution_attempts.add(identity[1])
                provider_failure_attempts.add(identity[1])
        elif event.get("type") == "MODEL_OUTPUT_REJECTED" and payload.get("state") == state:
            identity = event_task_identity(event)
            if identity:
                execution_attempts.add(identity[1])
                rejection_attempts.add(identity[1])
            else:
                legacy_rejections += 1
    _, output_filename = stage_output(state, run)
    raw_packet_attempts = {
        int(match.group(1))
        for path in (directory / "tasks").glob(f"{state.lower()}-*.json")
        if (match := re.fullmatch(rf"{re.escape(state.lower())}-(\d+)\.json", path.name))
    }
    raw_output_attempts: set[int] = set()
    for root_name in ("submissions", "artifacts"):
        for path in (directory / root_name).glob(f"*-{output_filename}"):
            match = re.fullmatch(rf"(\d+)-{re.escape(output_filename)}", path.name)
            if match:
                raw_output_attempts.add(int(match.group(1)))
    for path in (directory / "receipts").glob(f"model-call-{state.lower()}-*.json"):
        match = re.fullmatch(rf"model-call-{re.escape(state.lower())}-(\d+)\.json", path.name)
        if match:
            raw_output_attempts.add(int(match.group(1)))
    execution_attempts.update(raw_output_attempts)
    counter = int(run.get("attempts", {}).get(state, 0))
    dispatch_count = len(dispatched_attempts)
    ordinal = max(
        counter,
        max(recorded_packet_attempts, default=0),
        max(raw_packet_attempts, default=0),
        max(dispatched_attempts, default=0),
        max(receipt_attempts, default=0),
        max(raw_output_attempts, default=0),
        len(recorded_packet_attempts),
        len(raw_packet_attempts),
        dispatch_count,
        max(execution_attempts, default=0),
        max(durable_execution_numbers, default=0),
        legacy_rejections,
    )
    settled_execution_count = len([item for item in execution_attempts if item <= settled_attempt])
    baseline = max(int(run.get("attempt_baselines", {}).get(state, 0)), settled_execution_count)
    execution_count = max(
        len(execution_attempts),
        legacy_rejections,
        max(durable_execution_numbers, default=0),
    )
    return {
        "ordinal": ordinal,
        "window_baseline": baseline,
        "window_used": max(0, execution_count - baseline),
        "recorded_packet_count": len(recorded_packet_attempts),
        "raw_packet_count": len(raw_packet_attempts),
        "dispatch_count": dispatch_count,
        "execution_count": execution_count,
        "model_execution_count": len(execution_attempts),
        "provider_failure_count": len(provider_failure_attempts),
        "rejection_count": max(len(rejection_attempts), legacy_rejections),
    }


def reset_attempt_window(directory: Path, run: dict[str, Any], state: str) -> int:
    """Authorize a new bounded repair window without reusing artifact paths."""
    evidence = stage_attempt_evidence(directory, run, state)
    ordinal = evidence["ordinal"]
    run.setdefault("attempt_baselines", {})[state] = evidence["execution_count"]
    run.setdefault("attempts", {})[state] = max(int(run.get("attempts", {}).get(state, 0)), ordinal)
    return ordinal


def latest_repair_source_epoch_sequence(events: list[dict[str, Any]], state: str) -> int:
    return max(
        (
            int(event.get("sequence", 0))
            for event in events
            if event.get("type") == "REPAIR"
            and str((event.get("payload") or {}).get("source_state") or "") == state
        ),
        default=0,
    )


def latest_repair_window_epoch_sequence(events: list[dict[str, Any]], state: str) -> int:
    return max(
        (
            int(event.get("sequence", 0))
            for event in events
            if event.get("type") == "REPAIR"
            and str((event.get("payload") or {}).get("repair_state") or event.get("state") or "") == state
        ),
        default=0,
    )


def artifact_record_sequence(events: list[dict[str, Any]], item: dict[str, Any]) -> int:
    return max(
        (
            int(event.get("sequence", 0))
            for event in events
            if event.get("type") == "ARTIFACT_RECORDED"
            and isinstance((event.get("payload") or {}).get("artifact"), dict)
            and (
                (event.get("payload") or {})["artifact"].get("artifact_id") == item.get("artifact_id")
                or (
                    (event.get("payload") or {})["artifact"].get("type") == item.get("type")
                    and (event.get("payload") or {})["artifact"].get("path") == item.get("path")
                    and (event.get("payload") or {})["artifact"].get("sha256") == item.get("sha256")
                )
            )
        ),
        default=0,
    )


def remember_repair_context(
    directory: Path,
    run: dict[str, Any],
    source_stage: str,
    definition: dict[str, Any],
) -> dict[str, Any] | None:
    """Persist the latest rejected bytes and normalized gate findings for repair."""
    def omit_stale_context() -> None:
        pending = run.get("pending_repair")
        if isinstance(pending, dict) and pending.get("source_stage") == source_stage:
            run.pop("pending_repair", None)

    pending = run.get("pending_repair")
    current_events = _read_jsonl(directory / str(run["event_log"]))
    current_epoch = latest_repair_window_epoch_sequence(current_events, source_stage)
    current_gate_id = str(definition.get("gate") or "")
    current_gate_item = artifact(run, f"gate-receipt:{current_gate_id}") if current_gate_id else None
    has_new_gate_decision = bool(
        current_gate_item
        and artifact_record_sequence(current_events, current_gate_item) > current_epoch
    )
    if (
        isinstance(pending, dict)
        and pending.get("repair_state") == source_stage
        and not has_new_gate_decision
    ):
        # A provider failure while executing a targeted repair has not resolved
        # the rejected gate evidence.  Carry the already validated context
        # forward explicitly into the next operator-authorized window.
        stored = json.loads(json.dumps(pending))
        validated, _ = repair_context_for_packet(directory, run, source_stage)
        if validated is not None:
            # Validation resolves paths for the outgoing packet copy.  Durable
            # run/event state must retain canonical run-relative references.
            run["pending_repair"] = stored
            return stored

    if source_stage not in MODEL_STATES:
        omit_stale_context()
        return None
    artifact_type, _ = stage_output(source_stage, run)
    rejected = artifact(run, artifact_type)
    gate_id = str(definition.get("gate") or "")
    gate_item = artifact(run, f"gate-receipt:{gate_id}") if gate_id else None
    if not rejected or not gate_item:
        omit_stale_context()
        return None
    events = current_events
    if artifact_record_sequence(events, gate_item) <= latest_repair_source_epoch_sequence(events, source_stage):
        # The last gate rejection was already consumed by an explicit repair.
        # Do not resurrect it when a later provider-only window exhausts.
        omit_stale_context()
        return None
    rejected_path = directory / safe_relative(str(rejected["path"]))
    gate_path = directory / safe_relative(str(gate_item["path"]))
    if not rejected_path.is_file() or not gate_path.is_file():
        return None
    if sha256_path(rejected_path) != rejected.get("sha256") or sha256_path(gate_path) != gate_item.get("sha256"):
        raise FlowError("Rejected output or gate receipt changed before repair context was recorded", EXIT_INTEGRITY)
    receipt = load_json(gate_path)
    findings = receipt.get("findings")
    if receipt.get("outcome") == "PASS" or receipt.get("gate_id") != gate_id:
        omit_stale_context()
        return None
    if not isinstance(findings, list) or not findings:
        omit_stale_context()
        return None
    if (
        receipt.get("run_id") != run.get("run_id")
        or receipt.get("repair_state") not in {
            definition.get("repair_state"),
            effective_repair_state(definition, receipt.get("findings") or []),
        }
        or (receipt.get("artifact_hashes") or {}).get(artifact_type) != rejected.get("sha256")
    ):
        raise FlowError("Gate receipt is not cross-bound to the rejected repair artifact", EXIT_INTEGRITY)
    task_binding = receipt.get("task_binding")
    if isinstance(task_binding, dict):
        try:
            bound_attempt = int(task_binding.get("attempt", 0))
        except (TypeError, ValueError):
            bound_attempt = 0
        packet_item = latest_recorded_artifact(
            directory,
            run,
            lambda item: item.get("type") == f"task-packet:{source_stage}:{bound_attempt}",
        )
        if (
            task_binding.get("state") != source_stage
            or bound_attempt < 1
            or not packet_item
            or packet_item.get("sha256") != task_binding.get("task_packet_sha256")
            or (receipt.get("artifact_hashes") or {}).get(f"task-packet:{source_stage}:{bound_attempt}")
            != task_binding.get("task_packet_sha256")
        ):
            raise FlowError("Gate receipt is not cross-bound to its rejected task packet", EXIT_INTEGRITY)
    elif (receipt.get("evaluator") or {}).get("type") not in {"operator", "human"}:
        # Compatibility for archived 1.0 receipts: their artifact hash map is
        # the only task binding available.  New automated receipts are 1.1 and
        # must carry the explicit identity above.
        legacy_packet_bound = receipt.get("gate_receipt_schema_version") == "1.0.0" and any(
            str(item.get("type", "")).startswith(f"task-packet:{source_stage}:")
            and (receipt.get("artifact_hashes") or {}).get(str(item.get("type"))) == item.get("sha256")
            for item in run.get("artifact_index", [])
        )
        if not legacy_packet_bound:
            raise FlowError("Automated repair receipt lacks its task-packet binding", EXIT_INTEGRITY)
    evidence = stage_attempt_evidence(directory, run, source_stage)
    failed_attempt = int(task_binding["attempt"]) if isinstance(task_binding, dict) else evidence["ordinal"]
    if failed_attempt < 1:
        # An operator may request a repair before any task attempt exists.  The
        # receipt still records a normalized finding, but there is no rejected
        # attempt identity to place in task-packet repair_context.
        omit_stale_context()
        return None
    context = {
        "context_type": "targeted_gate_repair",
        "source_stage": source_stage,
        "repair_state": effective_repair_state(definition, findings),
        "failed_attempt": failed_attempt,
        "maximum_attempts": int(definition.get("max_attempts", 1)),
        "rejected_output": {
            "input_id": f"rejected-output:{source_stage}:{failed_attempt}",
            "artifact_type": artifact_type,
            "path": str(rejected["path"]),
            "sha256": str(rejected["sha256"]),
        },
        "gate_receipt": {
            "input_id": f"gate-receipt:{gate_id}:{failed_attempt}",
            "gate_id": gate_id,
            "path": str(gate_item["path"]),
            "sha256": str(gate_item["sha256"]),
        },
        "findings": findings,
    }
    if isinstance(task_binding, dict):
        context["task_binding"] = json.loads(json.dumps(task_binding))
    run["pending_repair"] = context
    return context


def rejected_attempt_requires_repair_context(
    directory: Path,
    run: dict[str, Any],
    source_stage: str,
    gate_id: str,
) -> bool:
    """Return whether repair authorization must bind rejected gate evidence.

    A provider/execution exhaustion has task packets but no rejected output or
    gate decision, so an operator may open a fresh ordinary attempt window.
    Once a non-PASS task-bound gate decision exists, however, losing any part
    of its context must fail closed instead of silently downgrading to an
    ordinary packet.
    """
    events = _read_jsonl(directory / str(run["event_log"]))
    epoch_sequence = latest_repair_source_epoch_sequence(events, source_stage)
    for event in events:
        if int(event.get("sequence", 0)) <= epoch_sequence:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event.get("type") == "MODEL_OUTPUT_REJECTED":
            identity = event_task_identity(event)
            if identity and identity[0] == source_stage:
                return True
        if (
            event.get("type") == "GATE_RECORDED"
            and payload.get("gate_id") == gate_id
            and payload.get("outcome") != "PASS"
            and payload.get("state") == source_stage
        ):
            try:
                if int(payload.get("attempt", 0)) > 0 and re.fullmatch(
                    r"[0-9a-f]{64}", str(payload.get("task_packet_sha256") or "")
                ):
                    return True
            except (TypeError, ValueError):
                return True
    gate_item = artifact(run, f"gate-receipt:{gate_id}") if gate_id else None
    if not gate_item:
        return False
    if artifact_record_sequence(events, gate_item) <= epoch_sequence:
        return False
    try:
        gate_path = directory / safe_relative(str(gate_item.get("path", "")))
    except FlowError:
        return True
    if not gate_path.is_file():
        return True
    try:
        receipt = load_json(gate_path)
    except (OSError, json.JSONDecodeError, FlowError):
        return True
    if receipt.get("outcome") == "PASS":
        return False
    binding = receipt.get("task_binding")
    if isinstance(binding, dict):
        return binding.get("state") == source_stage
    if receipt.get("gate_receipt_schema_version") == "1.0.0":
        packet_hashes = {
            str(item.get("type")): str(item.get("sha256"))
            for item in run.get("artifact_index", [])
            if str(item.get("type", "")).startswith(f"task-packet:{source_stage}:")
        }
        exact = [
            artifact_type
            for artifact_type, packet_hash in packet_hashes.items()
            if (receipt.get("artifact_hashes") or {}).get(artifact_type) == packet_hash
        ]
        # This predicate decides whether context is mandatory, not whether a
        # legacy receipt can be unambiguously replayed.  Any relevant packet
        # hash means a missing/ambiguous rejected output must fail closed.
        return bool(exact)
    return False


def repair_context_for_packet(
    directory: Path,
    run: dict[str, Any],
    state: str,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Resolve and verify pending repair evidence for one new task packet."""
    stored = run.get("pending_repair")
    if not isinstance(stored, dict) or stored.get("repair_state") != state:
        return None, []
    context = json.loads(json.dumps(stored))
    inputs: list[dict[str, str]] = []
    for key in ("rejected_output", "gate_receipt"):
        reference = context.get(key)
        if not isinstance(reference, dict):
            raise FlowError(f"Pending repair context lacks {key}", EXIT_INTEGRITY)
        relative = safe_relative(str(reference.get("path", "")))
        path = (directory / relative).resolve()
        try:
            path.relative_to(directory.resolve())
        except ValueError as exc:
            raise FlowError("Pending repair context escapes its run directory", EXIT_INTEGRITY) from exc
        if not path.is_file() or sha256_path(path) != reference.get("sha256"):
            raise FlowError(f"Pending repair {key} changed before task dispatch", EXIT_INTEGRITY)
        reference["path"] = str(path)
        inputs.append({
            "id": str(reference["input_id"]),
            "path": str(path),
            "sha256": str(reference["sha256"]),
        })
    receipt = load_json(Path(context["gate_receipt"]["path"]))
    task_binding = context.get("task_binding")
    receipt_binding = receipt.get("task_binding")
    if (
        receipt.get("run_id") != run.get("run_id")
        or receipt.get("gate_id") != context["gate_receipt"].get("gate_id")
        or receipt.get("outcome") == "PASS"
        or receipt.get("repair_state") != state
        or receipt.get("findings") != context.get("findings")
        or (receipt.get("artifact_hashes") or {}).get(context["rejected_output"].get("artifact_type"))
        != context["rejected_output"].get("sha256")
    ):
        raise FlowError("Pending repair findings no longer match their hash-bound gate receipt", EXIT_INTEGRITY)
    if task_binding is not None:
        if receipt_binding != task_binding:
            raise FlowError("Pending repair task binding no longer matches its gate receipt", EXIT_INTEGRITY)
        try:
            bound_attempt = int(task_binding.get("attempt", 0))
        except (AttributeError, TypeError, ValueError):
            bound_attempt = 0
        packet_item = latest_recorded_artifact(
            directory,
            run,
            lambda item: item.get("type") == f"task-packet:{context.get('source_stage')}:{bound_attempt}",
        )
        if (
            not packet_item
            or packet_item.get("sha256") != task_binding.get("task_packet_sha256")
            or (receipt.get("artifact_hashes") or {}).get(
                f"task-packet:{context.get('source_stage')}:{bound_attempt}"
            ) != task_binding.get("task_packet_sha256")
        ):
            raise FlowError("Pending repair task packet is not hash-bound to its receipt", EXIT_INTEGRITY)
    elif (receipt.get("evaluator") or {}).get("type") not in {"operator", "human"}:
        legacy_packet_bound = receipt.get("gate_receipt_schema_version") == "1.0.0" and any(
            str(item.get("type", "")).startswith(f"task-packet:{context.get('source_stage')}:")
            and (receipt.get("artifact_hashes") or {}).get(str(item.get("type"))) == item.get("sha256")
            for item in run.get("artifact_index", [])
        )
        if not legacy_packet_bound:
            raise FlowError("Automated pending repair lacks its task-packet binding", EXIT_INTEGRITY)
    return context, inputs


def blocked_only_by_attempt_window(directory: Path, run: dict[str, Any], state: str) -> bool:
    """True when the run's durable block is this stage's exhausted window.

    Integrity failures persist BLOCKED too, and a reopened window must never
    clear one of those, so only the most recent escalation is consulted.
    """
    latest: dict[str, Any] | None = None
    for event in _read_jsonl(directory / str(run["event_log"])):
        if event.get("type") == "ESCALATION":
            latest = event
    if latest is None:
        return False
    payload = latest.get("payload") if isinstance(latest.get("payload"), dict) else {}
    return (
        str(payload.get("reason") or "") == "attempt_window_exhausted"
        and str(payload.get("state") or latest.get("state") or "") == state
    )


def block_exhausted_stage(
    directory: Path,
    run: dict[str, Any],
    state: str,
    definition: dict[str, Any],
) -> dict[str, int]:
    """Persist an auditable, resumable stop at a stage's declared boundary."""
    evidence = stage_attempt_evidence(directory, run, state)
    run.setdefault("attempts", {})[state] = max(
        int(run.get("attempts", {}).get(state, 0)),
        evidence["ordinal"],
    )
    remember_repair_context(directory, run, state, definition)
    events = _read_jsonl(directory / str(run["event_log"]))
    latest_repair_sequence = max(
        (
            int(event.get("sequence", 0))
            for event in events
            if event.get("type") == "REPAIR"
            and str((event.get("payload") or {}).get("repair_state") or event.get("state") or "") == state
        ),
        default=0,
    )

    def same_exhausted_window(event: dict[str, Any]) -> bool:
        if event.get("type") != "ESCALATION":
            return False
        payload = event.get("payload") or {}
        if (
            payload.get("state") != state
            or int(payload.get("attempts", -1)) != evidence["window_used"]
            or int(payload.get("maximum", -1)) != int(definition.get("max_attempts", 1))
            or not (
                payload.get("reason") == "attempt_window_exhausted"
                or "Repair attempts are exhausted" in str(payload.get("question", ""))
            )
        ):
            return False
        # New events carry a monotonic packet ordinal and execution baseline,
        # which uniquely identify the bounded window.  A legacy escalation can
        # suppress a duplicate only when no later REPAIR opened another epoch.
        if payload.get("attempt_ordinal") is not None:
            if int(payload.get("attempt_ordinal", -1)) != evidence["ordinal"]:
                return False
            if payload.get("window_baseline") is not None:
                return int(payload.get("window_baseline", -1)) == evidence["window_baseline"]
            return True
        return int(event.get("sequence", 0)) > latest_repair_sequence

    already_escalated = any(
        same_exhausted_window(event)
        for event in events
    )
    if not already_escalated:
        append_event(directory, run, "ESCALATION", "controller", {
            "state": state,
            "gate_id": definition.get("gate"),
            "reason": "attempt_window_exhausted",
            "attempts": evidence["window_used"],
            "attempt_ordinal": evidence["ordinal"],
            "window_baseline": evidence["window_baseline"],
            "model_execution_count": evidence["model_execution_count"],
            "rejection_count": evidence["rejection_count"],
            "maximum": int(definition.get("max_attempts", 1)),
            "question": "Repair attempts are exhausted. Review the latest rejected output and gate findings before authorizing another bounded repair window.",
        })
    run["status"] = "BLOCKED"
    save_run(directory, run)
    return evidence


def task_packet(
    directory: Path,
    run: dict[str, Any],
    *,
    requested_route: str | None = None,
    allow_canary: bool = False,
) -> tuple[Path, dict[str, Any]]:
    state = run["state"]
    if run.get("repair_recovery_error"):
        run["status"] = "BLOCKED"
        save_run(directory, run)
        raise FlowError(
            "Repair authorization could not be reconstructed from durable evidence",
            EXIT_INTEGRITY,
            run["repair_recovery_error"],
        )
    definition = state_definition(state, run)
    artifact_type, filename = stage_output(state, run)
    attempt_evidence = stage_attempt_evidence(directory, run, state)
    if attempt_evidence["window_used"] >= int(definition.get("max_attempts", 1)):
        block_exhausted_stage(directory, run, state, definition)
        raise FlowError(f"{state} exhausted its bounded attempts and requires an operator decision", EXIT_WAITING)
    attempt = attempt_evidence["ordinal"] + 1
    failures_for_state = run.get("route_failures", {}).get(state, {})
    unrestricted_route = route_candidates(state)
    durable_retry_candidates = [
        json.loads(json.dumps(item))
        for item in run.get("route_retry_candidates", {}).get(state, [])
        if isinstance(item, dict) and item.get("eligible")
    ] if not requested_route else []
    retry_source_packet: dict[str, Any] | None = None
    if durable_retry_candidates:
        retry_source_item = latest_task_packet_item(directory, run, state)
        if retry_source_item:
            _, retry_source_packet, retry_source_issue = validate_recorded_task_packet(
                directory,
                run,
                retry_source_item,
            )
            if retry_source_issue:
                raise FlowError("Durable fallback source packet failed integrity", EXIT_INTEGRITY, retry_source_issue)
    eligible_route_keys = {
        f"{item.get('provider')}:{item.get('model')}"
        for item in [*unrestricted_route.get("candidates", []), *durable_retry_candidates]
        if item.get("eligible")
    }
    failed_route_keys = {
        key for key, count in failures_for_state.items()
        if int(count) > 0 and key in eligible_route_keys
    }
    # Route fallback is independent from the stage execution bound. Prefer a
    # route without a prior failure when one exists, but never exclude every
    # eligible route and thereby prevent the remaining bounded executions.
    # An agent-hosted route does not count as an alternative while automation
    # is driving the run, because execute-stage refuses to perform a packet
    # itself. Counting it meant a stage whose every controller route had one
    # rejected output excluded them all and stopped on a fallback that cannot
    # run, which is exactly the prevention this rule exists to avoid. The
    # independence check below already discounts agent-hosted routes the same
    # way.
    controller_route_keys = {
        f"{item.get('provider')}:{item.get('model')}"
        for item in [*unrestricted_route.get("candidates", []), *durable_retry_candidates]
        if item.get("eligible")
        and (not automation_enabled(run) or item.get("kind") != "agent-hosted")
    }
    excluded = failed_route_keys if controller_route_keys - failed_route_keys else set()
    eligible_retry_candidates = [
        item for item in durable_retry_candidates
        if f"{item.get('provider')}:{item.get('model')}" not in failed_route_keys
    ]
    if eligible_retry_candidates:
        route = {
            **unrestricted_route,
            "candidates": eligible_retry_candidates,
            "chosen": eligible_retry_candidates[0],
            "fallbacks": eligible_retry_candidates[1:],
            "reason": "fresh packet selected the next durable fallback from the consumed attempt",
        }
    else:
        route = route_candidates(state, excluded) if excluded else unrestricted_route
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
        "VISUAL_PLAN": ["AF-VISUAL-001", "AF-EVIDENCE-001"],
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
    if is_v31_run(run) and state == "VOICE_PROBE":
        output_schema_name = "voice-candidates.schema.json"
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
    repair_context, repair_inputs = repair_context_for_packet(directory, run, state)
    if retry_source_packet is not None:
        # A fallback is a fresh execution identity over the exact immutable
        # inputs of the consumed packet.  This also preserves compatibility
        # with old packets whose declared input set predates current workflow
        # requirements.
        inputs = json.loads(json.dumps(retry_source_packet.get("inputs", [])))
        for item in inputs:
            path = Path(str(item.get("path", ""))).expanduser().resolve()
            if not path.is_file() or sha256_path(path) != item.get("sha256"):
                raise FlowError("Durable fallback source input changed", EXIT_INTEGRITY, item)
    else:
        inputs = packet_inputs(directory, run, state)
        inputs.extend(repair_inputs)
    if is_v31_run(run) and state == "VOICE_PROBE" and not any(item.get("id") == "voice-anchor" for item in inputs):
        inputs.append(ensure_voice_anchor(directory, run))
    revision_input = revision_task_input(directory, run)
    if revision_input and not any(item.get("id") == "revision-request" for item in inputs):
        inputs.append(revision_input)
    constraints = [rule_map[item] for item in stage_rules.get(state, [])]
    if state in {"CLAIM_VERIFICATION", "POST_EDIT_CLAIM_VERIFICATION"}:
        constraints.append(
            "Each source_url_or_local_id must contain exactly one direct HTTP(S) URL or one local input locator. "
            "Never concatenate sources in that field; split materially different evidence into separate claims."
        )
    if state == "POST_EDIT_CLAIM_VERIFICATION":
        constraints.append(
            "For an unchanged claim, preserve the exact source_url_or_local_id from the verified-claim-ledger. "
            "Put scope qualifications in allowed_wording or the supporting excerpt, not beside the source locator."
        )
    if is_v31_run(run) and state == "VOICE_PROBE":
        constraints.extend([
            "Rewrite only the controller-owned voice-anchor passage. Do not invent IDs, hashes, comparison order, or an operator choice; the controller owns that envelope.",
            "Return three genuinely different registers: direct field note, conversational reflection, and crisp engineering note. Preserve one shared claim set and keep each candidate to one paragraph.",
        ])
    if state == "VISUAL_PLAN":
        constraints.append("Choose only useful visuals, use an exact existing Markdown heading for every placement, label reconstructions as reconstructions, and do not ask the model to produce SVG or HTML.")
    if revision_input:
        constraints.append("This is a correction run. The separate revision-request is the current operator instruction and overrides conflicting assumptions from the historical seed; preserve the seed as evidence rather than silently rewriting it.")
    if repair_context:
        constraints.append(
            "This is a targeted repair. Resolve every hash-bound gate finding in repair_context while preserving unaffected verified content."
        )
    packet = {
        "task_packet_schema_version": "1.1.0" if repair_context else "1.0.0",
        "workflow_version": run["workflow_version"],
        "run_id": run["run_id"],
        "stage": state,
        "attempt": attempt,
        "objective": definition["objective"],
        "inputs": inputs,
        "reader_job": reader_job,
        "article_recipe": recipe,
        "allowed_tools": allowed_tools,
        "side_effect_policy": definition["side_effect_class"],
        "constraints": constraints,
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
    if repair_context:
        packet["repair_context"] = repair_context
    path = directory / "tasks" / f"{state.lower()}-{attempt:02d}.json"
    errors = validate_instance_schema(packet, "task-packet.schema.json")
    if errors:
        raise FlowError("Controller generated an invalid task packet", EXIT_INTEGRITY, errors)
    packet_bytes = (json.dumps(packet, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    packet_hash = sha256_bytes(packet_bytes)
    try:
        immutable_write(path, packet_bytes)
        if not path.is_file() or sha256_path(path) != packet_hash:
            raise FlowError("Task packet changed after immutable creation", EXIT_INTEGRITY)
        record_artifact(
            directory,
            run,
            path,
            f"task-packet:{state}:{attempt}",
            {"actor": "controller", "version": CONTROLLER_VERSION},
            expected_bytes=packet_bytes,
        )
        if not path.is_file() or sha256_path(path) != packet_hash:
            raise FlowError("Task packet changed after artifact recording", EXIT_INTEGRITY)
    except (FlowError, OSError) as exc:
        try:
            actual_hash = sha256_path(path) if path.is_file() else None
        except OSError:
            actual_hash = None
        issue = {
            "reason": "task_packet_evidence_changed_during_commit",
            "path": str(path),
            "expected_sha256": packet_hash,
            "actual_sha256": actual_hash,
            "error": str(exc),
        }
        block_attempt_reconciliation(directory, run, state, attempt, packet_hash, issue)
        raise FlowError("Task packet evidence changed during commit", EXIT_INTEGRITY, issue) from exc
    # Keep the durable fallback chain through the packet-artifact crash
    # boundary.  TASK_DISPATCHED, not file creation, consumes the candidate.
    run.setdefault("route_retry_candidates", {}).pop(state, None)
    run["attempts"][state] = attempt
    run["status"] = "WAITING_MODEL"
    append_event(directory, run, "TASK_DISPATCHED", "controller", {
        "state": state,
        "attempt": attempt,
        "packet": path.relative_to(directory).as_posix(),
        "task_packet_sha256": packet_hash,
        "route": route,
    })
    try:
        dispatched_hash = sha256_path(path) if path.is_file() else None
    except OSError:
        dispatched_hash = None
    if dispatched_hash != packet_hash:
        issue = {
            "reason": "task_packet_changed_after_dispatch",
            "path": str(path),
            "expected_sha256": packet_hash,
            "actual_sha256": dispatched_hash,
        }
        block_attempt_reconciliation(directory, run, state, attempt, packet_hash, issue)
        raise FlowError("Task packet changed after dispatch", EXIT_INTEGRITY, issue)
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
    if kind == "command" and output_path.is_file():
        # Command adapters may write compact JSON while returning its
        # canonicalized representation.  Normalize those uncommitted bytes
        # atomically here so the execution boundary can require literal byte
        # identity.  A crash before this rewrite leaves uncommitted evidence
        # that recovery preserves and abandons under a fresh ordinal.
        atomic_write(output_path, cleaned.encode("utf-8"))
    elapsed_ms = round((time.monotonic() - started) * 1000)
    return cleaned, {"provider": route["provider"], "model": route["model"], "model_version": route.get("model_version"), "elapsed_ms": elapsed_ms, "transport": transport}


def latest_recorded_artifact(
    directory: Path,
    run: dict[str, Any],
    predicate: Any,
) -> dict[str, Any] | None:
    """Resolve artifact evidence from the event-log WAL before run.json."""
    for event in reversed(_read_jsonl(directory / str(run["event_log"]))):
        if event.get("type") != "ARTIFACT_RECORDED":
            continue
        payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
        item = payload.get("artifact")
        if isinstance(item, dict) and predicate(item):
            return item
    return next((item for item in reversed(run.get("artifact_index", [])) if predicate(item)), None)


def latest_task_packet_item(directory: Path, run: dict[str, Any], state: str) -> dict[str, Any] | None:
    prefix = f"task-packet:{state}:"
    return latest_recorded_artifact(directory, run, lambda item: str(item.get("type", "")).startswith(prefix))


def validate_recorded_task_packet(
    directory: Path,
    run: dict[str, Any],
    item: dict[str, Any],
) -> tuple[Path | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Validate the bytes and identity of a controller-recorded task packet."""
    artifact_type = str(item.get("type", ""))
    match = re.fullmatch(r"task-packet:([^:]+):(\d+)", artifact_type)
    if not match:
        return None, None, {"reason": "invalid_task_packet_artifact_type", "artifact_type": artifact_type}
    expected_state = match.group(1)
    expected_attempt = int(match.group(2))
    try:
        relative = safe_relative(str(item.get("path", "")))
    except FlowError as exc:
        return None, None, {"reason": "unsafe_task_packet_path", "error": str(exc)}
    path = (directory / relative).resolve()
    try:
        path.relative_to(directory.resolve())
    except ValueError:
        return None, None, {"reason": "task_packet_path_escaped_run", "path": str(path)}
    if not path.is_file():
        return path, None, {"reason": "task_packet_missing", "path": str(path), "expected_sha256": item.get("sha256")}
    actual_hash = sha256_path(path)
    if actual_hash != item.get("sha256"):
        return path, None, {
            "reason": "task_packet_hash_mismatch",
            "path": str(path),
            "expected_sha256": item.get("sha256"),
            "actual_sha256": actual_hash,
        }
    try:
        packet = load_json(path)
    except FlowError as exc:
        return path, None, {"reason": "task_packet_unreadable", "path": str(path), "error": str(exc)}
    packet_errors = validate_instance_schema(packet, "task-packet.schema.json")
    if packet_errors:
        return path, None, {"reason": "task_packet_schema_mismatch", "path": str(path), "errors": packet_errors}
    identity = {
        "run_id": packet.get("run_id"),
        "state": packet.get("stage"),
        "attempt": packet.get("attempt"),
    }
    if identity != {"run_id": run.get("run_id"), "state": expected_state, "attempt": expected_attempt}:
        return path, None, {
            "reason": "task_packet_identity_mismatch",
            "path": str(path),
            "expected": {"run_id": run.get("run_id"), "state": expected_state, "attempt": expected_attempt},
            "actual": identity,
        }
    return path, packet, None


def task_packet_dispatch_sequence(
    directory: Path,
    run: dict[str, Any],
    state: str,
    attempt: int,
    packet_path: Path,
) -> int | None:
    relative = packet_path.relative_to(directory).as_posix()
    packet_hash = sha256_path(packet_path)
    for event in reversed(_read_jsonl(directory / str(run["event_log"]))):
        payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
        if (
            event.get("type") == "TASK_DISPATCHED"
            and payload.get("state") == state
            and int(payload.get("attempt", 0)) == attempt
            and payload.get("packet") == relative
            and payload.get("task_packet_sha256", packet_hash) == packet_hash
        ):
            return int(event.get("sequence", 0))
    return None


def task_packet_gate_consumed(
    directory: Path,
    run: dict[str, Any],
    state: str,
    attempt: int,
    packet_sha256: str,
    dispatch_sequence: int,
) -> bool:
    gate_id = state_definition(state, run).get("gate")
    for event in _read_jsonl(directory / str(run["event_log"])):
        if int(event.get("sequence", 0)) <= dispatch_sequence:
            continue
        payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
        try:
            payload_attempt = int(payload.get("attempt", 0))
        except (TypeError, ValueError):
            payload_attempt = 0
        binding_matches = (
            payload.get("state") == state
            and payload_attempt == attempt
            and payload.get("task_packet_sha256") == packet_sha256
        )
        if event.get("type") == "MODEL_OUTPUT_REJECTED" and binding_matches:
            return True
        if event.get("type") == "GATE_RECORDED" and payload.get("gate_id") == gate_id and binding_matches:
            return True
    return False


def task_packet_lifecycle_events(
    directory: Path,
    run: dict[str, Any],
    state: str,
    attempt: int,
    packet_sha256: str,
    dispatch_sequence: int,
) -> list[dict[str, Any]]:
    identity = (state, attempt, packet_sha256)
    return [
        event
        for event in _read_jsonl(directory / str(run["event_log"]))
        if int(event.get("sequence", 0)) > dispatch_sequence
        and event_task_identity(event) == identity
    ]


def validated_model_call_item(
    directory: Path,
    run: dict[str, Any],
    state: str,
    attempt: int,
    packet_path: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    item = latest_recorded_artifact(
        directory,
        run,
        lambda candidate: candidate.get("type") == f"model-call:{state}:{attempt}",
    )
    if not item:
        return None, None
    path = (directory / safe_relative(str(item.get("path", "")))).resolve()
    try:
        path.relative_to(directory.resolve())
    except ValueError:
        return None, {"reason": "model_call_receipt_escaped_run", "path": str(path)}
    if not path.is_file() or sha256_path(path) != item.get("sha256"):
        return None, {"reason": "model_call_receipt_changed", "path": str(path), "expected_sha256": item.get("sha256")}
    receipt = load_json(path)
    if (
        receipt.get("run_id") != run.get("run_id")
        or receipt.get("stage") != state
        or int(receipt.get("attempt", 0)) != attempt
        or receipt.get("packet_sha256") != sha256_path(packet_path)
    ):
        return None, {"reason": "model_call_receipt_identity_mismatch", "path": str(path)}
    return {"item": item, "path": str(path), "receipt": receipt}, None


def validated_gate_receipt_for_attempt(
    directory: Path,
    run: dict[str, Any],
    state: str,
    attempt: int,
    packet_sha256: str,
    dispatch_sequence: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Find a durable gate receipt committed for one exact task identity."""
    gate_id = str(state_definition(state, run).get("gate") or "")
    for event in reversed(_read_jsonl(directory / str(run["event_log"]))):
        if int(event.get("sequence", 0)) <= dispatch_sequence:
            continue
        if event.get("type") != "ARTIFACT_RECORDED":
            continue
        payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
        item = payload.get("artifact")
        if not isinstance(item, dict) or item.get("type") != f"gate-receipt:{gate_id}":
            continue
        path = (directory / safe_relative(str(item.get("path", "")))).resolve()
        try:
            path.relative_to(directory.resolve())
        except ValueError:
            return None, {"reason": "gate_receipt_escaped_run", "path": str(path)}
        if not path.is_file() or sha256_path(path) != item.get("sha256"):
            return None, {"reason": "gate_receipt_changed", "path": str(path), "expected_sha256": item.get("sha256")}
        receipt = load_json(path)
        binding = receipt.get("task_binding")
        if not isinstance(binding, dict):
            packet_type = f"task-packet:{state}:{attempt}"
            packet_hashes = {
                str(value)
                for key, value in (receipt.get("artifact_hashes") or {}).items()
                if key == packet_type
            }
            recorded_hashes = {
                str(candidate.get("sha256"))
                for prior_event in _read_jsonl(directory / str(run["event_log"]))
                if prior_event.get("type") == "ARTIFACT_RECORDED"
                for candidate in [(prior_event.get("payload") or {}).get("artifact", {})]
                if candidate.get("type") == packet_type
            }
            if (
                receipt.get("gate_receipt_schema_version") == "1.0.0"
                and receipt.get("run_id") == run.get("run_id")
                and receipt.get("gate_id") == gate_id
                and packet_hashes == {packet_sha256}
                and recorded_hashes == {packet_sha256}
            ):
                return {"item": item, "path": str(path), "receipt": receipt, "legacy_binding": True}, None
            return None, {
                "reason": "legacy_gate_receipt_is_not_uniquely_bound",
                "path": str(path),
                "state": state,
                "attempt": attempt,
            }
        try:
            bound_attempt = int(binding.get("attempt", 0))
        except (TypeError, ValueError):
            bound_attempt = 0
        if (
            receipt.get("run_id") == run.get("run_id")
            and receipt.get("gate_id") == gate_id
            and binding.get("state") == state
            and bound_attempt == attempt
            and binding.get("task_packet_sha256") == packet_sha256
        ):
            return {"item": item, "path": str(path), "receipt": receipt}, None
    return None, None


def resumable_model_output(
    directory: Path,
    run: dict[str, Any],
    packet_path: Path,
    packet: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Resolve a durable model call to the exact output bound by its packet."""
    state = str(packet.get("stage"))
    attempt = int(packet.get("attempt", 0))
    model_call, issue = validated_model_call_item(directory, run, state, attempt, packet_path)
    if issue or not model_call:
        return None, issue
    try:
        output_path = Path(str(packet["expected_outputs"][0]["path"])).expanduser().resolve()
        output_path.relative_to((directory / "submissions").resolve())
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        return None, {"reason": "model_output_path_is_not_the_bound_run_submission", "error": str(exc)}
    receipt = model_call["receipt"]
    if not output_path.is_file():
        return None, {"reason": "recorded_model_output_missing", "path": str(output_path)}
    actual_hash = sha256_path(output_path)
    if receipt.get("output_sha256") != actual_hash:
        return None, {
            "reason": "recorded_model_output_changed",
            "path": str(output_path),
            "expected_sha256": receipt.get("output_sha256"),
            "actual_sha256": actual_hash,
        }
    return {"model_call": model_call, "output_path": output_path}, None


def abandon_cached_packet(
    directory: Path,
    run: dict[str, Any],
    state: str,
    item: dict[str, Any],
    details: dict[str, Any],
) -> None:
    match = re.fullmatch(rf"task-packet:{re.escape(state)}:(\d+)", str(item.get("type", "")))
    if not match or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
        raise FlowError("Cannot abandon a task packet without its exact identity", EXIT_INTEGRITY, item)
    identity = task_identity_payload(state, int(match.group(1)), str(item["sha256"]))
    duplicate = any(
        event.get("type") == "RETRY"
        and event_task_identity(event) == (state, identity["attempt"], identity["task_packet_sha256"])
        for event in _read_jsonl(directory / str(run["event_log"]))
    )
    if not duplicate:
        append_event(directory, run, "RETRY", "controller", {
            **identity,
            "task_packet_artifact_id": item.get("artifact_id"),
            **details,
        })
    run["status"] = "ACTIVE"
    save_run(directory, run)


def block_attempt_reconciliation(
    directory: Path,
    run: dict[str, Any],
    state: str,
    attempt: int,
    packet_sha256: str,
    details: dict[str, Any],
) -> None:
    """Fail closed once for a committed decision that cannot be replayed."""
    identity = task_identity_payload(state, attempt, packet_sha256)
    already_escalated = any(
        event.get("type") == "ESCALATION"
        and event_task_identity(event) == (state, attempt, packet_sha256)
        and (event.get("payload") or {}).get("reason") == details.get("reason")
        for event in _read_jsonl(directory / str(run["event_log"]))
    )
    if not already_escalated:
        append_event(directory, run, "ESCALATION", "controller", {
            **identity,
            "gate_id": state_definition(state, run).get("gate"),
            **details,
        })
    run["status"] = "BLOCKED"
    save_run(directory, run)


def current_packet(
    directory: Path,
    run: dict[str, Any],
    *,
    requested_route: str | None = None,
    allow_canary: bool = False,
) -> tuple[Path, dict[str, Any]]:
    if run.get("status") == "BLOCKED":
        # load_run deliberately recovers in memory only.  current_packet is a
        # mutation boundary, so make a recovered BLOCKED decision durable
        # under the run lock before returning it to the caller.
        cached = load_json(directory / "run.json")
        if cached.get("status") != "BLOCKED":
            persist_recovered_cache(directory, run)
        definition = state_definition(run["state"], run)
        raise FlowError(
            f"{run['state']} is blocked and requires an explicit repair",
            EXIT_WAITING,
            {
                "action": "repair_required",
                "gate": definition.get("gate"),
                "command": ["article-flow", "repair", run["run_id"], definition.get("gate")],
            },
        )
    # Only a genuinely pending model task may reuse its exact packet.  A gate
    # repair transitions the run back to ACTIVE, which must mint the next
    # monotonic attempt and preserve the rejected packet and output unchanged.
    if run.get("status") == "WAITING_MODEL":
        item = latest_task_packet_item(directory, run, run["state"])
        if item:
            path, packet, issue = validate_recorded_task_packet(directory, run, item)
            if issue:
                run["status"] = "BLOCKED"
                append_event(directory, run, "ESCALATION", "controller", {
                    "state": run["state"],
                    "gate_id": state_definition(run["state"], run).get("gate"),
                    **issue,
                })
                save_run(directory, run)
                raise FlowError("Recorded task packet failed integrity validation", EXIT_INTEGRITY, issue)
            assert path is not None and packet is not None
            attempt = int(packet["attempt"])
            packet_hash = sha256_path(path)
            dispatch_sequence = task_packet_dispatch_sequence(directory, run, run["state"], attempt, path)
            if dispatch_sequence is None:
                issue = {"reason": "task_packet_was_not_durably_dispatched", "attempt": attempt}
                run["status"] = "BLOCKED"
                append_event(directory, run, "ESCALATION", "controller", {
                    "state": run["state"],
                    "gate_id": state_definition(run["state"], run).get("gate"),
                    **issue,
                })
                save_run(directory, run)
                raise FlowError("Recorded task packet lacks durable dispatch evidence", EXIT_INTEGRITY, issue)
            if task_packet_gate_consumed(
                directory,
                run,
                run["state"],
                attempt,
                packet_hash,
                dispatch_sequence,
            ):
                issue = {
                    "reason": "task_packet_gate_already_recorded",
                    "dispatch_sequence": dispatch_sequence,
                }
                # The recorded gate is the decision commit for this attempt.  A
                # stale cache must never turn it into another execution.  Full
                # outcome reconciliation is operator-visible; block safely if
                # no later transition was durably completed.
                block_attempt_reconciliation(directory, run, run["state"], attempt, packet_hash, issue)
                raise FlowError("Task packet gate outcome is already recorded and requires reconciliation", EXIT_WAITING, issue)
            committed_gate, gate_issue = validated_gate_receipt_for_attempt(
                directory,
                run,
                run["state"],
                attempt,
                packet_hash,
                dispatch_sequence,
            )
            if gate_issue or committed_gate:
                issue = gate_issue or {
                    "reason": "task_packet_gate_receipt_requires_reconciliation",
                    "gate_receipt": committed_gate["path"],
                }
                block_attempt_reconciliation(directory, run, run["state"], attempt, packet_hash, issue)
                raise FlowError("Task packet has a committed gate receipt requiring reconciliation", EXIT_WAITING, issue)
            model_call, receipt_issue = validated_model_call_item(directory, run, run["state"], attempt, path)
            if receipt_issue:
                run["status"] = "BLOCKED"
                append_event(directory, run, "ESCALATION", "controller", {
                    "state": run["state"],
                    "gate_id": state_definition(run["state"], run).get("gate"),
                    **receipt_issue,
                })
                save_run(directory, run)
                raise FlowError("Recorded model-call receipt failed integrity validation", EXIT_INTEGRITY, receipt_issue)
            if model_call:
                chosen = packet.get("selected_route", {}).get("chosen") or {}
                chosen_key = f"{chosen.get('provider')}:{chosen.get('model')}"
                if requested_route and (
                    chosen_key != requested_route
                    or bool(chosen.get("canary_execution")) != bool(allow_canary)
                ):
                    raise FlowError(
                        "A durable model call already consumed this packet; its route cannot be changed",
                        EXIT_INTEGRITY,
                        {"recorded_route": chosen_key, "requested_route": requested_route},
                    )
                return path, packet
            lifecycle = task_packet_lifecycle_events(
                directory,
                run,
                run["state"],
                attempt,
                packet_hash,
                dispatch_sequence,
            )
            lifecycle_types = {str(event.get("type")) for event in lifecycle}
            if lifecycle_types & {"MODEL_EXECUTION_STARTED", "MODEL_ROUTE_FAILURE", "RETRY"}:
                if "RETRY" not in lifecycle_types:
                    abandon_cached_packet(directory, run, run["state"], item, {
                        "reason": "recovered_consumed_execution",
                        "prior_event_types": sorted(lifecycle_types),
                    })
                else:
                    run["status"] = "ACTIVE"
                    save_run(directory, run)
                return task_packet(directory, run, requested_route=requested_route, allow_canary=allow_canary)
            if not requested_route:
                chosen = packet.get("selected_route", {}).get("chosen") or {}
                if automation_enabled(run) and chosen.get("kind") == "agent-hosted":
                    refreshed_routes = route_candidates(run["state"])
                    refreshed_routes = prefer_controller_route(run, run["state"], refreshed_routes)
                    refreshed_routes = pin_writing_route(run, run["state"], refreshed_routes)
                    replacement = refreshed_routes.get("chosen") or {}
                    if replacement and replacement.get("kind") != "agent-hosted":
                        recorded_key = f"{chosen.get('provider')}:{chosen.get('model')}"
                        replacement_key = f"{replacement.get('provider')}:{replacement.get('model')}"
                        abandon_cached_packet(directory, run, run["state"], item, {
                            "reason": "controller_route_became_available",
                            "recorded_route": recorded_key,
                            "replacement_route": replacement_key,
                        })
                        return task_packet(directory, run)
                return path, packet
            chosen = packet.get("selected_route", {}).get("chosen") or {}
            chosen_key = f"{chosen.get('provider')}:{chosen.get('model')}"
            if chosen_key == requested_route and bool(chosen.get("canary_execution")) == bool(allow_canary):
                return path, packet
            abandon_cached_packet(directory, run, run["state"], item, {
                "reason": "route_refresh",
                "recorded_route": chosen_key,
                "requested_route": requested_route,
            })
            return task_packet(directory, run, requested_route=requested_route, allow_canary=allow_canary)
    return task_packet(directory, run, requested_route=requested_route, allow_canary=allow_canary)


def latest_model_call_route(directory: Path, run: dict[str, Any], stage: str, attempt: int) -> dict[str, Any] | None:
    expected_type = f"model-call:{stage}:{attempt}"
    item = latest_recorded_artifact(directory, run, lambda entry: entry.get("type") == expected_type)
    if not item:
        return None
    path = (directory / safe_relative(str(item.get("path", "")))).resolve()
    try:
        path.relative_to(directory.resolve())
    except ValueError as exc:
        raise FlowError("Recorded model-call route receipt escaped its run", EXIT_INTEGRITY, item) from exc
    if not path.is_file() or sha256_path(path) != item.get("sha256"):
        raise FlowError("Recorded model-call route receipt changed", EXIT_INTEGRITY, item)
    value = load_json(path)
    if value.get("run_id") != run.get("run_id") or value.get("stage") != stage or int(value.get("attempt", 0)) != attempt:
        raise FlowError("Recorded model-call route receipt has the wrong identity", EXIT_INTEGRITY, item)
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


def editorial_repair_must_preserve_operator_article(
    run: dict[str, Any],
    stage: str,
    repair_destination: str | None,
) -> bool:
    article_item = artifact(run, "article") or {}
    producer = article_item.get("producer") if isinstance(article_item.get("producer"), dict) else {}
    return (
        stage == "EDITORIAL_QA"
        and repair_destination == "EDIT"
        and producer.get("actor") == "operator"
    )


def command_execute_stage(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    if args.canary and not args.route:
        raise FlowError("--canary requires an exact --route PROVIDER:MODEL", EXIT_USAGE)
    resumed = False
    output_path: Path | None = None
    receipt: dict[str, Any] | None = None
    submission_state: str | None = None

    # The lock covers packet resolution, the durable execution claim, provider
    # invocation, and receipt commit.  The submit subprocess runs after release
    # because it takes the same lock and independently revalidates the identity.
    with run_lock(directory, run):
        if run["state"] not in MODEL_STATES:
            raise FlowError(f"State {run['state']} is deterministic or complete and cannot invoke a model")
        while True:
            state = str(run["state"])
            definition = state_definition(state, run)
            evidence = stage_attempt_evidence(directory, run, state)
            if run.get("status") != "WAITING_MODEL" and evidence["window_used"] >= int(definition.get("max_attempts", 1)):
                block_exhausted_stage(directory, run, state, definition)
                raise FlowError(
                    f"{state} exhausted its bounded attempts and requires repair",
                    EXIT_WAITING,
                    next_state_payload(directory, run),
                )

            packet_path, packet = current_packet(
                directory,
                run,
                requested_route=args.route,
                allow_canary=bool(args.canary),
            )
            attempt = int(packet["attempt"])
            packet_bytes = (json.dumps(packet, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            packet_hash = sha256_bytes(packet_bytes)

            def require_exact_packet(reason: str) -> None:
                try:
                    actual_bytes = packet_path.read_bytes()
                    actual_hash = sha256_bytes(actual_bytes)
                except OSError:
                    actual_bytes = None
                    actual_hash = None
                if actual_bytes != packet_bytes:
                    issue = {
                        "reason": reason,
                        "path": str(packet_path),
                        "expected_sha256": packet_hash,
                        "actual_sha256": actual_hash,
                    }
                    block_attempt_reconciliation(directory, run, state, attempt, packet_hash, issue)
                    raise FlowError("Task packet changed across model execution", EXIT_INTEGRITY, issue)

            require_exact_packet("task_packet_changed_before_execution")
            resumable, resume_issue = resumable_model_output(directory, run, packet_path, packet)
            require_exact_packet("task_packet_changed_during_receipt_resume")
            if resume_issue:
                block_attempt_reconciliation(directory, run, state, attempt, packet_hash, resume_issue)
                raise FlowError("Recorded model-call evidence failed integrity validation", EXIT_INTEGRITY, resume_issue)
            if resumable:
                output_path = resumable["output_path"]
                receipt = resumable["model_call"]["receipt"]
                submission_state = state
                resumed = True
                break

            expected_output = Path(str(packet["expected_outputs"][0]["path"])).expanduser().resolve()
            raw_receipt = directory / "receipts" / f"model-call-{state.lower()}-{attempt:02d}.json"
            if expected_output.exists() or raw_receipt.exists():
                item = latest_task_packet_item(directory, run, state)
                if not item:
                    raise FlowError("Attempt bytes exist without a recorded task packet", EXIT_INTEGRITY)
                abandon_cached_packet(directory, run, state, item, {
                    "reason": "uncommitted_attempt_bytes_preserved",
                    "output_present": expected_output.exists(),
                    "receipt_present": raw_receipt.exists(),
                })
                continue

            route_set = packet["selected_route"]
            route = route_set.get("chosen") if isinstance(route_set.get("chosen"), dict) else None
            if args.route:
                chosen_key = f"{(route or {}).get('provider')}:{(route or {}).get('model')}"
                if chosen_key != args.route:
                    raise FlowError("Hash-bound task packet does not select the requested route", EXIT_INTEGRITY, route_set)
            if not route or route.get("kind") == "agent-hosted":
                raise FlowError(
                    "No controller-hosted route is eligible; the active host must perform the task packet",
                    EXIT_WAITING,
                    {
                        "task_packet": str(packet_path),
                        "submission_command": [
                            "article-flow", "submit", run["run_id"], "--stage", state,
                            "--file", packet["expected_outputs"][0]["path"],
                        ],
                    },
                )

            # Recheck immediately before each route.  A provider invocation is
            # not allowed to begin unless this claim fits in the current bounded
            # window, and the fsynced claim itself consumes that slot.
            evidence = stage_attempt_evidence(directory, run, state)
            maximum = int(definition.get("max_attempts", 1))
            if evidence["window_used"] >= maximum:
                block_exhausted_stage(directory, run, state, definition)
                raise FlowError(f"{state} exhausted its bounded attempts and requires repair", EXIT_WAITING)
            execution_number = int(evidence["execution_count"]) + 1
            identity = task_identity_payload(state, attempt, packet_hash)
            append_event(directory, run, "MODEL_EXECUTION_STARTED", "controller", {
                **identity,
                "execution_number": execution_number,
                "route": route,
            })
            save_run(directory, run)

            try:
                output, call = invoke_route(route, packet_path, packet)
            except FlowError as exc:
                require_exact_packet("task_packet_changed_during_failed_execution")
                key = f"{route.get('provider')}:{route.get('model')}"
                stage_failures = run.setdefault("route_failures", {}).setdefault(state, {})
                failure_count = int(stage_failures.get(key, 0)) + 1
                stage_failures[key] = failure_count
                remaining_routes = [
                    json.loads(json.dumps(candidate))
                    for candidate in route_set.get("fallbacks", [])
                    if isinstance(candidate, dict)
                    and candidate.get("eligible")
                    and (candidate.get("provider"), candidate.get("model"))
                    != (route.get("provider"), route.get("model"))
                ]
                if remaining_routes:
                    run.setdefault("route_retry_candidates", {})[state] = remaining_routes
                else:
                    run.setdefault("route_retry_candidates", {}).pop(state, None)
                append_event(directory, run, "MODEL_ROUTE_FAILURE", "controller", {
                    **identity,
                    "execution_number": execution_number,
                    "route": route,
                    "failure_count": failure_count,
                    "remaining_routes": remaining_routes,
                    "error": str(exc),
                    "details": exc.details,
                })
                item = latest_task_packet_item(directory, run, state)
                if not item:
                    raise FlowError("Provider failure lost its task packet identity", EXIT_INTEGRITY) from exc
                abandon_cached_packet(directory, run, state, item, {
                    "reason": "provider_failure",
                    "route": {"provider": route.get("provider"), "model": route.get("model")},
                })
                evidence = stage_attempt_evidence(directory, run, state)
                if evidence["window_used"] >= maximum:
                    block_exhausted_stage(directory, run, state, definition)
                    raise FlowError("Every bounded provider execution failed", EXIT_WAITING, {
                        "state": state,
                        "attempts": evidence["window_used"],
                        "maximum": maximum,
                    }) from exc
                continue

            require_exact_packet("task_packet_changed_during_execution")
            output_path = Path(str(packet["expected_outputs"][0]["path"])).expanduser().resolve()
            output_bytes = output.encode("utf-8")
            output_hash = sha256_bytes(output_bytes)
            try:
                immutable_write(output_path, output_bytes)
            except (FlowError, OSError) as exc:
                try:
                    existing_hash = sha256_path(output_path) if output_path.is_file() else None
                except OSError:
                    existing_hash = None
                issue = {
                    "reason": "provider_output_bytes_disagree",
                    "path": str(output_path),
                    "existing_sha256": existing_hash,
                    "returned_sha256": output_hash,
                    "error": str(exc),
                }
                block_attempt_reconciliation(directory, run, state, attempt, packet_hash, issue)
                raise FlowError(
                    "Provider output bytes disagree with the immutable attempt output",
                    EXIT_INTEGRITY,
                    issue,
                ) from exc
            try:
                committed_output_hash = sha256_path(output_path) if output_path.is_file() else None
            except OSError:
                committed_output_hash = None
            if committed_output_hash != output_hash:
                issue = {
                    "reason": "provider_output_changed_before_receipt",
                    "path": str(output_path),
                    "expected_sha256": output_hash,
                    "actual_sha256": committed_output_hash,
                }
                block_attempt_reconciliation(directory, run, state, attempt, packet_hash, issue)
                raise FlowError("Provider output changed before receipt commit", EXIT_INTEGRITY, issue)
            receipt = {
                "model_call_receipt_schema_version": "1.0.0",
                "run_id": run["run_id"],
                "stage": state,
                "attempt": attempt,
                "packet_sha256": packet_hash,
                "output_sha256": output_hash,
                "selection_reason": route_set.get("reason"),
                "route": call,
                "canary_execution": bool(route.get("canary_execution")),
                "created_at": utc_now(),
            }
            receipt_path = directory / "receipts" / f"model-call-{state.lower()}-{attempt:02d}.json"
            receipt_bytes = (json.dumps(receipt, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            receipt_hash = sha256_bytes(receipt_bytes)
            try:
                immutable_write(receipt_path, receipt_bytes)
                if not receipt_path.is_file() or sha256_path(receipt_path) != receipt_hash:
                    raise FlowError("Model-call receipt changed after immutable creation", EXIT_INTEGRITY)
                record_artifact(
                    directory,
                    run,
                    receipt_path,
                    f"model-call:{state}:{attempt}",
                    {"actor": "controller", "version": CONTROLLER_VERSION},
                    expected_bytes=receipt_bytes,
                )
                final_receipt_hash = sha256_path(receipt_path) if receipt_path.is_file() else None
                final_output_hash = sha256_path(output_path) if output_path.is_file() else None
            except (FlowError, OSError) as exc:
                try:
                    actual_receipt_hash = sha256_path(receipt_path) if receipt_path.is_file() else None
                except OSError:
                    actual_receipt_hash = None
                try:
                    actual_output_hash = sha256_path(output_path) if output_path.is_file() else None
                except OSError:
                    actual_output_hash = None
                issue = {
                    "reason": "model_call_evidence_changed_during_commit",
                    "receipt_path": str(receipt_path),
                    "expected_receipt_sha256": receipt_hash,
                    "actual_receipt_sha256": actual_receipt_hash,
                    "output_path": str(output_path),
                    "expected_output_sha256": output_hash,
                    "actual_output_sha256": actual_output_hash,
                    "error": str(exc),
                }
                block_attempt_reconciliation(directory, run, state, attempt, packet_hash, issue)
                raise FlowError("Model-call evidence changed during commit", EXIT_INTEGRITY, issue) from exc
            if final_receipt_hash != receipt_hash or final_output_hash != output_hash:
                issue = {
                    "reason": "model_call_evidence_changed_after_record",
                    "receipt_path": str(receipt_path),
                    "expected_receipt_sha256": receipt_hash,
                    "actual_receipt_sha256": final_receipt_hash,
                    "output_path": str(output_path),
                    "expected_output_sha256": output_hash,
                    "actual_output_sha256": final_output_hash,
                }
                block_attempt_reconciliation(directory, run, state, attempt, packet_hash, issue)
                raise FlowError("Model-call evidence changed after record", EXIT_INTEGRITY, issue)
            require_exact_packet("task_packet_changed_before_receipt_release")
            submission_state = state
            break

    assert output_path is not None and receipt is not None and submission_state is not None
    command = [
        sys.executable,
        str(SCRIPT_PATH),
        "submit",
        args.run_id,
        "--stage",
        submission_state,
        "--file",
        str(output_path),
        "--json",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    try:
        submission = json.loads(result.stdout)
    except json.JSONDecodeError:
        submission = {"raw_stdout": result.stdout, "stderr": result.stderr}
    emit({
        "ok": result.returncode in {EXIT_OK, EXIT_WAITING},
        "resumed_recorded_model_call": resumed,
        "model_call": receipt,
        "submission": submission,
    }, args.json)
    return result.returncode


def find_locked_tokens(text: str) -> dict[str, list[str]]:
    patterns = {
        "urls": r"https?://[^\s)\]>'\"]+",
        "numbers": r"(?<![A-Za-z])\d+(?:[.,]\d+)*(?:%|\b)",
        "dates": r"\b(?:19|20)\d{2}(?:-\d{2}-\d{2})?\b",
        "inline_code": r"`[^`\n]+`",
        # Image placement and targets are owned by the visual manifest. Keep
        # evidence links locked, but do not make a model-guessed image path an
        # immutable factual value.
        "markdown_links": r"(?<!!)\[[^\]]+\]\([^)]+\)",
        "code_blocks": r"```[^\n]*\n.*?```",
        "direct_quotes": r"(?:^|\n)>[^\n]+",
    }
    return {name: sorted(re.findall(pattern, text, flags=re.MULTILINE | re.DOTALL)) for name, pattern in patterns.items()}


def permitted_citation_additions(locked_record: dict[str, Any]) -> set[str]:
    """Source URLs a naturalized article may introduce that its draft lacked.

    ``claim_citation_mapping`` requires every used medium or high risk claim's
    source URL to appear in the article, and claim verification can accept a
    claim the draft never cited.  ``urls`` is also a locked token category, so
    requiring an unchanged token set at the same time makes those two gates
    unsatisfiable together and consumes the entire naturalization window.  The
    lock exists to stop naturalization altering verified values, not to forbid
    satisfying another gate, so exactly these additions are permitted and every
    other change still fails closed.
    """
    recorded = locked_record.get("citation_additions")
    if isinstance(recorded, list):
        return {str(value) for value in recorded}
    # Runs locked before the field existed: derive the same set from the
    # snapshot, which is the required source URLs the draft never carried.
    locked_urls = set(locked_record.get("tokens", {}).get("urls", []))
    return {
        str(claim["source_url_or_local_id"])
        for claim in locked_record.get("claims", [])
        if isinstance(claim, dict)
        and claim.get("risk") in {"medium", "high"}
        and isinstance(claim.get("source_url_or_local_id"), str)
        and str(claim["source_url_or_local_id"]).startswith("http")
    } - locked_urls


def unverified_locked_urls(locked_record: dict[str, Any]) -> set[str]:
    """Locked URLs that no verified claim cites.

    The lock exists to stop naturalization altering verified values. A URL the
    draft happened to write that the evidence does not record is not one of
    them: locking it protects a possible mis-citation, and when the ledger
    records a different address for the same source the citation gate and the
    lock cannot both be satisfied. A live run reached editorial QA carrying two
    URLs for one paper because the draft cited the legacy proceedings host and
    verification recorded the current one, and no rewrite could satisfy both.
    """
    cited = {
        str(claim.get("source_url_or_local_id"))
        for claim in locked_record.get("claims", [])
        if isinstance(claim, dict)
        and isinstance(claim.get("source_url_or_local_id"), str)
        and str(claim["source_url_or_local_id"]).startswith("http")
    }
    return {
        str(url)
        for url in locked_record.get("tokens", {}).get("urls", [])
        if str(url) not in cited
    }


def strip_citation_additions(text: str, additions: set[str]) -> str:
    """Remove permitted new citations so locked tokens compare like for like.

    A newly cited URL also introduces the numbers, dates, and markdown link it
    contains, so removing the citation itself is what keeps every other locked
    category strict.  The link text is deliberately preserved.
    """
    # A locked URL may extend a permitted one, so only whole URL tokens are
    # removed.  find_locked_tokens ends a URL at whitespace or one of ) ] > ' ",
    # and without this boundary stripping "https://host/a" would also destroy
    # the locked "https://host/a/b" and report it as removed.
    boundary = r"(?![^\s)\]>'\"])"
    for url in sorted(additions, key=len, reverse=True):
        text = re.sub(r"\]\(\s*" + re.escape(url) + boundary + r"[^)]*\)", "]", text)
        text = re.sub(re.escape(url) + boundary, " ", text)
    return text


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
    draft_text = draft.read_text(encoding="utf-8")
    value = {
        "locked_fields_schema_version": "1.0.0",
        "run_id": run["run_id"],
        "source_sha256": sha256_path(draft),
        "tokens": find_locked_tokens(draft_text),
        "claims": claims,
        # Record which required citations the draft never carried, so
        # naturalization is measured against a constraint it can satisfy.
        "citation_additions": sorted({
            str(claim["source_url_or_local_id"])
            for claim in claims
            if claim.get("risk") in {"medium", "high"}
            and isinstance(claim.get("source_url_or_local_id"), str)
            and str(claim["source_url_or_local_id"]).startswith("http")
            and str(claim["source_url_or_local_id"]) not in draft_text
        }),
    }
    path = directory / "artifacts" / "locked-fields.json"
    write_json(path, value)
    errors = validate_json_schema(path, "locked-fields.schema.json")
    if errors:
        raise FlowError("Controller generated invalid locked fields", EXIT_INTEGRITY, errors)
    record_artifact(directory, run, path, "locked-fields", {"actor": "controller", "version": CONTROLLER_VERSION}, inputs=[artifact(run, "draft")["artifact_id"], artifact(run, "verified-claim-ledger")["artifact_id"]])


DRAFT_COVERAGE_STOPWORDS = frozenset({
    "about", "above", "after", "again", "against", "all", "already", "also", "although",
    "always", "among", "and", "another", "any", "are", "around", "because", "been",
    "before", "being", "below", "between", "both", "but", "can", "cannot", "could",
    "did", "does", "doing", "done", "down", "during", "each", "either", "else",
    "enough", "even", "ever", "every", "few", "for", "from", "further", "had", "has",
    "have", "having", "here", "how", "however", "into", "its", "itself", "just",
    "less", "like", "made", "make", "many", "may", "might", "more", "most", "much",
    "must", "neither", "never", "not", "now", "off", "often", "once", "one", "only",
    "onto", "other", "others", "our", "out", "over", "own", "per", "rather", "same",
    "several", "shall", "should", "since", "some", "still", "such", "than", "that",
    "the", "their", "them", "then", "there", "these", "they", "this", "those",
    "through", "thus", "too", "under", "until", "upon", "use", "used", "using",
    "very", "was", "were", "what", "when", "where", "whether", "which", "while",
    "who", "whom", "whose", "why", "will", "with", "within", "without", "would",
    "you", "your",
})
# A rough draft is allowed to paraphrase, so a claim counts as covered on a
# modest share of its distinctive terms, and the gate only blocks when most of
# the brief is missing.  Both bounds are deliberately forgiving: a false
# rejection consumes one of DRAFT's three bounded attempts.
MINIMUM_CLAIM_TERM_COVERAGE = 0.4
MINIMUM_COVERED_CLAIM_SHARE = 0.5


def coverage_terms(value: str) -> set[str]:
    """Distinctive lowercase terms used to test whether prose covers a claim."""
    words = re.findall(r"[a-z0-9][a-z0-9'-]{2,}", unicodedata.normalize("NFKC", value).casefold())
    return {word for word in words if word not in DRAFT_COVERAGE_STOPWORDS}


def draft_coverage_findings(brief: dict[str, Any] | None, text: str, artifact: str) -> list[dict[str, Any]]:
    """Report the brief claims a rough draft does not argue at all.

    ``G-DRAFT-COVERAGE`` is named for this check but never performed it, so a
    draft that declined to write anything -- a single "Unresolved:" line, for
    example -- passed with no findings and carried an empty article through
    claim verification to the operator's only manual gate.  DRAFT already
    declares three bounded attempts and repairs to itself, so reporting the
    uncovered claims here is enough to route a refusal back into that window
    with the specific gaps attached.
    """
    if not isinstance(brief, dict):
        return []
    claims = [str(claim) for claim in brief.get("claims_to_support", []) if str(claim).strip()]
    if not claims:
        return []
    drafted = coverage_terms(text)
    uncovered: list[tuple[int, str]] = []
    for index, claim in enumerate(claims):
        required = coverage_terms(claim)
        if not required:
            continue
        if len(required & drafted) / len(required) < MINIMUM_CLAIM_TERM_COVERAGE:
            uncovered.append((index, claim))
    if len(claims) - len(uncovered) >= MINIMUM_COVERED_CLAIM_SHARE * len(claims):
        return []
    findings = [{
        "criterion": "brief_claim_coverage",
        "artifact": artifact,
        "location": "claims_to_support",
        "finding": (
            f"The rough draft covers {len(claims) - len(uncovered)} of the {len(claims)} claims the brief requires."
        ),
        "repair_instruction": "Write the complete rough draft the brief describes. If a required claim cannot be supported by the verified evidence, repair the brief instead of leaving the draft unwritten.",
    }]
    for index, claim in uncovered:
        findings.append({
            "criterion": "brief_claim_coverage",
            "artifact": artifact,
            "location": f"claims_to_support[{index}]",
            "finding": f"The rough draft does not argue the required claim: {claim}",
            "repair_instruction": "Argue this claim from the verified evidence, or remove it from the brief with a recorded reason.",
        })
    return findings


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
        compact_voice_submission = bool(
            state == "VOICE_PROBE"
            and is_v31_run(run)
            and value.get("voice_candidates_schema_version") == "1.0.0"
        )
        schema_by_state = {
            "RESEARCH_PLAN": "research-plan.schema.json",
            "RESEARCH": "claim-ledger.schema.json",
            "INTENT_REVIEW": "intent.schema.json",
            "ARTICLE_RECIPE": "article-recipe.schema.json",
            "BRIEF": "brief.schema.json",
            "VISUAL_PLAN": "visual-plan.schema.json",
            "VOICE_PROBE": "voice-candidates.schema.json" if compact_voice_submission else "voice-probe.schema.json",
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
                            detail = (
                                "is not a single well-formed URL"
                                if status < 0
                                else f"did not resolve during independent verification (HTTP {status})"
                            )
                            findings.append({"criterion": "source_resolution", "artifact": str(submission), "location": str(claim.get("claim_id")), "finding": f"Source URL {detail}.", "repair_instruction": "Give exactly one direct source URL for this claim, use another direct source, qualify/omit, or escalate."})
        if state == "VOICE_PROBE" and compact_voice_submission:
            raw_candidates = [item for item in value.get("candidates", []) if isinstance(item, dict)]
            if len(raw_candidates) != 3:
                findings.append({"criterion": "exactly_three_voice_variants", "artifact": str(submission), "location": "candidates", "finding": "Voice probe must contain exactly three candidates.", "repair_instruction": "Return exactly three one-paragraph variants of the controller-owned anchor."})
            claim_sets: list[tuple[str, ...]] = []
            dimension_sets: list[tuple[str, ...]] = []
            normalized_passages: list[str] = []
            for index, item in enumerate(raw_candidates):
                passage = str(item.get("passage") or "").strip()
                location = f"candidates[{index}]"
                paragraphs = [part for part in re.split(r"\n\s*\n", passage) if part.strip()]
                if len(paragraphs) != 1:
                    findings.append({"criterion": "one_paragraph_variant", "artifact": str(submission), "location": location, "finding": "A voice candidate is not exactly one paragraph.", "repair_instruction": "Return one paragraph per candidate."})
                for finding in forbidden_public_prose_character_findings(passage):
                    findings.append({**finding, "artifact": str(submission), "location": location})
                for finding in style_phrase_findings(passage, str(submission)):
                    findings.append({**finding, "location": location})
                claim_sets.append(tuple(sorted(str(claim) for claim in item.get("preserved_claim_ids", []))))
                dimension_sets.append(tuple(sorted(str(dimension) for dimension in item.get("intended_dimensions", []))))
                normalized_passages.append(re.sub(r"\W+", " ", passage.casefold()).strip())
            if claim_sets and len(set(claim_sets)) != 1:
                findings.append({"criterion": "shared_verified_meaning", "artifact": str(submission), "location": "candidates.preserved_claim_ids", "finding": "Candidates do not preserve the same verified claim set.", "repair_instruction": "Hold meaning and claims constant; vary only voice."})
            if len(set(dimension_sets)) != len(dimension_sets):
                findings.append({"criterion": "distinct_registers", "artifact": str(submission), "location": "candidates.intended_dimensions", "finding": "The candidates declare duplicate voice treatments.", "repair_instruction": "Use three meaningfully different registers, not cosmetic rewrites."})
            for left in range(len(normalized_passages)):
                for right in range(left + 1, len(normalized_passages)):
                    if difflib.SequenceMatcher(None, normalized_passages[left], normalized_passages[right]).ratio() > 0.88:
                        findings.append({"criterion": "distinct_registers", "artifact": str(submission), "location": f"candidates[{left}],candidates[{right}]", "finding": "Two candidates are nearly the same wording.", "repair_instruction": "Change rhythm, warmth, and framing while preserving the same meaning."})
        if state == "VOICE_PROBE" and not compact_voice_submission:
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
                    # A candidate is public prose the operator may promote
                    # into the voice profile, so it answers to the same
                    # deterministic character policy and formulaic-phrase
                    # scan as the draft, the article, and the public title
                    # and description.  Without this a selected candidate
                    # could teach the profile a character the house style
                    # forbids.
                    for finding in forbidden_public_prose_character_findings(passage):
                        findings.append({**finding, "artifact": str(submission), "location": str(item.get("candidate_id"))})
                    for finding in style_phrase_findings(passage, str(submission)):
                        findings.append({**finding, "location": str(item.get("candidate_id"))})
                    claim_sets.append(tuple(sorted(str(claim) for claim in item.get("preserved_claim_ids", []))))
                if claim_sets and len(set(claim_sets)) != 1:
                    findings.append({"criterion": "shared_verified_meaning", "artifact": str(submission), "location": "candidates.preserved_claim_ids", "finding": "Candidates do not preserve the same verified claim set.", "repair_instruction": "Hold meaning and claims constant; vary only the declared voice dimensions."})
                if len(orders) != 2 or any(set(order) != set(candidate_ids) for order in orders if isinstance(order, list)) or (len(orders) == 2 and list(orders[1]) != list(reversed(orders[0]))):
                    findings.append({"criterion": "balanced_comparison_orders", "artifact": str(submission), "location": "comparison_orders", "finding": "Comparison orders must contain the same three IDs in forward and reverse order.", "repair_instruction": "Provide one order and its exact reverse."})
        if state == "BRIEF":
            # The brief owns the public title and description, and nothing
            # downstream can repair them: editorial QA reports display-text
            # problems but repairs to EDIT, which only rewrites the article.
            # Catch them here, where the brief's own bounded window can.
            for field in ("title", "description"):
                display_text = str(value.get(field) or "")
                for finding in forbidden_public_prose_character_findings(display_text):
                    findings.append({**finding, "artifact": str(submission), "location": field})
                for finding in style_phrase_findings(display_text, str(submission)):
                    findings.append({**finding, "location": field})
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
        if state == "VISUAL_PLAN":
            draft_path = artifact_path(directory, run, "draft")
            draft_text = draft_path.read_text(encoding="utf-8") if draft_path else ""
            headings = {
                re.sub(r"\s+", " ", match.group(1)).strip().casefold()
                for match in re.finditer(r"^#{2,6}\s+(.+?)\s*$", draft_text, flags=re.MULTILINE)
            }
            visual_ids: set[str] = set()
            for index, visual in enumerate(value.get("visuals", [])):
                if not isinstance(visual, dict):
                    continue
                visual_id = str(visual.get("visual_id") or "")
                location = f"visuals[{index}]"
                if visual_id in visual_ids:
                    findings.append({"criterion": "unique_visual_id", "artifact": str(submission), "location": location, "finding": f"Duplicate visual_id {visual_id}.", "repair_instruction": "Give every planned visual a stable unique ID."})
                visual_ids.add(visual_id)
                after_heading = re.sub(r"\s+", " ", str((visual.get("placement") or {}).get("after_heading") or "")).strip().casefold()
                if after_heading not in headings:
                    findings.append({"criterion": "visual_placement", "artifact": str(submission), "location": f"{location}.placement.after_heading", "finding": "Placement does not match an exact level-2-or-lower heading in the draft.", "repair_instruction": "Copy one existing Markdown heading exactly, without its # prefix."})
                if visual.get("kind") == "console_reconstruction" and "reconstruct" not in str(visual.get("caption") or "").casefold():
                    findings.append({"criterion": "reconstruction_disclosure", "artifact": str(submission), "location": f"{location}.caption", "finding": "A screenshot-style reconstruction is not labeled as a reconstruction.", "repair_instruction": "State plainly in the caption that this is a reconstruction, not a captured product screenshot."})
                if visual.get("kind") == "console_reconstruction" and len(visual.get("labels", [])) < 4:
                    findings.append({"criterion": "console_sequence", "artifact": str(submission), "location": f"{location}.labels", "finding": "The console reconstruction does not contain the full observed question sequence.", "repair_instruction": "Include at least four concise interaction labels."})
        if state == "EDITORIAL_QA" and value.get("outcome") != "PASS":
            supplied = value.get("findings", [])
            if supplied:
                # These findings come from the model. Repair routing is a
                # controller decision, so strip any destination they carry
                # rather than letting an assessment choose where the run goes.
                findings.extend(
                    {key: item[key] for key in item if key != "repair_state"}
                    if isinstance(item, dict)
                    else item
                    for item in supplied
                )
            else:
                findings.append({"criterion": "editorial_outcome", "artifact": str(submission), "location": None, "finding": f"Editorial assessment returned {value.get('outcome')}.", "repair_instruction": "Return a passage-specific finding and repair destination."})
    if state == "EDIT":
        locked_path = artifact_path(directory, run, "locked-fields")
        if locked_path:
            locked_record = load_json(locked_path)
            before = locked_record.get("tokens", {})
            article_text = submission.read_text(encoding="utf-8")
            permitted = permitted_citation_additions(locked_record)
            # A URL the evidence never cited is not a verified value, so
            # naturalization may replace it with the one the ledger records.
            # Both sides are measured with those URLs removed, which keeps
            # every other locked category strict: the numbers, dates, and
            # markdown links such a URL carries disappear from both.
            droppable = unverified_locked_urls(locked_record)
            draft_path = artifact_path(directory, run, "draft")
            if (
                draft_path
                and draft_path.is_file()
                and sha256_path(draft_path) == locked_record.get("source_sha256")
            ):
                # Recompute from the exact locked source so releases created
                # before image links became manifest-owned migrate safely.
                before = find_locked_tokens(
                    strip_citation_additions(draft_path.read_text(encoding="utf-8"), droppable)
                )
                permitted = permitted | droppable
            after = find_locked_tokens(strip_citation_additions(article_text, permitted))
            for category in before:
                # Compare the set of verified values, not their multiplicity.
                # Introducing, altering, or dropping a locked value all still
                # fail, but naturalization rewrites sentences, so mentioning an
                # unchanged value a different number of times is not a change
                # to that value and must not consume the repair window.
                locked_before = set(before[category])
                locked_after = set(after[category])
                if locked_before == locked_after:
                    continue
                removed = sorted(locked_before - locked_after)
                added = sorted(locked_after - locked_before)
                # Name the values.  These findings are the writer's whole
                # instruction on the next attempt, and "changed locked urls"
                # identifies nothing, so a rewrite that also has to satisfy the
                # citation gate alternates between the two instead of
                # converging.
                detail = []
                if removed:
                    detail.append("removed " + ", ".join(repr(item) for item in removed[:5]))
                if added:
                    detail.append("added " + ", ".join(repr(item) for item in added[:5]))
                findings.append({
                    "criterion": "locked_fields",
                    "artifact": str(submission),
                    "location": category,
                    "finding": f"Naturalization changed locked {category}: " + "; ".join(detail) + ".",
                    "repair_instruction": f"Restore every removed {category} value verbatim and remove any that was added, keeping each required citation in place, or reopen claim verification.",
                })
            recipe = json_artifact(directory, run, "article-recipe") or {}
            if recipe.get("citation_mode") == "links":
                for claim in locked_record.get("claims", []):
                    source = claim.get("source_url_or_local_id")
                    if claim.get("risk") in {"medium", "high"} and isinstance(source, str) and source.startswith("http") and source not in article_text:
                        findings.append({
                            "criterion": "claim_citation_mapping",
                            "artifact": str(submission),
                            "location": str(claim.get("claim_id")),
                            # Name the claim and its exact URL.  The repair
                            # context carries these findings verbatim to the
                            # next attempt, and a message that says only that
                            # "a" link was lost gives the writer nothing to act
                            # on: it identifies neither which claim nor which
                            # string, so the same omission repeats.
                            "finding": f"Claim {claim.get('claim_id')} lost its source link. The article must contain this exact URL: {source}",
                            # Say how to satisfy this without breaking the
                            # neighbouring rules.  Editorial QA rejects a bare
                            # duplicate URL and the locked-token check rejects
                            # re-targeting a link the draft already carried, so
                            # a finding that asks only for presence sends the
                            # writer between two gates it cannot satisfy at once.
                            "repair_instruction": f"Insert {source} byte-identically as a Markdown link on the claim it supports, not as bare URL text. Do not substitute an equivalent, shortened, or modernized URL, and do not remove or re-target any URL the draft already carried; adding a second link for the same source is expected when the draft cited a different form of it.",
                        })
    if state in {"DRAFT", "EDIT"}:
        text = submission.read_text(encoding="utf-8")
        for pattern in (r"\[Writer to research[^\]]*\]", r"\bTODO\b", r"/mnt/[a-z]/Users/", r"[A-Z]:\\Users\\"):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                findings.append({"criterion": "no_placeholders_or_private_paths", "artifact": str(submission), "location": match.group(0), "finding": "Public-candidate text contains a placeholder or private local path.", "repair_instruction": "Resolve or remove the private/internal text."})
        for finding in forbidden_public_prose_character_findings(text):
            findings.append({**finding, "artifact": str(submission)})
        findings.extend(style_phrase_findings(text, str(submission)))
        if state == "DRAFT":
            findings.extend(draft_coverage_findings(
                json_artifact(directory, run, "brief"),
                text,
                str(submission),
            ))
    if state in {"CLAIM_VERIFICATION", "POST_EDIT_CLAIM_VERIFICATION"}:
        # Every code-owned check at these gates validates the ledger just
        # submitted, not the article it describes, so direct their repairs at
        # the stage that produced the record.  A check added later that really
        # is about the article can set its own destination and keep it.
        for finding in findings:
            finding.setdefault("repair_state", state)
    return ("PASS" if not findings else "REPAIR"), findings


def materialize_voice_probe(
    directory: Path,
    run: dict[str, Any],
    candidates_path: Path,
    attempt: int,
) -> Path:
    """Wrap model prose in a controller-owned, hash-bound comparison envelope."""
    source = load_json(candidates_path)
    anchor_path = artifact_path(directory, run, "voice-anchor")
    draft_path = artifact_path(directory, run, "draft")
    ledger_path = artifact_path(directory, run, "verified-claim-ledger")
    profile_path = artifact_path(directory, run, "voice-profile")
    assignment_path = artifact_path(directory, run, "model-assignment")
    if not all((anchor_path, draft_path, ledger_path, profile_path, assignment_path)):
        raise FlowError("Voice-probe controller bindings are incomplete", EXIT_INTEGRITY)
    anchor = load_json(anchor_path)  # type: ignore[arg-type]
    ids = ("A", "B", "C")
    candidates: list[dict[str, Any]] = []
    for candidate_id, raw in zip(ids, source.get("candidates", [])):
        passage = str(raw["passage"]).strip()
        candidates.append({
            "candidate_id": candidate_id,
            "passage": passage,
            "passage_sha256": sha256_bytes(passage.encode("utf-8")),
            "intended_dimensions": list(raw.get("intended_dimensions", [])),
            "preserved_claim_ids": list(raw.get("preserved_claim_ids", [])),
        })
    probe = {
        "voice_probe_schema_version": "2.0.0",
        "run_id": run["run_id"],
        "rough_draft_sha256": sha256_path(draft_path),  # type: ignore[arg-type]
        "claim_ledger_sha256": sha256_path(ledger_path),  # type: ignore[arg-type]
        "voice_profile_sha256": sha256_path(profile_path),  # type: ignore[arg-type]
        "model_assignment_sha256": sha256_path(assignment_path),  # type: ignore[arg-type]
        "source_anchor": {
            "locator": anchor["locator"],
            "source_passage": anchor["source_passage"],
            "source_passage_sha256": anchor["source_passage_sha256"],
        },
        "article_register": source.get("article_register", {}),
        "candidates": candidates,
        "comparison_orders": [list(ids), list(reversed(ids))],
        "held_out_plan": "Compare the selected register against a different opening or thesis paragraph during editorial QA; do not treat one selection as a universal trait.",
        "operator_selection": None,
    }
    path = directory / "artifacts" / f"voice-probe-{attempt:02d}.json"
    write_json(path, probe)
    errors = validate_json_schema(path, "voice-probe.schema.json")
    if errors:
        raise FlowError("Controller generated an invalid voice-probe envelope", EXIT_INTEGRITY, errors)
    record_artifact(
        directory,
        run,
        path,
        "voice-probe",
        {"actor": "controller", "version": CONTROLLER_VERSION, "model_prose_artifact": candidates_path.name},
        inputs=[item["artifact_id"] for item in run.get("artifact_index", []) if item.get("type") in {"voice-candidates", "voice-anchor", "draft", "verified-claim-ledger", "voice-profile", "model-assignment"}],
    )
    return path


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


VOICE_CANDIDATE_ARTIFACT_TYPE = "voice-probe-candidates"


def _probe_holds_no_selection(path: Path, item: dict[str, Any]) -> bool:
    """True when these exact recorded bytes are still a pre-decision probe."""
    try:
        if not path.is_file() or sha256_path(path) != item.get("sha256"):
            return False
        value = load_json(path)
    except (FlowError, OSError):
        return False
    return isinstance(value, dict) and value.get("operator_selection") is None


def voice_candidate_probe(
    directory: Path,
    run: dict[str, Any],
    events: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, Path | None]:
    """Resolve the code-validated three-candidate probe.

    The approved probe is recorded over the ``voice-probe`` type so voice
    learning keeps reading exactly one selection-bearing artifact.  That
    overwrite used to be the only surviving record, so a crash between the
    durable selection and its state transition left the candidate authority
    unreachable and made every retry fail ``operator_selection_authority``.
    The candidate bytes are now preserved under their own type before the
    overwrite: prefer that record, fall back to a ``voice-probe`` entry that
    still carries no selection, and finally recover the overwritten record
    from the immutable event log for runs stored before this change.
    """
    preserved = artifact(run, VOICE_CANDIDATE_ARTIFACT_TYPE)
    if preserved:
        return preserved, directory / preserved["path"]
    item = artifact(run, "voice-probe")
    if item and _probe_holds_no_selection(directory / item["path"], item):
        return item, directory / item["path"]
    if events is None:
        verified, _, _, events = verify_event_log(directory, run)
        if not verified:
            return None, None
    for event in reversed(events):
        if event.get("type") != "ARTIFACT_RECORDED":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        recorded = payload.get("artifact")
        if not isinstance(recorded, dict) or recorded.get("type") != "voice-probe":
            continue
        try:
            recovered = (directory / safe_relative(str(recorded.get("path", "")))).resolve()
            recovered.relative_to(directory.resolve())
        except (FlowError, ValueError):
            continue
        if _probe_holds_no_selection(recovered, recorded):
            return recorded, recovered
    return None, None


def preserve_voice_candidate_probe(
    directory: Path,
    run: dict[str, Any],
    item: dict[str, Any],
    path: Path,
) -> None:
    """Record the three-candidate probe under its own immutable type.

    This runs before the approved probe overwrites the ``voice-probe`` record,
    so the code-validated candidate authority survives every later crash.
    """
    if artifact(run, VOICE_CANDIDATE_ARTIFACT_TYPE):
        return
    try:
        candidate_bytes = path.read_bytes()
    except OSError as exc:
        raise FlowError(
            "Voice candidate probe could not be read for preservation",
            EXIT_INTEGRITY,
            {"path": str(path)},
        ) from exc
    if sha256_bytes(candidate_bytes) != item.get("sha256"):
        raise FlowError(
            "Voice candidate probe changed before its authority was preserved",
            EXIT_INTEGRITY,
            {
                "path": str(path),
                "expected_sha256": item.get("sha256"),
                "actual_sha256": sha256_bytes(candidate_bytes),
            },
        )
    record_artifact(
        directory,
        run,
        path,
        VOICE_CANDIDATE_ARTIFACT_TYPE,
        {"actor": "controller", "version": CONTROLLER_VERSION},
        inputs=[str(item["artifact_id"])] if item.get("artifact_id") else [],
        expected_bytes=candidate_bytes,
    )


def committed_voice_selection(
    directory: Path,
    run: dict[str, Any],
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return a human voice decision that is durable but not yet transitioned.

    ``VOICE_SELECTION_RECORDED`` and the passing ``G-VOICE-PROBE`` receipt are
    both appended before the state transition, so a crash in that window leaves
    a committed human decision behind a run still parked in ``VOICE_PROBE``.
    That pair is the commitment and the missing transition is the only
    unfinished work; any later ``STATE_TRANSITION`` means the commitment
    already completed and there is nothing left to reconcile.
    """
    if not is_v3_run(run) or run.get("state") != "VOICE_PROBE":
        return None
    if events is None:
        verified, _, _, events = verify_event_log(directory, run)
        if not verified:
            return None
    pending: dict[str, Any] | None = None
    for event in events:
        kind = event.get("type")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if kind == "VOICE_SELECTION_RECORDED":
            pending = {
                "candidate_id": str(payload.get("candidate_id") or ""),
                "voice_probe_sha256": str(payload.get("voice_probe_sha256") or ""),
                "selection_sequence": int(event.get("sequence", 0)),
                "gate_sequence": None,
            }
        elif kind == "GATE_RECORDED" and payload.get("gate_id") == "G-VOICE-PROBE":
            if pending is None:
                continue
            if payload.get("outcome") == "PASS":
                pending["gate_sequence"] = int(event.get("sequence", 0))
            else:
                pending = None
        elif kind == "STATE_TRANSITION":
            pending = None
    if pending is None or pending["gate_sequence"] is None or not pending["candidate_id"]:
        return None
    return pending


def finish_committed_voice_selection(
    directory: Path,
    run: dict[str, Any],
    committed: dict[str, Any],
) -> None:
    """Complete exactly the interrupted transition and add no new evidence."""
    definition = state_definition(run["state"], run)
    transition(
        directory,
        run,
        definition["next_on_pass"],
        "controller",
        "Completed the interrupted transition for committed voice selection "
        + str(committed["candidate_id"]),
    )


def reconcile_committed_voice_selection(
    directory: Path,
    run: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """Resolve a retry of an already committed voice decision, or fail closed."""
    if str(args.gate_id) != "G-VOICE-PROBE":
        return None
    committed = committed_voice_selection(directory, run)
    if committed is None:
        return None
    if args.outcome != "PASS":
        raise FlowError(
            "The operator's voice selection is already committed and cannot be replaced at this gate",
            EXIT_APPROVAL,
            committed,
        )
    if str(getattr(args, "selection", None) or "") != committed["candidate_id"]:
        raise FlowError(
            "A different voice candidate is already committed for this run",
            EXIT_APPROVAL,
            {
                "committed_candidate_id": committed["candidate_id"],
                "requested_candidate_id": getattr(args, "selection", None),
            },
        )
    finish_committed_voice_selection(directory, run, committed)
    next_command = ["article-flow", "advance", run["run_id"]] if automation_enabled(run) else ["article-flow", "next", run["run_id"]]
    return {
        "ok": True,
        "outcome": "PASS",
        "state": run["state"],
        "approval_id": None,
        "reconciled_voice_selection": committed["candidate_id"],
        "next_command": next_command,
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


def voice_probe_awaits_human(
    directory: Path,
    run: dict[str, Any],
    events: list[dict[str, Any]] | None = None,
) -> bool:
    """True when the recorded probe passed its gate and is waiting on the operator.

    ``command_submit`` records the produced artifact before writing the gate
    receipt, so a probe rejected by its code-owned checks still leaves a
    ``voice-probe`` artifact behind.  Presenting the operator a probe that
    ``automatic_gate`` refuses is worse than useless: choosing a candidate is
    rejected as an integrity failure, and because the caller stops at the
    decision the declared repair window never dispatches its next attempt.

    A passing review submission records ``ESCALATE`` for the human decision and
    a rejected one records ``REPAIR``, so the newest gate outcome is the
    durable signal.  A later dispatch means a fresh attempt is in flight.  Runs
    whose probe was recorded without any gate event keep the prior behaviour.
    """
    if events is None:
        verified, _, _, events = verify_event_log(directory, run)
        if not verified:
            return False
    awaiting = True
    for event in events:
        kind = event.get("type")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if kind == "GATE_RECORDED" and payload.get("gate_id") == "G-VOICE-PROBE":
            awaiting = payload.get("outcome") == "ESCALATE"
        elif kind == "TASK_DISPATCHED" and payload.get("state") == "VOICE_PROBE":
            awaiting = False
        elif kind == "REPAIR" and str(payload.get("repair_state") or "") == "VOICE_PROBE":
            # An authorized repair supersedes a pending decision: the probe is
            # being regenerated, so there is nothing to choose from until the
            # next attempt is produced.  Without this the caller re-presents
            # the superseded candidates forever and the repair never runs.
            awaiting = False
    return awaiting


def next_state_payload(directory: Path, run: dict[str, Any]) -> dict[str, Any]:
    state = run["state"]
    if state in {"COMPLETE", "TERMINAL"}:
        return {"action": state.lower(), "run_id": run["run_id"], "state": state}
    if run.get("status") == "BLOCKED":
        definition = state_definition(state, run)
        return {"action": "repair_required", "run_id": run["run_id"], "state": state, "gate": definition.get("gate"), "command": ["article-flow", "repair", run["run_id"], definition.get("gate")]}
    if is_v3_run(run) and state == "VOICE_PROBE":
        committed = committed_voice_selection(directory, run)
        if committed is not None:
            # The human already decided.  Only the interrupted transition is
            # outstanding, so never re-ask and never re-enter WAITING_HUMAN.
            return {
                "action": "run_command",
                "run_id": run["run_id"],
                "state": state,
                "committed_voice_selection": committed["candidate_id"],
                "command": ["article-flow", "choose-voice", run["run_id"], committed["candidate_id"]],
            }
    review_artifact = {
        "INTENT_REVIEW": "intent-candidate",
        "ARTICLE_RECIPE": "article-recipe",
        "VOICE_PROBE": "voice-probe",
        "EDITORIAL_QA": "editorial-qa",
    }
    if (
        state in REVIEW_STATES
        and artifact(run, review_artifact[state])
        and (state != "VOICE_PROBE" or voice_probe_awaits_human(directory, run))
    ):
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
                "question": "Which one of these three paragraphs sounds most like you, or should all three be regenerated? A short reason is optional for a selection and required for regeneration.",
                "candidates": candidates,
                "selection_commands": {
                    str(item["candidate_id"]): ["article-flow", "choose-voice", run["run_id"], str(item["candidate_id"]), "--auto"]
                    for item in candidates
                },
                "rejection_command": ["article-flow", "regenerate-voice", run["run_id"], "--feedback", "WHAT_MISSED", "--auto"],
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
    if state == "VISUAL_RENDER":
        return {"action": "run_command", "run_id": run["run_id"], "state": state, "command": ["article-flow", "render-visuals", run["run_id"]]}
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
    resumable, resume_issue = resumable_model_output(directory, run, packet_path, packet)
    if resume_issue:
        run["status"] = "BLOCKED"
        append_event(directory, run, "ESCALATION", "controller", {
            "state": state,
            "gate_id": state_definition(state, run).get("gate"),
            **resume_issue,
        })
        save_run(directory, run)
        raise FlowError("Recorded model-call evidence failed integrity validation", EXIT_INTEGRITY, resume_issue)
    if resumable:
        return {
            "action": "run_command",
            "run_id": run["run_id"],
            "state": state,
            "reason": "resume_recorded_model_call",
            "command": ["article-flow", "submit", run["run_id"], "--stage", state, "--file", str(resumable["output_path"])],
        }
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
        "attempt_baselines": {},
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


def command_revise(args: argparse.Namespace) -> int:
    """Create a new, fully verified run that replaces one completed URL in place."""
    source_directory, source_run = load_run(args.source_run_id)
    if source_run.get("state") != "COMPLETE":
        raise FlowError("A same-URL revision requires a completed source run", EXIT_USAGE)
    request_path = Path(args.request_file).expanduser().resolve()
    if not request_path.is_file() or not request_path.read_text(encoding="utf-8").strip():
        raise FlowError(f"Revision request does not exist or is empty: {request_path}", EXIT_USAGE)
    source_seed = artifact_path(source_directory, source_run, "seed")
    source_metadata_path = source_directory / "package" / "public" / "metadata.json"
    if not source_seed or not source_metadata_path.is_file():
        raise FlowError("Completed source run lacks its seed or publication metadata", EXIT_INTEGRITY)
    source_metadata = load_json(source_metadata_path)
    start_args = argparse.Namespace(
        seed=None,
        seed_file=str(source_seed),
        slug=str(source_metadata.get("slug") or ""),
        draft_model=getattr(args, "draft_model", None),
        auto=False,
        hold_before_publish=bool(getattr(args, "hold_before_publish", False)),
        json=True,
    )
    code, created = _silent_command(command_start, start_args)
    if code != EXIT_OK or not created or not created.get("run_id"):
        raise FlowError("Could not create the correction run", code or EXIT_FAILED, created)
    run_id = str(created["run_id"])
    directory, run = load_run(run_id)
    with run_lock(directory, run):
        request_destination = directory / "artifacts" / "revision-request.md"
        request_bytes = request_path.read_bytes()
        immutable_write(request_destination, request_bytes)
        request_artifact = record_artifact(
            directory,
            run,
            request_destination,
            "revision-request",
            {"actor": "operator", "source_run_id": source_run["run_id"], "preserved_verbatim": True},
            expected_bytes=request_bytes,
        )
        target = load_json(SPEC_ROOT / "publication" / "theproductiveprompter.json")
        revision = {
            "revision_schema_version": "1.0.0",
            "source_run_id": source_run["run_id"],
            "mode": "replace_in_place",
            "slug": str(source_metadata["slug"]),
            "canonical_url": target["canonical_url"].format(slug=source_metadata["slug"]),
            "original_published_date": str(source_metadata["date"]),
            "requested_at": utc_now(),
            "request_sha256": request_artifact["sha256"],
        }
        revision_path = directory / "artifacts" / "revision.json"
        write_json(revision_path, revision)
        errors = validate_json_schema(revision_path, "revision.schema.json")
        if errors:
            raise FlowError("Controller generated an invalid revision record", EXIT_INTEGRITY, errors)
        record_artifact(directory, run, revision_path, "revision", {"actor": "controller", "version": CONTROLLER_VERSION}, inputs=[request_artifact["artifact_id"]])
        run["revision"] = revision
        run["parent_run_id"] = source_run["run_id"]
        append_event(directory, run, "REVISION_CREATED", "controller", revision)
        save_run(directory, run)
    if bool(getattr(args, "auto", False)):
        return command_advance(argparse.Namespace(run_id=run_id, max_steps=100, json=args.json))
    emit({"ok": True, "run_id": run_id, "source_run_id": source_run["run_id"], "state": run["state"], "revision": revision, "next_command": ["article-flow", "advance", run_id]}, args.json)
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
        "next_action_summary": (
            "complete" if run["state"] == "COMPLETE"
            else "terminal" if run["state"] == "TERMINAL"
            else "operator repair required" if run.get("status") == "BLOCKED"
            else "choose or reject the three voice candidates" if run["state"] == "VOICE_PROBE" and run.get("status") == "WAITING_HUMAN"
            else "run the next automatic controller step" if run["state"] in DETERMINISTIC_STATES
            else "produce and validate the current model-stage artifact"
        ),
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
    artifact_type, filename = stage_output(args.stage, run)
    with run_lock(directory, run):
        if run["state"] != args.stage:
            raise FlowError(
                f"Submission for {args.stage} is stale or the recorded task is no longer waiting for a model",
                EXIT_INTEGRITY,
                {"state": run["state"], "status": run.get("status")},
            )
        packet_item = latest_task_packet_item(directory, run, args.stage)
        if not packet_item:
            raise FlowError(f"No dispatched task packet exists for {args.stage}", EXIT_INTEGRITY)
        packet_path, packet_value, packet_issue = validate_recorded_task_packet(directory, run, packet_item)
        if packet_issue or packet_path is None or packet_value is None:
            packet_match = re.fullmatch(
                rf"task-packet:{re.escape(args.stage)}:(\d+)",
                str(packet_item.get("type", "")),
            )
            recorded_hash = str(packet_item.get("sha256", ""))
            if packet_match and re.fullmatch(r"[0-9a-f]{64}", recorded_hash):
                block_attempt_reconciliation(
                    directory,
                    run,
                    args.stage,
                    int(packet_match.group(1)),
                    recorded_hash,
                    packet_issue or {"reason": "recorded_task_packet_unreadable"},
                )
            raise FlowError("Recorded task packet failed integrity validation", EXIT_INTEGRITY, packet_issue)
        attempt = int(packet_value["attempt"])
        packet_bytes = (json.dumps(packet_value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        packet_hash = sha256_bytes(packet_bytes)
        try:
            current_packet_bytes = packet_path.read_bytes()
        except OSError:
            current_packet_bytes = None
        if current_packet_bytes != packet_bytes or packet_item.get("sha256") != packet_hash:
            issue = {
                "reason": "task_packet_changed_before_submission",
                "path": str(packet_path),
                "expected_sha256": packet_hash,
                "actual_sha256": sha256_bytes(current_packet_bytes) if isinstance(current_packet_bytes, bytes) else None,
            }
            block_attempt_reconciliation(directory, run, args.stage, attempt, packet_hash, issue)
            raise FlowError("Task packet changed before submission", EXIT_INTEGRITY, issue)
        if int(run.get("attempts", {}).get(args.stage, 0)) != attempt:
            raise FlowError(
                "Submission attempt does not match the current monotonic task attempt",
                EXIT_INTEGRITY,
                {"packet_attempt": attempt, "run_attempt": run.get("attempts", {}).get(args.stage)},
            )
        dispatch_sequence = task_packet_dispatch_sequence(directory, run, args.stage, attempt, packet_path)
        if dispatch_sequence is None:
            issue = {"reason": "task_packet_was_not_durably_dispatched", "attempt": attempt}
            block_attempt_reconciliation(directory, run, args.stage, attempt, packet_hash, issue)
            raise FlowError("Task packet was never durably dispatched", EXIT_INTEGRITY, issue)
        if task_packet_gate_consumed(
            directory,
            run,
            args.stage,
            attempt,
            packet_hash,
            dispatch_sequence,
        ):
            issue = {
                "reason": "task_packet_gate_already_recorded",
                "attempt": attempt,
                "dispatch_sequence": dispatch_sequence,
            }
            block_attempt_reconciliation(directory, run, args.stage, attempt, packet_hash, issue)
            raise FlowError(
                "Task packet gate outcome is already recorded and cannot be replayed",
                EXIT_WAITING,
                issue,
            )
        committed_gate, gate_issue = validated_gate_receipt_for_attempt(
            directory,
            run,
            args.stage,
            attempt,
            packet_hash,
            dispatch_sequence,
        )
        if gate_issue or committed_gate:
            issue = gate_issue or {
                "reason": "task_packet_gate_receipt_requires_reconciliation",
                "attempt": attempt,
                "gate_receipt": committed_gate["path"],
            }
            block_attempt_reconciliation(directory, run, args.stage, attempt, packet_hash, issue)
            raise FlowError("Submission gate receipt is already committed and cannot be replayed", EXIT_WAITING, issue)
        if run.get("status") != "WAITING_MODEL":
            # Gate evidence is checked first so a cache reconstructed as
            # BLOCKED is durably reconciled instead of merely rejected while
            # run.json remains WAITING_MODEL.  Other stale statuses have no
            # decision to replay and are rejected without mutation.
            raise FlowError(
                f"Submission for {args.stage} is stale or the recorded task is no longer waiting for a model",
                EXIT_INTEGRITY,
                {"state": run["state"], "status": run.get("status")},
            )
        model_call, receipt_issue = validated_model_call_item(directory, run, args.stage, attempt, packet_path)
        if receipt_issue:
            block_attempt_reconciliation(directory, run, args.stage, attempt, packet_hash, receipt_issue)
            raise FlowError("Recorded model-call receipt failed integrity validation", EXIT_INTEGRITY, receipt_issue)
        expected_output = Path(packet_value["expected_outputs"][0]["path"]).expanduser().resolve()
        submissions_root = (directory / "submissions").resolve()
        try:
            source.relative_to(submissions_root)
            source_is_run_submission = True
        except ValueError:
            source_is_run_submission = False
        if is_v3_run(run) and source != expected_output:
            raise FlowError(
                "Workflow 3 submissions must use the exact output path bound by the current task packet",
                EXIT_INTEGRITY,
                {"source": str(source), "expected_output": str(expected_output), "attempt": attempt},
            )
        if not is_v3_run(run) and source_is_run_submission and source != expected_output:
            raise FlowError(
                "Submission file belongs to a stale task attempt",
                EXIT_INTEGRITY,
                {"source": str(source), "expected_output": str(expected_output), "attempt": attempt},
            )
        # Bind validation and the accepted artifact to one byte snapshot.  A
        # second path read after hashing creates a TOCTOU window in which the
        # receipt can validate one file while different bytes are copied.
        try:
            source_bytes = source.read_bytes()
        except OSError as exc:
            issue = {
                "reason": "submission_bytes_unreadable",
                "path": str(source),
                "attempt": attempt,
                "error": str(exc),
            }
            block_attempt_reconciliation(directory, run, args.stage, attempt, packet_hash, issue)
            raise FlowError("Submission bytes could not be read", EXIT_INTEGRITY, issue) from exc
        source_hash = sha256_bytes(source_bytes)
        if model_call and model_call["receipt"].get("output_sha256") != source_hash:
            issue = {
                "reason": "submission_bytes_changed_after_model_call",
                "expected_sha256": model_call["receipt"].get("output_sha256"),
                "actual_sha256": source_hash,
                "attempt": attempt,
            }
            block_attempt_reconciliation(directory, run, args.stage, attempt, packet_hash, issue)
            raise FlowError(
                "Submission bytes do not match the recorded model-call output",
                EXIT_INTEGRITY,
                issue,
            )
        destination = directory / "artifacts" / f"{attempt:02d}-{filename}"
        declared_inputs: list[tuple[Path, str, str]] = []
        for item in packet_value.get("inputs", []):
            input_path = Path(item["path"])
            try:
                input_bytes = input_path.read_bytes()
                actual_hash = sha256_bytes(input_bytes)
            except OSError:
                actual_hash = None
            if actual_hash != item["sha256"]:
                issue = {
                    "reason": "task_input_changed_before_submission",
                    "input_id": item["id"],
                    "expected_sha256": item["sha256"],
                    "actual_sha256": actual_hash,
                    "path": str(input_path),
                }
                block_attempt_reconciliation(directory, run, args.stage, attempt, packet_hash, issue)
                raise FlowError(f"Task input changed before submission: {item['id']}", EXIT_INTEGRITY, issue)
            declared_inputs.append((input_path, str(item["sha256"]), str(item["id"])))
        try:
            immutable_write(destination, source_bytes)
        except (FlowError, OSError) as exc:
            try:
                existing_hash = sha256_path(destination) if destination.is_file() else None
            except OSError:
                existing_hash = None
            issue = {
                "reason": "accepted_attempt_destination_bytes_disagree",
                "path": str(destination),
                "existing_sha256": existing_hash,
                "submitted_sha256": source_hash,
                "error": str(exc),
            }
            block_attempt_reconciliation(directory, run, args.stage, attempt, packet_hash, issue)
            raise FlowError(
                "Accepted attempt destination already contains different immutable bytes",
                EXIT_INTEGRITY,
                issue,
            ) from exc
        outcome, findings = automatic_gate(directory, run, args.stage, destination)
        try:
            accepted_hash = sha256_path(destination) if destination.is_file() else None
        except OSError:
            accepted_hash = None
        if accepted_hash != source_hash:
            issue = {
                "reason": "accepted_attempt_destination_changed_during_gate",
                "path": str(destination),
                "expected_sha256": source_hash,
                "actual_sha256": accepted_hash,
            }
            block_attempt_reconciliation(directory, run, args.stage, attempt, packet_hash, issue)
            raise FlowError(
                "Accepted attempt destination changed during gate evaluation",
                EXIT_INTEGRITY,
                issue,
            )

        def require_submit_evidence(reason: str) -> None:
            mismatch: dict[str, Any] | None = None
            try:
                observed_packet_bytes = packet_path.read_bytes()
            except OSError:
                observed_packet_bytes = None
            if observed_packet_bytes != packet_bytes:
                mismatch = {
                    "evidence": "task_packet",
                    "path": str(packet_path),
                    "expected_sha256": packet_hash,
                    "actual_sha256": sha256_bytes(observed_packet_bytes) if isinstance(observed_packet_bytes, bytes) else None,
                }
            if mismatch is None and model_call:
                receipt_path = Path(str(model_call["path"]))
                try:
                    actual_receipt_hash = sha256_path(receipt_path) if receipt_path.is_file() else None
                except OSError:
                    actual_receipt_hash = None
                expected_receipt_hash = str(model_call["item"].get("sha256") or "")
                if actual_receipt_hash != expected_receipt_hash:
                    mismatch = {
                        "evidence": "model_call_receipt",
                        "path": str(receipt_path),
                        "expected_sha256": expected_receipt_hash,
                        "actual_sha256": actual_receipt_hash,
                    }
            # The model output file is deliberately not re-read here.  Its
            # authority was consumed by the single snapshot above, which the
            # model-call receipt validated and which was committed verbatim to
            # the immutable destination.  Re-reading that path would reopen the
            # exact TOCTOU window the snapshot exists to close, and would let a
            # post-commit write to a transient model scratch file invalidate an
            # attempt whose accepted bytes are already immutable.  The accepted
            # copy below is the evidence that must not change.
            if mismatch is None:
                try:
                    actual_destination_hash = sha256_path(destination) if destination.is_file() else None
                except OSError:
                    actual_destination_hash = None
                if actual_destination_hash != source_hash:
                    mismatch = {
                        "evidence": "accepted_output",
                        "path": str(destination),
                        "expected_sha256": source_hash,
                        "actual_sha256": actual_destination_hash,
                    }
            if mismatch is None:
                for input_path, expected_input_hash, input_id in declared_inputs:
                    try:
                        actual_input_hash = sha256_path(input_path) if input_path.is_file() else None
                    except OSError:
                        actual_input_hash = None
                    if actual_input_hash != expected_input_hash:
                        mismatch = {
                            "evidence": "task_input",
                            "input_id": input_id,
                            "path": str(input_path),
                            "expected_sha256": expected_input_hash,
                            "actual_sha256": actual_input_hash,
                        }
                        break
            if mismatch is not None:
                issue = {"reason": reason, **mismatch}
                block_attempt_reconciliation(directory, run, args.stage, attempt, packet_hash, issue)
                raise FlowError("Attempt evidence changed during submission", EXIT_INTEGRITY, issue)

        require_submit_evidence("attempt_evidence_changed_after_gate")
        packet_route = latest_model_call_route(directory, run, args.stage, attempt)
        if packet_route is None and packet_item:
            packet_route = packet_value.get("selected_route", {}).get("chosen")
        existing_output = latest_recorded_artifact(
            directory,
            run,
            lambda item: item.get("type") == artifact_type
            and item.get("path") == destination.relative_to(directory).as_posix()
            and item.get("sha256") == source_hash,
        )
        try:
            if destination.read_bytes() != source_bytes:
                raise FlowError("Accepted output changed before artifact recording", EXIT_INTEGRITY)
            if existing_output:
                run["artifact_index"] = [item for item in run["artifact_index"] if item.get("type") != artifact_type]
                run["artifact_index"].append(existing_output)
            else:
                record_artifact(
                    directory,
                    run,
                    destination,
                    artifact_type,
                    {"actor": "model_or_host", "route": packet_route},
                    inputs=[item["artifact_id"] for item in run["artifact_index"]],
                    expected_bytes=source_bytes,
                )
            recorded_hash = sha256_path(destination) if destination.is_file() else None
        except (FlowError, OSError) as exc:
            try:
                recorded_hash = sha256_path(destination) if destination.is_file() else None
            except OSError:
                recorded_hash = None
            issue = {
                "reason": "accepted_attempt_destination_changed_before_record",
                "path": str(destination),
                "expected_sha256": source_hash,
                "actual_sha256": recorded_hash,
                "error": str(exc),
            }
            block_attempt_reconciliation(directory, run, args.stage, attempt, packet_hash, issue)
            raise FlowError("Accepted attempt changed before artifact recording", EXIT_INTEGRITY, issue) from exc
        if recorded_hash != source_hash:
            issue = {
                "reason": "accepted_attempt_destination_changed_after_record",
                "path": str(destination),
                "expected_sha256": source_hash,
                "actual_sha256": recorded_hash,
            }
            block_attempt_reconciliation(directory, run, args.stage, attempt, packet_hash, issue)
            raise FlowError("Accepted attempt changed after artifact recording", EXIT_INTEGRITY, issue)
        require_submit_evidence("attempt_evidence_changed_after_artifact_record")
        if args.stage == "VOICE_PROBE" and is_v31_run(run) and outcome == "PASS":
            materialize_voice_probe(directory, run, destination, attempt)
        if args.stage == "CLAIM_VERIFICATION" and outcome == "PASS":
            lock_verified_fields(directory, run, destination)
        definition = state_definition(args.stage, run)
        policy_accepted_findings: list[dict[str, Any]] = []
        if (
            outcome != "PASS"
            and automation_enabled(run)
            and args.stage in AUTO_REVIEW_STATES
            and gate_class(str(definition.get("gate") or "")) == "soft"
            and stage_attempt_evidence(directory, run, args.stage)["window_used"]
            >= int(definition.get("max_attempts", 1))
        ):
            # A soft review gate this run delegates to policy must not become a
            # second manual stop; the voice choice is the only pause. Its
            # bounded repairs are spent, so accept the reviewed artifact and
            # keep the unresolved findings on the receipt as durable notes.
            # Every code-owned gate still blocks: this only applies where the
            # workflow declares the judgment soft and the run assigns it to
            # policy rather than to the operator.
            policy_accepted_findings = list(findings)
            outcome = "PASS"
            findings = []
        policy_review = outcome == "PASS" and automation_enabled(run) and args.stage in AUTO_REVIEW_STATES
        human_review = outcome == "PASS" and args.stage in REVIEW_STATES and not policy_review
        recorded_outcome = "ESCALATE" if human_review else outcome
        review_findings = policy_accepted_findings or findings
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
        repair_destination = effective_repair_state(definition, review_findings)
        preserve_operator_article = editorial_repair_must_preserve_operator_article(
            run,
            args.stage,
            repair_destination,
        )
        gate_receipt_path = write_gate_receipt(
            directory,
            run,
            definition["gate"],
            recorded_outcome,
            review_findings,
            evaluator,
            repair_destination,
            task_state=args.stage,
            task_attempt=attempt,
            task_packet_sha256=packet_hash,
        )
        require_submit_evidence("attempt_evidence_changed_after_gate_receipt")
        if outcome != "PASS":
            if packet_route:
                append_event(directory, run, "MODEL_OUTPUT_REJECTED", "controller", {
                    "state": args.stage,
                    "attempt": attempt,
                    "task_packet_sha256": packet_hash,
                    "route": packet_route,
                    "classification": "content_or_schema_rejection",
                    "route_eligibility_changed": False,
                    "findings": findings,
                })
            repair_context = remember_repair_context(directory, run, args.stage, definition)
            if is_v3_run(run) and repair_context is None:
                block_attempt_reconciliation(
                    directory,
                    run,
                    args.stage,
                    attempt,
                    sha256_path(packet_path),
                    {"reason": "automatic_repair_context_unavailable"},
                )
                raise FlowError(
                    "Automatic repair could not bind the rejected output and gate findings",
                    EXIT_INTEGRITY,
                )
            attempt_evidence = stage_attempt_evidence(directory, run, args.stage)
            attempts_used = attempt_evidence["window_used"]
            maximum = int(definition.get("max_attempts", 1))
            if (
                automation_enabled(run)
                and attempts_used < maximum
                and repair_destination in MODEL_STATES
                and not preserve_operator_article
            ):
                append_event(directory, run, "REPAIR", "controller", {
                    "gate_id": definition["gate"],
                    "source_state": args.stage,
                    "findings": findings,
                    "repair_state": repair_destination,
                    "attempt": attempt_evidence["ordinal"],
                    "attempt_ordinal_baseline": int(run.get("attempts", {}).get(args.stage, 0)),
                    "execution_count_baseline": int(run.get("attempt_baselines", {}).get(str(repair_destination), 0)),
                    "attempts_in_window": attempts_used,
                    "maximum": maximum,
                    "gate_receipt": gate_receipt_path.relative_to(directory).as_posix(),
                    "repair_context": repair_context,
                    "repair_context_required": True,
                    "clear_route_failures": False,
                })
                require_submit_evidence("attempt_evidence_changed_before_repair_transition")
                transition(directory, run, str(repair_destination), "controller", f"Automatic targeted repair after {definition['gate']}")
                require_submit_evidence("attempt_evidence_changed_after_repair_transition")
                payload = {
                    "ok": False,
                    "outcome": outcome,
                    "state": run["state"],
                    "findings": findings,
                    "next_command": ["article-flow", "advance", run["run_id"]],
                }
                emit(payload, args.json)
                return EXIT_OK
            if preserve_operator_article:
                append_event(directory, run, "ESCALATION", "controller", {
                    "state": args.stage,
                    "gate_id": definition["gate"],
                    "reason": "operator_article_requires_scoped_amendment",
                    "findings": findings,
                })
                run["status"] = "BLOCKED"
                save_run(directory, run)
            elif automation_enabled(run) and attempts_used >= maximum:
                block_exhausted_stage(directory, run, args.stage, definition)
            else:
                run["status"] = "BLOCKED"
                save_run(directory, run)
            payload = {"ok": False, "outcome": outcome, "state": run["state"], "findings": findings, "repair_command": ["article-flow", "repair", run["run_id"], definition["gate"]]}
            if preserve_operator_article:
                payload["repair_mode"] = "scoped_operator_amendment"
                payload["amend_command"] = ["article-flow", "amend", run["run_id"], "--article", "REVISED_MARKDOWN_PATH"]
            emit(payload, args.json)
            return EXIT_FAILED
        pending_repair = run.get("pending_repair")
        if isinstance(pending_repair, dict) and pending_repair.get("repair_state") == args.stage:
            run.pop("pending_repair", None)
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
        # An accepted attempt closes this stage's bounded repair window.  The
        # window bounds consecutive repairs of one piece of work, and the
        # baseline is otherwise only advanced for a repair_state, so a stage
        # that repairs to a different stage never had its own baseline moved:
        # POST_EDIT_CLAIM_VERIFICATION and EDITORIAL_QA could each execute only
        # max_attempts times in an entire run, and escalated with zero
        # rejections once the article was rewritten that many times.
        reset_attempt_window(directory, run, args.stage)
        update_writing_provenance(directory, run, args.stage, packet_route)
        require_submit_evidence("attempt_evidence_changed_before_pass_transition")
        if policy_review:
            if policy_accepted_findings:
                append_event(directory, run, "POLICY_APPROVAL", "policy", {
                    "state": args.stage,
                    "gate_id": definition.get("gate"),
                    "reason": "soft_review_window_exhausted",
                    "accepted_findings": policy_accepted_findings,
                })
            approve_review_artifact(directory, run, args.stage, actor="policy")
            require_submit_evidence("attempt_evidence_changed_after_policy_approval")
            transition(directory, run, definition["next_on_pass"], "policy", f"Policy approved validated {args.stage} artifact")
            require_submit_evidence("attempt_evidence_changed_after_pass_transition")
            payload = {"ok": True, "outcome": "PASS", "state": run["state"], "next_command": ["article-flow", "advance", run["run_id"]]}
        elif args.stage in REVIEW_STATES:
            require_submit_evidence("attempt_evidence_changed_before_review_hold")
            run["status"] = "WAITING_HUMAN"
            save_run(directory, run)
            require_submit_evidence("attempt_evidence_changed_after_review_hold")
            payload = next_state_payload(directory, run)
        else:
            require_submit_evidence("attempt_evidence_changed_before_pass_transition")
            transition(directory, run, definition["next_on_pass"], "controller", f"{definition['gate']} passed")
            require_submit_evidence("attempt_evidence_changed_after_pass_transition")
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
        if is_v3_run(run) and run["state"] == "VOICE_PROBE":
            # A durable selection plus its passing receipt is the human's
            # committed decision.  Retrying it must finish the interrupted
            # transition rather than re-approve a probe that now carries the
            # choice, and a conflicting retry must fail closed.
            reconciled = reconcile_committed_voice_selection(directory, run, args)
            if reconciled is not None:
                emit(reconciled, args.json)
                return EXIT_OK
        findings = []
        if args.finding:
            findings.append({"criterion": "operator_review", "artifact": args.artifact or "current", "location": None, "finding": args.finding, "repair_instruction": args.finding})
        elif args.outcome == "REPAIR":
            findings.append({
                "criterion": "operator_requested_repair",
                "artifact": args.artifact or "current",
                "location": None,
                "finding": "The operator requested a bounded repair without adding a passage-specific finding.",
                "repair_instruction": "Re-evaluate the current artifact against every criterion of this gate and repair only the failing content.",
            })
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
            voice_gate = run["state"] == "VOICE_PROBE" and is_v3_run(run)
            recorded_item: dict[str, Any] | None = None
            recorded_path: Path | None = None
            if voice_gate:
                # The candidate authority is the three-candidate probe, which
                # may already have been superseded on the ``voice-probe`` type
                # by an approved copy from an interrupted decision.
                recorded_item, recorded_path = voice_candidate_probe(directory, run)
                if recorded_item is None or recorded_path is None:
                    # Fall back to the recorded probe so a tampered or missing
                    # artifact is reported by the precise check below instead
                    # of as a generic missing candidate.
                    recorded_item = artifact(run, candidate_type)
                    recorded_path = artifact_path(directory, run, candidate_type)
            default_path = recorded_path if voice_gate else artifact_path(directory, run, candidate_type)
            candidate_path = Path(args.artifact).resolve() if args.artifact else default_path
            if not candidate_path or not candidate_path.is_file():
                raise FlowError(f"Candidate artifact is missing for {run['state']}")
            if voice_gate:
                if not recorded_item or not recorded_path or candidate_path.resolve() != recorded_path.resolve():
                    raise FlowError("Voice selection must use the controller-recorded probe artifact", EXIT_APPROVAL)
                if sha256_path(recorded_path) != recorded_item.get("sha256"):
                    raise FlowError("Recorded voice probe changed after validation", EXIT_INTEGRITY)
                probe_outcome, probe_findings = automatic_gate(directory, run, "VOICE_PROBE", recorded_path)
                if probe_outcome != "PASS":
                    raise FlowError("Recorded voice probe no longer passes its code-owned checks", EXIT_INTEGRITY, probe_findings)
                preserve_voice_candidate_probe(directory, run, recorded_item, recorded_path)
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
            source_state = run["state"]
            repair_context = remember_repair_context(directory, run, source_state, definition)
            context_required = bool(
                is_v3_run(run)
                and (
                    repair_context is not None
                    or rejected_attempt_requires_repair_context(
                        directory,
                        run,
                        source_state,
                        str(args.gate_id),
                    )
                )
            )
            if context_required and repair_context is None:
                run["status"] = "BLOCKED"
                save_run(directory, run)
                raise FlowError(
                    "Operator repair could not bind the rejected artifact and gate receipt",
                    EXIT_INTEGRITY,
                )
            baseline = reset_attempt_window(directory, run, repair_state)
            execution_baseline = int(run.get("attempt_baselines", {}).get(repair_state, 0))
            repair_event_source_state = str(
                repair_context.get("source_stage")
                if isinstance(repair_context, dict)
                else source_state
            )
            append_event(directory, run, "REPAIR", "operator", {
                "gate_id": args.gate_id,
                "finding": args.finding,
                "source_state": repair_event_source_state,
                "repair_state": repair_state,
                "attempt_ordinal_baseline": baseline,
                "execution_count_baseline": execution_baseline,
                "repair_context": repair_context,
                "repair_context_required": context_required,
                "clear_route_failures": True,
            })
            run.setdefault("route_failures", {}).pop(repair_state, None)
            transition(directory, run, repair_state, "operator", (args.finding or "Operator requested repair") + f"; next bounded window begins after attempt {baseline}")
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
        definition = state_definition(run["state"], run)
        if args.gate_id != definition.get("gate"):
            raise FlowError(f"Gate {args.gate_id} no longer controls current state {run['state']}", EXIT_WAITING)
        # Authorize another window where the rejected findings actually point.
        # Routing an operator repair by the stage declaration alone would send
        # a malformed ledger back to rewrite the article, and would reset that
        # stage's window instead of the one that is exhausted.
        recorded_receipt = json_artifact(directory, run, f"gate-receipt:{args.gate_id}") or {}
        repair_state = str(
            effective_repair_state(definition, recorded_receipt.get("findings") or []) or ""
        )
        source_state = run["state"]
        repair_context = remember_repair_context(directory, run, source_state, definition)
        context_required = bool(
            is_v3_run(run)
            and (
                repair_context is not None
                or rejected_attempt_requires_repair_context(
                    directory,
                    run,
                    source_state,
                    str(args.gate_id),
                )
            )
        )
        if context_required and repair_context is None:
            run["status"] = "BLOCKED"
            save_run(directory, run)
            raise FlowError(
                "Repair authorization could not bind the rejected artifact and gate receipt",
                EXIT_INTEGRITY,
            )
        baseline = reset_attempt_window(directory, run, repair_state)
        execution_baseline = int(run.get("attempt_baselines", {}).get(repair_state, 0))
        repair_event_source_state = str(
            repair_context.get("source_stage")
            if isinstance(repair_context, dict)
            else source_state
        )
        append_event(directory, run, "REPAIR", "operator_or_controller", {
            "gate_id": args.gate_id,
            "finding": args.finding,
            "source_state": repair_event_source_state,
            "repair_state": repair_state,
            "attempt_ordinal_baseline": baseline,
            "execution_count_baseline": execution_baseline,
            "repair_context": repair_context,
            "repair_context_required": context_required,
            "clear_route_failures": True,
        })
        run.setdefault("route_failures", {}).pop(repair_state, None)
        transition(directory, run, repair_state, "controller", (args.finding or f"Repair requested by {args.gate_id}") + f"; next bounded window begins after attempt {baseline}")
    emit({"ok": True, "state": run["state"], "next_command": ["article-flow", "next", run["run_id"]]}, args.json)
    return EXIT_OK


def _svg_text(value: str) -> str:
    return html.escape(re.sub(r"\s+", " ", value).strip(), quote=True)


def _svg_wrapped_text(value: str, *, x: int, y: int, width: int, line_height: int = 24, css_class: str = "label") -> str:
    lines = textwrap.wrap(re.sub(r"\s+", " ", value).strip(), width=max(12, width)) or [""]
    spans = "".join(
        f'<tspan x="{x}" dy="{0 if index == 0 else line_height}">{_svg_text(line)}</tspan>'
        for index, line in enumerate(lines[:3])
    )
    return f'<text x="{x}" y="{y}" class="{css_class}">{spans}</text>'


def render_visual_svg(visual: dict[str, Any]) -> bytes:
    """Render one schema-limited visual without accepting model-authored markup."""
    kind = str(visual["kind"])
    title = _svg_text(str(visual["title"]))
    alt = _svg_text(str(visual["alt_text"]))
    labels = [str(item) for item in visual.get("labels", [])]
    style = """
      .bg{fill:#0b1020}.panel{fill:#121a2d;stroke:#33415f;stroke-width:2}.muted{fill:#95a3bd}
      .title{fill:#f8fafc;font:700 30px system-ui,sans-serif}.label{fill:#e8edf7;font:500 19px system-ui,sans-serif}
      .small{fill:#aebbd0;font:500 16px system-ui,sans-serif}.accent{fill:#7dd3fc}.warm{fill:#fbbf24}
      .line-a{fill:none;stroke:#7dd3fc;stroke-width:7;stroke-linecap:round}.line-b{fill:none;stroke:#fbbf24;stroke-width:7;stroke-linecap:round}
      .arrow{fill:none;stroke:#71819d;stroke-width:3;marker-end:url(#arrow)}
    """
    defs = '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#71819d"/></marker></defs>'
    elements = [f'<rect class="bg" width="1000" height="560" rx="28"/>', f'<text x="60" y="66" class="title">{title}</text>']
    if kind == "console_reconstruction":
        elements.extend([
            '<rect x="55" y="96" width="890" height="410" rx="18" class="panel"/>',
            '<circle cx="88" cy="126" r="7" fill="#fb7185"/><circle cx="112" cy="126" r="7" fill="#fbbf24"/><circle cx="136" cy="126" r="7" fill="#4ade80"/>',
            '<text x="830" y="132" class="small">RECONSTRUCTION</text>',
        ])
        count = min(7, len(labels))
        compact = count >= 6
        y = 174 if compact else 186
        row_step = 50 if compact else 66
        radius = 14 if compact else 17
        line_height = 18 if compact else 21
        for index, label in enumerate(labels[:7], start=1):
            elements.append(f'<circle cx="98" cy="{y - 7}" r="{radius}" fill="#24324d"/><text x="92" y="{y}" class="small">{index}</text>')
            elements.append(_svg_wrapped_text(label, x=135, y=y, width=70, line_height=line_height))
            y += row_step
    elif kind == "trend_gap":
        first = _svg_text(labels[0] if labels else "Model capability")
        second = _svg_text(labels[1] if len(labels) > 1 else "Product default")
        elements.extend([
            '<line x1="100" y1="465" x2="910" y2="465" class="arrow"/>',
            '<line x1="100" y1="465" x2="100" y2="120" class="arrow"/>',
            '<path d="M130 420 C320 390, 420 325, 555 260 S780 150, 885 125" class="line-a"/>',
            '<path d="M130 382 C360 378, 650 374, 885 370" class="line-b"/>',
            f'<circle cx="720" cy="176" r="7" class="accent"/><text x="738" y="181" class="label">{first}</text>',
            f'<circle cx="720" cy="372" r="7" class="warm"/><text x="738" y="378" class="label">{second}</text>',
            '<text x="858" y="507" class="small">Time</text><text x="30" y="120" class="small" transform="rotate(-90 30 120)">Capability used</text>',
            '<line x1="620" y1="270" x2="620" y2="365" stroke="#a78bfa" stroke-width="3" stroke-dasharray="8 8"/>',
            '<text x="640" y="320" class="small">integration gap</text>',
        ])
    elif kind == "delivery_loop":
        count = min(6, len(labels))
        card_width = 128 if count == 6 else 150 if count == 5 else 180
        gap = 18 if count == 6 else 22
        total = count * card_width + max(0, count - 1) * gap
        start = max(45, (1000 - total) // 2)
        for index, label in enumerate(labels[:6]):
            x = start + index * (card_width + gap)
            elements.append(f'<rect x="{x}" y="185" width="{card_width}" height="150" rx="16" class="panel"/>')
            elements.append(f'<text x="{x + 18}" y="218" class="small">0{index + 1}</text>')
            elements.append(_svg_wrapped_text(label, x=x + 18, y=255, width=12 if count == 6 else 15, line_height=23))
            if index < count - 1:
                elements.append(f'<line x1="{x + card_width + 4}" y1="260" x2="{x + card_width + gap - 4}" y2="260" class="arrow"/>')
        if count:
            last_x = start + (count - 1) * (card_width + gap) + card_width // 2
            first_x = start + card_width // 2
            elements.append(f'<path d="M{last_x} 350 C{last_x} 455,{first_x} 455,{first_x} 350" class="arrow"/>')
            elements.append('<text x="420" y="445" class="small">telemetry starts the next review</text>')
    else:
        raise FlowError(f"Unsupported deterministic visual kind: {kind}", EXIT_INTEGRITY)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 560" role="img" aria-labelledby="title desc">'
        f'<title id="title">{title}</title><desc id="desc">{alt}</desc>{defs}<style>{style}</style>'
        + "".join(elements)
        + "</svg>\n"
    )
    return svg.encode("utf-8")


def validate_visual_manifest(directory: Path, run: dict[str, Any], manifest_path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for error in validate_json_schema(manifest_path, "visual-manifest.schema.json"):
        findings.append({"criterion": "schema", "artifact": str(manifest_path), "location": None, "finding": error, "repair_instruction": "Re-render the validated visual plan."})
    if findings:
        return findings
    value = load_json(manifest_path)
    plan_path = artifact_path(directory, run, "visual-plan")
    if not plan_path or value.get("visual_plan_sha256") != sha256_path(plan_path):
        findings.append({"criterion": "visual_plan_binding", "artifact": str(manifest_path), "location": "visual_plan_sha256", "finding": "Manifest is not bound to the approved visual plan.", "repair_instruction": "Render from the current plan."})
    for item in value.get("assets", []):
        source = directory / safe_relative(str(item.get("source_path") or ""))
        if not source.is_file() or sha256_path(source) != item.get("sha256") or source.stat().st_size != item.get("byte_size"):
            findings.append({"criterion": "visual_asset_hash", "artifact": str(source), "location": str(item.get("visual_id")), "finding": "Rendered asset is missing or does not match its manifest.", "repair_instruction": "Re-render the deterministic asset."})
    return findings


def strip_planned_visual_blocks(markdown: str, manifest: dict[str, Any]) -> str:
    """Remove model-authored image placeholders in controller-owned sections."""
    lines = markdown.splitlines()
    planned_headings = {
        re.sub(r"\s+", " ", str((asset.get("placement") or {}).get("after_heading") or "")).strip().casefold()
        for asset in manifest.get("assets", [])
        if isinstance(asset, dict)
    }
    remove: set[int] = set()
    for index, line in enumerate(lines):
        heading = re.match(r"^(#{2,6})\s+(.+?)\s*$", line)
        if not heading:
            continue
        normalized = re.sub(r"\s+", " ", heading.group(2)).strip().casefold()
        if normalized not in planned_headings:
            continue
        end = next(
            (candidate for candidate in range(index + 1, len(lines)) if re.match(r"^#{2,6}\s+", lines[candidate])),
            len(lines),
        )
        for image_index in range(index + 1, end):
            if not re.fullmatch(r"\s*!\[[^\]\n]*\]\([^)\n]+\)\s*", lines[image_index]):
                continue
            remove.add(image_index)
            previous = next((item for item in range(image_index - 1, index, -1) if lines[item].strip()), None)
            following = next((item for item in range(image_index + 1, end) if lines[item].strip()), None)
            if previous is not None and re.fullmatch(r"\s*\*\*[^*\n]+\*\*\s*", lines[previous]):
                remove.add(previous)
            if following is not None and re.fullmatch(r"\s*\*[^*\n]+\*\s*", lines[following]):
                remove.add(following)
    cleaned = "\n".join(line for index, line in enumerate(lines) if index not in remove)
    return re.sub(r"\n{3,}", "\n\n", cleaned).rstrip() + "\n"


def materialize_manifest_visuals_markdown(markdown: str, manifest: dict[str, Any]) -> str:
    """Replace draft placeholders with the exact hash-bound public visual references."""
    cleaned = strip_planned_visual_blocks(markdown, manifest)
    assets_by_heading: dict[str, list[dict[str, Any]]] = {}
    for asset in manifest.get("assets", []):
        if not isinstance(asset, dict):
            continue
        heading = re.sub(r"\s+", " ", str((asset.get("placement") or {}).get("after_heading") or "")).strip().casefold()
        assets_by_heading.setdefault(heading, []).append(asset)
    seen = {heading: 0 for heading in assets_by_heading}
    output: list[str] = []
    for line in cleaned.splitlines():
        output.append(line)
        match = re.match(r"^#{2,6}\s+(.+?)\s*$", line)
        if not match:
            continue
        heading = re.sub(r"\s+", " ", match.group(1)).strip().casefold()
        if heading not in assets_by_heading:
            continue
        seen[heading] += 1
        output.append("")
        for asset in assets_by_heading[heading]:
            alt = str(asset["alt_text"]).replace("]", "\\]")
            output.append(f"![{alt}]({asset['public_path']})")
            output.append("")
            output.append(f"*{asset['caption']}*")
            output.append("")
    missing = [heading for heading, count in seen.items() if count != 1]
    if missing:
        raise FlowError(
            "Rendered visuals could not be materialized at exactly one Markdown heading",
            EXIT_INTEGRITY,
            {"headings": missing},
        )
    return re.sub(r"\n{3,}", "\n\n", "\n".join(output)).rstrip() + "\n"


def command_visual_render(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    refresh = bool(getattr(args, "refresh", False))
    if run["state"] != "VISUAL_RENDER" and not (refresh and run["state"] == "PUBLISH_APPROVAL"):
        suffix = " or --refresh from PUBLISH_APPROVAL" if refresh else ""
        raise FlowError(f"Visual rendering requires VISUAL_RENDER{suffix}, current state is {run['state']}")
    with run_lock(directory, run):
        refresh = bool(getattr(args, "refresh", False)) and run["state"] == "PUBLISH_APPROVAL"
        plan_path = artifact_path(directory, run, "visual-plan")
        if not plan_path:
            raise FlowError("Approved visual plan is missing", EXIT_INTEGRITY)
        plan = load_json(plan_path)
        plan_errors = validate_json_schema(plan_path, "visual-plan.schema.json")
        if plan_errors:
            raise FlowError("Visual plan is invalid", EXIT_INTEGRITY, plan_errors)
        slug = package_metadata_slug(directory, run)
        plan_hash = sha256_path(plan_path)
        source_draft_item = artifact(run, "draft") if not refresh else None
        source_draft_path = artifact_path(directory, run, "draft") if not refresh else None
        if not refresh and (not source_draft_item or not source_draft_path):
            raise FlowError("Visual rendering requires the accepted rough draft", EXIT_INTEGRITY)
        prior_manifest_item = artifact(run, "visual-manifest")
        assets: list[dict[str, Any]] = []
        visuals_root = directory / "artifacts" / "visuals"
        visuals_root.mkdir(parents=True, exist_ok=True)
        for visual in plan.get("visuals", []):
            visual_id = str(visual["visual_id"])
            data = render_visual_svg(visual)
            data_hash = sha256_bytes(data)
            path = visuals_root / f"{visual_id}-{plan_hash[:8]}-{data_hash[:8]}.svg"
            immutable_write(path, data)
            record_artifact(directory, run, path, f"visual-asset:{visual_id}", {"actor": "controller", "version": CONTROLLER_VERSION, "renderer": "deterministic-svg-v2"}, expected_bytes=data)
            assets.append({
                "visual_id": visual_id,
                "kind": visual["kind"],
                "source_path": path.relative_to(directory).as_posix(),
                "public_path": f"/assets/articles/{slug}/{visual_id}.svg",
                "sha256": data_hash,
                "byte_size": len(data),
                "title": visual["title"],
                "alt_text": visual["alt_text"],
                "caption": visual["caption"],
                "placement": visual["placement"],
                "claim_ids": visual.get("claim_ids", []),
            })
        manifest = {
            "visual_manifest_schema_version": "1.0.0",
            "run_id": run["run_id"],
            "visual_plan_sha256": plan_hash,
            "assets": assets,
        }
        manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        manifest_hash = sha256_bytes(manifest_bytes)
        manifest_path = directory / "artifacts" / f"visual-manifest-{plan_hash[:8]}-{manifest_hash[:8]}.json"
        immutable_write(manifest_path, manifest_bytes)
        findings = validate_visual_manifest(directory, run, manifest_path)
        if findings:
            write_gate_receipt(directory, run, "G-VISUAL-RENDER", "REPAIR", findings, {"type": "code", "version": CONTROLLER_VERSION}, "VISUAL_PLAN")
            raise FlowError("Deterministic visual rendering failed", EXIT_INTEGRITY, findings)
        manifest_item = record_artifact(directory, run, manifest_path, "visual-manifest", {"actor": "controller", "version": CONTROLLER_VERSION, "renderer": "deterministic-svg-v2"}, inputs=[artifact(run, "visual-plan")["artifact_id"]] if artifact(run, "visual-plan") else [], expected_bytes=manifest_bytes)
        if refresh:
            write_gate_receipt(directory, run, "G-VISUAL-RENDER", "PASS", [], {"type": "code", "version": CONTROLLER_VERSION})
            append_event(directory, run, "VISUALS_REFRESHED", "controller", {
                "visual_plan_sha256": plan_hash,
                "prior_manifest_sha256": prior_manifest_item.get("sha256") if prior_manifest_item else None,
                "manifest_sha256": manifest_item["sha256"],
                "asset_sha256s": {item["visual_id"]: item["sha256"] for item in assets},
            })
            transition(directory, run, "PACKAGE", "controller", "Held publication visuals refreshed from the unchanged approved plan")
            emit({"ok": True, "state": run["state"], "manifest": str(manifest_path), "assets": assets, "next_command": ["article-flow", "package", run["run_id"]]}, args.json)
            return EXIT_OK
        assert source_draft_path is not None and source_draft_item is not None
        visualized_draft = materialize_manifest_visuals_markdown(
            source_draft_path.read_text(encoding="utf-8"),
            manifest,
        )
        visualized_draft_path = directory / "artifacts" / f"visualized-draft-{plan_hash[:8]}.md"
        visualized_bytes = visualized_draft.encode("utf-8")
        immutable_write(visualized_draft_path, visualized_bytes)
        record_artifact(
            directory,
            run,
            visualized_draft_path,
            "draft",
            {"actor": "controller", "version": CONTROLLER_VERSION, "renderer": "manifest-markdown-v1"},
            inputs=[source_draft_item["artifact_id"], manifest_item["artifact_id"]],
            expected_bytes=visualized_bytes,
        )
        write_gate_receipt(directory, run, "G-VISUAL-RENDER", "PASS", [], {"type": "code", "version": CONTROLLER_VERSION})
        transition(directory, run, "CLAIM_VERIFICATION", "controller", "Visual assets rendered and hash-bound to their plan")
    emit({"ok": True, "state": run["state"], "manifest": str(manifest_path), "assets": assets, "next_command": ["article-flow", "advance", run["run_id"]]}, args.json)
    return EXIT_OK


def package_metadata_slug(directory: Path, run: dict[str, Any]) -> str:
    brief = json_artifact(directory, run, "brief") or {}
    revision = run.get("revision") if isinstance(run.get("revision"), dict) else {}
    return slugify(str(revision.get("slug") or brief.get("slug") or brief.get("title") or "untitled-article"), 80)


def markdown_inline(value: str) -> str:
    placeholders: dict[str, str] = {}
    def hold(rendered: str) -> str:
        key = f"@@AF{len(placeholders)}@@"
        placeholders[key] = rendered
        return key
    # Decode entities to characters before escaping. This renders legitimate
    # Markdown entities such as &nbsp; once, while encoded HTML remains text.
    value = html.unescape(value)
    def safe_target(raw: str) -> str | None:
        target = raw.strip()
        parsed = urllib.parse.urlparse(target)
        if parsed.scheme and parsed.scheme not in {"http", "https", "mailto"}:
            return None
        if target.startswith("//"):
            return None
        return html.escape(target, quote=True)
    def image_replacement(match: re.Match[str]) -> str:
        target = safe_target(match.group(2))
        alt = html.escape(match.group(1), quote=True)
        if target is None:
            return alt
        title = f' title="{html.escape(match.group(3), quote=True)}"' if match.group(3) else ""
        return hold(f'<img src="{target}" alt="{alt}" loading="lazy" decoding="async"{title}>')
    def link_replacement(match: re.Match[str]) -> str:
        target = safe_target(match.group(2))
        label = html.escape(match.group(1))
        return hold(f'<a href="{target}">{label}</a>') if target is not None else label
    value = re.sub(r"`([^`]+)`", lambda match: hold(f"<code>{html.escape(match.group(1))}</code>"), value)
    value = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)", image_replacement, value)
    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_replacement, value)
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
            rendered: list[str] = []
            for item in paragraph:
                hard_break = item.endswith("  ")
                rendered.append(markdown_inline(item.rstrip()))
                rendered.append("<br>\n" if hard_break else " ")
            output.append(f"<p>{''.join(rendered).rstrip()}</p>")
            paragraph.clear()
    def close_list() -> None:
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = None
    index = 0
    while index < len(lines):
        line = lines[index]
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
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
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
            index += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            if level == 1 and not output:
                index += 1
                continue
            output.append(f"<h{level}>{markdown_inline(heading.group(2))}</h{level}>")
            index += 1
            continue
        if (
            "|" in line
            and index + 1 < len(lines)
            and re.match(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", lines[index + 1])
        ):
            flush_paragraph()
            close_list()
            headers = [cell.strip() for cell in line.strip().strip("|").split("|")]
            output.append(
                f'<div class="article-table-wrap" data-column-count="{len(headers)}"><table><thead><tr>'
            )
            output.extend(f"<th>{markdown_inline(cell)}</th>" for cell in headers)
            output.append("</tr></thead><tbody>")
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if len(cells) != len(headers):
                    break
                output.append("<tr>" + "".join(f"<td>{markdown_inline(cell)}</td>" for cell in cells) + "</tr>")
                index += 1
            output.append("</tbody></table></div>")
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
            index += 1
            continue
        if line.startswith("> "):
            flush_paragraph()
            close_list()
            output.append(f"<blockquote><p>{markdown_inline(line[2:])}</p></blockquote>")
            index += 1
            continue
        if not line.strip():
            flush_paragraph()
            close_list()
        else:
            paragraph.append(line)
        index += 1
    flush_paragraph()
    close_list()
    if in_code:
        output.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(output)


def package_metadata(directory: Path, run: dict[str, Any]) -> dict[str, Any]:
    brief = json_artifact(directory, run, "brief") or {}
    recipe = json_artifact(directory, run, "article-recipe") or {}
    title = str(brief.get("title") or "Untitled article")
    revision = run.get("revision") if isinstance(run.get("revision"), dict) else {}
    slug = slugify(str(revision.get("slug") or brief.get("slug") or title), 80)
    date_value = str(revision.get("original_published_date") or brief.get("date") or dt.date.today().isoformat())
    modified_value = utc_now() if revision else (date_value if "T" in date_value else f"{date_value}T12:00:00-05:00")
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
        "modified_date": modified_value[:10],
        "modified_date_iso": modified_value,
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
        "revision_mode": "replace_in_place" if revision else "new",
        "source_run_id": revision.get("source_run_id"),
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


def replace_existing_article_card(content: str, slug: str, replacement: str) -> str:
    pattern = re.compile(
        rf'<article\b(?=[^>]*\bdata-article-flow-slug="{re.escape(slug)}")[^>]*>.*?</article>',
        flags=re.DOTALL,
    )
    matches = list(pattern.finditer(content))
    if len(matches) != 1:
        raise FlowError(f"Expected exactly one existing card for same-URL revision {slug}; found {len(matches)}")
    old = matches[0].group(0)
    if "article-card--featured" not in old:
        replacement = replacement.replace("article-card article-card--featured", "article-card")
        replacement = re.sub(r'\s*<span class="article-card__badge">Latest</span>', "", replacement)
    return content[:matches[0].start()] + replacement + content[matches[0].end():]


def replace_existing_feed_item(content: str, canonical: str, replacement: str) -> str:
    pattern = re.compile(r"<item>.*?</item>", flags=re.DOTALL)
    matches = [match for match in pattern.finditer(content) if canonical in match.group(0)]
    if len(matches) != 1:
        raise FlowError(f"Expected exactly one existing feed item for same-URL revision; found {len(matches)}")
    match = matches[0]
    return content[:match.start()] + replacement + content[match.end():]


def replace_existing_sitemap_item(content: str, canonical: str, replacement: str) -> str:
    pattern = re.compile(r"<url>.*?</url>", flags=re.DOTALL)
    matches = [match for match in pattern.finditer(content) if canonical in match.group(0)]
    if len(matches) != 1:
        raise FlowError(f"Expected exactly one existing sitemap entry for same-URL revision; found {len(matches)}")
    match = matches[0]
    return content[:match.start()] + replacement.strip() + content[match.end():]


def inject_manifest_visuals(directory: Path, run: dict[str, Any], body: str) -> str:
    manifest_path = artifact_path(directory, run, "visual-manifest")
    if not manifest_path:
        return body
    findings = validate_visual_manifest(directory, run, manifest_path)
    if findings:
        raise FlowError("Visual manifest failed before publication rendering", EXIT_INTEGRITY, findings)
    manifest = load_json(manifest_path)
    rendered = body
    for asset in manifest.get("assets", []):
        heading = str((asset.get("placement") or {}).get("after_heading") or "")
        heading_html = markdown_inline(heading)
        pattern = re.compile(rf"(<h([2-6])>{re.escape(heading_html)}</h\2>)")
        figure = (
            f'<figure class="article-visual" data-visual-id="{html.escape(str(asset["visual_id"]), quote=True)}" '
            f'data-asset-sha256="{html.escape(str(asset["sha256"]), quote=True)}">'
            f'<img src="{html.escape(str(asset["public_path"]), quote=True)}" alt="{html.escape(str(asset["alt_text"]), quote=True)}" '
            'loading="lazy" decoding="async">'
            f'<figcaption><strong>{html.escape(str(asset["title"]))}.</strong> {html.escape(str(asset["caption"]))}</figcaption>'
            '</figure>'
        )
        rendered, count = pattern.subn(rf"\1\n{figure}", rendered, count=1)
        if count != 1:
            raise FlowError(f"Visual {asset['visual_id']} could not be placed after heading {heading!r}", EXIT_INTEGRITY)
    return rendered


def render_publication_files(directory: Path, run: dict[str, Any], package_root: Path, metadata: dict[str, Any]) -> list[Path]:
    article_path = artifact_path(directory, run, "article")
    if not article_path:
        raise FlowError("Approved article artifact is missing")
    target = load_json(SPEC_ROOT / "publication" / "theproductiveprompter.json")
    repository = publication_repo_root(required=True)
    template = (SPEC_ROOT / target["article_template"]).read_text(encoding="utf-8")
    packaged_article_path = package_root / "public" / "article.md"
    revision_article_path = packaged_article_path if packaged_article_path.is_file() else article_path
    article_markdown = revision_article_path.read_text(encoding="utf-8")
    manifest_path = artifact_path(directory, run, "visual-manifest")
    if manifest_path:
        article_markdown = strip_planned_visual_blocks(article_markdown, load_json(manifest_path))
    body = inject_manifest_visuals(directory, run, markdown_to_html(article_markdown))
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
    words = len(re.findall(r"\b\w+\b", article_markdown))
    reading_minutes = max(1, round(words / 230))
    replacements = {
        "{{TITLE}}": html.escape(metadata["title"]),
        "{{DESCRIPTION}}": html.escape(metadata["description"], quote=True),
        "{{CANONICAL_URL}}": html.escape(canonical, quote=True),
        "{{DATE_ISO}}": html.escape(metadata["date_iso"], quote=True),
        "{{MODIFIED_DATE_ISO}}": html.escape(str(metadata.get("modified_date_iso") or metadata["date_iso"]), quote=True),
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
        "{{ARTICLE_REVISION}}": sha256_path(revision_article_path),
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
    site_root.mkdir(parents=True, exist_ok=True)
    # Article figures and table wrappers rely on the release stylesheet. Keep
    # that exact reviewed byte set in the publication plan with the article.
    shutil.copy2(REPO_ROOT / "styles.css", site_root / "styles.css")
    manifest_path = artifact_path(directory, run, "visual-manifest")
    if manifest_path:
        for asset in load_json(manifest_path).get("assets", []):
            source = directory / safe_relative(str(asset["source_path"]))
            destination = site_root / str(asset["public_path"]).lstrip("/")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
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
        source_text = source.read_text(encoding="utf-8")
        if metadata.get("revision_mode") == "replace_in_place":
            updated = replace_existing_article_card(source_text, metadata["slug"], replacement)
        else:
            updated = prepend_marked(
                source_text,
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
    feed_updated = (
        replace_existing_feed_item(feed_source, canonical, feed_item)
        if metadata.get("revision_mode") == "replace_in_place"
        else prepend_marked(feed_source, "<!-- ARTICLE_FLOW_FEED_START -->", "<!-- ARTICLE_FLOW_FEED_END -->", feed_item, unique_token=canonical)
    )
    feed_updated = re.sub(
        r"<lastBuildDate>.*?</lastBuildDate>",
        f"<lastBuildDate>{dt.datetime.fromisoformat(metadata.get('modified_date_iso') or metadata['date_iso']).strftime('%a, %d %b %Y %H:%M:%S %z')}</lastBuildDate>",
        feed_updated,
        count=1,
    )
    feed_output = site_root / target["feed_file"]
    atomic_write(feed_output, feed_updated.encode("utf-8"))
    sitemap_source = (repository / target["sitemap_file"]).read_text(encoding="utf-8")
    sitemap_item = f"  <url>\n    <loc>{canonical}</loc>\n    <lastmod>{metadata.get('modified_date') or metadata['date'][:10]}</lastmod>\n  </url>"
    sitemap_updated = (
        replace_existing_sitemap_item(sitemap_source, canonical, sitemap_item)
        if metadata.get("revision_mode") == "replace_in_place"
        else prepend_marked(sitemap_source, "<!-- ARTICLE_FLOW_SITEMAP_START -->", "<!-- ARTICLE_FLOW_SITEMAP_END -->", sitemap_item, unique_token=canonical)
    )
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
        workflow_parts = str(metadata.get("workflow_version", "0.0")).split(".")
        try:
            visuals_required = (int(workflow_parts[0]), int(workflow_parts[1])) >= (3, 1)
        except (IndexError, ValueError):
            visuals_required = False
        if visuals_required:
            assets_path = public_root / "assets.json"
            try:
                asset_manifest = load_json(assets_path)
            except FlowError as exc:
                findings.append({"criterion": "visual_manifest", "path": str(assets_path), "finding": str(exc)})
                asset_manifest = {"assets": []}
            assets = [item for item in asset_manifest.get("assets", []) if isinstance(item, dict)]
            if not assets:
                findings.append({"criterion": "required_visual", "path": str(article_html), "finding": "Workflow 3.1 article has no rendered visuals."})
            for asset in assets:
                visual_id = str(asset.get("visual_id") or "")
                public_target = site_root / str(asset.get("public_path") or "").lstrip("/")
                if not public_target.is_file() or sha256_path(public_target) != asset.get("sha256"):
                    findings.append({"criterion": "visual_asset_hash", "path": str(public_target), "finding": f"Visual {visual_id} is missing or has the wrong hash."})
                required_figure_bits = [
                    f'data-visual-id="{html.escape(visual_id, quote=True)}"',
                    f'data-asset-sha256="{asset.get("sha256")}"',
                    f'alt="{html.escape(str(asset.get("alt_text") or ""), quote=True)}"',
                    f'<figcaption><strong>{html.escape(str(asset.get("title") or ""))}.',
                ]
                if any(bit not in text for bit in required_figure_bits):
                    findings.append({"criterion": "visual_figure_binding", "path": str(article_html), "finding": f"Visual {visual_id} is not rendered with its bound hash, alt text, title, and caption."})
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
    article_argument = getattr(args, "article", None)
    if args.title is None and args.description is None and article_argument is None:
        raise FlowError("Amend requires --title, --description, and/or --article", EXIT_USAGE)
    if article_argument is not None and run["state"] not in ARTICLE_AMENDABLE_STATES:
        raise FlowError(
            f"Amending the article requires EDITORIAL_QA, PACKAGE, or PUBLISH_APPROVAL, current state is {run['state']}"
        )
    if (args.title is not None or args.description is not None) and run["state"] not in DISPLAY_TEXT_AMENDABLE_STATES:
        raise FlowError(
            f"Amending public display text requires an article under review, current state is {run['state']}"
        )
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
        elif changed and run["state"] == "PUBLISH_APPROVAL":
            transition(directory, run, "PACKAGE", "operator", "Public display text changed; rebuild the package")
        else:
            # Before packaging the amended brief is simply read when the
            # package is built, so the run stays where it is.  Advancing to
            # PACKAGE from here would skip the very gate that asked for the
            # change, including editorial QA.
            save_run(directory, run)
    if run["state"] == "POST_EDIT_CLAIM_VERIFICATION":
        next_command = ["article-flow", "next", run["run_id"]]
    elif run["state"] == "PACKAGE":
        next_command = ["article-flow", "package", run["run_id"]]
    elif run["state"] == "PUBLISH_APPROVAL":
        next_command = ["article-flow", "publish", "--plan", run["run_id"]]
    else:
        next_command = ["article-flow", "advance", run["run_id"]]
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
        visual_manifest_path = artifact_path(directory, run, "visual-manifest")
        visual_manifest: dict[str, Any] | None = None
        public_article_text = article_path.read_text(encoding="utf-8")
        if is_v31_run(run):
            if not visual_manifest_path:
                raise FlowError("Workflow 3.1 packaging requires a rendered visual manifest", EXIT_INTEGRITY)
            visual_findings = validate_visual_manifest(directory, run, visual_manifest_path)
            if visual_findings:
                raise FlowError("Workflow 3.1 visual manifest is invalid", EXIT_INTEGRITY, visual_findings)
            visual_manifest = load_json(visual_manifest_path)
            public_article_text = materialize_manifest_visuals_markdown(public_article_text, visual_manifest)
        atomic_write(public_root / "article.md", public_article_text.encode("utf-8"))
        metadata = package_metadata(directory, run)
        write_json(public_root / "metadata.json", metadata)
        claim_path = artifact_path(directory, run, "post-edit-claim-ledger") or artifact_path(directory, run, "verified-claim-ledger")
        references = {"sources": []}
        if claim_path:
            ledger = load_json(claim_path)
            references["sources"] = sorted({claim.get("source_url_or_local_id") for claim in ledger.get("claims", []) if claim.get("source_url_or_local_id")})
        write_json(public_root / "references.json", references)
        if is_v31_run(run):
            assert visual_manifest is not None
            for asset in visual_manifest.get("assets", []):
                source = directory / safe_relative(str(asset["source_path"]))
                destination = public_root / "assets" / f"{asset['visual_id']}.svg"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            write_json(public_root / "assets.json", visual_manifest)
        else:
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


def normalize_git_remote_url(value: str, *, repository: Path) -> str:
    """Normalize equivalent Windows, WSL, SSH, and HTTPS Git remote forms."""
    raw = value.strip().replace("\\", "/")
    if not raw:
        raise FlowError("Publication remote URL is empty", EXIT_INTEGRITY)

    def normalized_local(path_value: str) -> str:
        file_drive_match = re.fullmatch(r"/([A-Za-z]):(?:/(.*))?", path_value)
        if file_drive_match:
            path_value = f"{file_drive_match.group(1)}:/{file_drive_match.group(2) or ''}"
        drive_match = re.fullmatch(r"([A-Za-z]):(?:/(.*))?", path_value)
        if drive_match:
            suffix = (drive_match.group(2) or "").rstrip("/")
            if suffix.lower().endswith(".git"):
                suffix = suffix[:-4]
            return f"file:///{drive_match.group(1).lower()}:/{suffix.lower()}"
        wsl_match = re.fullmatch(r"/mnt/([A-Za-z])(?:/(.*))?", path_value)
        if wsl_match:
            suffix = (wsl_match.group(2) or "").rstrip("/")
            if suffix.lower().endswith(".git"):
                suffix = suffix[:-4]
            return f"file:///{wsl_match.group(1).lower()}:/{suffix.lower()}"
        local = Path(path_value)
        if not local.is_absolute():
            local = repository / local
        normalized = local.resolve().as_posix().rstrip("/")
        if normalized.lower().endswith(".git"):
            normalized = normalized[:-4]
        return f"file://{normalized}"

    if re.match(r"^[A-Za-z]:/", raw) or raw.startswith(("/", "./", "../")):
        return normalized_local(raw)
    scp = re.fullmatch(r"(?:[^/@]+@)?([^/:]+):(.+)", raw) if "://" not in raw else None
    if scp:
        host = scp.group(1).lower()
        remote_path = scp.group(2).strip("/")
        if remote_path.lower().endswith(".git"):
            remote_path = remote_path[:-4]
        return f"git://{host}/{remote_path}"
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme.lower() == "file":
        return normalized_local(urllib.parse.unquote(parsed.path))
    if not parsed.hostname:
        return normalized_local(raw)
    host = parsed.hostname.lower()
    port = f":{parsed.port}" if parsed.port else ""
    remote_path = urllib.parse.unquote(parsed.path).strip("/")
    if remote_path.lower().endswith(".git"):
        remote_path = remote_path[:-4]
    return f"git://{host}{port}/{remote_path}"


def publication_target_identity(repository: Path, target: dict[str, Any]) -> dict[str, str]:
    remote_name = str(target.get("deployment", {}).get("remote", "")).strip()
    branch = str(target.get("publication_branch", "")).strip()
    if not remote_name or not branch:
        raise FlowError("Publication target is missing its remote or branch", EXIT_INTEGRITY)
    remote_url = str(git(["remote", "get-url", "--push", remote_name], cwd=repository)).strip()
    return {
        "remote_url": normalize_git_remote_url(remote_url, repository=repository),
        "publication_branch": branch,
    }


def publication_target_lock_path(repository: Path, target: dict[str, Any]) -> Path:
    """Return one host-neutral lock path for a configured publication target."""
    identity = publication_target_identity(repository, target)
    digest = sha256_bytes(canonical_json(identity))[:24]
    filename = f"target-{digest}.lock"
    shared_root = (shared_state_root() / "locks" / "publication").resolve()
    repository_root = repository.resolve()
    try:
        shared_root.relative_to(repository_root)
    except ValueError:
        return shared_root / filename
    raise FlowError(
        "Shared Article Flow state must be outside the publication checkout before publishing",
        EXIT_INTEGRITY,
        {"shared_state_root": str(shared_state_root()), "publication_repository": str(repository_root)},
    )


def publication_lock_wait_seconds() -> float:
    configured = os.environ.get("ARTICLE_FLOW_PUBLICATION_LOCK_WAIT_SECONDS", "300")
    try:
        value = float(configured)
    except ValueError as exc:
        raise FlowError("ARTICLE_FLOW_PUBLICATION_LOCK_WAIT_SECONDS must be a number", EXIT_USAGE) from exc
    if not 0 < value <= 3600:
        raise FlowError("ARTICLE_FLOW_PUBLICATION_LOCK_WAIT_SECONDS must be greater than 0 and at most 3600", EXIT_USAGE)
    return value


@contextlib.contextmanager
def publication_target_lock(
    repository: Path,
    target: dict[str, Any],
    *,
    wait_seconds: float | None = None,
) -> Iterator[Path]:
    """Serialize publication mutations across runs and Windows/WSL hosts."""
    path = publication_target_lock_path(repository, target)
    with shared_lock(path, wait_seconds=publication_lock_wait_seconds() if wait_seconds is None else wait_seconds):
        yield path


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
    if args.push and not args.commit:
        raise FlowError("--push requires --commit", EXIT_USAGE)
    repository = publication_repo_root(required=True)
    target = load_json(SPEC_ROOT / "publication" / "theproductiveprompter.json")
    with publication_target_lock(repository, target):
        return _command_publish_execute_locked(args, repository=repository, target=target)


def _command_publish_execute_locked(
    args: argparse.Namespace,
    *,
    repository: Path,
    target: dict[str, Any],
) -> int:
    directory, run = load_run(args.run_id)
    if run["state"] != "PUBLISH":
        raise FlowError(f"Publication execution requires PUBLISH, current state is {run['state']}")
    approval_path = directory / "approvals" / f"{args.approval}.json"
    if not approval_path.is_file():
        raise FlowError("Scoped publication approval not found", EXIT_APPROVAL)
    approval = load_json(approval_path)
    plan_path = directory / "publication" / "plan.json"
    plan = load_json(plan_path)
    if approval["package_revision"] != plan["package_revision"] or approval["target"] != plan["target"]:
        raise FlowError("Approval does not match this target and package revision", EXIT_APPROVAL)
    if approval.get("plan_sha256") != sha256_path(plan_path):
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
        # The plan is a snapshot of the target, and the target repository moves
        # for reasons unrelated to this run.  Nothing has been copied yet, so
        # drop the stale plan and return to approval where a fresh one is built
        # against the current head rather than stopping with an instruction the
        # run has no way to carry out.
        plan_path.unlink(missing_ok=True)
        transition(
            directory, run, "PUBLISH_APPROVAL", "controller",
            "Publication target head moved after planning; replan against the current head",
        )
        raise FlowError(
            "Repository HEAD changed after publication planning; a fresh plan is required",
            EXIT_WAITING,
            {"planned": plan.get("base_commit"), "actual": current_commit},
        )
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
            # Verify every target before writing any of them.  Checking and
            # writing in one pass left the publication repository partially
            # published when a later file had moved: earlier approved files
            # were already on disk, the rest were abandoned, and the resulting
            # dirty checkout was then refused by the clean-checkout guard.
            for change in plan["changes"]:
                rel = safe_relative(change["path"])
                destination = repository / rel
                current_hash = sha256_path(destination) if destination.is_file() else None
                if current_hash != change["current_sha256"]:
                    # The plan is a snapshot of the target, so a target that
                    # moved makes the plan stale rather than the run unsound.
                    # Drop it and return to approval so a fresh plan is built
                    # against what is actually there; the publication itself
                    # has not started.
                    plan_path.unlink(missing_ok=True)
                    transition(
                        directory, run, "PUBLISH_APPROVAL", "controller",
                        f"Publication target {rel} changed after planning; replan against the current target",
                    )
                    raise FlowError(
                        f"Publication target changed after planning: {rel}; a fresh plan is required",
                        EXIT_WAITING,
                    )
            for change in plan["changes"]:
                rel = safe_relative(change["path"])
                atomic_write(repository / rel, (site_root / rel).read_bytes())
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
    try:
        request = urllib.request.Request(url, headers={"User-Agent": f"article-flow/{CONTROLLER_VERSION}"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read(), {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(), {key.lower(): value for key, value in exc.headers.items()}
    except (urllib.error.URLError, TimeoutError):
        return 0, b"", {}
    except (ValueError, http.client.HTTPException):
        # A malformed target (unknown scheme, embedded whitespace, or several
        # URLs joined into one field) fails before any socket work: Request
        # raises ValueError for an unknown scheme, and urlopen raises
        # http.client.InvalidURL, which derives from HTTPException and not from
        # OSError or ValueError.  Both escaped the handlers above and aborted
        # the caller with an unhandled traceback.  Zero is reserved for a
        # genuinely unreachable host and is accepted by the evidence gate, so a
        # distinct negative status is required to keep a broken source from
        # being misreported as transport-impossible.
        return -1, b"", {}


def command_verify_live(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    if run["state"] != "LIVE_VERIFICATION":
        raise FlowError(f"Live verification requires LIVE_VERIFICATION, current state is {run['state']}")
    events = _read_jsonl(directory / str(run["event_log"]))
    prior_attempts = sum(1 for event in events if event.get("type") == "VERIFICATION" and (event.get("payload") or {}).get("state") == "LIVE_VERIFICATION")
    maximum = int(state_definition("LIVE_VERIFICATION", run).get("max_attempts", 4))
    if prior_attempts >= maximum:
        run["status"] = "BLOCKED"
        save_run(directory, run)
        raise FlowError("Live verification exhausted its bounded retry window", EXIT_WAITING, {"attempts": prior_attempts, "maximum": maximum})
    attempt = prior_attempts + 1
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
    checks: list[dict[str, Any]] = []
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
    expected_surface_paths = {
        "blog": directory / "package" / "site" / "docs" / "blog.html",
        "homepage": directory / "package" / "site" / "index.html",
        "feed": directory / "package" / "site" / "feed.xml",
        "sitemap": directory / "package" / "site" / "sitemap.xml",
    }
    for surface in ("blog", "homepage", "feed", "sitemap"):
        status, body, _ = fetch_url(urls[surface])
        decoded = body.decode("utf-8", errors="replace")
        checks.append({"name": f"{surface}_http", "ok": status == 200, "status": status})
        checks.append({"name": f"{surface}_revision", "ok": sha256_bytes(body) == sha256_path(expected_surface_paths[surface]), "expected_sha256": sha256_path(expected_surface_paths[surface]), "actual_sha256": sha256_bytes(body)})
        checks.append({"name": f"{surface}_links_article", "ok": urls["article"] in decoded or f"{metadata['slug']}.html" in decoded})
    asset_manifest = load_json(directory / "package" / "public" / "assets.json")
    for asset in asset_manifest.get("assets", []):
        if not isinstance(asset, dict):
            continue
        asset_url = urllib.parse.urljoin(target["homepage_url"], str(asset.get("public_path") or "").lstrip("/"))
        status, body, _ = fetch_url(asset_url)
        checks.append({
            "name": "visual_asset",
            "visual_id": asset.get("visual_id"),
            "url": asset_url,
            "status": status,
            "expected_sha256": asset.get("sha256"),
            "actual_sha256": sha256_bytes(body),
            "ok": status == 200 and sha256_bytes(body) == asset.get("sha256"),
        })
    external_links = sorted(set(re.findall(r'href="(https?://[^"]+)"', article_text)) - set(urls.values()))
    link_results = []
    for link in external_links:
        status, _, _ = fetch_url(html.unescape(link), timeout=15)
        classification = "resolved" if 200 <= status < 400 else "inconclusive_access_control" if status in {401, 403, 429, 999} else "failed"
        link_results.append({"url": html.unescape(link), "status": status, "classification": classification})
        checks.append({"name": "external_link", "url": html.unescape(link), "status": status, "classification": classification, "ok": classification != "failed"})
    ok = all(item["ok"] for item in checks)
    failed = [item for item in checks if not item["ok"]]
    propagation_names = {"article_http", "article_revision", "blog_http", "blog_revision", "homepage_http", "homepage_revision", "feed_http", "feed_revision", "sitemap_http", "sitemap_revision", "visual_asset"}
    propagation = bool(failed) and all(str(item.get("name")) in propagation_names or str(item.get("name", "")).endswith("_links_article") for item in failed)
    classification = "verified" if ok else "deployment_propagation" if propagation else "permanent_validation_failure"
    retry_schedule = [10, 20, 40, 60]
    retry_after = retry_schedule[min(attempt - 1, len(retry_schedule) - 1)] if not ok and propagation and attempt < maximum else None
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
        "attempt": attempt,
        "maximum_attempts": maximum,
        "classification": classification,
        "retry_after_seconds": retry_after,
        "created_at": utc_now(),
    }
    receipt_path = directory / "receipts" / f"live-verification-{attempt:02d}.json"
    write_json(receipt_path, receipt)
    record_artifact(directory, run, receipt_path, f"live-verification-attempt:{attempt}", {"actor": "controller", "version": CONTROLLER_VERSION})
    append_event(directory, run, "VERIFICATION", "controller", {"state": "LIVE_VERIFICATION", "attempt": attempt, "ok": ok, "url": receipt["url"], "classification": classification, "retry_after_seconds": retry_after, "checks": checks})
    if not ok:
        write_gate_receipt(directory, run, "G-LIVE-REVISION", "RETRY", [
            {"criterion": item["name"], "artifact": str(item.get("url") or urls["article"]), "location": None, "finding": json.dumps(item), "repair_instruction": "Wait for bounded deployment propagation when classified retryable; otherwise return to the publication repair state."}
            for item in failed
        ], {"type": "code", "version": CONTROLLER_VERSION}, "PUBLISH")
        run["live_verification"] = {"attempt": attempt, "maximum": maximum, "classification": classification, "retry_after_seconds": retry_after, "next_retry_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=retry_after)).replace(microsecond=0).isoformat().replace("+00:00", "Z") if retry_after else None}
        run["status"] = "ACTIVE" if retry_after else "BLOCKED"
        save_run(directory, run)
        emit({"ok": False, "receipt": str(receipt_path), "checks": checks, "classification": classification, "retryable": retry_after is not None, "retry_after_seconds": retry_after, "attempt": attempt, "maximum_attempts": maximum, "indexing": "unknown_not_claimed"}, args.json)
        return EXIT_FAILED
    write_gate_receipt(directory, run, "G-LIVE-REVISION", "PASS", [], {"type": "code", "version": CONTROLLER_VERSION})
    record_artifact(directory, run, receipt_path, "live-verification", {"actor": "controller", "version": CONTROLLER_VERSION})
    run["publication"] = {
        "status": "VERIFIED",
        "url": receipt["url"],
        "commit": receipt.get("commit"),
        "package_revision": package["package_revision"],
        "verified_at": receipt["created_at"],
        "represented_for_discovery": receipt["represented_for_discovery"],
        "indexing": receipt["indexing"],
    }
    run["live_verification"] = {"attempt": attempt, "maximum": maximum, "classification": "verified", "retry_after_seconds": None, "next_retry_at": None}
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
            reopened = False
            if state in MODEL_STATES:
                # Observer recovery is intentionally pure.  Advance is a
                # mutating command, so reconcile the attempt boundary and
                # persist the recovered BLOCKED projection while serialized.
                with run_lock(directory, run):
                    definition = state_definition(run["state"], run)
                    evidence = stage_attempt_evidence(directory, run, run["state"])
                    if evidence["window_used"] >= int(definition.get("max_attempts", 1)):
                        block_exhausted_stage(directory, run, run["state"], definition)
                    elif blocked_only_by_attempt_window(directory, run, run["state"]):
                        # The window that produced this stop has reopened, so
                        # the durable block no longer describes the run and
                        # must not outlive its cause.  Any other escalation
                        # keeps the run blocked for an operator to review.
                        run["status"] = "ACTIVE"
                        reopened = True
                        save_run(directory, run)
                    else:
                        save_run(directory, run)
                directory, run = load_run(args.run_id)
            if reopened:
                progress.append({"state": state, "command": "attempt-window-reopened"})
                continue
            payload = {**next_state_payload(directory, run), "ok": False, "progress": progress}
            emit(payload, args.json)
            return EXIT_WAITING
        if state == "VOICE_PROBE" and is_v3_run(run) and committed_voice_selection(directory, run):
            # Finish the crashed commit under the lock instead of presenting
            # the decision again or dispatching another probe task.
            with run_lock(directory, run):
                _, locked = load_run(args.run_id)
                relocked = committed_voice_selection(directory, locked)
                if relocked is not None:
                    finish_committed_voice_selection(directory, locked, relocked)
                    progress.append({
                        "state": state,
                        "command": "voice-selection-reconciled",
                        "candidate_id": relocked["candidate_id"],
                    })
            continue
        if (
            state == "VOICE_PROBE"
            and artifact(run, "voice-probe")
            and voice_probe_awaits_human(directory, run)
        ):
            payload = {**next_state_payload(directory, run), "ok": True, "progress": progress}
            emit(payload, args.json)
            return EXIT_WAITING
        if state in MODEL_STATES:
            boundary: dict[str, Any] | None = None
            with run_lock(directory, run):
                definition = state_definition(run["state"], run)
                evidence = stage_attempt_evidence(directory, run, run["state"])
                if (
                    run.get("status") != "WAITING_MODEL"
                    and evidence["window_used"] >= int(definition.get("max_attempts", 1))
                ):
                    block_exhausted_stage(directory, run, run["state"], definition)
                    boundary = {
                        "state": run["state"],
                        "command": "attempt-boundary",
                        "attempts": evidence["window_used"],
                        "attempt_ordinal": evidence["ordinal"],
                        "maximum": int(definition.get("max_attempts", 1)),
                    }
            if boundary is not None:
                progress.append(boundary)
                directory, run = load_run(args.run_id)
                payload = {**next_state_payload(directory, run), "ok": False, "progress": progress}
                emit(payload, args.json)
                return EXIT_WAITING
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
                if run.get("status") == "BLOCKED":
                    payload = {**next_state_payload(directory, run), "ok": False, "progress": progress, "result": result}
                    emit(payload, args.json)
                    return EXIT_WAITING
                payload = {"ok": False, "action": "blocked", "run_id": run["run_id"], "state": run["state"], "progress": progress, "result": result}
                emit(payload, args.json)
                return code
            continue
        if state == "VOICE_LEARNING":
            with run_lock(directory, run):
                result = apply_voice_learning(directory, run)
            progress.append({"state": state, "command": "voice-apply", "result": result})
            continue
        if state == "VISUAL_RENDER":
            code, result = _silent_command(command_visual_render, argparse.Namespace(run_id=run["run_id"], json=True))
            progress.append({"state": state, "command": "render-visuals", "exit_code": code, "result": result})
            if code != EXIT_OK:
                emit({"ok": False, "action": "blocked", "run_id": run["run_id"], "state": state, "progress": progress}, args.json)
                return code
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
                if isinstance(result, dict) and result.get("retryable") and int(result.get("retry_after_seconds") or 0) <= 60:
                    time.sleep(max(0, int(result.get("retry_after_seconds") or 0)))
                    continue
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


def command_regenerate_voice(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    if not is_v31_run(run) or run.get("state") != "VOICE_PROBE" or not voice_probe_awaits_human(directory, run):
        raise FlowError("Voice regeneration requires a workflow 3.1 run waiting at the voice choice", EXIT_USAGE)
    feedback = str(args.feedback or "").strip()
    if not feedback:
        raise FlowError("Voice regeneration requires concrete feedback", EXIT_USAGE)
    probe_path = artifact_path(directory, run, "voice-probe")
    if not probe_path:
        raise FlowError("The current voice probe is missing", EXIT_INTEGRITY)
    ordinal = 1 + len([item for item in run.get("artifact_index", []) if str(item.get("type", "")).startswith("voice-set-rejection:")])
    rejection = {
        "voice_set_rejection_schema_version": "1.0.0",
        "run_id": run["run_id"],
        "voice_probe_sha256": sha256_path(probe_path),
        "feedback": feedback,
        "rejected_at": utc_now(),
        "learning_applied": False,
    }
    with run_lock(directory, run):
        path = directory / "artifacts" / f"voice-set-rejection-{ordinal:02d}.json"
        write_json(path, rejection)
        errors = validate_json_schema(path, "voice-set-rejection.schema.json")
        if errors:
            raise FlowError("Controller generated an invalid voice-set rejection", EXIT_INTEGRITY, errors)
        record_artifact(directory, run, path, f"voice-set-rejection:{ordinal}", {"actor": "operator"})
        append_event(directory, run, "VOICE_SET_REJECTED", "operator", {"feedback": feedback, "voice_probe_sha256": rejection["voice_probe_sha256"], "learning_applied": False})
        save_run(directory, run)
    gate_args = argparse.Namespace(
        run_id=run["run_id"], gate_id="G-VOICE-PROBE", outcome="REPAIR", finding=feedback,
        artifact=str(probe_path), selection=None, feedback=None, json=True,
    )
    code, result = _silent_command(command_gate, gate_args)
    if code != EXIT_OK:
        emit(result or {"ok": False}, args.json)
        return code
    if bool(getattr(args, "auto", False)):
        return command_advance(argparse.Namespace(run_id=run["run_id"], max_steps=100, json=args.json))
    directory, run = load_run(run["run_id"])
    emit({"ok": True, "state": run["state"], "learning_applied": False, "next_command": ["article-flow", "advance", run["run_id"]]}, args.json)
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


def command_voice_feedback(args: argparse.Namespace) -> int:
    directory, run = load_run(args.run_id)
    live_receipt = json_artifact(directory, run, "live-verification") or {}
    if run.get("state") != "COMPLETE" or live_receipt.get("status") != "VERIFIED":
        raise FlowError("Published-article feedback requires a completed run with a verified live receipt", EXIT_USAGE)
    feedback_path = Path(args.feedback_file).expanduser().resolve()
    if not feedback_path.is_file():
        raise FlowError(f"Feedback file does not exist: {feedback_path}", EXIT_USAGE)
    feedback_text = feedback_path.read_text(encoding="utf-8").strip()
    if not feedback_text:
        raise FlowError("Article feedback cannot be empty", EXIT_USAGE)
    article_path = artifact_path(directory, run, "article")
    if not article_path:
        raise FlowError("Article feedback requires a recorded article artifact", EXIT_INTEGRITY)
    recorded_at = utc_now()
    identity_hash = sha256_bytes(canonical_json({"run_id": run["run_id"], "outcome": args.outcome, "feedback": feedback_text, "article_sha256": sha256_path(article_path)}))
    record_id = f"AFB-{identity_hash[:20]}"
    feedback = {
        "article_feedback_schema_version": "1.0.0",
        "run_id": run["run_id"],
        "outcome": args.outcome,
        "feedback": feedback_text,
        "recorded_at": recorded_at,
    }
    root = voice_state_root()
    with shared_lock(root / ".lock"):
        prior_profile, _, pointer = _initialize_voice_runtime_locked()
        evidence_path = root / "article-feedback.jsonl"
        existing = next((item for item in _read_jsonl(evidence_path) if item.get("record_id") == record_id), None)
        if existing:
            emit({"ok": True, "idempotent": True, "record_id": record_id, "current_version": pointer.get("current_version")}, args.json)
            return EXIT_OK
        profile = json.loads(json.dumps(prior_profile))
        retired_guidance: list[str] = []
        retired_sources: set[str] = set()
        if args.outcome == "rejected":
            active_guidance = [item for item in profile.get("provisional_guidance", []) if isinstance(item, dict)]
            retired_guidance = [str(item.get("guidance_id")) for item in active_guidance]
            retired_sources = {str(item.get("source_record_id")) for item in active_guidance}
            profile["provisional_guidance"] = []
            profile["positive_examples"] = [
                item for item in profile.get("positive_examples", [])
                if not (isinstance(item, dict) and str(item.get("source_record_id")) in retired_sources)
            ]
            profile["accepted_rejected_pairs"] = [
                item for item in profile.get("accepted_rejected_pairs", [])
                if not (isinstance(item, dict) and str(item.get("source_record_id")) in retired_sources)
            ]
            profile.setdefault("negative_examples", []).append({
                "example_id": f"VN-{identity_hash[:16]}",
                "status": "operator_rejected_published_article",
                "run_id": run["run_id"],
                "article_sha256": sha256_path(article_path),
                "excerpt": re.sub(r"\s+", " ", article_path.read_text(encoding="utf-8")).strip()[:700],
                "feedback": feedback_text,
                "source_record_id": record_id,
            })
        profiles_count = len(list((root / "profiles").glob("runtime-*.json"))) + 1
        new_version = f"runtime-{profiles_count:06d}-{identity_hash[:10]}"
        guidance_id = f"VG-{identity_hash[:16]}"
        profile["version"] = new_version
        profile["status"] = "provisional"
        profile["parent_version"] = prior_profile["version"]
        profile["base_profile_sha256"] = sha256_path(baseline_voice_profile_path())
        profile["source_learning_record_id"] = record_id
        profile.setdefault("provisional_guidance", []).append({
            "guidance_id": guidance_id,
            "text": (
                "For senior-engineer field notes, prefer a concrete first-person observation, short paragraphs, ordinary nouns, and a clear practical thesis. "
                "Use technical detail only when it helps the reader see or decide something. Operator feedback: " + feedback_text
            ),
            "status": "provisional",
            "source_record_id": record_id,
            "created_at": recorded_at,
            "dimensions": ["concrete", "conversational", "field-note", "human", "practical", "senior-engineer"],
        })
        profile.setdefault("change_history", []).append({
            "version": new_version,
            "date": dt.date.today().isoformat(),
            "status": "provisional",
            "reason": f"Published-article feedback {record_id}; retired {len(retired_guidance)} active provisional guidance entries while immutable history remains available.",
        })
        errors = validate_instance_schema(profile, "voice-profile.schema.json")
        if errors:
            raise FlowError("Controller generated an invalid feedback-adjusted voice profile", EXIT_INTEGRITY, errors)
        profile_path = root / "profiles" / f"{slugify(new_version, 80)}-{sha256_bytes(canonical_json(profile))[:12]}.json"
        write_json(profile_path, profile)
        evidence = {
            **feedback,
            "record_id": record_id,
            "article_sha256": sha256_path(article_path),
            "prior_profile_version": prior_profile["version"],
            "new_profile_version": new_version,
            "retired_guidance_ids": retired_guidance,
            "guidance_added": guidance_id,
        }
        _append_jsonl(evidence_path, evidence)
        new_pointer = {
            "voice_profile_pointer_schema_version": "1.0.0",
            "profile_id": profile["profile_id"],
            "current_version": new_version,
            "profile_sha256": sha256_path(profile_path),
            "updated_at": recorded_at,
            "source_learning_record_id": record_id,
            "previous_version": prior_profile["version"],
        }
        pointer_errors = validate_instance_schema(new_pointer, "voice-profile-pointer.schema.json")
        if pointer_errors:
            raise FlowError("Controller generated an invalid voice-profile pointer", EXIT_INTEGRITY, pointer_errors)
        write_json(root / "current.json", new_pointer)
    with run_lock(directory, run):
        local_path = directory / "artifacts" / f"article-feedback-{record_id}.json"
        write_json(local_path, feedback)
        local_errors = validate_json_schema(local_path, "article-feedback.schema.json")
        if local_errors:
            raise FlowError("Controller generated an invalid article feedback artifact", EXIT_INTEGRITY, local_errors)
        record_artifact(directory, run, local_path, f"article-feedback:{record_id}", {"actor": "operator"})
        append_event(directory, run, "ARTICLE_VOICE_FEEDBACK", "operator", {"record_id": record_id, "outcome": args.outcome, "new_profile_version": new_version, "retired_guidance_ids": retired_guidance})
        save_run(directory, run)
    emit({"ok": True, "idempotent": False, "record_id": record_id, "new_profile_version": new_version, "retired_guidance_ids": retired_guidance, "guidance_added": guidance_id}, args.json)
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
    route_health = automated_route_health()
    dirty = dirty_classification()
    authoring = {
        "ok": launcher["ok"] and integrity["ok"] and route_health["ok"] and not dirty["protected_unstaged"],
        "spec_integrity": integrity,
        "automated_routes": route_health,
        "route_available": route_health["ok"],
        "protected_worktree_state": "VERIFIED" if integrity["ok"] and not dirty["protected_unstaged"] else "UNVERIFIED",
        "dirty_state": dirty,
    }
    head_integrity = check_manifest("head")
    installations = installation_health()
    conformance = host_conformance_health()
    release = {
        "ok": launcher["ok"] and head_integrity["ok"] and schemas["ok"] and dirty["clean"] and commands["ok"] and installations["ok"] and conformance["ok"] and route_health["ok"],
        "head_integrity": head_integrity,
        "schemas_and_documents": schemas,
        "clean_checkout": dirty["clean"],
        "global_command_discovery": commands,
        "installations": installations,
        "host_conformance": conformance,
        "automated_routes": route_health,
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

    revise = sub.add_parser("revise", help="Create a new verified run that replaces one completed article at the same URL.")
    revise.add_argument("source_run_id")
    revise.add_argument("--request-file", required=True)
    revise.add_argument("--auto", action="store_true", help="Continue synchronously until the voice choice, a blocker, or completion.")
    revise.add_argument("--draft-model", choices=DEFAULT_DRAFT_MODEL_POOL)
    revise.add_argument("--hold-before-publish", action="store_true")
    add_json(revise)

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

    regenerate_voice = sub.add_parser("regenerate-voice", help="Reject all three voice candidates without learning and create a new bounded set.")
    regenerate_voice.add_argument("run_id")
    regenerate_voice.add_argument("--feedback", required=True)
    regenerate_voice.add_argument("--auto", action="store_true")
    add_json(regenerate_voice)

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
    voice_feedback = voice_sub.add_parser("feedback")
    voice_feedback.add_argument("run_id")
    voice_feedback.add_argument("--outcome", choices=["accepted", "rejected"], required=True)
    voice_feedback.add_argument("--feedback-file", required=True)
    add_json(voice_feedback)

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

    render_visuals = sub.add_parser("render-visuals", help="Render a validated visual plan into deterministic SVG assets.")
    render_visuals.add_argument("run_id")
    render_visuals.add_argument("--refresh", action="store_true", help="Re-render a held publication from its unchanged approved visual plan, then rebuild its package.")
    add_json(render_visuals)

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
        if args.command == "revise":
            return command_revise(args)
        if args.command == "advance":
            return command_advance(args)
        if args.command == "choose-voice":
            return command_choose_voice(args)
        if args.command == "regenerate-voice":
            return command_regenerate_voice(args)
        if args.command == "models" and args.models_command == "history":
            return command_models_history(args)
        if args.command == "voice":
            if args.voice_command == "apply":
                return command_voice_apply(args)
            if args.voice_command == "history":
                return command_voice_history(args)
            if args.voice_command == "feedback":
                return command_voice_feedback(args)
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
        if args.command == "render-visuals":
            return command_visual_render(args)
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
