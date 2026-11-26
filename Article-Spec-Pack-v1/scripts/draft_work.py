"""Private, portable draft work alongside the verified publication path."""
from __future__ import annotations

import json
import re
import tempfile
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any

DRAFT = "working-draft"
CHECK = "working-draft-check"
ADOPTION = "working-draft-adoption"
REVIEW_WARNING = "working-review-warning"
ATTRIBUTION = "Drafting model: Unverified for the externally edited draft."
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 20 * 1024 * 1024
REVIEW_SUBMISSIONS = {
    "claims": ("POST_EDIT_CLAIM_VERIFICATION", "claim-ledger.schema.json"),
    "qa": ("EDITORIAL_QA", "editorial-assessment.schema.json"),
}
PUBLICATION_STATES = {"PUBLISH", "LIVE_VERIFICATION", "COMPLETE", "TERMINAL"}
REVIEW_STATES = {
    "DRAFT", "DEVELOPMENT_REVIEW", "VISUAL_PLAN", "VISUAL_RENDER",
    "CLAIM_VERIFICATION", "VOICE_PROBE", "VOICE_LEARNING", "EDIT",
    "POST_EDIT_CLAIM_VERIFICATION", "DISPLAY_REVISION", "EDITORIAL_QA", "PACKAGE", "PUBLISH_APPROVAL",
}


def parser(sub: Any, add_json: Any) -> None:
    work = sub.add_parser("work", help="Export, return, or check editable draft work at any editorial stage.")
    commands = work.add_subparsers(dest="work_command", required=True)
    export = commands.add_parser("export", help="Write a local Markdown and JSON handoff plus bound assets.")
    export.add_argument("run_id")
    export.add_argument("--directory", required=True, help="New private directory outside the repository and run.")
    export.add_argument("--include-private", action="store_true", help="Include private author decisions and editorial findings in a separate file.")
    add_json(export)
    imported = commands.add_parser("import", help="Save a returned Markdown draft without running any stage.")
    imported.add_argument("run_id")
    imported.add_argument("--file", required=True)
    imported.add_argument("--base-sha256", required=True, help="Draft hash in handoff.json, or 'none' before a draft exists.")
    add_json(imported)
    check = commands.add_parser("check", help="Recheck affected claims in the current working draft with a supplied claim ledger.")
    check.add_argument("run_id")
    check.add_argument("--ledger", help="Any UTF-8 claim-ledger.json containing the affected rows. Omit to see the recheck scope.")
    add_json(check)
    resume = commands.add_parser("resume", help="Use the returned manuscript in this Run's normal verification path.")
    resume.add_argument("run_id")
    resume.add_argument("--visual-plan", help="Use an externally edited visual-plan.json, including an explicit optional omission.")
    add_json(resume)
    submit = commands.add_parser("submit", help="Return outside evidence for the current manuscript's claim or QA check.")
    submit.add_argument("run_id")
    submit.add_argument("review", choices=REVIEW_SUBMISSIONS)
    submit.add_argument("--file", required=True)
    submit.add_argument("--scope-sha256", required=True, help="Review-basis hash returned in the working handoff.")
    add_json(submit)


def guidance(run: dict) -> dict:
    run_id = run["run_id"]
    return {
        "export_command": ["article-flow", "work", "export", run_id, "--directory", "<new private directory>", "--json"],
        "check_command": ["article-flow", "work", "check", run_id, "--json"],
        "resume_command": ["article-flow", "work", "resume", run_id, "--json"],
        "instruction": "Continue drafting or get outside help while checks or decisions are pending. Export locally and share only material you are authorized to disclose.",
    }


def checked_bytes(af: Any, directory: Path, item: dict, *, limit: int = MAX_TEXT_BYTES) -> bytes:
    path = (directory / af.safe_relative(item["path"])).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise af.FlowError("Handoff artifact escapes its Run", af.EXIT_INTEGRITY, {"type": item["type"]})
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit or af.sha256_bytes(data) != item["sha256"]:
        raise af.FlowError("Handoff artifact exceeds its size limit or has changed", af.EXIT_INTEGRITY,
                           {"type": item["type"]})
    return data


def checked_json(af: Any, directory: Path, run: dict, kind: str) -> dict:
    item = af.artifact(run, kind)
    return json.loads(checked_bytes(af, directory, item)) if item else {}


def draft_item(af: Any, run: dict) -> dict | None:
    # Working draft is a deliberate operator edit. An unaccepted draft on an
    # ordinary stage is still useful for editing. Earlier official prose must
    # not supersede a newer development repair.
    items = [item for item in run.get("artifact_index", []) if item["type"] in {"article", "draft"}]
    return af.artifact(run, DRAFT) or (items[-1] if items else af.artifact(run, "previous-article"))


