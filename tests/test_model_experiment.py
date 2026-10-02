"""Behavioral checks of the experiment's prompt, coverage, and preservation guards."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("model_experiment", ROOT / "scripts/model_experiment.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
import model_experiment_views as views


class ExperimentTests(unittest.TestCase):
    def test_model_discovered_after_article_is_not_generated_before_introduction(self):
        registry=m.empty_registry()
        old=self.row("old-model")
        new=self.row("new-model")
        m.reconcile(registry,[old])
        self.record(registry)
        m.atomic_json(self.pack/"registry.json",registry)
        verify=m.verify_registry
        with patch.object(m,"PACK",self.pack), patch.object(m,"discover",return_value=([old,new],{})), \
             patch.object(m,"verify_registry",side_effect=lambda value: verify(value,self.pack)), \
             patch.object(m,"run_once") as launch, patch.object(m,"write_preview"), redirect_stdout(io.StringIO()):
            m.main(["update","--state-dir",str(self.state)],allowed_models={m.model_key("codex","old-model")})
        launch.assert_not_called()
        report=m.load(self.state/"last-check.json")
        self.assertEqual(report["models_waiting_for_article"],[{"provider":"codex","model":"new-model"}])

    def test_failed_settings_profile_stays_visible_without_being_rescheduled(self):
        row = {"provider": "codex", "model": "m", "effort_levels": ["low", "medium"]}
        low = m.variants(row)[1]
        registry = {"models": [row], "records": [
            {"provider": "codex", "model": "m", "status": "response captured"},
            {"provider": "codex", "model": "m", "variant": low, "status": "generation failed"}]}
        self.assertEqual(m.missing_trials(registry, [row]), [])
        self.assertEqual(len(m.unsuccessful_trials(registry, [row])), 1)
        self.assertEqual(m.response_coverage(registry), [])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pack = Path(self.tmp.name) / "pack"
        self.state = Path(self.tmp.name) / "state"
        self.pack.mkdir()
        self.state.mkdir()
        for name in ("prompt.txt", "experiment.json", "preview-template.html"):
            (self.pack / name).write_bytes((m.PACK / name).read_bytes())

    def tearDown(self):
        self.tmp.cleanup()

    def row(self, model="new-model", provider="codex"):
        return {"provider": provider, "model": model, "aliases": [model],
                "display_name": model, "release_date": None, "release_date_source": None}

    def record(self, registry, model="old-model"):
        key = m.model_key("codex", model)
        relative = f"records/{key}/response.txt"
        path = self.pack / relative
        path.parent.mkdir(parents=True)
        path.write_bytes(b"Original response <script>alert('unsafe')</script>")
        record = {"key": key, "provider": "codex", "model": model, "status": "recorded",
                  "prompt_sha256": m.PROMPT_SHA256, "artifacts": {relative: m.sha(path.read_bytes())}}
        registry["records"].append(record)
        return path, record

    def test_prompt_bytes_verified_and_whitespace_change_refused(self):
        self.assertEqual(m.sha(m.freeze_prompt(self.pack)), m.PROMPT_SHA256)
        path = self.pack / "prompt.txt"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(m.ExperimentError, "Frozen prompt changed"):
            m.freeze_prompt(self.pack)

    def test_changing_manifest_does_not_reauthorize_changed_prompt(self):
        path = self.pack / "prompt.txt"
        path.write_bytes(b"different prompt")
        config = m.load(self.pack / "experiment.json")
        config["prompt_sha256"] = m.sha(path.read_bytes())
        m.atomic_json(self.pack / "experiment.json", config)
        with self.assertRaisesRegex(m.ExperimentError, "expected prompt hash changed"):
            m.freeze_prompt(self.pack)

    def test_claude_aliases_and_context_options_are_deduplicated(self):
        rows = m.normalize_claude({"models": [
            {"value": "default", "resolvedModel": "claude-example[1m]"},
            {"value": "opus", "resolvedModel": "claude-example"}]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["model"], "claude-example")
        self.assertEqual(rows[0]["aliases"], ["default", "opus"])

    def test_unresolved_claude_alias_blocks_coverage(self):
        with self.assertRaisesRegex(m.ExperimentError, "resolved model"):
            m.normalize_claude({"models": [{"value": "default"}]})

    def test_hidden_codex_services_excluded(self):
        rows = m.normalize_codex({"models": [
            {"slug": "text-model", "visibility": "list"},
            {"slug": "review-service", "visibility": "hide"},
            {"slug": "image-only", "input_modalities": ["image"]}]})
        self.assertEqual([row["model"] for row in rows], ["text-model"])

    def test_repeated_discovery_preserves_history_and_finds_only_missing_results(self):
        registry = m.empty_registry()
        path, record = self.record(registry)
        catalog = [self.row("old-model"), self.row("new-model")]
        self.assertEqual([row["model"] for row in m.reconcile(registry, catalog)], ["new-model"])
        previous = json.loads(json.dumps(registry))
        m.reconcile(registry, catalog)
        self.assertEqual(registry, previous)
        self.assertEqual(path.read_bytes(), b"Original response <script>alert('unsafe')</script>")
        m.verify_registry(registry, self.pack)

    def test_older_model_temporarily_missing_from_catalog_remains_in_registry(self):
        registry = m.empty_registry()
        m.reconcile(registry, [self.row("old-model")])
        m.reconcile(registry, [self.row("new-model")])
        self.assertEqual({row["model"] for row in registry["models"]}, {"old-model", "new-model"})

    def test_changed_saved_response_is_refused(self):
        registry = m.empty_registry()
        path, record = self.record(registry)
        path.write_text("Replacement response")
        with self.assertRaisesRegex(m.ExperimentError, "Existing evidence changed"):
            m.verify_registry(registry, self.pack)

    def test_removed_or_replaced_record_is_refused(self):
        registry = m.empty_registry()
        self.record(registry)
        m.anchor_history(registry, self.state)
        changed = json.loads(json.dumps(registry))
        changed["records"][0]["status"] = "preferred replacement"
        with self.assertRaisesRegex(m.ExperimentError, "removed or replaced"):
            m.verify_history(changed, self.state)
        registry["records"] = []
        with self.assertRaisesRegex(m.ExperimentError, "removed or replaced"):
            m.verify_history(registry, self.state)

    def test_concurrent_update_is_refused(self):
        with m.update_lock(self.state):
            with self.assertRaisesRegex(m.ExperimentError, "Another update"):
                with m.update_lock(self.state):
                    self.fail("A second updater entered the lock")

    def test_record_path_escape_is_refused(self):
        with self.assertRaisesRegex(m.ExperimentError, "escapes"):
            m.safe_path(self.pack, "../../private.txt")

    def test_generated_preview_does_not_execute_output_or_overwrite_manual_edits(self):
        registry = m.empty_registry()
        path, _ = self.record(registry)
        m.reconcile(registry, [self.row("old-model")])
        target = self.state / "preview.html"
        m.write_preview(registry, self.state, target, self.pack)
        text = target.read_text()
        self.assertIn("/runs/", text)
        escaped = views.response_html(path.read_text(encoding="utf-8"))
        self.assertIn("&lt;script&gt;", escaped)
        self.assertNotIn("<script>alert", escaped)
        m.write_preview(registry, self.state, target, self.pack)
        target.write_text("human changes")
        with self.assertRaisesRegex(m.ExperimentError, "unowned changes"):
            m.write_preview(registry, self.state, target, self.pack)
        self.assertEqual(target.read_text(), "human changes")

    def test_profiles_cover_native_efforts_and_verbosity_without_changing_prompt(self):
        row = dict(self.row(), effort_levels=["low", "medium", "high", "xhigh"], supports_verbosity=True)
        profiles = m.variants(row)
        self.assertEqual({v["effort"] for v in profiles}, {"low", "medium", "high", "xhigh"})
        self.assertEqual({v["verbosity"] for v in profiles}, {"default", "low", "medium", "high"})
        self.assertEqual(len(m.variants(row, "factorial")), 16)
        self.assertEqual(m.sha(m.freeze_prompt(self.pack)), m.PROMPT_SHA256)

    def test_settings_identity_preserves_baseline_and_separates_combinations(self):
        baseline = {"id":"baseline","effort":"medium","verbosity":"default"}
        low = {"id":"effort-low","effort":"low","verbosity":"default"}
        high = {"id":"verbosity-high","effort":"medium","verbosity":"high"}
        self.assertEqual(m.trial_key("codex", "example", baseline), m.model_key("codex","example"))
        self.assertNotEqual(m.trial_key("codex","example",low), m.trial_key("codex","example",high))
        registry = m.empty_registry()
        self.record(registry, "example")
        row = dict(self.row("example"), effort_levels=["low","medium"], supports_verbosity=True)
        self.assertNotIn("baseline", [r["_variant"]["id"] for r in m.missing_trials(registry,[row])])

    def test_unsupported_controls_are_rejected_before_launch(self):
        row = dict(self.row("claude-example","claude"), effort_levels=["low","medium"])
        with patch.object(m,"cli",return_value="claude"), self.assertRaisesRegex(m.ExperimentError,"not advertised"):
            m.candidate_args(dict(row,_variant={"id":"effort-max","effort":"max","verbosity":"default"}), self.state)
        with patch.object(m,"cli",return_value="claude"), self.assertRaisesRegex(m.ExperimentError,"verbosity"):
            m.candidate_args(dict(row,_variant={"id":"verbosity-high","effort":"medium","verbosity":"high"}), self.state)

    def test_claude_effort_and_codex_verbosity_are_real_client_arguments(self):
        claude = dict(self.row("claude-example","claude"),effort_levels=["low","high"],
                      _variant={"id":"effort-high","effort":"high","verbosity":"default"})
        with patch.object(m,"cli",return_value="client"):
            args, settings = m.candidate_args(claude,self.state)
            self.assertEqual(args[args.index("--effort")+1],"high")
            codex = dict(self.row("example"),effort_levels=["medium"],supports_verbosity=True,
                         _native={"slug":"example"},_variant={"id":"verbosity-high","effort":"medium","verbosity":"high"})
            args, settings = m.candidate_args(codex,self.state)
            self.assertIn('model_verbosity="high"',args)
            self.assertIn('model_reasoning_effort="medium"',args)

    def test_response_prose_and_code_are_escaped_and_code_is_collapsible(self):
        text = "# A story\n\nReadable **prose** <script>alert(1)</script>\n\n" + chr(96)*3 + "json\n{}\n" + chr(96)*3
        rendered = views.response_html(text)
        self.assertIn("<p>Readable <strong>prose</strong>",rendered)
        self.assertIn("<summary>Receipt</summary>",rendered)
        self.assertIn("&lt;script&gt;",rendered)
        self.assertNotIn("<script>",rendered)

    def test_chronological_order_and_explicit_date_fallback(self):
        older = dict(self.row("z-older"), release_date="2025-01-01", first_seen="2026-10-02T00:00:00Z")
        newer = dict(self.row("a-newer"), release_date="2026-01-01", first_seen="2026-10-02T00:00:00Z")
        unknown = dict(self.row("unknown"), first_seen="2026-10-02T00:00:00Z")
        rows = sorted([unknown, newer, older], key=m.chronological)
        self.assertEqual([row["model"] for row in rows], ["z-older", "a-newer", "unknown"])
        preview = m.render(dict(m.empty_registry(), models=rows), self.pack)
        self.assertIn("First seen 2026-10-02; release date unavailable", preview)
        self.assertLess(preview.index("z-older"), preview.index("a-newer"))

    def test_independent_answer_key(self):
        initial, revised = m.answer_key(80), m.answer_key(66)
        self.assertEqual(initial["orders"], ["A", "C", "F", "G"])
        self.assertEqual((initial["repair_contribution"], initial["shortfall"]), (179, 41))
        self.assertEqual(revised["orders"], ["A", "B", "C", "E"])
        self.assertEqual((revised["repair_contribution"], revised["shortfall"]), (144, 76))
        receipt = {"initial": initial, "revised": revised, "donation_confirmed": False}
        self.assertTrue(m.validate_response(json.dumps(receipt))["receipt_passed"])
        receipt["revised"]["repair_contribution"] = 244
        self.assertEqual(m.validate_response(json.dumps(receipt))["receipt_checks"]["revised.repair_contribution"], "fail")

    def test_invalid_candidate_receipt_does_not_crash_checker(self):
        receipt = {"initial": {"orders": ["A", 3]}, "revised": {}, "donation_confirmed": True}
        self.assertFalse(m.validate_response(json.dumps(receipt))["receipt_passed"])

    def test_usage_comes_from_provider_events_and_missing_is_not_zero(self):
        events = [{"type": "item.completed", "item": {"type": "agent_message", "text": "original"}},
                  {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 75, "output_tokens": 20}}]
        parsed = m.parse_events("codex", "\n".join(json.dumps(e) for e in events).encode())
        self.assertEqual(parsed["response"], "original")
        self.assertEqual(parsed["usage"]["cached_input_tokens"], 75)
        self.assertIsNone(m.parse_events("codex", b"")["usage"])

    def test_tool_use_is_identified_as_protocol_violation(self):
        event = {"type": "item.completed", "item": {"type": "command_execution"}}
        self.assertTrue(m.parse_events("codex", json.dumps(event).encode())["tool_used"])
        event = {"type": "system", "subtype": "init", "tools": ["Bash"]}
        self.assertTrue(m.parse_events("claude", json.dumps(event).encode())["tool_used"])

    def test_append_and_repeat_do_not_replace_original_response(self):
        registry = m.empty_registry()
        key = m.model_key("codex", "one-model")
        metadata = {"key": key, "provider": "codex", "model": "one-model", "status": "response captured",
                    "prompt_sha256": m.PROMPT_SHA256, "started_at": "2026-10-02T00:00:00Z"}
        m.append_result(registry, metadata, b"first response", self.pack)
        m.append_result(registry, metadata, b"replacement", self.pack)
        self.assertEqual(len(registry["records"]), 1)
        self.assertEqual((self.pack / f"records/{key}/response.txt").read_bytes(), b"first response")
        with self.assertRaisesRegex(m.ExperimentError, "overwrite original"):
            m.exclusive_write(self.pack / f"records/{key}/response.txt", b"replacement")

    def test_ambiguous_interruption_is_not_resent(self):
        row = self.row("interrupted")
        folder = self.state / "attempts" / m.model_key("codex", "interrupted")
        folder.mkdir(parents=True)
        (folder / "started.json").write_text("{}")
        with patch.object(m, "process") as launch:
            with self.assertRaisesRegex(m.ExperimentError, "no automatic resend"):
                m.run_once(row, self.state)
            launch.assert_not_called()

    def test_captured_response_recovers_without_generation(self):
        row = self.row("captured")
        folder = self.state / "attempts" / m.model_key("codex", "captured")
        folder.mkdir(parents=True)
        (folder / "response.txt").write_bytes(b"captured response")
        m.atomic_json(folder / "captured.json", {"private_hashes": {"response.txt": m.sha(b"captured response")}})
        with patch.object(m, "process") as launch:
            metadata, response = m.run_once(row, self.state)
            self.assertEqual(response, b"captured response")
            launch.assert_not_called()

    def test_authentication_failure_waits_for_restored_access(self):
        registry = m.empty_registry()
        row = self.row("claude-example", "claude")
        key = m.model_key("claude", "claude-example")
        metadata = {"key": key, "provider": "claude", "model": "claude-example",
                    "status": "generation failed", "prompt_sha256": m.PROMPT_SHA256,
                    "started_at": "2026-10-02T00:00:00Z", "attempt": 1}
        m.append_result(registry, metadata, b"Failed to authenticate: OAuth session expired", self.pack)
        self.assertEqual(m.access_recovery_candidates(registry, [row], False, self.pack), [])
        candidates = m.access_recovery_candidates(registry, [row], True, self.pack)
        self.assertEqual(candidates, [(row, 2)])
        old = (self.pack / f"records/{key}/response.txt").read_bytes()
        recovered = dict(metadata, key=f"{key}-attempt-2", attempt=2, status="response captured")
        m.append_result(registry, recovered, b"First actual model response", self.pack)
        m.verify_registry(registry, self.pack)
        self.assertEqual((self.pack / f"records/{key}/response.txt").read_bytes(), old)
        self.assertEqual(m.access_recovery_candidates(registry, [row], True, self.pack), [])

    def test_auth_recovery_does_not_retry_an_ordinary_generation_failure(self):
        registry = m.empty_registry()
        row = self.row("claude-example", "claude")
        key = m.model_key("claude", "claude-example")
        metadata = {"key": key, "provider": "claude", "model": "claude-example",
                    "status": "generation failed", "prompt_sha256": m.PROMPT_SHA256,
                    "started_at": "2026-10-02T00:00:00Z"}
        m.append_result(registry, metadata, b"An observed failed generation", self.pack)
        self.assertEqual(m.access_recovery_candidates(registry, [row], True, self.pack), [])

    def test_missing_response_is_distinct_from_missing_model_record(self):
        registry = m.empty_registry()
        path, record = self.record(registry)
        record["status"] = "generation failed"
        m.reconcile(registry, [self.row("old-model")])
        self.assertEqual(m.reconcile(registry, [self.row("old-model")]), [])
        self.assertEqual([row["model"] for row in m.response_coverage(registry)], ["old-model"])
        record["status"] = "response captured"
        self.assertEqual(m.response_coverage(registry), [])


if __name__ == "__main__":
    unittest.main()
