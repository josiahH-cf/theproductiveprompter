"""Behavioral regressions for compact voice, bounded collaboration and 3.2 delivery."""
from __future__ import annotations

import copy
import contextlib
import io
import json
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import article_maintenance as maintenance
import editorial_context as context
import editorial_learning as learning
import editorial_workbench as workbench
from test_article_flow_v3 import TemporaryRuntime, NoPublishAutomationTests, call, namespace, af


class EditorialTests(TemporaryRuntime):
    def profile(self):
        return af.load_json(af.SPEC_ROOT / "profiles/voice-profile.capstone.v1.json")

    def start_current(self):
        code, payload = call(af.command_start, seed="Explain a small library's shared return record.", seed_file=None, slug=None)
        self.assertEqual(code, 0)
        return af.load_run(payload["run_id"])

    def test_current_run_freezes_definitions_and_schemas(self):
        directory, run = self.start_current()
        self.assertEqual(run["workflow_version"], "3.2.0")
        frozen = copy.deepcopy(af.workflow_for_run(run))
        with mock.patch.object(af, "workflow", return_value={"workflow_version": "99.0.0"}):
            self.assertEqual(af.workflow_for_run(run), frozen)
        self.assertIn("brief.schema.json", context.definitions(run)["schemas"])
        run["definition_snapshot"]["value"]["workflow"]["workflow_version"] = "99.0.0"
        with self.assertRaisesRegex(ValueError, "integrity"):
            af.workflow_for_run(run)

    def test_projection_cannot_leak_untyped_history_or_generated_positives(self):
        profile = self.profile()
        profile["provisional_guidance"] = [{"text": "450–650 words; appendix C18; mean $0.0241"}]
        profile["accepted_rejected_pairs"] = [{"selected": "ALWAYS CONVERSATIONAL"}]
        profile["positive_examples"].insert(0, {"excerpt": "Generated fake author experience", "operator_confirmation": True})
        projection = context.compact_voice(profile, run_id="A")
        value = json.dumps(projection)
        self.assertNotIn("0.0241", value)
        self.assertNotIn("ALWAYS CONVERSATIONAL", value)
        self.assertNotIn("fake author", value)
        self.assertEqual(len(projection["core_rules"]), 8)
        self.assertEqual(len(projection["authentic_excerpts"]), 4)

    def test_live_gate_reclassification_cannot_change_frozen_approval_authority(self):
        directory, run = self.start_current()
        af.transition(directory, run, "CLAIM_VERIFICATION", "test", "Frozen gate fixture")
        live = copy.deepcopy(af.workflow())
        live["gates"]["hard"].remove("G-CLAIMS-VERIFIED")
        live["gates"]["soft"].append("G-CLAIMS-VERIFIED")
        live["gates"]["soft"].remove("G-INTENT-FIDELITY")
        live["gates"]["hard"].append("G-INTENT-FIDELITY")
        with mock.patch.object(af, "workflow", return_value=live):
            with self.assertRaisesRegex(af.FlowError, "code-owned"):
                call(af.command_gate, run_id=run["run_id"], gate_id="G-CLAIMS-VERIFIED", outcome="PASS", finding=None, artifact=None)
            self.assertEqual(af.gate_class("G-CLAIMS-VERIFIED", run), "hard")
            self.assertEqual(af.gate_class("G-INTENT-FIDELITY", run), "soft")
            af.transition(directory, run, "INTENT_REVIEW", "test", "Frozen human-review gate fixture")
            self.record_json(directory, run, "intent-candidate", {"intent_schema_version": "1.0.0", "run_id": run["run_id"],
                "reader": "Library staff", "reader_job": "Choose a pilot", "purpose": "Explain", "scope": "One pilot",
                "position": None, "explicit_seed_content": [], "assumptions": [], "remaining_unknowns": []})
            code, result = call(af.command_gate, run_id=run["run_id"], gate_id="G-INTENT-FIDELITY", outcome="PASS", finding=None, artifact=None)
            self.assertEqual(code, 0, result)
            _, updated = af.load_run(run["run_id"])
            self.assertEqual(updated["state"], "ARTICLE_RECIPE")
            receipts = [af.load_json(p) for p in (directory / "receipts").glob("*.json")]
            self.assertEqual(next(r for r in receipts if r["gate_id"] == "G-INTENT-FIDELITY")["gate_class"], "soft")

    def test_local_and_register_preferences_do_not_become_global(self):
        profile = self.profile()
        profile["author_voice"]["scoped_preferences"] = [
            {"status": "accepted", "decision_maker": "human", "scope": "article", "run_id": "A", "text": "Short appendix"},
            {"status": "accepted", "decision_maker": "human", "scope": "register", "register": "technical", "text": "Show dependency"}]
        self.assertEqual(context.compact_voice(profile, run_id="B")["scoped_preferences"], [])
        self.assertEqual(len(context.compact_voice(profile, run_id="A", register="technical")["scoped_preferences"]), 2)

    def test_feedback_is_pending_and_does_not_move_current_pointer(self):
        directory, run = self.start_current()
        af.transition(directory, run, "COMPLETE", "test", "feedback fixture")
        before = af.active_voice_profile()[2]
        path = self.root / "feedback.txt"
        path.write_text("This paragraph needs a concrete dependency.", encoding="utf-8")
        code, result = call(af.command_voice_feedback, run_id=run["run_id"], feedback_file=str(path), outcome="rejected", actor="assistant")
        self.assertEqual(code, 0)
        self.assertFalse(result["activated"])
        self.assertEqual(before, af.active_voice_profile()[2])
        proposal = af.load_json(Path(result["path"]))
        self.assertEqual(proposal["evidence_kind"], "generated_interpretation")
        self.assertEqual(proposal["scope"], "article")

    def test_accept_requires_human_reason_and_regression_checks(self):
        learning.activate_guide(af, self.profile(), "User authorized using the candidate")
        result = learning.store_proposal(af, {"run_id": "A", "decision_maker": "assistant", "scope": "article", "outcome": "rejected"})
        with self.assertRaises(ValueError):
            learning.accept_proposal(af, result["record_id"], {"decision_maker": "assistant"})
        confirmation = {"decision_maker": "human", "exact_human_response": "For this article, keep the explanation together.",
                        "rule": "Keep this dependency together", "reason": "The split lost the causal connection", "scope": "article",
                        "exceptions": "Do not generalize beyond A", "retained_example_check": "V06 preserved", "different_form_check": "Reference summary stays compact"}
        accepted = learning.accept_proposal(af, result["record_id"], confirmation)
        repeated = learning.accept_proposal(af, result["record_id"], confirmation)
        self.assertTrue(repeated["idempotent"])
        self.assertEqual(accepted["version"], repeated["version"])
        profile = af.active_voice_profile()[0]
        self.assertEqual(context.compact_voice(profile, run_id="B")["scoped_preferences"], [])

    def test_activation_and_rollback_preserve_the_protected_baseline(self):
        baseline_hash = af.sha256_path(af.baseline_voice_profile_path())
        original_version = af.active_voice_profile()[0]["version"]
        first = learning.activate_guide(af, self.profile(), "Actual author authorization")
        repeated = learning.activate_guide(af, self.profile(), "Actual author authorization")
        self.assertTrue(repeated["idempotent"])
        self.assertEqual(first["human_quality_judgment"], "pending")
        self.assertEqual(af.rollback_voice_profile(original_version)["current_version"], original_version)
        self.assertEqual(af.sha256_path(af.baseline_voice_profile_path()), baseline_hash)

    def test_rollback_does_not_allow_redefining_a_historical_guide_version(self):
        baseline = af.active_voice_profile()[0]["version"]
        learning.activate_guide(af, self.profile(), "Actual author authorization")
        original = af.active_voice_profile()[1].read_bytes()
        af.rollback_voice_profile(baseline)
        changed = self.profile()
        changed["author_voice"]["operational_rules"][0]["instruction"] = "A different instruction"
        with self.assertRaisesRegex(ValueError, "immutable"):
            learning.activate_guide(af, changed, "Actual author authorization")
        learning.activate_guide(af, self.profile(), "Actual author authorization")
        self.assertEqual(af.active_voice_profile()[1].read_bytes(), original)
        duplicate = copy.deepcopy(af.active_voice_profile()[0])
        duplicate["provenance_note"] += " Changed bytes"
        af.write_json(af.voice_state_root() / "profiles/duplicate.json", duplicate)
        with self.assertRaisesRegex(af.FlowError, "conflicting immutable"):
            af.active_voice_profile()

    def test_frozen_prose_policy_controls_gate_and_publication_hash(self):
        directory, run = self.start_current()
        path = directory / "submissions/frozen-draft.md"
        path.write_text("A clear bounded explanation gives the reader enough context to choose a next step.\n", encoding="utf-8")
        before = af.automatic_gate(directory, run, "DRAFT", path)
        before_hash = af.style_policy_sha256(run)
        live = copy.deepcopy(af.policy())
        live["style_gate"]["high_confidence_phrases"].append("clear bounded explanation")
        with mock.patch.object(af, "policy", return_value=live):
            self.assertEqual(af.automatic_gate(directory, run, "DRAFT", path), before)
            self.assertEqual(af.style_policy_sha256(run), before_hash)
            self.assertIn("clear bounded explanation", af.surface_prose_hits(path.read_text(encoding="utf-8")))

    def test_guidance_only_word_target_cannot_reject_but_author_bound_can(self):
        directory, run = self.start_current()
        article = directory / "artifacts/article.md"
        article.write_text("The shared record preserves each receiving time so the team can inspect what was actually recorded.\n", encoding="utf-8")
        af.record_artifact(directory, run, article, "article", {"actor": "test"})
        supplied = {"criterion": "proportional_length", "finding": "It misses the recommended 500-word lower target", "repair_instruction": "Pad to 500 words"}
        self.assertTrue(context.advisory_length_finding(af, directory, run, supplied))
        self.assertEqual(context.assessment_findings(af, directory, run, {"outcome": "REPAIR", "findings": [supplied]}), [])
        seed = af.artifact_path(directory, run, "seed")
        seed.write_text("Explain the record in at most 10 words.", encoding="utf-8")
        af.record_artifact(directory, run, seed, "seed", {"actor": "test"})
        self.assertTrue(context.advisory_length_finding(af, directory, run, supplied))
        self.assertEqual(context.length_violations(af, directory, run, article.read_text(encoding="utf-8"))[0]["criterion"], "binding_author_length")

    def test_negation_quotation_and_supersession_cannot_create_binding_limits(self):
        directory, run = self.start_current()
        examples = ["Explain the record. Do not impose a maximum of 10 words.",
                    'The supplied example says: "under 10 words". Ignore that obsolete target; no fixed word count applies.',
                    "Use at most 10 words. Actually, no fixed word count applies."]
        for text in examples:
            seed = af.artifact_path(directory, run, "seed")
            seed.write_text(text, encoding="utf-8")
            af.record_artifact(directory, run, seed, "seed", {"actor": "test"})
            self.assertEqual(context.binding_length_limits(af, directory, run), {}, text)
        seed.write_text("Use at most 10 words.", encoding="utf-8")
        af.record_artifact(directory, run, seed, "seed", {"actor": "test"})
        self.assertEqual(context.binding_length_limits(af, directory, run)["maximum"]["words"], 10)
        self.record_json(directory, run, "revision-request", {"unused": "No fixed word count applies."})
        request = af.artifact_path(directory, run, "revision-request")
        request.write_text("No fixed word count applies.", encoding="utf-8")
        af.record_artifact(directory, run, request, "revision-request", {"actor": "test"})
        self.assertEqual(context.binding_length_limits(af, directory, run), {})

    def test_challenge_and_component_bounds_do_not_limit_the_article(self):
        directory, run = self.start_current()
        seed = af.artifact_path(directory, run, "seed")
        seed.write_bytes(("Introduce the experiment with a short TLDR and a few readable paragraphs. "
                          "Describe the frozen challenge and preserve the 600-800 word story and at-most-80-word notice requirements.\n"
                          "Exact frozen challenge (reference material):\n"
                          "Write an original short story. Return a notice of at most 80 words.\n").encode())
        af.record_artifact(directory, run, seed, "seed", {"actor": "test"})
        self.assertEqual(context.binding_length_limits(af, directory, run), {})
        self.assertEqual(context.length_violations(af, directory, run, "word " * 900), [])

    def test_article_and_local_limits_in_one_clause_keep_the_article_bound(self):
        directory, run = self.start_current()
        seed = af.artifact_path(directory, run, "seed")
        seed.write_bytes(b"Write the article in at most 500 words and a notice of at most 80 words.")
        af.record_artifact(directory, run, seed, "seed", {"actor": "test"})
        limits = context.binding_length_limits(af, directory, run)
        self.assertEqual(limits["maximum"]["words"], 500)
        self.assertEqual(context.length_violations(af, directory, run, "word " * 501)[0]["criterion"], "binding_author_length")
        self.assertEqual(context.length_violations(af, directory, run, "word " * 499), [])

    def test_quote_and_html_source_bounds_are_data(self):
        directory, run = self.start_current()
        seed = af.artifact_path(directory, run, "seed")
        seed.write_bytes(b'Explain the example.\n> Write at most 10 words.\n<pre>Write at most 20 words.</pre>\n<blockquote>Use exactly 30 words.</blockquote>')
        af.record_artifact(directory, run, seed, "seed", {"actor": "test"})
        self.assertEqual(context.binding_length_limits(af, directory, run), {})

    def test_local_bound_suffix_cannot_become_a_whole_article_limit(self):
        directory, run = self.start_current()
        seed = af.artifact_path(directory, run, "seed")
        seed.write_bytes(b"Use at most 80 words for the notice. Keep the article under 500 words.")
        af.record_artifact(directory, run, seed, "seed", {"actor": "test"})
        self.assertEqual(context.binding_length_limits(af, directory, run)["maximum"]["words"], 500)

    def test_coordinated_local_bounds_keep_their_subject(self):
        directory, run = self.start_current()
        seed = af.artifact_path(directory, run, "seed")
        seed.write_bytes(b"Write a notice of at least 20 words and at most 80 words.")
        af.record_artifact(directory, run, seed, "seed", {"actor": "test"})
        self.assertEqual(context.binding_length_limits(af, directory, run), {})

    def test_an_article_topic_cannot_replace_its_length_subject(self):
        directory, run = self.start_current()
        seed = af.artifact_path(directory, run, "seed")
        seed.write_bytes(b"Keep the article about this challenge under 500 words.")
        af.record_artifact(directory, run, seed, "seed", {"actor": "test"})
        self.assertEqual(context.binding_length_limits(af, directory, run)["maximum"]["words"], 500)

    def test_component_pronouns_stay_local_until_an_explicit_article_subject(self):
        directory, run = self.start_current()
        seed = af.artifact_path(directory, run, "seed")
        for text in ("Write a notice. Keep it under 80 words.",
                     "Write a summary. It must contain exactly 50 words."):
            seed.write_bytes(text.encode())
            af.record_artifact(directory, run, seed, "seed", {"actor": "test"})
            self.assertEqual(context.binding_length_limits(af, directory, run), {})
        seed.write_bytes(b"Write a notice. Keep it under 80 words. Keep the article under 500 words.")
        af.record_artifact(directory, run, seed, "seed", {"actor": "test"})
        self.assertEqual(context.binding_length_limits(af, directory, run)["maximum"]["words"], 500)

    def test_obligations_retain_distinct_passages_and_require_the_correct_surface(self):
        directory, run = self.start_current()
        article = directory / "artifacts/article.md"
        article.write_text("# Title\n\nFirst affected paragraph remains here.\n\nAnother separate paragraph appears here.\n", encoding="utf-8")
        af.record_artifact(directory, run, article, "article", {"actor": "test"})
        common = {"criterion": "development", "artifact": "article", "finding": "Missing connection", "repair_instruction": "Connect it", "repair_state": "DRAFT"}
        first, second = ({**common, "location": location} for location in ("paragraph one", "paragraph two"))
        self.assertNotEqual(context.obligation_id(first), context.obligation_id(second))
        value = {"outcome": "REPAIR", "findings": [first, second]}
        self.assertEqual(len(context.assessment_findings(af, directory, run, value)), 2)
        self.record_json(directory, run, "editorial-repair-obligations", {"pending": [{"id": context.obligation_id(f), "finding": f} for f in (first, second)]})
        value = {"outcome": "PASS", "findings": [], "dimensions": {"repair_resolution": {
            context.obligation_id(first): {"status": "PASS", "surface": "article", "finding_location": "paragraph one", "excerpt": "Another separate paragraph appears here.", "reason": "A sufficiently long reason cannot authorize an unrelated excerpt."}}}}
        self.assertEqual(len(context.assessment_findings(af, directory, run, value)), 2)
        value["dimensions"]["repair_resolution"][context.obligation_id(first)]["excerpt"] = "First affected paragraph remains here."
        self.assertEqual(context.assessment_findings(af, directory, run, value), [second])
        display = {**common, "criterion": "description", "artifact": "brief.description", "location": "description", "repair_state": "DISPLAY_REVISION"}
        self.record_json(directory, run, "brief", {"description": "The corrected description names the shared record."})
        self.record_json(directory, run, "editorial-repair-obligations", {"pending": [{"id": context.obligation_id(display), "finding": display}]})
        resolution = {"status": "PASS", "surface": "brief.description", "finding_location": "description", "excerpt": "First affected paragraph remains here.", "reason": "The supplied reason does not permit body text to resolve metadata."}
        value["dimensions"]["repair_resolution"] = {context.obligation_id(display): resolution}
        self.assertEqual(context.assessment_findings(af, directory, run, value), [display])
        resolution["excerpt"] = "The corrected description names the shared record."
        self.assertEqual(context.assessment_findings(af, directory, run, value), [])

    def test_offline_workspaces_reject_runtime_and_publication_paths(self):
        for root in (self.runtime, self.runtime / "experiment", af.REPO_ROOT, af.REPO_ROOT.parent):
            with self.subTest(root=root), self.assertRaises(ValueError):
                workbench.workspace(af, str(root))

    def test_unknown_or_sentence_locations_cannot_resolve_from_unrelated_prose(self):
        directory, run = self.start_current()
        article = directory / "artifacts/article.md"
        article.write_text("# Title\n\nUnrelated opening remains here.\n\nThe affected sentence remains. A separate second sentence follows.\n\n## Repeated\n\nOne section.\n\n## Repeated\n\nAnother section.\n", encoding="utf-8")
        af.record_artifact(directory, run, article, "article", {"actor": "test"})
        for location in ("paragraph 2, sentence 1", "Unknown heading", "Repeated", "paragraph 99", "paragraph 2, sentence 99"):
            finding = {"criterion": "development", "artifact": "article", "location": location,
                       "finding": "Missing connection", "repair_instruction": "Develop it", "repair_state": "DRAFT"}
            identifier = context.obligation_id(finding)
            self.record_json(directory, run, "editorial-repair-obligations", {"pending": [{"id": identifier, "finding": finding}]})
            resolution = {"status": "PASS", "surface": "article", "finding_location": location,
                          "excerpt": "Unrelated opening remains here.", "reason": "An unrelated passage cannot prove that this concern has been resolved."}
            assessment = {"outcome": "PASS", "findings": [], "dimensions": {"repair_resolution": {identifier: resolution}}}
            self.assertEqual(context.assessment_findings(af, directory, run, assessment), [finding], location)
            resolution["excerpt"] = "A separate second sentence follows."
            self.assertEqual(context.assessment_findings(af, directory, run, assessment), [finding], location)
            resolution["excerpt"] = "The affected sentence remains."
            self.assertEqual(context.assessment_findings(af, directory, run, assessment), [] if location == "paragraph 2, sentence 1" else [finding], location)

    def test_offline_call_budget_counts_failures_and_cannot_publish(self):
        root = workbench.workspace(af, str(self.root / "offline"))
        af.write_json(root / "budget.json", {"calls": 23, "writer": 15, "review": 8, "limit": 24})
        with mock.patch.object(workbench, "select_route", return_value={"provider": "fixture", "model": "exact"}), \
             mock.patch.object(af, "invoke_route", side_effect=ValueError("Provider failed")), \
             mock.patch.object(af, "command_publish_execute", side_effect=AssertionError("must not publish")) as publish:
            with self.assertRaisesRegex(ValueError, "Provider failed"):
                workbench.assist(af, root, "draft", {"facts": "fixed"}, execute=True, requested="fixture:exact")
            self.assertEqual(af.load_json(root / "budget.json")["calls"], 24)
            with self.assertRaisesRegex(ValueError, "budget exhausted"):
                workbench.assist(af, root, "draft", {"facts": "other"}, execute=True, requested="fixture:exact")
        publish.assert_not_called()

    def test_matched_comparison_changes_only_guidance_with_same_draft_and_facts(self):
        root = workbench.workspace(af, str(self.root / "offline"))
        material = {"reader_job": "Understand records", "facts": ["Both desks use one record"], "draft": "The same draft.", "current_guidance": "old", "proposed_guidance": "new"}
        report = workbench.evaluate(af, root, material, namespace(route="fixture:exact", execute=False))
        self.assertEqual(len(report["results"]), 12)
        values = []
        for result in report["results"]:
            packet = af.load_json(Path(result["packet"]))
            values.append(af.load_json(Path(packet["inputs"][0]["path"])))
            self.assertEqual(packet["side_effect_policy"], "none")
        for a, b in zip(values[:2], values[2:4]):
            self.assertEqual({k:v for k,v in a.items() if k != "voice_guidance"}, {k:v for k,v in b.items() if k != "voice_guidance"})
        self.assertFalse((af.voice_state_root() / "current.json").exists())

    def test_source_event_distinguishes_cosmetic_change_and_all_public_surfaces(self):
        index = {"run_id": "A", "canonical_url": "https://example.org/a", "first_publication_date": "2026-01-01", "sources": [{"source": "https://example.org/source", "claim_id": "C1", "dependent_surfaces": ["article", "description", "cards", "feed", "visual:one"]}]}
        event = {"source": "https://example.org/source", "before": "Three trials", "after": "Three  trials"}
        self.assertEqual(maintenance.source_event(index, event)["status"], "cosmetic_no_revision")
        event["after"] = "Four trials"
        result = maintenance.source_event(index, event)
        self.assertEqual(result["status"], "semantic_review_pending")
        self.assertEqual(len(result["required_surfaces"]), 5)
        self.assertFalse(result["revision_required"])

    def test_repair_routes_are_classified_by_controller(self):
        definition = next(s for s in af.workflow()["states"] if s["id"] == "EDITORIAL_QA")
        for criterion, expected in (("description", "DISPLAY_REVISION"), ("development", "DRAFT"), ("fact", "CLAIM_VERIFICATION"), ("visual", "VISUAL_PLAN"), ("naturalness", "EDIT")):
            self.assertEqual(af.editorial_repair_destination({"criterion": criterion, "repair_state": "PUBLISH"}), expected)
            self.assertEqual(af.effective_repair_state(definition, [{"repair_state": expected}]), expected)

    def test_explicit_upstream_repair_reopens_source_assessment_window_durably(self):
        directory, run = self.start_current()
        af.transition(directory, run, "EDITORIAL_QA", "test", "Exhausted assessment fixture")
        finding = {"criterion": "development", "artifact": "article", "location": None, "finding": "A supported connection is missing.", "repair_instruction": "Develop that connection.", "repair_state": "DRAFT"}
        af.write_gate_receipt(directory, run, "G-EDITORIAL-QA", "REPAIR", [finding], {"type": "code"}, "DRAFT")
        with mock.patch.object(af, "remember_repair_context", return_value=None), \
             mock.patch.object(af, "rejected_attempt_requires_repair_context", return_value=False), \
             mock.patch.object(af, "stage_attempt_evidence", return_value={"ordinal": 3, "execution_count": 3}):
            code, result = call(af.command_repair, run_id=run["run_id"], gate_id="G-EDITORIAL-QA", finding="Author authorized one new bounded repair")
        self.assertEqual(code, 0, result)
        _, repaired = af.load_run(run["run_id"])
        self.assertEqual(repaired["state"], "DRAFT")
        self.assertEqual(repaired["attempt_baselines"]["EDITORIAL_QA"], 3)
        self.assertEqual(repaired["attempt_baselines"]["DRAFT"], 3)

    def test_duplicate_bytes_are_embedded_once_and_both_aliases_survive(self):
        path = self.root / "material.txt"
        path.write_text("A unique passage of source evidence.", encoding="utf-8")
        packet = {"inputs": [{"id": role, "path": str(path), "sha256": af.sha256_path(path)} for role in ("draft", "current-article")]}
        prompt = af.model_prompt(packet)
        self.assertEqual(prompt.count(path.read_text(encoding="utf-8")), 1)
        self.assertIn("draft, current-article", prompt)
        path.write_text("Changed", encoding="utf-8")
        with self.assertRaises(af.FlowError):
            af.model_prompt(packet)

    def test_global_skill_sync_is_versioned_and_keeps_previous_bytes(self):
        destination = self.root / "user/.agents/skills/article-flow/SKILL.md"
        destination.parent.mkdir(parents=True)
        destination.write_text("---\nname: article-flow\n---\nOld guidance", encoding="utf-8")
        result = context.sync_skill(af, self.root / "user", self.root / "backups")
        self.assertEqual(len(result), 2)
        self.assertEqual(destination.read_bytes(), (af.SPEC_ROOT.parent / ".agents/skills/article-flow/SKILL.md").read_bytes())
        self.assertEqual(len(list((self.root / "backups/skill-backups").glob("*/SKILL.md"))), 1)

    def test_material_question_stops_and_actual_answer_is_preserved(self):
        directory, run = self.start_current()
        value = {"intent_schema_version": "1.0.0", "run_id": run["run_id"], "reader": "Library staff", "reader_job": "Choose a pilot", "purpose": "Explain", "scope": "One pilot", "position": None, "explicit_seed_content": [], "assumptions": [], "remaining_unknowns": [], "material_questions": ["Which team will use this pilot?"]}
        path = self.record_json(directory, run, "intent-candidate", value)
        outcome, findings = af.automatic_gate(directory, run, "INTENT_REVIEW", path)
        self.assertEqual(outcome, "ESCALATE")
        self.assertEqual(findings[0]["criterion"], "material_author_decision")
        af.transition(directory, run, "INTENT_REVIEW", "test", "Question fixture")
        run["status"] = "BLOCKED"
        af.save_run(directory, run)
        handoff = af.next_state_payload(directory, run)
        self.assertEqual(handoff["action"], "author_clarification")
        response = self.root / "response.txt"
        response.write_text("The north receiving desk and south collection team.", encoding="utf-8")
        code, _ = call(af.command_clarify, run_id=run["run_id"], response_file=str(response), auto=False)
        self.assertEqual(code, 0)
        directory, updated = af.load_run(run["run_id"])
        recorded = af.json_artifact(directory, updated, "author-context")
        self.assertEqual(recorded["responses"][0]["exact_author_response"], response.read_text(encoding="utf-8"))
        self.assertEqual(updated["status"], "ACTIVE")

    def test_tampered_context_source_is_rejected_before_projection(self):
        directory, run = self.start_current()
        path = self.record_json(directory, run, "brief", {"reader_job": "Original"})
        path.write_text('{"reader_job":"Poisoned"}', encoding="utf-8")
        with self.assertRaisesRegex(af.FlowError, "source changed"):
            context.contract(af, directory, run)


