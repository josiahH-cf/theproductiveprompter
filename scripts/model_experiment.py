#!/usr/bin/env python3
"""Repository-owned Model Release Experiment discovery and evidence guards."""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = "model-release-v1"
PROMPT_SHA256 = "d6ea22391915e294a6ed80dc109550b035cf7c9548159dc71d0efc39e661f96d"
PACK = ROOT / "experiments" / "model-release"
DEFAULT_STATE = Path.home() / ".local" / "state" / "ProductivePrompter" / EXPERIMENT


class ExperimentError(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stream.write((json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
        staged = Path(stream.name)
    try:
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def freeze_prompt(pack: Path = PACK) -> bytes:
    config = load(pack / "experiment.json")
    prompt = (pack / "prompt.txt").read_bytes()
    if config.get("experiment") != EXPERIMENT or config.get("prompt_sha256") != PROMPT_SHA256:
        raise ExperimentError("Experiment identity or expected prompt hash changed.")
    if sha(prompt) != PROMPT_SHA256:
        raise ExperimentError("Frozen prompt changed. Refusing discovery, recording, or rendering.")
    return prompt


def model_key(provider: str, model: str) -> str:
    return sha(f"{EXPERIMENT}\0{provider}\0{model}".encode())


def empty_registry():
    return {"schema_version": 1, "experiment": EXPERIMENT,
            "prompt_sha256": PROMPT_SHA256, "models": [], "records": []}


def safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ExperimentError("Artifact path escapes the experiment directory.")
    return path


def verify_registry(registry, pack: Path = PACK) -> None:
    if registry.get("experiment") != EXPERIMENT or registry.get("prompt_sha256") != PROMPT_SHA256:
        raise ExperimentError("Registry belongs to another experiment or prompt.")
    seen = set()
    for record in registry["records"]:
        base = model_key(record["provider"], record["model"])
        attempt = record.get("attempt", 1)
        if not isinstance(attempt, int) or attempt < 1:
            raise ExperimentError("Invalid result attempt identity.")
        key = base if attempt == 1 else f"{base}-attempt-{attempt}"
        if key in seen or key != record.get("key"):
            raise ExperimentError("Duplicate or mismatched result identity.")
        seen.add(key)
        if record.get("prompt_sha256") != PROMPT_SHA256:
            raise ExperimentError("A recorded response used another prompt.")
        for relative, digest in record["artifacts"].items():
            path = safe_path(pack, relative)
            if not path.is_file() or sha(path.read_bytes()) != digest:
                raise ExperimentError(f"Existing evidence changed or is missing: {relative}")


def verify_history(registry, state: Path) -> None:
    anchor = state / "record-history.json"
    historical = load(anchor) if anchor.exists() else {}
    current = {row["key"]: sha(json.dumps(row, sort_keys=True).encode()) for row in registry["records"]}
    for key, digest in historical.items():
        if current.get(key) != digest:
            raise ExperimentError("A previously recorded result was removed or replaced.")


def anchor_history(registry, state: Path) -> None:
    atomic_json(state / "record-history.json", {
        row["key"]: sha(json.dumps(row, sort_keys=True).encode()) for row in registry["records"]})


@contextmanager
def update_lock(state: Path):
    state.mkdir(parents=True, exist_ok=True)
    lock = state / "update.lock"
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ExperimentError("Another update is running, or an interrupted update needs reconciliation.")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps({"pid": os.getpid(), "started_at": now()}))
        yield
    finally:
        lock.unlink(missing_ok=True)


def cli(name: str) -> str:
    found = shutil.which(name + ".cmd") if os.name == "nt" else shutil.which(name)
    found = found or shutil.which(name)
    if not found:
        raise ExperimentError(f"{name} CLI is not installed.")
    return found


def process(args, **kwargs):
    if os.name == "nt":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    return subprocess.Popen(args, **kwargs)


def stop_process(proc) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def codex_catalog():
    with tempfile.TemporaryDirectory(prefix="model-catalog-") as cwd:
        p = process([cli("codex"), "debug", "models"], cwd=cwd,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            output, error = p.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            stop_process(p)
            raise ExperimentError("Codex model discovery timed out.")
        if p.returncode:
            raise ExperimentError("Codex model discovery failed; current coverage is unknown.")
        data = json.loads(output)
        return normalize_codex(data)


def normalize_codex(data):
    rows = data.get("models", data.get("data", [])) if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows:
        raise ExperimentError("Codex returned an empty or unsupported catalog.")
    models = []
    for item in rows:
        if item.get("hidden") or item.get("visibility", "list") != "list":
            continue
        if "text" not in item.get("input_modalities", item.get("inputModalities", ["text"])):
            continue
        model = item.get("slug", item.get("model", item.get("id")))
        if not model:
            raise ExperimentError("Codex catalog entry has no model identity.")
        models.append({"provider": "codex", "model": model, "aliases": [model],
                       "display_name": item.get("display_name", item.get("displayName", model)),
                       "source": "codex debug models (remote refresh)",
                       "release_date": item.get("release_date"),
                       "release_date_source": item.get("release_date_source"),
                       "revision_status": "revision not exposed", "_native": item,
                       "effort_levels": [level.get("effort", level.get("reasoning_effort"))
                                         for level in item.get("supported_reasoning_levels", [])]})
    return models


def normalize_claude(data):
    if not isinstance(data.get("models"), list) or not data["models"]:
        raise ExperimentError("Claude returned an empty or unsupported catalog.")
    models = {}
    for item in data["models"]:
        resolved = item.get("resolvedModel")
        if not resolved:
            raise ExperimentError("Claude catalog does not expose resolved model identities.")
        # Context-window annotations are client options, not new weights.
        model = re.sub(r"\[[^]]+\]$", "", resolved)
        row = models.setdefault(model, {"provider": "claude", "model": model,
            "display_name": model, "aliases": [], "source": "Claude CLI initialization model catalog",
            "release_date": None, "release_date_source": None,
            "effort_levels": item.get("supportedEffortLevels", []),
            "revision_status": "snapshot ID" if re.search(r"-\d{8}$", model) else "revision not exposed"})
        if item["value"] not in row["aliases"]:
            row["aliases"].append(item["value"])
    return list(models.values())


def claude_catalog():
    # An initialize control request contains no user turn and performs no generation.
    args = [cli("claude"), "--safe-mode", "--disable-slash-commands",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--tools", "",
            "--print", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
    with tempfile.TemporaryDirectory(prefix="model-catalog-") as cwd:
        p = process(args, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        lines = queue.Queue()
        def reader():
            for line in p.stdout:
                lines.put(line)
            lines.put(None)
        threading.Thread(target=reader, daemon=True).start()
        try:
            p.stdin.write(json.dumps({"type": "control_request", "request_id": "catalog-only",
                "request": {"subtype": "initialize", "hooks": {}}}) + "\n")
            p.stdin.flush()
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                try:
                    line = lines.get(timeout=1)
                except queue.Empty:
                    continue
                if line is None:
                    break
                event = json.loads(line)
                if event.get("type") == "control_response":
                    response = event.get("response", {})
                    if response.get("subtype") != "success":
                        raise ExperimentError("Claude model discovery was refused.")
                    return normalize_claude(response.get("response", {}))
            raise ExperimentError("Claude model discovery did not complete; coverage is unknown.")
        finally:
            stop_process(p)
            for stream in (p.stdin, p.stdout):
                stream.close()


def discover():
    catalog, errors = [], {}
    for provider, discover_provider in (("codex", codex_catalog), ("claude", claude_catalog)):
        try:
            catalog.extend(discover_provider())
        except (ExperimentError, OSError, ValueError, subprocess.SubprocessError) as exc:
            errors[provider] = str(exc)
    if not catalog:
        raise ExperimentError("Neither provider's current model catalog could be verified.")
    return catalog, errors


def reconcile(registry, catalog):
    dated = load(PACK / "release-dates.json") if (PACK / "release-dates.json").exists() else {}
    existing = {model_key(row["provider"], row["model"]): row for row in registry["models"]}
    for row in catalog:
        key = model_key(row["provider"], row["model"])
        if key not in existing:
            item = dict({k: v for k, v in row.items() if not k.startswith("_")}, first_seen=now())
            registry["models"].append(item)
            existing[key] = item
        else:
            aliases = existing[key]["aliases"]
            for alias in row["aliases"]:
                if alias not in aliases:
                    aliases.append(alias)
        date = dated.get(row["model"])
        if date and not existing[key].get("release_date"):
            existing[key]["release_date"] = date["date"]
            existing[key]["release_date_source"] = date["source"]
            existing[key]["release_date_precision"] = date.get("precision", "day")
            if date.get("note"):
                existing[key]["release_date_note"] = date["note"]
    records = {model_key(row["provider"], row["model"]) for row in registry["records"]}
    return [row for row in catalog if model_key(row["provider"], row["model"]) not in records]


def chronological(row):
    # A missing release date stays explicit; first-seen is the documented fallback.
    return (row.get("release_date") or row["first_seen"][:10], row["model"])


def answer_key(budget):
    orders = [("A",18,25,68),("B",24,40,90),("C",10,15,38),("D",28,35,96),
              ("E",14,20,49),("F",22,30,76),("G",30,50,112),("H",16,25,58)]
    feasible = []
    for mask in range(256):
        selected = [row for i, row in enumerate(orders) if mask & (1 << i)]
        materials, minutes, revenue = (sum(row[i] for row in selected) for i in (1,2,3))
        if materials <= budget and minutes <= 120:
            contribution = revenue - materials - 35
            feasible.append({"orders": [row[0] for row in selected], "materials": materials,
                "minutes": minutes, "revenue": revenue, "order_surplus": revenue - materials,
                "repair_contribution": contribution, "shortfall": max(0, 220 - contribution)})
    return max(feasible, key=lambda row: row["repair_contribution"])


def validate_response(text):
    receipt = None
    decoder = json.JSONDecoder()
    for found in re.finditer(r"\{", text):
        try:
            value, end = decoder.raw_decode(text[found.start():])
            if isinstance(value, dict) and "initial" in value and "revised" in value:
                receipt = value
                break
        except ValueError:
            continue
    checks = {}
    for name, budget in (("initial",80),("revised",66)):
        expected = answer_key(budget)
        observed = receipt.get(name) if receipt else None
        for field, value in expected.items():
            actual = observed.get(field) if isinstance(observed, dict) else None
            if field == "orders" and isinstance(actual, list) and all(isinstance(x, str) for x in actual):
                good = sorted(actual) == sorted(value)
            else:
                good = actual == value and not isinstance(actual, bool)
            checks[f"{name}.{field}"] = "pass" if good else ("missing" if actual is None else "fail")
    donation = receipt.get("donation_confirmed") if receipt else None
    checks["donation_confirmed"] = "pass" if donation is False else ("missing" if donation is None else "fail")
    # Story coherence and literary quality are deliberately not invented by this mechanical checker.
    return {"validator_version": "1.0", "receipt_checks": checks,
            "receipt_passed": all(value == "pass" for value in checks.values()),
            "story_consistency": "not assessed", "literary_quality": "not assessed",
            "word_limits": "not assessed"}


def exclusive_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ExperimentError(f"Refusing to overwrite original evidence: {path.name}")
        return
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def candidate_args(row, private: Path):
    effort = "medium" if "medium" in row.get("effort_levels", []) else None
    if row["provider"] == "claude":
        args = [cli("claude"), "--safe-mode", "--disable-slash-commands", "--tools", "",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--model", row["model"],
            "--print", "--output-format", "stream-json", "--verbose", "--no-session-persistence"]
        if effort:
            args += ["--effort", effort]
        isolation = "safe mode; no built-in tools, skills, or MCP"
    else:
        native = dict(row.get("_native", {}))
        if not native or native.get("slug") != row["model"]:
            raise ExperimentError("Fresh native Codex metadata is required for this selected model.")
        # Keep the provider's model identity and instructions; narrow only the client tool surface.
        native.update(apply_patch_tool_type=None, experimental_supported_tools=[],
                      supports_search_tool=False, tool_mode="direct")
        catalog = private / "text-only-catalog.json"
        exclusive_write(catalog, json.dumps({"models": [native]}).encode())
        args = [cli("codex"), "exec", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
            "--ephemeral", "--json", "--model", row["model"], "--sandbox", "read-only",
            "--disable", "shell_tool", "--disable", "hooks", "--disable", "plugins",
            "--disable", "multi_agent", "--enable", "skip_host_skill_discovery",
            "-c", 'web_search="disabled"', "-c", "tools.view_image=false",
            "-c", "agents.enabled=false", "-c", "project_doc_max_bytes=0",
            "-c", "model_catalog_json=" + json.dumps(str(catalog.resolve())),
            "--output-last-message", str((private / "final.txt").resolve()), "-"]
        if effort:
            args[2:2] = ["-c", "model_reasoning_effort=" + json.dumps(effort)]
        isolation = "scoped config; empty workspace; task tools removed from catalog; no observed tool calls required"
    return args, {"effort": effort or "client default", "isolation": isolation}


def parse_events(provider, data: bytes):
    events = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    usage, actual, response, tool_used = None, None, "", False
    cost_estimate = None
    failed = False
    for event in events:
        if provider == "claude":
            if event.get("type") == "system" and event.get("subtype") == "init":
                actual = event.get("model")
                if event.get("tools"):
                    tool_used = True  # Isolation verification failed before any tool execution.
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    tool_used = True
            if event.get("type") == "result":
                response = event.get("result", "")
                usage = {"aggregate": event.get("usage"), "by_model": event.get("modelUsage")}
                responders = list((event.get("modelUsage") or {}).keys())
                if len(responders) == 1:
                    actual = responders[0]
                cost_estimate = event.get("total_cost_usd")
                failed = bool(event.get("is_error"))
        else:
            item = event.get("item", {})
            kind = item.get("type")
            if kind in ("command_execution", "mcp_tool_call", "web_search", "file_change", "collab_tool_call"):
                tool_used = True
            if kind == "agent_message" and event.get("type") == "item.completed":
                response = item.get("text", "")
            if event.get("type") == "turn.completed":
                usage = event.get("usage")
            if event.get("type") in ("turn.failed", "error"):
                failed = True
    return {"response": response, "actual_model": actual, "usage": usage,
            "client_cost_estimate_usd": cost_estimate, "tool_used": tool_used, "failed": failed}


def run_once(row, state: Path, timeout: int = 600, attempt: int = 1):
    base = model_key(row["provider"], row["model"])
    key = base if attempt == 1 else f"{base}-attempt-{attempt}"
    private = state / "attempts" / key
    captured = private / "captured.json"
    if captured.exists():
        metadata = load(captured)
        for filename, digest in metadata["private_hashes"].items():
            if sha((private / filename).read_bytes()) != digest:
                raise ExperimentError("Captured attempt evidence changed; refusing to regenerate.")
        return metadata, (private / "response.txt").read_bytes()
    if (private / "started.json").exists():
        raise ExperimentError(f"{row['model']}: interrupted attempt needs reconciliation; no automatic resend.")
    private.mkdir(parents=True, exist_ok=True)
    prompt = freeze_prompt()
    exclusive_write(private / "prompt.txt", prompt)
    args, settings = candidate_args(row, private)
    version = subprocess.run([cli(row["provider"]), "--version"], capture_output=True, timeout=30)
    started = {"key": key, "provider": row["provider"], "model": row["model"],
               "attempt": attempt,
               "prompt_sha256": sha(prompt), "started_at": now(), "settings": settings,
               "client_version": version.stdout.decode("utf-8", errors="replace").strip()}
    exclusive_write(private / "started.json", json.dumps(started, indent=2).encode())
    print(json.dumps({"event": "model_started", "model": row["model"]}), flush=True)
    begin = time.monotonic()
    timed_out = False
    with tempfile.TemporaryDirectory(prefix="model-candidate-") as cwd:
        with (private / "events.jsonl").open("xb") as stdout, (private / "stderr.txt").open("xb") as stderr:
            p = process(args, cwd=cwd, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
            try:
                p.communicate(input=prompt, timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                stop_process(p)
    event_data = (private / "events.jsonl").read_bytes()
    parsed = parse_events(row["provider"], event_data)
    response = parsed.pop("response").encode("utf-8")
    final = private / "final.txt"
    if row["provider"] == "codex" and final.exists():
        response = final.read_bytes()
    exclusive_write(private / "response.txt", response)
    status = ("timeout" if timed_out else "protocol violation" if parsed["tool_used"]
              else "generation failed" if p.returncode or parsed["failed"]
              else "response captured" if response else "incomplete response")
    metadata = dict(started, **parsed, status=status, exit_code=p.returncode,
                    ended_at=now(), elapsed_seconds=round(time.monotonic()-begin, 3),
                    cash_charge_usd=None, validation=validate_response(response.decode("utf-8", errors="replace")))
    if parsed["actual_model"] and re.sub(r"\[[^]]+\]$", "", parsed["actual_model"]) != row["model"]:
        metadata["identity_note"] = "Responder differs from the requested catalog identity; use the actual responder for interpretation."
    metadata["identity_evidence"] = "provider response" if parsed["actual_model"] else "CLI selection and catalog; responder ID not exposed"
    metadata["private_hashes"] = {name: sha((private / name).read_bytes())
                                 for name in ("prompt.txt", "response.txt", "events.jsonl", "stderr.txt")}
    exclusive_write(captured, (json.dumps(metadata, indent=2) + "\n").encode())
    return metadata, response


def append_result(registry, metadata, response: bytes, pack: Path = PACK):
    key = metadata["key"]
    if any(row["key"] == key for row in registry["records"]):
        return
    if metadata.get("prompt_sha256") != PROMPT_SHA256:
        raise ExperimentError("Candidate attempt used another prompt.")
    relative = f"records/{key}/response.txt"
    evidence = f"records/{key}/evidence.json"
    public = {k: v for k, v in metadata.items() if k != "private_hashes"}
    # Provider events and stderr remain private; the public evidence contains no auth/session data.
    exclusive_write(safe_path(pack, relative), response)
    exclusive_write(safe_path(pack, evidence), (json.dumps(public, indent=2) + "\n").encode())
    record = {"key": key, "provider": metadata["provider"], "model": metadata["model"],
        "attempt": metadata.get("attempt", 1),
        "prompt_sha256": PROMPT_SHA256, "status": metadata["status"], "tested_at": metadata["started_at"],
        "artifacts": {relative: sha(response), evidence: sha(safe_path(pack, evidence).read_bytes())}}
    registry["records"].append(record)


def response_coverage(registry):
    successful = {model_key(row["provider"], row["model"]) for row in registry["records"]
                  if row["status"] == "response captured"}
    return [row for row in registry["models"] if model_key(row["provider"], row["model"]) not in successful]


def access_recovery_candidates(registry, catalog, ready, pack: Path = PACK):
    if not ready:
        return []
    selected = []
    for row in catalog:
        if row["provider"] != "claude":
            continue
        prior = [record for record in registry["records"]
                 if (record["provider"], record["model"]) == (row["provider"], row["model"])]
        if not prior or any(record["status"] == "response captured" for record in prior):
            continue
        latest = prior[-1]
        response = safe_path(pack, f"records/{latest['key']}/response.txt").read_text(encoding="utf-8")
        if latest["status"] == "generation failed" and response.startswith("Failed to authenticate:"):
            selected.append((row, max(record.get("attempt", 1) for record in prior) + 1))
    return selected


def claude_auth_ready():
    p = subprocess.run([cli("claude"), "auth", "status"], capture_output=True, timeout=30)
    try:
        return p.returncode == 0 and bool(json.loads(p.stdout).get("loggedIn"))
    except ValueError:
        return False


def render(registry, pack: Path = PACK) -> str:
    records = {}
    for row in registry["records"]:
        base = model_key(row["provider"], row["model"])
        # Prefer the first observed successful response; preserve preceding eligibility failures.
        if base not in records or records[base]["status"] != "response captured":
            records[base] = row
    lanes = []
    for provider, name in (("claude", "Claude"), ("codex", "Codex")):
        cards = []
        rows = sorted((row for row in registry["models"] if row["provider"] == provider), key=chronological)
        for row in rows:
            key = model_key(provider, row["model"])
            record = records.get(key)
            date = (f"Released {row['release_date']}" if row.get("release_date")
                    else f"First seen {row['first_seen'][:10]}; release date unavailable")
            if record:
                artifact_key = record["key"]
                response_path = safe_path(pack, f"records/{artifact_key}/response.txt")
                response = response_path.read_text(encoding="utf-8")
                evidence_path = safe_path(pack, f"records/{artifact_key}/evidence.json")
                evidence = load(evidence_path) if evidence_path.exists() else record
                download = base64.b64encode(response_path.read_bytes()).decode("ascii")
                content = (f'<p>{html.escape(record["status"])}</p>'
                    f'<pre class="response">{html.escape(response)}</pre>'
                    f'<details><summary>Checks and usage</summary><pre><code>{html.escape(json.dumps(evidence, indent=2))}</code></pre></details>'
                    f'<p><a download="{html.escape(row["model"])}.txt" href="data:text/plain;base64,{download}">Exact response</a></p>')
                prior = [old for old in registry["records"] if old["provider"] == provider
                         and old["model"] == row["model"] and old["key"] != artifact_key]
                if prior:
                    content += '<details><summary>Earlier attempts</summary><pre>' + html.escape(json.dumps(prior, indent=2)) + '</pre></details>'
            else:
                content = '<p>Missing result</p>'
            cards.append(f'<details class="release-entry"><summary class="cursor-interaction">'
                f'{html.escape(row["display_name"])}</summary><div class="release-detail">{content}'
                f'<p>{html.escape(date)}</p><p>{html.escape(row["model"])}</p></div></details>')
        if not cards:
            cards = ['<p class="empty-group">No models recorded.</p>']
        lanes.append(f'<section class="{provider}-lane" aria-labelledby="mre-{provider}">'
            f'<div class="lane-heading"><span class="provider-dot" aria-hidden="true"></span>'
            f'<h3 id="mre-{provider}">{name}</h3></div><div class="release-list">{"".join(cards)}</div></section>')
    template = (pack / "preview-template.html").read_text(encoding="utf-8")
    return template.replace("<!-- MODEL_LANES -->", "".join(lanes))


def write_preview(registry, state: Path, destination: Path, pack: Path = PACK) -> None:
    ownership = state / "preview-owner.json"
    old = load(ownership) if ownership.exists() else None
    if destination.exists():
        if not old or old.get("path") != str(destination.resolve()) or old.get("sha256") != sha(destination.read_bytes()):
            raise ExperimentError("Preview has unowned changes. Refusing to overwrite it.")
    content = render(registry, pack).encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # The preview is a derived view; original evidence is exclusively created and never rewritten.
    staged = destination.with_suffix(".staged.html")
    with staged.open("xb") as stream:
        stream.write(content)
    os.replace(staged, destination)
    atomic_json(ownership, {"path": str(destination.resolve()), "sha256": sha(content)})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "preview", "update", "status"], nargs="?", default="update")
    parser.add_argument("--catalog", type=Path, help="Recorded fixture catalog; never reported as live discovery")
    parser.add_argument("--state-dir", type=Path,
        default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", help="Run only this exact discovered model ID")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)
    freeze_prompt()
    registry_path = PACK / "registry.json"
    if args.action == "status":
        registry = load(registry_path) if registry_path.exists() else empty_registry()
        verify_registry(registry)
        verify_history(registry, args.state_dir)
        print(json.dumps({"experiment": EXPERIMENT, "records": len(registry["records"]),
                          "known_models": len(registry["models"]), "prompt_verified": True,
                          "models_without_response": len(response_coverage(registry))}))
        return 0
    with update_lock(args.state_dir):
        registry = load(registry_path) if registry_path.exists() else empty_registry()
        verify_registry(registry)
        verify_history(registry, args.state_dir)
        if args.catalog:
            fixture = load(args.catalog)
            catalog, errors = fixture["models"], fixture.get("errors", {})
            source = "fixture"
        else:
            catalog, errors = discover()
            source = "live client catalogs"
        missing = reconcile(registry, catalog)
        verify_registry(registry)
        atomic_json(registry_path, registry)
        anchor_history(registry, args.state_dir)
        run_errors = {}
        added = []
        if args.action == "update":
            if args.catalog:
                raise ExperimentError("Live generation cannot use a fixture catalog.")
            selected = [(row, 1) for row in missing if not args.model or row["model"] == args.model]
            if any(row["provider"] == "claude" for row in response_coverage(registry)):
                selected += [(row, attempt) for row, attempt in access_recovery_candidates(
                    registry, catalog, claude_auth_ready()) if not args.model or row["model"] == args.model]
            if args.model and not any(row["model"] == args.model for row in catalog):
                raise ExperimentError("Requested model is not in the verified current catalogs; no substitution.")
            for row, attempt in selected:
                try:
                    freeze_prompt()
                    verify_registry(registry)
                    verify_history(registry, args.state_dir)
                    metadata, response = run_once(row, args.state_dir, args.timeout, attempt)
                    append_result(registry, metadata, response)
                    verify_registry(registry)
                    atomic_json(registry_path, registry)
                    anchor_history(registry, args.state_dir)
                    added.append({"provider": row["provider"], "model": row["model"], "status": metadata["status"]})
                    print(json.dumps({"event": "model_recorded", **added[-1]}), flush=True)
                except (ExperimentError, OSError, ValueError, subprocess.SubprocessError) as exc:
                    run_errors[row["model"]] = str(exc)
            missing = reconcile(registry, catalog)
        report = {"experiment": EXPERIMENT, "discovery": source, "prompt_verified": True,
            "existing_evidence_verified": True, "catalog_models": len(catalog),
            "recorded_results": len(registry["records"]),
            "missing_models": [{"provider": row["provider"], "model": row["model"]} for row in missing],
            "coverage": "complete for current CLI catalogs" if not errors else "partial",
            "discovery_errors": errors, "checked_at": now()}
        report["missing_responses"] = [{"provider": row["provider"], "model": row["model"]}
                                       for row in response_coverage(registry)]
        report["added_results"] = added
        report["run_errors"] = run_errors
        if args.action in ("preview", "update"):
            destination = args.output or args.state_dir / "preview.html"
            write_preview(registry, args.state_dir, destination)
            report["preview"] = str(destination.resolve())
        atomic_json(args.state_dir / "last-check.json", report)
        print(json.dumps(report, indent=2))
        return 2 if errors or run_errors or (args.action == "update" and report["missing_responses"]) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ExperimentError, OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}), file=sys.stderr)
        sys.exit(1)
