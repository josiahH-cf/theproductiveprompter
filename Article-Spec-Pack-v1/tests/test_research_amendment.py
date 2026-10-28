"""Same-run author-context corrections must reach research and every reviewer."""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import test_article_flow_v3 as fixtures
import test_editorial_recovery as recovery

af, call = fixtures.af, fixtures.call


class ResearchAmendmentTests(fixtures.TemporaryRuntime):
    anchor = fixtures.UsefulVisualPolicyTests.anchor
    fixture = fixtures.UsefulVisualPolicyTests.fixture
    prepared = recovery.EditorialRecoveryTests.prepared
    reason = "The author approved adding the new assistant example, with dated primary sources and provider-claim limits. Preserve the real prior voice choice; verify the new claims and rebuild the brief."

    def reopen(self, run, **kwargs):
        return call(af.command_amend, run_id=run["run_id"], reopen_research=True, reason=self.reason, **kwargs)

    def test_same_run_rebuild_preserves_seed_prose_prior_packets_and_frozen_definitions(self):
        directory, run, old_packet, _ = self.prepared()
        preserved = {path: path.read_bytes() for path in (
            old_packet, af.artifact_path(directory, run, "seed"), af.artifact_path(directory, run, "article"),
            af.artifact_path(directory, run, "effective-definitions"), af.artifact_path(directory, run, "brief"),
        )}
        before_assignment = run["model_experiment"]
        code, payload = self.reopen(run)
        self.assertEqual(code, af.EXIT_OK)
        self.assertEqual(payload["state"], "RESEARCH_PLAN")
        directory, latest = af.load_run(run["run_id"])
        self.assertEqual(latest["run_id"], run["run_id"])
        self.assertEqual(latest["model_experiment"], before_assignment)
        for path, data in preserved.items():
            self.assertEqual(path.read_bytes(), data)
        amendment = af.json_artifact(directory, latest, "research-amendment")
        baseline = af.artifact_path(directory, latest, "research-amendment-source")
        self.assertEqual(amendment["reason"], self.reason)
        self.assertEqual(amendment["reverify_from"], "RESEARCH_PLAN")
        self.assertEqual(baseline.read_bytes(), af.artifact_path(directory, latest, "article").read_bytes())
        events = af._read_jsonl(directory / latest["event_log"])
        resets = [x["payload"] for x in events if x["type"] == "REPAIR" and "research_amendment_sha256" in x["payload"]]
        self.assertEqual({x["repair_state"] for x in resets}, af.MODEL_STATES)
        self.assertTrue(all("execution_count_baseline" in x for x in resets))
        self.assertEqual(len(list((directory / "publication").glob("*"))), 0)

    def test_new_context_is_hash_bound_in_all_model_packets_including_real_review_surfaces(self):
        directory, run, _, _ = self.prepared()
        self.reopen(run)
        directory, run = af.load_run(run["run_id"])
        for state in sorted(af.MODEL_STATES):
            for kind in af.state_definition(state, run).get("required_inputs", []):
                if not af.artifact(run, kind):
                    self.record_json(directory, run, kind, {})
        for state in sorted(af.MODEL_STATES):
            with self.subTest(state=state):
                af.transition(directory, run, state, "test", "Inspect renewed packet projection")
                candidate = {"provider": "active-host", "model": "active-capable-host", "kind": "agent-hosted", "eligible": True}
                route = {"stage": state, "candidates": [candidate], "chosen": candidate, "fallbacks": [], "reason": "fixture"}
                with mock.patch.object(af, "route_candidates", return_value=route), mock.patch.object(af, "pin_writing_route", side_effect=lambda run, state, route: route), af.run_lock(directory, run):
                    _, packet = af.task_packet(directory, run)
                inputs = {x["id"]: x for x in packet["inputs"]}
                self.assertEqual(af.load_json(Path(inputs["research-amendment"]["path"]))["reason"], self.reason)
                self.assertEqual(inputs["research-amendment"]["sha256"], af.artifact(run, "research-amendment")["sha256"])
                self.assertEqual(inputs["research-amendment-source"]["sha256"], af.artifact(run, "research-amendment-source")["sha256"])
                guidance = "\n".join(packet["constraints"])
                self.assertIn("rebuild the normal scope and evidence records", guidance)
                self.assertIn("Verify every new factual claim normally", guidance)
                self.assertIn("never transfer an old A/B/C label", guidance)

    def test_research_recovery_is_available_at_the_actual_failed_development_checkpoint(self):
        directory, run, _, _ = self.prepared()
        call(af.command_amend, run_id=run["run_id"], reopen_development=True, reason="Develop the approved addition before new locks.")
        directory, run = af.load_run(run["run_id"])
        self.assertEqual(run["state"], "DRAFT")
        prior = af.artifact_path(directory, run, "development-amendment").read_bytes()
        self.reopen(run)
        directory, run = af.load_run(run["run_id"])
        self.assertEqual(run["state"], "RESEARCH_PLAN")
        self.assertEqual(af.artifact_path(directory, run, "development-amendment").read_bytes(), prior)

    def test_repeated_request_is_idempotent_even_after_research_progress(self):
        directory, run, _, _ = self.prepared()
        self.reopen(run)
        directory, run = af.load_run(run["run_id"])
        af.transition(directory, run, "RESEARCH", "test", "Already began the approved research cycle")
        events = (directory / run["event_log"]).read_bytes()
        code, payload = self.reopen(run)
        self.assertEqual(code, af.EXIT_OK)
        self.assertTrue(payload["already_applied"])
        self.assertEqual(payload["state"], "RESEARCH")
        self.assertEqual((directory / run["event_log"]).read_bytes(), events)

    def test_interrupted_window_reset_blocks_dispatch_and_publication_then_resumes_once(self):
        directory, run, _, _ = self.prepared()
        original = af.append_event
        count = 0
        def interrupt(directory, run, kind, actor, payload):
            nonlocal count
            if kind == "REPAIR" and "research_amendment_sha256" in payload:
                count += 1
                if count == 4:
                    raise RuntimeError("isolated injected crash")
            return original(directory, run, kind, actor, payload)
        with mock.patch.object(af, "append_event", side_effect=interrupt), self.assertRaisesRegex(RuntimeError, "injected crash"):
            self.reopen(run)
        directory, run = af.load_run(run["run_id"])
        amendment = af.artifact(run, "research-amendment")
        with self.assertRaisesRegex(af.FlowError, "amendment is incomplete"):
            af.current_packet(directory, run)
        with self.assertRaisesRegex(af.FlowError, "amendment is incomplete"):
            call(af.command_publish_plan, run_id=run["run_id"])
        with self.assertRaisesRegex(af.FlowError, "amendment is incomplete"):
            call(af.command_amend, run_id=run["run_id"], reopen_research=True, reason="A replacement cannot conceal unfinished work.")
        self.reopen(run)
        directory, run = af.load_run(run["run_id"])
        self.assertEqual(run["state"], "RESEARCH_PLAN")
        self.assertEqual(af.artifact(run, "research-amendment"), amendment)
        events = af._read_jsonl(directory / run["event_log"])
        resets = [x for x in events if x["type"] == "REPAIR" and x["payload"].get("research_amendment_sha256") == amendment["sha256"]]
        self.assertEqual(len(resets), len(af.MODEL_STATES))
        af.require_complete_research_amendment(directory, run)

    def test_committed_transition_recovers_after_cache_save_crash_without_reopening_again(self):
        directory, run, _, _ = self.prepared()
        original = af.save_run
        def interrupt(directory, run):
            if run["state"] == "RESEARCH_PLAN":
                raise RuntimeError("isolated cache crash")
            return original(directory, run)
        with mock.patch.object(af, "save_run", side_effect=interrupt), self.assertRaisesRegex(RuntimeError, "cache crash"):
            self.reopen(run)
        directory, run = af.load_run(run["run_id"])
        self.assertEqual(run["state"], "RESEARCH_PLAN")
        before = (directory / run["event_log"]).read_bytes()
        _, payload = self.reopen(run)
        self.assertTrue(payload["already_applied"])
        self.assertEqual((directory / run["event_log"]).read_bytes(), before)

    def test_reason_mixed_edits_changed_source_and_published_runs_are_rejected(self):
        for case in ("reason", "mixed", "source", "published", "terminal"):
            with self.subTest(case=case):
                directory, run, _, _ = self.prepared()
                options = {"run_id": run["run_id"], "reopen_research": True, "reason": self.reason}
                if case == "reason": options["reason"] = " "
                elif case == "mixed": options["reopen_development"] = True
                elif case == "source":
                    path = af.artifact_path(directory, run, "article")
                    path.write_bytes(path.read_bytes() + b" ")
                else: af.transition(directory, run, "COMPLETE" if case == "published" else "TERMINAL", "test", "Existing stop")
                with self.assertRaises(af.FlowError): call(af.command_amend, **options)
                self.assertIsNone(af.artifact(af.load_run(run["run_id"])[1], "research-amendment"))

    def test_changed_amendment_or_baseline_cannot_dispatch_or_replay(self):
        for kind in ("research-amendment", "research-amendment-source"):
            with self.subTest(kind=kind):
                directory, run, _, _ = self.prepared()
                self.reopen(run)
                directory, run = af.load_run(run["run_id"])
                path = af.artifact_path(directory, run, kind)
                path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaises(af.FlowError): af.current_packet(directory, run)
                with self.assertRaises(af.FlowError): self.reopen(run)

    def test_public_parser_exposes_the_explicit_operation(self):
        args = af.build_parser().parse_args(["amend", "AF-test", "--reopen-research", "--reason", self.reason])
        self.assertTrue(args.reopen_research)
        self.assertFalse(args.reopen_development)

    def test_legacy_run_does_not_silently_acquire_an_editorial_research_restart(self):
        run_id = self.start("A retained legacy run has no approved editorial context extension.")
        directory, run = af.load_run(run_id)
        self.record_text(directory, run, "article", "A retained original article.")
        af.transition(directory, run, "EDITORIAL_QA", "test", "A frozen legacy workflow")
        with self.assertRaises(af.FlowError): self.reopen(run)
        self.assertIsNone(af.artifact(af.load_run(run_id)[1], "research-amendment"))
