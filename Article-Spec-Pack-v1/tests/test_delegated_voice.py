"""Delegated choices preserve frozen schemas without inventing human evidence."""
from unittest import mock
import copy

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


class ConnectedQuestionTests(TemporaryRuntime):
    """Synthetic transport-boundary fixtures, never author answers or delivery proof."""

    voice_probe = VoiceLearningTests.voice_probe
    prepare_voice_choice = VoiceLearningTests.prepare_voice_choice

    def test_unknown_question_cannot_select_a_current_candidate(self):
        run_id, directory, _, _, _ = self.prepare_voice_choice()
        before = (directory / "events.jsonl").read_bytes()
        with self.assertRaises(af.FlowError):
            call(af.command_choose_voice, run_id=run_id, candidate_id="B",
                 question_id="Q-from-a-different-question")
        self.assertEqual((directory / "events.jsonl").read_bytes(), before)

    def pending(self, run_id):
        code, result = call(af.command_next, run_id=run_id)
        self.assertEqual(code, af.EXIT_WAITING)
        return result

    def test_pending_question_survives_reconnect_without_claiming_delivery(self):
        run_id, directory, _, _, _ = self.prepare_voice_choice()
        first = self.pending(run_id)
        events = (directory / "events.jsonl").read_bytes()
        second = self.pending(run_id)
        self.assertEqual(first["question_id"], second["question_id"])
        self.assertEqual(first["question_record"], second["question_record"])
        self.assertEqual(events, (directory / "events.jsonl").read_bytes())
        record = af.load_json(__import__("pathlib").Path(first["question_record"]))
        self.assertEqual(record["candidates"], first["candidates"])
        self.assertEqual(record["run_id"], run_id)
        self.assertEqual(first["delivery_status"], "unverified")
        self.assertNotIn("receipt", record)
        for command in first["selection_commands"].values():
            self.assertIn(first["question_id"], command)
        self.assertIn(first["question_id"], first["rejection_command"])

    def test_regenerated_labels_reject_the_old_answer_before_writes(self):
        run_id, directory, _, _, probe = self.prepare_voice_choice()
        old = self.pending(run_id)
        _, run = af.load_run(run_id)
        changed = copy.deepcopy(probe)
        changed["candidates"][1]["passage"] = "A new exact passage belongs to this revised choice."
        changed["candidates"][1]["passage_sha256"] = af.sha256_bytes(changed["candidates"][1]["passage"].encode())
        self.record_json(directory, run, "voice-probe", changed, "regenerated-probe.json")
        current = self.pending(run_id)
        self.assertNotEqual(old["question_id"], current["question_id"])
        before = (directory / "events.jsonl").read_bytes()
        with self.assertRaises(af.FlowError):
            call(af.command_choose_voice, run_id=run_id, candidate_id="B", question_id=old["question_id"])
        with self.assertRaises(af.FlowError):
            call(af.command_regenerate_voice, run_id=run_id, feedback="Fixture feedback", question_id=old["question_id"])
        self.assertEqual(before, (directory / "events.jsonl").read_bytes())
        call(af.command_choose_voice, run_id=run_id, candidate_id="B", question_id=current["question_id"])
        events = af._read_jsonl(directory / "events.jsonl")
        selected = [e for e in events if e["type"] == "VOICE_SELECTION_RECORDED"]
        self.assertEqual([e["payload"]["question_id"] for e in selected], [current["question_id"]])

    def test_a_question_from_another_run_is_rejected(self):
        run_id, _, _, _, _ = self.prepare_voice_choice()
        first = self.pending(run_id)
        other_id, directory, _, _, _ = self.prepare_voice_choice()
        self.pending(other_id)
        before = (directory / "events.jsonl").read_bytes()
        with self.assertRaises(af.FlowError):
            call(af.command_choose_voice, run_id=other_id, candidate_id="B", question_id=first["question_id"])
        self.assertEqual(before, (directory / "events.jsonl").read_bytes())

    def test_bound_answer_recovers_one_committed_selection_after_a_crash(self):
        run_id, directory, _, _, _ = self.prepare_voice_choice()
        pending = self.pending(run_id)
        with mock.patch.object(af, "transition", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError):
                call(af.command_choose_voice, run_id=run_id, candidate_id="B", question_id=pending["question_id"])
        call(af.command_choose_voice, run_id=run_id, candidate_id="B", question_id=pending["question_id"])
        _, run = af.load_run(run_id)
        self.assertEqual(run["state"], "VOICE_LEARNING")
        choices = [e for e in af._read_jsonl(directory / "events.jsonl") if e["type"] == "VOICE_SELECTION_RECORDED"]
        self.assertEqual(len(choices), 1)
        self.assertEqual(choices[0]["payload"]["question_id"], pending["question_id"])
        before = (directory / "events.jsonl").read_bytes()
        with self.assertRaises(af.FlowError):
            call(af.command_choose_voice, run_id=run_id, candidate_id="C", question_id=pending["question_id"])
        self.assertEqual(before, (directory / "events.jsonl").read_bytes())

    def test_rejected_set_cannot_receive_an_answer_while_repair_is_pending(self):
        run_id, directory, _, _, _ = self.prepare_voice_choice()
        pending = self.pending(run_id)
        call(af.command_regenerate_voice, run_id=run_id, feedback="Fixture rejection of this set", question_id=pending["question_id"])
        before = (directory / "events.jsonl").read_bytes()
        with self.assertRaises(af.FlowError):
            call(af.command_choose_voice, run_id=run_id, candidate_id="B", question_id=pending["question_id"])
        self.assertEqual(before, (directory / "events.jsonl").read_bytes())

    def test_a_stale_reader_projects_the_refreshed_candidates(self):
        run_id, directory, stale, _, probe = self.prepare_voice_choice()
        self.pending(run_id)
        _, fresh = af.load_run(run_id)
        changed = copy.deepcopy(probe)
        changed["candidates"][1]["passage"] = "A fresh candidate replaces the earlier paragraph."
        changed["candidates"][1]["passage_sha256"] = af.sha256_bytes(changed["candidates"][1]["passage"].encode())
        self.record_json(directory, fresh, "voice-probe", changed, "fresh-question-probe.json")
        result = af.next_state_payload(directory, stale)
        self.assertEqual(result["candidates"][1]["passage"], changed["candidates"][1]["passage"])
        self.assertEqual(af.load_json(__import__("pathlib").Path(result["question_record"]))["source"]["sha256"], af.artifact(fresh, "voice-probe")["sha256"])

    def prepare_clarification(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        self.record_json(directory, run, "intent-candidate", {"material_questions": ["What should the reader understand?"]}, "question-intent.json")
        af.transition(directory, run, "INTENT_REVIEW", "test", "fixture material question")
        run["status"] = "BLOCKED"
        af.save_run(directory, run)
        return run_id, directory

    def test_clarification_is_bound_and_preserves_actual_response_text(self):
        run_id, directory = self.prepare_clarification()
        pending = self.pending(run_id)
        self.assertIn(pending["question_id"], pending["response_command"])
        response = self.root / "fixture-answer.txt"
        exact = "  Fixture answer in the author's actual wording.\n"
        response.write_text(exact, encoding="utf-8")
        before = (directory / "events.jsonl").read_bytes()
        with self.assertRaises(af.FlowError):
            call(af.command_clarify, run_id=run_id, response_file=str(response), question_id="Q-stale")
        self.assertEqual(before, (directory / "events.jsonl").read_bytes())
        call(af.command_clarify, run_id=run_id, response_file=str(response), question_id=pending["question_id"])
        _, run = af.load_run(run_id)
        answer = af.json_artifact(directory, run, "author-context")["responses"][-1]
        self.assertEqual(answer["exact_author_response"], exact)
        self.assertEqual(answer["question_id"], pending["question_id"])
        before = (directory / "events.jsonl").read_bytes()
        with self.assertRaises(af.FlowError):
            call(af.command_clarify, run_id=run_id, response_file=str(response), question_id=pending["question_id"])
        self.assertEqual(before, (directory / "events.jsonl").read_bytes())
