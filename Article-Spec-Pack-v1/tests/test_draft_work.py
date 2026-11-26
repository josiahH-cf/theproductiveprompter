from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from unittest import mock

from test_article_flow_v3 import TemporaryRuntime, af, fixture_comprehension


class DraftWorkTests(TemporaryRuntime):
    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = af.main([*args, "--json"])
        return code, json.loads(output.getvalue())

    def current_run(self):
        code, capture = self.cli("capture", "Explain what the example source establishes.")
        self.assertEqual(code, af.EXIT_OK, capture)
        return af.load_run(capture["run_id"])

    def prepare_review(self, state, draft=None):
        directory, run = self.current_run()
        self.record_json(directory, run, "article-recipe", {"components": {"diagram": "auto"}, "citation_mode": "links"})
        self.record_json(directory, run, "brief", {"title": "A scoped review", "description": "The scope of an example."})
        self.record_json(directory, run, "claim-ledger", self.ledger(run, []))
        if draft:
            self.record_text(directory, run, "draft", draft)
        af.transition(directory, run, state, "test", "Set up the prior review boundary")
        return directory, run

    def claim(self, claim_id, statement, url, disposition="use"):
        return {"claim_id": claim_id, "exact_claim": statement, "class": "fact", "risk": "medium",
                "source_tier": "primary", "source_url_or_local_id": url, "source_title_and_publisher": "Example",
                "exact_locator_or_supporting_excerpt": statement, "checked_at": af.utc_now(),
                "freshness_horizon": "Bounded to this observed revision", "contradiction_status": "none_found",
                "allowed_wording": statement, "confidence": 1.0, "disposition": disposition}

    def ledger(self, run, claims):
        return {"claim_ledger_schema_version": "1.0.0", "run_id": run["run_id"],
                "generated_at": af.utc_now(), "claims": claims}

    def export(self, run, name, *flags):
        path = self.root / name
        code, payload = self.cli("work", "export", run["run_id"], "--directory", str(path), *flags)
        self.assertEqual(code, af.EXIT_OK, payload)
        return path, payload

    def return_draft(self, run, path, base, text):
        path.write_bytes(text.encode("utf-8"))
        return self.cli("work", "import", run["run_id"], "--file", str(path), "--base-sha256", base)

    def test_lock_write_denial_keeps_one_recoverable_capture_and_no_dispatch(self):
        denial = PermissionError(13, "Windows lock write denied", str(self.runtime / "models" / ".lock"))
        with mock.patch.object(af, "publish_lock_owner", side_effect=denial):
            code, interrupted = self.cli("capture", "Verbatim intake with original scope.", "--auto")
        self.assertEqual(code, af.EXIT_WAITING, interrupted)
        run_id = interrupted["details"]["run_id"]
        directory, run = af.load_run(run_id)
        self.assertEqual(run["state"], "NEW")
        self.assertEqual(af.artifact_path(directory, run, "seed").read_text(encoding="utf-8"),
                         "Verbatim intake with original scope.")
        self.assertEqual(list((directory / "tasks").iterdir()), [])
        self.assertFalse((af.model_state_root() / "assignments.jsonl").exists())
        code, next_action = self.cli("next", run_id)
        self.assertEqual(code, af.EXIT_WAITING)
        self.assertEqual(next_action["action"], "intake_recovery")
        export, handoff = self.export(run, "intake-copy", "--include-private")
        self.assertEqual(handoff["base_sha256"], "none")
        self.assertIn("Verbatim intake", (export / "private-context.json").read_text(encoding="utf-8"))
        code, resumed = self.cli("resume-intake", run_id)
        self.assertEqual(code, af.EXIT_OK, resumed)
        self.assertEqual(resumed["state"], "RESEARCH_PLAN")
        self.assertTrue(self.cli("resume-intake", run_id)[1]["idempotent"])
        self.assertEqual(len(af._read_jsonl(af.model_state_root() / "assignments.jsonl")), 1)
        self.assertEqual(list((directory / "tasks").iterdir()), [])
        self.assertEqual([path.name for path in af.runs_root().glob("AF-*")], [run_id])

    def test_outside_handoff_before_qa_keeps_warning_and_no_publication(self):
        source = "Public draft paragraph with [context](https://example.org/notes)."
        directory, run = self.prepare_review("EDITORIAL_QA", source)
        self.record_json(directory, run, "author-context", {"responses": [{"exact_author_response": "private detail"}]})
        asset = self.record_text(directory, run, "visual-asset:example", '<svg viewBox="0 0 4 4"/>', "example.svg")
        self.record_json(directory, run, "visual-manifest", {"assets": [{"visual_id": "example", "sha256": af.sha256_path(asset),
                          "source_path": "artifacts/example.svg", "public_path": "/assets/articles/example/example.svg"}]})
        findings = [{"criterion": "editorial_dimension", "finding": "Unresolved private review detail."}]
        af.write_gate_receipt(directory, run, "G-EDITORIAL-QA", "REPAIR", findings, {"type": "code"})
        before = (directory / "events.jsonl").read_bytes()
        path, handoff = self.export(run, "handoff")
        self.assertEqual((path / "draft.md").read_text(encoding="utf-8"), source)
        self.assertEqual((path / handoff["assets"][0]["file"]).read_bytes(), asset.read_bytes())
        self.assertEqual(handoff["unresolved_checks"][0]["gate"], "G-EDITORIAL-QA")
        self.assertEqual(handoff["verification"], "working_copy")
        self.assertFalse(handoff["publication_authorized"])
        self.assertFalse((path / "private-context.json").exists())
        self.assertNotIn("private detail", (path / "handoff.json").read_text(encoding="utf-8"))
        self.assertEqual((directory / "events.jsonl").read_bytes(), before)
        code, imported = self.return_draft(run, path / "draft.md", handoff["base_sha256"], source + "\n\nA clearer example.")
        self.assertEqual(code, af.EXIT_OK, imported)
        self.assertFalse(imported["publication_authorized"])
        _, updated = af.load_run(run["run_id"])
        self.assertEqual(updated["state"], "EDITORIAL_QA")
        self.assertEqual(af.json_artifact(directory, updated, "gate-receipt:G-EDITORIAL-QA")["outcome"], "REPAIR")
        self.assertFalse(af.artifact(updated, "publish-approval"))
        self.assertFalse(list((directory / "publication").iterdir()))
        stale, conflict = self.return_draft(run, path / "draft.md", handoff["base_sha256"], source + "\n\nConflicting edit.")
        self.assertEqual(stale, af.EXIT_WAITING, conflict)

    def test_broken_citation_can_be_repaired_outside_with_only_affected_fetch(self):
        stable_url = "https://example.org/retained"
        broken_url = "https://example.org/missing"
        new_url = "https://example.org/replacement"
        stable = "The example retains a stable baseline."
        old = "The obsolete document gave a secondary example."
        corrected = "The updated source gives the current secondary example."
        prior = f"{stable} [Source]({stable_url}).\n\n{old} [Extra]({broken_url})."
        returned = f"{stable} [Source]({stable_url}).\n\n{corrected} [Current source]({new_url})."
        directory, run = self.prepare_review("CLAIM_VERIFICATION", prior)
        rows = [self.claim("C1", stable, stable_url), self.claim("C2", old, broken_url)]
        self.record_json(directory, run, "verified-claim-ledger", self.ledger(run, rows), "baseline-ledger.json")
        af.write_gate_receipt(directory, run, "G-CLAIMS-VERIFIED", "PASS", [], {"type": "code"})
        af.write_gate_receipt(directory, run, "G-CLAIMS-VERIFIED", "REPAIR",
                              [{"criterion": "source_resolution", "location": "C2", "finding": "HTTP 404"}],
                              {"type": "code"})
        run["status"] = "BLOCKED"
        af.save_run(directory, run)
        code, blocker = self.cli("next", run["run_id"])
        self.assertEqual(code, af.EXIT_WAITING)
        self.assertEqual(blocker["findings"][0]["finding"], "HTTP 404")
        path, handoff = self.export(run, "outside")
        code, result = self.return_draft(run, path / "draft.md", handoff["base_sha256"], returned)
        self.assertEqual(code, af.EXIT_OK, result)
        ledger_path = path / "ledger.json"
        af.write_json(ledger_path, self.ledger(run, [self.claim("C2", corrected, new_url)]))
        with mock.patch.object(af, "fetch_url", return_value=(200, b"current source", {})) as fetch:
            code, review = self.cli("work", "check", run["run_id"], "--ledger", str(ledger_path))
        self.assertEqual(code, af.EXIT_OK, review)
        self.assertEqual(review["findings"], [])
        self.assertEqual(review["scope"]["carried_claim_ids"], ["C1"])
        self.assertEqual(review["scope"]["changed_paragraphs"], [2])
        self.assertEqual(review["checked_claim_ids"], ["C2"])
        self.assertEqual(review["editorial_qa"], "unchecked")
        fetch.assert_called_once_with(new_url, timeout=15)
        plan_file = path / "visual-plan.json"
        af.write_json(plan_file, {"visual_plan_schema_version": "1.0.0", "run_id": run["run_id"], "visuals": [],
                                 "omission_reason": "The two short examples do not need a separate diagram."})
        code, resumed = self.cli("work", "resume", run["run_id"], "--visual-plan", str(plan_file))
        self.assertEqual(code, af.EXIT_OK, resumed)
        self.assertEqual(resumed["state"], "VISUAL_RENDER")
        self.assertEqual(self.cli("render-visuals", run["run_id"])[1]["state"], "POST_EDIT_CLAIM_VERIFICATION")
        _, reviewed = af.load_run(run["run_id"])
        self.assertEqual(af.artifact_path(directory, reviewed, "article").read_text(encoding="utf-8"), returned)
        self.assertEqual(af.json_artifact(directory, reviewed, "gate-receipt:G-CLAIMS-VERIFIED")["outcome"], "REPAIR")
        self.assertIsNone(af.artifact(reviewed, "voice-learning"))
        self.assertIsNone(af.artifact(reviewed, "gate-receipt:G-POST-EDIT-CLAIMS"))
        self.assertIsNone(af.artifact(reviewed, "publish-approval"))

        path, claim_offer = self.export(reviewed, "ready-for-claims")
        claim_scope = claim_offer["outside_review"]["scope_sha256"]
        self.assertEqual(claim_offer["outside_review"]["review"], "claims")
        with mock.patch.object(af, "route_candidates", side_effect=AssertionError("No provider should be required")), \
             mock.patch.object(af, "fetch_url", side_effect=AssertionError("The exact reviewed sources should carry forward")):
            code, verified = self.cli("work", "submit", run["run_id"], "claims", "--file", str(ledger_path),
                                      "--scope-sha256", claim_scope)
        self.assertEqual(code, af.EXIT_OK, verified)
        self.assertEqual(verified["state"], "DISPLAY_REVISION")
        self.assertFalse(verified["publication_authorized"])
        self.assertTrue(self.cli("work", "submit", run["run_id"], "claims", "--file", str(ledger_path),
                                 "--scope-sha256", claim_scope)[1]["idempotent"])
        qa = {
            "editorial_assessment_schema_version": "1.0.0", "run_id": run["run_id"],
            "outcome": "PASS", "calibration_status": "uncalibrated-advisory", "findings": [],
            "dimensions": {name: {} for name in ("intent_fidelity", "clarity_utility", "voice_fit", "naturalness",
                           "public_surface_voice", "structural_interest", "proportional_length")},
            "naturalization_review": {name: {"status": "PASS", "excerpt": stable,
                                               "reason": "The example keeps the source and scope visible in direct language."}
                                      for name in ("language", "rhetoric", "structure", "preservation")},
            "comprehension_review": fixture_comprehension(returned, excerpt=stable),
        }
        qa_path = path / "assessment.json"
        qa_scope = verified["outside_review"]["scope_sha256"]
        wrong = {**qa, "naturalization_review": {**qa["naturalization_review"],
                 "language": {"status": "PASS", "excerpt": "This was never in the manuscript.",
                              "reason": "An invented excerpt must fail the contextual review."}}}
        af.write_json(qa_path, wrong)
        code, failed = self.cli("work", "submit", run["run_id"], "qa", "--file", str(qa_path),
                                 "--scope-sha256", qa_scope)
        self.assertEqual(code, af.EXIT_WAITING, failed)
        self.assertTrue(failed["details"]["findings"])
        _, still_open = af.load_run(run["run_id"])
        _, failure_handoff = self.export(still_open, "review-warning")
        self.assertIn("G-EDITORIAL-QA", [row["gate"] for row in failure_handoff["unresolved_checks"]])
        af.write_json(qa_path, qa)
        code, accepted = self.cli("work", "submit", run["run_id"], "qa", "--file", str(qa_path),
                                   "--scope-sha256", qa_scope)
        self.assertEqual(code, af.EXIT_OK, accepted)
        self.assertEqual(accepted["state"], "PACKAGE")
        self.assertFalse(list((directory / "tasks").iterdir()))
        with mock.patch.object(af, "command_publish_execute", side_effect=AssertionError("Draft work cannot publish")):
            code, hold = self.cli("advance", run["run_id"])
        self.assertEqual(code, af.EXIT_WAITING, hold)
        self.assertEqual(hold["action"], "publication_hold")
        _, checked = af.load_run(run["run_id"])
        self.assertIsNone(af.artifact(checked, "publish-approval"))
        self.assertIsNone(af.artifact(checked, "live-verification"))
        packaged = af.load_json(directory / "package/package.json")
        self.assertEqual(packaged["model_attribution"]["footer_text"], af.draft_work.ATTRIBUTION)
