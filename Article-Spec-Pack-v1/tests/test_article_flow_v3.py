from __future__ import annotations

import argparse
import contextlib
import html
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock


SPEC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPEC_ROOT / "scripts"))
import article_flow as af  # noqa: E402


MODEL_POOL = [
    "gpt-5.5",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
]


def namespace(**values):
    defaults = {
        "json": True,
        "feedback": None,
        "auto": False,
        "draft_model": None,
        "hold_before_publish": False,
        "route": None,
        "canary": False,
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
        self.root = Path(self.temp.name)
        self.runtime = self.root / "runtime"
        self.environment = mock.patch.dict(
            os.environ,
            {
                "ARTICLE_FLOW_HOME": str(self.runtime),
                "ARTICLE_FLOW_RUNS_ROOT": str(self.runtime / "runs"),
                "ARTICLE_FLOW_TEST_NO_PUBLISH": "1",
            },
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.integrity = mock.patch.object(
            af,
            "check_manifest",
            return_value={"ok": True, "source": "test", "failures": []},
        )
        self.integrity.start()
        self.addCleanup(self.integrity.stop)

    def start(self, seed="A test of the Article Flow 3 voice loop.", **overrides):
        values = {
            "seed": seed,
            "seed_file": None,
            "slug": None,
            "auto": False,
            "draft_model": None,
            "hold_before_publish": False,
        }
        values.update(overrides)
        code, payload = call(af.command_start, **values)
        self.assertEqual(code, af.EXIT_OK, payload)
        return payload["run_id"]

    def record_json(self, directory, run, artifact_type, value, filename=None):
        path = directory / "artifacts" / (filename or f"{artifact_type}.json")
        af.write_json(path, value)
        af.record_artifact(directory, run, path, artifact_type, {"actor": "test"})
        return path

    def record_text(self, directory, run, artifact_type, value, filename=None):
        path = directory / "artifacts" / (filename or f"{artifact_type}.md")
        af.atomic_write(path, value.encode("utf-8"))
        af.record_artifact(directory, run, path, artifact_type, {"actor": "test"})
        return path


class WorkflowV3ContractTests(unittest.TestCase):
    def test_v3_public_commands_and_run_overrides_parse(self):
        parser = af.build_parser()
        capture = parser.parse_args([
            "capture",
            "A compact article idea.",
            "--auto",
            "--draft-model",
            "gpt-5.6-terra",
            "--hold-before-publish",
        ])
        self.assertTrue(capture.auto)
        self.assertEqual(capture.draft_model, "gpt-5.6-terra")
        self.assertTrue(capture.hold_before_publish)
        self.assertEqual(parser.parse_args(["advance", "AF-TEST"]).command, "advance")
        choice = parser.parse_args(["choose-voice", "AF-TEST", "B", "--feedback", "More direct.", "--auto"])
        self.assertEqual(choice.candidate_id, "B")
        self.assertTrue(choice.auto)
        self.assertEqual(parser.parse_args(["models", "history"]).command, "models")
        self.assertEqual(parser.parse_args(["voice", "history"]).command, "voice")
        self.assertEqual(parser.parse_args(["voice", "rollback", "VP-2"]).version, "VP-2")

    def test_v3_order_has_one_normal_human_gate_and_bundles_v2(self):
        current = json.loads((SPEC_ROOT / "workflow" / "workflow.json").read_text(encoding="utf-8"))
        legacy = json.loads((SPEC_ROOT / "workflow" / "workflow.v2.0.0.json").read_text(encoding="utf-8"))
        self.assertEqual(current["workflow_version"], "3.0.0")
        self.assertEqual(legacy["workflow_version"], "2.0.0")

        states = {item["id"]: item for item in current["states"]}
        self.assertEqual(states["DRAFT"]["next_on_pass"], "CLAIM_VERIFICATION")
        self.assertEqual(states["CLAIM_VERIFICATION"]["next_on_pass"], "VOICE_PROBE")
        self.assertEqual(states["VOICE_PROBE"]["next_on_pass"], "VOICE_LEARNING")
        self.assertEqual(states["VOICE_LEARNING"]["next_on_pass"], "EDIT")

        human_states = [
            item["id"]
            for item in current["states"]
            if item.get("normal_action") == "human_decision"
            or item.get("actor") == "human"
        ]
        self.assertEqual(human_states, ["VOICE_PROBE"])

    def test_voice_probe_schema_requires_exactly_three_bound_candidates(self):
        schema = json.loads((SPEC_ROOT / "schemas" / "voice-probe.schema.json").read_text(encoding="utf-8"))
        v3 = next(
            branch
            for branch in schema["oneOf"]
            if branch["properties"]["voice_probe_schema_version"].get("const") == "2.0.0"
        )
        self.assertEqual(v3["properties"]["candidates"]["minItems"], 3)
        self.assertEqual(v3["properties"]["candidates"]["maxItems"], 3)
        for field in ("rough_draft_sha256", "claim_ledger_sha256", "source_anchor"):
            self.assertIn(field, v3["required"])


class LegacyRunTests(TemporaryRuntime):
    def test_v2_run_keeps_original_intent_approval_behavior(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        run["workflow_version"] = "2.0.0"
        run["state"] = "INTENT_REVIEW"
        run["status"] = "ACTIVE"
        af.save_run(directory, run)
        candidate = directory / "artifacts" / "legacy-intent-candidate.json"
        af.write_json(candidate, {"intent_schema_version": "1.0.0", "run_id": run_id})
        af.record_artifact(directory, run, candidate, "intent-candidate", {"actor": "test"})

        payload = af.next_state_payload(directory, run)
        self.assertEqual(payload["action"], "human_decision")
        self.assertEqual(payload["state"], "INTENT_REVIEW")
        self.assertEqual(payload["approval_command"][3], "G-INTENT-FIDELITY")

        definition = af.state_definition("VOICE_PROBE", run)
        self.assertEqual(definition["next_on_pass"], "DRAFT")


class ActiveSessionRegressionTests(TemporaryRuntime):
    def test_auto_start_invokes_advance(self):
        observed = {}

        def fake_advance(args):
            observed.update({"run_id": args.run_id, "max_steps": args.max_steps})
            af.emit({
                "ok": True,
                "action": "advanced-by-test-double",
                "run_id": args.run_id,
                "state": "RESEARCH_PLAN",
            }, args.json)
            return af.EXIT_WAITING

        with mock.patch.object(af, "command_advance", side_effect=fake_advance) as advance:
            code, payload = call(
                af.command_start,
                seed="Auto must continue the newly created run.",
                seed_file=None,
                slug=None,
                auto=True,
                draft_model=None,
                hold_before_publish=False,
            )

        self.assertEqual(code, af.EXIT_WAITING, payload)
        self.assertEqual(payload["action"], "advanced-by-test-double")
        self.assertEqual(observed, {"run_id": payload["run_id"], "max_steps": 100})
        advance.assert_called_once()
        _, run = af.load_run(payload["run_id"])
        self.assertEqual(run["state"], "RESEARCH_PLAN")


class ProcessLivenessRegressionTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows uses a Win32 process probe")
    def test_windows_pid_liveness_probe_never_uses_os_kill(self):
        with mock.patch.object(af.os, "kill", side_effect=AssertionError("os.kill would broadcast CTRL_C_EVENT")):
            self.assertTrue(af.process_is_alive(os.getpid()))

    def test_lock_release_retries_a_transient_windows_sharing_violation(self):
        path = mock.Mock()
        path.unlink.side_effect = [PermissionError("sharing violation"), None]
        with mock.patch.object(af.time, "sleep") as pause:
            af.release_lock_file(path)
        self.assertEqual(path.unlink.call_count, 2)
        pause.assert_called_once_with(0.01)


class PublicationTargetLockRegressionTests(TemporaryRuntime):
    def publication_repository(self, name="publication-repo"):
        repository = self.root / name
        (repository / "docs").mkdir(parents=True)
        (repository / "index.html").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(repository), "add", "index.html"], check=True)
        subprocess.run(["git", "-C", str(repository), "commit", "-qm", "base"], check=True)
        subprocess.run([
            "git", "-C", str(repository), "remote", "add", "origin",
            "https://github.com/example/theproductiveprompter.git",
        ], check=True)
        return repository

    def owner_record(self, **values):
        owner = {
            "pid": os.getpid(),
            "namespace": af.lock_namespace(),
            "created_at": af.utc_now(),
            "token": "a" * 32,
        }
        owner.update(values)
        return owner

    def publishable_run(self, repository, filename, contents):
        run_id = self.start(f"Publish {filename} safely.")
        directory, run = af.load_run(run_id)
        run["workflow_version"] = af.LEGACY_WORKFLOW_VERSION
        af.save_run(directory, run)
        source = directory / "package" / "site" / "docs" / filename
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(contents, encoding="utf-8")
        revision = af.sha256_bytes(contents.encode("utf-8"))
        af.write_json(directory / "package" / "package.json", {
            "package_revision": revision,
            "public_files": [],
        })
        base_commit = subprocess.check_output(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        plan = {
            "run_id": run_id,
            "target": "theproductiveprompter",
            "base_commit": base_commit,
            "package_revision": revision,
            "changes": [{
                "path": f"docs/{filename}",
                "current_sha256": None,
                "planned_sha256": af.sha256_path(source),
                "action": "add",
            }],
        }
        plan_path = directory / "publication" / "plan.json"
        af.write_json(plan_path, plan)
        approval_id = f"AP-{filename.replace('.', '-')}"
        approval_path = directory / "approvals" / f"{approval_id}.json"
        af.write_json(approval_path, {
            "publication_receipt_schema_version": "1.0.0",
            "run_id": run_id,
            "target": plan["target"],
            "package_revision": revision,
            "approval_id": approval_id,
            "plan_sha256": af.sha256_path(plan_path),
            "expires_at": "2099-01-01T00:00:00Z",
            "status": "APPROVED",
            "commit": None,
            "url": None,
            "checks": [],
            "created_at": af.utc_now(),
        })
        af.transition(directory, run, "PUBLISH", "test", "exercise publication serialization")
        return run_id, approval_id, directory

    def test_target_identity_uses_one_shared_lock_outside_checkout(self):
        first_repository = self.publication_repository("first-publication-repo")
        second_repository = self.publication_repository("second-publication-repo")
        target = af.load_json(af.SPEC_ROOT / "publication" / "theproductiveprompter.json")
        renamed_target = json.loads(json.dumps(target))
        renamed_target["target_id"] = "renamed-local-label"
        renamed_target["canonical_url"] = "https://changed.example/docs/{slug}.html"
        first_path = af.publication_target_lock_path(first_repository, target)
        second_path = af.publication_target_lock_path(second_repository, renamed_target)

        self.assertEqual(first_path, second_path)
        with self.assertRaises(ValueError):
            first_path.relative_to(first_repository)
        with af.publication_target_lock(first_repository, target):
            self.assertTrue(first_path.is_file())
            with self.assertRaises(af.FlowError) as caught:
                with af.publication_target_lock(second_repository, target, wait_seconds=0.05):
                    pass
        self.assertIn("Timed out waiting", str(caught.exception))
        self.assertFalse(first_path.exists())

    def test_shared_state_inside_checkout_is_rejected_instead_of_diverging_by_clone(self):
        repository = self.publication_repository()
        target = af.load_json(af.SPEC_ROOT / "publication" / "theproductiveprompter.json")
        with (
            mock.patch.object(af, "shared_state_root", return_value=repository / "runtime"),
            self.assertRaises(af.FlowError) as caught,
        ):
            af.publication_target_lock_path(repository, target)
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        self.assertIn("outside the publication checkout", str(caught.exception))

    def test_windows_and_wsl_remote_paths_normalize_to_one_identity(self):
        repository = self.publication_repository()
        windows = af.normalize_git_remote_url(
            r"C:\Users\Josia\Documents\theproductiveprompter.git",
            repository=repository,
        )
        wsl = af.normalize_git_remote_url(
            "/mnt/c/Users/Josia/Documents/theproductiveprompter.git",
            repository=repository,
        )
        self.assertEqual(windows, wsl)
        self.assertEqual(windows, "file:///c:/users/josia/documents/theproductiveprompter")
        https = af.normalize_git_remote_url(
            "https://github.com/josiahH-cf/theproductiveprompter.git",
            repository=repository,
        )
        ssh = af.normalize_git_remote_url(
            "git@github.com:josiahH-cf/theproductiveprompter.git",
            repository=repository,
        )
        self.assertEqual(https, ssh)

    def test_partial_owner_record_is_never_stolen(self):
        repository = self.publication_repository()
        target = af.load_json(af.SPEC_ROOT / "publication" / "theproductiveprompter.json")
        path = af.publication_target_lock_path(repository, target)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = b'{"pid":'
        path.write_bytes(partial)

        with self.assertRaises(af.FlowError) as caught:
            with af.publication_target_lock(repository, target, wait_seconds=0.05):
                pass

        self.assertIn("manual recovery", str(caught.exception))
        self.assertEqual(path.read_bytes(), partial)
        self.assertFalse(list(path.parent.glob(f"{path.name}.recovered-*")))
        path.unlink()

    def test_cross_host_owner_is_never_stolen_even_after_old_stale_horizon(self):
        repository = self.publication_repository()
        target = af.load_json(af.SPEC_ROOT / "publication" / "theproductiveprompter.json")
        path = af.publication_target_lock_path(repository, target)
        foreign = self.owner_record(
            pid=99999999,
            namespace="windows:other-host",
            created_at="2000-01-01T00:00:00Z",
            token="b" * 32,
        )
        af.atomic_write(path, af.canonical_json(foreign))

        with self.assertRaises(af.FlowError) as caught:
            with af.publication_target_lock(repository, target, wait_seconds=0.05):
                pass

        self.assertIn("cross-host ownership cannot be proven dead", str(caught.exception))
        self.assertEqual(af.read_lock_owner(path), ("valid", foreign))
        self.assertFalse(list(path.parent.glob(f"{path.name}.recovered-*")))
        path.unlink()

    def test_proven_dead_same_host_owner_is_recovered(self):
        repository = self.publication_repository()
        target = af.load_json(af.SPEC_ROOT / "publication" / "theproductiveprompter.json")
        path = af.publication_target_lock_path(repository, target)
        dead = self.owner_record(pid=99999999, created_at="2000-01-01T00:00:00Z", token="c" * 32)
        af.atomic_write(path, af.canonical_json(dead))

        with af.publication_target_lock(repository, target, wait_seconds=1):
            status, current = af.read_lock_owner(path)
            self.assertEqual(status, "valid")
            self.assertNotEqual(current["token"], dead["token"])

        recovered = path.with_name(f"{path.name}.recovered-{dead['token']}")
        self.assertEqual(af.read_lock_owner(recovered), ("valid", dead))
        self.assertFalse(path.exists())

    def test_release_detects_aba_and_preserves_successor(self):
        repository = self.publication_repository()
        target = af.load_json(af.SPEC_ROOT / "publication" / "theproductiveprompter.json")
        path = af.publication_target_lock_path(repository, target)
        successor = self.owner_record(token="d" * 32)

        with self.assertRaises(af.FlowError) as caught:
            with af.publication_target_lock(repository, target, wait_seconds=0.05):
                af.atomic_write(path, af.canonical_json(successor))

        self.assertIn("successor was preserved", str(caught.exception))
        self.assertEqual(af.read_lock_owner(path), ("valid", successor))
        path.unlink()

    def test_publication_lock_wait_covers_preflight_and_normal_push(self):
        self.assertEqual(af.publication_lock_wait_seconds(), 300)
        with mock.patch.dict(os.environ, {"ARTICLE_FLOW_PUBLICATION_LOCK_WAIT_SECONDS": "420"}, clear=False):
            self.assertEqual(af.publication_lock_wait_seconds(), 420)

    def test_concurrent_runs_revalidate_base_only_after_target_lock(self):
        repository = self.publication_repository()
        first_run, first_approval, _ = self.publishable_run(repository, "first.html", "first\n")
        second_run, second_approval, _ = self.publishable_run(repository, "second.html", "second\n")
        entered_copy = threading.Event()
        release_copy = threading.Event()
        original_atomic_write = af.atomic_write
        first_destination = repository / "docs" / "first.html"

        def paused_atomic_write(path, data):
            if Path(path) == first_destination:
                entered_copy.set()
                if not release_copy.wait(timeout=5):
                    raise AssertionError("test did not release the first publisher")
            return original_atomic_write(path, data)

        def execute(run_id, approval_id):
            try:
                return af.command_publish_execute(namespace(
                    run_id=run_id,
                    approval=approval_id,
                    commit=True,
                    push=False,
                ))
            except Exception as exc:  # Return the expected loser for thread-safe inspection.
                return exc

        with (
            mock.patch.dict(os.environ, {"ARTICLE_FLOW_TEST_NO_PUBLISH": ""}, clear=False),
            mock.patch.object(af, "publication_repo_root", return_value=repository),
            mock.patch.object(af, "atomic_write", side_effect=paused_atomic_write),
            mock.patch.object(af, "emit"),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            first_future = pool.submit(execute, first_run, first_approval)
            self.assertTrue(entered_copy.wait(timeout=5))
            second_future = pool.submit(execute, second_run, second_approval)
            self.assertFalse(second_future.done())
            release_copy.set()
            first_result = first_future.result(timeout=10)
            second_result = second_future.result(timeout=10)

        self.assertEqual(first_result, af.EXIT_OK)
        self.assertIsInstance(second_result, af.FlowError)
        self.assertIn("HEAD changed after publication planning", str(second_result))
        self.assertTrue((repository / "docs" / "first.html").is_file())
        self.assertFalse((repository / "docs" / "second.html").exists())
        commit_count = subprocess.check_output(
            ["git", "-C", str(repository), "rev-list", "--count", "HEAD"],
            text=True,
        ).strip()
        self.assertEqual(commit_count, "2")

    def test_push_failure_handoff_is_created_before_target_unlock(self):
        repository = self.publication_repository()
        run_id, approval_id, directory = self.publishable_run(repository, "failed-push.html", "pending\n")
        target = af.load_json(af.SPEC_ROOT / "publication" / "theproductiveprompter.json")
        original_git = af.git
        original_handoff = af.create_publication_handoff
        observed = {"locked_during_cleanup": False}

        def fail_push(arguments, **kwargs):
            if arguments and arguments[0] == "push":
                raise af.FlowError("simulated push failure")
            return original_git(arguments, **kwargs)

        def checked_handoff(*args, **kwargs):
            with self.assertRaises(af.FlowError):
                with af.publication_target_lock(repository, target, wait_seconds=0.05):
                    pass
            observed["locked_during_cleanup"] = True
            return original_handoff(*args, **kwargs)

        with (
            mock.patch.dict(os.environ, {"ARTICLE_FLOW_TEST_NO_PUBLISH": ""}, clear=False),
            mock.patch.object(af, "publication_repo_root", return_value=repository),
            mock.patch.object(af, "publication_push_preflight", return_value={"ok": True, "reason": "test"}),
            mock.patch.object(af, "git", side_effect=fail_push),
            mock.patch.object(af, "create_publication_handoff", side_effect=checked_handoff),
        ):
            code, payload = call(
                af.command_publish_execute,
                run_id=run_id,
                approval=approval_id,
                commit=True,
                push=True,
            )

        self.assertEqual(code, af.EXIT_WAITING, payload)
        self.assertTrue(observed["locked_during_cleanup"])
        self.assertTrue((directory / "publication" / "incomplete.json").is_file())
        self.assertFalse(af.publication_target_lock_path(repository, target).exists())
class RepairAttemptBoundRegressionTests(TemporaryRuntime):
    @staticmethod
    def route_set(stage):
        chosen = {
            "provider": "fixture",
            "model": "fixture-model",
            "model_version": "test",
            "eligible": True,
            "exclusion_reason": None,
            "capability_assumptions": [],
            "evaluation_score": None,
            "kind": "command",
            "privacy": "test",
            "locality": "local",
            "cost_class": "test",
            "latency_class": "test",
            "canary_status": "passed",
        }
        return {
            "stage": stage,
            "required_capabilities": sorted(af.STAGE_CAPABILITIES.get(stage, set())),
            "candidates": [chosen],
            "chosen": chosen,
            "fallbacks": [],
            "reason": "fixture repair route",
            "configuration_path": "test",
        }

    def research_run(self):
        run_id = self.start("A bounded evidence repair should never reuse an attempt.")
        directory, run = af.load_run(run_id)
        self.record_json(directory, run, "research-plan", {"fixture": True})
        af.transition(directory, run, "RESEARCH", "test", "Exercise the evidence repair boundary")
        return run_id, directory

    @staticmethod
    def finding(number):
        return {
            "criterion": "claim_disposition",
            "artifact": "claim-ledger",
            "location": f"claim:CL-{number:03d}",
            "finding": f"Claim CL-{number:03d} still needs a disposition.",
            "repair_instruction": "Mark the claim supported, qualified, or omitted with evidence.",
        }

    def test_shifting_findings_get_three_immutable_hash_bound_attempts_then_block(self):
        run_id, directory = self.research_run()
        packets = []
        gate_calls = 0

        def shifting_gate(_directory, _run, _stage, _destination):
            nonlocal gate_calls
            gate_calls += 1
            return "REPAIR", [self.finding(gate_calls)]

        def execute_fixture(args):
            current_directory, run = af.load_run(args.run_id)
            packet_path, packet = af.current_packet(current_directory, run)
            packets.append(json.loads(json.dumps(packet)))
            output_path = Path(packet["expected_outputs"][0]["path"])
            af.write_json(output_path, {"attempt": packet["attempt"], "marker": f"immutable-{packet['attempt']}"})
            route = packet["selected_route"]["chosen"]
            receipt_path = current_directory / "receipts" / f"model-call-research-{packet['attempt']:02d}.json"
            af.write_json(receipt_path, {
                "stage": "RESEARCH",
                "attempt": packet["attempt"],
                "packet_sha256": af.sha256_path(packet_path),
                "output_sha256": af.sha256_path(output_path),
                "route": {"provider": route["provider"], "model": route["model"]},
            })
            af.record_artifact(
                current_directory,
                run,
                receipt_path,
                f"model-call:RESEARCH:{packet['attempt']}",
                {"actor": "test"},
            )
            return af.command_submit(namespace(
                run_id=args.run_id,
                stage="RESEARCH",
                file=str(output_path),
            ))

        with (
            mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
            mock.patch.object(af, "automatic_gate", side_effect=shifting_gate),
            mock.patch.object(af, "command_execute_stage", side_effect=execute_fixture) as execute,
        ):
            code, blocked = call(af.command_advance, run_id=run_id)
            self.assertEqual(code, af.EXIT_WAITING, blocked)
            self.assertEqual(blocked["action"], "repair_required")
            self.assertEqual(blocked["gate"], "G-EVIDENCE-COVERAGE")
            self.assertEqual(execute.call_count, 3)

            code, still_blocked = call(af.command_advance, run_id=run_id)
            self.assertEqual(code, af.EXIT_WAITING, still_blocked)
            self.assertEqual(still_blocked["action"], "repair_required")
            self.assertEqual(execute.call_count, 3)

        self.assertEqual([packet["attempt"] for packet in packets], [1, 2, 3])
        self.assertIsNone(packets[0]["repair_context"])
        for packet, prior_attempt in zip(packets[1:], (1, 2)):
            context = packet["repair_context"]
            self.assertEqual(context["failed_attempt"], prior_attempt)
            self.assertEqual(context["findings"][0]["location"], f"claim:CL-{prior_attempt:03d}")
            references = {item["id"]: item for item in packet["inputs"]}
            for key in ("rejected_output", "gate_receipt"):
                reference = context[key]
                self.assertIn(reference["input_id"], references)
                self.assertEqual(references[reference["input_id"]]["sha256"], reference["sha256"])
                self.assertEqual(af.sha256_path(Path(reference["path"])), reference["sha256"])

        for attempt in (1, 2, 3):
            self.assertEqual(
                af.load_json(directory / "artifacts" / f"{attempt:02d}-claim-ledger.json"),
                {"attempt": attempt, "marker": f"immutable-{attempt}"},
            )
            self.assertTrue((directory / "tasks" / f"research-{attempt:02d}.json").is_file())
            self.assertTrue((directory / "submissions" / f"{attempt:02d}-claim-ledger.json").is_file())
            self.assertTrue((directory / "receipts" / f"model-call-research-{attempt:02d}.json").is_file())
        self.assertEqual(len(list((directory / "receipts").glob("g-evidence-coverage-*.json"))), 3)

        _, run = af.load_run(run_id)
        self.assertEqual(run["status"], "BLOCKED")
        self.assertEqual(run["attempts"]["RESEARCH"], 3)
        events = af._read_jsonl(directory / "events.jsonl")
        rejected = [event for event in events if event["type"] == "MODEL_OUTPUT_REJECTED"]
        self.assertEqual([event["payload"]["findings"][0]["location"] for event in rejected], [
            "claim:CL-001",
            "claim:CL-002",
            "claim:CL-003",
        ])
        repairs = [event for event in events if event["type"] == "REPAIR" and event["actor"] == "controller"]
        self.assertEqual(len(repairs), 2)
        escalations = [event for event in events if event["type"] == "ESCALATION"]
        self.assertEqual(len(escalations), 1)
        self.assertEqual(escalations[0]["payload"]["maximum"], 3)

        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            code, repaired = call(af.command_repair, run_id=run_id, gate_id="G-EVIDENCE-COVERAGE", finding=None)
            self.assertEqual(code, af.EXIT_OK, repaired)
            current_directory, run = af.load_run(run_id)
            packet_path, packet = af.task_packet(current_directory, run)
        self.assertEqual(packet["attempt"], 4)
        self.assertEqual(packet["repair_context"]["failed_attempt"], 3)
        self.assertEqual(packet["repair_context"]["findings"][0]["location"], "claim:CL-003")
        self.assertEqual(packet_path.name, "research-04.json")

    def test_stale_attempt_counter_uses_four_rejections_and_blocks_before_execution(self):
        run_id, directory = self.research_run()
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            _, packet = af.task_packet(directory, af.load_run(run_id)[1])
        output_path = directory / "artifacts" / "01-claim-ledger.json"
        af.write_json(output_path, {"attempt": 1, "marker": "latest-overwritten-legacy-output"})
        _, run = af.load_run(run_id)
        af.record_artifact(directory, run, output_path, "claim-ledger", {"actor": "test"})
        af.write_gate_receipt(
            directory,
            run,
            "G-EVIDENCE-COVERAGE",
            "REPAIR",
            [self.finding(4)],
            {"type": "code", "version": "legacy-test"},
            "RESEARCH",
        )
        for failure_count in range(1, 5):
            af.append_event(directory, run, "MODEL_OUTPUT_REJECTED", "controller", {
                "state": "RESEARCH",
                "route": packet["selected_route"]["chosen"],
                "failure_count": failure_count,
                "findings": [self.finding(failure_count)],
            })
        run["attempts"]["RESEARCH"] = 1
        run["status"] = "ACTIVE"
        af.save_run(directory, run)

        with mock.patch.object(af, "command_execute_stage", side_effect=AssertionError("a fifth execution was launched")) as execute:
            code, blocked = call(af.command_advance, run_id=run_id)
        self.assertEqual(code, af.EXIT_WAITING, blocked)
        self.assertEqual(blocked["action"], "repair_required")
        execute.assert_not_called()
        _, run = af.load_run(run_id)
        self.assertEqual(run["status"], "BLOCKED")
        self.assertEqual(run["attempts"]["RESEARCH"], 4)
        self.assertEqual(run["pending_repair"]["failed_attempt"], 4)
        self.assertEqual(run["pending_repair"]["findings"][0]["location"], "claim:CL-004")

        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            code, _ = call(af.command_repair, run_id=run_id, gate_id="G-EVIDENCE-COVERAGE", finding=None)
            self.assertEqual(code, af.EXIT_OK)
            current_directory, run = af.load_run(run_id)
            packet_path, resumed = af.task_packet(current_directory, run)
        self.assertEqual(resumed["attempt"], 5)
        self.assertEqual(resumed["repair_context"]["failed_attempt"], 4)
        self.assertEqual(resumed["repair_context"]["findings"][0]["location"], "claim:CL-004")
        self.assertEqual(packet_path.name, "research-05.json")
        self.assertEqual(af.load_json(output_path)["marker"], "latest-overwritten-legacy-output")


class InstallationRegressionTests(TemporaryRuntime):
    def install_fixture(self, label):
        root = self.root / label
        wsl_user = root / "wsl-user"
        windows_user = root / "windows-user"
        publication = root / "publication"
        publication.mkdir(parents=True)
        wsl_record = wsl_user / ".local" / "share" / "article-flow" / "current.json"
        windows_record = windows_user / ".article-flow" / "current.json"
        wsl_launcher = wsl_user / ".local" / "bin" / "article-flow"
        windows_launcher = windows_user / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "article-flow.cmd"
        python_exe = windows_user / "AppData" / "Local" / "Programs" / "Python" / "Python312" / "python.exe"
        values = {
            wsl_record: b'{"sentinel":"wsl-record"}\n',
            windows_record: b'{"sentinel":"windows-record"}\n',
            wsl_launcher: b"#!/bin/sh\n# article-flow managed launcher sentinel\n",
            windows_launcher: b"@echo off\r\nrem article-flow managed launcher sentinel\r\n",
            python_exe: b"test-python",
        }
        for path, value in values.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        watched = (wsl_record, windows_record, wsl_launcher, windows_launcher)
        return {
            "wsl_user": wsl_user,
            "windows_user": windows_user,
            "publication": publication,
            "wsl_home": wsl_record.parent,
            "windows_home": windows_record.parent,
            "watched": watched,
            "before": {path: path.read_bytes() for path in watched},
        }

    def install_args(self, *, development):
        return namespace(
            hosts="windows,wsl",
            providers="auto",
            user=True,
            development=development,
        )

    def assert_install_targets_unchanged(self, fixture):
        self.assertEqual(
            fixture["before"],
            {path: path.read_bytes() for path in fixture["watched"]},
        )

    def test_dual_host_install_preflight_is_atomic_for_invalid_release_tree(self):
        for invalid_host in ("wsl", "windows"):
            with self.subTest(invalid_host=invalid_host):
                fixture = self.install_fixture(f"invalid-{invalid_host}")
                invalid_home = fixture[f"{invalid_host}_home"]
                (invalid_home / "releases" / "unrecognized" / "Article-Spec-Pack-v1").mkdir(parents=True)
                with (
                    mock.patch.object(Path, "home", return_value=fixture["wsl_user"]),
                    mock.patch.object(af, "windows_user_root", return_value=fixture["windows_user"]),
                    mock.patch.object(af, "publication_repo_root", return_value=fixture["publication"]),
                    mock.patch.dict(os.environ, {"ARTICLE_FLOW_HOME": ""}),
                ):
                    with self.assertRaises(af.FlowError) as caught:
                        af.command_install(self.install_args(development=True))
                self.assertIn("unrecognized release directory", str(caught.exception))
                self.assert_install_targets_unchanged(fixture)

    def test_dual_host_install_manifest_failure_is_atomic(self):
        fixture = self.install_fixture("manifest-failure")
        failed_manifest = {
            "ok": False,
            "source": "worktree",
            "failures": [{"kind": "hash_mismatch"}],
        }
        with (
            mock.patch.object(Path, "home", return_value=fixture["wsl_user"]),
            mock.patch.object(af, "windows_user_root", return_value=fixture["windows_user"]),
            mock.patch.object(af, "check_manifest", return_value=failed_manifest),
            mock.patch.dict(os.environ, {"ARTICLE_FLOW_HOME": ""}),
        ):
            with self.assertRaises(af.FlowError) as caught:
                af.command_install(self.install_args(development=False))
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        self.assert_install_targets_unchanged(fixture)

    def test_installation_health_requires_exact_repo_root_in_both_host_launchers(self):
        fixture = self.install_fixture("health")
        wsl_record, windows_record, wsl_launcher, windows_launcher = fixture["watched"]
        source_commit = "a" * 40
        expected_runs_root = self.runtime / "runs"
        publication = fixture["publication"].resolve()
        common = {
            "controller_version": af.CONTROLLER_VERSION,
            "workflow_version": af.workflow()["workflow_version"],
            "development": False,
            "linked_checkout": True,
            "source_commit": source_commit,
        }
        af.write_json(wsl_record, {
            **common,
            "spec_root": str(af.SPEC_ROOT.resolve()),
            "source_checkout": str(af.REPO_ROOT.resolve()),
            "publication_repo_root": str(publication),
            "captured_material_root": str(expected_runs_root.resolve()),
        })
        af.write_json(windows_record, {
            **common,
            "spec_root": af.windows_path(af.SPEC_ROOT),
            "source_checkout": af.windows_path(af.REPO_ROOT),
            "publication_repo_root": af.windows_path(publication),
            "captured_material_root": af.windows_path(expected_runs_root),
        })
        wsl_launcher_bytes = (
            f"#!/usr/bin/env sh\n# article-flow managed launcher {af.CONTROLLER_VERSION}\n"
            f"export ARTICLE_FLOW_HOME={af.shlex.quote(str(wsl_record.parent.resolve()))}\n"
            f"export ARTICLE_FLOW_RUNS_ROOT={af.shlex.quote(str(expected_runs_root.resolve()))}\n"
            f"export ARTICLE_FLOW_REPO_ROOT={af.shlex.quote(str(publication))}\n"
            f"exec python3 {af.shlex.quote(str(af.SCRIPT_PATH.resolve()))} \"$@\"\n"
        ).encode("utf-8")
        python_exe = fixture["windows_user"] / "AppData" / "Local" / "Programs" / "Python" / "Python312" / "python.exe"
        windows_launcher_bytes = (
            f"@echo off\r\nrem article-flow managed launcher {af.CONTROLLER_VERSION}\r\n"
            f"set \"ARTICLE_FLOW_HOME={af.windows_path(windows_record.parent)}\"\r\n"
            f"set \"ARTICLE_FLOW_RUNS_ROOT={af.windows_path(expected_runs_root)}\"\r\n"
            f"set \"ARTICLE_FLOW_REPO_ROOT={af.windows_path(publication)}\"\r\n"
            f"\"{af.windows_path(python_exe)}\" \"{af.windows_path(af.SCRIPT_PATH)}\" %*\r\n"
        ).encode("utf-8")
        af.atomic_write(wsl_launcher, wsl_launcher_bytes)
        af.atomic_write(windows_launcher, windows_launcher_bytes)

        with (
            mock.patch.object(Path, "home", return_value=fixture["wsl_user"]),
            mock.patch.object(af, "windows_user_root", return_value=fixture["windows_user"]),
            mock.patch.object(af, "publication_repo_root", return_value=publication),
            mock.patch.object(af, "release_source_commit", return_value=source_commit),
        ):
            healthy = af.installation_health()
            self.assertTrue(healthy["ok"], healthy)
            expected_hosts = {"windows"} if os.name == "nt" else {"wsl", "windows"}
            self.assertEqual({item["host"] for item in healthy["checks"]}, expected_hosts)

            if os.name != "nt":
                repo_line = f"export ARTICLE_FLOW_REPO_ROOT={af.shlex.quote(str(publication))}\n".encode("utf-8")
                af.atomic_write(wsl_launcher, wsl_launcher_bytes.replace(repo_line, b""))
                missing = af.installation_health()
                missing_by_host = {item["host"]: item for item in missing["checks"]}
                self.assertFalse(missing_by_host["wsl"]["launcher_agrees"])
                self.assertTrue(missing_by_host["windows"]["launcher_agrees"])

            af.atomic_write(wsl_launcher, wsl_launcher_bytes)
            windows_repo_line = (
                f"set \"ARTICLE_FLOW_REPO_ROOT={af.windows_path(publication)}\"\r\n"
            ).encode("utf-8")
            wrong_repo_line = (
                f"set \"ARTICLE_FLOW_REPO_ROOT={af.windows_path(publication)}-wrong\"\r\n"
            ).encode("utf-8")
            altered_launcher = windows_launcher_bytes.replace(windows_repo_line, wrong_repo_line)
            self.assertNotEqual(altered_launcher, windows_launcher_bytes)
            af.atomic_write(windows_launcher, altered_launcher)
            altered = af.installation_health()
            altered_by_host = {item["host"]: item for item in altered["checks"]}
            if os.name != "nt":
                self.assertTrue(altered_by_host["wsl"]["launcher_agrees"])
            self.assertFalse(altered_by_host["windows"]["launcher_agrees"])


class ModelRotationTests(TemporaryRuntime):
    @staticmethod
    def model_id(assignment):
        return assignment["assigned_model_id"]

    def test_four_model_round_robin_override_and_history(self):
        assignments = [af.reserve_draft_model(f"AF-ROTATION-{index}") for index in range(8)]
        self.assertEqual([self.model_id(item) for item in assignments], MODEL_POOL * 2)

        override = af.reserve_draft_model("AF-OVERRIDE", override="gpt-5.6-luna")
        self.assertEqual(self.model_id(override), "gpt-5.6-luna")
        self.assertTrue(override["override"])
        following = af.reserve_draft_model("AF-AFTER-OVERRIDE")
        self.assertEqual(self.model_id(following), "gpt-5.5")

        history = af.model_history()
        records = history["runs"]
        self.assertEqual(len(records), 10)
        self.assertEqual(records[-2]["assigned_model_id"], "gpt-5.6-luna")
        self.assertTrue(records[-2]["override"])

    def test_concurrent_reservations_do_not_duplicate_rotation_slots(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            assignments = list(pool.map(lambda index: af.reserve_draft_model(f"AF-CONCURRENT-{index}"), range(8)))
        counts = {model: 0 for model in MODEL_POOL}
        for assignment in assignments:
            counts[self.model_id(assignment)] += 1
        self.assertEqual(counts, {model: 2 for model in MODEL_POOL})
        history = af.model_history()["runs"]
        self.assertEqual(len(history), 8)
        self.assertEqual({item["run_id"] for item in history}, {f"AF-CONCURRENT-{index}" for index in range(8)})

    def test_writing_fallback_is_pinned_and_provenance_is_disclosed(self):
        run_id = self.start(draft_model="gpt-5.5")
        directory, run = af.load_run(run_id)
        af.transition(directory, run, "DRAFT", "test", "exercise writing fallback provenance")
        run["status"] = "WAITING_MODEL"
        af.save_run(directory, run)

        packet_path = directory / "tasks" / "fallback-test.json"
        af.write_json(packet_path, {"run_id": run_id, "stage": "DRAFT"})
        af.record_artifact(directory, run, packet_path, "task-packet:DRAFT:1", {"actor": "test"})
        run["attempts"]["DRAFT"] = 1
        af.save_run(directory, run)
        output_path = directory / "submissions" / "fallback-draft.md"
        route = lambda model: {
            "provider": "codex-cli",
            "model": model,
            "model_version": "test",
            "kind": "codex-cli",
            "eligible": True,
        }
        packet = {
            "run_id": run_id,
            "stage": "DRAFT",
            "attempt": 1,
            "expected_outputs": [{"path": str(output_path), "format": "md"}],
            "selected_route": {
                "reason": "pinned writing experiment",
                "chosen": route("gpt-5.5"),
                "fallbacks": [route("gpt-5.6-sol")],
                "candidates": [route("gpt-5.5"), route("gpt-5.6-sol")],
            },
        }
        successful_call = {
            "provider": "codex-cli",
            "model": "gpt-5.6-sol",
            "model_version": "test",
            "elapsed_ms": 1,
            "transport": {"kind": "codex-cli", "exit_code": 0},
        }
        def submit_in_process(command, **kwargs):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                return_code = af.command_submit(
                    namespace(run_id=run_id, stage="DRAFT", file=str(output_path))
                )
            return subprocess.CompletedProcess(
                args=command,
                returncode=return_code,
                stdout=stream.getvalue(),
                stderr="",
            )

        with (
            mock.patch.object(af, "current_packet", return_value=(packet_path, packet)),
            mock.patch.object(
                af,
                "invoke_route",
                side_effect=[af.FlowError("assigned route failed"), ("# Fallback draft\n", successful_call)],
            ),
            mock.patch.object(af.subprocess, "run", side_effect=submit_in_process),
        ):
            code, payload = call(af.command_execute_stage, run_id=run_id)
        self.assertEqual(code, af.EXIT_OK, payload)
        _, current = af.load_run(run_id)
        experiment = current["model_experiment"]
        self.assertEqual(experiment["assigned_model_id"], "gpt-5.5")
        self.assertEqual(experiment["active_model_id"], "gpt-5.6-sol")
        self.assertTrue(experiment["contaminated"])
        self.assertEqual(experiment["actual_models"], ["gpt-5.6-sol"])
        self.assertEqual(experiment["stage_routes"]["DRAFT"]["actual_model_id"], "gpt-5.6-sol")
        accepted_draft = af.artifact_path(directory, current, "draft")
        self.record_text(
            directory,
            current,
            "article",
            accepted_draft.read_text(encoding="utf-8"),
            "fallback-article.md",
        )
        metadata = af.package_metadata(directory, current)
        self.assertEqual(metadata["drafting_models"], [{
            "model_id": "gpt-5.6-sol",
            "public_display_name": "GPT-5.6 Sol",
        }])
        package_root = self.root / "fallback-footer"
        af.render_publication_files(directory, current, package_root, metadata)
        rendered = (package_root / "site" / "docs" / f"{metadata['slug']}.html").read_text(encoding="utf-8")
        self.assertIn("Drafting model: GPT-5.6 Sol", rendered)
        self.assertNotIn("Drafting model: GPT-5.5", rendered)

        history = af.model_history()["runs"]
        record = next(item for item in history if item["run_id"] == run_id)
        self.assertTrue(record["contaminated"])
        self.assertEqual(record["actual_models"], ["gpt-5.6-sol"])

    def test_model_history_uses_durable_outcome_when_run_directory_is_missing(self):
        run_id = self.start(draft_model="gpt-5.5")
        directory, run = af.load_run(run_id)
        run["model_experiment"].update({
            "active_model_id": "gpt-5.6-sol",
            "actual_models": ["gpt-5.6-sol"],
            "contaminated": True,
            "stage_routes": {
                "DRAFT": {
                    "provider_id": "codex-cli",
                    "assigned_model_id": "gpt-5.5",
                    "actual_model_id": "gpt-5.6-sol",
                    "public_display_name": "GPT-5.6 Sol",
                    "fallback": True,
                    "accepted_at": af.utc_now(),
                },
            },
        })
        af.save_run(directory, run)
        durable = af.record_experiment_outcome(directory, run)
        self.assertEqual(durable["actual_model_id"], "gpt-5.6-sol")
        detached = directory.with_name(f"detached-{directory.name}")
        directory.rename(detached)

        record = next(item for item in af.model_history()["runs"] if item["run_id"] == run_id)
        self.assertEqual(record["state"], "COMPLETE")
        self.assertEqual(record["active_model_id"], "gpt-5.6-sol")
        self.assertEqual(record["actual_models"], ["gpt-5.6-sol"])
        self.assertEqual(record["stage_routes"]["DRAFT"]["actual_model_id"], "gpt-5.6-sol")
        self.assertTrue(record["contaminated"])

    def test_pin_writing_route_chooses_first_eligible_experiment_pool_fallback(self):
        run_id = self.start(draft_model="gpt-5.5")
        _, run = af.load_run(run_id)

        def route(model, eligible, reason=None):
            return {
                "provider": "codex-cli",
                "model": model,
                "model_version": "test",
                "eligible": eligible,
                "exclusion_reason": reason,
            }

        assigned = route("gpt-5.5", False, "canary failed")
        sol = route("gpt-5.6-sol", True)
        terra = route("gpt-5.6-terra", True)
        pinned = af.pin_writing_route(run, "DRAFT", {
            "stage": "DRAFT",
            "candidates": [terra, assigned, sol],
            "chosen": terra,
            "fallbacks": [sol],
            "reason": "generic router choice",
        })

        self.assertEqual(pinned["chosen"]["model"], "gpt-5.6-sol")
        self.assertEqual([item["model"] for item in pinned["fallbacks"]], ["gpt-5.6-terra"])
        self.assertTrue(pinned["assignment_fallback"])
        self.assertEqual(pinned["assigned_route"], assigned)

    def test_explicit_route_cannot_bypass_pinned_writing_model_or_accepted_fallback(self):
        run_id = self.start(draft_model="gpt-5.5")
        directory, run = af.load_run(run_id)
        af.transition(directory, run, "DRAFT", "test", "exercise explicit writing-route isolation")

        def route(model):
            return {
                "provider": "codex-cli",
                "model": model,
                "model_version": "test",
                "eligible": True,
                "exclusion_reason": None,
                "capability_assumptions": [],
                "evaluation_score": None,
                "kind": "codex-cli",
                "privacy": "test",
                "locality": "local",
                "cost_class": "test",
                "latency_class": "test",
                "canary_status": "passed",
            }

        candidates = [route(model) for model in MODEL_POOL]
        routes = {
            "stage": "DRAFT",
            "required_capabilities": ["long-form"],
            "candidates": candidates,
            "chosen": candidates[2],
            "fallbacks": candidates[:2] + candidates[3:],
            "reason": "generic router choice",
            "configuration_path": "test",
        }
        with mock.patch.object(af, "route_candidates", return_value=routes):
            with self.assertRaises(af.FlowError) as initial_error:
                af.command_execute_stage(namespace(
                    run_id=run_id,
                    route="codex-cli:gpt-5.6-terra",
                    canary=False,
                ))
            self.assertEqual(initial_error.exception.code, af.EXIT_APPROVAL)
            self.assertIn("cannot bypass", str(initial_error.exception))

            af.update_writing_provenance(directory, run, "DRAFT", {
                "provider": "codex-cli",
                "model": "gpt-5.6-sol",
            })
            with self.assertRaises(af.FlowError) as fallback_error:
                af.command_execute_stage(namespace(
                    run_id=run_id,
                    route="codex-cli:gpt-5.5",
                    canary=False,
                ))
            self.assertEqual(fallback_error.exception.code, af.EXIT_APPROVAL)
            self.assertIn("cannot bypass", str(fallback_error.exception))

        _, current = af.load_run(run_id)
        self.assertEqual(current["model_experiment"]["active_model_id"], "gpt-5.6-sol")
        self.assertFalse(any(
            str(item.get("type", "")).startswith("task-packet:DRAFT:")
            for item in current["artifact_index"]
        ))

    def test_rendered_footer_uses_the_accepted_draft_receipt(self):
        run_id = self.start(draft_model="gpt-5.6-terra")
        directory, run = af.load_run(run_id)
        draft_text = "# Model Footer Test\n\nA concrete paragraph proves which drafting receipt was accepted.\n"
        draft_path = self.record_text(directory, run, "draft", draft_text, "footer-draft.md")
        self.record_text(directory, run, "article", draft_text, "footer-article.md")
        receipt = {
            "model_call_receipt_schema_version": "1.0.0",
            "run_id": run_id,
            "stage": "DRAFT",
            "attempt": 1,
            "packet_sha256": "0" * 64,
            "output_sha256": af.sha256_path(draft_path),
            "selection_reason": "fallback accepted after the assigned route failed",
            "route": {
                "provider": "codex-cli",
                "model": "gpt-5.6-terra",
                "model_version": "test",
                "elapsed_ms": 1,
                "transport": {"kind": "codex-cli", "exit_code": 0},
            },
            "canary_execution": False,
            "created_at": af.utc_now(),
        }
        self.record_json(directory, run, "model-call:DRAFT:1", receipt, "footer-model-call.json")
        accepted_route = af.latest_model_call_route(directory, run, "DRAFT", 1)
        af.update_writing_provenance(directory, run, "DRAFT", accepted_route)
        derived = af.package_metadata(directory, run)
        self.assertEqual(derived["drafting_models"], [{
            "model_id": "gpt-5.6-terra",
            "public_display_name": "GPT-5.6 Terra",
        }])
        metadata = {
            "title": "Model Footer Test",
            "slug": "model-footer-test-v3",
            "description": "A direct check of truthful drafting attribution.",
            "reader_job": "Verify the drafting model attribution.",
            "date": "2026-09-01",
            "date_iso": "2026-09-01T12:00:00-05:00",
            "author": "Josiah Hunter",
            "tags": ["workflow"],
            "archetype": "field-note",
            "opening": "artifact",
            "ending": "decision-rule",
            "summary": "never",
            "narrative_person": "mixed",
            "workflow_version": "3.0.0",
            "voice_profile_version": "test",
            "drafting_models": derived["drafting_models"],
            "style_policy_sha256": derived["style_policy_sha256"],
        }
        package_root = self.root / "footer-package"
        af.render_publication_files(directory, run, package_root, metadata)
        rendered = (package_root / "site" / "docs" / "model-footer-test-v3.html").read_text(encoding="utf-8")
        self.assertIn("Drafting model: GPT-5.6 Terra", rendered)
        self.assertNotIn("Drafting model: GPT-5.5", rendered)


class PacketRoutingRegressionTests(TemporaryRuntime):
    @staticmethod
    def route(model, *, eligible, canary_status, exclusion_reason=None):
        return {
            "provider": "fixture-command",
            "model": model,
            "model_version": "test",
            "eligible": eligible,
            "exclusion_reason": exclusion_reason,
            "capability_assumptions": [],
            "evaluation_score": None,
            "kind": "command",
            "privacy": "test",
            "locality": "local",
            "cost_class": "test",
            "latency_class": "test",
            "canary_status": canary_status,
        }

    def test_explicit_canary_refreshes_cached_packet_and_receipt_uses_selected_route(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        default = self.route("default-model", eligible=True, canary_status="passed")
        canary = self.route(
            "canary-model",
            eligible=False,
            canary_status="required",
            exclusion_reason="canary required",
        )
        routes = {
            "stage": "RESEARCH_PLAN",
            "required_capabilities": ["structured-output"],
            "candidates": [default, canary],
            "chosen": default,
            "fallbacks": [],
            "reason": "fixture default",
            "configuration_path": "test",
        }
        output = json.dumps({
            "research_plan_schema_version": "1.0.0",
            "run_id": run_id,
            "questions": [{
                "question": "Does the refreshed packet remain hash-bound?",
                "why_it_matters": "The receipt must identify the selected route.",
                "intent_changing": True,
            }],
            "source_strategy": ["Inspect the local task packet and receipt."],
            "claim_risks": [],
            "no_search_behavior": "not-applicable",
        })
        call_receipt = {
            "provider": "fixture-command",
            "model": "canary-model",
            "model_version": "test",
            "elapsed_ms": 1,
            "transport": {"kind": "command", "exit_code": 0},
        }
        submitted = subprocess.CompletedProcess(args=[], returncode=af.EXIT_OK, stdout="{}\n", stderr="")

        with mock.patch.object(af, "route_candidates", return_value=routes):
            cached_path, cached = af.task_packet(directory, run)
            self.assertEqual(cached["selected_route"]["chosen"]["model"], "default-model")
            refreshed_path, refreshed = af.current_packet(
                directory,
                run,
                requested_route="fixture-command:canary-model",
                allow_canary=True,
            )
            self.assertNotEqual(refreshed_path, cached_path)
            self.assertEqual(refreshed["attempt"], cached["attempt"] + 1)
            selected = refreshed["selected_route"]["chosen"]
            self.assertEqual((selected["provider"], selected["model"]), ("fixture-command", "canary-model"))
            self.assertTrue(selected["canary_execution"])

            _, current = af.load_run(run_id)
            same_path, same_packet = af.current_packet(
                directory,
                current,
                requested_route="fixture-command:canary-model",
                allow_canary=True,
            )
            self.assertEqual(same_path, refreshed_path)
            self.assertEqual(same_packet["attempt"], refreshed["attempt"])

            with (
                mock.patch.object(af, "invoke_route", return_value=(output, call_receipt)) as invoked,
                mock.patch.object(af.subprocess, "run", return_value=submitted),
            ):
                # Deliberately omit CLI canary flags here: receipt truth must come
                # from the already selected, hash-bound route in the cached packet.
                code, payload = call(
                    af.command_execute_stage,
                    run_id=run_id,
                    route=None,
                    canary=False,
                )

        self.assertEqual(code, af.EXIT_OK, payload)
        self.assertTrue(payload["model_call"]["canary_execution"])
        self.assertEqual(payload["model_call"]["packet_sha256"], af.sha256_path(refreshed_path))
        invoked_route, invoked_packet_path, invoked_packet = invoked.call_args.args
        self.assertEqual(invoked_route["model"], "canary-model")
        self.assertEqual(invoked_packet_path, refreshed_path)
        self.assertEqual(invoked_packet["selected_route"]["chosen"]["model"], "canary-model")
        _, final_run = af.load_run(run_id)
        receipt_item = next(
            item for item in final_run["artifact_index"]
            if item["type"] == f"model-call:RESEARCH_PLAN:{refreshed['attempt']}"
        )
        stored_receipt = af.load_json(directory / receipt_item["path"])
        self.assertTrue(stored_receipt["canary_execution"])
        self.assertEqual(stored_receipt["packet_sha256"], af.sha256_path(refreshed_path))


class VoiceLearningTests(TemporaryRuntime):
    def voice_probe(self, run_id, draft_path, ledger_path, selection="B"):
        source = "The observable result is a page whose revision can be checked."
        passages = {
            "A": "The result is visible, and its revision is inspectable.",
            "B": "You can see the result and verify the exact revision yourself.",
            "C": "A visible page matters because its revision can be independently checked.",
        }
        return {
            "voice_probe_schema_version": "2.0.0",
            "run_id": run_id,
            "rough_draft_sha256": af.sha256_path(draft_path),
            "claim_ledger_sha256": af.sha256_path(ledger_path),
            "source_anchor": {
                "locator": "paragraph:1",
                "source_passage": source,
                "source_passage_sha256": af.sha256_bytes(source.encode("utf-8")),
            },
            "article_register": {"technical_depth": "moderate", "warmth": "direct"},
            "candidates": [
                {
                    "candidate_id": candidate_id,
                    "passage": passage,
                    "passage_sha256": af.sha256_bytes(passage.encode("utf-8")),
                    "intended_dimensions": [dimension],
                    "preserved_claim_ids": [],
                }
                for candidate_id, passage, dimension in (
                    ("A", passages["A"], "precision"),
                    ("B", passages["B"], "directness"),
                    ("C", passages["C"], "skepticism"),
                )
            ],
            "comparison_orders": [["A", "B", "C"], ["C", "B", "A"]],
            "held_out_plan": "Retest directness on a different article form.",
            "operator_selection": None if selection is None else {
                "candidate_id": selection,
                "selected_at": af.utc_now(),
                "feedback": None,
            },
        }

    def prepare_voice_choice(self, selection=None):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        source = "The observable result is a page whose revision can be checked."
        draft_path = self.record_text(directory, run, "draft", f"# Test\n\n{source}\n", "voice-draft.md")
        ledger = {
            "claim_ledger_schema_version": "1.0.0",
            "run_id": run_id,
            "generated_at": af.utc_now(),
            "claims": [],
        }
        ledger_path = self.record_json(directory, run, "verified-claim-ledger", ledger, "voice-ledger.json")
        probe = self.voice_probe(run_id, draft_path, ledger_path, selection=selection)
        probe_path = self.record_json(directory, run, "voice-probe", probe, "voice-probe-v2.json")
        af.transition(directory, run, "VOICE_PROBE", "test", "exercise the sole human voice gate")
        return run_id, directory, run, probe_path, probe

    def test_model_authored_probe_must_leave_operator_selection_null(self):
        _, directory, run, probe_path, probe = self.prepare_voice_choice(selection="B")
        outcome, findings = af.automatic_gate(directory, run, "VOICE_PROBE", probe_path)
        self.assertEqual(outcome, "REPAIR")
        self.assertTrue(any(item["criterion"] == "operator_selection_authority" for item in findings))

        probe["operator_selection"] = None
        af.write_json(probe_path, probe)
        outcome, findings = af.automatic_gate(directory, run, "VOICE_PROBE", probe_path)
        self.assertEqual(outcome, "PASS", findings)

    def test_voice_choice_rejects_external_and_tampered_probe_artifacts(self):
        run_id, directory, _, probe_path, probe = self.prepare_voice_choice()
        external = self.root / "unrecorded-probe.json"
        af.write_json(external, probe)
        gate_args = {
            "run_id": run_id,
            "gate_id": "G-VOICE-PROBE",
            "outcome": "PASS",
            "finding": None,
            "selection": "B",
            "feedback": None,
        }
        with self.assertRaises(af.FlowError) as external_error:
            af.command_gate(namespace(**gate_args, artifact=str(external)))
        self.assertEqual(external_error.exception.code, af.EXIT_APPROVAL)

        probe["held_out_plan"] += " This change is not recorded."
        af.write_json(probe_path, probe)
        with self.assertRaises(af.FlowError) as tamper_error:
            af.command_gate(namespace(**gate_args, artifact=None))
        self.assertEqual(tamper_error.exception.code, af.EXIT_INTEGRITY)
        _, current = af.load_run(run_id)
        self.assertEqual(current["state"], "VOICE_PROBE")
        selection_events = [
            event for event in af._read_jsonl(directory / "events.jsonl")
            if event.get("type") == "VOICE_SELECTION_RECORDED"
        ]
        self.assertEqual(selection_events, [])

    def test_concurrent_second_voice_choice_is_rejected_as_stale(self):
        run_id, directory, _, _, _ = self.prepare_voice_choice()
        real_load = af.load_run
        rendezvous = threading.Barrier(2)
        first_done = threading.Event()
        local = threading.local()

        def coordinated_load(target_run_id):
            loaded = real_load(target_run_id)
            count = getattr(local, "load_count", 0) + 1
            local.load_count = count
            if count == 1:
                rendezvous.wait(timeout=5)
                if local.role == "second":
                    self.assertTrue(first_done.wait(timeout=5))
            return loaded

        def decide(role):
            local.role = role
            local.load_count = 0
            try:
                return af.command_gate(namespace(
                    run_id=run_id,
                    gate_id="G-VOICE-PROBE",
                    outcome="PASS",
                    finding=None,
                    artifact=None,
                    selection="B",
                    feedback=None,
                ))
            except af.FlowError as exc:
                return exc
            finally:
                if role == "first":
                    first_done.set()

        with (
            mock.patch.object(af, "load_run", side_effect=coordinated_load),
            mock.patch.object(af, "emit"),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            futures = [pool.submit(decide, role) for role in ("first", "second")]
            results = [future.result(timeout=10) for future in futures]

        self.assertEqual(results[0], af.EXIT_OK)
        self.assertIsInstance(results[1], af.FlowError)
        self.assertEqual(results[1].code, af.EXIT_WAITING)
        self.assertIn("changed concurrently", str(results[1]))
        _, current = af.load_run(run_id)
        self.assertEqual(current["state"], "VOICE_LEARNING")
        selection_events = [
            event for event in af._read_jsonl(directory / "events.jsonl")
            if event.get("type") == "VOICE_SELECTION_RECORDED"
        ]
        self.assertEqual(len(selection_events), 1)

    def test_selection_learning_is_immediate_idempotent_and_rollback_preserves_evidence(self):
        baseline_path = SPEC_ROOT / "profiles" / "voice-profile.v1.json"
        baseline_hash = af.sha256_path(baseline_path)
        baseline_version = json.loads(baseline_path.read_text(encoding="utf-8"))["version"]
        run_id = self.start()
        directory, run = af.load_run(run_id)
        source = "The observable result is a page whose revision can be checked."
        draft_path = self.record_text(directory, run, "draft", f"# Test\n\n{source}\n", "voice-draft.md")
        ledger = {
            "claim_ledger_schema_version": "1.0.0",
            "run_id": run_id,
            "generated_at": af.utc_now(),
            "claims": [],
        }
        ledger_path = self.record_json(directory, run, "verified-claim-ledger", ledger, "voice-ledger.json")
        probe = self.voice_probe(run_id, draft_path, ledger_path)
        self.record_json(directory, run, "voice-probe", probe, "voice-probe-v2.json")
        af.transition(directory, run, "VOICE_LEARNING", "test", "exercise idempotent voice learning")

        first = af.apply_voice_learning(directory, run)
        directory, replay_run = af.load_run(run_id)
        af.transition(directory, replay_run, "VOICE_LEARNING", "test", "replay after a simulated crash")
        second = af.apply_voice_learning(directory, replay_run)
        first_record = first["learning"]
        second_record = second["learning"]
        history = af.voice_history()
        self.assertEqual(first_record["record_id"], second_record["record_id"])
        self.assertEqual(first_record["new_profile_version"], second_record["new_profile_version"])
        self.assertEqual(history["evidence_count"], 1)
        self.assertEqual(history["current_version"], first_record["new_profile_version"])
        self.assertEqual(len(history["profiles"]), 2)

        profile, _, pointer = af.active_voice_profile()
        profile_text = json.dumps(profile, ensure_ascii=False)
        for passage in (item["passage"] for item in probe["candidates"]):
            self.assertIn(passage, profile_text)
        self.assertEqual(pointer["current_version"], first_record["new_profile_version"])
        self.assertEqual(af.sha256_path(baseline_path), baseline_hash)

        rollback = af.rollback_voice_profile(baseline_version)
        after = af.voice_history()
        self.assertEqual(rollback["current_version"], baseline_version)
        self.assertEqual(after["current_version"], baseline_version)
        self.assertEqual(after["evidence_count"], 1)
        self.assertEqual(len(after["profiles"]), 2)


class NoPublishAutomationTests(TemporaryRuntime):
    def route_set(self, stage):
        if stage in af.V3_WRITING_STATES:
            candidates = [
                {
                    "provider": "codex-cli",
                    "model": model,
                    "model_version": "test",
                    "eligible": True,
                    "exclusion_reason": None,
                    "capability_assumptions": [],
                    "evaluation_score": None,
                    "kind": "codex-cli",
                    "privacy": "test",
                    "locality": "local",
                    "cost_class": "test",
                    "latency_class": "test",
                    "canary_status": "passed",
                }
                for model in MODEL_POOL
            ]
            return {
                "stage": stage,
                "required_capabilities": sorted(af.STAGE_CAPABILITIES.get(stage, set())),
                "candidates": candidates,
                "chosen": candidates[0],
                "fallbacks": candidates[1:],
                "reason": "fixture-backed writing route",
                "configuration_path": "test",
            }
        chosen = {
            "provider": "fixture",
            "model": "fixture-model",
            "model_version": "test",
            "eligible": True,
            "exclusion_reason": None,
            "capability_assumptions": [],
            "evaluation_score": None,
            "kind": "command",
            "privacy": "test",
            "locality": "local",
            "cost_class": "test",
            "latency_class": "test",
            "canary_status": "passed",
        }
        return {
            "stage": stage,
            "required_capabilities": sorted(af.STAGE_CAPABILITIES.get(stage, set())),
            "candidates": [chosen],
            "chosen": chosen,
            "fallbacks": [],
            "reason": "fixture-backed model route",
            "configuration_path": "test",
        }

    def stage_value(self, state, directory, run):
        run_id = run["run_id"]
        ledger = {
            "claim_ledger_schema_version": "1.0.0",
            "run_id": run_id,
            "generated_at": af.utc_now(),
            "claims": [],
        }
        if state == "RESEARCH_PLAN":
            return {
                "research_plan_schema_version": "1.0.0",
                "run_id": run_id,
                "questions": [{
                    "question": "What does the local workflow prove?",
                    "why_it_matters": "It bounds the article.",
                    "intent_changing": True,
                }],
                "source_strategy": ["Use repository evidence and direct primary documentation."],
                "claim_risks": [],
                "no_search_behavior": "not-applicable",
            }
        if state in {"RESEARCH", "CLAIM_VERIFICATION", "POST_EDIT_CLAIM_VERIFICATION"}:
            return ledger
        if state == "INTENT_REVIEW":
            return {
                "intent_schema_version": "1.0.0",
                "run_id": run_id,
                "reader": "A person evaluating a repeatable article workflow",
                "reader_job": "Understand the observable proof boundary",
                "purpose": "Show how one human voice choice guides the finished article",
                "scope": "The local Article Flow test",
                "position": None,
                "explicit_seed_content": ["Article Flow voice loop"],
                "assumptions": [],
                "remaining_unknowns": [],
                "research_that_shaped_candidate": [],
            }
        if state == "ARTICLE_RECIPE":
            return {
                "recipe_version": "1.0.0",
                "status": "candidate",
                "archetype": "field-note",
                "reader_job": "Understand the observable proof boundary",
                "scope_boundary": "The local test, not a provider comparison",
                "length": {
                    "mode": "brief",
                    "target_words": {"minimum": 500, "maximum": 900},
                    "stop_when": "The reader can explain the check.",
                },
                "opening": {"strategy": "artifact", "reason": "The result is inspectable."},
                "ending": {"strategy": "decision-rule", "reason": "The reader needs a reusable rule."},
                "summary": {"policy": "never", "form": None},
                "narrative_person": "mixed",
                "evidence_posture": "documentary",
                "citation_mode": "links",
                "components": {
                    "diagram": "off",
                    "checklist": "optional",
                    "mental_models": "off",
                    "workflow_count": None,
                    "activation_header": "off",
                },
                "outline_candidates": [{"id": "artifact-first"}, {"id": "failure-first"}],
                "selection_reason": "Artifact-first matches the available evidence.",
                "recent_post_comparison": {"observed": [], "unknowns": ["prior metadata unavailable"]},
                "variation_budget": {
                    "macro_dimensions": ["archetype", "opening"],
                    "recent_post_comparison": True,
                    "experiment_seed": "v3-no-publish",
                },
            }
        if state == "BRIEF":
            return {
                "brief_schema_version": "1.0.0",
                "run_id": run_id,
                "title": "The Voice Choice Is the Gate",
                "slug": "the-voice-choice-is-the-gate-v3-test",
                "description": "A bounded test of an automated article workflow.",
                "date": "2026-09-01",
                "tags": ["workflow"],
                "reader_job": "Understand the observable proof boundary",
                "scope": "One local no-publish run",
                "exclusions": ["provider rankings"],
                "claims_to_support": [],
                "acceptance_criteria": ["The no-publish run reaches completion after one voice choice."],
            }
        if state in {"DRAFT", "EDIT"}:
            return (
                "# The Voice Choice Is the Gate\n\n"
                "The page is visible. Its recorded revision identifies the exact result.\n\n"
                "## What the check proves\n\n"
                "A private receipt can support a public result without exposing private run data.\n"
            )
        if state == "VOICE_PROBE":
            draft_path = af.artifact_path(directory, run, "draft")
            ledger_path = af.artifact_path(directory, run, "verified-claim-ledger")
            source = "The page is visible. Its recorded revision identifies the exact result."
            passages = [
                ("A", "The page is visible, and its recorded revision identifies the result.", "precision"),
                ("B", "You can inspect the page and verify the exact recorded revision.", "directness"),
                ("C", "A visible page only proves something when its recorded revision matches.", "skepticism"),
            ]
            return {
                "voice_probe_schema_version": "2.0.0",
                "run_id": run_id,
                "rough_draft_sha256": af.sha256_path(draft_path),
                "claim_ledger_sha256": af.sha256_path(ledger_path),
                "source_anchor": {
                    "locator": "paragraph:1",
                    "source_passage": source,
                    "source_passage_sha256": af.sha256_bytes(source.encode("utf-8")),
                },
                "article_register": {"technical_depth": "moderate"},
                "candidates": [{
                    "candidate_id": candidate_id,
                    "passage": passage,
                    "passage_sha256": af.sha256_bytes(passage.encode("utf-8")),
                    "intended_dimensions": [dimension],
                    "preserved_claim_ids": [],
                } for candidate_id, passage, dimension in passages],
                "comparison_orders": [["A", "B", "C"], ["C", "B", "A"]],
                "held_out_plan": "Retest the selected trait on a different article form.",
                "operator_selection": None,
            }
        if state == "EDITORIAL_QA":
            dimensions = {
                key: {}
                for key in (
                    "intent_fidelity",
                    "clarity_utility",
                    "voice_fit",
                    "naturalness",
                    "public_surface_voice",
                    "structural_interest",
                    "proportional_length",
                )
            }
            return {
                "editorial_assessment_schema_version": "1.0.0",
                "run_id": run_id,
                "outcome": "PASS",
                "dimensions": dimensions,
                "findings": [],
                "calibration_status": "uncalibrated-advisory",
            }
        raise AssertionError(f"No fixture output for {state}")

    def execute_fixture_stage(self, args):
        directory, run = af.load_run(args.run_id)
        packet_path, packet = af.current_packet(directory, run)
        output_path = Path(packet["expected_outputs"][0]["path"])
        value = self.stage_value(run["state"], directory, run)
        if isinstance(value, dict):
            af.write_json(output_path, value)
        else:
            af.atomic_write(output_path, value.encode("utf-8"))
        route = packet["selected_route"]["chosen"]
        receipt = {
            "model_call_receipt_schema_version": "1.0.0",
            "run_id": run["run_id"],
            "stage": run["state"],
            "attempt": packet["attempt"],
            "packet_sha256": af.sha256_path(packet_path),
            "output_sha256": af.sha256_path(output_path),
            "selection_reason": packet["selected_route"]["reason"],
            "route": {
                "provider": route["provider"],
                "model": route["model"],
                "model_version": route.get("model_version"),
                "elapsed_ms": 1,
                "transport": {"kind": "fixture"},
            },
            "canary_execution": False,
            "created_at": af.utc_now(),
        }
        receipt_path = directory / "receipts" / f"fixture-{run['state'].lower()}.json"
        af.write_json(receipt_path, receipt)
        af.record_artifact(
            directory,
            run,
            receipt_path,
            f"model-call:{run['state']}:{packet['attempt']}",
            {"actor": "test"},
        )
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            return af.command_submit(namespace(run_id=run["run_id"], stage=run["state"], file=str(output_path)))

    def test_no_publish_advance_has_one_human_gate_then_completes(self):
        run_id = self.start()
        recorded_states = []
        real_record_outcome = af.record_experiment_outcome

        def record_before_completion(directory, run):
            recorded_states.append(run["state"])
            return real_record_outcome(directory, run)

        def fixture_routes(stage, excluded_routes=None):
            return self.route_set(stage)

        with (
            mock.patch.object(af, "route_candidates", side_effect=fixture_routes),
            mock.patch.object(af, "command_execute_stage", side_effect=self.execute_fixture_stage),
            mock.patch.object(
                af,
                "command_publish_execute",
                side_effect=AssertionError("no-publish automation invoked the real publisher"),
            ) as real_publish,
            mock.patch.object(af, "record_experiment_outcome", side_effect=record_before_completion),
        ):
            code, waiting = call(af.command_advance, run_id=run_id)
            self.assertEqual(code, af.EXIT_WAITING, waiting)
            self.assertEqual(waiting["action"], "human_decision")
            self.assertEqual(waiting["state"], "VOICE_PROBE")
            self.assertEqual(len(waiting["candidates"]), 3)

            code, chosen = call(
                af.command_choose_voice,
                run_id=run_id,
                candidate_id="B",
                feedback=None,
                auto=False,
            )
            self.assertEqual(code, af.EXIT_OK, chosen)
            try:
                code, completed = call(af.command_advance, run_id=run_id)
            except af.FlowError as exc:
                self.fail(f"advance raised {exc}: {exc.details}")
            self.assertEqual(code, af.EXIT_OK, completed)

        real_publish.assert_not_called()
        self.assertEqual(recorded_states, ["LIVE_VERIFICATION"])
        _, run = af.load_run(run_id)
        self.assertEqual(run["state"], "COMPLETE")
        decisions = [
            event
            for event in af._read_jsonl(af.run_dir(run_id) / "events.jsonl")
            if event.get("type") == "VOICE_SELECTION_RECORDED"
        ]
        self.assertEqual(len(decisions), 1)
        artifact_types = {item["type"] for item in run["artifact_index"]}
        self.assertIn("publication", artifact_types)
        self.assertIn("live-verification", artifact_types)


class StyleDefenseTests(TemporaryRuntime):
    def make_package(self, *, title="Root Relative Test", description="A direct test of packaged links."):
        package_root = self.root / "package"
        public_root = package_root / "public"
        site_root = package_root / "site"
        docs_root = site_root / "docs"
        public_root.mkdir(parents=True)
        docs_root.mkdir(parents=True)
        metadata = {
            "slug": "root-relative-test",
            "title": title,
            "description": description,
        }
        (public_root / "article.md").write_text(f"# {title}\n", encoding="utf-8")
        for name in ("metadata.json", "references.json", "assets.json"):
            (public_root / name).write_text("{}\n", encoding="utf-8")
        (site_root / "styles.css").write_text("body {}\n", encoding="utf-8")
        (docs_root / "blog.html").write_text("<html></html>\n", encoding="utf-8")
        (site_root / "index.html").write_text("<html></html>\n", encoding="utf-8")
        (site_root / "feed.xml").write_text("<rss></rss>\n", encoding="utf-8")
        (site_root / "sitemap.xml").write_text("<urlset></urlset>\n", encoding="utf-8")
        canonical = json.loads(
            (SPEC_ROOT / "publication" / "theproductiveprompter.json").read_text(encoding="utf-8")
        )["canonical_url"].format(slug=metadata["slug"])
        article = (
            "<html><head>"
            f"<title>{html.escape(metadata['title'])}</title>"
            f'<link rel="canonical" href="{canonical}">'
            '<meta name="article-flow-revision" content="abc">'
            '<script type="application/ld+json">{"@type": "BlogPosting"}</script>'
            '<link rel="stylesheet" href="/styles.css">'
            "</head><body></body></html>"
        )
        (docs_root / f"{metadata['slug']}.html").write_text(article, encoding="utf-8")
        return package_root, metadata

    def test_cliches_are_normalized_but_code_urls_and_attributed_quotes_are_ignored(self):
        prose = "At\n\nits   CORE, this is the same claim."
        findings = af.style_phrase_findings(prose)
        self.assertTrue(any("at its core" in item["finding"].casefold() for item in findings))

        exempt = (
            "`at its core`\n\n"
            "https://example.com/at-its-core\n\n"
            '> Ada wrote, "At its core, the check is deliberately small."\n'
        )
        self.assertEqual(af.style_phrase_findings(exempt), [])
        self.assertEqual(
            af.style_phrase_findings('"At its core, the check is deliberately small," Ada wrote.'),
            [],
        )
        unattributed = af.style_phrase_findings("> At its core, the check is deliberately small.\n")
        self.assertTrue(any("at its core" in item["finding"].casefold() for item in unattributed))

    def test_literal_and_encoded_em_dashes_are_rejected(self):
        for value in ("one\u2014two", "one&mdash;two", "one&#8212;two", "one&#x2014;two"):
            with self.subTest(value=value):
                findings = af.forbidden_public_prose_character_findings(value)
                self.assertTrue(findings)
                self.assertTrue(any(item["criterion"] == "forbidden_public_prose_character" for item in findings))

    def test_root_relative_article_links_resolve_from_the_site_root(self):
        package_root, metadata = self.make_package()
        with mock.patch.object(af, "publication_repo_root", return_value=self.root / "repository"):
            findings = af.validate_public_package(package_root, metadata)
        broken_links = [item for item in findings if item["criterion"] == "internal_link_or_asset"]
        self.assertEqual(broken_links, [], findings)

    def test_traversal_link_cannot_escape_the_publication_repository(self):
        package_root, metadata = self.make_package()
        repository = self.root / "repository"
        (repository / "docs").mkdir(parents=True)
        outside = self.root / "outside-repository.txt"
        outside.write_text("A real file outside the publication repository.\n", encoding="utf-8")
        traversal = os.path.relpath(outside, repository / "docs").replace(os.sep, "/")
        article_path = package_root / "site" / "docs" / f"{metadata['slug']}.html"
        article = article_path.read_text(encoding="utf-8").replace(
            "</body>",
            f'<a href="{traversal}">outside</a></body>',
        )
        article_path.write_text(article, encoding="utf-8")

        with mock.patch.object(af, "publication_repo_root", return_value=repository):
            findings = af.validate_public_package(package_root, metadata)
        broken_links = [item for item in findings if item["criterion"] == "internal_link_or_asset"]
        self.assertTrue(any(traversal in item["finding"] for item in broken_links), findings)

    def test_public_package_scans_article_metadata_rendered_cards_and_feed(self):
        phrase = "At its core, the phrase must be repaired."
        package_root, metadata = self.make_package(title=phrase, description=phrase)
        public_root = package_root / "public"
        site_root = package_root / "site"
        docs_root = site_root / "docs"
        (public_root / "article.md").write_text(f"# Test\n\n{phrase}\n", encoding="utf-8")
        article_path = docs_root / f"{metadata['slug']}.html"
        article_path.write_text(article_path.read_text(encoding="utf-8").replace("</body>", f"<p>{phrase}</p></body>"), encoding="utf-8")
        (docs_root / "blog.html").write_text(f"<html><body><p>{phrase}</p></body></html>\n", encoding="utf-8")
        (site_root / "index.html").write_text(f"<html><body><p>{phrase}</p></body></html>\n", encoding="utf-8")
        (site_root / "feed.xml").write_text(f"<rss><channel><description>{phrase}</description></channel></rss>\n", encoding="utf-8")

        with mock.patch.object(af, "publication_repo_root", return_value=self.root / "repository"):
            findings = af.validate_public_package(package_root, metadata)
        locations = json.dumps(
            [item for item in findings if "at its core" in json.dumps(item).casefold()],
            ensure_ascii=False,
        )
        for expected in (
            "metadata.title",
            "metadata.description",
            "article.md",
            "root-relative-test.html",
            "blog.html",
            "index.html",
            "feed.xml",
        ):
            self.assertIn(expected, locations, findings)


class SchemaAndCanaryRegressionTests(TemporaryRuntime):
    def test_custom_validator_enforces_provider_conditionals_and_boolean_false(self):
        def config(provider):
            return {
                "provider_config_schema_version": "1.0.0",
                "providers": [provider],
            }

        valid_codex = {
            "provider_id": "codex-cli",
            "kind": "codex-cli",
            "enabled": True,
            "models": [{"model_id": "gpt-5.6-sol"}],
        }
        self.assertEqual(af.validate_instance_schema(config(valid_codex), "provider-config.schema.json"), [])

        disallowed_codex_command = {**valid_codex, "command": ["codex"]}
        codex_errors = af.validate_instance_schema(config(disallowed_codex_command), "provider-config.schema.json")
        self.assertTrue(any("forbidden by the schema" in error for error in codex_errors), codex_errors)

        missing_command = {
            "provider_id": "fixture-command",
            "kind": "command",
            "enabled": True,
            "models": [{"model_id": "fixture-model"}],
        }
        command_errors = af.validate_instance_schema(config(missing_command), "provider-config.schema.json")
        self.assertTrue(any("required property 'command'" in error for error in command_errors), command_errors)
        self.assertEqual(af.validate_schema_value("allowed", True, {}), [])
        self.assertTrue(af.validate_schema_value("forbidden", False, {}))

    def test_missing_canary_is_ineligible_but_explicit_canary_packet_can_select_it(self):
        registry = {
            "registry_schema_version": "1.0.0",
            "workflow_version": "3.0.0",
            "configuration_path": "test-fixture",
            "providers": [{
                "provider_id": "fixture-command",
                "kind": "command",
                "enabled": True,
                "command": [sys.executable],
                "models": [{
                    "model_id": "missing-canary",
                    "version": "test",
                    "enabled": True,
                    "capabilities": ["structured-output"],
                    "stages": ["RESEARCH_PLAN"],
                }],
            }],
        }
        with (
            mock.patch.object(af, "capability_registry", return_value=registry),
            mock.patch.object(af, "promoted_evaluation_scores", return_value={}),
        ):
            routes = af.route_candidates("RESEARCH_PLAN")
            candidate = routes["candidates"][0]
            self.assertFalse(candidate["eligible"])
            self.assertEqual(candidate["canary_status"], "not-declared")
            self.assertIn("canary not-declared", candidate["exclusion_reason"])
            self.assertIsNone(routes["chosen"])

            run_id = self.start()
            directory, run = af.load_run(run_id)
            _, packet = af.task_packet(
                directory,
                run,
                requested_route="fixture-command:missing-canary",
                allow_canary=True,
            )

        chosen = packet["selected_route"]["chosen"]
        self.assertEqual((chosen["provider"], chosen["model"]), ("fixture-command", "missing-canary"))
        self.assertTrue(chosen["eligible"])
        self.assertTrue(chosen["canary_execution"])
        self.assertEqual(packet["selected_route"]["fallbacks"], [])

    def test_codex_passed_canary_declaration_without_matching_receipt_is_ineligible(self):
        registry = {
            "registry_schema_version": "1.0.0",
            "workflow_version": "3.0.0",
            "configuration_path": "test-fixture",
            "providers": [{
                "provider_id": "codex-cli",
                "kind": "codex-cli",
                "enabled": True,
                "executable": sys.executable,
                "models": [{
                    "model_id": "gpt-test-with-unsupported-pass-claim",
                    "version": "test",
                    "enabled": True,
                    "capabilities": ["structured-output"],
                    "stages": ["RESEARCH_PLAN"],
                    "canary_status": "passed",
                    "canary_receipt_sha256": "f" * 64,
                }],
            }],
        }
        with (
            mock.patch.object(af, "capability_registry", return_value=registry),
            mock.patch.object(af, "promoted_evaluation_scores", return_value={}),
        ):
            routes = af.route_candidates("RESEARCH_PLAN")

        candidate = routes["candidates"][0]
        self.assertEqual(candidate["canary_status"], "invalid-evidence")
        self.assertFalse(candidate["eligible"])
        self.assertIn("canary invalid-evidence", candidate["exclusion_reason"])
        self.assertIsNone(routes["chosen"])


if __name__ == "__main__":
    unittest.main()
