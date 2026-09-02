#!/usr/bin/env python3
"""Isolated Codex CLI transport for Article Flow model stages."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence


RECEIPT_SCHEMA_VERSION = "1.0.0"
DEFAULT_REASONING_EFFORT = "high"
VALID_REASONING_EFFORTS = {"low", "medium", "high", "xhigh", "max", "ultra"}
MODEL_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
JSON_ENVELOPE_FIELD = "artifact_json"
DEFAULT_WEB_SEARCH_MODE = "disabled"
VALID_WEB_SEARCH_MODES = {"disabled", "live"}
LIVE_WEB_SEARCH_STAGES = frozenset({
    "RESEARCH_PLAN",
    "RESEARCH",
    "CLAIM_VERIFICATION",
    "POST_EDIT_CLAIM_VERIFICATION",
})
DISABLED_HOST_TOOL_FEATURES = (
    "shell_tool",
    "unified_exec",
    "computer_use",
    "apps",
    "enable_mcp_apps",
    "plugins",
    "remote_plugin",
    "multi_agent",
    "multi_agent_v2",
    "code_mode",
    "code_mode_host",
    "deferred_executor",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "in_app_browser",
    "workspace_dependencies",
    "image_generation",
    "hooks",
    "skill_mcp_dependency_install",
    "tool_call_mcp_elicitation",
)


class CodexExecError(RuntimeError):
    """A bounded failure returned by the Codex CLI adapter."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