class CurrentAutomationTests(NoPublishAutomationTests):
    """Re-exercise the real controller state machine with the new stages and local learning."""
    def start(self, seed="A current no-publish editorial path.", **overrides):
        learning.activate_guide(af, af.load_json(af.SPEC_ROOT / "profiles/voice-profile.capstone.v1.json"), "Fixture author authorized candidate use")
        code, payload = call(af.command_start, seed=seed, seed_file=None, slug=None, **overrides)
        self.assertEqual(code, 0)
        return payload["run_id"]

    def stage_value(self, state, directory, run):
        if state == "DEVELOPMENT_REVIEW":
            return {"run_id": run["run_id"], "outcome": "PASS", "reverse_outline": [{"section": "What the check proves", "job": "Explain the proof boundary", "supported_connection": "A revision binds the result to evidence"}], "findings": []}
        if state == "DISPLAY_REVISION":
            return af.json_artifact(directory, run, "brief")
        return super().stage_value(state, directory, run)

    def test_new_stage_packets_use_compact_guide_and_brief(self):
        self.test_no_publish_advance_has_one_human_gate_then_completes()
        directory = next((self.runtime / "runs").glob("AF-*"))
        run = af.load_json(directory / "run.json")
        self.assertEqual(run["workflow_version"], "3.2.0")
        for stage in ("ARTICLE_RECIPE", "BRIEF", "EDIT", "DEVELOPMENT_REVIEW", "DISPLAY_REVISION"):
            packet = af.load_json(sorted((directory / "tasks").glob(stage.lower() + "-*.json"))[0])
            ids = {i["id"] for i in packet["inputs"]}
            self.assertIn("editorial-context", ids)
            self.assertNotIn("voice-profile", ids)
            if stage == "EDIT":
                self.assertIn("brief", ids)
        self.assertEqual(af.active_voice_profile()[0]["version"], "capstone-1.0.0")
        self.assertFalse(af.json_artifact(directory, run, "voice-learning")["profile_update"]["activated"])

    def test_schema_update_after_plan_acceptance_cannot_strand_frozen_run(self):
        original_stage = self.stage_value
        original_bundle = af.schema_bundle
        changed = False
        run_schemas = {"visual-plan.schema.json", "visual-manifest.schema.json", "locked-fields.schema.json",
                       "voice-probe.schema.json", "brief.schema.json", "package.schema.json",
                       "task-packet.schema.json", "event.schema.json", "artifact.schema.json",
                       "run.schema.json", "gate-receipt.schema.json"}

        def stage(state, directory, run):
            nonlocal changed
            result = original_stage(state, directory, run)
            if state == "VISUAL_PLAN":
                changed = True
            return result

        def bundle(root):
            schemas, registry = original_bundle(root)
            if changed:
                schemas = copy.deepcopy(schemas)
                for name in run_schemas:
                    schemas[name].setdefault("required", []).append("new_live_only_field")
            return schemas, registry

        with mock.patch.object(af, "schema_bundle", side_effect=bundle), mock.patch.object(self, "stage_value", side_effect=stage):
            self.test_no_publish_advance_has_one_human_gate_then_completes()
            directory = next((self.runtime / "runs").glob("AF-*"))
            run = af.load_json(directory / "run.json")
            plan = af.json_artifact(directory, run, "visual-plan")
            self.assertTrue(changed)
            self.assertEqual(af.validate_instance_schema(plan, "visual-plan.schema.json", run), [])
            self.assertTrue(any("new_live_only_field" in e for e in af.validate_instance_schema(plan, "visual-plan.schema.json")))
            self.assertTrue(any("new_live_only_field" in e for e in af.validate_instance_schema(plan, "visual-plan.schema.json", {"workflow_version": "3.1.0"})))

    def test_actual_qa_gate_treats_recipe_target_and_positive_observations_as_advisory(self):
        self.test_no_publish_advance_has_one_human_gate_then_completes()
        directory = next((self.runtime / "runs").glob("AF-*"))
        run = af.load_json(directory / "run.json")
        value = self.stage_value("EDITORIAL_QA", directory, run)
        common = {"artifact": "article", "location": None, "repair_state": "EDIT"}
        value["outcome"] = "REPAIR"
        value["findings"] = [{**common, "criterion": "proportional_length", "finding": "It misses the recommended 500-word lower target", "repair_instruction": "Reach the lower target"}]
        path = directory / "submissions/advisory-qa.json"
        af.write_json(path, value)
        self.assertEqual(af.automatic_gate(directory, run, "EDITORIAL_QA", path), ("PASS", []))
        value["outcome"] = "PASS"
        value["findings"] = [{**common, "criterion": "development", "finding": "The opening satisfies the required route.", "repair_instruction": "No repair required."}]
        af.write_json(path, value)
        self.assertEqual(af.automatic_gate(directory, run, "EDITORIAL_QA", path), ("PASS", []))

    def repair_round_trip(self, criteria, factual_change=False):
        run_id = self.start()
        counts = {}
        original = self.stage_value

        def value(state, directory, run):
            counts[state] = counts.get(state, 0) + 1
            result = original(state, directory, run)
            if state in {"DRAFT", "CLAIM_VERIFICATION", "VISUAL_PLAN"} and counts[state] > 1:
                packet = af.current_packet(directory, run)[1]
                supplied = next((i for i in packet["inputs"] if i["id"] == "current-article"), None)
                self.assertIsNotNone(supplied, state)
                self.assertIn("carefully retained phrasing", Path(supplied["path"]).read_text(encoding="utf-8"))
            if state == "DRAFT":
                if counts[state] > 1:
                    result = af.artifact_path(directory, run, "article").read_text(encoding="utf-8")
                    if factual_change:
                        result = result.replace("16 records", "17 records")
                    result += "\nThe next supported connection remains visible in the revised explanation.\n"
                elif factual_change:
                    result += "\nThe fixture has 16 records.\n"
                return result
            if state == "EDIT":
                result = af.artifact_path(directory, run, "article" if af.artifact(run, "article") else "draft").read_text(encoding="utf-8")
                if "carefully retained phrasing" not in result:
                    result += "\nThis carefully retained phrasing belongs only to the accepted edit.\n"
                return result
            if state == "CLAIM_VERIFICATION":
                result["generated_at"] = f"2026-10-09T12:00:{counts[state]:02d}Z"
                if factual_change:
                    result["claims"] = [{"claim_id": "C1", "exact_claim": "The fixture has 16 records." if counts[state] == 2 else ("The fixture has 17 records." if counts[state] > 2 else "The fixture has 16 records."),
                        "class": "fact", "risk": "low", "source_tier": "primary", "source_url_or_local_id": "fixture:independent-count",
                        "source_title_and_publisher": "Independent fixture count", "exact_locator_or_supporting_excerpt": "The updated count is 17 records." if counts[state] > 1 else "Initial count: 16 records.",
                        "checked_at": af.utc_now(), "freshness_horizon": "fixture", "contradiction_status": "none_found",
                        "allowed_wording": "The fixture has 17 records." if counts[state] > 1 else "The fixture has 16 records.", "confidence": 1.0, "disposition": "qualify" if counts[state] == 2 else "use"}]
            if state == "EDITORIAL_QA":
                if counts[state] == 1:
                    result["outcome"] = "REPAIR"
                    result["findings"] = [{"criterion": c, "artifact": "article", "location": None,
                                           "finding": f"The {c} concern needs its owning stage.",
                                           "repair_instruction": f"Resolve the {c} concern.", "repair_state": "PUBLISH"} for c in criteria]
                else:
                    pending = af.json_artifact(directory, run, "editorial-repair-obligations")["pending"]
                    article = af.artifact_path(directory, run, "article").read_text(encoding="utf-8")
                    result["dimensions"]["repair_resolution"] = {o["id"]: {"status": "PASS", "surface": context.resolution_surface(af, directory, run, o["finding"])[0],
                        "finding_location": o["finding"].get("location"), "excerpt": context.resolution_surface(af, directory, run, o["finding"])[1][:60],
                        "reason": "The affected owner has rerun and the revised current affected surface supplies the supported connection."} for o in pending}
            return result

        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)), \
             mock.patch.object(self, "stage_value", side_effect=value), \
             mock.patch.object(af, "command_execute_stage", side_effect=self.execute_fixture_stage), \
             mock.patch.object(af, "command_publish_execute", side_effect=AssertionError("must not publish")):
            code, waiting = call(af.command_advance, run_id=run_id)
            self.assertEqual(waiting["state"], "VOICE_PROBE")
            choices = 0
            while code == af.EXIT_WAITING and waiting.get("state") == "VOICE_PROBE":
                choice = af.build_parser().parse_args(["choose-voice", run_id, "B", "--json"])
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    code = af.command_choose_voice(choice)
                choices += 1
                waiting = json.loads(output.getvalue())
                self.assertLessEqual(choices, 2)
            self.assertEqual(code, 0, waiting)
        directory, run = af.load_run(run_id)
        self.assertEqual(run["state"], "COMPLETE")
        article = af.artifact_path(directory, run, "article").read_text(encoding="utf-8")
        self.assertIn("carefully retained phrasing", article)
        if factual_change:
            self.assertIn("17 records", article)
            self.assertNotIn("16 records", article)
            self.assertIn("17", af.json_artifact(directory, run, "locked-fields")["tokens"]["numbers"])
        self.assertEqual(af.json_artifact(directory, run, "editorial-repair-obligations")["pending"], [])
        for event in af._read_jsonl(directory / "events.jsonl"):
            item = event.get("payload", {}).get("artifact", {})
            if item.get("type") in {"voice-anchor", "voice-probe", "voice-probe-candidates", "voice-learning", "locked-fields", "draft"}:
                self.assertEqual(af.sha256_path(directory / item["path"]), item["sha256"], item)
        return counts, choices

    def test_mixed_development_and_display_repairs_finish_with_current_authority(self):
        counts, choices = self.repair_round_trip(["development", "description"])
        self.assertEqual(counts["DRAFT"], 2)
        self.assertEqual(counts["DISPLAY_REVISION"], 2)
        self.assertEqual(choices, 2)

    def test_mixed_fact_and_prose_repairs_verify_latest_article_and_preserve_edits(self):
        counts, choices = self.repair_round_trip(["fact", "naturalness"])
        self.assertEqual(counts["CLAIM_VERIFICATION"], 3)
        self.assertEqual(counts["EDIT"], 2)
        self.assertEqual(choices, 2)

    def test_factual_content_can_change_before_new_locks_are_applied(self):
        counts, _ = self.repair_round_trip(["fact"], factual_change=True)
        self.assertEqual(counts["DRAFT"], 2)

    def test_clean_assessment_cannot_discard_pending_repair(self):
        directory, run = af.load_run(self.start())
        finding = {"criterion": "development", "finding": "Missing a supported connection", "repair_instruction": "Develop the connection", "repair_state": "DRAFT"}
        self.record_json(directory, run, "editorial-repair-obligations", {"pending": [{"id": context.obligation_id(finding), "finding": finding}]})
        result = context.assessment_findings(af, directory, run, {"outcome": "PASS", "findings": [], "dimensions": {}})
        self.assertEqual(result, [finding])
