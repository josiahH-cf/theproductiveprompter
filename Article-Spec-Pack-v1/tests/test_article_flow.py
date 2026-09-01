from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SPEC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPEC_ROOT / "scripts"))
import article_flow as af  # noqa: E402


def namespace(**values):
    defaults = {
        "json": True,
        "selection": None,
        "feedback": None,
        "finding": None,
        "artifact": None,
        "route": None,
        "canary": False,
        "redirect_to": None,
        "title": None,
        "description": None,
        "article": None,
    }
    defaults.update(values)
    return argparse.Namespace(**defaults)


def call(function, **values):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = function(namespace(**values))
    output = stream.getvalue().strip()
    return code, json.loads(output) if output else None


class TemporaryRuntime(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name) / "runtime"
        self.environment = mock.patch.dict(os.environ, {"ARTICLE_FLOW_HOME": str(self.runtime), "ARTICLE_FLOW_RUNS_ROOT": str(self.runtime / "runs"), "ARTICLE_FLOW_TEST_NO_PUBLISH": "1"}, clear=False)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.integrity = mock.patch.object(af, "check_manifest", return_value={"ok": True, "source": "test", "failures": []})
        self.integrity.start()
        self.addCleanup(self.integrity.stop)


class AuthorityTests(unittest.TestCase):
    def test_machine_authority_and_generated_view_are_consistent(self):
        result = subprocess.run([sys.executable, str(SPEC_ROOT / "scripts" / "render_workflow_docs.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("\u2014", (SPEC_ROOT / "1-Master" / "Article-Workflow-v2.md").read_text(encoding="utf-8"))
        workflow = json.loads((SPEC_ROOT / "workflow" / "workflow.json").read_text())
        self.assertTrue(workflow["authority"])
        self.assertEqual(workflow["precedence"], ["run_overrides", "approved_article_recipe", "workflow_schema", "house_policy", "examples"])
        rules = {item["id"]: item["text"] for item in workflow["rules"]}
        self.assertIn("no grammatical person is universal", rules["AF-PERSON-001"])
        self.assertIn("house bands are never pass/fail gates", rules["AF-LENGTH-001"])
        self.assertIn("Do not require a universal article skeleton", rules["AF-SHAPE-001"])
        self.assertIn("U+2014", rules["AF-CHAR-001"])
        house_policy = json.loads((SPEC_ROOT / "workflow" / "house-policy.json").read_text())
        configured_characters = {
            item["character"]: {"name": item["name"], "codepoint": item["codepoint"]}
            for item in house_policy["voice"]["forbidden_public_prose_characters"]
        }
        self.assertEqual(configured_characters, af.FORBIDDEN_PUBLIC_PROSE_CHARACTERS)
        lint = af.normative_lint()
        self.assertTrue(lint["ok"], lint["issues"])
        self.assertEqual(lint["conflicting_normative_statement_count"], 0)

    def test_global_command_is_the_only_host_entrypoint(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = af.main([])
        payload = json.loads(stream.getvalue())
        self.assertEqual(code, af.EXIT_OK)
        self.assertEqual(payload["interface"], "local-global-command")
        self.assertEqual(payload["command"], "article-flow")
        self.assertEqual(payload["start_command"][:2], ["article-flow", "capture"])
        self.assertIn("local command execution", payload["capability_requirement"])
        self.assertFalse((SPEC_ROOT / "adapters" / "start-article" / "SKILL.md").exists())
        self.assertFalse((SPEC_ROOT / "adapters" / "registry.json").exists())
        self.assertFalse((SPEC_ROOT / "0-START-ARTICLE.md").exists())
        repository = af.publication_repo_root() or SPEC_ROOT.parent
        copilot = repository / ".github" / "copilot-instructions.md"
        if copilot.is_file():
            self.assertNotIn("article-flow", copilot.read_text(encoding="utf-8"))
        help_text = af.build_parser().format_help()
        self.assertNotIn("entrypoint", help_text)
        self.assertNotIn("kickoff", help_text)
        self.assertNotIn("adapters", help_text)

    def test_every_legacy_rule_document_has_machine_readable_redirect(self):
        registry = json.loads((SPEC_ROOT / "workflow" / "document-registry.json").read_text())
        for item in registry["non_authoritative_documents"]:
            text = (SPEC_ROOT / item["path"]).read_text(encoding="utf-8")[:800]
            self.assertIn("article_flow_authority: false", text, item["path"])
            self.assertIn(f"article_flow_document_status: {item['status']}", text, item["path"])
            self.assertIn(f'article_flow_removal_version: "{item["removal_version"]}"', text, item["path"])

    def test_all_json_and_json_schemas_parse(self):
        for path in SPEC_ROOT.rglob("*.json"):
            with self.subTest(path=path):
                json.loads(path.read_text(encoding="utf-8"))
        health = af.schema_health()
        self.assertTrue(health["ok"], [item for item in health["checks"] if not item["ok"]])


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.spec = self.repo / "Article-Spec-Pack-v1"
        (self.spec / "workflow").mkdir(parents=True)
        (self.spec / "schemas").mkdir(parents=True)
        shutil.copy2(SPEC_ROOT / "schemas" / "manifest.schema.json", self.spec / "schemas" / "manifest.schema.json")
        self.control = self.spec / "workflow" / "control.json"
        self.control.write_text('{"value":1}\n', encoding="utf-8")
        protected = {
            "protected_set_schema_version": "1.0.0",
            "workflow_version": "test",
            "watched_roots": ["workflow"],
            "excluded_prefixes": [],
            "entries": [
                {"path": "workflow/control.json", "role": "normative", "rule_set": "test"},
                {"path": "workflow/protected-paths.json", "role": "runtime", "rule_set": "integrity"},
            ],
        }
        (self.spec / "workflow" / "protected-paths.json").write_text(json.dumps(protected, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "core.autocrlf", "false"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "add", "Article-Spec-Pack-v1/workflow"], check=True)
        self.patches = [
            mock.patch.object(af, "SPEC_ROOT", self.spec),
            mock.patch.object(af, "REPO_ROOT", self.repo),
            mock.patch.object(af, "MANIFEST_PATH", self.spec / "manifest.json"),
            mock.patch.object(af, "PROTECTED_PATHS_PATH", self.spec / "workflow" / "protected-paths.json"),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        payload = af.manifest_payload_from_index()
        af.write_json(self.spec / "manifest.json", payload)
        subprocess.run(["git", "-C", str(self.repo), "add", "Article-Spec-Pack-v1/manifest.json"], check=True)

    def test_hash_mutation_delete_unexpected_and_restoration(self):
        self.assertTrue(af.check_manifest("index")["ok"])
        original = self.control.read_bytes()
        self.control.write_bytes(original + b" ")
        failure = af.check_manifest("worktree")
        self.assertFalse(failure["ok"])
        self.assertIn("hash_mismatch", {item["kind"] for item in failure["failures"]})
        self.control.write_bytes(original)
        self.assertTrue(af.check_manifest("worktree")["ok"])
        self.control.unlink()
        self.assertIn("missing_file", {item["kind"] for item in af.check_manifest("worktree")["failures"]})
        self.control.write_bytes(original)
        unexpected = self.spec / "workflow" / "unexpected.json"
        unexpected.write_text("{}\n", encoding="utf-8")
        self.assertIn("unexpected_protected_file", {item["kind"] for item in af.check_manifest("worktree")["failures"]})

    def test_algorithm_and_traversal_are_rejected(self):
        manifest = json.loads((self.spec / "manifest.json").read_text())
        manifest["hash_algorithm"] = "md5"
        af.write_json(self.spec / "manifest.json", manifest)
        self.assertIn("hash_algorithm", {item["kind"] for item in af.check_manifest("worktree")["failures"]})
        with self.assertRaises(af.FlowError):
            af.safe_relative("../outside")


class RunAndSmokeTests(TemporaryRuntime):
    def start(self, seed="A small idea about reliable article workflows."):
        code, payload = call(af.command_start, seed=seed, seed_file=None, slug=None)
        self.assertEqual(code, af.EXIT_OK)
        # This module is the frozen 2.0 regression suite. New 3.0 behavior lives
        # in test_article_flow_v3.py; pin these runs to the bundled authority so
        # its historical human-gate and state-order assertions remain meaningful.
        directory, run = af.load_run(payload["run_id"])
        run["workflow_version"] = "2.0.0"
        run["run_overrides"].update({
            "automation_mode": "manual",
            "intent_approval": "required",
            "recipe_approval": "required",
            "editorial_approval": "required",
        })
        af.save_run(directory, run)
        return payload["run_id"]

    def write_submission(self, run_id, state, value, suffix="json"):
        path = self.runtime / f"{state.lower()}.{suffix}"
        if suffix == "json":
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        else:
            path.write_text(value, encoding="utf-8")
        return call(af.command_submit, run_id=run_id, stage=state, file=str(path))

    def next(self, run_id):
        return call(af.command_next, run_id=run_id)

    def gate(self, run_id, gate_id, **extra):
        return call(af.command_gate, run_id=run_id, gate_id=gate_id, outcome="PASS", **extra)

    def walk_to_package(self):
        run_id = self.start()
        _, first = self.next(run_id)
        _, second = self.next(run_id)
        self.assertEqual(first["task_packet"], second["task_packet"])
        directory, run = af.load_run(run_id)
        self.assertEqual(run["attempts"]["RESEARCH_PLAN"], 1)
        self.write_submission(run_id, "RESEARCH_PLAN", {
            "research_plan_schema_version": "1.0.0", "run_id": run_id,
            "questions": [{"question": "What changed?", "why_it_matters": "It bounds the article.", "intent_changing": True}],
            "source_strategy": ["Use the repository and direct primary documentation."], "claim_risks": [], "no_search_behavior": "not-applicable",
        })
        self.next(run_id)
        ledger = {"claim_ledger_schema_version": "1.0.0", "run_id": run_id, "generated_at": af.utc_now(), "claims": []}
        self.write_submission(run_id, "RESEARCH", ledger)
        self.next(run_id)
        self.write_submission(run_id, "INTENT_REVIEW", {
            "intent_schema_version": "1.0.0", "run_id": run_id, "reader": "A person building a repeatable article flow", "reader_job": "Understand the proof boundary", "purpose": "Show how the checks fit together", "scope": "One MVP and its checks", "position": None,
            "explicit_seed_content": ["reliable article workflows"], "assumptions": [], "remaining_unknowns": [], "research_that_shaped_candidate": [],
        })
        self.gate(run_id, "G-INTENT-FIDELITY")
        self.next(run_id)
        self.write_submission(run_id, "ARTICLE_RECIPE", {
            "recipe_version": "1.0.0", "status": "candidate", "archetype": "case-study", "reader_job": "Understand the proof boundary", "scope_boundary": "The MVP, not a platform comparison",
            "length": {"mode": "brief", "target_words": {"minimum": 500, "maximum": 900}, "stop_when": "The reader can explain the checks."},
            "opening": {"strategy": "artifact", "reason": "The URL makes the result inspectable."}, "ending": {"strategy": "decision-rule", "reason": "The reader needs a reusable rule."},
            "summary": {"policy": "never", "form": None}, "narrative_person": "mixed", "evidence_posture": "documentary", "citation_mode": "links",
            "components": {"diagram": "off", "checklist": "optional", "mental_models": "off", "workflow_count": None, "activation_header": "off"},
            "outline_candidates": [{"id": "artifact-first"}, {"id": "failure-first"}], "selection_reason": "Artifact-first serves the reader job with the available evidence.",
            "recent_post_comparison": {"observed": [], "unknowns": ["older recipe metadata unavailable"]},
            "variation_budget": {"macro_dimensions": ["archetype", "opening"], "recent_post_comparison": True, "experiment_seed": "smoke-1"},
        })
        self.gate(run_id, "G-RECIPE-FIT")
        self.next(run_id)
        self.write_submission(run_id, "BRIEF", {
            "brief_schema_version": "1.0.0", "run_id": run_id, "title": "A Test Article", "slug": "a-test-article", "description": "A bounded test of the article workflow.", "date": "2026-08-18", "tags": ["workflow"],
            "reader_job": "Understand the proof boundary", "scope": "One MVP", "exclusions": ["provider rankings"], "claims_to_support": [], "acceptance_criteria": ["The package is reproducible."],
        })
        self.next(run_id)
        self.write_submission(run_id, "VOICE_PROBE", {
            "voice_probe_schema_version": "1.0.0", "run_id": run_id, "article_register": {"technical_depth": "moderate"},
            "candidates": [{"candidate_id": "A", "passage": "The page is live, and the hash tells us which page.", "intended_dimensions": ["directness"]}, {"candidate_id": "B", "passage": "A live page only proves something when its bytes match.", "intended_dimensions": ["precision"]}],
            "comparison_orders": [["A", "B"], ["B", "A"]], "held_out_plan": "Retest the chosen trait on a field note.", "operator_selection": None,
        })
        self.gate(run_id, "G-VOICE-PROBE", selection="A", feedback="It is more direct without overstating the result.")
        self.next(run_id)
        article = "# A Test Article\n\nThe page is live, and the hash tells us which page.\n\n## What the check proves\n\nThe package keeps public output separate from private receipts.\n"
        self.write_submission(run_id, "DRAFT", article, suffix="md")
        self.next(run_id)
        self.write_submission(run_id, "CLAIM_VERIFICATION", ledger)
        self.next(run_id)
        self.write_submission(run_id, "EDIT", article, suffix="md")
        self.next(run_id)
        self.write_submission(run_id, "POST_EDIT_CLAIM_VERIFICATION", ledger)
        self.next(run_id)
        dimensions = {key: {} for key in ["intent_fidelity", "clarity_utility", "voice_fit", "naturalness", "public_surface_voice", "structural_interest", "proportional_length"]}
        self.write_submission(run_id, "EDITORIAL_QA", {"editorial_assessment_schema_version": "1.0.0", "run_id": run_id, "outcome": "PASS", "dimensions": dimensions, "findings": [], "calibration_status": "uncalibrated-advisory"})
        self.gate(run_id, "G-EDITORIAL-QA")
        directory, run = af.load_run(run_id)
        self.assertEqual(run["state"], "PACKAGE")
        return run_id

    def test_similar_slugs_are_collision_safe(self):
        first = self.start("Same seed")
        second = self.start("Same seed")
        self.assertNotEqual(first, second)
        self.assertNotEqual(af.run_dir(first), af.run_dir(second))
        code, status = call(af.command_status, run_id=None)
        self.assertEqual(code, af.EXIT_OK)
        self.assertEqual(status["run_id"], second)

    def test_capture_and_list_make_raw_ideas_easy_to_find(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = af.main(["capture", "A sentence that could become an article.", "--json"])
        self.assertEqual(code, af.EXIT_OK)
        captured = json.loads(stream.getvalue())
        code, listing = call(af.command_list)
        self.assertEqual(code, af.EXIT_OK)
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["runs"][0]["run_id"], captured["run_id"])
        self.assertEqual(listing["runs"][0]["seed_preview"], "A sentence that could become an article.")
        self.assertEqual(Path(listing["captured_material_root"]), af.runs_root())

    def test_public_display_text_is_linted_and_can_be_amended_without_rewind(self):
        run_id = self.walk_to_package()
        with self.assertRaises(af.FlowError) as caught:
            call(af.command_amend, run_id=run_id, title=None, description="At its core, this is not a magic spell.")
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        self.assertIn("public_surface_voice", {item["criterion"] for item in caught.exception.details})
        with self.assertRaises(af.FlowError) as caught:
            call(af.command_amend, run_id=run_id, title=None, description="A bounded test\u2014with a forbidden separator.")
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        self.assertIn("forbidden_public_prose_character", {item["criterion"] for item in caught.exception.details})
        call(af.command_amend, run_id=run_id, title=None, description="A bounded test of the article workflow.")
        code, packaged = call(af.command_package, run_id=run_id)
        self.assertEqual(code, af.EXIT_OK, packaged)

    def test_em_dash_is_rejected_in_draft_edit_and_package_defense(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        candidate = Path(self.temp.name) / "candidate.md"
        candidate.write_text("# Test\n\nOne clause\u2014another clause.\n", encoding="utf-8")
        for state in ("DRAFT", "EDIT"):
            outcome, findings = af.automatic_gate(directory, run, state, candidate)
            self.assertEqual(outcome, "REPAIR")
            self.assertIn("forbidden_public_prose_character", {item["criterion"] for item in findings})

        packaged_run = self.walk_to_package()
        packaged_directory, packaged_state = af.load_run(packaged_run)
        article_path = af.artifact_path(packaged_directory, packaged_state, "article")
        self.assertIsNotNone(article_path)
        article_path.write_text("# A Test Article\n\nOne clause\u2014another clause.\n", encoding="utf-8")
        with self.assertRaises(af.FlowError) as caught:
            call(af.command_package, run_id=packaged_run)
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        self.assertIn("forbidden_public_prose_character", {item["criterion"] for item in caught.exception.details})

    def test_bounded_article_amendment_revalidates_downstream_stages(self):
        run_id = self.walk_to_package()
        invalid = Path(self.temp.name) / "invalid-amendment.md"
        invalid.write_text("# A Test Article\n\nOne clause\u2014another clause.\n", encoding="utf-8")
        with self.assertRaises(af.FlowError) as caught:
            call(af.command_amend, run_id=run_id, article=str(invalid))
        self.assertIn("forbidden_public_prose_character", {item["criterion"] for item in caught.exception.details})

        directory, run = af.load_run(run_id)
        current = af.artifact_path(directory, run, "article")
        revised = Path(self.temp.name) / "revised-amendment.md"
        revised.write_text(
            current.read_text(encoding="utf-8").replace(
                "The page is live, and the hash tells us which page.",
                "The page is live. Its hash identifies the exact page.",
            ),
            encoding="utf-8",
        )
        code, amended = call(af.command_amend, run_id=run_id, article=str(revised))
        self.assertEqual(code, af.EXIT_OK, amended)
        self.assertTrue(amended["article_changed"])
        self.assertEqual(amended["state"], "POST_EDIT_CLAIM_VERIFICATION")
        directory, run = af.load_run(run_id)
        self.assertEqual(af.artifact_path(directory, run, "article").read_text(encoding="utf-8"), revised.read_text(encoding="utf-8"))

    def test_review_regate_same_file_terminal_and_targeted_repairs_are_safe(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        af.transition(directory, run, "INTENT_REVIEW", "test", "exercise unchanged approval")
        candidate = directory / "artifacts" / "approved-intent.json"
        af.write_json(candidate, {"intent_schema_version": "1.0.0", "run_id": run_id})
        af.record_artifact(directory, run, candidate, "intent-candidate", {"actor": "test"})
        code, gated = call(af.command_gate, run_id=run_id, gate_id="G-INTENT-FIDELITY", outcome="PASS")
        self.assertEqual(code, af.EXIT_OK, gated)
        self.assertEqual(gated["state"], "ARTICLE_RECIPE")
        directory, run = af.load_run(run_id)
        af.transition(directory, run, "CLAIM_VERIFICATION", "test", "exercise safe terminal")
        run["attempts"]["CLAIM_VERIFICATION"] = 3
        run["route_failures"]["CLAIM_VERIFICATION"] = {"only:route": 2}
        af.save_run(directory, run)
        code, repaired = call(af.command_repair, run_id=run_id, gate_id="G-CLAIMS-VERIFIED", finding="Retry only the failed verification.")
        self.assertEqual(code, af.EXIT_OK, repaired)
        _, run = af.load_run(run_id)
        self.assertEqual(run["attempts"]["CLAIM_VERIFICATION"], 0)
        self.assertNotIn("CLAIM_VERIFICATION", run["route_failures"])
        code, ended = call(af.command_gate, run_id=run_id, gate_id="G-CLAIMS-VERIFIED", outcome="TERMINAL")
        self.assertEqual(code, af.EXIT_OK, ended)
        self.assertEqual(ended["state"], "TERMINAL")
        self.assertEqual(af.state_definition("CLAIM_VERIFICATION")["repair_state"], "CLAIM_VERIFICATION")
        self.assertEqual(af.state_definition("EDITORIAL_QA")["repair_state"], "EDIT")

    def test_only_route_verification_discloses_its_independence_limit(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        draft = directory / "artifacts" / "draft.md"
        draft.write_text("# Draft\n", encoding="utf-8")
        af.record_artifact(directory, run, draft, "draft", {
            "actor": "model_or_host",
            "route": {"provider": "only", "model": "route"},
        })
        ledger = directory / "artifacts" / "claim-ledger.json"
        af.write_json(ledger, {"claim_ledger_schema_version": "1.0.0", "run_id": run_id, "generated_at": af.utc_now(), "claims": []})
        af.record_artifact(directory, run, ledger, "claim-ledger", {"actor": "model_or_host"})
        af.transition(directory, run, "CLAIM_VERIFICATION", "test", "exercise disclosed same-route fallback")
        only_route = {
            "provider": "only", "model": "route", "model_version": "1", "kind": "agent-hosted",
            "eligible": True, "evaluation_score": None, "exclusions": [],
        }
        selection = {
            "stage": "CLAIM_VERIFICATION", "required_capabilities": ["research"],
            "candidates": [only_route], "chosen": only_route, "fallbacks": [],
            "reason": "the only eligible route", "configuration_path": "test",
        }
        with mock.patch.object(af, "route_candidates", return_value=selection):
            _, packet = af.task_packet(directory, run)
        self.assertTrue(packet["selected_route"]["independence_waiver"]["required"])

    def test_transport_impossible_is_not_misreported_as_a_broken_source(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        run["state"] = "CLAIM_VERIFICATION"
        ledger = self.runtime / "transport-ledger.json"
        ledger.write_text(json.dumps({
            "claim_ledger_schema_version": "1.0.0",
            "run_id": run_id,
            "generated_at": af.utc_now(),
            "claims": [{
                "claim_id": "C1", "exact_claim": "A supported claim.", "class": "fact", "risk": "medium",
                "source_tier": "primary", "source_url_or_local_id": "https://example.com/source",
                "source_title_and_publisher": "Example", "exact_locator_or_supporting_excerpt": "Supporting text",
                "checked_at": af.utc_now(), "freshness_horizon": "one year", "contradiction_status": "none_found",
                "allowed_wording": "A supported claim.", "confidence": 0.8, "disposition": "use"
            }],
        }), encoding="utf-8")
        with mock.patch.object(af, "fetch_url", return_value=(0, b"", {})):
            outcome, findings = af.automatic_gate(directory, run, "CLAIM_VERIFICATION", ledger)
        self.assertEqual(outcome, "PASS", findings)
        self.assertNotIn("source_resolution", {item["criterion"] for item in findings})

    def test_publish_preflight_creates_one_handoff_and_attestation_resumes(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        fake_repo = Path(self.temp.name) / "publication-repo"
        (fake_repo / "docs").mkdir(parents=True)
        (fake_repo / "index.html").write_text("index", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(fake_repo)], check=True)
        subprocess.run(["git", "-C", str(fake_repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(fake_repo), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(fake_repo), "add", "index.html"], check=True)
        subprocess.run(["git", "-C", str(fake_repo), "commit", "-qm", "base"], check=True)
        base_commit = subprocess.check_output(["git", "-C", str(fake_repo), "rev-parse", "HEAD"], text=True).strip()
        fake_remote = Path(self.temp.name) / "publication-remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(fake_remote)], check=True)
        subprocess.run(["git", "-C", str(fake_repo), "remote", "add", "origin", str(fake_remote)], check=True)
        subprocess.run(["git", "-C", str(fake_repo), "push", "-q", "origin", "HEAD:main"], check=True)
        revision = "a" * 64
        af.write_json(directory / "package" / "package.json", {"package_revision": revision, "public_files": []})
        published_hash = af.sha256_path(fake_repo / "index.html")
        plan = {
            "run_id": run_id,
            "target": "theproductiveprompter",
            "base_commit": base_commit,
            "package_revision": revision,
            "changes": [{"path": "index.html", "current_sha256": published_hash, "planned_sha256": published_hash, "action": "modify"}],
        }
        plan_path = directory / "publication" / "plan.json"
        af.write_json(plan_path, plan)
        approval_id = "AP-test"
        approval = {
            "publication_receipt_schema_version": "1.0.0", "run_id": run_id, "target": "theproductiveprompter",
            "package_revision": revision, "approval_id": approval_id, "plan_sha256": af.sha256_path(plan_path),
            "expires_at": "2099-01-01T00:00:00Z", "status": "APPROVED", "commit": None, "url": None,
            "checks": [], "created_at": af.utc_now(),
        }
        approval_path = directory / "approvals" / f"{approval_id}.json"
        af.write_json(approval_path, approval)
        af.record_artifact(directory, run, approval_path, "publish-approval", {"actor": "operator"})
        af.transition(directory, run, "PUBLISH", "test", "exercise capability handoff")
        with (
            mock.patch.dict(os.environ, {"ARTICLE_FLOW_TEST_NO_PUBLISH": ""}, clear=False),
            mock.patch.object(af, "publication_repo_root", return_value=fake_repo),
            mock.patch.object(af, "publication_push_preflight", return_value={"ok": False, "reason": "no credentials"}),
        ):
            code, handoff = call(af.command_publish_execute, run_id=run_id, approval=approval_id, commit=True, push=True)
            self.assertEqual(code, af.EXIT_WAITING, handoff)
            self.assertEqual(handoff["action"], "human_action")
            self.assertTrue(Path(handoff["handoff"]).is_file())
            _, current = af.load_run(run_id)
            action = af.next_state_payload(directory, current)
            self.assertEqual(action["action"], "human_action")
            (fake_repo / "local-only.txt").write_text("not deployed", encoding="utf-8")
            subprocess.run(["git", "-C", str(fake_repo), "add", "local-only.txt"], check=True)
            subprocess.run(["git", "-C", str(fake_repo), "commit", "-qm", "local only"], check=True)
            local_only_commit = subprocess.check_output(["git", "-C", str(fake_repo), "rev-parse", "HEAD"], text=True).strip()
            with self.assertRaises(af.FlowError) as caught:
                call(af.command_deployment_attest, run_id=run_id, remote_rev=local_only_commit)
            self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
            code, attested = call(af.command_deployment_attest, run_id=run_id, remote_rev=base_commit)
        self.assertEqual(code, af.EXIT_OK, attested)
        self.assertEqual(attested["state"], "LIVE_VERIFICATION")

    def test_expired_unchanged_publication_approval_can_be_renewed(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        revision = "b" * 64
        af.write_json(directory / "package" / "package.json", {"package_revision": revision, "public_files": []})
        plan = {"run_id": run_id, "target": "theproductiveprompter", "base_commit": "c" * 40, "package_revision": revision, "changes": []}
        plan_path = directory / "publication" / "plan.json"
        af.write_json(plan_path, plan)
        expired_id = "AP-expired"
        expired = {
            "publication_receipt_schema_version": "1.0.0", "run_id": run_id, "target": "theproductiveprompter",
            "package_revision": revision, "approval_id": expired_id, "plan_sha256": af.sha256_path(plan_path),
            "expires_at": "2020-01-01T00:00:00Z", "status": "APPROVED", "commit": None, "url": None,
            "checks": [], "created_at": af.utc_now(),
        }
        expired_path = directory / "approvals" / f"{expired_id}.json"
        af.write_json(expired_path, expired)
        af.record_artifact(directory, run, expired_path, "publish-approval", {"actor": "operator"})
        old_handoff = directory / "publication" / "handoff-ap-expired.json"
        af.write_json(old_handoff, {
            "handoff_schema_version": "1.0.0", "status": "AWAITING_OPERATOR_DEPLOY", "run_id": run_id,
            "package_revision": revision, "reason": "no credentials", "created_commit": None, "changed_paths": [],
            "retry_command": ["article-flow", "publish", "--execute", run_id, "--approval", expired_id, "--commit", "--push"],
            "attestation_command": ["article-flow", "deployment-attest", run_id, "--remote-rev", "REMOTE_COMMIT"],
            "instructions": [], "created_at": af.utc_now(),
        })
        af.record_artifact(directory, run, old_handoff, "publication-handoff", {"actor": "controller"})
        af.transition(directory, run, "PUBLISH", "test", "exercise explicit unchanged-scope renewal")
        action = af.next_state_payload(directory, run)
        self.assertEqual(action["action"], "human_decision")
        self.assertIn("--renew-approval", action["approval_command"])
        code, renewed = call(af.command_publish_renew_approval, run_id=run_id)
        self.assertEqual(code, af.EXIT_OK, renewed)
        self.assertEqual(renewed["renewed_from"], expired_id)
        self.assertNotEqual(renewed["approval_id"], expired_id)
        _, current = af.load_run(run_id)
        latest = af.json_artifact(directory, current, "publish-approval")
        self.assertEqual(latest["approval_id"], renewed["approval_id"])
        self.assertEqual(latest["checks"][-1], {"renewed_from": expired_id, "scope_unchanged": True})
        latest_handoff = af.json_artifact(directory, current, "publication-handoff")
        self.assertIn(renewed["approval_id"], latest_handoff["retry_command"])
        self.assertNotEqual(Path(renewed["handoff"]), old_handoff)
        self.assertTrue(old_handoff.is_file())
        self.assertEqual(current["state"], "PUBLISH")

    def test_task_packet_is_complete_and_schema_rejects_hidden_context(self):
        run_id = self.start()
        _, action = self.next(run_id)
        packet_path = Path(action["task_packet"])
        packet = json.loads(packet_path.read_text())
        for field in ["workflow_version", "run_id", "stage", "attempt", "objective", "inputs", "reader_job", "article_recipe", "allowed_tools", "side_effect_policy", "constraints", "expected_outputs", "success_criteria", "non_authorities", "stop_conditions", "escalation_question"]:
            self.assertIn(field, packet)
        packet.pop("escalation_question")
        broken = Path(self.temp.name) / "broken-packet.json"
        broken.write_text(json.dumps(packet), encoding="utf-8")
        self.assertTrue(af.validate_json_schema(broken, "task-packet.schema.json"))

    def test_event_corruption_is_detected(self):
        run_id = self.start()
        directory, _ = af.load_run(run_id)
        events = directory / "events.jsonl"
        events.write_text(events.read_text(encoding="utf-8").replace("RUN_CREATED", "RUN_CORRUPTED", 1), encoding="utf-8")
        with self.assertRaises(af.FlowError):
            af.load_run(run_id)

    def test_stale_lock_is_recovered_and_recorded(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        af.write_json(directory / ".lock", {"pid": 99999999, "created_at": "2000-01-01T00:00:00Z"})
        with af.run_lock(directory, run):
            self.assertTrue((directory / ".lock").exists())
            self.assertEqual(json.loads((directory / ".lock").read_text())["namespace"], af.lock_namespace())
        self.assertTrue(list(directory.glob(".lock.recovered-*")))
        af.load_run(run_id)

    def test_recent_foreign_host_lock_is_not_reclaimed(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        af.write_json(directory / ".lock", {"pid": 99999999, "namespace": "foreign-host:test", "created_at": af.utc_now()})
        with self.assertRaises(af.FlowError) as caught:
            with af.run_lock(directory, run):
                pass
        self.assertIn("already locked", str(caught.exception))
        self.assertTrue((directory / ".lock").is_file())
        (directory / ".lock").unlink()

    def test_end_to_end_smoke_packages_without_publishing(self):
        run_id = self.walk_to_package()
        code, payload = call(af.command_package, run_id=run_id)
        self.assertEqual(code, af.EXIT_OK, payload)
        directory, run = af.load_run(run_id)
        self.assertEqual(run["state"], "PUBLISH_APPROVAL")
        package = json.loads((directory / "package" / "package.json").read_text())
        self.assertEqual(package["canonical_article_file"], "public/article.md")
        self.assertTrue((directory / "package" / "site" / "docs" / "a-test-article.html").is_file())
        for surface in [directory / "package" / "site" / "docs" / "blog.html", directory / "package" / "site" / "feed.xml", directory / "package" / "site" / "sitemap.xml"]:
            text = surface.read_text(encoding="utf-8")
            self.assertIn("a-test-article.html", text)
            self.assertIn("from-idea-to-verified-url.html", text)
        repository = af.publication_repo_root(required=True)
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in [repository / "index.html", repository / "docs" / "blog.html", repository / "feed.xml", repository / "sitemap.xml"]}
        _, first = call(af.command_publish_plan, run_id=run_id)
        _, second = call(af.command_publish_plan, run_id=run_id)
        self.assertTrue(second["idempotent"])
        self.assertEqual(first["package_revision"], second["package_revision"])
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before}
        self.assertEqual(before, after)

    def test_protected_drift_blocks_package_and_conformance_blocks_execute(self):
        run_id = self.walk_to_package()
        with mock.patch.object(af, "check_manifest", return_value={"ok": False, "failures": [{"kind": "hash_mismatch"}]}):
            with self.assertRaises(af.FlowError) as caught:
                call(af.command_package, run_id=run_id)
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        with self.assertRaises(af.FlowError) as caught:
            af.command_publish_execute(namespace(run_id="AF-20000101T000000Z-test-00000000", approval="none", commit=False, push=False, json=True))
        self.assertEqual(caught.exception.code, af.EXIT_APPROVAL)

    def test_memory_citation_and_naturalization_drift_fail(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        run["state"] = "RESEARCH"
        ledger_path = Path(self.temp.name) / "ledger.json"
        ledger_path.write_text(json.dumps({
            "claim_ledger_schema_version": "1.0.0", "run_id": run_id, "generated_at": af.utc_now(), "claims": [{
                "claim_id": "C1", "exact_claim": "A current number is 42.", "class": "fact", "risk": "high", "source_tier": "memory", "source_url_or_local_id": "model-memory", "source_title_and_publisher": None, "exact_locator_or_supporting_excerpt": "remembered", "checked_at": af.utc_now(), "freshness_horizon": "one day", "contradiction_status": "none_found", "allowed_wording": "42", "confidence": 0.5, "disposition": "use"
            }]
        }), encoding="utf-8")
        outcome, findings = af.automatic_gate(directory, run, "RESEARCH", ledger_path)
        self.assertEqual(outcome, "REPAIR")
        self.assertIn("no_memory_citations", {item["criterion"] for item in findings})
        locked = directory / "artifacts" / "locked-fields.json"
        af.write_json(locked, {"locked_fields_schema_version": "1.0.0", "run_id": run_id, "source_sha256": "0" * 64, "tokens": af.find_locked_tokens("The value is 42 on 2026-08-18.\n"), "claims": []})
        af.record_artifact(directory, run, locked, "locked-fields", {"actor": "test"})
        changed = Path(self.temp.name) / "changed.md"
        changed.write_text("The value is 43 on 2026-08-18.\n", encoding="utf-8")
        outcome, findings = af.automatic_gate(directory, run, "EDIT", changed)
        self.assertEqual(outcome, "REPAIR")
        self.assertIn("locked_fields", {item["criterion"] for item in findings})

    def test_wrong_live_revision_fails_even_with_http_200(self):
        run_id = self.walk_to_package()
        call(af.command_package, run_id=run_id)
        directory, run = af.load_run(run_id)
        af.transition(directory, run, "LIVE_VERIFICATION", "test", "simulate a completed deployment without performing one")
        with mock.patch.object(af, "fetch_url", return_value=(200, b"older cached page", {})):
            code, payload = call(af.command_verify_live, run_id=run_id)
        self.assertEqual(code, af.EXIT_FAILED)
        self.assertFalse(next(item for item in payload["checks"] if item["name"] == "article_revision")["ok"])
        _, current = af.load_run(run_id)
        self.assertEqual(current["state"], "LIVE_VERIFICATION")

    def test_lifecycle_changes_are_plans_and_archive_requires_a_redirect(self):
        run_id = self.start("A completed article that later needs archiving.")
        directory, run = af.load_run(run_id)
        af.transition(directory, run, "COMPLETE", "test", "exercise lifecycle planning")
        with self.assertRaises(af.FlowError):
            call(af.command_lifecycle, run_id=run_id, action="archive", reason="Retired", redirect_to=None)
        code, payload = call(af.command_lifecycle, run_id=run_id, action="archive", reason="Retired", redirect_to="https://example.com/replacement")
        self.assertEqual(code, af.EXIT_OK)
        self.assertEqual(payload["lifecycle"]["status"], "PLANNED_NOT_APPLIED")
        self.assertTrue(any("redirect verified" in item for item in payload["lifecycle"]["required_checks"]))


class GlobalCommandTests(TemporaryRuntime):
    def test_release_health_reads_only_the_current_native_hosts_receipts(self):
        fake_home = Path(self.temp.name) / "release-home"
        fake_windows = Path(self.temp.name) / "windows-home"
        with (
            mock.patch.object(Path, "home", return_value=fake_home),
            mock.patch.object(af, "windows_user_root", return_value=fake_windows),
        ):
            installations = af.installation_health()
            conformance = af.host_conformance_health()
        expected_installation = "windows" if os.name == "nt" else "wsl"
        expected_conformance = "native-windows" if os.name == "nt" else "wsl"
        self.assertEqual([item["host"] for item in installations["checks"]], [expected_installation])
        self.assertEqual([item["host"] for item in conformance["checks"]], [expected_conformance])

    def test_launcher_smoke_accepts_the_capture_bootstrap(self):
        fake_home = Path(self.temp.name) / "launcher-home"
        fake_runtime = Path(self.temp.name) / "launcher-runtime"
        context = subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps({
            "controller_version": af.CONTROLLER_VERSION,
            "workflow_version": af.workflow()["workflow_version"],
            "spec_root": str(af.SPEC_ROOT),
            "runtime_home": str(fake_runtime),
            "captured_material_root": str(fake_runtime / "runs"),
        }), stderr="")
        bootstrap = subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(af.bootstrap_payload()), stderr="")
        patches = [
            mock.patch.object(af, "runtime_home", return_value=fake_runtime),
            mock.patch.object(af, "runs_root", return_value=fake_runtime / "runs"),
            mock.patch.object(af.subprocess, "run", side_effect=[context, bootstrap]),
        ]
        if os.name == "nt":
            patches.append(mock.patch.object(af, "windows_user_root", return_value=fake_home))
        else:
            patches.append(mock.patch.object(Path, "home", return_value=fake_home))
        with patches[0], patches[1], patches[2], patches[3]:
            result = af.installed_launcher_smoke()
        self.assertTrue(result["ok"], result)

    def test_install_is_content_idempotent_and_drift_is_detected(self):
        fake_home = Path(self.temp.name) / "home"
        fake_windows = Path(self.temp.name) / "windows-user"
        python_exe = fake_windows / "AppData" / "Local" / "Programs" / "Python" / "Python312" / "python.exe"
        python_exe.parent.mkdir(parents=True)
        python_exe.write_bytes(b"test")
        legacy_paths = [
            fake_home / ".agents" / "skills" / "start-article",
            fake_windows / ".agents" / "skills" / "start-article",
        ]
        for path in legacy_paths:
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text("legacy managed pointer", encoding="utf-8")
            (path / ".article-flow-adapter.json").write_text("{}\n", encoding="utf-8")
        for runtime in (fake_home / ".local" / "share" / "article-flow", fake_windows / ".article-flow"):
            legacy_release = runtime / "releases" / "2.0.0" / "Article-Spec-Pack-v1"
            (legacy_release / "scripts").mkdir(parents=True)
            (legacy_release / "manifest.json").write_text('{"generator_name_and_version":"article-flow 2.0.0"}\n', encoding="utf-8")
            (legacy_release / "scripts" / "article_flow.py").write_text('CONTROLLER_VERSION = "2.0.0"\n', encoding="utf-8")
        with (
            mock.patch.object(Path, "home", return_value=fake_home),
            mock.patch.object(af, "windows_user_root", return_value=fake_windows),
            mock.patch.dict(os.environ, {"ARTICLE_FLOW_HOME": ""}),
        ):
            args = namespace(hosts="windows,wsl", providers="auto", user=True, development=True)
            _, first_install = call(af.command_install, **vars(args))
            self.assertEqual(sum(len(item["retired_skill_adapters"]) for item in first_install["installed"]), 2)
            self.assertTrue(all(not path.exists() for path in legacy_paths))
            tracked = [fake_home / ".local" / "bin" / "article-flow", fake_windows / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "article-flow.cmd"]
            hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked}
            call(af.command_install, **vars(args))
            self.assertEqual(hashes, {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked})
            self.assertTrue(all("article-flow managed launcher" in path.read_text() for path in tracked))
            shared_runs_root = fake_windows / ".article-flow" / "runs"
            self.assertIn("ARTICLE_FLOW_RUNS_ROOT=", tracked[0].read_text())
            self.assertIn(str(shared_runs_root), tracked[0].read_text())
            self.assertIn(f"ARTICLE_FLOW_RUNS_ROOT={af.windows_path(shared_runs_root)}", tracked[1].read_text())
            self.assertEqual(json.loads((fake_home / ".local" / "share" / "article-flow" / "current.json").read_text())["captured_material_root"], str(shared_runs_root))
            self.assertEqual(json.loads((fake_windows / ".article-flow" / "current.json").read_text())["captured_material_root"], af.windows_path(shared_runs_root))
            self.assertFalse((fake_home / ".local" / "share" / "article-flow" / "releases").exists())
            self.assertFalse((fake_windows / ".article-flow" / "releases").exists())
            installed_script = af.SCRIPT_PATH
            unrelated = Path(self.temp.name) / "unrelated"
            unrelated.mkdir()
            result = subprocess.run([sys.executable, str(installed_script), "--version"], cwd=unrelated, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(af.CONTROLLER_VERSION, result.stdout)
            primary_wrapper = fake_home / ".local" / "bin" / "article-flow"
            primary_wrapper_hash = hashlib.sha256(primary_wrapper.read_bytes()).hexdigest()
            nested_runtime = Path(self.temp.name) / "nested-runtime"
            nested_user_home = Path(self.temp.name) / "nested-user-home"
            nested_user_home.mkdir()
            nested_environment = os.environ.copy()
            nested_environment["ARTICLE_FLOW_HOME"] = str(nested_runtime)
            nested_environment["ARTICLE_FLOW_REPO_ROOT"] = str(af.REPO_ROOT)
            nested_environment["HOME"] = str(nested_user_home)
            nested_environment["USERPROFILE"] = str(nested_user_home)
            nested = subprocess.run(
                [sys.executable, str(installed_script), "install", "--hosts", "wsl", "--development", "--json"],
                cwd=unrelated,
                env=nested_environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(nested.returncode, 0, nested.stderr)
            nested_record = json.loads((nested_runtime / "current.json").read_text())
            self.assertTrue(nested_record["source_commit"])
            self.assertEqual(primary_wrapper_hash, hashlib.sha256(primary_wrapper.read_bytes()).hexdigest())
            self.assertTrue((nested_user_home / ".local" / "bin" / "article-flow").is_file())
            verification = af.global_command_health()
            self.assertTrue(verification["ok"], verification)
            active_host_command = tracked[-1] if os.name == "nt" else tracked[0]
            active_host_command.write_text("drift", encoding="utf-8")
            verification = af.global_command_health()
            failed = [item for item in verification["checks"] if not item["ok"]]
            self.assertEqual(len(failed), 1)
            self.assertIn("install", failed[0]["repair_command"])

    def test_conformance_forwards_the_publication_checkout_and_retains_history(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="tests passed", stderr="")
        with (
            mock.patch.object(af, "release_source_commit", return_value="a" * 40),
            mock.patch.object(af, "publication_repo_root", return_value=af.REPO_ROOT),
            mock.patch.object(af, "installed_launcher_smoke", return_value={
                "ok": True,
                "launcher": "test-launcher",
                "return_code": 0,
                "controller_version": af.CONTROLLER_VERSION,
                "workflow_version": af.workflow()["workflow_version"],
                "spec_root_match": True,
                "runtime_home_match": True,
                "captured_material_root_match": True,
                "bootstrap_ok": True,
                "unrelated_cwd": True,
                "error": "",
            }),
            mock.patch.object(af.subprocess, "run", return_value=completed) as executed,
        ):
            code, first = call(af.command_conformance)
            self.assertEqual(code, af.EXIT_OK)
            self.assertEqual(executed.call_args.kwargs["env"]["ARTICLE_FLOW_REPO_ROOT"], str(af.REPO_ROOT))
            code, second = call(af.command_conformance)
            self.assertEqual(code, af.EXIT_OK)
        self.assertEqual(first["commit"], second["commit"])
        self.assertTrue(list((self.runtime / "conformance" / "history").glob("*.json")))


class MCPTests(TemporaryRuntime):
    def exchange(self, *requests):
        source = io.StringIO("".join(json.dumps(item) + "\n" for item in requests))
        destination = io.StringIO()
        with mock.patch.object(sys, "stdin", source), contextlib.redirect_stdout(destination):
            self.assertEqual(af.command_mcp(namespace()), af.EXIT_OK)
        return [json.loads(line) for line in destination.getvalue().splitlines()]

    def test_mcp_discovers_tools_starts_resumes_and_records_a_human_gate(self):
        initialized, listed, started = self.exchange(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "start", "arguments": {"seed": "An MCP-started article idea."}}},
        )
        self.assertEqual(initialized["result"]["serverInfo"]["version"], af.CONTROLLER_VERSION)
        self.assertEqual({item["name"] for item in listed["result"]["tools"]}, {"start", "status", "next", "resume", "gate"})
        start_payload = json.loads(started["result"]["content"][0]["text"])
        run_id = start_payload["run_id"]

        directory, run = af.load_run(run_id)
        candidate = directory / "artifacts" / "intent-candidate.json"
        af.write_json(candidate, {"intent_schema_version": "1.0.0", "run_id": run_id})
        af.record_artifact(directory, run, candidate, "intent-candidate", {"actor": "test"})
        af.transition(directory, run, "INTENT_REVIEW", "test", "exercise the MCP human-gate adapter")

        status, resumed, gated = self.exchange(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "status", "arguments": {"run_id": run_id}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "resume", "arguments": {"run_id": run_id}}},
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "gate", "arguments": {"run_id": run_id, "gate_id": "G-INTENT-FIDELITY", "outcome": "PASS"}}},
        )
        self.assertEqual(json.loads(status["result"]["content"][0]["text"])["state"], "INTENT_REVIEW")
        self.assertEqual(json.loads(resumed["result"]["content"][0]["text"])["action"], "human_decision")
        self.assertEqual(json.loads(gated["result"]["content"][0]["text"])["state"], "ARTICLE_RECIPE")
        af.load_run(run_id)


class ProviderTests(TemporaryRuntime):
    def test_command_provider_consumes_the_same_packet(self):
        helper = Path(self.temp.name) / "provider.py"
        helper.write_text(
            "import json,sys\n"
            "p=json.load(open(sys.argv[1],encoding='utf-8'))\n"
            "o={'research_plan_schema_version':'1.0.0','run_id':p['run_id'],'questions':[{'question':'Q','why_it_matters':'B','intent_changing':True}],'source_strategy':['primary sources'],'claim_risks':[],'no_search_behavior':'not-applicable'}\n"
            "open(sys.argv[2],'w',encoding='utf-8').write(json.dumps(o))\n",
            encoding="utf-8",
        )
        config = self.runtime / "config" / "providers.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"provider_config_schema_version": "1.0.0", "providers": [{
            "provider_id": "fixture", "kind": "command", "enabled": True,
            "command": [sys.executable, str(helper), "{packet}", "{output}"],
            "models": [{"model_id": "fixture-model", "version": "1", "capabilities": ["structured-output", "long-form", "research"], "stages": ["RESEARCH_PLAN"], "locality": "local", "canary_status": "passed"}],
        }]}), encoding="utf-8")
        code, started = call(af.command_start, seed="test command route", seed_file=None, slug=None)
        self.assertEqual(code, 0)
        run_id = started["run_id"]
        call(af.command_next, run_id=run_id)
        code, result = call(af.command_execute_stage, run_id=run_id, route="fixture:fixture-model")
        self.assertEqual(code, 0, result)
        _, run = af.load_run(run_id)
        self.assertEqual(run["state"], "RESEARCH")
        receipt = next(item for item in run["artifact_index"] if item["type"].startswith("model-call:"))
        receipt_value = json.loads((af.run_dir(run_id) / receipt["path"]).read_text())
        self.assertNotIn("credential", json.dumps(receipt_value).lower())

    def test_required_canary_cannot_become_default_but_can_run_explicitly(self):
        helper = Path(self.temp.name) / "canary-provider.py"
        helper.write_text(
            "import json,sys\n"
            "p=json.load(open(sys.argv[1],encoding='utf-8'))\n"
            "o={'research_plan_schema_version':'1.0.0','run_id':p['run_id'],'questions':[{'question':'Q','why_it_matters':'B','intent_changing':True}],'source_strategy':['primary sources'],'claim_risks':[],'no_search_behavior':'not-applicable'}\n"
            "open(sys.argv[2],'w',encoding='utf-8').write(json.dumps(o))\n",
            encoding="utf-8",
        )
        config = self.runtime / "config" / "providers.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"provider_config_schema_version": "1.0.0", "providers": [{
            "provider_id": "canary-fixture", "kind": "command", "enabled": True,
            "command": [sys.executable, str(helper), "{packet}", "{output}"],
            "models": [{"model_id": "new-version", "version": "2", "capabilities": ["structured-output", "long-form", "research"], "stages": ["RESEARCH_PLAN"], "locality": "local", "canary_status": "required"}],
        }]}), encoding="utf-8")
        code, started = call(af.command_start, seed="test canary route", seed_file=None, slug=None)
        self.assertEqual(code, 0)
        run_id = started["run_id"]
        call(af.command_next, run_id=run_id)
        with self.assertRaises(af.FlowError):
            call(af.command_execute_stage, run_id=run_id, route="canary-fixture:new-version", canary=False)
        code, result = call(af.command_execute_stage, run_id=run_id, route="canary-fixture:new-version", canary=True)
        self.assertEqual(code, 0, result)
        self.assertTrue(result["model_call"]["canary_execution"])

    def test_routing_promotion_requires_human_calibration(self):
        source = Path(self.temp.name) / "evaluation.json"
        source.write_text(json.dumps({
            "evaluation_schema_version": "1.0.0", "evaluation_id": "eval-no-human", "fixture_id": "fixture-1",
            "workflow_version": af.workflow()["workflow_version"], "stage": "DRAFT", "provider": "fixture", "model": "model", "model_version": "1",
            "grader": {"order_reversal_passed": True}, "candidate_order": ["A", "B"], "metrics": {"overall": 0.9},
            "human_calibration": None, "promotion_status": "promoted", "canary": {"status": "passed"}, "created_at": af.utc_now(),
        }), encoding="utf-8")
        with self.assertRaises(af.FlowError) as caught:
            call(af.command_evaluation_record, file=str(source))
        self.assertIn("human calibration", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
