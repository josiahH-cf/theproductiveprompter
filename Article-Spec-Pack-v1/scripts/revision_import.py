"""Carry a supplied revision through the existing verification owners.

An external candidate is data, not a dispatched writer response, author evidence,
or an instruction to waive a gate. Its original bytes remain immutable.
"""
from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any


def enabled(af: Any, run: dict) -> bool:
    return (af.artifact(run, "external-revision-intake") is not None
            or af.artifact(run, "external-revision-candidate") is not None)


def checked(af: Any, directory: Path, run: dict, kind: str) -> tuple[Path, dict]:
    item = af.artifact(run, kind) or {}
    path = (directory / af.safe_relative(str(item.get("path", "")))).resolve()
    if (not path.is_relative_to(directory.resolve()) or not path.is_file()
            or af.sha256_path(path) != item.get("sha256")):
        raise af.FlowError(f"External revision evidence changed: {kind}", af.EXIT_INTEGRITY)
    return path, item


def install(af: Any, directory: Path, run: dict, source: dict) -> None:
    candidate = source["candidate"]
    intake = {"source_file_sha256": af.sha256_bytes(source["external_source_bytes"]),
              "candidate_sha256": af.sha256_bytes(candidate),
              "author_feedback_sha256": af.sha256_bytes(source["request"])}
    intake_path = directory / "artifacts/external-revision-intake.json"
    af.write_json_immutable(intake_path, intake)
    af.record_artifact(directory, run, intake_path, "external-revision-intake", {"actor": "controller"})
    path = directory / "artifacts/external-revision-candidate.md"
    af.immutable_write(path, candidate)
    item = af.record_artifact(directory, run, path, "external-revision-candidate",
                              {"actor": "external_assistant", "human_original": False,
                               "model_identity": "unverified", "preserved_verbatim": True},
                              expected_bytes=candidate)
    bindings = []
    for n, asset in enumerate(source.get("assets", [])):
        # Only the source reader resolves public paths and checks Git/live bytes.
        data = asset["bytes"]
        destination = directory / "artifacts/preserved-assets" / str(n)
        af.immutable_write(destination, data)
        value = {k: v for k, v in asset.items() if k != "bytes"}
        value.update(source_path=destination.relative_to(directory).as_posix(),
                     sha256=af.sha256_bytes(data), byte_size=len(data))
        bindings.append(value)
    record = {"external_revision_version": "1.0.0", "source": source["external_source"],
              "candidate_sha256": item["sha256"], "assets": bindings,
              "source_file_sha256": af.sha256_bytes(source["external_source_bytes"]),
              "author_feedback_sha256": af.sha256_bytes(source["request"]),
              "provenance": "Externally supplied GPT revision; exact model and client unverified; no human voice judgment."}
    receipt = directory / "artifacts/external-revision.json"
    af.write_json_immutable(receipt, record)
    af.record_artifact(directory, run, receipt, "external-revision", {"actor": "controller"}, inputs=[item["artifact_id"]])


