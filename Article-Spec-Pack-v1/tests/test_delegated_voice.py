"""Delegated choices preserve frozen schemas without inventing human evidence."""
from unittest import mock

from test_article_flow_v3 import TemporaryRuntime, VoiceLearningTests, af, call, namespace
import editorial_learning


class DelegatedVoiceTests(TemporaryRuntime):
    voice_probe = VoiceLearningTests.voice_probe
    prepare_voice_choice = VoiceLearningTests.prepare_voice_choice

    def start(self, **overrides):
        code, result = call(af.command_start, seed="A delegated article voice test.",
                            seed_file=None, slug=None, **overrides)
        self.assertEqual(code, af.EXIT_OK)
        return result["run_id"]

    def choose(self, run_id, actor="human", authorization=None):
        return call(af.command_choose_voice, run_id=run_id, candidate_id="B",
                    decision_maker=actor, authorization=authorization)

    def test_human_selection_remains_human(self):
        run_id, directory, _, original, _ = self.prepare_voice_choice()
        original_bytes = original.read_bytes()
        self.choose(run_id)
        _, run = af.load_run(run_id)
        self.assertEqual(af.artifact(run, "voice-probe")["producer"]["actor"], "operator")
        self.assertEqual(af.json_artifact(directory, run, "gate-receipt:G-VOICE-PROBE")["evaluator"]["type"], "human")
        with mock.patch.object(af, "emit"):
            result = editorial_learning.apply_local_selection(af, directory, run)
        self.assertEqual(result["learning"]["decision_maker"], "human")
        self.assertEqual(original.read_bytes(), original_bytes)

    def test_delegated_selection_and_learning_are_assistant(self):
        run_id, directory, _, original, _ = self.prepare_voice_choice()
        original_bytes = original.read_bytes()
        self.choose(run_id, "assistant", "Choose the friendliest voice yourself.")
        _, run = af.load_run(run_id)
        item = af.artifact(run, "voice-probe")
        self.assertEqual(item["producer"]["decision_maker"], "assistant")
        self.assertEqual(item["producer"]["authorization"], "Choose the friendliest voice yourself.")
        self.assertEqual(af.validate_json_schema(directory / item["path"], "voice-probe.schema.json", run), [])
        self.assertEqual(af.json_artifact(directory, run, "gate-receipt:G-VOICE-PROBE")["evaluator"]["type"], "assistant")
        result = editorial_learning.apply_local_selection(af, directory, run)
        self.assertEqual(result["learning"]["decision_maker"], "assistant")
        proposal = af.load_json(__import__("pathlib").Path(result["proposal"]["path"]))
        self.assertEqual(proposal["evidence_kind"], "generated_interpretation")
        self.assertFalse(proposal["activated"])
        self.assertEqual(original.read_bytes(), original_bytes)

    def test_delegation_requires_authorization_without_writes(self):
        run_id, directory, _, _, _ = self.prepare_voice_choice()
        before = (directory / "events.jsonl").read_bytes()
        with self.assertRaises(af.FlowError):
            self.choose(run_id, "assistant")
        self.assertEqual((directory / "events.jsonl").read_bytes(), before)

    def test_crash_replay_cannot_relabel_delegation_as_human(self):
        run_id, directory, _, _, _ = self.prepare_voice_choice()
        with mock.patch.object(af, "transition", side_effect=RuntimeError("crash")):
            with self.assertRaises(RuntimeError):
                self.choose(run_id, "assistant", "Choose yourself.")
        with self.assertRaises(af.FlowError):
            self.choose(run_id)
        self.choose(run_id, "assistant", "Choose yourself.")
        _, run = af.load_run(run_id)
        self.assertEqual(run["state"], "VOICE_LEARNING")
        events = af._read_jsonl(directory / "events.jsonl")
        choices = [e for e in events if e["type"] == "VOICE_SELECTION_RECORDED"]
        self.assertEqual(len(choices), 1)
        self.assertEqual(choices[0]["actor"], "assistant")