def source_links(text: str) -> set[str]:
    return set(re.findall(r"(?<!!)\[[^\]\n]+\]\((https?://[^)\s]+)\)", text))


def portable_link(url: str) -> bool:
    # Keep local and credential-bearing locators out of the portable index.
    # Query strings can carry access tokens, so they stay in the draft or
    # private source material until the operator reviews the export.
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        return False
    return (parts.scheme in {"http", "https"} and "." in host
            and not host.endswith((".local", ".internal", ".localhost"))
            and not (parts.username or parts.password or parts.query)
            and not re.fullmatch(r"[\d.]+", host))


def warnings(af: Any, directory: Path, run: dict) -> list[dict]:
    results = []
    for item in run["artifact_index"]:
        if not item["type"].startswith("gate-receipt:"):
            continue
        # The gate receipt records evidence; a filename alone is not proof.
        try:
            value = json.loads(checked_bytes(af, directory, item))
        except (af.FlowError, OSError, ValueError):
            results.append({"gate": item["type"][13:], "outcome": "unreadable", "findings": []})
            continue
        if value.get("outcome") != "PASS":
            results.append({"gate": value.get("gate_id"), "outcome": value.get("outcome"),
                            "findings": value.get("findings", [])})
    try:
        review_warning = checked_json(af, directory, run, REVIEW_WARNING)
    except (af.FlowError, OSError, ValueError):
        results.append({"gate": None, "outcome": "unreadable", "findings": []})
        review_warning = {}
    if review_warning:
        gate_id = af.state_definition(review_warning["stage"], run)["gate"]
        latest = af.artifact(run, f"gate-receipt:{gate_id}")
        current = draft_item(af, run)
        warning = af.artifact(run, REVIEW_WARNING)
        if current and review_warning.get("draft_sha256") == current["sha256"] and (
            not latest or run["artifact_index"].index(latest) < run["artifact_index"].index(warning)
        ):
            results.append({"gate": gate_id, "outcome": "REPAIR", "findings": review_warning["findings"]})
    return results


def recommended_repair(gate: str | None) -> str:
    if gate in {"G-CLAIMS-VERIFIED", "G-POST-EDIT-CLAIMS", "G-EVIDENCE-COVERAGE"}:
        return "Replace broken citations with direct support, or remove unsupported wording and optional links. Recheck the affected claims."
    if gate in {"G-VISUAL-PLAN", "G-VISUAL-RENDER"}:
        return "Review the actual diagram or capture. Correct its relationship or placement, or omit an optional visual."
    if gate in {"G-INTENT-FIDELITY", "G-VOICE-PROBE"}:
        return "Keep the pending question and continue the draft under the recorded author constraints."
    return "Review the affected passage or artifact against the Run's findings; retain unfinished checks as open."


