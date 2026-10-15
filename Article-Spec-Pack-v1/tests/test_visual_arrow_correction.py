"""Scoped SVG correction preserves run authority and cannot replace arbitrary assets."""
import copy
import xml.etree.ElementTree as ET
from unittest import mock

import test_article_flow_v3 as fixtures

af, call = fixtures.af, fixtures.call


class VisualReturnCorrectionTests(fixtures.TemporaryRuntime):
    def rendered_run(self):
        run_id = self.start("Explain an approved frame and a separate, deliberate continuation.")
        directory, run = af.load_run(run_id)
        self.record_json(directory, run, "brief", {
            "brief_schema_version": "1.0.0", "run_id": run_id, "title": "A retained research record",
            "slug": "retained-research-record", "description": "A bounded workflow explanation.", "date": "2026-10-15",
            "tags": [], "reader_job": "Understand the boundaries", "scope": "The documented process", "exclusions": [],
            "claims_to_support": [], "acceptance_criteria": ["Preserve the selected passages and truthful diagrams."],
        })
        self.record_text(directory, run, "draft", "# A retained research record\n\n"
                         "The exact newly selected paragraph stays here.\n\n## Research boundaries\n\n"
                         "The distinct earlier selected paragraph stays here.\n\n"
                         "```text\n  literal evidence  \n\nkeeps spacing\n```\n")
        visual = {
            "visual_id": "frame-review-frozen-source", "kind": "parallel_review", "title": "Frame and Frozen Source",
            "purpose": "Show forward investigation, reconciliation, snapshot reuse and terminal deferral.",
            "placement": {"after_heading": "Research boundaries"},
            "alt_text": "The approved frame branches and rejoins before a frozen source; presentation does not restart research.",
            "caption": "A conceptual view of the forward path, with deliberate continuation handled separately.",
            "claim_ids": [], "labels": ["Approved frame", "Investigation", "Review", "Reconcile claims", "Frozen source",
                                         "HTML reuses snapshot", "Claims deferred", "Records retained"],
            "design_rationale": "The overview shows forward flow only. Explicitly invoked continuation is a separate view, so return arrows would falsely authorize new research.",
        }
        second = {**visual, "visual_id": "research-loop", "kind": "delivery_loop", "title": "Research Round",
                  "placement": {"after_paragraph": "The distinct earlier selected paragraph stays here."},
                  "labels": ["Research", "Review reopens needed work"]}
        self.record_json(directory, run, "visual-plan", {"visual_plan_schema_version": "1.0.0", "run_id": run_id, "visuals": [visual, second]})
        af.transition(directory, run, "VISUAL_RENDER", "test", "Render the accepted plan")
        call(af.command_visual_render, run_id=run_id)
        directory, run = af.load_run(run_id)
        self.record_text(directory, run, "article", af.artifact_path(directory, run, "draft").read_text(encoding="utf-8"))
        run["attempts"]["VISUAL_PLAN"] = 8
        run.setdefault("attempt_baselines", {})["VISUAL_PLAN"] = 6
        af.save_run(directory, run)
        asset = af.json_artifact(directory, run, "visual-manifest")["assets"][0]
        before = (directory / asset["source_path"]).read_bytes()
        candidate = self.root / "reviewed-forward-only.svg"
        # Independent construction of the exact reviewed deletion set.
        expected = before
        for path in ("M45 860 H25 V695 H40", "M465 1050 H740 V85 H380 V105", "M715 710 H740"):
            expected = expected.replace(f'<path d="{path}" class="arrow return"/>'.encode(), b"")
        candidate.write_bytes(expected)
        values = {"run_id": run_id, "correct_return_arrows": visual["visual_id"], "replacement_svg": str(candidate),
                  "expected_source_sha256": af.sha256_bytes(before), "reason": "The author approved only the reviewed return-arrow correction."}
        return directory, run, candidate, values

    def test_exact_correction_preserves_prose_counters_approvals_history_and_other_assets(self):
        directory, run, candidate, values = self.rendered_run()
        before = copy.deepcopy(run)
        manifest = af.json_artifact(directory, run, "visual-manifest")
        old_manifest_path = af.artifact_path(directory, run, "visual-manifest")
        old_manifest_bytes = old_manifest_path.read_bytes()
        old_svg = (directory / manifest["assets"][0]["source_path"]).read_bytes()
        prose = {kind: af.artifact_path(directory, run, kind).read_bytes() for kind in ("article", "draft")}
        event_prefix = (directory / run["event_log"]).read_bytes()
        code, result = call(af.command_visual_render, **values)
        self.assertEqual(code, af.EXIT_OK, result)
        directory, current = af.load_run(run["run_id"])
        for field in ("state", "status", "attempts", "attempt_baselines", "run_overrides", "publication"):
            self.assertEqual(current.get(field), before.get(field), field)
        for kind, data in prose.items():
            self.assertEqual(af.artifact_path(directory, current, kind).read_bytes(), data)
        self.assertEqual(af.artifact(current, "visual-plan"), af.artifact(before, "visual-plan"))
        self.assertEqual(old_manifest_path.read_bytes(), old_manifest_bytes)
        self.assertEqual((directory / manifest["assets"][0]["source_path"]).read_bytes(), old_svg)
        self.assertTrue((directory / current["event_log"]).read_bytes().startswith(event_prefix))
        changed = af.json_artifact(directory, current, "visual-manifest")
        self.assertEqual(changed["assets"][1], manifest["assets"][1])
        target = changed["assets"][0]
        for field in ("kind", "title", "alt_text", "caption", "placement", "claim_ids", "public_path"):
            self.assertEqual(target[field], manifest["assets"][0][field], field)
        corrected = (directory / target["source_path"]).read_bytes()
        self.assertEqual(corrected, candidate.read_bytes())
        root = ET.fromstring(corrected)
        paths = root.findall(".//{http://www.w3.org/2000/svg}path")
        self.assertEqual(sum(p.get("class") == "arrow" for p in paths), 8)
        self.assertFalse(any(p.get("class") == "arrow return" for p in paths))
        self.assertEqual(af.validate_visual_manifest(directory, current, af.artifact_path(directory, current, "visual-manifest")), [])
        self.assertTrue(af.verify_event_log(directory, current)[0])

    def test_identical_retry_is_observer_pure(self):
        directory, run, _, values = self.rendered_run()
        call(af.command_visual_render, **values)
        event_bytes = (directory / run["event_log"]).read_bytes()
        cache = (directory / "run.json").read_bytes()
        _, result = call(af.command_visual_render, **values)
        self.assertTrue(result["idempotent"])
        self.assertEqual((directory / run["event_log"]).read_bytes(), event_bytes)
        self.assertEqual((directory / "run.json").read_bytes(), cache)

    def test_held_refresh_retains_approved_correction(self):
        directory, run, candidate, values = self.rendered_run()
        call(af.command_visual_render, **values)
        directory, run = af.load_run(run["run_id"])
        af.transition(directory, run, "PUBLISH_APPROVAL", "test", "Exercise normal held refresh")
        call(af.command_visual_render, run_id=run["run_id"], refresh=True)
        directory, run = af.load_run(run["run_id"])
        target = af.json_artifact(directory, run, "visual-manifest")["assets"][0]
        self.assertEqual((directory / target["source_path"]).read_bytes(), candidate.read_bytes())
        self.assertEqual(run["state"], "PACKAGE")

    def test_retry_settles_a_manifest_committed_before_its_gate(self):
        directory, run, _, values = self.rendered_run()
        with mock.patch.object(af, "write_gate_receipt", side_effect=RuntimeError("simulated interruption")):
            with self.assertRaises(RuntimeError):
                call(af.command_visual_render, **values)
        directory, pending = af.load_run(run["run_id"])
        counters = copy.deepcopy(pending["attempts"])
        _, result = call(af.command_visual_render, **values)
        self.assertFalse(result["idempotent"])
        directory, settled = af.load_run(run["run_id"])
        gate = af.json_artifact(directory, settled, "gate-receipt:G-VISUAL-RENDER")
        self.assertEqual(gate["artifact_hashes"]["visual-manifest"], af.artifact(settled, "visual-manifest")["sha256"])
        self.assertEqual(settled["attempts"], counters)
        self.assertTrue(af.verify_event_log(directory, settled)[0])
        _, final = call(af.command_visual_render, **values)
        self.assertTrue(final["idempotent"])

    def test_correction_authority_is_not_applied_to_a_different_plan(self):
        directory, run, _, values = self.rendered_run()
        call(af.command_visual_render, **values)
        directory, run = af.load_run(run["run_id"])
        visual = af.json_artifact(directory, run, "visual-plan")["visuals"][0]
        self.assertEqual(af.scoped_visual_svg(directory, run, visual, "f" * 64), af.render_visual_svg(visual))

    def test_arbitrary_svg_changes_and_wrong_source_hash_are_rejected_without_events(self):
        directory, run, candidate, values = self.rendered_run()
        events = (directory / run["event_log"]).read_bytes()
        original = candidate.read_bytes()
        for bad in (original.replace(b"Approved frame", b"Automatically restart"), original + b"<script/>", original.replace(b'M255 750 V805', b'M255 750 V1')):
            candidate.write_bytes(bad)
            with self.assertRaises(af.FlowError):
                call(af.command_visual_render, **values)
            self.assertEqual((directory / run["event_log"]).read_bytes(), events)
        candidate.write_bytes(original)
        with self.assertRaises(af.FlowError):
            call(af.command_visual_render, **{**values, "expected_source_sha256": "0" * 64})
        self.assertEqual((directory / run["event_log"]).read_bytes(), events)

    def test_stops_wrong_stage_and_dispatched_claim_task_cannot_be_bypassed(self):
        directory, run, _, values = self.rendered_run()
        for status in ("BLOCKED", "WAITING_MODEL", "WAITING_HUMAN"):
            run["status"] = status
            af.save_run(directory, run)
            events = (directory / run["event_log"]).read_bytes()
            with self.assertRaises(af.FlowError):
                call(af.command_visual_render, **values)
            self.assertEqual((directory / run["event_log"]).read_bytes(), events)
        run["status"] = "ACTIVE"
        af.save_run(directory, run)
        events = (directory / run["event_log"]).read_bytes()
        with mock.patch.object(af, "latest_task_packet_item", return_value={"sha256": "a" * 64}), \
                mock.patch.object(af, "validate_recorded_task_packet", return_value=(directory / "pending.json", {"attempt": 1}, None)), \
                mock.patch.object(af, "task_packet_dispatch_sequence", return_value=1), \
                mock.patch.object(af, "task_packet_gate_consumed", return_value=False):
            with self.assertRaises(af.FlowError):
                call(af.command_visual_render, **values)
        self.assertEqual((directory / run["event_log"]).read_bytes(), events)
        af.transition(directory, run, "VISUAL_PLAN", "test", "A different stage owns work")
        with self.assertRaises(af.FlowError):
            call(af.command_visual_render, **values)

    def test_tampered_correction_and_changed_renderer_fail_closed(self):
        directory, run, _, values = self.rendered_run()
        call(af.command_visual_render, **values)
        directory, run = af.load_run(run["run_id"])
        plan = af.json_artifact(directory, run, "visual-plan")
        visual = plan["visuals"][0]
        plan_hash = af.artifact(run, "visual-plan")["sha256"]
        native_renderer = af.render_visual_svg
        with mock.patch.object(af, "render_visual_svg", side_effect=lambda v: native_renderer(v) + b"<!-- drift -->"):
            with self.assertRaises(af.FlowError):
                af.scoped_visual_svg(directory, run, visual, plan_hash)
        receipt = af.artifact_path(directory, run, "visual-return-correction:" + visual["visual_id"])
        receipt.write_text("{}", encoding="utf-8")
        with self.assertRaises(af.FlowError):
            af.scoped_visual_svg(directory, run, visual, plan_hash)

    def test_actual_authorization_and_explicit_mode_are_required(self):
        _, _, _, values = self.rendered_run()
        for updates in ({"reason": ""}, {"replacement_svg": None}, {"refresh": True}, {"correct_return_arrows": None}):
            with self.assertRaises(af.FlowError):
                call(af.command_visual_render, **{**values, **updates})
