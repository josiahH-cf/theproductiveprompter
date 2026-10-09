"""Small, evidence-backed writing context. History is deliberately not a prompt."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

VOICE_STAGES = {"INTENT_REVIEW", "ARTICLE_RECIPE", "BRIEF", "DRAFT", "VOICE_PROBE", "EDIT", "EDITORIAL_QA"}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def enabled(run: dict) -> bool:
    return tuple(int(x) for x in run.get("workflow_version", "0.0.0").split(".")[:2]) >= (3, 2)


def freeze(af: Any, directory: Path, run: dict) -> None:
    definitions = {
        "workflow": af.workflow(),
        "house_policy": af.load_json(af.SPEC_ROOT / "workflow/house-policy.json"),
        "schemas": {p.name: af.load_json(p) for p in sorted((af.SPEC_ROOT / "schemas").glob("*.json"))},
        "recipe_defaults": af.load_json(af.SPEC_ROOT / "workflow/article-recipe.defaults.json"),
    }
    run["definition_snapshot"] = {"value": definitions, "sha256": digest(definitions)}
    path = directory / "artifacts/effective-definitions.json"
    af.write_json_immutable(path, run["definition_snapshot"])
    af.record_artifact(directory, run, path, "effective-definitions", {"actor": "controller", "version": af.CONTROLLER_VERSION})


def definitions(run: dict) -> dict | None:
    snapshot = run.get("definition_snapshot")
    if not snapshot:
        return None
    if digest(snapshot["value"]) != snapshot.get("sha256"):
        raise ValueError("Frozen editorial definitions failed their integrity check")
    if snapshot["value"]["workflow"]["workflow_version"] != run["workflow_version"]:
        raise ValueError("Run version disagrees with its frozen definitions")
    return snapshot["value"]


def checked_json(af: Any, directory: Path, run: dict, kind: str) -> dict | None:
    path = af.artifact_path(directory, run, kind)
    item = af.artifact(run, kind)
    if not path or not item:
        return None
    if af.sha256_path(path) != item["sha256"]:
        raise af.FlowError(f"Editorial context source changed: {kind}", af.EXIT_INTEGRITY)
    return af.load_json(path)


def compact_voice(profile: dict, *, run_id: str, register: str = "", form: str = "") -> dict:
    """Only typed rules and confirmed original excerpts can enter the new writer path."""
    voice = profile.get("author_voice", {})
    rules = voice.get("operational_rules", [])
    examples = [e for e in profile.get("positive_examples", [])
                if e.get("evidence_kind") == "human_original" and e.get("authorship_confirmed") is True]
    preferences = [p for p in voice.get("scoped_preferences", [])
                   if p.get("status") == "accepted" and p.get("decision_maker") == "human"
                   and (p.get("scope") == "core"
                        or (p.get("scope") == "article" and p.get("run_id") == run_id)
                        or (p.get("scope") == "register" and p.get("register") == register and register)
                        or (p.get("scope") == "form" and p.get("form") == form and form))]
    if len(rules) > 10 or len(preferences) > 6:
        raise ValueError("Active guidance exceeds its budget; consolidate the guide before writing")
    result = {"profile_id": profile["profile_id"], "version": profile["version"],
              "status": profile["status"], "calibration": "human cross-genre judgment pending",
              "core_rules": rules, "scoped_preferences": preferences,
              "register_adjustments": voice.get("register_adjustments", {}),
              "authentic_excerpts": [{k: e[k] for k in ("evidence_id", "excerpt", "locator", "scope") if k in e}
                                     for e in examples[:4]],
              "preservation": "Preserve facts, qualifications, citations, quotes, code, meaning and authorized author position. Never fabricate experience or beliefs.",
              "excluded": "Trial-derived habits, candidate labels, article feedback, full history and unconfirmed generated positives"}
    if len(json.dumps(result, ensure_ascii=False).split()) > 1150:
        raise ValueError("Compact voice exceeds 1,150 words; simplify rather than silently truncating")
    return result


def contract(af: Any, directory: Path, run: dict) -> dict:
    seed = af.artifact_path(directory, run, "seed")
    request = af.artifact_path(directory, run, "revision-request")
    brief = checked_json(af, directory, run, "brief") or {}
    intent = checked_json(af, directory, run, "intent") or {}
    recipe = checked_json(af, directory, run, "article-recipe") or {}
    for kind, path in (("seed", seed), ("revision-request", request)):
        if path and af.sha256_path(path) != af.artifact(run, kind)["sha256"]:
            raise af.FlowError(f"Author constraint source changed: {kind}", af.EXIT_INTEGRITY)
    return {"schema_version": "1.0.0", "run_id": run["run_id"],
            "precedence": "current explicit author request > approved article decisions > workflow/house constraints > illustrative examples",
            "author_constraints": [{"origin": role, "sha256": af.sha256_path(path),
                                     "exact_text": path.read_text(encoding="utf-8"), "binding": True}
                                    for role, path in (("historical_seed", seed), ("current_revision_request", request)) if path],
            "reader": intent.get("reader", intent.get("audience", brief.get("audience"))),
            "reader_purpose": recipe.get("reader_job", intent.get("reader_job")),
            "authorized_position": intent.get("position", intent.get("author_position")),
            "register": recipe.get("register", brief.get("register", "article-specific")),
            "narrative_person": recipe.get("narrative_person"),
            "form": recipe.get("archetype"), "opening": recipe.get("opening"),
            "ending": recipe.get("ending"),
            "length_policy": "Recipe word bands are targets only unless the exact author request makes length binding. Never fail QA solely for missing a target.",
            "stopping_condition": "Reader can understand the supported reasoning or perform the requested task; remove redundant development.",
            "perspective_policy": "Use only the supplied author position or confirmed observations. AI angle suggestions are hypotheses until adopted; absence permits an evidence-led article.",
            "summary_ownership": "Public description belongs to DISPLAY_REVISION; final article controls its substance. TLDR and standalone summaries have separate reader jobs.",
            "conflict_policy": "Report a genuine binding conflict before writing. Preserve protected quotations/code; reopen verification rather than silently changing them."}


def binding_length_limits(af: Any, directory: Path, run: dict) -> dict:
    """Recognize explicit author bounds, never numbers supplied by a recipe/model."""
    limits = {}
    texts = []
    for kind in ("seed", "revision-request"):
        path = af.artifact_path(directory, run, kind)
        if path:
            if af.sha256_path(path) != af.artifact(run, kind)["sha256"]:
                raise af.FlowError("Author length source changed", af.EXIT_INTEGRITY)
            texts.append(path.read_text(encoding="utf-8"))
    author = checked_json(af, directory, run, "author-context") or {}
    texts.extend(r.get("exact_author_response", "") for r in author.get("responses", []))
    patterns = {
            "maximum": r"\b(?:at most|no more than|under|maximum(?: of)?|limit(?: it| the article)? to|keep (?:it|the article) (?:under|below))\s+(\d[\d,]*)\s+words\b",
            "minimum": r"\b(?:at least|no fewer than|minimum(?: of)?)\s+(\d[\d,]*)\s+words\b",
            "exact": r"\b(?:exactly|must (?:be|contain|have))\s+(\d[\d,]*)\s+words\b",
    }
    for text in texts:
        # Quoted examples and fenced/code material are source data. Recognize
        # only a narrow positive author instruction, never an embedded target.
        text = re.sub(r"(?s)```.*?```|~~~.*?~~~|`[^`]*`|\"[^\"]*\"|“[^”]*”", " ", text)
        for clause in re.split(r"[.!?;\n]", text):
            if re.search(r"\bno (?:fixed|binding|mandatory) (?:word|length)|\bno word band", clause, re.I):
                limits = {}
                continue
            guard = re.sub(r"\bno (?:more|fewer) than\b", "bounded", clause, flags=re.I)
            if re.search(r"\b(?:not|never|ignore|obsolete|retired|example|illustrative|suggested|recommended|target)\b|\bdo(?:es)?n['’]t\b", guard, re.I):
                continue
            for name, pattern in patterns.items():
                for match in re.finditer(pattern, clause, re.I):
                    limits[name] = {"words": int(match.group(1).replace(",", "")), "exact_author_excerpt": match.group(0)}
    return limits


def length_violations(af: Any, directory: Path, run: dict, text: str) -> list[dict]:
    count = len(re.findall(r"\b[\w'-]+\b", text))
    result = []
    for kind, bound in binding_length_limits(af, directory, run).items():
        target = bound["words"]
        if (kind == "maximum" and count > target) or (kind == "minimum" and count < target) or (kind == "exact" and count != target):
            result.append({"criterion": "binding_author_length", "artifact": "current-article", "location": None,
                           "finding": f"Article has {count} words; explicit author requirement: {bound['exact_author_excerpt']}",
                           "repair_instruction": "Meet the explicit author bound while preserving substance, or surface a material conflict.",
                           "repair_state": "EDIT"})
    return result


def advisory_length_finding(af: Any, directory: Path, run: dict, finding: dict) -> bool:
    criterion = str(finding.get("criterion", "")).lower()
    wording = str(finding.get("finding", "")).lower()
    is_target = (any(term in criterion for term in ("length", "word_count", "wordcount"))
                 and any(term in wording for term in ("word", "target", "minimum", "maximum")))
    if not is_target:
        return False
    # The controller checks actual author bounds separately. A model's numeric
    # recipe target never acquires authority from an unrelated binding bound.
    return criterion != "binding_author_length"


def obligation_id(finding: dict) -> str:
    return "ER-" + digest({k: finding.get(k) for k in ("criterion", "artifact", "location", "finding", "repair_instruction", "repair_state", "source_sha256")})[:16]


def positive_observation(finding: dict) -> bool:
    return bool(re.match(r"^no(?: article)? repair (?:is )?(?:required|needed|necessary)\b", str(finding.get("repair_instruction", "")).strip(), re.I))


def resolution_surface(af: Any, directory: Path, run: dict, finding: dict) -> tuple[str, str]:
    """The owner and named surface constrain where a resolution may cite evidence."""
    owner = finding.get("repair_state")
    named = " ".join(str(finding.get(k, "")) for k in ("artifact", "location", "criterion")).lower()
    if owner == "DISPLAY_REVISION":
        brief = checked_json(af, directory, run, "brief") or {}
        if "description" in named:
            return "brief.description", str(brief.get("description", ""))
        if "title" in named:
            return "brief.title", str(brief.get("title", ""))
        return "brief.title+description", str(brief.get("title", "")) + "\n" + str(brief.get("description", ""))
    if owner == "VISUAL_PLAN":
        plan = checked_json(af, directory, run, "visual-plan") or {}
        manifest = checked_json(af, directory, run, "visual-manifest") or {}
        return "visual-plan+manifest", json.dumps({"plan": plan, "manifest": manifest}, ensure_ascii=False)
    path = af.artifact_path(directory, run, "article")
    text = path.read_text(encoding="utf-8") if path else ""
    location = str(finding.get("location") or "").strip()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip() and not p.lstrip().startswith("#")]
    ordinals = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "first": 1, "second": 2, "third": 3}
    match = re.fullmatch(r"paragraph (\d+|one|two|three|four|five|six|first|second|third)(?:,\s*sentence (\d+))?", location, re.I)
    if match:
        number = ordinals.get(match.group(1).lower()) or int(match.group(1))
        text = paragraphs[number - 1] if 0 < number <= len(paragraphs) else ""
        if match.group(2):
            sentences = re.split(r"(?<=[.!?])\s+", text)
            sentence = int(match.group(2))
            text = sentences[sentence - 1] if 0 < sentence <= len(sentences) else ""
    elif location.lower() in {"opening", "opening paragraphs"}:
        text = "\n\n".join(paragraphs[:3])
    elif location:
        headings = list(re.finditer(r"(?m)^#{1,6}\s+" + re.escape(location) + r"\s*$", text))
        if len(headings) == 1:
            heading = headings[0]
            tail = text[heading.end():]
            next_heading = re.search(r"(?m)^#{1,6}\s+", tail)
            text = tail[:next_heading.start()] if next_heading else tail
        else:
            text = ""  # Unknown or ambiguous local locators must never widen to the whole body.
    return "article", text


def assessment_findings(af: Any, directory: Path, run: dict, value: dict) -> list[dict]:
    supplied = [f for f in value.get("findings", []) if isinstance(f, dict)]
    material = [{**f, "repair_state": af.editorial_repair_destination(f)} for f in supplied
                if not advisory_length_finding(af, directory, run, f)
                and not (value.get("outcome") == "PASS" and positive_observation(f))]
    previous = checked_json(af, directory, run, "editorial-repair-obligations") or {}
    dispositions = value.get("dimensions", {}).get("repair_resolution", {})
    for old in previous.get("pending", []):
        if positive_observation(old["finding"]):
            continue
        resolution = dispositions.get(old["id"], {})
        excerpt = str(resolution.get("excerpt", ""))
        surface, current_text = resolution_surface(af, directory, run, old["finding"])
        if not (resolution.get("status") == "PASS" and resolution.get("surface") == surface
                and resolution.get("finding_location") == old["finding"].get("location")
                and len(excerpt) >= 8 and excerpt in current_text
                and len(str(resolution.get("reason", ""))) >= 20):
            material.append(old["finding"])
    if value.get("outcome") != "PASS" and not supplied and not material:
        material.append({"criterion": "editorial_outcome", "artifact": "assessment", "location": None,
                         "finding": "Assessment rejects without an actionable finding", "repair_instruction": "Name the material issue or return PASS", "repair_state": "EDITORIAL_QA"})
    return list({obligation_id(f): f for f in material}.values())


def record_assessment(af: Any, directory: Path, run: dict, value: dict, findings: list[dict], outcome: str) -> None:
    previous = checked_json(af, directory, run, "editorial-repair-obligations") or {}
    prior = {obligation_id(o["finding"]): o for o in previous.get("pending", [])}
    pending = []
    if outcome != "PASS":
        for finding in findings:
            if finding.get("repair_state") == "EDITORIAL_QA":
                continue  # The retry must pass the assessment's own code checks.
            surface, text = resolution_surface(af, directory, run, finding)
            bound = {"source_sha256": digest({"surface": surface, "text": text})}
            pending.append(prior.get(obligation_id(finding)) or {"id": obligation_id({**finding, **bound}), "finding": finding, **bound})
    advisory = [f for f in value.get("findings", []) if isinstance(f, dict)
                and (advisory_length_finding(af, directory, run, f) or (value.get("outcome") == "PASS" and positive_observation(f)))]
    evidence = {"run_id": run["run_id"], "assessment_sha256": af.artifact(run, "editorial-qa")["sha256"],
                "pending": pending, "advisory": advisory, "resolutions": value.get("dimensions", {}).get("repair_resolution", {})}
    path = directory / "artifacts" / f"editorial-repair-obligations-{digest(evidence)[:16]}.json"
    af.write_json_immutable(path, evidence)
    af.record_artifact(directory, run, path, "editorial-repair-obligations", {"actor": "controller", "version": af.CONTROLLER_VERSION})


def prepare(af: Any, directory: Path, run: dict, state: str, inputs: list[dict]) -> list[dict]:
    if not enabled(run) or state not in VOICE_STAGES | {"DISPLAY_REVISION", "DEVELOPMENT_REVIEW"}:
        return inputs
    profile = checked_json(af, directory, run, "voice-profile") or {}
    local_contract = contract(af, directory, run)
    context = {"contract": local_contract,
               "voice": compact_voice(profile, run_id=run["run_id"], register=str(local_contract["register"]), form=str(local_contract["form"])),
               "local_selection": checked_json(af, directory, run, "voice-learning") or None}
    author_context = checked_json(af, directory, run, "author-context")
    if author_context:
        context["author_context"] = author_context
    obligations = checked_json(af, directory, run, "editorial-repair-obligations")
    if obligations and obligations.get("pending"):
        context["repair_obligations"] = obligations["pending"]
    frozen = definitions(run)
    if frozen:
        context["house_constraints"] = {"style_gate": frozen["house_policy"].get("style_gate", {}),
                                       "forbidden_characters": frozen["house_policy"]["voice"].get("forbidden_public_prose_characters", [])}
    # A selection records a bundled local preference, not a human-original example.
    path = directory / "artifacts" / f"editorial-context-{digest(context)[:16]}.json"
    af.write_json_immutable(path, context)
    if not any(i.get("sha256") == af.sha256_path(path) and i.get("type") == "editorial-context" for i in run["artifact_index"]):
        af.record_artifact(directory, run, path, "editorial-context", {"actor": "controller", "version": af.CONTROLLER_VERSION})
    projected = [i for i in inputs if i["id"] not in {"voice-profile", "voice-learning"}]
    projected.append({"id": "editorial-context", "path": str(path), "sha256": af.sha256_path(path)})
    return projected


def constraints(stage: str) -> list[str]:
    common = ["editorial-context is the sole active voice authority. Historical examples and labels are evidence only, never additional writing rules. Use one author with article-specific register; no fixed skeleton or persona.",
              "In assessments, findings contains only actionable defects. Put favorable observations in dimensions; a PASS should have no defect findings. Do not manufacture a repair from evidence that a requirement is already satisfied.",
              "Use supported body finding locations: paragraph N, paragraph N, sentence M, opening, or an exact unique heading. Paragraphs are nonempty blank-line-separated body blocks excluding headings; sentences split after terminal punctuation followed by whitespace. Use null only for a genuinely whole-article issue. Unknown, missing or ambiguous local passages cannot be resolved with evidence from elsewhere.",
              "Retain every repair_obligation. Address findings owned by this stage. In EDITORIAL_QA, dimensions.repair_resolution must map every pending ER ID to status PASS, the exact surface (article, brief.title, brief.description, brief.title+description, or visual-plan+manifest), finding_location copied from the finding, an exact excerpt from that CURRENT affected surface/passage, and a substantive reason, or report the unresolved finding. A later clean assessment cannot silently discard earlier concerns. Whole-body evidence cannot resolve a display issue.",
              "Distinguish binding author requirements from guidance targets. A publication gate or mechanical phrase check is not proof of author resemblance."]
    specific = {
        "INTENT_REVIEW": "Make the supplied author angle legible. Ask only a material question whose answer changes the article. Keep suggested angles distinct from actual views; do not require an interview.",
        "ARTICLE_RECIPE": "Choose form and register emphases for reader purpose; record register and the opening/development/ending voice_probe_target when useful. Compare recent actual prose moves when available. No quota of dimensions to vary; keeping a useful form is valid. Voice does not prescribe a universal opening or ending.",
        "BRIEF": "Carry exact author requirements and their source separately from interpretation. Name authorized perspective, reader outcome, factual limits and stopping condition. Description should reflect the actual argument, not a repeated generic promise.",
        "DRAFT": "Develop evidence, mechanism and consequence where needed. Give each section a distinct job. Supply authorized perspective now; a later conservative edit cannot invent it. Do not append a separate development review to the article.",
        "DEVELOPMENT_REVIEW": "Return a reverse outline and only material findings: section job, exact passage, missing connection or repetition, smallest repair. Examine the entire argument. Judge development separately from fluency and resemblance. No finding when a short explanation is sufficient.",
        "VOICE_PROBE": "Use the voice-anchor's structural job and claim set. Offer three local wording/cadence choices within the SAME requested register, not three personas. Do not change the opening strategy or infer a global trait from a choice. Candidates are bundled comparisons.",
        "EDIT": "Preserve effective distinctive phrasing and unaffected edits. Use current-article when supplied. Missing reasoning, evidence or author position belongs in DRAFT repair, never invented during polishing. Preserve the selected local passage's purpose and meaning rather than forcing it into another structural job.",
        "DISPLAY_REVISION": "Revise only title and description in this copy of the brief using the finished article. Preserve every other brief field exactly. Description must be supported by the final article and preserve scope. Do not change article body, slug or first publication date.",
        "EDITORIAL_QA": "Assess author resemblance (pending human judgment), clarity, facts and repetition separately. Preserve useful specificity. Identify exact passages. Classify findings as development, facts, display, visual or prose using criterion; do not fail a guidance-only word band. Do not call AI self-assessment human approval.",
    }
    return common + ([specific[stage]] if stage in specific else [])


def input_sections(packet: dict) -> list[str]:
    """Shared CLI/API renderer: one copy of identical bytes, all role aliases retained."""
    groups: dict[str, dict] = {}
    for item in packet.get("inputs", []):
        data = Path(item["path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"Task input changed: {item['id']}")
        group = groups.setdefault(item["sha256"], {"roles": [], "data": data})
        group["roles"].append(item["id"])
    sections = []
    for sha, group in groups.items():
        sections += ["", f"INPUT {', '.join(group['roles'])} sha256={sha}", group["data"].decode("utf-8")]
    return sections


def sync_skill(af: Any, user_root: Path, backup_root: Path) -> list[dict]:
    """Install the repository-owned global skill and reference, preserving prior bytes."""
    source = af.SPEC_ROOT.parent / ".agents/skills/article-flow"
    targets = [user_root / ".agents/skills/article-flow", user_root / ".claude/skills/article-flow"]
    codex_target = user_root / ".codex/skills/article-flow"
    if codex_target.exists():
        targets.append(codex_target)
    for target in targets:
        existing = target / "SKILL.md"
        if existing.exists() and "name: article-flow" not in existing.read_text(encoding="utf-8"):
            raise af.FlowError(f"Conflicting unmanaged skill at {target}", af.EXIT_INTEGRITY)
    results = []
    for target in targets:
        for relative in ("SKILL.md", "references/editorial.md"):
            incoming = (source / relative).read_bytes()
            destination = target / relative
            if destination.exists() and destination.read_bytes() != incoming:
                old = destination.read_bytes()
                old_hash = af.sha256_bytes(old)
                af.immutable_write(backup_root / "skill-backups" / old_hash / relative, old)
            af.write_if_changed(destination, incoming)
        results.append({"path": str(target), "sha256": af.sha256_path(target / "SKILL.md")})
    return results