def write_export(af: Any, directory: Path, run: dict, args: Any) -> dict:
    target = Path(args.directory).expanduser().resolve()
    roots = {af.REPO_ROOT, af.publication_repo_root(), af.runs_root()}
    if target.exists() or any(root and target.is_relative_to(root.resolve()) for root in roots):
        raise af.FlowError("Choose a new private handoff directory outside the repositories and the Runs directory",
                           af.EXIT_USAGE)
    draft = draft_item(af, run)
    raw = checked_bytes(af, directory, draft) if draft else b""
    links = source_links(raw.decode("utf-8"))
    unavailable = []

    def available(kind: str) -> bytes | None:
        item = af.artifact(run, kind)
        if not item:
            return None
        try:
            return checked_bytes(af, directory, item)
        except (af.FlowError, OSError, ValueError):
            unavailable.append(kind)
            return None

    def available_json(kind: str) -> dict:
        data = available(kind)
        if data:
            try:
                value = json.loads(data)
                if isinstance(value, dict):
                    return value
            except ValueError:
                pass
            unavailable.append(kind)
        return {}

    for kind in ("claim-ledger", "verified-claim-ledger", "post-edit-claim-ledger", "previous-claims"):
        rows = available_json(kind).get("claims")
        if isinstance(rows, list):
            links.update(row["source_url_or_local_id"] for row in rows
                         if isinstance(row, dict) and isinstance(row.get("source_url_or_local_id"), str))
    findings = warnings(af, directory, run)
    # Keep the exact current candidate and all approved-to-render asset bytes.
    # This is a local private export. No file is uploaded or put into Git.
    target.mkdir(mode=0o700)
    (target / "draft.md").write_bytes(raw)
    assets = []
    omissions = []
    total = 0
    declared_assets = available_json("visual-manifest").get("assets", [])
    plan_bytes = available("visual-plan")
    if plan_bytes:
        (target / "visual-plan.json").write_bytes(plan_bytes)
    if af.artifact(run, "external-revision"):
        declared_assets += available_json("external-revision").get("assets", [])
    for asset in declared_assets:
        if not isinstance(asset, dict) or not all(isinstance(asset.get(k), str) for k in ("source_path", "sha256")):
            omissions.append({"reason": "Invalid asset binding"})
            continue
        source_item = {"type": "visual-asset", "path": asset["source_path"], "sha256": asset["sha256"]}
        try:
            data = checked_bytes(af, directory, source_item, limit=MAX_ASSET_BYTES - total)
        except (af.FlowError, OSError) as exc:
            omissions.append({"visual_id": asset.get("visual_id"), "reason": str(exc)})
            continue
        total += len(data)
        suffix = Path(asset["source_path"]).suffix.lower()
        if suffix not in {".svg", ".png", ".jpg", ".jpeg"}:
            suffix = Path(str(asset.get("public_path", ""))).suffix.lower()
        if suffix not in {".svg", ".png", ".jpg", ".jpeg"}:
            omissions.append({"visual_id": asset.get("visual_id"), "reason": "Unsupported asset format"})
            continue
        path = Path("assets") / f"{len(assets) + 1:02d}{suffix}"
        (target / path).parent.mkdir(exist_ok=True)
        (target / path).write_bytes(data)
        assets.append({"file": path.as_posix(), "visual_id": asset.get("visual_id"),
                       "sha256": asset["sha256"], "public_path": asset.get("public_path")})
    if args.include_private:
        documents = {}
        for kind in ("seed", "intent", "brief", "author-context", "voice-learning", "revision-request",
                     "research-amendment", "development-amendment", "editorial-repair-obligations",
                     "working-draft-adoption", "working-draft-check", "post-edit-claim-ledger"):
            content = available(kind)
            if content:
                value = content.decode("utf-8")
                documents[kind] = value
                if af.artifact(run, kind)["path"].endswith(".json"):
                    try:
                        documents[kind] = json.loads(value)
                    except ValueError:
                        unavailable.append(kind)
        af.write_json(target / "private-context.json", {"author_context": documents, "unresolved_findings": findings})
    manifest = {
        "format": "article-flow-working-draft-v1",
        "run_id": run["run_id"], "controller_state_at_export": run["state"], "working_draft": "draft.md",
        "base_sha256": draft["sha256"] if draft else "none",
        "sources": sorted(link for link in links if portable_link(link)),
        "assets": assets, "unavailable_assets": omissions,
        "visual_plan": "visual-plan.json" if plan_bytes else None,
        "unavailable_context": sorted(set(unavailable)),
        "context_repair": "Restore missing or invalid context from the original Run. Continue editing with the files available.",
        "unresolved_checks": [
            {"gate": row["gate"], "outcome": row["outcome"],
             "criteria": sorted({f.get("criterion", "unspecified") for f in row["findings"]}),
             "recommended_repair": recommended_repair(row["gate"])}
            for row in findings
        ],
        "checks_pending": ["Review the exact returned prose, its affected claims and visuals, and any unfinished QA."],
        "editorial_decisions": ("See private-context.json for available author decisions."
                                if args.include_private else "Private author decisions can be exported separately."),
        "source_links_withheld": sum(not portable_link(link) for link in links),
        "scope": plan(af, directory, run, raw.decode("utf-8"))[0] if draft else None,
        "outside_review": review_offer(af, directory, run),
        "publication_authorized": False, "verification": "working_copy",
        "handling": "Private draft. Inspect all files, URLs and assets before sharing with an outside editor.",
        "return_command": ["article-flow", "work", "import", run["run_id"], "--file", "<edited draft.md>",
                           "--base-sha256", draft["sha256"] if draft else "none", "--json"],
    }
    if args.include_private:
        manifest["private_context"] = "private-context.json"
    af.write_json(target / "handoff.json", manifest)
    return {**manifest, "directory": str(target), "ok": True}


def read_input(af: Any, path: str) -> bytes:
    with Path(path).expanduser().open("rb") as stream:
        data = stream.read(MAX_TEXT_BYTES + 1)
    try:
        if len(data) <= MAX_TEXT_BYTES and data.decode("utf-8").strip() and b"\x00" not in data:
            return data
    except UnicodeError:
        pass
    raise af.FlowError("Return a nonempty UTF-8 file of at most 2 MiB", af.EXIT_USAGE)