def existing(af: Any, args: Any) -> tuple[Path, dict] | None:
    """Exact retries return their existing owner; they never resume a Stop."""
    try:
        source = Path(args.source_file).expanduser().resolve().read_bytes()
        candidate = Path(args.candidate_file).expanduser().resolve().read_bytes()
        request = Path(args.request_file).expanduser().resolve().read_bytes()
    except (OSError, TypeError):
        return None  # Typed preparation owns the useful input error.
    key = (af.sha256_bytes(source), af.sha256_bytes(candidate), af.sha256_bytes(request))
    for path in af.runs_root().glob("*/run.json"):
        directory, run = af.load_run(path.parent.name)
        intake_kind = "external-revision-intake" if af.artifact(run, "external-revision-intake") else "external-revision"
        intake_item = af.artifact(run, intake_kind)
        if not intake_item:
            continue
        # Read only the bounded identity before inspecting this owner's other
        # evidence. A damaged unrelated import cannot hold another article.
        try:
            intake_path, _ = checked(af, directory, run, intake_kind)
            value = af.load_json(intake_path)
        except (af.FlowError, OSError):
            candidate_item = af.artifact(run, "external-revision-candidate") or {}
            request_item = af.artifact(run, "revision-request") or {}
            if (candidate_item.get("sha256"), request_item.get("sha256")) == key[1:]:
                raise af.FlowError("Matching external revision has damaged intake evidence; reconcile its original Run",
                                   af.EXIT_INTEGRITY, {"run_id": run["run_id"], "action": "reconciliation_required"})
            continue
        if key == (value.get("source_file_sha256"), value["candidate_sha256"], value["author_feedback_sha256"]):
            if not af.artifact(run, "external-revision"):
                raise af.FlowError("This exact external revision has an interrupted installation; reconcile its existing Run before continuing",
                                   af.EXIT_INTEGRITY, {"run_id": run["run_id"], "action": "reconciliation_required"})
            record(af, directory, run)
            return directory, run
    return None


def record(af: Any, directory: Path, run: dict) -> dict:
    path, _ = checked(af, directory, run, "external-revision")
    value = af.load_json(path)
    candidate, item = checked(af, directory, run, "external-revision-candidate")
    request, request_item = checked(af, directory, run, "revision-request")
    if (value["candidate_sha256"] != item["sha256"]
            or value["author_feedback_sha256"] != request_item["sha256"]
            or value["source"]["source_html_sha256"] != run["revision"]["source_html_sha256"]):
        raise af.FlowError("External candidate/source/feedback binding changed", af.EXIT_INTEGRITY)
    for asset in value["assets"]:
        path = (directory / af.safe_relative(asset["source_path"])).resolve()
        if (not path.is_relative_to(directory.resolve()) or not path.is_file()
                or af.sha256_path(path) != asset["sha256"] or path.stat().st_size != asset["byte_size"]):
            raise af.FlowError("Preserved revision asset changed", af.EXIT_INTEGRITY)
    return value


def assets(af: Any, directory: Path, run: dict) -> list[dict]:
    return record(af, directory, run)["assets"] if enabled(af, run) else []


def assert_current_assets(af: Any, run: dict) -> None:
    if not enabled(af, run):
        return
    directory = af.run_dir(run["run_id"])
    repository = af.publication_repo_root(required=True)
    for asset in assets(af, directory, run):
        relative = af.safe_relative(asset["public_path"].lstrip("/"))
        path = (repository / relative).resolve()
        if not path.is_relative_to(repository.resolve()) or not path.is_file():
            raise af.FlowError("Revision asset is missing or escapes the publication repository", af.EXIT_INTEGRITY)
        committed = af.git(["show", f"HEAD:{relative.as_posix()}"], cwd=repository, binary=True)
        status, live, _ = af.fetch_url(urllib.parse.urljoin(run["revision"]["canonical_url"], asset["public_path"]))
        if (not isinstance(committed, bytes) or path.read_bytes() != committed
                or af.sha256_bytes(committed) != asset["sha256"] or status != 200 or live != committed):
            raise af.FlowError("Published revision asset changed since GPT's source snapshot", af.EXIT_INTEGRITY)


def public_handoff(af: Any, rendered: bytes, markdown: bytes, metadata: dict) -> dict:
    """Only already-public prose and identity; never author feedback or run paths."""
    markdown = af.external_revision.public_markdown(af, markdown)
    target = af.load_json(af.SPEC_ROOT / "publication/theproductiveprompter.json")
    source = {"revision_source_version": "1.0.0", "canonical_url": target["canonical_url"].format(slug=metadata["slug"]),
              "slug": metadata["slug"], "title": metadata["title"],
              "original_published_timestamp": metadata["date_iso"],
              "source_html_sha256": af.sha256_bytes(rendered), "source_markdown_sha256": af.sha256_bytes(markdown),
              "source_commit": None, "source_observed_at": af.utc_now()}
    return {"source": source, "article_markdown": markdown.decode("utf-8")}


