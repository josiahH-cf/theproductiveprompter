"""Typed, scoped editorial evidence; publication and AI choices never teach globally."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from editorial_context import digest


def store_proposal(af: Any, value: dict) -> dict:
    if value.get("decision_maker") not in {"human", "assistant", "unknown"}:
        raise ValueError("Record the actual decision maker")
    if value.get("scope") not in {"passage", "article", "register", "form", "core"}:
        raise ValueError("Feedback needs an explicit scope")
    # Human edits can be evidence of a local preference. Reasons inferred by AI stay pending.
    value = {**value, "schema_version": "1.0.0", "status": "pending", "activated": False,
             "evidence_kind": "explicit_preference" if value["decision_maker"] == "human" else "generated_interpretation"}
    record_id = "EP-" + digest(value)[:20]
    path = af.voice_state_root() / "proposals" / f"{record_id}.json"
    af.write_json_immutable(path, {**value, "record_id": record_id})
    return {"record_id": record_id, "path": str(path), "status": "pending", "activated": False}


def apply_local_selection(af: Any, directory: Path, run: dict) -> dict:
    probe = af.json_artifact(directory, run, "voice-probe") or {}
    selection = probe.get("operator_selection") or {}
    selected = next((c for c in probe.get("candidates", []) if c["candidate_id"] == selection.get("candidate_id")), None)
    if not selected:
        raise af.FlowError("Voice learning requires an explicit recorded candidate choice", af.EXIT_WAITING)
    profile = af.json_artifact(directory, run, "voice-profile")
    actor = selection.get("decision_maker", "human")
    proposal = store_proposal(af, {"run_id": run["run_id"], "decision_maker": actor, "scope": "passage",
                                 "before": probe.get("source_passage", ""), "after": selected["passage"],
                                 "reason": selection.get("feedback"), "reason_status": "recorded" if selection.get("feedback") else "pending",
                                 "source_sha256": af.artifact(run, "voice-probe")["sha256"],
                                 "bundled_choice": True, "rejected_generated_candidates_are_positive_evidence": False})
    local = {"schema_version": "2.0.0", "record_id": proposal["record_id"], "run_id": run["run_id"],
             "decision_maker": actor, "scope": "passage", "selected_candidate": selected,
             "reason": selection.get("feedback"), "reason_status": "recorded" if selection.get("feedback") else "pending",
             "profile_version": profile["version"], "profile_update": {"activated": False},
             "evidence_kind": "generated_passage_preference", "human_original": False,
             "rejected_candidates": "Not positive evidence; not proof of universal dislike"}
    local["prior_profile_version"] = profile["version"]
    local["new_profile_version"] = profile["version"]
    local["voice_probe_sha256"] = af.artifact(run, "voice-probe")["sha256"]
    with af.shared_lock(af.voice_state_root() / ".lock"):
        evidence_path = af.voice_state_root() / "evidence.jsonl"
        if not any(e.get("record_id") == local["record_id"] for e in af._read_jsonl(evidence_path)):
            af._append_jsonl(evidence_path, local)
    path = directory / "artifacts" / f"voice-learning-{local['record_id']}.json"
    af.write_json_immutable(path, local)
    recorded = af.artifact(run, "voice-learning")
    if not recorded or recorded["sha256"] != af.sha256_path(path):
        af.record_artifact(directory, run, path, "voice-learning", {"actor": actor, "version": af.CONTROLLER_VERSION})
    af.append_event(directory, run, "VOICE_LEARNING_PROPOSED", "controller", {"record_id": proposal["record_id"], "activated": False})
    af.write_gate_receipt(directory, run, "G-VOICE-LEARNING", "PASS", [], {"type": "code", "version": af.CONTROLLER_VERSION})
    af.transition(directory, run, "EDIT", "controller", "Use the bundled passage choice locally; reusable learning remains pending")
    af.save_run(directory, run)
    return {"ok": True, "learning": local, "proposal": proposal, "state": run["state"]}


def feedback(af: Any, args: Any) -> int:
    directory, run = af.load_run(args.run_id)
    if run.get("state") != "COMPLETE":
        raise af.FlowError("Article feedback requires a completed run", af.EXIT_USAGE)
    text = Path(args.feedback_file).read_text(encoding="utf-8").strip()
    if not text:
        raise af.FlowError("Feedback cannot be empty", af.EXIT_USAGE)
    result = store_proposal(af, {"run_id": run["run_id"], "decision_maker": getattr(args, "actor", "unknown"),
                                 "scope": "article", "outcome": args.outcome, "reason": text,
                                 "source_sha256": (af.artifact(run, "article") or {}).get("sha256"),
                                 "retire_only_source_run": run["run_id"] if args.outcome == "rejected" else None})
    af.emit({"ok": True, **result, "current_profile_changed": False}, args.json)
    return af.EXIT_OK


def migration_preview(profile: dict) -> dict:
    return {"profile_version": profile["version"], "read_only": True,
            "retained_human_original": [e.get("evidence_id") for e in profile.get("positive_examples", []) if e.get("evidence_kind") == "human_original"],
            "historical_only": {key: len(profile.get(key, [])) for key in ("provisional_guidance", "accepted_rejected_pairs", "change_history")},
            "untyped_positives_excluded": len([e for e in profile.get("positive_examples", []) if e.get("evidence_kind") != "human_original"]),
            "action": "Retain immutable records. New writer projections omit untyped history; do not convert it into human evidence."}


def activate_guide(af: Any, candidate: dict, authorization: str) -> dict:
    """Authorizes use, not a false human quality judgment. Rollback uses existing machinery."""
    if not authorization.strip():
        raise ValueError("Guide activation needs the actual user's authorization")
    errors = af.validate_instance_schema(candidate, "voice-profile.schema.json")
    if errors:
        raise ValueError(str(errors))
    with af.shared_lock(af.voice_state_root() / ".lock"):
        prior, _, _ = af._initialize_voice_runtime_locked()
        if prior["profile_id"] != candidate["profile_id"]:
            raise ValueError("The guide must belong to the installed author profile")
        existing = af._voice_profile_path_for_version(candidate["version"])
        if existing:
            saved = af.load_json(existing)
            activation = next((h for h in saved.get("change_history", []) if h.get("candidate_sha256")), {})
            ignored = {"parent_version", "status", "provenance_note", "base_profile_sha256", "change_history"}
            same = (activation["candidate_sha256"] == digest(candidate)) if activation else all(
                saved.get(k) == v for k, v in candidate.items() if k not in ignored)
            if not same:
                raise ValueError("A guide version is immutable; give the changed candidate a new version")
            pointer = {"voice_profile_pointer_schema_version": "1.0.0", "profile_id": saved["profile_id"],
                       "current_version": saved["version"], "profile_sha256": af.sha256_path(existing),
                       "updated_at": af.utc_now(), "source_learning_record_id": None, "previous_version": prior["version"]}
            if prior["version"] != saved["version"]:
                af.write_json(af.voice_state_root() / "current.json", pointer)
            return {"ok": True, "idempotent": prior["version"] == saved["version"], "reused_immutable_version": True,
                    "profile_version": saved["version"], "human_quality_judgment": "pending"}
        profile = copy.deepcopy(candidate)
        profile["parent_version"] = prior["version"]
        profile["status"] = "provisional"
        profile["provenance_note"] += " Use authorized by the author; cross-genre human calibration remains pending."
        profile["base_profile_sha256"] = af.sha256_path(af.baseline_voice_profile_path())
        profile.setdefault("change_history", []).append({"version": profile["version"], "date": af.utc_now()[:10],
                                                        "authorization": authorization, "candidate_sha256": digest(candidate),
                                                        "human_quality_judgment": "pending"})
        path = af.voice_state_root() / "profiles" / f"{af.slugify(profile['version'], 80)}-{digest(profile)[:12]}.json"
        af.write_json_immutable(path, profile)
        pointer = {"voice_profile_pointer_schema_version": "1.0.0", "profile_id": profile["profile_id"],
                   "current_version": profile["version"], "profile_sha256": af.sha256_path(path),
                   "updated_at": af.utc_now(), "source_learning_record_id": None, "previous_version": prior["version"]}
        af.write_json(af.voice_state_root() / "current.json", pointer)
        return {"ok": True, "profile_version": profile["version"], "previous_version": prior["version"],
                "profile_sha256": pointer["profile_sha256"], "human_quality_judgment": "pending"}


def accept_proposal(af: Any, proposal_id: str, confirmation: dict) -> dict:
    """An explicit human confirmation supplies rule, reason, scope, exceptions and regression evidence."""
    if Path(proposal_id).name != proposal_id or not proposal_id.startswith("EP-"):
        raise ValueError("Invalid proposal ID")
    proposal = af.load_json(af.voice_state_root() / "proposals" / f"{proposal_id}.json")
    required = {"decision_maker", "exact_human_response", "rule", "reason", "scope", "exceptions", "retained_example_check", "different_form_check"}
    if not required <= confirmation.keys() or confirmation["decision_maker"] != "human" or not all(confirmation[k] for k in required):
        raise ValueError("Reusable guidance requires actual human confirmation and two regression comparisons")
    if confirmation["scope"] not in {"core", "article", "register", "form"}:
        raise ValueError("Use core, article, register or form scope")
    if confirmation["scope"] in {"register", "form"} and not confirmation.get(confirmation["scope"]):
        raise ValueError("Name the specific register or form")
    with af.shared_lock(af.voice_state_root() / ".lock"):
        decision_path = af.voice_state_root() / "decisions" / f"{proposal_id}.json"
        if decision_path.exists():
            recorded = af.load_json(decision_path)
            if recorded["confirmation"] != confirmation:
                raise ValueError("The proposal already has a different immutable decision")
            return {"ok": True, "idempotent": True, "version": recorded["version"], "proposal_id": proposal_id, "reactivated": False}
        profile, _, pointer = af._initialize_voice_runtime_locked()
        profile = copy.deepcopy(profile)
        scoped = profile["author_voice"].setdefault("scoped_preferences", [])
        retire_ids = set(confirmation.get("retire_proposal_ids", []))
        if not retire_ids <= {p.get("proposal_id") for p in scoped}:
            raise ValueError("Cannot retire an unknown preference")
        scoped[:] = [p for p in scoped if p.get("proposal_id") not in retire_ids]
        # A rejection removes only preferences originating in that article, never all active guidance.
        if proposal.get("outcome") == "rejected":
            scoped[:] = [p for p in scoped if p.get("run_id") != proposal["run_id"]]
        if not any(p.get("proposal_id") == proposal_id for p in scoped):
            scoped.append({**confirmation, "text": confirmation["rule"], "status": "accepted", "proposal_id": proposal_id, "run_id": proposal["run_id"]})
        from editorial_context import compact_voice
        compact_voice(profile, run_id=proposal["run_id"])
        prior_version = profile["version"]
        profile["version"] = "guide-" + digest({"parent": prior_version, "proposal": proposal_id, "confirmation": confirmation})[:16]
        profile["parent_version"] = prior_version
        profile["status"] = "provisional"
        path = af.voice_state_root() / "profiles" / f"{profile['version']}-{digest(profile)[:12]}.json"
        af.write_json_immutable(path, profile)
        af.write_json(af.voice_state_root() / "current.json", {**pointer, "current_version": profile["version"],
                      "profile_sha256": af.sha256_path(path), "previous_version": prior_version, "updated_at": af.utc_now()})
        af.write_json_immutable(decision_path, {"confirmation": confirmation, "version": profile["version"]})
        return {"ok": True, "version": profile["version"], "proposal_id": proposal_id}