def save_return(af: Any, directory: Path, run: dict, args: Any) -> dict:
    data = read_input(af, args.file)
    digest = af.sha256_bytes(data)
    with af.run_lock(directory, run):
        if run["state"] in PUBLICATION_STATES:
            raise af.FlowError("The publication or completion boundary owns this Run. Keep editing a local export or open a new revision.",
                               af.EXIT_WAITING, guidance(run))
        current = draft_item(af, run)
        current_hash = current["sha256"] if current else "none"
        if current:
            checked_bytes(af, directory, current)
        if digest == current_hash and current and current["type"] == DRAFT:
            return {"ok": True, "run_id": run["run_id"], "draft_sha256": digest, "idempotent": True,
                    "verification": "working_copy", "publication_authorized": False, **guidance(run)}
        if current_hash != args.base_sha256:
            raise af.FlowError("The Run's draft changed since export. Merge against a new export and return the merged Markdown.",
                               af.EXIT_WAITING, {"current_sha256": current_hash, **guidance(run)})
        path = directory / "artifacts" / f"working-draft-{digest}.md"
        af.immutable_write(path, data)
        af.record_artifact(directory, run, path, DRAFT, {"actor": "operator", "origin": "external_work",
                           "base_sha256": current_hash, "model_identity": "unverified", "human_original": False},
                           inputs=[current["artifact_id"]] if current else [], expected_bytes=data)
    return {"ok": True, "run_id": run["run_id"], "draft_sha256": digest, "verification": "working_copy",
            "publication_authorized": False, **guidance(run)}


def paragraphs(text: str) -> list[str]:
    return [part for part in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()) if part]


def claim_anchor(row: dict, parts: list[str]) -> str | None:
    # Transfer proof only when a literal, uniquely located claim is in the
    # exact same paragraph. A paraphrase, ambiguous location or changed link
    # needs review even if the source URL itself did not change.
    for field in ("allowed_wording", "exact_claim"):
        value = str(row.get(field) or "").strip()
        if len(value) < 16:
            continue
        matches = [part for part in parts if value in part]
        if len(matches) == 1:
            return matches[0]
    return None


def passed_claims(af: Any, directory: Path, run: dict) -> tuple[list[dict], str, str | None]:
    ok, error, _, events = af.verify_event_log(directory, run)
    if not ok:
        raise af.FlowError("Cannot establish prior claim verification", af.EXIT_INTEGRITY, error)
    items = {}
    baseline = [], "", None
    for event in events:
        if event["type"] != "ARTIFACT_RECORDED":
            continue
        item = event["payload"]["artifact"]
        items[(item["type"], item["sha256"])] = item
        kind = {"gate-receipt:G-POST-EDIT-CLAIMS": "post-edit-claim-ledger",
                "gate-receipt:G-CLAIMS-VERIFIED": "verified-claim-ledger"}.get(item["type"])
        if not kind:
            continue
        try:
            receipt = json.loads(checked_bytes(af, directory, item))
            if receipt.get("outcome") != "PASS" or receipt.get("evaluator", {}).get("simulation"):
                continue
            hashes = receipt.get("artifact_hashes", {})
            source_type = "article" if hashes.get("article") else "draft"
            source = items.get((source_type, hashes.get(source_type)))
            ledger = items.get((kind, hashes.get(kind)))
            if source and ledger:
                baseline = (json.loads(checked_bytes(af, directory, ledger))["claims"],
                            checked_bytes(af, directory, source).decode("utf-8"), item["sha256"])
        except (af.FlowError, OSError, ValueError):
            # An unavailable archived input cannot be used as evidence. Keep
            # the latest earlier proof whose bytes still check out.
            continue
    return baseline


def plan(af: Any, directory: Path, run: dict, text: str) -> tuple[dict, list[dict]]:
    previous_rows, previous_text, proof = passed_claims(af, directory, run)
    current_parts = paragraphs(text)
    previous_parts = paragraphs(previous_text)
    current_counts = Counter(current_parts)
    previous_counts = Counter(previous_parts)
    unchanged = current_counts & previous_counts
    carried = [row for row in previous_rows
               if row.get("disposition") in {"use", "qualify"}
               and (anchor := claim_anchor(row, previous_parts)) and unchanged[anchor] == 1
               and claim_anchor(row, current_parts) == anchor]
    kept_ids = {row["claim_id"] for row in carried}
    return {
        "prior_verification_receipt_sha256": proof,
        "carried_claim_ids": sorted(kept_ids),
        "claims_to_review": sorted({row["claim_id"] for row in previous_rows
                                   if row.get("disposition") in {"use", "qualify"}} - kept_ids),
        "changed_paragraphs": [index + 1 for index, part in enumerate(current_parts)
                               if current_counts[part] != unchanged[part]],
        "removed_or_changed_prior_paragraphs": sum((previous_counts - unchanged).values()),
        "coverage": "Review changed and new text for missing claims, qualify or omit unsupported statements, and retain exact source links. Carried claims refer to the prior dated verification.",
    }, carried


