"""One copyable GPT return, unpacked into separate immutable backend inputs."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def parse(af: Any, data: bytes) -> dict:
    try:
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("handoff exceeds 2 MiB")
        text = data.decode("utf-8-sig")
        openings = list(re.finditer(r"(?m)^(`{3,}|~{3,})article-flow-revision[ \t]*\r?$", text))
        if openings:
            if len(openings) != 1:
                raise ValueError("return exactly one article-flow-revision block")
            opening = openings[0]
            closing = re.search(r"(?m)^" + re.escape(opening[1]) + r"[ \t]*\r?$", text[opening.end():])
            if not closing:
                raise ValueError("handoff block is not closed")
            text = text[opening.end():opening.end() + closing.start()]
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("duplicate JSON field: " + key)
                result[key] = value
            return result
        value = json.loads(text, object_pairs_hook=pairs)
        required = {"article_flow_revision_version", "source", "candidate_markdown", "author_feedback"}
        if not isinstance(value, dict) or not required <= set(value) or set(value) - required - {"visual_plan"}:
            raise ValueError("unexpected or missing handoff fields")
        if value["article_flow_revision_version"] != "1.0.0":
            raise ValueError("unsupported handoff version")
        if not isinstance(value["source"], dict):
            raise ValueError("source must be the unchanged identity object")
        for key in ("candidate_markdown", "author_feedback"):
            if not isinstance(value[key], str) or not value[key].strip():
                raise ValueError(key + " must be a nonempty string")
        def check_text(item):
            if isinstance(item, str) and any(ord(char) < 32 and char not in "\r\n\t" for char in item):
                raise ValueError("unsupported control character")
            if isinstance(item, dict):
                for key, child in item.items():
                    check_text(key); check_text(child)
            elif isinstance(item, list):
                for child in item:
                    check_text(child)
        check_text(value)
        return value
    except (UnicodeError, ValueError, TypeError) as exc:
        raise af.FlowError(f"Invalid Article Flow revision handoff: {exc}", af.EXIT_USAGE) from exc


def unpack(af: Any, args: Any) -> Any:
    if any(getattr(args, field, None) for field in ("source_file", "candidate_file", "request_file", "visual_plan_file",
                                                   "source_run_id", "published_slug", "expected_source_sha256")):
        raise af.FlowError("--handoff-file supplies all revision inputs; do not combine input variants", af.EXIT_USAGE)
    value = parse(af, af.external_revision.read_utf8(af, args.handoff_file, "GPT revision handoff"))
    root = (af.runtime_home() / "revision-imports").resolve()
    directory = (root / af.sha256_bytes(af.canonical_json(value))).resolve()
    if not directory.is_relative_to(root):
        raise af.FlowError("Revision handoff storage escapes its private root", af.EXIT_INTEGRITY)
    directory.mkdir(parents=True, exist_ok=True)
    result = argparse.Namespace(**vars(args))
    for field, name, data in (
        ("source_file", "source.json", af.canonical_json(value["source"])),
        ("candidate_file", "candidate.md", value["candidate_markdown"].encode("utf-8")),
        ("request_file", "feedback.md", value["author_feedback"].encode("utf-8")),
    ):
        path = directory / name
        if path.is_symlink():
            raise af.FlowError("Revision import file is a symbolic link", af.EXIT_INTEGRITY)
        af.immutable_write(path, data)
        setattr(result, field, str(path))
    if "visual_plan" in value:
        path = directory / "visual-plan.json"
        if path.is_symlink():
            raise af.FlowError("Revision visual plan is a symbolic link", af.EXIT_INTEGRITY)
        af.immutable_write(path, af.canonical_json(value["visual_plan"]))
        result.visual_plan_file = str(path)
    return result


def visual_plan(af: Any, args: Any, candidate: bytes, slug: str) -> tuple[dict | None, bytes | None]:
    path = getattr(args, "visual_plan_file", None)
    if not path:
        return None, None
    data = af.external_revision.read_utf8(af, path, "Revision visual plan")
    try:
        value = json.loads(data)
        if (not isinstance(value, dict) or set(value) != {"visuals", "replace_assets"}
                or not isinstance(value["replace_assets"], list)
                or any(not isinstance(item, str) for item in value["replace_assets"])
                or len(set(value["replace_assets"])) != len(value["replace_assets"])):
            raise ValueError("visual_plan requires visuals and unique replace_assets")
        plan = {"visual_plan_schema_version": "1.0.0", "run_id": "preflight", "visuals": value["visuals"]}
        errors = af.validate_instance_schema(plan, "visual-plan.schema.json")
        if errors:
            raise ValueError("; ".join(errors))
        public_body = af.external_revision.public_markdown(af, candidate).decode("utf-8")
        keys = [af.visual_block_key(block) for block in re.split(r"\n\s*\n", public_body.strip())]
        ids = set()
        for visual in value["visuals"]:
            if visual["visual_id"] in ids or visual.get("claim_ids") or len(visual.get("design_rationale", "")) < 40:
                raise ValueError("unique visual IDs, empty claim_ids and an explicit design_rationale are required")
            ids.add(visual["visual_id"])
            if keys.count(af.visual_anchor_key(visual["placement"])) != 1:
                raise ValueError("diagram placement must match one unique candidate heading or prose paragraph")
            af.render_visual_svg(visual)
        paths = {f"/assets/articles/{slug}/{visual_id}.svg" for visual_id in ids}
        if set(value["replace_assets"]) - paths:
            raise ValueError("each replacement must have a matching controller-rendered visual ID for this article")
        return value, data
    except (ValueError, TypeError, KeyError) as exc:
        raise af.FlowError(f"Invalid revision visual plan: {exc}", af.EXIT_USAGE) from exc


def public_visuals(af: Any, directory: Path, run: dict) -> list[dict]:
    plan = af.json_artifact(directory, run, "visual-plan") or {}
    manifest = af.json_artifact(directory, run, "visual-manifest") or {}
    paths = {item["visual_id"]: item["public_path"] for item in manifest.get("assets", [])}
    fields = ("visual_id", "kind", "title", "placement", "alt_text", "caption", "labels", "edges")
    result = [{**{key: item[key] for key in fields if key in item}, "public_path": paths[item["visual_id"]]}
              for item in plan.get("visuals", []) if item["visual_id"] in paths]
    if af.revision_import.enabled(af, run):
        value = af.revision_import.record(af, directory, run)
        if "source_visuals_sha256" in value:
            source, _ = af.revision_import.checked(af, directory, run, "external-revision-source-visuals")
            occupied = {item["public_path"] for item in result} | set(value.get("replaced_assets", []))
            body_path = af.artifact_path(directory, run, "article") or af.artifact_path(directory, run, "external-revision-candidate")
            public_body = af.external_revision.public_markdown(af, body_path.read_bytes()).decode("utf-8") if body_path else ""
            blocks = re.split(r"\n\s*\n", public_body.strip()) if public_body else []
            keys = [af.visual_block_key(block) for block in blocks]
            for item in af.load_json(source)["visuals"]:
                if item["public_path"] in occupied:
                    continue
                kept = {key: child for key, child in item.items() if key != "placement"}
                images = [index for index, block in enumerate(blocks) if re.fullmatch(
                    r"\s*!\[[^\]]*\]\(" + re.escape(item["public_path"]) + r"\)\s*", block)]
                if len(images) == 1:
                    index = images[0] - 1
                    if index >= 0 and blocks[index].strip() == "### " + item["title"]:
                        index -= 1
                    if index >= 0:
                        key = keys[index]
                        if keys.count(key) == 1 and (key[0] == "after_heading" or not re.match(
                                r"^\s*(?:#|!\[|```|~~~|>|[-*+]\s|\d+[.)]\s|\|)", blocks[index])):
                            kept["placement"] = {key[0]: re.sub(r"^#{2,6}\s+", "", blocks[index].strip())}
                result.append(kept)
    return result