def block(af: Any, directory: Path, run: dict, findings: list[dict]) -> None:
    run["status"] = "BLOCKED"
    af.append_event(directory, run, "ESCALATION", "controller",
                    {"reason": "external_candidate_conflict", "state": run["state"],
                     "findings": findings, "candidate_preserved": True})
    af.save_run(directory, run)


def adopt(af: Any, directory: Path, run: dict) -> bool:
    """Validate and carry bytes; never impersonate a model task or repair prose."""
    if not enabled(af, run) or run["state"] not in {"DRAFT", "EDIT", "VISUAL_PLAN"}:
        return False
    state = run["state"]
    record(af, directory, run)
    definition = af.state_definition(state, run)
    accepted = af.artifact(run, f"external-revision-acceptance:{state}")
    if accepted:
        ok, error, _, events = af.verify_event_log(directory, run)
        if not ok:
            raise af.FlowError("External revision acceptance history changed", af.EXIT_INTEGRITY, error)
        recorded = next((event for event in events if event.get("type") == "ARTIFACT_RECORDED"
                         and (event.get("payload", {}).get("artifact") or {}).get("artifact_id") == accepted["artifact_id"]), None)
        left_stage = recorded and any(event.get("type") == "STATE_TRANSITION"
                                      and event["sequence"] > recorded["sequence"]
                                      and event.get("payload", {}).get("from") == state for event in events)
        if recorded and not left_stage:
            # A committed acceptance whose transition was interrupted can finish
            # under its original identity. A later return to the same stage is a
            # downstream conflict, not a reason to replay the carry.
            path, _ = checked(af, directory, run, f"external-revision-acceptance:{state}")
            receipt = af.load_json(path)
            gate, _ = checked(af, directory, run, "gate-receipt:" + definition["gate"])
            output_type = {"DRAFT": "draft", "EDIT": "article", "VISUAL_PLAN": "visual-plan"}[state]
            output, _ = checked(af, directory, run, output_type)
            if (receipt["candidate_sha256"] != af.artifact(run, "external-revision-candidate")["sha256"]
                    or receipt["gate_receipt_sha256"] != af.sha256_path(gate)
                    or receipt["output_sha256"] != af.sha256_path(output)
                    or af.load_json(gate).get("outcome") != "PASS"):
                raise af.FlowError("Interrupted external carry lost its acceptance binding", af.EXIT_INTEGRITY)
            af.transition(directory, run, definition["next_on_pass"], "controller", "Finish the original committed external carry")
            return True
        # A return to an already-carried stage reflects a downstream failure.
        block(af, directory, run, [{"criterion": "external_candidate_conflict", "finding":
              "A downstream check requires changes to the supplied candidate. Return its findings to GPT in a new source-bound revision."}])
        return True
    af.revision_sources.assert_unchanged_source(af, run)
    if state == "VISUAL_PLAN":
        value = {"visual_plan_schema_version": "1.0.0", "run_id": run["run_id"], "visuals": [],
                 "omission_reason": "This prose revision preserves the existing published illustrations in place and introduces no new diagrams."}
        destination = directory / "artifacts/external-visual-plan.json"
        af.write_json_immutable(destination, value)
        output_type = "visual-plan"
    else:
        source, _ = checked(af, directory, run, "external-revision-candidate" if state == "DRAFT" else "draft")
        destination = directory / ("artifacts/external-draft.md" if state == "DRAFT" else "artifacts/external-article.md")
        af.immutable_write(destination, source.read_bytes())
        output_type = "draft" if state == "DRAFT" else "article"
    outcome, findings = af.automatic_gate(directory, run, state, destination)
    item = af.record_artifact(directory, run, destination, output_type,
                              {"actor": "external_assistant", "human_original": False,
                               "source": "validated_external_candidate", "model_identity": "unverified"},
                              inputs=[af.artifact(run, "external-revision-candidate")["artifact_id"]])
    gate = af.write_gate_receipt(directory, run, definition["gate"], outcome, findings,
                                 {"type": "code", "version": af.CONTROLLER_VERSION},
                                 state if outcome != "PASS" else None)
    if outcome != "PASS":
        block(af, directory, run, findings)
        return True
    receipt = directory / f"receipts/external-revision-{state.lower()}.json"
    af.write_json_immutable(receipt, {"state": state, "output_sha256": item["sha256"],
                                     "gate_receipt_sha256": af.sha256_path(gate),
                                     "candidate_sha256": af.artifact(run, "external-revision-candidate")["sha256"]})
    af.record_artifact(directory, run, receipt, f"external-revision-acceptance:{state}", {"actor": "controller"})
    af.transition(directory, run, definition["next_on_pass"], "controller", "Validated external revision carried without rewriting")
    return True