def check(af: Any, directory: Path, run: dict, args: Any) -> dict:
    item = draft_item(af, run)
    if not item:
        raise af.FlowError("Save a draft or return Markdown before checking claims", af.EXIT_WAITING, guidance(run))
    text = checked_bytes(af, directory, item).decode("utf-8")
    scope, carried = plan(af, directory, run, text)
    result = {
        "ok": True, "run_id": run["run_id"], "draft_sha256": item["sha256"], "scope": scope,
        "verification": "unchecked", "publication_authorized": False, **guidance(run),
    }
    if not args.ledger:
        return result
    submitted = json.loads(read_input(af, args.ledger))
    errors = af.validate_instance_schema(submitted, "claim-ledger.schema.json", run)
    if errors or submitted.get("run_id") != run["run_id"]:
        raise af.FlowError("Return a claim ledger for this Run", af.EXIT_USAGE, errors)
    provided = {row["claim_id"]: row for row in submitted["claims"]}
    if len(provided) != len(submitted["claims"]):
        raise af.FlowError("Claim ledger contains duplicate claim IDs", af.EXIT_USAGE)
    reusable = {row["claim_id"]: row for row in carried if row["claim_id"] not in provided}
    ledger = {**submitted, "claims": [*reusable.values(), *provided.values()]}
    with tempfile.TemporaryDirectory(prefix="article-flow-claim-review-") as scratch:
        ledger_path = Path(scratch) / "claims.json"
        af.write_json(ledger_path, ledger)
        _, findings = af.automatic_gate(directory, run, "POST_EDIT_CLAIM_VERIFICATION", ledger_path,
                                        verification_text=text, carried_claims=reusable)
    unchecked = sorted(set(scope["claims_to_review"]) - set(provided))
    # The check evaluates supplied rows and citations. It cannot infer that a
    # missing row was intentionally removed or that a new paragraph has no claims.
    result.update(verification="scoped_claim_check", unchecked_claim_ids=unchecked,
                  editorial_qa="unchecked", checked_claim_ids=sorted(provided),
                  needs_attention=bool(findings or unchecked),
                  findings=[{k: v for k, v in finding.items() if k != "artifact"} for finding in findings],
                  ledger=ledger)
    with af.run_lock(directory, run):
        current = draft_item(af, run)
        if not current or current["sha256"] != item["sha256"]:
            raise af.FlowError("Draft changed during claim review. Recheck the latest export.", af.EXIT_WAITING, guidance(run))
        digest = af.sha256_bytes(af.canonical_json(result))
        path = directory / "artifacts" / f"working-draft-check-{digest}.json"
        af.write_json_immutable(path, result)
        prior = af.artifact(run, CHECK)
        if not prior or prior["sha256"] != af.sha256_path(path):
            af.record_artifact(directory, run, path, CHECK, {"actor": "controller", "scope": "partial_claim_review"},
                               inputs=[current["artifact_id"]])
    return result


def active(af: Any, run: dict) -> bool:
    work = af.artifact(run, DRAFT)
    adoption = af.artifact(run, ADOPTION)
    article = af.artifact(run, "article")
    return bool(work and adoption and article and article["sha256"] == work["sha256"]
                and work["artifact_id"] in adoption.get("inputs", []))


def has_pending(af: Any, run: dict) -> bool:
    return bool(af.artifact(run, DRAFT) and not active(af, run))


def require_consistent_publication(af: Any, directory: Path, run: dict) -> None:
    if has_pending(af, run):
        raise af.FlowError("A newer working draft is ready for review. Resume verification on that exact draft before packaging or publishing.",
                           af.EXIT_WAITING, guidance(run))
    if not active(af, run):
        return
    article = af.artifact(run, "article")
    checked_bytes(af, directory, article)
    for gate, required in (
        ("G-POST-EDIT-CLAIMS", ("article", "post-edit-claim-ledger", "article-recipe")),
        ("G-EDITORIAL-QA", ("article", "brief", "article-recipe", "visual-plan", "visual-manifest",
                            "post-edit-claim-ledger", "editorial-qa", "style-policy")),
    ):
        if not verified_gate(af, directory, run, gate, required):
            raise af.FlowError("The returned manuscript still needs claim and editorial checks for the current inputs",
                               af.EXIT_WAITING, {"gate": gate, **guidance(run)})


def verified_gate(af: Any, directory: Path, run: dict, gate: str, required: tuple) -> bool:
    receipt = checked_json(af, directory, run, f"gate-receipt:{gate}")
    hashes = receipt.get("artifact_hashes", {})
    if receipt.get("outcome") != "PASS":
        return False
    for kind in required:
        item = af.artifact(run, kind)
        if not item or hashes.get(kind) != item["sha256"]:
            return False
        checked_bytes(af, directory, item)
    return True


