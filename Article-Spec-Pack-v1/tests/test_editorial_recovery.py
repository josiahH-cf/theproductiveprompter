"""Regressions for owned review surfaces and immutable legacy-obligation recovery."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_context as context
import test_article_flow_v3 as fixtures

af, call = fixtures.af, fixtures.call


class EditorialRecoveryTests(fixtures.TemporaryRuntime):
    anchor = fixtures.UsefulVisualPolicyTests.anchor
    fixture = fixtures.UsefulVisualPolicyTests.fixture

    def prepared(self):
        directory, run, _, _ = self.fixture(current=True)
        af.transition(directory, run, "VISUAL_RENDER", "test", "Render reviewed caption")
        call(af.command_visual_render, run_id=run["run_id"])
        directory, run = af.load_run(run["run_id"])
        self.record_text(directory, run, "article", '---\ndescription: "An imprecise old description needs revision."\n---\n\n' + af.artifact_path(directory, run, "draft").read_text(encoding="utf-8"))
        self.record_json(directory, run, "brief", {"slug": "competing-effects", "title": "Two competing effects", "description": "The supported competing effects remain uncertain."}, "review-brief.json")
        for kind in ("verified-claim-ledger", "post-edit-claim-ledger", "voice-learning"):
            self.record_json(directory, run, kind, {})
        af.transition(directory, run, "EDITORIAL_QA", "test", "Original review inputs")
        with af.run_lock(directory, run):
            packet_path, packet = af.task_packet(directory, run)
        return directory, run, packet_path, packet

    def legacy_obligation(self, directory, run, packet_path, packet, excerpt):
        finding = {"criterion": "contextual_naturalness", "artifact": "article", "location": excerpt,
                   "finding": "The assessed language needs a focused correction.",
                   "repair_instruction": "Repair the affected prose while preserving its proposition and locked material.", "repair_state": "EDIT"}
        assessment = {"outcome": "REPAIR", "findings": [], "dimensions": {}}
        self.record_json(directory, run, "editorial-qa", assessment)
        af.write_gate_receipt(directory, run, "G-EDITORIAL-QA", "REPAIR", [finding], {"type": "test"}, "EDIT",
                              task_state="EDITORIAL_QA", task_attempt=packet["attempt"], task_packet_sha256=af.sha256_path(packet_path))
        context.record_assessment(af, directory, run, assessment, [finding], "REPAIR")
        old_path = af.artifact_path(directory, run, "editorial-repair-obligations")
        return finding, old_path, old_path.read_bytes(), af.load_json(old_path)["pending"][0]

    def test_new_naturalization_findings_use_visual_display_and_body_owners(self):
        directory, run, _, _ = self.prepared()
        caption = af.json_artifact(directory, run, "visual-manifest")["assets"][0]["caption"]
        for excerpt, expected in ((caption, "VISUAL_PLAN"), ("An imprecise old description needs revision.", "EDIT"), (af.json_artifact(directory, run, "brief")["description"], "DISPLAY_REVISION"), (self.anchor, "EDIT")):
            with self.subTest(expected=expected):
                review = {key: {"status": "PASS", "excerpt": self.anchor, "reason": "The excerpt explains the specific competing mechanisms clearly."} for key in ("language", "rhetoric", "structure", "preservation")}
                review["language"].update(status="REPAIR", excerpt=excerpt)
                findings = af.naturalization_review_findings(directory, run, {"naturalization_review": review}, "qa")
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0]["repair_state"], expected)
                self.assertNotEqual(findings[0]["location"], excerpt)
        self.assertEqual(context.current_excerpt_owner(af, directory, run, self.anchor)["location"], "paragraph 1")

    def test_legacy_caption_normalization_keeps_identity_and_requires_specific_resolution(self):
        directory, run, packet_path, packet = self.prepared()
        caption = af.json_artifact(directory, run, "visual-manifest")["assets"][0]["caption"]
        finding, old_path, old_bytes, old = self.legacy_obligation(directory, run, packet_path, packet, caption)
        recovered = context.normalized_obligations(af, directory, run)["pending"][0]
        self.assertEqual(recovered["id"], old["id"])
        self.assertEqual(recovered["finding"], finding)
        self.assertEqual(recovered["source_sha256"], old["source_sha256"])
        self.assertEqual(recovered["normalization"]["selector"]["location"], "visual:competing-effects:caption")
        self.assertEqual(old_path.read_bytes(), old_bytes)
        reason = "The prose explains both mechanisms; the omitted graph would imply an unsupported relationship."
        plan_path = self.record_json(directory, run, "visual-plan", {"visual_plan_schema_version": "1.0.0", "run_id": run["run_id"], "visuals": [], "omission_reason": reason}, "omitted-plan.json")
        self.record_json(directory, run, "visual-manifest", {"visual_manifest_schema_version": "1.0.0", "run_id": run["run_id"], "visual_plan_sha256": af.sha256_path(plan_path), "assets": [], "omission_reason": reason}, "omitted-manifest.json")
        resolution = {"status": "PASS", "surface": "visual-plan+manifest", "finding_location": finding["location"], "excerpt": self.anchor, "reason": "This unrelated prose is not evidence about the bound caption."}
        assessment = {"outcome": "PASS", "findings": [], "dimensions": {"repair_resolution": {old["id"]: resolution}}}
        self.assertTrue(context.assessment_findings(af, directory, run, assessment))
        resolution["excerpt"] = reason
        self.assertEqual(context.assessment_findings(af, directory, run, assessment), [])
        context.record_assessment(af, directory, run, assessment, [], "PASS")
        self.assertEqual(af.json_artifact(directory, run, "editorial-repair-obligations")["pending"], [])
        self.assertEqual(old_path.read_bytes(), old_bytes)

    def test_recovery_requires_intact_original_sources_and_display_field(self):
        directory, run, packet_path, packet = self.prepared()
        excerpt = "An imprecise old description needs revision."
        _, _, _, old = self.legacy_obligation(directory, run, packet_path, packet, excerpt)
        recovered = context.normalized_obligations(af, directory, run)["pending"][0]
        self.assertEqual(recovered["normalization"]["selector"], {"artifact": "article", "location": "frontmatter.description", "repair_state": "EDIT"})
        resolution = {"status": "PASS", "surface": "brief.description", "finding_location": excerpt, "excerpt": self.anchor, "reason": "A body passage cannot clear the separately owned description."}
        assessment = {"outcome": "PASS", "findings": [], "dimensions": {"repair_resolution": {old["id"]: resolution}}}
        self.assertTrue(context.assessment_findings(af, directory, run, assessment))
        resolution["excerpt"] = af.json_artifact(directory, run, "brief")["description"]
        self.assertTrue(context.assessment_findings(af, directory, run, assessment))
        resolution["surface"] = "article.frontmatter.description"
        self.assertTrue(context.assessment_findings(af, directory, run, assessment))
        article = af.artifact_path(directory, run, "article").read_text(encoding="utf-8").replace(excerpt, resolution["excerpt"])
        self.record_text(directory, run, "article", article, "corrected-frontmatter.md")
        self.assertEqual(context.assessment_findings(af, directory, run, assessment), [])

        other_directory, other_run, source_path, other_packet = self.prepared()
        self.legacy_obligation(other_directory, other_run, source_path, other_packet, excerpt)
        source_path.write_bytes(source_path.read_bytes() + b' ')
        with self.assertRaisesRegex(af.FlowError, "recovery source changed"):
            context.normalized_obligations(af, other_directory, other_run)

    def test_ambiguous_or_unproven_locations_stay_unresolved(self):
        directory, run, packet_path, packet = self.prepared()
        missing = "This was never part of the original reviewed article."
        _, _, _, old = self.legacy_obligation(directory, run, packet_path, packet, missing)
        pending = context.normalized_obligations(af, directory, run)["pending"][0]
        self.assertNotIn("normalization", pending)
        self.assertEqual(pending["id"], old["id"])
        self.assertIsNone(context.excerpt_owner(af, self.anchor + '\n\n' + self.anchor, {}, {}, self.anchor))
        self.assertIsNone(context.excerpt_owner(af, "# Body\n", {"title": missing, "description": missing}, {}, missing))

    def test_recovery_reads_original_sources_after_later_artifacts_replace_the_index(self):
        for replaced in ("article", "brief", "visual-manifest", "gate-receipt", "all"):
            with self.subTest(replaced=replaced):
                directory, run, packet_path, packet = self.prepared()
                caption = af.json_artifact(directory, run, "visual-manifest")["assets"][0]["caption"]
                finding, old_path, old_bytes, old = self.legacy_obligation(directory, run, packet_path, packet, caption)
                if replaced in {"article", "all"}:
                    self.record_text(directory, run, "article", "# A corrected article\n\nThe current explanation is different.\n", "later-article.md")
                if replaced in {"brief", "all"}:
                    self.record_json(directory, run, "brief", {"title": "A later title", "description": "A later description."}, "later-brief.json")
                if replaced in {"visual-manifest", "all"}:
                    self.record_json(directory, run, "visual-manifest", {"assets": []}, "later-manifest.json")
                if replaced in {"gate-receipt", "all"}:
                    af.write_gate_receipt(directory, run, "G-EDITORIAL-QA", "REPAIR", [], {"type": "test"}, "EDITORIAL_QA")
                recovered = context.normalized_obligations(af, directory, run)["pending"][0]
                self.assertEqual(recovered["id"], old["id"])
                self.assertEqual(recovered["finding"], finding)
                self.assertEqual(recovered["normalization"]["selector"]["location"], "visual:competing-effects:caption")
                self.assertEqual(old_path.read_bytes(), old_bytes)

    def test_recovery_rejects_tampered_historical_sources_and_event_chain(self):
        for changed in ("article", "brief", "visual-manifest", "gate-receipt:G-EDITORIAL-QA", "events"):
            with self.subTest(changed=changed):
                directory, run, packet_path, packet = self.prepared()
                caption = af.json_artifact(directory, run, "visual-manifest")["assets"][0]["caption"]
                self.legacy_obligation(directory, run, packet_path, packet, caption)
                path = directory / run["event_log"] if changed == "events" else af.artifact_path(directory, run, changed)
                if changed == "events":
                    path.write_bytes(path.read_bytes().replace(b'"test"', b'"changed"', 1))
                else:
                    path.write_bytes(path.read_bytes() + b' ')
                with self.assertRaisesRegex(af.FlowError, "recovery (source|event history) changed"):
                    context.normalized_obligations(af, directory, run)

    def test_late_visual_amendment_cannot_reuse_old_prose_in_a_qa_fallback(self):
        directory, run, packet_path, packet = self.prepared()
        old_bytes = packet_path.read_bytes()
        old_article = next(i for i in packet["inputs"] if i["id"] == "article")
        with af.run_lock(directory, run):
            af.abandon_cached_packet(directory, run, "EDITORIAL_QA", af.latest_task_packet_item(directory, run, "EDITORIAL_QA"), {"reason": "fixture_provider_failure"})
            run.setdefault("route_retry_candidates", {})["EDITORIAL_QA"] = packet["selected_route"]["candidates"]
            af.save_run(directory, run)
        call(af.command_amend, run_id=run["run_id"], diagrams="off", title=None, description=None, article=None,
             reason="A reviewed graph implies an unsupported relationship; omit it and reassess current prose.")
        directory, run = af.load_run(run["run_id"])
        self.assertNotIn("EDITORIAL_QA", run.get("route_retry_candidates", {}))
        self.record_json(directory, run, "visual-plan", {"visual_plan_schema_version": "1.0.0", "run_id": run["run_id"], "visuals": [],
                         "omission_reason": "The prose explains both mechanisms without the misleading graph."}, "late-empty-plan.json")
        af.transition(directory, run, "VISUAL_RENDER", "test", "Render the checked omission")
        call(af.command_visual_render, run_id=run["run_id"])
        directory, run = af.load_run(run["run_id"])
        self.record_json(directory, run, "post-edit-claim-ledger", {"checked_revision": "current"}, "later-claims.json")
        self.record_json(directory, run, "brief", {"title": "Two competing effects", "description": "Current scoped description."}, "later-display.json")
        af.transition(directory, run, "EDITORIAL_QA", "test", "Return after renewed verification")
        self.assertNotEqual(af.artifact(run, "article")["sha256"], old_article["sha256"])
        # Also exercise stale cached authority independently of the epoch reset.
        run.setdefault("route_retry_candidates", {})["EDITORIAL_QA"] = packet["selected_route"]["candidates"]
        with af.run_lock(directory, run):
            _, renewed = af.task_packet(directory, run)
        inputs = {i["id"]: i for i in renewed["inputs"]}
        for kind in ("article", "brief", "post-edit-claim-ledger", "visual-plan", "visual-manifest"):
            self.assertEqual(inputs[kind]["sha256"], af.artifact(run, kind)["sha256"])
        self.assertTrue(af.qa_packet_has_current_visuals(directory, run, renewed))
        self.assertEqual(packet_path.read_bytes(), old_bytes)

    def test_draft_caption_ownership_requires_the_exact_manifest_image_path(self):
        directory, run, _, _ = self.prepared()
        manifest = af.json_artifact(directory, run, "visual-manifest")
        visual = manifest["assets"][0]
        caption = "An old internal production note must be removed."
        image = "![A conceptual relationship](" + visual["public_path"] + ")\n\n*" + caption + "*"
        selector = context.excerpt_owner(af, image, {}, manifest, caption)
        self.assertEqual(selector, {"artifact": "visual-manifest", "location": "visual:competing-effects:caption", "repair_state": "VISUAL_PLAN"})
        other = image.replace(visual["public_path"], "/assets/unrelated.svg")
        self.assertEqual(context.excerpt_owner(af, other, {}, manifest, caption)["repair_state"], "EDIT")
        self.assertIsNone(context.excerpt_owner(af, image + "\n\n" + image, {}, manifest, caption))