def provenance(af: Any, directory: Path, run: dict) -> dict:
    value = record(af, directory, run)
    hashes = []
    accepted = []
    for state in ("DRAFT", "EDIT"):
        path, item = checked(af, directory, run, f"external-revision-acceptance:{state}")
        receipt = af.load_json(path)
        gate_kind = "gate-receipt:" + af.state_definition(state, run)["gate"]
        gate, _ = checked(af, directory, run, gate_kind)
        gate_value = af.load_json(gate)
        output_kind = "draft" if state == "DRAFT" else "article"
        output, output_item = checked(af, directory, run, output_kind)
        # Visual materialization may create a later draft from the accepted
        # external draft. The immutable carry receipt still identifies its
        # original bytes, rather than retroactively claiming model authorship.
        if state == "DRAFT":
            output = directory / "artifacts/external-draft.md"
            output_item = {"sha256": af.sha256_path(output)}
        if (receipt["candidate_sha256"] != value["candidate_sha256"]
                or gate_value["outcome"] != "PASS"
                or receipt["gate_receipt_sha256"] != af.sha256_path(gate)
                or receipt["output_sha256"] != output_item["sha256"]
                or gate_value["artifact_hashes"].get(output_kind) != output_item["sha256"]):
            raise af.FlowError("External writing acceptance disagrees with its checked output/gate", af.EXIT_INTEGRITY)
        hashes.append(item["sha256"])
        accepted.append({"stage": state, "output_sha256": output_item["sha256"], "gate_receipt_sha256": af.sha256_path(gate)})
    return {"run_id": run["run_id"], "source_receipt_hashes": hashes, "agent_hosted_acceptances": [],
            "external_revision_acceptances": accepted, "evidence_kind": "validated_external_assistant_candidate",
            "limits": value["provenance"]}


def offer(af: Any, run: dict) -> dict:
    if run.get("state") != "COMPLETE":
        return {}
    url = (run.get("publication") or {}).get("url")
    slug = (run.get("revision") or {}).get("slug")
    if not slug and url:
        slug = url.rsplit("/", 1)[-1].removesuffix(".html")
    source_url = None
    if url and slug:
        directory = af.run_dir(run["run_id"])
        source = directory / "package/site/docs" / f"{slug}.revision.json"
        package_path = directory / "package/package.json"
        if source.is_file() and package_path.is_file():
            package = af.load_json(package_path)
            if any(item.get("path") == f"site/docs/{slug}.revision.json" and item.get("sha256") == af.sha256_path(source)
                   for item in package.get("public_files", [])):
                source_url = url.removesuffix(".html") + ".revision.json"
    return {"optional_revision": {"optional": True, "prompt_trigger": ":article-flow-revision",
              "blog_url": "https://theproductiveprompter.com/docs/blog.html", "article_url": url,
              "source_url": source_url,
              "export_command": ["article-flow", "revision-export", "--published-slug", slug, "--output-dir", "<private handoff directory>", "--json"] if slug else None,
              "message": "Publication is complete. If you want edits, use :article-flow-revision in GPT and return its Markdown with your exact feedback. Otherwise there is nothing more to do."}}