def resume(af: Any, directory: Path, run: dict, args: Any) -> dict:
    supplied_plan = read_input(af, args.visual_plan) if args.visual_plan else None
    with af.run_lock(directory, run):
        work = af.artifact(run, DRAFT)
        if not work:
            raise af.FlowError("Return a working draft before resuming its verification", af.EXIT_USAGE, guidance(run))
        prior_plan = af.artifact(run, "visual-plan")
        same_plan = bool(supplied_plan and prior_plan and prior_plan["sha256"] == af.sha256_bytes(supplied_plan)
                         and work["artifact_id"] in prior_plan.get("inputs", []))
        if (supplied_plan is None or same_plan) and active(af, run) and run["state"] in {
            "VISUAL_PLAN", "VISUAL_RENDER", "POST_EDIT_CLAIM_VERIFICATION",
            "DISPLAY_REVISION", "EDITORIAL_QA", "PACKAGE", "PUBLISH_APPROVAL",
        }:
            return {"ok": True, "state": run["state"], "idempotent": True,
                    "next_command": ["article-flow", "next", run["run_id"], "--json"], **guidance(run)}
        if run["state"] in PUBLICATION_STATES or af.revision_import.enabled(af, run):
            raise af.FlowError("Resume the existing publication or revision owner. The returned draft remains available for a separately authorized revision.",
                               af.EXIT_WAITING, guidance(run))
        required = {"article-recipe", "brief", "claim-ledger"}
        missing = sorted(kind for kind in required if not af.artifact(run, kind))
        if (not af.editorial_context.enabled(run) or run["state"] not in REVIEW_STATES or missing
                or run.get("run_overrides", {}).get("model_release")):
            raise af.FlowError("Normal verification needs the current editorial brief and evidence context. Draft work and scoped checking can continue now.",
                               af.EXIT_WAITING, {"missing": missing, "state": run["state"], **guidance(run)})
        af.require_complete_research_amendment(directory, run)
        path = directory / work["path"]
        data = checked_bytes(af, directory, work)
        # Renew factual locks on the accepted manuscript. The EDIT code check
        # still enforces exact revision evidence, visual references and prose
        # rules. Changed facts receive a fresh full-ledger validation.
        index = [item for item in run["artifact_index"] if item["type"] not in {"locked-fields", "draft"}]
        projected = {**run, "artifact_index": [*index, {**work, "type": "draft"}]}
        _, findings = af.automatic_gate(directory, projected, "EDIT", path)
        if supplied_plan is not None:
            # The incoming plan's image references are checked against the
            # actual new manifest after render, before any normal verification.
            findings = [f for f in findings if f.get("criterion") != "unplanned_visual_reference"]
        if findings:
            raise af.FlowError("Working draft saved. Repair these publication-candidate findings or continue editing locally.",
                               af.EXIT_WAITING, {"findings": findings, **guidance(run)})
        destination = "POST_EDIT_CLAIM_VERIFICATION"
        plan_path = None
        if supplied_plan is not None:
            plan_hash = af.sha256_bytes(supplied_plan)
            plan_path = directory / "artifacts" / f"working-visual-plan-{plan_hash}.json"
            af.immutable_write(plan_path, supplied_plan)
            errors = af.validate_json_schema(plan_path, "visual-plan.schema.json", run)
            if errors:
                raise af.FlowError("Correct the returned visual plan against visual-plan.schema.json",
                                   af.EXIT_WAITING, {"findings": errors, **guidance(run)})
            _, plan_findings = af.automatic_gate(directory, projected, "VISUAL_PLAN", plan_path)
            if plan_findings:
                raise af.FlowError("Repair the returned visual plan or continue editing locally",
                                   af.EXIT_WAITING, {"findings": plan_findings, **guidance(run)})
            destination = "VISUAL_RENDER"
        elif not all(af.artifact(run, kind) for kind in ("visual-plan", "visual-manifest")):
            destination = "VISUAL_PLAN"
        if run["status"] == "WAITING_MODEL":
            packet = af.latest_task_packet_item(directory, run, run["state"])
            if packet:
                af.abandon_cached_packet(directory, run, run["state"], packet, {"reason": "working_draft_replaced_inputs"})
        if not af.artifact(run, "article") or af.artifact(run, "article")["sha256"] != work["sha256"]:
            af.record_artifact(directory, run, path, "article", {"actor": "operator", "origin": "external_work"},
                               inputs=[work["artifact_id"]], expected_bytes=data)
        if plan_path:
            af.record_artifact(directory, run, plan_path, "visual-plan", {"actor": "operator", "origin": "external_work"},
                               inputs=[work["artifact_id"]], expected_bytes=supplied_plan)
            af.write_gate_receipt(directory, run, "G-VISUAL-PLAN", "PASS", [],
                                  {"type": "code", "source": "outside_visual_plan_validation"})
        review_scope, carried = plan(af, directory, run, data.decode("utf-8"))
        adoption = {"draft_sha256": work["sha256"], "scope": review_scope, "carried_claims": carried,
                    "publication_authorized": False}
        adoption_hash = af.sha256_bytes(af.canonical_json(adoption))
        adoption_path = directory / "artifacts" / f"working-draft-adoption-{adoption_hash}.json"
        af.write_json_immutable(adoption_path, adoption)
        run.pop("pending_repair", None)
        if destination in af.MODEL_STATES:
            af.reset_attempt_window(directory, run, destination)
        af.transition(directory, run, destination, "operator",
                      "Returned manuscript is the current editorial candidate; recheck affected claims and QA")
        af.record_artifact(directory, run, adoption_path, ADOPTION, {"actor": "operator"}, inputs=[work["artifact_id"]])
    return {"ok": True, "state": run["state"], "verification": "pending", "publication_authorized": False,
            "outside_review": review_offer(af, directory, run),
            "next_command": ["article-flow", "next", run["run_id"], "--json"], **guidance(run)}


