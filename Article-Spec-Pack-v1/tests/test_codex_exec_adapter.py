from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SPEC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPEC_ROOT / "scripts"))
import codex_exec_adapter as adapter  # noqa: E402


class CodexExecAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.executable = self.root / "codex"
        self.executable.write_text("fixture", encoding="utf-8")

    def packet(self, *, stage: str = "RESEARCH_PLAN", input_hash: str | None = None) -> Path:
        source = self.root / "source.md"
        source.write_text("Verified source text.\n", encoding="utf-8")
        digest = input_hash or hashlib.sha256(source.read_bytes()).hexdigest()
        packet = {
            "run_id": "AF-test",
            "stage": stage,
            "inputs": [{"id": "seed", "path": str(source), "sha256": digest}],
            "expected_outputs": [{
                "path": str(self.root / "controller-output.json"),
                "format": "json",
                "schema_name": "fixture.schema.json",
                "schema": {
                    "type": "object",
                    "required": ["ok"],
                    "properties": {"ok": {"type": "boolean"}},
                    "additionalProperties": False,
                },
            }],
        }
        path = self.root / "packet.json"
        path.write_text(json.dumps(packet), encoding="utf-8")
        return path

    def test_command_is_fixed_isolated_and_keeps_prompt_out_of_argv(self):
        command = adapter.build_codex_command(
            executable=str(self.executable),
            model="gpt-5.6-terra",
            working_directory=self.root,
            output_path=self.root / "last-message.json",
            output_schema_path=self.root / "schema.json",
            reasoning_effort="high",
        )
        self.assertEqual(command[:2], [str(self.executable), "exec"])
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertIn("--ephemeral", command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertEqual(command[command.index("--model") + 1], "gpt-5.6-terra")
        self.assertEqual(command[-1], "-")
        self.assertNotIn("secret prompt", command)
        disabled = {command[index + 1] for index, item in enumerate(command[:-1]) if item == "--disable"}
        self.assertEqual(disabled, set(adapter.DISABLED_HOST_TOOL_FEATURES))
        self.assertEqual(len(disabled), 21)
        self.assertTrue({"shell_tool", "unified_exec", "computer_use", "apps", "plugins", "multi_agent"} <= disabled)
        config_values = [command[index + 1] for index, item in enumerate(command[:-1]) if item == "--config"]
        self.assertIn('web_search="disabled"', config_values)

    def test_task_packet_exec_returns_observed_receipt_and_writes_output(self):
        packet_path = self.packet()
        output_path = self.root / "result.json"
        calls: list[list[str]] = []

        def completed(command, **kwargs):
            calls.append(command)
            if command[-1] == "--version":
                return subprocess.CompletedProcess(command, 0, "codex-cli 0.144.4\n", "")
            last_message = Path(command[command.index("--output-last-message") + 1])
            last_message.write_text(json.dumps({"artifact_json": json.dumps({"ok": True})}) + "\n", encoding="utf-8")
            stdout = "\n".join([
                json.dumps({"type": "thread.started", "thread_id": "thread-1", "model": "gpt-5.6-terra"}),
                json.dumps({"type": "turn.started", "turn_id": "turn-1"}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 12, "output_tokens": 3}}),
            ])
            self.assertEqual(kwargs["input"].count("Verified source text."), 1)
            self.assertIn("JSON TRANSPORT ENVELOPE", kwargs["input"])
            self.assertIn('"additionalProperties": false', kwargs["input"])
            self.assertEqual(kwargs["cwd"], last_message.parent)
            return subprocess.CompletedProcess(command, 0, stdout, "")

        with mock.patch.object(adapter.subprocess, "run", side_effect=completed):
            result = adapter.execute_task_packet(
                packet_path,
                output_path,
                model="gpt-5.6-terra",
                timeout_seconds=30,
                executable=self.executable,
            )

        self.assertEqual(json.loads(result.output_text), {"ok": True})
        self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), {"ok": True})
        self.assertEqual(result.receipt["requested_model"], "gpt-5.6-terra")
        self.assertEqual(result.receipt["observed_model"], "gpt-5.6-terra")
        self.assertEqual(result.receipt["model_evidence"], "cli-event")
        self.assertEqual(result.receipt["cli_version"], "0.144.4")
        self.assertEqual(result.receipt["thread_id"], "thread-1")
        self.assertEqual(result.receipt["turn_id"], "turn-1")
        self.assertEqual(result.receipt["usage"]["output_tokens"], 3)
        self.assertEqual(result.receipt["transport"]["host_tool_access"], "disabled")
        self.assertEqual(result.receipt["transport"]["host_file_access"], "none_via_model_tools")
        self.assertEqual(result.receipt["transport"]["web_search_mode"], "live")
        self.assertEqual(
            set(result.receipt["transport"]["disabled_host_tool_features"]),
            set(adapter.DISABLED_HOST_TOOL_FEATURES),
        )
        self.assertEqual(len(calls), 2)
        self.assertNotIn("Verified source text.", " ".join(calls[1]))
        config_values = [
            calls[1][index + 1]
            for index, item in enumerate(calls[1][:-1])
            if item == "--config"
        ]
        self.assertIn('web_search="live"', config_values)

    def test_task_packet_prompt_includes_schema_and_article_recipe_once(self):
        recipe = self.root / "article-recipe.json"
        recipe.write_text('{"recipe_marker":"ONLY_ONCE_RECIPE"}\n', encoding="utf-8")
        schema = {
            "type": "object",
            "required": ["ONLY_ONCE_SCHEMA"],
            "properties": {"ONLY_ONCE_SCHEMA": {"type": "boolean"}},
            "additionalProperties": False,
        }
        packet = {
            "run_id": "AF-test",
            "stage": "DRAFT",
            "article_recipe": {"recipe_marker": "ONLY_ONCE_RECIPE"},
            "inputs": [{
                "id": "article-recipe",
                "path": str(recipe),
                "sha256": hashlib.sha256(recipe.read_bytes()).hexdigest(),
            }],
            "expected_outputs": [{
                "path": str(self.root / "controller-output.json"),
                "format": "json",
                "schema_name": "fixture.schema.json",
                "schema": schema,
            }],
        }
        packet_path = self.root / "packet-with-recipe.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")

        _, compact_prompt, expected_format, output_schema = adapter._load_task_packet(packet_path)
        transport_prompt = adapter._enveloped_json_prompt(compact_prompt, output_schema, "disabled")

        self.assertEqual(expected_format, "json")
        self.assertEqual(compact_prompt.count("ONLY_ONCE_RECIPE"), 1)
        self.assertNotIn("ONLY_ONCE_SCHEMA", compact_prompt)
        self.assertEqual(transport_prompt.count("ONLY_ONCE_RECIPE"), 1)
        self.assertEqual(transport_prompt.count("ONLY_ONCE_SCHEMA"), 2)

    def test_task_packet_stage_scopes_live_web_search_to_research_and_verification(self):
        self.assertEqual(
            adapter.LIVE_WEB_SEARCH_STAGES,
            {
                "RESEARCH_PLAN",
                "RESEARCH",
                "CLAIM_VERIFICATION",
                "POST_EDIT_CLAIM_VERIFICATION",
            },
        )
        expected_modes = {
            "RESEARCH_PLAN": "live",
            "RESEARCH": "live",
            "CLAIM_VERIFICATION": "live",
            "POST_EDIT_CLAIM_VERIFICATION": "live",
            "DRAFT": "disabled",
            "STYLE_CHECK": "disabled",
            "UNRECOGNIZED_FUTURE_STAGE": "disabled",
        }

        for stage, expected_mode in expected_modes.items():
            with self.subTest(stage=stage):
                commands: list[list[str]] = []

                def completed(command, **_kwargs):
                    commands.append(command)
                    if command[-1] == "--version":
                        return subprocess.CompletedProcess(command, 0, "codex-cli 0.144.4\n", "")
                    last_message = Path(command[command.index("--output-last-message") + 1])
                    last_message.write_text(
                        json.dumps({"artifact_json": json.dumps({"ok": True})}) + "\n",
                        encoding="utf-8",
                    )
                    return subprocess.CompletedProcess(command, 0, '{"type":"turn.completed"}\n', "")

                with mock.patch.object(adapter.subprocess, "run", side_effect=completed):
                    result = adapter.execute_task_packet(
                        self.packet(stage=stage),
                        None,
                        model="gpt-5.6-luna",
                        timeout_seconds=30,
                        executable=self.executable,
                    )

                invocation = commands[1]
                config_values = [
                    invocation[index + 1]
                    for index, item in enumerate(invocation[:-1])
                    if item == "--config"
                ]
                self.assertEqual(
                    [value for value in config_values if value.startswith("web_search=")],
                    [f'web_search="{expected_mode}"'],
                )
                disabled = {
                    invocation[index + 1]
                    for index, item in enumerate(invocation[:-1])
                    if item == "--disable"
                }
                self.assertEqual(disabled, set(adapter.DISABLED_HOST_TOOL_FEATURES))
                self.assertEqual(result.receipt["transport"]["web_search_mode"], expected_mode)

    def test_direct_execute_defaults_to_disabled_web_search(self):
        commands: list[list[str]] = []

        def completed(command, **_kwargs):
            commands.append(command)
            if command[-1] == "--version":
                return subprocess.CompletedProcess(command, 0, "codex-cli 0.144.4\n", "")
            last_message = Path(command[command.index("--output-last-message") + 1])
            last_message.write_text("finished\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, '{"type":"turn.completed"}\n', "")

        with mock.patch.object(adapter.subprocess, "run", side_effect=completed):
            result = adapter.execute_codex(
                prompt="Return plain text.",
                model="gpt-5.5",
                expected_format="markdown",
                output_schema=None,
                timeout_seconds=30,
                executable=self.executable,
            )

        invocation = commands[1]
        config_values = [
            invocation[index + 1]
            for index, item in enumerate(invocation[:-1])
            if item == "--config"
        ]
        self.assertIn('web_search="disabled"', config_values)
        self.assertEqual(result.receipt["transport"]["web_search_mode"], "disabled")

    def test_hash_mismatch_stops_before_codex_execution(self):
        packet_path = self.packet(input_hash="0" * 64)
        with mock.patch.object(adapter.subprocess, "run") as executed:
            with self.assertRaisesRegex(adapter.CodexExecError, "input changed"):
                adapter.execute_task_packet(
                    packet_path,
                    self.root / "result.json",
                    model="gpt-5.5",
                    timeout_seconds=30,
                    executable=self.executable,
                )
        executed.assert_not_called()

    def test_unsafe_model_id_is_rejected_before_execution(self):
        with mock.patch.object(adapter.subprocess, "run") as executed:
            with self.assertRaisesRegex(adapter.CodexExecError, "model ID"):
                adapter.execute_codex(
                    prompt="Return JSON.",
                    model="--dangerous option",
                    expected_format="json",
                    output_schema={"type": "object"},
                    timeout_seconds=30,
                    executable=self.executable,
                )
        executed.assert_not_called()

    def test_normative_schema_uses_a_strict_outer_envelope(self):
        normative = {
            "type": "object",
            "required": ["dimensions"],
            "properties": {
                "dimensions": {
                    "type": "object",
                    "required": ["voice_fit"],
                    "additionalProperties": {"type": "object"},
                },
            },
        }
        transported = adapter.codex_transport_schema(normative)
        self.assertEqual(transported["required"], ["artifact_json"])
        self.assertFalse(transported["additionalProperties"])
        self.assertEqual(transported["properties"], {"artifact_json": {"type": "string"}})
        self.assertNotIn("dimensions", json.dumps(transported))

    def test_envelope_preserves_open_dynamic_objects_and_optional_nulls(self):
        artifact = {
            "dimensions": {
                "voice_fit": {"score": 4, "evidence": {"passages": ["A", "B"]}},
                "new_dimension": {"score": 3},
            },
            "outline_candidates": [
                {"shape": "field-note", "sections": ["result", "method"]},
                {"shape": "teardown", "sections": ["failure", "repair"]},
            ],
            "optional_note": None,
        }
        raw = json.dumps({"artifact_json": json.dumps(artifact)})
        normalized = adapter._normalize_output(
            raw,
            "json",
            {"type": "object", "additionalProperties": True},
        )
        self.assertEqual(json.loads(normalized), artifact)

    def test_json_output_without_the_exact_envelope_fails_closed(self):
        with self.assertRaisesRegex(adapter.CodexExecError, "transport envelope"):
            adapter._normalize_output('{"ok":true}', "json", {"type": "object"})

    def test_nonzero_exit_is_bounded_and_does_not_claim_success(self):
        def completed(command, **_kwargs):
            if command[-1] == "--version":
                return subprocess.CompletedProcess(command, 0, "codex-cli 0.144.4\n", "")
            return subprocess.CompletedProcess(command, 7, '{"type":"thread.started","thread_id":"thread-2"}\n', "provider unavailable")

        with mock.patch.object(adapter.subprocess, "run", side_effect=completed):
            with self.assertRaisesRegex(adapter.CodexExecError, "execution failed") as raised:
                adapter.execute_codex(
                    prompt="Return JSON.",
                    model="gpt-5.5",
                    expected_format="json",
                    output_schema={"type": "object"},
                    timeout_seconds=30,
                    executable=self.executable,
                )
        self.assertEqual(raised.exception.details["exit_code"], 7)
        self.assertEqual(raised.exception.details["thread_id"], "thread-2")
        self.assertEqual(raised.exception.details["stderr"], "provider unavailable")

    def test_reported_model_mismatch_fails_closed(self):
        def completed(command, **_kwargs):
            if command[-1] == "--version":
                return subprocess.CompletedProcess(command, 0, "codex-cli 0.144.4\n", "")
            last_message = Path(command[command.index("--output-last-message") + 1])
            last_message.write_text(json.dumps({"artifact_json": json.dumps({"ok": True})}) + "\n", encoding="utf-8")
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps({"type": "thread.started", "thread_id": "thread-3", "model": "gpt-5.6-luna"}),
                "",
            )

        with mock.patch.object(adapter.subprocess, "run", side_effect=completed):
            with self.assertRaisesRegex(adapter.CodexExecError, "different model"):
                adapter.execute_codex(
                    prompt="Return JSON.",
                    model="gpt-5.5",
                    expected_format="json",
                    output_schema={"type": "object"},
                    timeout_seconds=30,
                    executable=self.executable,
                )


if __name__ == "__main__":
    unittest.main()