@dataclasses.dataclass(frozen=True)
class CodexExecResult:
    output_text: str
    receipt: dict[str, Any]


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _bounded_diagnostic(value: str | bytes | None, limit: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[-limit:]


def _validate_model_id(model: str) -> str:
    if not MODEL_ID_PATTERN.fullmatch(model):
        raise CodexExecError("Codex model ID contains unsupported characters", {"model": model})
    return model


def _resolve_executable(executable: str | Path) -> str:
    candidate = os.fspath(executable)
    if Path(candidate).parent != Path("."):
        resolved = Path(candidate).expanduser().resolve()
        if not resolved.is_file():
            raise CodexExecError("Codex executable does not exist", {"executable": str(resolved)})
        return str(resolved)
    resolved_command = shutil.which(candidate)
    if not resolved_command:
        raise CodexExecError("Codex executable is unavailable", {"executable": candidate})
    return str(Path(resolved_command).resolve())


def codex_cli_version(executable: str | Path = "codex") -> str:
    resolved = _resolve_executable(executable)
    try:
        completed = subprocess.run(
            [resolved, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CodexExecError("Could not inspect the Codex CLI version", {"error": str(exc)}) from exc
    if completed.returncode:
        raise CodexExecError(
            "Codex CLI version check failed",
            {"exit_code": completed.returncode, "stderr": _bounded_diagnostic(completed.stderr)},
        )
    match = re.search(r"(?:codex(?:-cli)?\s+)?([^\s]+)", completed.stdout.strip())
    if not match:
        raise CodexExecError("Codex CLI returned an empty version")
    return match.group(1)


def build_codex_command(
    *,
    executable: str,
    model: str,
    working_directory: Path,
    output_path: Path,
    output_schema_path: Path | None,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    web_search_mode: str = DEFAULT_WEB_SEARCH_MODE,
) -> list[str]:
    """Build a fixed argv array; the prompt is intentionally supplied over stdin."""
    _validate_model_id(model)
    if reasoning_effort not in VALID_REASONING_EFFORTS:
        raise CodexExecError(
            "Unsupported Codex reasoning effort",
            {"reasoning_effort": reasoning_effort, "allowed": sorted(VALID_REASONING_EFFORTS)},
        )
    if web_search_mode not in VALID_WEB_SEARCH_MODES:
        raise CodexExecError(
            "Unsupported Codex web search mode",
            {"web_search_mode": web_search_mode, "allowed": sorted(VALID_WEB_SEARCH_MODES)},
        )
    command = [
        executable,
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "--json",
        "--model",
        model,
        "--config",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--config",
        "shell_environment_policy.inherit=none",
        "--config",
        f'web_search="{web_search_mode}"',
    ]
    for feature in DISABLED_HOST_TOOL_FEATURES:
        command.extend(["--disable", feature])
    command.extend([
        "--cd",
        str(working_directory),
        "--output-last-message",
        str(output_path),
    ])
    if output_schema_path is not None:
        command.extend(["--output-schema", str(output_schema_path)])
    command.append("-")
    return command


def _event_metadata(stdout: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    malformed_lines = 0
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            malformed_lines += 1
            continue
        if isinstance(value, dict):
            events.append(value)
        else:
            malformed_lines += 1

    thread_id = None
    turn_id = None
    observed_model = None
    usage = None
    event_types: list[str] = []
    errors: list[str] = []
    for event in events:
        event_type = event.get("type")
        if isinstance(event_type, str):
            event_types.append(event_type)
        if event_type == "thread.started" and isinstance(event.get("thread_id"), str):
            thread_id = event["thread_id"]
        if event_type == "turn.started" and isinstance(event.get("turn_id"), str):
            turn_id = event["turn_id"]
        if event_type == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]
        if event_type in {"thread.started", "turn.started", "turn.completed"}:
            candidate = event.get("model") or event.get("model_id")
            if isinstance(candidate, str):
                observed_model = candidate
        if event_type in {"error", "turn.failed"}:
            message = event.get("message") or (event.get("error") or {}).get("message") if isinstance(event.get("error"), dict) else event.get("message")
            if isinstance(message, str):
                errors.append(message[-2000:])
    return {
        "thread_id": thread_id,
        "turn_id": turn_id,
        "observed_model": observed_model,
        "usage": usage,
        "event_count": len(events),
        "event_types": event_types,
        "malformed_event_lines": malformed_lines,
        "errors": errors[-3:],
    }


def codex_transport_schema(_normative_schema: dict[str, Any]) -> dict[str, Any]:
    """Return a strict envelope without weakening or rewriting the artifact schema."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": [JSON_ENVELOPE_FIELD],
        "properties": {JSON_ENVELOPE_FIELD: {"type": "string"}},
        "additionalProperties": False,
    }


def _enveloped_json_prompt(
    prompt: str,
    normative_schema: dict[str, Any],
    web_search_mode: str,
) -> str:
    tool_policy = (
        "Host tools are disabled. Live hosted web search is available for this research stage; "
        "it cannot access host files or applications."
        if web_search_mode == "live"
        else "Host tools and web search are disabled. Use only the task packet and input text already present in this prompt."
    )
    return "\n".join([
        prompt,
        "",
        "JSON TRANSPORT ENVELOPE",
        tool_policy,
        f"Return exactly one JSON object with one required string field named {JSON_ENVELOPE_FIELD!r}.",
        f"The {JSON_ENVELOPE_FIELD!r} string must itself contain the complete JSON serialization of the requested artifact.",
        "Do not omit optional artifact fields merely to satisfy the outer envelope. Do not add any other outer fields.",
        "The decoded artifact must satisfy this normative schema; the controller will validate it after unwrapping:",
        json.dumps(normative_schema, indent=2, ensure_ascii=False),
    ])


def _normalize_output(raw: str, expected_format: str, output_schema: dict[str, Any] | None = None) -> str:
    value = raw.strip()
    if value.startswith("```") and value.endswith("```"):
        lines = value.splitlines()
        if lines and lines[-1].strip() == "```":
            value = "\n".join(lines[1:-1]).strip()
    if expected_format == "json":
        try:
            envelope = json.loads(value)
        except json.JSONDecodeError as exc:
            raise CodexExecError(
                "Codex did not return the requested JSON transport envelope",
                {"line": exc.lineno, "column": exc.colno, "message": exc.msg},
            ) from exc
        if not isinstance(envelope, dict) or set(envelope) != {JSON_ENVELOPE_FIELD}:
            raise CodexExecError(
                "Codex returned an invalid JSON transport envelope",
                {"required_fields": [JSON_ENVELOPE_FIELD]},
            )
        artifact_json = envelope.get(JSON_ENVELOPE_FIELD)
        if not isinstance(artifact_json, str):
            raise CodexExecError("Codex JSON transport envelope did not contain a string artifact")
        try:
            parsed = json.loads(artifact_json)
        except json.JSONDecodeError as exc:
            raise CodexExecError(
                "Codex JSON transport envelope contained an invalid artifact",
                {"line": exc.lineno, "column": exc.colno, "message": exc.msg},
            ) from exc
        value = json.dumps(parsed, indent=2, ensure_ascii=False)
    if not value:
        raise CodexExecError("Codex returned an empty artifact")
    return value + "\n"


def execute_codex(
    *,
    prompt: str,
    model: str,
    expected_format: str,
    output_schema: dict[str, Any] | None,
    timeout_seconds: int,
    executable: str | Path = "codex",
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    web_search_mode: str = DEFAULT_WEB_SEARCH_MODE,
) -> CodexExecResult:
    """Execute one isolated Codex turn and return normalized output plus observations."""
    model = _validate_model_id(model)
    if not prompt.strip():
        raise CodexExecError("Codex prompt must not be empty")
    if expected_format == "json" and not isinstance(output_schema, dict):
        raise CodexExecError("A JSON task requires an object output schema")
    if timeout_seconds < 1:
        raise CodexExecError("Codex timeout must be positive", {"timeout_seconds": timeout_seconds})
    if web_search_mode not in VALID_WEB_SEARCH_MODES:
        raise CodexExecError(
            "Unsupported Codex web search mode",
            {"web_search_mode": web_search_mode, "allowed": sorted(VALID_WEB_SEARCH_MODES)},
        )

    resolved_executable = _resolve_executable(executable)
    cli_version = codex_cli_version(resolved_executable)
    transport_prompt = (
        _enveloped_json_prompt(prompt, output_schema, web_search_mode)
        if expected_format == "json"
        else prompt
    )
    created_at = _utc_now()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="article-flow-codex-") as temporary_name:
        workspace = Path(temporary_name).resolve()
        last_message_path = workspace / "last-message.txt"
        transport_schema = codex_transport_schema(output_schema) if output_schema is not None else None
        schema_path = workspace / "output-schema.json" if transport_schema is not None else None
        if schema_path is not None:
            schema_path.write_bytes(_canonical_json(transport_schema))
        command = build_codex_command(
            executable=resolved_executable,
            model=model,
            working_directory=workspace,
            output_path=last_message_path,
            output_schema_path=schema_path,
            reasoning_effort=reasoning_effort,
            web_search_mode=web_search_mode,
        )
        try:
            completed = subprocess.run(
                command,
                input=transport_prompt,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                cwd=workspace,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = round((time.monotonic() - started) * 1000)
            raise CodexExecError(
                "Codex execution timed out",
                {
                    "model": model,
                    "timeout_seconds": timeout_seconds,
                    "elapsed_ms": elapsed_ms,
                    "stderr": _bounded_diagnostic(exc.stderr),
                },
            ) from exc
        except OSError as exc:
            raise CodexExecError("Codex execution could not start", {"error": str(exc)}) from exc

        elapsed_ms = round((time.monotonic() - started) * 1000)
        metadata = _event_metadata(completed.stdout)
        if completed.returncode:
            raise CodexExecError(
                "Codex execution failed",
                {
                    "model": model,
                    "cli_version": cli_version,
                    "exit_code": completed.returncode,
                    "elapsed_ms": elapsed_ms,
                    "thread_id": metadata["thread_id"],
                    "event_types": metadata["event_types"],
                    "errors": metadata["errors"],
                    "stderr": _bounded_diagnostic(completed.stderr),
                },
            )
        if not last_message_path.is_file():
            raise CodexExecError(
                "Codex completed without a final-message artifact",
                {"exit_code": completed.returncode, "event_types": metadata["event_types"]},
            )
        normalized = _normalize_output(last_message_path.read_text(encoding="utf-8"), expected_format, output_schema)

    observed_model = metadata["observed_model"]
    if observed_model is not None and observed_model != model:
        raise CodexExecError(
            "Codex reported a different model than the explicit request",
            {"requested_model": model, "observed_model": observed_model},
        )
    receipt = {
        "codex_exec_receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "requested_model": model,
        "observed_model": observed_model,
        "model_evidence": "cli-event" if observed_model else "explicit-cli-argument",
        "reasoning_effort": reasoning_effort,
        "cli_version": cli_version,
        "thread_id": metadata["thread_id"],
        "turn_id": metadata["turn_id"],
        "usage": metadata["usage"],
        "elapsed_ms": elapsed_ms,
        "exit_code": completed.returncode,
        "prompt_sha256": _sha256_text(transport_prompt),
        "output_sha256": _sha256_text(normalized),
        "output_schema_sha256": _sha256_bytes(_canonical_json(output_schema)) if output_schema is not None else None,
        "transport_output_schema_sha256": _sha256_bytes(_canonical_json(transport_schema)) if transport_schema is not None else None,
        "transport": {
            "kind": "codex-cli",
            "executable": resolved_executable,
            "prompt_transport": "stdin",
            "sandbox": "read-only",
            "temporary_workspace": True,
            "ephemeral": True,
            "user_config": "ignored",
            "project_rules": "ignored",
            "shell_environment_inheritance": "none",
            "host_tool_access": "disabled",
            "host_file_access": "none_via_model_tools",
            "tool_access_enforcement": "fixed_cli_feature_disables",
            "disabled_host_tool_features": list(DISABLED_HOST_TOOL_FEATURES),
            "web_search_mode": web_search_mode,
            "structured_output_transport": "json-string-envelope" if output_schema is not None else None,
            "structured_output_envelope_field": JSON_ENVELOPE_FIELD if output_schema is not None else None,
            "event_count": metadata["event_count"],
            "event_types": metadata["event_types"],
            "malformed_event_lines": metadata["malformed_event_lines"],
        },
        "created_at": created_at,
    }
    return CodexExecResult(output_text=normalized, receipt=receipt)


def _load_task_packet(packet_path: Path) -> tuple[dict[str, Any], str, str, dict[str, Any] | None]:
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CodexExecError("Could not read the Article Flow task packet", {"packet": str(packet_path)}) from exc
    if not isinstance(packet, dict):
        raise CodexExecError("Article Flow task packet must be a JSON object")
    outputs = packet.get("expected_outputs")
    if not isinstance(outputs, list) or len(outputs) != 1 or not isinstance(outputs[0], dict):
        raise CodexExecError("Article Flow task packet must declare exactly one expected output")
    expected_format = str(outputs[0].get("format", ""))
    output_schema = outputs[0].get("schema")
    if output_schema is not None and not isinstance(output_schema, dict):
        raise CodexExecError("Task packet output schema must be an object")

    # The packet on disk retains the complete hash-bound contract. The prompt
    # carries a compact view because the transport appends the output schema
    # once and the input files are included once below. Repeating both inflated
    # small repairs into very large calls without adding authority.
    prompt_packet = json.loads(json.dumps(packet))
    for output in prompt_packet.get("expected_outputs", []):
        if isinstance(output, dict):
            output.pop("schema", None)
    input_ids = {str(item.get("id")) for item in prompt_packet.get("inputs", []) if isinstance(item, dict)}
    if "article-recipe" in input_ids:
        prompt_packet.pop("article_recipe", None)
    sections = [
        "You are performing one bounded stage in a provider-neutral article workflow.",
        "The controller, not you, owns state transitions and gate outcomes.",
        "Return only the requested artifact. Do not wrap it in a Markdown fence and do not add commentary.",
        "If a stop condition is met, return the smallest schema-valid artifact that records the unresolved condition; never invent evidence or operator intent.",
        "",
        "TASK PACKET",
        json.dumps(prompt_packet, indent=2, ensure_ascii=False),
    ]
    inputs = packet.get("inputs", [])
    if not isinstance(inputs, list):
        raise CodexExecError("Task packet inputs must be an array")
    for item in inputs:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
            raise CodexExecError("Task packet input entry is incomplete")
        path = Path(item["path"])
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise CodexExecError("Task packet input is unavailable", {"input": item.get("id"), "path": str(path)}) from exc
        actual_hash = _sha256_bytes(data)
        if actual_hash != item["sha256"]:
            raise CodexExecError(
                "Task packet input changed before Codex invocation",
                {"input": item.get("id"), "expected_sha256": item["sha256"], "actual_sha256": actual_hash},
            )
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CodexExecError("Task packet input is not UTF-8 text", {"input": item.get("id")}) from exc
        sections.extend(["", f"INPUT {item.get('id')} sha256={actual_hash}", content])
    return packet, "\n".join(sections), expected_format, output_schema


def execute_task_packet(
    packet_path: str | Path,
    output_path: str | Path | None,
    *,
    model: str,
    timeout_seconds: int,
    executable: str | Path = "codex",
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> CodexExecResult:
    """Validate and execute an Article Flow packet, optionally writing its artifact."""
    packet_file = Path(packet_path).expanduser().resolve()
    packet, prompt, expected_format, output_schema = _load_task_packet(packet_file)
    web_search_mode = (
        "live" if packet.get("stage") in LIVE_WEB_SEARCH_STAGES else DEFAULT_WEB_SEARCH_MODE
    )
    result = execute_codex(
        prompt=prompt,
        model=model,
        expected_format=expected_format,
        output_schema=output_schema,
        timeout_seconds=timeout_seconds,
        executable=executable,
        reasoning_effort=reasoning_effort,
        web_search_mode=web_search_mode,
    )
    if output_path is not None:
        _atomic_write(Path(output_path).expanduser().resolve(), result.output_text.encode("utf-8"))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--executable", default="codex")
    parser.add_argument("--reasoning-effort", choices=sorted(VALID_REASONING_EFFORTS), default=DEFAULT_REASONING_EFFORT)
    parser.add_argument("--receipt", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    receipt_path = args.receipt or Path(str(args.output) + ".codex-receipt.json")
    try:
        result = execute_task_packet(
            args.packet,
            args.output,
            model=args.model,
            timeout_seconds=args.timeout,
            executable=args.executable,
            reasoning_effort=args.reasoning_effort,
        )
    except CodexExecError as exc:
        failure = {"ok": False, "error": str(exc), "details": exc.details}
        print(json.dumps(failure, sort_keys=True), file=os.sys.stderr)
        return 1
    _atomic_write(receipt_path.expanduser().resolve(), _canonical_json(result.receipt))
    print(json.dumps({"ok": True, "receipt": str(receipt_path)}, sort_keys=True), file=os.sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