def review_basis(af: Any, directory: Path, run: dict, review: str) -> dict:
    stage, schema = REVIEW_SUBMISSIONS[review]
    inputs = af.packet_inputs(directory, run, stage)
    hashes = {item["id"]: item["sha256"] for item in inputs}
    for kind in ("effective-definitions", "editorial-repair-obligations", "working-draft-adoption"):
        item = af.artifact(run, kind)
        if item:
            checked_bytes(af, directory, item)
            hashes[kind] = item["sha256"]
    basis = {"run_id": run["run_id"], "review": review, "schema": schema, "inputs": hashes}
    return {**basis, "scope_sha256": af.sha256_bytes(af.canonical_json(basis))}


def review_offer(af: Any, directory: Path, run: dict) -> dict | None:
    if not active(af, run):
        return None
    review = {"POST_EDIT_CLAIM_VERIFICATION": "claims", "DISPLAY_REVISION": "qa",
              "EDITORIAL_QA": "qa"}.get(run["state"])
    if not review:
        return None
    try:
        basis = review_basis(af, directory, run, review)
    except (af.FlowError, OSError, ValueError) as exc:
        return {"review": review, "reason": str(exc), "repair_instruction": "Restore the named inputs or continue in the exported draft."}
    return {**basis, "command": ["article-flow", "work", "submit", run["run_id"], review, "--file",
                                 "<outside review JSON>", "--scope-sha256", basis["scope_sha256"], "--json"]}


def submit_review(af: Any, directory: Path, run: dict, args: Any) -> dict:
    data = read_input(af, args.file)
    value = json.loads(data)
    digest = af.sha256_bytes(data)
    stage, schema = REVIEW_SUBMISSIONS[args.review]
    with af.run_lock(directory, run):
        artifact_type, _ = af.stage_output(stage, run)
        gate = af.state_definition(stage, run)["gate"]
        existing = af.artifact(run, artifact_type)
        can_reconcile = {"POST_EDIT_CLAIM_VERIFICATION"} if args.review == "claims" else {"DISPLAY_REVISION", "EDITORIAL_QA"}
        if (active(af, run) and existing and existing["producer"].get("outside_sha256") == digest
                and existing["producer"].get("scope_sha256") == args.scope_sha256
                and verified_gate(af, directory, run, gate, ("article", artifact_type))):
            if run["state"] in can_reconcile:
                # The PASS receipt already committed this decision. A retry
                # only finishes the transition, unless any bound input moved.
                receipt = checked_json(af, directory, run, f"gate-receipt:{gate}")
                required = ("article-recipe", ADOPTION) if args.review == "claims" else (
                    "brief", "article-recipe", "visual-plan", "visual-manifest", "post-edit-claim-ledger"
                )
                if all(af.artifact(run, kind) and receipt["artifact_hashes"].get(kind) == af.artifact(run, kind)["sha256"]
                       for kind in required):
                    af.transition(directory, run, af.state_definition(stage, run)["next_on_pass"], "controller",
                                  "Reconciled the previously accepted outside assessment")
                    return {"ok": True, "state": run["state"], "idempotent": True, **guidance(run)}
            else:
                return {"ok": True, "state": run["state"], "idempotent": True, **guidance(run)}
        offer = review_offer(af, directory, run)
        if not offer or offer.get("review") != args.review or offer.get("scope_sha256") != args.scope_sha256:
            raise af.FlowError("The review scope changed or its evidence is pending. Export the current review basis.",
                               af.EXIT_WAITING, {"outside_review": offer, **guidance(run)})
        if run.get("repair_recovery_error"):
            raise af.FlowError("Reconcile the existing verification evidence before recording a reviewed result",
                               af.EXIT_INTEGRITY, run["repair_recovery_error"])
        errors = af.validate_instance_schema(value, schema, run)
        if errors or value.get("run_id") != run["run_id"]:
            raise af.FlowError("Correct the external review against the named schema and Run", af.EXIT_USAGE, errors)
        carried = {}
        if args.review == "claims":
            adoption = checked_json(af, directory, run, ADOPTION)
            by_id = {row["claim_id"]: row for row in value["claims"]}
            if len(by_id) != len(value["claims"]):
                raise af.FlowError("Claim ledger contains duplicate claim IDs", af.EXIT_USAGE)
            missing = set(adoption["scope"]["claims_to_review"]) - by_id.keys()
            if missing:
                raise af.FlowError("Review the earlier affected claims, including actual omissions", af.EXIT_WAITING,
                                   {"unchecked_claim_ids": sorted(missing), **guidance(run)})
            carried = {row["claim_id"]: row for row in adoption["carried_claims"] if row["claim_id"] not in by_id}
            value["claims"] = [*carried.values(), *by_id.values()]
            scoped = checked_json(af, directory, run, CHECK)
            if (scoped and not scoped.get("needs_attention", True) and scoped.get("ledger") == value
                    and scoped.get("draft_sha256") == adoption["draft_sha256"]
                    and scoped.get("scope") == adoption["scope"]):
                # The exact same code-checked rows and links were already
                # observed for this draft. This still validates the full ledger.
                carried = {row["claim_id"]: row for row in value["claims"]}
        else:
            # A returned assessment is evidence about the manuscript. This
            # path cannot establish that a human or calibrated model wrote it.
            value["calibration_status"] = "uncalibrated-advisory"
        review_hash = af.sha256_bytes(af.canonical_json(value))
        path = directory / "artifacts" / f"working-review-{review_hash}.json"
        af.write_json_immutable(path, value)
        _, findings = af.automatic_gate(directory, run, stage, path, carried_claims=carried)
        if findings:
            warning = {"stage": stage, "draft_sha256": af.artifact(run, DRAFT)["sha256"],
                       "scope_sha256": args.scope_sha256, "findings": findings}
            warning_path = directory / "artifacts" / f"working-review-warning-{af.sha256_bytes(af.canonical_json(warning))}.json"
            af.write_json_immutable(warning_path, warning)
            prior_warning = af.artifact(run, REVIEW_WARNING)
            if not prior_warning or prior_warning["sha256"] != af.sha256_path(warning_path):
                af.record_artifact(directory, run, warning_path, REVIEW_WARNING, {"actor": "controller"})
            raise af.FlowError("The outside assessment found or left open issues. Repair the affected material and return it.",
                               af.EXIT_WAITING, {"findings": findings, **guidance(run)})
        if review_basis(af, directory, run, args.review)["scope_sha256"] != args.scope_sha256:
            raise af.FlowError("The review inputs changed during assessment; retain the outside file and export the current basis",
                               af.EXIT_INTEGRITY, guidance(run))
        if run["status"] == "WAITING_MODEL":
            packet = af.latest_task_packet_item(directory, run, run["state"])
            if packet:
                af.abandon_cached_packet(directory, run, run["state"], packet, {"reason": "outside_review_supplied"})
        producer = {"actor": "operator", "origin": "external_review", "outside_sha256": digest,
                    "scope_sha256": args.scope_sha256, "model_identity": "unverified"}
        af.record_artifact(directory, run, path, artifact_type, producer,
                           inputs=[item["artifact_id"] for item in run["artifact_index"]
                                   if item["type"] in offer["inputs"]])
        if stage == "EDITORIAL_QA":
            af.editorial_context.record_assessment(af, directory, run, value, [], "PASS")
        af.write_gate_receipt(directory, run, gate, "PASS", [],
                              {"type": "code", "version": af.CONTROLLER_VERSION,
                               "source": "outside_review", "scope_sha256": args.scope_sha256})
        run.pop("pending_repair", None)
        destination = af.state_definition(stage, run)["next_on_pass"]
        af.transition(directory, run, destination, "controller", "Validated the returned review for the current draft")
    return {"ok": True, "state": run["state"], "accepted_review": args.review, "publication_authorized": False,
            "outside_review": review_offer(af, directory, run),
            "next_command": ["article-flow", "next", run["run_id"], "--json"], **guidance(run)}


def command(af: Any, args: Any) -> int:
    directory, run = af.load_run(args.run_id)
    try:
        if args.work_command == "export":
            result = write_export(af, directory, run, args)
        elif args.work_command == "import":
            result = save_return(af, directory, run, args)
        elif args.work_command == "check":
            result = check(af, directory, run, args)
        elif args.work_command == "submit":
            result = submit_review(af, directory, run, args)
        else:
            result = resume(af, directory, run, args)
    except (OSError, ValueError) as exc:
        raise af.FlowError(f"Draft work could not read or write its files: {exc}", af.EXIT_WAITING, guidance(run)) from exc
    af.emit(result, args.json)
    return af.EXIT_OK
