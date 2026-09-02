from __future__ import annotations

import argparse
import builtins
import contextlib
import html
import io
import json
import os
import re
import subprocess
import symtable
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
        self.assertEqual(parser.parse_args(["regenerate-voice", "AF-TEST", "--feedback", "Too formal."]).command, "regenerate-voice")
        self.assertEqual(parser.parse_args(["revise", "AF-TEST", "--request-file", "repair.md"]).command, "revise")

    def test_v3_order_has_one_normal_human_gate_and_bundles_v2(self):
        current = json.loads((SPEC_ROOT / "workflow" / "workflow.json").read_text(encoding="utf-8"))
        legacy = json.loads((SPEC_ROOT / "workflow" / "workflow.v2.0.0.json").read_text(encoding="utf-8"))
        archived_v3 = json.loads((SPEC_ROOT / "workflow" / "workflow.v3.0.0.json").read_text(encoding="utf-8"))
        self.assertEqual(current["workflow_version"], "3.1.0")
        self.assertEqual(archived_v3["workflow_version"], "3.0.0")
        self.assertEqual(legacy["workflow_version"], "2.0.0")

        states = {item["id"]: item for item in current["states"]}
        self.assertEqual(states["DRAFT"]["next_on_pass"], "VISUAL_PLAN")
        self.assertEqual(states["VISUAL_PLAN"]["next_on_pass"], "VISUAL_RENDER")
        self.assertEqual(states["VISUAL_RENDER"]["next_on_pass"], "CLAIM_VERIFICATION")
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

    def post_edit_repair_run(self, label):
        run_id = self.start(label)
        directory, run = af.load_run(run_id)
        for artifact_type in ("verified-claim-ledger", "article-recipe", "voice-learning", "voice-profile", "locked-fields"):
            if not af.artifact(run, artifact_type):
                self.record_json(directory, run, artifact_type, {"fixture": artifact_type})
        for artifact_type in ("article", "draft", "naturalization-directive"):
            if not af.artifact(run, artifact_type):
                self.record_text(directory, run, artifact_type, f"{artifact_type} fixture\n")
        run.setdefault("model_experiment", {}).update({
            "provider_id": "fixture",
            "assigned_model_id": "fixture-model",
            "active_model_id": "fixture-model",
        })
        af.transition(directory, run, "POST_EDIT_CLAIM_VERIFICATION", "test", "seed cross-stage repair context")
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            _, packet = af.task_packet(directory, run)
        output = Path(packet["expected_outputs"][0]["path"])
        af.write_json(output, {"attempt": packet["attempt"]})
        with (
            mock.patch.object(af, "automatic_gate", return_value=("REPAIR", [self.finding(packet["attempt"])])),
            mock.patch.object(af, "emit"),
        ):
            self.assertEqual(
                af.command_submit(namespace(
                    run_id=run_id,
                    stage="POST_EDIT_CLAIM_VERIFICATION",
                    file=str(output),
                )),
                af.EXIT_OK,
            )
        directory, run = af.load_run(run_id)
        self.assertEqual(run["state"], "EDIT")
        self.assertEqual(run["pending_repair"]["source_stage"], "POST_EDIT_CLAIM_VERIFICATION")
        return run_id, directory, run, json.loads(json.dumps(run["pending_repair"]))

    @staticmethod
    def finding(number):
        return {
            "criterion": "claim_disposition",
            "artifact": "claim-ledger",
            "location": f"claim:CL-{number:03d}",
            "finding": f"Claim CL-{number:03d} still needs a disposition.",
            "repair_instruction": "Mark the claim supported, qualified, or omitted with evidence.",
        }

    def test_packet_crash_windows_roll_forward_without_overwriting_evidence(self):
        # ARTIFACT_RECORDED is durable but run.json was not saved.
        run_id = self.start("Recover a packet artifact event before dispatch.")
        directory, run = af.load_run(run_id)
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            with mock.patch.object(af, "save_run", side_effect=RuntimeError("crash after artifact event")):
                with self.assertRaisesRegex(RuntimeError, "artifact event"):
                    af.task_packet(directory, run)
            first_path = directory / "tasks" / "research_plan-01.json"
            first_hash = af.sha256_path(first_path)
            recovered_directory, recovered = af.load_run(run_id)
            self.assertTrue(any(item["type"] == "task-packet:RESEARCH_PLAN:1" for item in recovered["artifact_index"]))
            self.assertEqual(recovered["status"], "ACTIVE")
            second_path, second = af.task_packet(recovered_directory, recovered)
        self.assertEqual(second["attempt"], 2)
        self.assertEqual(af.sha256_path(first_path), first_hash)
        self.assertNotEqual(second_path, first_path)

        # TASK_DISPATCHED is durable but its final cache save was interrupted.
        run_id = self.start("Recover a dispatch event before its cache save.")
        directory, run = af.load_run(run_id)
        real_save = af.save_run
        saves = 0

        def crash_on_final_save(save_directory, save_run):
            nonlocal saves
            saves += 1
            if saves == 2:
                raise RuntimeError("crash after dispatch event")
            return real_save(save_directory, save_run)

        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            with mock.patch.object(af, "save_run", side_effect=crash_on_final_save):
                with self.assertRaisesRegex(RuntimeError, "dispatch event"):
                    af.task_packet(directory, run)
            recovered_directory, recovered = af.load_run(run_id)
            self.assertEqual(recovered["status"], "WAITING_MODEL")
            self.assertEqual(recovered["attempts"]["RESEARCH_PLAN"], 1)
            packet_path, packet = af.current_packet(recovered_directory, recovered)
        self.assertEqual(packet["attempt"], 1)
        self.assertEqual(packet_path.name, "research_plan-01.json")

        # STATE_TRANSITION is the state authority even if run.json stayed stale.
        run_id = self.start("Recover a transition event before its cache save.")
        directory, run = af.load_run(run_id)
        with mock.patch.object(af, "save_run", side_effect=RuntimeError("crash after transition event")):
            with self.assertRaisesRegex(RuntimeError, "transition event"):
                af.transition(directory, run, "RESEARCH", "test", "exercise WAL recovery")
        _, recovered = af.load_run(run_id)
        self.assertEqual(recovered["state"], "RESEARCH")
        self.assertEqual(recovered["status"], "ACTIVE")

    def test_tampered_packet_blocks_and_never_mints_a_replacement(self):
        run_id = self.start("A recorded packet must remain hash-bound.")
        directory, run = af.load_run(run_id)
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            packet_path, _ = af.task_packet(directory, run)
        packet_path.write_bytes(packet_path.read_bytes() + b" ")
        directory, run = af.load_run(run_id)
        with self.assertRaises(af.FlowError) as caught:
            af.current_packet(directory, run)
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        self.assertEqual(af.load_json(directory / "run.json")["status"], "BLOCKED")
        self.assertFalse((directory / "tasks" / "research_plan-02.json").exists())

    def test_durable_model_receipt_resumes_submit_without_provider_reinvocation(self):
        run_id, directory = self.research_run()
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            packet_path, packet = af.task_packet(directory, af.load_run(run_id)[1])
        output_path = Path(packet["expected_outputs"][0]["path"])
        af.write_json(output_path, {"attempt": 1, "durable": True})
        route = packet["selected_route"]["chosen"]
        receipt = {
            "model_call_receipt_schema_version": "1.0.0",
            "run_id": run_id,
            "stage": "RESEARCH",
            "attempt": 1,
            "packet_sha256": af.sha256_path(packet_path),
            "output_sha256": af.sha256_path(output_path),
            "selection_reason": "durable crash fixture",
            "route": {"provider": route["provider"], "model": route["model"]},
            "canary_execution": False,
            "created_at": af.utc_now(),
        }
        receipt_path = directory / "receipts" / "model-call-research-01.json"
        af.write_json(receipt_path, receipt)
        _, run = af.load_run(run_id)
        with mock.patch.object(af, "save_run", side_effect=RuntimeError("crash after model receipt event")):
            with self.assertRaisesRegex(RuntimeError, "model receipt event"):
                af.record_artifact(directory, run, receipt_path, "model-call:RESEARCH:1", {"actor": "test"})
        _, recovered = af.load_run(run_id)
        self.assertTrue(any(item["type"] == "model-call:RESEARCH:1" for item in recovered["artifact_index"]))
        output_hash = af.sha256_path(output_path)
        receipt_hash = af.sha256_path(receipt_path)

        def submit_in_process(command, **_kwargs):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = af.command_submit(namespace(run_id=run_id, stage="RESEARCH", file=str(output_path)))
            return subprocess.CompletedProcess(command, code, stream.getvalue(), "")

        with mock.patch.object(af, "invoke_route", side_effect=AssertionError("provider was reinvoked")) as invoke:
            with self.assertRaises(af.FlowError) as changed_route:
                af.command_execute_stage(namespace(run_id=run_id, route="fixture:different-model", canary=False))
        self.assertEqual(changed_route.exception.code, af.EXIT_INTEGRITY)
        invoke.assert_not_called()

        with (
            mock.patch.object(af, "invoke_route", side_effect=AssertionError("provider was reinvoked")) as invoke,
            mock.patch.object(af, "automatic_gate", return_value=("PASS", [])),
            mock.patch.object(af.subprocess, "run", side_effect=submit_in_process),
        ):
            code, payload = call(af.command_execute_stage, run_id=run_id)
        self.assertEqual(code, af.EXIT_OK, payload)
        self.assertTrue(payload["resumed_recorded_model_call"])
        invoke.assert_not_called()
        self.assertEqual(af.sha256_path(output_path), output_hash)
        self.assertEqual(af.sha256_path(receipt_path), receipt_hash)

    def test_committed_gate_receipt_before_gate_event_blocks_replay(self):
        run_id, directory = self.research_run()
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            packet_path, packet = af.task_packet(directory, af.load_run(run_id)[1])
        _, run = af.load_run(run_id)
        real_append = af.append_event

        def crash_before_gate_event(event_directory, event_run, event_type, actor, payload):
            if event_type == "GATE_RECORDED":
                raise RuntimeError("crash before gate event")
            return real_append(event_directory, event_run, event_type, actor, payload)

        with mock.patch.object(af, "append_event", side_effect=crash_before_gate_event):
            with self.assertRaisesRegex(RuntimeError, "before gate event"):
                af.write_gate_receipt(
                    directory,
                    run,
                    "G-EVIDENCE-COVERAGE",
                    "REPAIR",
                    [self.finding(1)],
                    {"type": "code", "version": "test"},
                    "RESEARCH",
                    task_state="RESEARCH",
                    task_attempt=1,
                    task_packet_sha256=af.sha256_path(packet_path),
                )
        receipt_path = next((directory / "receipts").glob("g-evidence-coverage-*.json"))
        receipt_hash = af.sha256_path(receipt_path)
        directory, recovered = af.load_run(run_id)
        with self.assertRaises(af.FlowError) as caught:
            af.current_packet(directory, recovered)
        self.assertEqual(caught.exception.code, af.EXIT_WAITING)
        self.assertEqual(af.load_json(directory / "run.json")["status"], "BLOCKED")
        self.assertEqual(af.sha256_path(receipt_path), receipt_hash)
        self.assertFalse((directory / "tasks" / "research-02.json").exists())

    def test_a_passing_gate_closes_the_stage_repair_window(self):
        """A stage that repairs elsewhere must not exhaust by succeeding.

        POST_EDIT_CLAIM_VERIFICATION and EDITORIAL_QA declare EDIT as their
        repair state, so a repair never advances their own baseline. Without
        closing the window on an accepted attempt they could execute only
        max_attempts times in an entire run, and escalated as
        attempt_window_exhausted with zero rejections once the article had been
        rewritten that many times.
        """
        run_id = self.start("A passing attempt must not consume the repair window.")
        directory, run = af.load_run(run_id)
        with mock.patch.object(
            af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)
        ):
            _, packet = af.task_packet(directory, af.load_run(run_id)[1])
        output = Path(packet["expected_outputs"][0]["path"])
        af.write_json(output, {"attempt": 1})

        with mock.patch.object(af, "automatic_gate", return_value=("PASS", [])):
            code, _ = call(af.command_submit, run_id=run_id, stage="RESEARCH_PLAN", file=str(output))
        self.assertEqual(code, af.EXIT_OK)

        directory, accepted = af.load_run(run_id)
        evidence = af.stage_attempt_evidence(directory, accepted, "RESEARCH_PLAN")
        self.assertEqual(evidence["window_used"], 0, evidence)
        self.assertEqual(evidence["rejection_count"], 0, evidence)
        self.assertEqual(
            accepted["attempt_baselines"]["RESEARCH_PLAN"], evidence["execution_count"], evidence
        )

        # Runs recorded before the window closed on a pass carry a stale
        # baseline, so the floor is derived from the settled gate as well.
        accepted["attempt_baselines"]["RESEARCH_PLAN"] = 0
        af.save_run(directory, accepted)
        directory, legacy = af.load_run(run_id)
        healed = af.stage_attempt_evidence(directory, legacy, "RESEARCH_PLAN")
        self.assertEqual(healed["window_used"], 0, healed)
        self.assertGreaterEqual(healed["window_baseline"], 1, healed)

    def test_an_integrity_block_is_never_cleared_by_a_reopened_window(self):
        """Only an exhausted-window stop may be lifted automatically."""
        run_id = self.start("An integrity block must survive a reopened window.")
        directory, run = af.load_run(run_id)
        af.append_event(directory, run, "ESCALATION", "controller", {
            "state": "RESEARCH_PLAN", "reason": "gate_receipt_evidence_changed_during_commit"})
        run["status"] = "BLOCKED"
        af.save_run(directory, run)
        directory, blocked = af.load_run(run_id)
        self.assertFalse(af.blocked_only_by_attempt_window(directory, blocked, "RESEARCH_PLAN"))

        # The same run stopped at its declared boundary may be lifted.
        af.append_event(directory, blocked, "ESCALATION", "controller", {
            "state": "RESEARCH_PLAN", "reason": "attempt_window_exhausted"})
        af.save_run(directory, blocked)
        directory, exhausted = af.load_run(run_id)
        self.assertTrue(af.blocked_only_by_attempt_window(directory, exhausted, "RESEARCH_PLAN"))
        # ...but only for the stage it actually names.
        self.assertFalse(af.blocked_only_by_attempt_window(directory, exhausted, "EDIT"))

    def test_every_controller_route_rejected_once_still_gets_the_next_attempt(self):
        """An agent-hosted fallback is not an alternative under automation.

        Each content rejection records a route failure. Once every capable
        model had one, excluding them all left only the active-host route,
        which execute-stage refuses to perform, so the stage stopped on a
        fallback that cannot run. A stage repairing to another stage never has
        its own route failures cleared either, so the stop was permanent.
        """
        run_id = self.start("Every controller route rejected once must still run.")
        directory, run = af.load_run(run_id)
        observed = []

        def route_fixture(stage, excluded_routes=None):
            observed.append(set(excluded_routes or set()))
            return self.route_set(stage)

        run.setdefault("route_failures", {})["RESEARCH_PLAN"] = {"fixture:fixture-model": 1}
        af.save_run(directory, run)
        directory, failed = af.load_run(run_id)
        with mock.patch.object(af, "route_candidates", side_effect=route_fixture):
            _, packet = af.task_packet(directory, failed)

        # The only controller route is reused rather than excluded.
        self.assertEqual(packet["selected_route"]["chosen"]["model"], "fixture-model")
        self.assertNotIn({"fixture:fixture-model"}, observed)

    def test_stale_external_and_duplicate_submissions_are_rejected_before_write(self):
        run_id, directory = self.research_run()
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            first_path, first_packet = af.task_packet(directory, af.load_run(run_id)[1])
        first_output = Path(first_packet["expected_outputs"][0]["path"])
        af.write_json(first_output, {"attempt": 1, "marker": "immutable-first"})
        with mock.patch.object(af, "automatic_gate", return_value=("REPAIR", [self.finding(1)])):
            code, _ = call(af.command_submit, run_id=run_id, stage="RESEARCH", file=str(first_output))
        self.assertEqual(code, af.EXIT_OK)
        accepted_first = directory / "artifacts" / "01-claim-ledger.json"
        first_hash = af.sha256_path(accepted_first)
        receipt_hashes = {path.name: af.sha256_path(path) for path in (directory / "receipts").glob("*.json")}

        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            _, second_packet = af.task_packet(directory, af.load_run(run_id)[1])
        second_output = Path(second_packet["expected_outputs"][0]["path"])
        af.write_json(second_output, {"attempt": 2, "marker": "current"})
        external = self.root / "external-current.json"
        external.write_bytes(second_output.read_bytes())

        with self.assertRaises(af.FlowError) as stale:
            af.command_submit(namespace(run_id=run_id, stage="RESEARCH", file=str(first_output)))
        self.assertEqual(stale.exception.code, af.EXIT_INTEGRITY)
        with self.assertRaises(af.FlowError) as outside:
            af.command_submit(namespace(run_id=run_id, stage="RESEARCH", file=str(external)))
        self.assertEqual(outside.exception.code, af.EXIT_INTEGRITY)
        self.assertEqual(af.sha256_path(accepted_first), first_hash)
        self.assertEqual(
            {path.name: af.sha256_path(path) for path in (directory / "receipts").glob("*.json")},
            receipt_hashes,
        )

    def test_repair_context_rejects_a_receipt_swapped_from_another_run(self):
        first_id, first_directory = self.research_run()
        _, first_run = af.load_run(first_id)
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            af.task_packet(first_directory, first_run)
        _, first_run = af.load_run(first_id)
        first_output = first_directory / "artifacts" / "first-rejected.json"
        af.write_json(first_output, {"run": "first"})
        af.record_artifact(first_directory, first_run, first_output, "claim-ledger", {"actor": "test"})
        definition = af.state_definition("RESEARCH", first_run)
        af.write_gate_receipt(
            first_directory,
            first_run,
            definition["gate"],
            "REPAIR",
            [self.finding(1)],
            {"type": "human", "identity": "operator"},
            definition["repair_state"],
        )
        af.remember_repair_context(first_directory, first_run, "RESEARCH", definition)
        af.save_run(first_directory, first_run)

        second_id, second_directory = self.research_run()
        _, second_run = af.load_run(second_id)
        second_output = second_directory / "artifacts" / "second-rejected.json"
        af.write_json(second_output, {"run": "second"})
        af.record_artifact(second_directory, second_run, second_output, "claim-ledger", {"actor": "test"})
        second_receipt = af.write_gate_receipt(
            second_directory,
            second_run,
            definition["gate"],
            "REPAIR",
            [self.finding(2)],
            {"type": "human", "identity": "operator"},
            definition["repair_state"],
        )
        swapped = first_directory / "receipts" / "swapped-other-run.json"
        swapped.write_bytes(second_receipt.read_bytes())
        _, first_run = af.load_run(first_id)
        first_run["pending_repair"]["gate_receipt"].update({
            "path": swapped.relative_to(first_directory).as_posix(),
            "sha256": af.sha256_path(swapped),
        })
        af.save_run(first_directory, first_run)
        with self.assertRaises(af.FlowError) as caught:
            af.repair_context_for_packet(first_directory, first_run, "RESEARCH")
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)

    def test_operator_empty_repair_is_valid_and_single_route_gets_both_executions(self):
        run_id = self.start("An operator can request a recipe repair without prose findings.")
        directory, run = af.load_run(run_id)
        self.record_json(directory, run, "intent", {"reader_job": "Understand the bounded workflow."})
        self.record_json(directory, run, "claim-ledger", {"claims": []})
        rejected = directory / "artifacts" / "manual-rejected-article-recipe.json"
        af.write_json(rejected, {"marker": "operator repair"})
        af.record_artifact(directory, run, rejected, "article-recipe", {"actor": "test"})
        af.transition(directory, run, "ARTICLE_RECIPE", "test", "exercise an empty operator repair")
        code, payload = call(
            af.command_gate,
            run_id=run_id,
            gate_id="G-RECIPE-FIT",
            outcome="REPAIR",
            finding=None,
            artifact=None,
        )
        self.assertEqual(code, af.EXIT_OK, payload)
        _, operator_run = af.load_run(run_id)
        operator_receipt = af.json_artifact(directory, operator_run, "gate-receipt:G-RECIPE-FIT")
        self.assertTrue(operator_receipt["findings"])
        self.assertEqual(operator_receipt["findings"][0]["criterion"], "operator_requested_repair")
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            _, repair_packet = af.task_packet(directory, af.load_run(run_id)[1])
        self.assertEqual(repair_packet["task_packet_schema_version"], "1.0.0")
        self.assertNotIn("repair_context", repair_packet)

        ordinary_run = self.start("One route still gets the full two-execution budget.")
        ordinary_directory, ordinary = af.load_run(ordinary_run)
        observed_exclusions = []

        def route_fixture(stage, excluded_routes=None):
            observed_exclusions.append(set(excluded_routes or set()))
            value = self.route_set(stage)
            if "fixture:fixture-model" in set(excluded_routes or set()):
                value["chosen"] = None
                value["fallbacks"] = []
            return value

        with mock.patch.object(af, "route_candidates", side_effect=route_fixture):
            _, first = af.task_packet(ordinary_directory, ordinary)
        first_output = Path(first["expected_outputs"][0]["path"])
        af.write_json(first_output, {"attempt": 1})
        with mock.patch.object(af, "automatic_gate", return_value=("REPAIR", [self.finding(1)])):
            code, _ = call(af.command_submit, run_id=ordinary_run, stage="RESEARCH_PLAN", file=str(first_output))
        self.assertEqual(code, af.EXIT_OK)
        with mock.patch.object(af, "route_candidates", side_effect=route_fixture):
            _, second = af.task_packet(ordinary_directory, af.load_run(ordinary_run)[1])
        self.assertEqual(second["attempt"], 2)
        self.assertEqual(second["selected_route"]["chosen"]["model"], "fixture-model")
        self.assertNotIn({"fixture:fixture-model"}, observed_exclusions)

        # Packet schema compatibility is explicit: old ordinary packets remain
        # strict 1.0, while repair context requires 1.1.
        ordinary_packet = json.loads(json.dumps(first))
        self.assertFalse(af.validate_instance_schema(ordinary_packet, "task-packet.schema.json"))
        ordinary_packet["repair_context"] = {
            "context_type": "targeted_gate_repair",
            "source_stage": "RESEARCH_PLAN",
            "repair_state": "RESEARCH_PLAN",
            "failed_attempt": 1,
            "maximum_attempts": 2,
            "rejected_output": {"input_id": "rejected", "artifact_type": "research-plan", "path": "/tmp/rejected", "sha256": "0" * 64},
            "gate_receipt": {"input_id": "gate", "gate_id": "G-RESEARCH-PLAN", "path": "/tmp/gate", "sha256": "1" * 64},
            "findings": [self.finding(1)],
        }
        self.assertTrue(af.validate_instance_schema(ordinary_packet, "task-packet.schema.json"))
        valid_repair_packet = json.loads(json.dumps(ordinary_packet))
        valid_repair_packet["task_packet_schema_version"] = "1.1.0"
        self.assertFalse(af.validate_instance_schema(valid_repair_packet, "task-packet.schema.json"))
        repair_without_context = json.loads(json.dumps(first))
        repair_without_context["task_packet_schema_version"] = "1.1.0"
        self.assertTrue(af.validate_instance_schema(repair_without_context, "task-packet.schema.json"))

    def test_ambiguous_v10_repair_receipt_with_missing_rejected_bytes_fails_closed(self):
        run_id = self.start("A legacy human repair receipt cannot lose its rejected bytes.")
        directory, run = af.load_run(run_id)
        self.record_json(directory, run, "intent", {"reader_job": "Understand fail-closed repair."})
        self.record_json(directory, run, "claim-ledger", {"claims": []})
        af.transition(directory, run, "ARTICLE_RECIPE", "test", "exercise legacy repair ambiguity")
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            af.task_packet(directory, run)
            first_item = af.latest_task_packet_item(directory, run, "ARTICLE_RECIPE")
            af.abandon_cached_packet(directory, run, "ARTICLE_RECIPE", first_item, {"reason": "fixture_refresh"})
            af.task_packet(directory, run)
        rejected = directory / "artifacts" / "02-article-recipe.json"
        af.write_json(rejected, {"rejected": True})
        af.record_artifact(directory, run, rejected, "article-recipe", {"actor": "test"})
        receipt_path = af.write_gate_receipt(
            directory,
            run,
            "G-RECIPE-FIT",
            "REPAIR",
            [self.finding(2)],
            {"type": "human", "identity": "operator"},
            "ARTICLE_RECIPE",
        )
        receipt = af.load_json(receipt_path)
        self.assertEqual(receipt["gate_receipt_schema_version"], "1.0.0")
        self.assertEqual(
            len([key for key in receipt["artifact_hashes"] if key.startswith("task-packet:ARTICLE_RECIPE:")]),
            2,
        )
        rejected.unlink()
        with self.assertRaises(af.FlowError) as caught:
            af.command_repair(namespace(run_id=run_id, gate_id="G-RECIPE-FIT", finding=None))
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        self.assertEqual(af.load_json(directory / "run.json")["status"], "BLOCKED")
        self.assertFalse(any(
            event["type"] == "REPAIR"
            for event in af._read_jsonl(directory / "events.jsonl")
        ))

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
                "run_id": run["run_id"],
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
        self.assertEqual(packets[0]["task_packet_schema_version"], "1.0.0")
        self.assertNotIn("repair_context", packets[0])
        for packet, prior_attempt in zip(packets[1:], (1, 2)):
            self.assertEqual(packet["task_packet_schema_version"], "1.1.0")
            context = packet["repair_context"]
            self.assertEqual(context["failed_attempt"], prior_attempt)
            self.assertEqual(context["findings"][0]["location"], f"claim:CL-{prior_attempt:03d}")
            self.assertEqual(context["task_binding"]["attempt"], prior_attempt)
            bound_receipt = af.load_json(Path(context["gate_receipt"]["path"]))
            self.assertEqual(bound_receipt["task_binding"], context["task_binding"])
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

    def test_concurrent_execute_claims_once_and_preserves_the_event_chain(self):
        run_id = self.start("Concurrent execution must have one external owner.")
        started = threading.Event()
        release = threading.Event()
        invocations = 0

        def invoke(_route, _packet_path, _packet):
            nonlocal invocations
            invocations += 1
            started.set()
            self.assertTrue(release.wait(5))
            return '{"fixture": true}\n', {"provider": "fixture", "model": "fixture-model"}

        completed = subprocess.CompletedProcess([], af.EXIT_WAITING, '{"ok": false}\n', "")
        with (
            mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
            mock.patch.object(af, "invoke_route", side_effect=invoke),
            mock.patch.object(af.subprocess, "run", return_value=completed),
            mock.patch.object(af, "emit"),
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(
                    af.command_execute_stage,
                    namespace(run_id=run_id, route=None, canary=False),
                )
                self.assertTrue(started.wait(5))
                with self.assertRaises(af.FlowError):
                    af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False))
                release.set()
                self.assertEqual(first.result(timeout=10), af.EXIT_WAITING)

        self.assertEqual(invocations, 1)
        directory, run = af.load_run(run_id)
        claims = [event for event in af._read_jsonl(directory / run["event_log"]) if event["type"] == "MODEL_EXECUTION_STARTED"]
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["payload"]["execution_number"], 1)
        self.assertTrue(af.verify_event_log(directory, run)[0])

    def test_provider_failures_consume_two_unique_bound_executions(self):
        run_id = self.start("Every failed provider call must consume the bounded window.")
        with (
            mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
            mock.patch.object(af, "invoke_route", side_effect=af.FlowError("fixture provider failed")) as invoke,
            mock.patch.object(af, "emit"),
        ):
            with self.assertRaises(af.FlowError) as caught:
                af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False))
        self.assertEqual(caught.exception.code, af.EXIT_WAITING)
        self.assertEqual(invoke.call_count, 2)
        directory, run = af.load_run(run_id)
        events = af._read_jsonl(directory / run["event_log"])
        claims = [event["payload"] for event in events if event["type"] == "MODEL_EXECUTION_STARTED"]
        failures = [event["payload"] for event in events if event["type"] == "MODEL_ROUTE_FAILURE"]
        retries = [event["payload"] for event in events if event["type"] == "RETRY"]
        self.assertEqual([item["attempt"] for item in claims], [1, 2])
        self.assertEqual([item["execution_number"] for item in claims], [1, 2])
        self.assertEqual([item["attempt"] for item in failures], [1, 2])
        self.assertEqual([item["attempt"] for item in retries], [1, 2])
        self.assertEqual(run["status"], "BLOCKED")
        self.assertEqual(af.stage_attempt_evidence(directory, run, "RESEARCH_PLAN")["window_used"], 2)
        with (
            mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
            mock.patch.object(af, "emit"),
        ):
            self.assertEqual(
                af.command_repair(namespace(run_id=run_id, gate_id="G-RESEARCH-PLAN", finding=None)),
                af.EXIT_OK,
            )
            directory, repaired_run = af.load_run(run_id)
            _, repaired_packet = af.task_packet(directory, repaired_run)
        self.assertEqual(repaired_packet["attempt"], 3)
        self.assertEqual(repaired_packet["task_packet_schema_version"], "1.0.0")
        self.assertNotIn("repair_context", repaired_packet)

    def test_provider_exhaustion_carries_unresolved_repair_context_through_crash(self):
        run_id = self.start("A failed repair provider must not lose the rejected gate context.")
        completed = subprocess.CompletedProcess([], af.EXIT_WAITING, '{"ok": false}\n', "")
        with (
            mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
            mock.patch.object(
                af,
                "invoke_route",
                return_value=('{"attempt": 1}\n', {"provider": "fixture", "model": "fixture-model"}),
            ),
            mock.patch.object(af.subprocess, "run", return_value=completed),
            mock.patch.object(af, "emit"),
        ):
            self.assertEqual(
                af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False)),
                af.EXIT_WAITING,
            )
        directory, run = af.load_run(run_id)
        first_packet_item = af.latest_task_packet_item(directory, run, "RESEARCH_PLAN")
        _, first_packet, issue = af.validate_recorded_task_packet(directory, run, first_packet_item)
        self.assertIsNone(issue)
        with (
            mock.patch.object(af, "automatic_gate", return_value=("REPAIR", [self.finding(1)])),
            mock.patch.object(af, "emit"),
        ):
            self.assertEqual(
                af.command_submit(namespace(
                    run_id=run_id,
                    stage="RESEARCH_PLAN",
                    file=first_packet["expected_outputs"][0]["path"],
                )),
                af.EXIT_OK,
            )
        original_context = af.load_run(run_id)[1]["pending_repair"]
        with (
            mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
            mock.patch.object(af, "invoke_route", side_effect=af.FlowError("repair provider failed")),
            mock.patch.object(af, "emit"),
        ):
            with self.assertRaises(af.FlowError) as caught:
                af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False))
        self.assertEqual(caught.exception.code, af.EXIT_WAITING)
        self.assertEqual(af.load_run(run_id)[1]["pending_repair"], original_context)

        real_save = af.save_run

        def crash_after_repair_transition(save_directory, save_value):
            tail = af._read_jsonl(save_directory / save_value["event_log"])[-1]
            if tail["type"] == "STATE_TRANSITION" and "next bounded window" in tail["payload"].get("reason", ""):
                raise RuntimeError("crash after carried repair transition")
            return real_save(save_directory, save_value)

        with mock.patch.object(af, "save_run", side_effect=crash_after_repair_transition):
            with self.assertRaisesRegex(RuntimeError, "carried repair"):
                af.command_repair(namespace(run_id=run_id, gate_id="G-RESEARCH-PLAN", finding=None))
        directory, recovered = af.load_run(run_id)
        operator_repair = next(
            event for event in reversed(af._read_jsonl(directory / recovered["event_log"]))
            if event["type"] == "REPAIR" and event["actor"] == "operator_or_controller"
        )
        self.assertTrue(operator_repair["payload"]["repair_context_required"])
        self.assertEqual(operator_repair["payload"]["repair_context"], original_context)
        self.assertEqual(recovered["pending_repair"], original_context)
        self.assertFalse(Path(operator_repair["payload"]["repair_context"]["rejected_output"]["path"]).is_absolute())
        self.assertFalse(Path(operator_repair["payload"]["repair_context"]["gate_receipt"]["path"]).is_absolute())
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            _, packet = af.task_packet(directory, recovered)
        self.assertEqual(packet["task_packet_schema_version"], "1.1.0")
        self.assertEqual(packet["repair_context"]["source_stage"], original_context["source_stage"])
        self.assertEqual(packet["repair_context"]["findings"], original_context["findings"])
        self.assertEqual(
            packet["repair_context"]["rejected_output"]["sha256"],
            original_context["rejected_output"]["sha256"],
        )
        self.assertEqual(
            packet["repair_context"]["gate_receipt"]["sha256"],
            original_context["gate_receipt"]["sha256"],
        )

    def test_cross_stage_provider_exhaustion_carries_context_through_crash(self):
        run_id, directory, _, original_context = self.post_edit_repair_run(
            "Cross-stage provider exhaustion must carry its unresolved context."
        )
        with (
            mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
            mock.patch.object(af, "invoke_route", side_effect=af.FlowError("edit repair provider failed")),
            mock.patch.object(af, "emit"),
        ):
            with self.assertRaises(af.FlowError) as caught:
                af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False))
        self.assertEqual(caught.exception.code, af.EXIT_WAITING)
        definition = af.state_definition("EDIT", af.load_run(run_id)[1])
        real_save = af.save_run

        def crash_after_cross_stage_repair(save_directory, save_value):
            tail = af._read_jsonl(save_directory / save_value["event_log"])[-1]
            if tail["type"] == "STATE_TRANSITION" and "next bounded window" in tail["payload"].get("reason", ""):
                raise RuntimeError("crash after cross-stage carried repair")
            return real_save(save_directory, save_value)

        with mock.patch.object(af, "save_run", side_effect=crash_after_cross_stage_repair):
            with self.assertRaisesRegex(RuntimeError, "cross-stage carried"):
                af.command_repair(namespace(run_id=run_id, gate_id=definition["gate"], finding=None))
        directory, recovered = af.load_run(run_id)
        self.assertNotIn("repair_recovery_error", recovered)
        self.assertEqual(recovered["pending_repair"], original_context)
        repair_event = next(
            event for event in reversed(af._read_jsonl(directory / recovered["event_log"]))
            if event["type"] == "REPAIR" and event["actor"] == "operator_or_controller"
        )
        self.assertEqual(repair_event["payload"]["source_state"], "POST_EDIT_CLAIM_VERIFICATION")
        self.assertEqual(repair_event["payload"]["repair_state"], "EDIT")
        self.assertTrue(repair_event["payload"]["repair_context_required"])
        self.assertEqual(repair_event["payload"]["repair_context"], original_context)
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            _, packet = af.task_packet(directory, recovered)
        self.assertEqual(packet["task_packet_schema_version"], "1.1.0")
        self.assertEqual(packet["repair_context"]["source_stage"], "POST_EDIT_CLAIM_VERIFICATION")

    def test_completed_cross_stage_context_is_not_resurrected_by_provider_exhaustion(self):
        run_id, directory, _, _ = self.post_edit_repair_run(
            "A completed cross-stage repair must not contaminate a later provider-only window."
        )
        completed = subprocess.CompletedProcess([], af.EXIT_WAITING, '{"ok": false}\n', "")
        with (
            mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
            mock.patch.object(
                af,
                "invoke_route",
                return_value=("Edited article fixture.\n", {"provider": "fixture", "model": "fixture-model"}),
            ),
            mock.patch.object(af.subprocess, "run", return_value=completed),
            mock.patch.object(af, "emit"),
        ):
            self.assertEqual(
                af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False)),
                af.EXIT_WAITING,
            )
        directory, edit_run = af.load_run(run_id)
        edit_item = af.latest_task_packet_item(directory, edit_run, "EDIT")
        _, edit_packet, issue = af.validate_recorded_task_packet(directory, edit_run, edit_item)
        self.assertIsNone(issue)
        with (
            mock.patch.object(af, "automatic_gate", return_value=("PASS", [])),
            mock.patch.object(af, "emit"),
        ):
            self.assertEqual(
                af.command_submit(namespace(
                    run_id=run_id,
                    stage="EDIT",
                    file=edit_packet["expected_outputs"][0]["path"],
                )),
                af.EXIT_OK,
            )
        directory, returned = af.load_run(run_id)
        self.assertEqual(returned["state"], "POST_EDIT_CLAIM_VERIFICATION")
        self.assertNotIn("pending_repair", returned)
        with (
            mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
            mock.patch.object(af, "invoke_route", side_effect=af.FlowError("later provider-only failure")),
            mock.patch.object(af, "emit"),
        ):
            with self.assertRaises(af.FlowError) as caught:
                af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False))
        self.assertEqual(caught.exception.code, af.EXIT_WAITING)
        directory, blocked = af.load_run(run_id)
        self.assertNotIn("pending_repair", blocked)
        definition = af.state_definition("POST_EDIT_CLAIM_VERIFICATION", blocked)
        with mock.patch.object(af, "emit"):
            self.assertEqual(
                af.command_repair(namespace(run_id=run_id, gate_id=definition["gate"], finding=None)),
                af.EXIT_OK,
            )
        directory, repaired = af.load_run(run_id)
        latest_repair = next(
            event for event in reversed(af._read_jsonl(directory / repaired["event_log"]))
            if event["type"] == "REPAIR" and event["actor"] == "operator_or_controller"
        )
        self.assertFalse(latest_repair["payload"]["repair_context_required"])
        self.assertIsNone(latest_repair["payload"]["repair_context"])
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            _, packet = af.task_packet(directory, repaired)
        self.assertEqual(packet["task_packet_schema_version"], "1.0.0")
        self.assertNotIn("repair_context", packet)

    def test_fallback_chain_survives_packet_artifact_crash_before_dispatch(self):
        run_id = self.start("A fallback packet crash must retain its exact next route.")
        primary_set = self.route_set("RESEARCH_PLAN")
        primary = primary_set["chosen"]
        fallback = {**primary, "model": "zz-fallback-model"}
        routes = {
            **primary_set,
            "candidates": [primary, fallback],
            "chosen": primary,
            "fallbacks": [fallback],
        }
        real_save = af.save_run

        def crash_after_fallback_artifact(save_directory, save_value):
            tail = af._read_jsonl(save_directory / save_value["event_log"])[-1]
            item = (tail.get("payload") or {}).get("artifact", {})
            if tail["type"] == "ARTIFACT_RECORDED" and item.get("type") == "task-packet:RESEARCH_PLAN:2":
                raise RuntimeError("crash after fallback packet artifact")
            return real_save(save_directory, save_value)

        with (
            mock.patch.object(af, "route_candidates", return_value=routes),
            mock.patch.object(af, "invoke_route", side_effect=af.FlowError("primary failed")),
            mock.patch.object(af, "save_run", side_effect=crash_after_fallback_artifact),
            mock.patch.object(af, "emit"),
        ):
            with self.assertRaisesRegex(RuntimeError, "fallback packet artifact"):
                af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False))
        directory, recovered = af.load_run(run_id)
        self.assertEqual(
            recovered["route_retry_candidates"]["RESEARCH_PLAN"][0]["model"],
            "zz-fallback-model",
        )
        events = af._read_jsonl(directory / recovered["event_log"])
        self.assertFalse(any(
            event["type"] == "TASK_DISPATCHED" and event["payload"].get("attempt") == 2
            for event in events
        ))
        with mock.patch.object(af, "route_candidates", return_value=routes):
            _, replacement = af.task_packet(directory, recovered)
        self.assertEqual(replacement["attempt"], 3)
        self.assertEqual(replacement["selected_route"]["chosen"]["model"], "zz-fallback-model")

    def test_crashed_execution_claim_is_abandoned_before_a_fresh_attempt(self):
        run_id = self.start("A provider crash cannot reuse its claimed packet.")
        calls = 0

        def invoke(_route, _packet_path, packet):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("provider process disappeared after invocation began")
            return json.dumps({"attempt": packet["attempt"]}) + "\n", {"provider": "fixture", "model": "fixture-model"}

        completed = subprocess.CompletedProcess([], af.EXIT_WAITING, '{"ok": false}\n', "")
        with (
            mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
            mock.patch.object(af, "invoke_route", side_effect=invoke),
            mock.patch.object(af.subprocess, "run", return_value=completed),
            mock.patch.object(af, "emit"),
        ):
            with self.assertRaisesRegex(RuntimeError, "disappeared"):
                af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False))
            self.assertEqual(
                af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False)),
                af.EXIT_WAITING,
            )
        self.assertEqual(calls, 2)
        directory, run = af.load_run(run_id)
        events = af._read_jsonl(directory / run["event_log"])
        claims = [event["payload"] for event in events if event["type"] == "MODEL_EXECUTION_STARTED"]
        retries = [event["payload"] for event in events if event["type"] == "RETRY"]
        self.assertEqual([item["attempt"] for item in claims], [1, 2])
        self.assertEqual([item["attempt"] for item in retries], [1])
        self.assertTrue((directory / "tasks" / "research_plan-01.json").is_file())
        self.assertTrue((directory / "tasks" / "research_plan-02.json").is_file())

    def test_repair_transition_crash_recovers_same_stage_v11_context(self):
        run_id = self.start("Recover a same-stage repair authorization from the WAL.")
        directory, run = af.load_run(run_id)
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            _, packet = af.task_packet(directory, run)
        output = Path(packet["expected_outputs"][0]["path"])
        af.write_json(output, {"attempt": 1})
        real_save = af.save_run

        def crash_after_transition(save_directory, save_value):
            tail = af._read_jsonl(save_directory / save_value["event_log"])[-1]
            if tail["type"] == "STATE_TRANSITION" and "Automatic targeted repair" in tail["payload"].get("reason", ""):
                raise RuntimeError("crash after repair transition")
            return real_save(save_directory, save_value)

        with (
            mock.patch.object(af, "automatic_gate", return_value=("REPAIR", [self.finding(1)])),
            mock.patch.object(af, "save_run", side_effect=crash_after_transition),
        ):
            with self.assertRaisesRegex(RuntimeError, "repair transition"):
                af.command_submit(namespace(run_id=run_id, stage="RESEARCH_PLAN", file=str(output)))
        directory, recovered = af.load_run(run_id)
        self.assertEqual(recovered["state"], "RESEARCH_PLAN")
        self.assertEqual(recovered["pending_repair"]["source_stage"], "RESEARCH_PLAN")
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            _, repaired = af.task_packet(directory, recovered)
        self.assertEqual(repaired["task_packet_schema_version"], "1.1.0")
        self.assertEqual(repaired["repair_context"]["failed_attempt"], 1)
        self.assertEqual(repaired["repair_context"]["findings"], [self.finding(1)])
        self.assertEqual(
            af.sha256_path(Path(repaired["repair_context"]["rejected_output"]["path"])),
            repaired["repair_context"]["rejected_output"]["sha256"],
        )

    def test_repair_transition_crash_recovers_cross_stage_v11_context(self):
        run_id = self.start("Recover a cross-stage repair authorization from the WAL.")
        directory, run = af.load_run(run_id)
        for artifact_type in ("verified-claim-ledger", "article-recipe", "voice-learning", "voice-profile", "locked-fields"):
            if not af.artifact(run, artifact_type):
                self.record_json(directory, run, artifact_type, {"fixture": artifact_type})
        for artifact_type in ("article", "draft", "naturalization-directive"):
            if not af.artifact(run, artifact_type):
                self.record_text(directory, run, artifact_type, f"{artifact_type} fixture\n")
        run.setdefault("model_experiment", {}).update({
            "provider_id": "fixture",
            "assigned_model_id": "fixture-model",
            "active_model_id": "fixture-model",
        })
        af.transition(directory, run, "POST_EDIT_CLAIM_VERIFICATION", "test", "exercise cross-stage repair recovery")
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            _, packet = af.task_packet(directory, run)
        output = Path(packet["expected_outputs"][0]["path"])
        af.write_json(output, {"attempt": 1})
        real_save = af.save_run

        def crash_after_transition(save_directory, save_value):
            tail = af._read_jsonl(save_directory / save_value["event_log"])[-1]
            if tail["type"] == "STATE_TRANSITION" and tail["payload"].get("to") == "EDIT":
                raise RuntimeError("crash after cross-stage repair transition")
            return real_save(save_directory, save_value)

        with (
            mock.patch.object(af, "automatic_gate", return_value=("REPAIR", [self.finding(1)])),
            mock.patch.object(af, "save_run", side_effect=crash_after_transition),
        ):
            with self.assertRaisesRegex(RuntimeError, "cross-stage"):
                af.command_submit(namespace(run_id=run_id, stage="POST_EDIT_CLAIM_VERIFICATION", file=str(output)))
        directory, recovered = af.load_run(run_id)
        self.assertEqual(recovered["state"], "EDIT")
        self.assertEqual(recovered["pending_repair"]["source_stage"], "POST_EDIT_CLAIM_VERIFICATION")
        self.assertEqual(recovered["pending_repair"]["repair_state"], "EDIT")
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            _, repaired = af.task_packet(directory, recovered)
        self.assertEqual(repaired["task_packet_schema_version"], "1.1.0")
        self.assertEqual(repaired["repair_context"]["task_binding"]["attempt"], 1)

    def test_duplicate_submit_after_committed_gate_durably_blocks_once(self):
        run_id, directory = self.research_run()
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            packet_path, packet = af.task_packet(directory, af.load_run(run_id)[1])
        output = Path(packet["expected_outputs"][0]["path"])
        af.write_json(output, {"attempt": 1})
        _, run = af.load_run(run_id)
        real_append = af.append_event

        def crash_before_gate(event_directory, event_run, event_type, actor, payload):
            if event_type == "GATE_RECORDED":
                raise RuntimeError("gate event crash")
            return real_append(event_directory, event_run, event_type, actor, payload)

        with mock.patch.object(af, "append_event", side_effect=crash_before_gate):
            with self.assertRaisesRegex(RuntimeError, "gate event"):
                af.write_gate_receipt(
                    directory,
                    run,
                    "G-EVIDENCE-COVERAGE",
                    "REPAIR",
                    [self.finding(1)],
                    {"type": "code", "version": "test"},
                    "RESEARCH",
                    task_state="RESEARCH",
                    task_attempt=1,
                    task_packet_sha256=af.sha256_path(packet_path),
                )
        for _ in range(2):
            with self.assertRaises(af.FlowError) as caught:
                af.command_submit(namespace(run_id=run_id, stage="RESEARCH", file=str(output)))
            self.assertEqual(caught.exception.code, af.EXIT_WAITING)
        raw = af.load_json(directory / "run.json")
        self.assertEqual(raw["status"], "BLOCKED")
        escalations = [event for event in af._read_jsonl(directory / raw["event_log"]) if event["type"] == "ESCALATION"]
        self.assertEqual(len(escalations), 1)
        self.assertEqual(escalations[0]["payload"]["task_packet_sha256"], af.sha256_path(packet_path))

    def test_submit_attempt_integrity_failures_durably_block(self):
        def pending_model_call(label):
            run_id = self.start(f"Submit integrity fixture: {label}.")
            completed = subprocess.CompletedProcess([], af.EXIT_WAITING, '{"ok": false}\n', "")
            with (
                mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
                mock.patch.object(
                    af,
                    "invoke_route",
                    return_value=('{}\n', {"provider": "fixture", "model": "fixture-model"}),
                ),
                mock.patch.object(af.subprocess, "run", return_value=completed),
                mock.patch.object(af, "emit"),
            ):
                self.assertEqual(
                    af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False)),
                    af.EXIT_WAITING,
                )
            directory, run = af.load_run(run_id)
            packet_item = af.latest_task_packet_item(directory, run, "RESEARCH_PLAN")
            packet_path, packet, issue = af.validate_recorded_task_packet(directory, run, packet_item)
            self.assertIsNone(issue)
            return run_id, directory, run, packet_path, packet

        for failure in ("packet", "receipt", "source", "destination"):
            with self.subTest(failure=failure):
                run_id, directory, run, packet_path, packet = pending_model_call(failure)
                source = Path(packet["expected_outputs"][0]["path"])
                if failure == "packet":
                    packet_path.write_bytes(packet_path.read_bytes() + b" ")
                elif failure == "receipt":
                    receipt = directory / "receipts" / "model-call-research_plan-01.json"
                    receipt.write_bytes(receipt.read_bytes() + b" ")
                elif failure == "source":
                    source.write_bytes(b'{"changed": true}\n')
                else:
                    (directory / "artifacts" / "01-research-plan.json").write_bytes(b'{"different": true}\n')
                with self.assertRaises(af.FlowError) as caught:
                    af.command_submit(namespace(run_id=run_id, stage="RESEARCH_PLAN", file=str(source)))
                self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
                raw = af.load_json(directory / "run.json")
                self.assertEqual(raw["status"], "BLOCKED")
                escalations = [
                    event for event in af._read_jsonl(directory / raw["event_log"])
                    if event["type"] == "ESCALATION"
                ]
                self.assertEqual(len(escalations), 1)
                self.assertEqual(escalations[0]["payload"]["attempt"], 1)

    def test_submit_copies_the_same_source_snapshot_bound_by_the_receipt(self):
        run_id = self.start("Submission must not switch bytes after receipt validation.")
        completed = subprocess.CompletedProcess([], af.EXIT_WAITING, '{"ok": false}\n', "")
        trusted = b'{"trusted": true}\n'
        with (
            mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
            mock.patch.object(
                af,
                "invoke_route",
                return_value=(trusted.decode("utf-8"), {"provider": "fixture", "model": "fixture-model"}),
            ),
            mock.patch.object(af.subprocess, "run", return_value=completed),
            mock.patch.object(af, "emit"),
        ):
            self.assertEqual(
                af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False)),
                af.EXIT_WAITING,
            )
        directory, run = af.load_run(run_id)
        packet_item = af.latest_task_packet_item(directory, run, "RESEARCH_PLAN")
        _, packet, issue = af.validate_recorded_task_packet(directory, run, packet_item)
        self.assertIsNone(issue)
        source = Path(packet["expected_outputs"][0]["path"])
        tampered = b'{"tampered": true}\n'
        original_read_bytes = Path.read_bytes
        swapped = False

        def swap_source_after_snapshot(path):
            nonlocal swapped
            value = original_read_bytes(path)
            if not swapped and path.resolve() == source.resolve():
                swapped = True
                path.write_bytes(tampered)
            return value

        with (
            mock.patch.object(Path, "read_bytes", new=swap_source_after_snapshot),
            mock.patch.object(af, "automatic_gate", return_value=("PASS", [])),
            mock.patch.object(af, "emit"),
        ):
            af.command_submit(namespace(run_id=run_id, stage="RESEARCH_PLAN", file=str(source)))
        self.assertTrue(swapped)
        destination = directory / "artifacts" / "01-research-plan.json"
        self.assertEqual(destination.read_bytes(), trusted)
        self.assertEqual(source.read_bytes(), tampered)
        accepted = next(item for item in af.load_run(run_id)[1]["artifact_index"] if item["type"] == "research-plan")
        self.assertEqual(accepted["sha256"], af.sha256_bytes(trusted))

    def test_submit_blocks_destination_create_race_and_gate_time_mutation(self):
        def pending_model_call(label):
            run_id = self.start(f"Destination integrity fixture: {label}.")
            completed = subprocess.CompletedProcess([], af.EXIT_WAITING, '{"ok": false}\n', "")
            with (
                mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
                mock.patch.object(
                    af,
                    "invoke_route",
                    return_value=('{"trusted": true}\n', {"provider": "fixture", "model": "fixture-model"}),
                ),
                mock.patch.object(af.subprocess, "run", return_value=completed),
                mock.patch.object(af, "emit"),
            ):
                af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False))
            directory, run = af.load_run(run_id)
            packet_item = af.latest_task_packet_item(directory, run, "RESEARCH_PLAN")
            _, packet, issue = af.validate_recorded_task_packet(directory, run, packet_item)
            self.assertIsNone(issue)
            return run_id, directory, Path(packet["expected_outputs"][0]["path"])

        run_id, directory, source = pending_model_call("create race")
        destination = directory / "artifacts" / "01-research-plan.json"
        real_immutable_write = af.immutable_write
        collided = False

        def create_conflict(path, data):
            nonlocal collided
            if path == destination and not collided:
                collided = True
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'{"raced": true}\n')
            return real_immutable_write(path, data)

        with mock.patch.object(af, "immutable_write", side_effect=create_conflict):
            with self.assertRaises(af.FlowError) as caught:
                af.command_submit(namespace(run_id=run_id, stage="RESEARCH_PLAN", file=str(source)))
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        self.assertTrue(collided)
        self.assertEqual(af.load_json(directory / "run.json")["status"], "BLOCKED")

        run_id, directory, source = pending_model_call("gate mutation")
        destination = directory / "artifacts" / "01-research-plan.json"

        def mutate_during_gate(_directory, _run, _stage, path):
            self.assertEqual(path, destination)
            path.write_bytes(b'{"mutated_during_gate": true}\n')
            return "PASS", []

        with mock.patch.object(af, "automatic_gate", side_effect=mutate_during_gate):
            with self.assertRaises(af.FlowError) as caught:
                af.command_submit(namespace(run_id=run_id, stage="RESEARCH_PLAN", file=str(source)))
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        self.assertEqual(af.load_json(directory / "run.json")["status"], "BLOCKED")

        run_id, directory, source = pending_model_call("record boundary mutation")
        destination = directory / "artifacts" / "01-research-plan.json"

        def mutate_before_record(_directory, _run, _stage, _attempt):
            destination.write_bytes(b'{"mutated_before_record": true}\n')
            return {"provider": "fixture", "model": "fixture-model"}

        with (
            mock.patch.object(af, "automatic_gate", return_value=("PASS", [])),
            mock.patch.object(af, "latest_model_call_route", side_effect=mutate_before_record),
        ):
            with self.assertRaises(af.FlowError) as caught:
                af.command_submit(namespace(run_id=run_id, stage="RESEARCH_PLAN", file=str(source)))
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        self.assertEqual(af.load_json(directory / "run.json")["status"], "BLOCKED")
        self.assertFalse(any(
            event["type"] == "ARTIFACT_RECORDED"
            and (event["payload"].get("artifact") or {}).get("type") == "research-plan"
            for event in af._read_jsonl(directory / "events.jsonl")
        ))

        for boundary in ("packet", "input"):
            with self.subTest(boundary=boundary):
                run_id, directory, source = pending_model_call(f"gate-time {boundary} mutation")
                current_run = af.load_run(run_id)[1]
                packet_item = af.latest_task_packet_item(directory, current_run, "RESEARCH_PLAN")
                packet_path, packet, issue = af.validate_recorded_task_packet(directory, current_run, packet_item)
                self.assertIsNone(issue)

                def mutate_attempt_evidence(_directory, _run, _stage, _destination):
                    if boundary == "packet":
                        swapped = af.load_json(packet_path)
                        swapped["objective"] = "Gate-time swapped objective."
                        af.write_json(packet_path, swapped)
                    else:
                        input_path = Path(packet["inputs"][0]["path"])
                        input_path.write_bytes(input_path.read_bytes() + b"\nmutated during gate\n")
                    return "PASS", []

                with mock.patch.object(af, "automatic_gate", side_effect=mutate_attempt_evidence):
                    with self.assertRaises(af.FlowError) as caught:
                        af.command_submit(namespace(run_id=run_id, stage="RESEARCH_PLAN", file=str(source)))
                self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
                self.assertEqual(af.load_json(directory / "run.json")["status"], "BLOCKED")
                self.assertFalse(any(
                    event["type"] == "GATE_RECORDED"
                    and event["payload"].get("gate_id") == "G-RESEARCH-PLAN"
                    for event in af._read_jsonl(directory / "events.jsonl")
                ))

    def test_legacy_v10_gate_receipt_uses_only_an_exact_unique_packet_hash(self):
        run_id, directory = self.research_run()
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            packet_path, _ = af.task_packet(directory, af.load_run(run_id)[1])
        _, run = af.load_run(run_id)
        real_append = af.append_event

        def crash_before_gate(event_directory, event_run, event_type, actor, payload):
            if event_type == "GATE_RECORDED":
                raise RuntimeError("legacy gate event crash")
            return real_append(event_directory, event_run, event_type, actor, payload)

        with mock.patch.object(af, "append_event", side_effect=crash_before_gate):
            with self.assertRaisesRegex(RuntimeError, "legacy gate"):
                af.write_gate_receipt(
                    directory,
                    run,
                    "G-EVIDENCE-COVERAGE",
                    "REPAIR",
                    [self.finding(1)],
                    {"type": "code", "version": "legacy"},
                    "RESEARCH",
                )
        receipt = next((directory / "receipts").glob("g-evidence-coverage-*.json"))
        self.assertEqual(af.load_json(receipt)["gate_receipt_schema_version"], "1.0.0")
        with self.assertRaises(af.FlowError) as caught:
            af.current_packet(*af.load_run(run_id))
        self.assertEqual(caught.exception.code, af.EXIT_WAITING)
        self.assertEqual(af.load_json(directory / "run.json")["status"], "BLOCKED")
        self.assertFalse((directory / "tasks" / "research-02.json").exists())
        self.assertEqual(
            af.load_json(receipt)["artifact_hashes"]["task-packet:RESEARCH:1"],
            af.sha256_path(packet_path),
        )

    def test_observer_load_does_not_write_or_drop_a_writer_tail(self):
        run_id = self.start("A watcher cannot overwrite an in-flight writer cache.")
        directory, run = af.load_run(run_id)
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            packet_path, packet = af.task_packet(directory, run)
        started = threading.Event()
        release = threading.Event()

        def writer():
            writer_directory, writer_run = af.load_run(run_id)
            with af.run_lock(writer_directory, writer_run):
                identity = af.task_identity_payload("RESEARCH_PLAN", 1, af.sha256_path(packet_path))
                route = packet["selected_route"]["chosen"]
                writer_run.setdefault("route_failures", {}).setdefault("RESEARCH_PLAN", {})["fixture:fixture-model"] = 1
                af.append_event(writer_directory, writer_run, "MODEL_ROUTE_FAILURE", "controller", {
                    **identity,
                    "execution_number": 1,
                    "route": route,
                    "failure_count": 1,
                    "error": "fixture",
                    "details": None,
                })
                started.set()
                self.assertTrue(release.wait(5))
                af.save_run(writer_directory, writer_run)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(writer)
            self.assertTrue(started.wait(5))
            before = (directory / "run.json").read_bytes()
            _, observed = af.load_run(run_id)
            self.assertEqual(observed["route_failures"]["RESEARCH_PLAN"]["fixture:fixture-model"], 1)
            self.assertEqual((directory / "run.json").read_bytes(), before)
            release.set()
            future.result(timeout=10)
        _, final = af.load_run(run_id)
        self.assertEqual(final["route_failures"]["RESEARCH_PLAN"]["fixture:fixture-model"], 1)

    def test_headless_legacy_waiting_human_cache_is_preserved_then_migrated(self):
        run_id = self.start("Legacy cache-only holds must remain stable.")
        directory, run = af.load_run(run_id)
        run["status"] = "WAITING_HUMAN"
        af.save_run(directory, run)
        raw = af.load_json(directory / "run.json")
        raw.pop("applied_event_head", None)
        af.write_json(directory / "run.json", raw)
        before = (directory / "run.json").read_bytes()
        _, observed = af.load_run(run_id)
        self.assertEqual(observed["status"], "WAITING_HUMAN")
        self.assertEqual((directory / "run.json").read_bytes(), before)
        with af.run_lock(directory, observed):
            pass
        migrated = af.load_json(directory / "run.json")
        self.assertEqual(migrated["status"], "WAITING_HUMAN")
        self.assertIn("applied_event_head", migrated)

    def test_headless_legacy_crash_reuses_its_durable_pending_dispatch(self):
        run_id = self.start("A pre-head dispatch crash must not mint a duplicate packet.")
        directory, run = af.load_run(run_id)
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            first_path, first_packet = af.task_packet(directory, run)
        raw = af.load_json(directory / "run.json")
        raw["status"] = "ACTIVE"
        raw["attempts"]["RESEARCH_PLAN"] = 0
        raw.pop("applied_event_head", None)
        af.write_json(directory / "run.json", raw)
        directory, recovered = af.load_run(run_id)
        self.assertEqual(recovered["status"], "WAITING_MODEL")
        self.assertEqual(recovered["attempts"]["RESEARCH_PLAN"], 1)
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            current_path, current_packet = af.current_packet(directory, recovered)
        self.assertEqual(current_path, first_path)
        self.assertEqual(current_packet["attempt"], first_packet["attempt"])
        self.assertFalse((directory / "tasks" / "research_plan-02.json").exists())

    def test_headless_legacy_route_state_remains_cache_authoritative(self):
        run_id = self.start("Legacy automatic repair must preserve cached route failures.")
        directory, run = af.load_run(run_id)
        route = {"provider": "legacy", "model": "model"}
        af.append_event(directory, run, "MODEL_OUTPUT_REJECTED", "controller", {
            "state": "RESEARCH_PLAN",
            "route": route,
            "failure_count": 1,
            "findings": [self.finding(1)],
        })
        af.append_event(directory, run, "REPAIR", "controller", {
            "source_state": "RESEARCH_PLAN",
            "repair_state": "RESEARCH_PLAN",
            "attempts_in_window": 1,
        })
        run["route_failures"] = {"RESEARCH_PLAN": {"legacy:model": 1}}
        af.save_run(directory, run)
        raw = af.load_json(directory / "run.json")
        raw.pop("applied_event_head", None)
        af.write_json(directory / "run.json", raw)
        self.assertEqual(
            af.load_run(run_id)[1]["route_failures"],
            {"RESEARCH_PLAN": {"legacy:model": 1}},
        )

        run_id = self.start("Legacy human repair must not resurrect cleared route failures.")
        directory, run = af.load_run(run_id)
        af.append_event(directory, run, "MODEL_OUTPUT_REJECTED", "controller", {
            "state": "RESEARCH_PLAN",
            "route": route,
            "failure_count": 1,
            "findings": [self.finding(1)],
        })
        af.append_event(directory, run, "GATE_RECORDED", "operator", {
            "state": "RESEARCH_PLAN",
            "gate_id": "G-RESEARCH-PLAN",
            "outcome": "REPAIR",
        })
        run["route_failures"] = {}
        af.save_run(directory, run)
        raw = af.load_json(directory / "run.json")
        raw.pop("applied_event_head", None)
        af.write_json(directory / "run.json", raw)
        self.assertEqual(af.load_run(run_id)[1]["route_failures"], {})

    def test_exhaustion_escalation_is_idempotent_only_within_one_repair_window(self):
        run_id = self.start("Each bounded repair window needs its own exhaustion record.")
        directory, run = af.load_run(run_id)
        definition = dict(af.state_definition("RESEARCH_PLAN", run))
        definition["max_attempts"] = 2
        for failure_count in (1, 2):
            af.append_event(directory, run, "MODEL_OUTPUT_REJECTED", "legacy", {
                "state": "RESEARCH_PLAN",
                "failure_count": failure_count,
                "findings": [self.finding(failure_count)],
            })
        af.block_exhausted_stage(directory, run, "RESEARCH_PLAN", definition)
        af.block_exhausted_stage(directory, run, "RESEARCH_PLAN", definition)
        baseline_ordinal = af.reset_attempt_window(directory, run, "RESEARCH_PLAN")
        execution_baseline = run["attempt_baselines"]["RESEARCH_PLAN"]
        af.append_event(directory, run, "REPAIR", "operator", {
            "source_state": "RESEARCH_PLAN",
            "repair_state": "RESEARCH_PLAN",
            "attempt_ordinal_baseline": baseline_ordinal,
            "execution_count_baseline": execution_baseline,
            "repair_context": None,
            "repair_context_required": False,
            "clear_route_failures": True,
        })
        af.transition(directory, run, "RESEARCH_PLAN", "operator", "open the second bounded repair window")
        for failure_count in (3, 4):
            af.append_event(directory, run, "MODEL_OUTPUT_REJECTED", "legacy", {
                "state": "RESEARCH_PLAN",
                "failure_count": failure_count,
                "findings": [self.finding(failure_count)],
            })
        af.block_exhausted_stage(directory, run, "RESEARCH_PLAN", definition)
        af.block_exhausted_stage(directory, run, "RESEARCH_PLAN", definition)
        escalations = [
            event for event in af._read_jsonl(directory / run["event_log"])
            if event["type"] == "ESCALATION"
            and event["payload"].get("reason") == "attempt_window_exhausted"
        ]
        self.assertEqual(len(escalations), 2)
        self.assertEqual([event["payload"]["attempt_ordinal"] for event in escalations], [2, 4])
        self.assertEqual([event["payload"]["window_baseline"] for event in escalations], [0, 2])

    def test_legacy_rejections_compose_with_new_execution_numbers_after_repair(self):
        run_id = self.start("Legacy lower bounds must compose with new exact claims.")
        directory, run = af.load_run(run_id)
        for failure_count in range(1, 5):
            af.append_event(directory, run, "MODEL_OUTPUT_REJECTED", "legacy", {
                "state": "RESEARCH_PLAN",
                "failure_count": failure_count,
                "findings": [self.finding(failure_count)],
            })
        baseline = af.reset_attempt_window(directory, run, "RESEARCH_PLAN")
        self.assertEqual(baseline, 4)
        af.append_event(directory, run, "REPAIR", "operator", {
            "gate_id": "G-RESEARCH-PLAN",
            "source_state": "RESEARCH_PLAN",
            "repair_state": "RESEARCH_PLAN",
            "attempt_ordinal_baseline": 4,
            "execution_count_baseline": 4,
            "repair_context": None,
            "repair_context_required": False,
            "clear_route_failures": True,
        })
        af.transition(directory, run, "RESEARCH_PLAN", "operator", "new bounded repair window")
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            packet_path, packet = af.task_packet(directory, run)
        self.assertEqual(packet["attempt"], 5)
        af.append_event(directory, run, "MODEL_EXECUTION_STARTED", "controller", {
            **af.task_identity_payload("RESEARCH_PLAN", 5, af.sha256_path(packet_path)),
            "execution_number": 5,
            "route": packet["selected_route"]["chosen"],
        })
        af.save_run(directory, run)
        evidence = af.stage_attempt_evidence(directory, run, "RESEARCH_PLAN")
        self.assertEqual(evidence["execution_count"], 5)
        self.assertEqual(evidence["window_baseline"], 4)
        self.assertEqual(evidence["window_used"], 1)

    def test_operator_repair_crash_recovers_distinct_ordinal_and_execution_baselines(self):
        run_id = self.start("Repair recovery must not confuse packet ordinals with executions.")
        directory, run = af.load_run(run_id)
        packets = []
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            for index in range(4):
                if index:
                    item = af.latest_task_packet_item(directory, run, "RESEARCH_PLAN")
                    af.abandon_cached_packet(directory, run, "RESEARCH_PLAN", item, {"reason": "test_route_refresh"})
                packet_path, packet = af.task_packet(directory, run)
                packets.append((packet_path, packet))
        for execution_number, (packet_path, packet) in enumerate(packets[:2], start=1):
            af.append_event(directory, run, "MODEL_EXECUTION_STARTED", "controller", {
                **af.task_identity_payload("RESEARCH_PLAN", packet["attempt"], af.sha256_path(packet_path)),
                "execution_number": execution_number,
                "route": packet["selected_route"]["chosen"],
            })
        rejected = directory / "artifacts" / "ordinal-four-rejected-plan.json"
        af.write_json(rejected, {"rejected": True})
        af.record_artifact(directory, run, rejected, "research-plan", {"actor": "test"})
        latest_path, latest_packet = packets[-1]
        af.write_gate_receipt(
            directory,
            run,
            "G-RESEARCH-PLAN",
            "REPAIR",
            [self.finding(4)],
            {"type": "code", "version": "test"},
            "RESEARCH_PLAN",
            task_state="RESEARCH_PLAN",
            task_attempt=4,
            task_packet_sha256=af.sha256_path(latest_path),
        )
        run["status"] = "BLOCKED"
        af.save_run(directory, run)
        before = af.stage_attempt_evidence(directory, run, "RESEARCH_PLAN")
        self.assertEqual((before["ordinal"], before["execution_count"]), (4, 2))
        real_save = af.save_run

        def crash_after_transition(save_directory, save_value):
            tail = af._read_jsonl(save_directory / save_value["event_log"])[-1]
            if tail["type"] == "STATE_TRANSITION" and "next bounded window" in tail["payload"].get("reason", ""):
                raise RuntimeError("crash after operator repair transition")
            return real_save(save_directory, save_value)

        with mock.patch.object(af, "save_run", side_effect=crash_after_transition):
            with self.assertRaisesRegex(RuntimeError, "operator repair"):
                af.command_repair(namespace(run_id=run_id, gate_id="G-RESEARCH-PLAN", finding=None))
        directory, recovered = af.load_run(run_id)
        self.assertEqual(recovered["attempt_baselines"]["RESEARCH_PLAN"], 2)
        repair_event = next(
            event for event in reversed(af._read_jsonl(directory / recovered["event_log"]))
            if event["type"] == "REPAIR"
        )
        self.assertEqual(repair_event["payload"]["attempt_ordinal_baseline"], 4)
        self.assertEqual(repair_event["payload"]["execution_count_baseline"], 2)
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            _, repaired = af.task_packet(directory, recovered)
        self.assertEqual(repaired["attempt"], 5)
        self.assertEqual(repaired["task_packet_schema_version"], "1.1.0")

    def test_provider_written_output_must_match_returned_bytes_exactly(self):
        run_id = self.start("Semantically equal bytes are not immutable evidence.")

        def invoke(_route, _packet_path, packet):
            Path(packet["expected_outputs"][0]["path"]).write_bytes(b'{"same":true}\n')
            return '{\n  "same": true\n}\n', {"provider": "fixture", "model": "fixture-model"}

        with (
            mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
            mock.patch.object(af, "invoke_route", side_effect=invoke),
            mock.patch.object(af, "emit"),
        ):
            with self.assertRaises(af.FlowError) as caught:
                af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False))
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        directory, run = af.load_run(run_id)
        self.assertEqual(run["status"], "BLOCKED")
        self.assertFalse(any(item["type"].startswith("model-call:") for item in run["artifact_index"]))

    def test_execute_stage_rejects_output_and_receipt_swaps_during_commit(self):
        for boundary in ("packet", "output", "receipt"):
            with self.subTest(boundary=boundary):
                run_id = self.start(f"Model-call {boundary} commit bytes must remain exact.")
                directory, _ = af.load_run(run_id)
                trusted = b'{"trusted": true}\n'
                tampered = b'{"tampered": true}\n'
                output_path = None
                real_immutable_write = af.immutable_write
                real_record_artifact = af.record_artifact
                real_current_packet = af.current_packet

                def swap_packet_before_hash(*args, **kwargs):
                    path, packet = real_current_packet(*args, **kwargs)
                    if boundary == "packet":
                        swapped = af.load_json(path)
                        swapped["objective"] = "Instructions swapped after task_packet returned."
                        af.write_json(path, swapped)
                    return path, packet

                def invoke(_route, _packet_path, packet):
                    nonlocal output_path
                    output_path = Path(packet["expected_outputs"][0]["path"])
                    return trusted.decode("utf-8"), {"provider": "fixture", "model": "fixture-model"}

                def mutate_after_output_write(path, data):
                    result = real_immutable_write(path, data)
                    if boundary == "output" and path.parent.name == "submissions":
                        path.write_bytes(tampered)
                    return result

                def swap_receipt_and_output(*args, **kwargs):
                    path = args[2]
                    artifact_type = args[3]
                    if boundary == "receipt" and artifact_type.startswith("model-call:"):
                        self.assertIsNotNone(output_path)
                        output_path.write_bytes(tampered)
                        swapped_receipt = af.load_json(path)
                        swapped_receipt["output_sha256"] = af.sha256_bytes(tampered)
                        af.write_json(path, swapped_receipt)
                    return real_record_artifact(*args, **kwargs)

                with (
                    mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
                    mock.patch.object(af, "current_packet", side_effect=swap_packet_before_hash),
                    mock.patch.object(af, "invoke_route", side_effect=invoke),
                    mock.patch.object(af, "immutable_write", side_effect=mutate_after_output_write),
                    mock.patch.object(af, "record_artifact", side_effect=swap_receipt_and_output),
                    mock.patch.object(af, "emit"),
                ):
                    with self.assertRaises(af.FlowError) as caught:
                        af.command_execute_stage(namespace(run_id=run_id, route=None, canary=False))
                self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
                _, blocked = af.load_run(run_id)
                self.assertEqual(blocked["status"], "BLOCKED")
                self.assertFalse(any(item["type"].startswith("model-call:") for item in blocked["artifact_index"]))

    def test_task_packet_and_gate_receipt_reject_schema_valid_commit_swaps(self):
        run_id = self.start("Task packet commit bytes must stay canonical.")
        directory, run = af.load_run(run_id)
        real_record_artifact = af.record_artifact

        def swap_task_packet(*args, **kwargs):
            path = args[2]
            artifact_type = args[3]
            if artifact_type.startswith("task-packet:"):
                swapped = af.load_json(path)
                swapped["objective"] = "Swapped instructions must never become durable evidence."
                af.write_json(path, swapped)
            return real_record_artifact(*args, **kwargs)

        with (
            mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)),
            mock.patch.object(af, "record_artifact", side_effect=swap_task_packet),
        ):
            with self.assertRaises(af.FlowError) as caught:
                af.task_packet(directory, run)
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        self.assertEqual(af.load_json(directory / "run.json")["status"], "BLOCKED")
        self.assertFalse(any(event["type"] == "TASK_DISPATCHED" for event in af._read_jsonl(directory / "events.jsonl")))

        run_id = self.start("Gate receipt commit bytes must stay canonical.")
        directory, run = af.load_run(run_id)
        with mock.patch.object(af, "route_candidates", side_effect=lambda stage, excluded_routes=None: self.route_set(stage)):
            packet_path, packet = af.task_packet(directory, run)

        def swap_gate_receipt(*args, **kwargs):
            path = args[2]
            artifact_type = args[3]
            if artifact_type.startswith("gate-receipt:"):
                swapped = af.load_json(path)
                swapped["outcome"] = "REPAIR"
                swapped["findings"] = [self.finding(1)]
                af.write_json(path, swapped)
            return real_record_artifact(*args, **kwargs)

        with mock.patch.object(af, "record_artifact", side_effect=swap_gate_receipt):
            with self.assertRaises(af.FlowError) as caught:
                af.write_gate_receipt(
                    directory,
                    run,
                    "G-RESEARCH-PLAN",
                    "PASS",
                    [],
                    {"type": "code", "version": "test"},
                    "RESEARCH_PLAN",
                    task_state="RESEARCH_PLAN",
                    task_attempt=packet["attempt"],
                    task_packet_sha256=af.sha256_path(packet_path),
                )
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        self.assertEqual(af.load_json(directory / "run.json")["status"], "BLOCKED")
        self.assertFalse(any(
            event["type"] == "GATE_RECORDED"
            and event["payload"].get("gate_id") == "G-RESEARCH-PLAN"
            for event in af._read_jsonl(directory / "events.jsonl")
        ))


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
        output_path = directory / "submissions" / "01-draft.md"
        route = lambda model: {
            "provider": "codex-cli",
            "model": model,
            "model_version": "test",
            "kind": "codex-cli",
            "eligible": True,
        }
        packet = {
            "task_packet_schema_version": "1.0.0",
            "workflow_version": run["workflow_version"],
            "run_id": run_id,
            "stage": "DRAFT",
            "attempt": 1,
            "objective": "Draft the article using the pinned writing route.",
            "inputs": [],
            "reader_job": None,
            "article_recipe": None,
            "allowed_tools": ["write_requested_output"],
            "side_effect_policy": "run_local_write",
            "constraints": [],
            "expected_outputs": [{"path": str(output_path), "format": "md"}],
            "success_criteria": ["Return a complete draft."],
            "non_authorities": [],
            "stop_conditions": [],
            "escalation_question": "What blocks this draft?",
            "selected_route": {
                "reason": "pinned writing experiment",
                "chosen": route("gpt-5.5"),
                "fallbacks": [route("gpt-5.6-sol")],
                "candidates": [route("gpt-5.5"), route("gpt-5.6-sol")],
            },
        }
        packet_path = directory / "tasks" / "draft-01.json"
        af.write_json(packet_path, packet)
        af.record_artifact(directory, run, packet_path, "task-packet:DRAFT:1", {"actor": "test"})
        run["attempts"]["DRAFT"] = 1
        af.append_event(directory, run, "TASK_DISPATCHED", "test", {
            "state": "DRAFT",
            "attempt": 1,
            "packet": packet_path.relative_to(directory).as_posix(),
            "route": packet["selected_route"],
        })
        af.save_run(directory, run)
        successful_call = {
            "provider": "codex-cli",
            "model": "gpt-5.6-sol",
            "model_version": "test",
            "elapsed_ms": 1,
            "transport": {"kind": "codex-cli", "exit_code": 0},
        }
        def submit_in_process(command, **kwargs):
            submitted_output = Path(command[command.index("--file") + 1])
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                return_code = af.command_submit(
                    namespace(run_id=run_id, stage="DRAFT", file=str(submitted_output))
                )
            return subprocess.CompletedProcess(
                args=command,
                returncode=return_code,
                stdout=stream.getvalue(),
                stderr="",
            )

        with (
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
            lifecycle = af._read_jsonl(directory / run["event_log"])
            dispatches = {
                (
                    event["payload"]["state"],
                    event["payload"]["attempt"],
                    event["payload"]["task_packet_sha256"],
                )
                for event in lifecycle
                if event["type"] == "TASK_DISPATCHED"
            }
            abandoned = {
                af.event_task_identity(event)
                for event in lifecycle
                if event["type"] == "RETRY"
            }
            self.assertIn(("RESEARCH_PLAN", cached["attempt"], af.sha256_path(cached_path)), abandoned)
            self.assertEqual(
                dispatches - abandoned,
                {("RESEARCH_PLAN", refreshed["attempt"], af.sha256_path(refreshed_path))},
            )

            _, current = af.load_run(run_id)
            same_path, same_packet = af.current_packet(
                directory,
                current,
                requested_route="fixture-command:canary-model",
                allow_canary=True,
            )
            self.assertEqual(same_path, refreshed_path)
            self.assertEqual(same_packet["attempt"], refreshed["attempt"])
            self.assertEqual(
                len([event for event in af._read_jsonl(directory / run["event_log"]) if event["type"] == "RETRY"]),
                1,
            )

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

    def test_a_voice_candidate_answers_to_the_public_prose_policy(self):
        """A selected candidate is promoted into the voice profile.

        The probe gate checked hashes, paragraph count, and comparison orders
        but never the character policy, so an operator could pick a passage
        containing a forbidden em dash and teach the profile a character the
        house style rejects everywhere else.
        """
        _, directory, run, probe_path, probe = self.prepare_voice_choice()
        outcome, findings = af.automatic_gate(directory, run, "VOICE_PROBE", probe_path)
        self.assertEqual(outcome, "PASS", findings)

        tainted = "You can see the result—and verify the exact revision yourself."
        probe["candidates"][1]["passage"] = tainted
        probe["candidates"][1]["passage_sha256"] = af.sha256_bytes(tainted.encode("utf-8"))
        af.write_json(probe_path, probe)
        outcome, findings = af.automatic_gate(directory, run, "VOICE_PROBE", probe_path)
        self.assertEqual(outcome, "REPAIR")
        flagged = [item for item in findings
                   if item["criterion"] == "forbidden_public_prose_character"]
        self.assertEqual([item["location"] for item in flagged], ["B"], findings)

        # A formulaic phrase in a candidate is caught the same way.
        cliche = "At its core, you can see the result and verify the revision."
        probe["candidates"][1]["passage"] = cliche
        probe["candidates"][1]["passage_sha256"] = af.sha256_bytes(cliche.encode("utf-8"))
        af.write_json(probe_path, probe)
        _, findings = af.automatic_gate(directory, run, "VOICE_PROBE", probe_path)
        self.assertIn("high_confidence_cliche", {item["criterion"] for item in findings})

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

    def crash_after_committed_voice_selection(self, selection="A"):
        """Commit the human choice durably, then die before the transition."""
        run_id, directory, _, probe_path, _ = self.prepare_voice_choice()
        candidate_bytes = probe_path.read_bytes()
        with (
            mock.patch.object(af, "transition", side_effect=RuntimeError("crash before voice transition")),
            mock.patch.object(af, "emit"),
        ):
            with self.assertRaises(RuntimeError):
                af.command_gate(namespace(
                    run_id=run_id,
                    gate_id="G-VOICE-PROBE",
                    outcome="PASS",
                    finding=None,
                    artifact=None,
                    selection=selection,
                    feedback=None,
                ))
        directory, crashed = af.load_run(run_id)
        self.assertEqual(crashed["state"], "VOICE_PROBE")
        return run_id, directory, crashed, probe_path, candidate_bytes

    def voice_event_counts(self, directory):
        events = af._read_jsonl(directory / "events.jsonl")
        return events, {
            "selection": [
                event for event in events
                if event["type"] == "VOICE_SELECTION_RECORDED"
            ],
            "gate_pass": [
                event for event in events
                if event["type"] == "GATE_RECORDED"
                and event["payload"].get("gate_id") == "G-VOICE-PROBE"
                and event["payload"].get("outcome") == "PASS"
            ],
            "transition": [
                event for event in events
                if event["type"] == "STATE_TRANSITION"
                and event["payload"].get("to") == "VOICE_LEARNING"
            ],
            "probe_dispatch": [
                event for event in events
                if event["type"] == "TASK_DISPATCHED"
                and event["payload"].get("state") == "VOICE_PROBE"
            ],
            "learning": [
                event for event in events
                if event["type"] == "VOICE_LEARNING_APPLIED"
            ],
        }

    def test_committed_voice_selection_survives_a_crash_before_its_transition(self):
        run_id, directory, crashed, probe_path, candidate_bytes = self.crash_after_committed_voice_selection("A")

        verified, error, _, _ = af.verify_event_log(directory, crashed)
        self.assertTrue(verified, error)
        _, counts = self.voice_event_counts(directory)
        self.assertEqual(len(counts["selection"]), 1)
        self.assertEqual(len(counts["gate_pass"]), 1)
        self.assertEqual(counts["transition"], [])

        # The code-validated candidate authority is preserved beside, not
        # replaced by, the approved probe.
        candidate_item, candidate_path = af.voice_candidate_probe(directory, crashed)
        self.assertIsNotNone(candidate_item)
        self.assertEqual(candidate_path.read_bytes(), candidate_bytes)
        self.assertIsNone(af.load_json(candidate_path)["operator_selection"])
        self.assertEqual(
            [item["candidate_id"] for item in af.load_json(candidate_path)["candidates"]],
            ["A", "B", "C"],
        )
        approved = af.load_json(af.artifact_path(directory, crashed, "voice-probe"))
        self.assertEqual(approved["operator_selection"]["candidate_id"], "A")

        committed = af.committed_voice_selection(directory, crashed)
        self.assertEqual(committed["candidate_id"], "A")

        # The controller must not re-ask a question the human already answered.
        payload = af.next_state_payload(directory, crashed)
        self.assertEqual(payload["action"], "run_command")
        self.assertEqual(payload["committed_voice_selection"], "A")
        self.assertNotEqual(af.load_json(directory / "run.json")["status"], "WAITING_HUMAN")

        # A conflicting retry fails closed and appends nothing.
        events_before = af._read_jsonl(directory / "events.jsonl")
        with mock.patch.object(af, "emit"):
            with self.assertRaises(af.FlowError) as conflict:
                af.command_gate(namespace(
                    run_id=run_id,
                    gate_id="G-VOICE-PROBE",
                    outcome="PASS",
                    finding=None,
                    artifact=None,
                    selection="B",
                    feedback=None,
                ))
        self.assertEqual(conflict.exception.code, af.EXIT_APPROVAL)
        self.assertEqual(af.load_run(run_id)[1]["state"], "VOICE_PROBE")
        self.assertEqual(af._read_jsonl(directory / "events.jsonl"), events_before)

        # Retrying the committed choice completes exactly one transition.
        with mock.patch.object(af, "emit"):
            self.assertEqual(
                af.command_choose_voice(namespace(
                    run_id=run_id, candidate_id="A", feedback=None, auto=False,
                )),
                af.EXIT_OK,
            )
        directory, reconciled = af.load_run(run_id)
        self.assertEqual(reconciled["state"], "VOICE_LEARNING")
        verified, error, _, _ = af.verify_event_log(directory, reconciled)
        self.assertTrue(verified, error)
        _, counts = self.voice_event_counts(directory)
        self.assertEqual(len(counts["selection"]), 1)
        self.assertEqual(len(counts["gate_pass"]), 1)
        self.assertEqual(len(counts["transition"]), 1)
        self.assertEqual(counts["probe_dispatch"], [])

        # Learning still runs exactly once off the single approved probe.
        af.apply_voice_learning(directory, reconciled)
        _, counts = self.voice_event_counts(directory)
        self.assertEqual(len(counts["learning"]), 1)

    def test_advance_reconciles_a_crashed_voice_commit_without_redispatch(self):
        run_id, directory, _, _, _ = self.crash_after_committed_voice_selection("C")
        with mock.patch.object(af, "emit"):
            self.assertEqual(
                af.command_advance(namespace(run_id=run_id, max_steps=1)),
                af.EXIT_WAITING,
            )
        directory, advanced = af.load_run(run_id)
        self.assertEqual(advanced["state"], "VOICE_LEARNING")
        verified, error, _, _ = af.verify_event_log(directory, advanced)
        self.assertTrue(verified, error)
        _, counts = self.voice_event_counts(directory)
        self.assertEqual(len(counts["selection"]), 1)
        self.assertEqual(len(counts["transition"]), 1)
        self.assertEqual(counts["probe_dispatch"], [])
        self.assertIsNone(af.committed_voice_selection(directory, advanced))

    def test_legacy_overwritten_probe_recovers_its_candidate_authority(self):
        """Runs stored before candidate preservation must still reconcile."""
        run_id, directory, crashed, _, candidate_bytes = self.crash_after_committed_voice_selection("B")
        # Simulate a run whose cache predates the preserved candidate record.
        stripped = af.load_json(directory / "run.json")
        stripped["artifact_index"] = [
            item for item in stripped["artifact_index"]
            if item["type"] != af.VOICE_CANDIDATE_ARTIFACT_TYPE
        ]
        af.write_json(directory / "run.json", stripped)
        directory, legacy = af.load_run(run_id)
        legacy["artifact_index"] = [
            item for item in legacy["artifact_index"]
            if item["type"] != af.VOICE_CANDIDATE_ARTIFACT_TYPE
        ]
        candidate_item, candidate_path = af.voice_candidate_probe(directory, legacy)
        self.assertIsNotNone(candidate_item)
        self.assertEqual(candidate_path.read_bytes(), candidate_bytes)
        self.assertEqual(af.committed_voice_selection(directory, legacy)["candidate_id"], "B")

    def gate_events(self, directory):
        return [
            event for event in af._read_jsonl(directory / "events.jsonl")
            if event["type"] == "GATE_RECORDED" and event["payload"].get("gate_id") == "G-VOICE-PROBE"
        ]

    def test_probe_rejected_by_its_gate_is_never_offered_as_the_human_choice(self):
        run_id, directory, run, probe_path, probe = self.prepare_voice_choice()
        # Reproduce a submission whose probe failed its code-owned checks: the
        # artifact is recorded before the gate receipt, so it survives.
        af.write_gate_receipt(
            directory, run, "G-VOICE-PROBE", "REPAIR",
            [{"criterion": "candidate_hash", "artifact": str(probe_path), "location": "A",
              "finding": "Candidate passage hash is incorrect.",
              "repair_instruction": "Hash the exact UTF-8 candidate passage."}],
            {"type": "code", "version": af.CONTROLLER_VERSION},
            "VOICE_PROBE",
        )
        af.save_run(directory, run)
        directory, rejected = af.load_run(run_id)

        self.assertFalse(af.voice_probe_awaits_human(directory, rejected))
        try:
            payload = af.next_state_payload(directory, rejected)
        except af.FlowError as exc:
            # The review branch was skipped, so the controller went on to mint
            # the next bounded attempt.  This fixture declares no model route,
            # which is itself proof the rejected probe was not offered.
            self.assertEqual(exc.code, af.EXIT_WAITING)
        else:
            self.assertNotEqual(payload["action"], "human_decision")
        self.assertNotEqual(af.load_json(directory / "run.json")["status"], "WAITING_HUMAN")

    def test_an_authorized_repair_supersedes_a_pending_voice_decision(self):
        """Regenerating the probe must not keep offering the old candidates."""
        run_id, directory, run, _, _ = self.prepare_voice_choice()
        af.write_gate_receipt(
            directory, run, "G-VOICE-PROBE", "ESCALATE",
            [{"criterion": "operator_owned_judgment", "artifact": "current", "location": None,
              "finding": "Mechanical validation passed.",
              "repair_instruction": "Ask the operator the decision question."}],
            {"type": "code", "version": af.CONTROLLER_VERSION}, "VOICE_PROBE")
        af.save_run(directory, run)
        directory, offered = af.load_run(run_id)
        self.assertTrue(af.voice_probe_awaits_human(directory, offered))

        af.append_event(directory, offered, "REPAIR", "operator_or_controller",
                        {"gate_id": "G-VOICE-PROBE", "repair_state": "VOICE_PROBE",
                         "finding": "A candidate carries a forbidden character."})
        af.save_run(directory, offered)
        directory, repaired = af.load_run(run_id)
        self.assertFalse(af.voice_probe_awaits_human(directory, repaired))

    def test_probe_that_passed_its_gate_is_still_offered(self):
        run_id, directory, run, _, _ = self.prepare_voice_choice()
        af.write_gate_receipt(
            directory, run, "G-VOICE-PROBE", "ESCALATE",
            [{"criterion": "operator_owned_judgment", "artifact": "current", "location": None,
              "finding": "Mechanical validation passed.",
              "repair_instruction": "Ask the operator the controller-supplied decision question."}],
            {"type": "code", "version": af.CONTROLLER_VERSION},
            "VOICE_PROBE",
        )
        af.save_run(directory, run)
        directory, escalated = af.load_run(run_id)

        self.assertTrue(af.voice_probe_awaits_human(directory, escalated))
        payload = af.next_state_payload(directory, escalated)
        self.assertEqual(payload["action"], "human_decision")
        self.assertEqual([item["candidate_id"] for item in payload["candidates"]], ["A", "B", "C"])

    def test_probe_recorded_without_a_gate_event_keeps_prior_behaviour(self):
        run_id, directory, run, _, _ = self.prepare_voice_choice()
        self.assertEqual(self.gate_events(directory), [])
        self.assertTrue(af.voice_probe_awaits_human(directory, run))
        self.assertEqual(af.next_state_payload(directory, run)["action"], "human_decision")

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
        if state == "VISUAL_PLAN":
            return {
                "visual_plan_schema_version": "1.0.0",
                "run_id": run_id,
                "visuals": [{
                    "visual_id": "proof-boundary",
                    "kind": "trend_gap",
                    "title": "Proof stays tied to the artifact",
                    "purpose": "Show that public visibility and private verification are separate concerns.",
                    "placement": {"after_heading": "What the check proves"},
                    "alt_text": "Two conceptual lines distinguish a visible public result from the private evidence that verifies it.",
                    "caption": "Conceptual comparison of public visibility and hash-bound verification.",
                    "claim_ids": [],
                    "labels": ["Visible result", "Verified artifact"],
                }],
            }
        if state == "VOICE_PROBE":
            passages = [
                ("The page is visible, and its recorded revision identifies the result.", "precision"),
                ("You can inspect the page and verify the exact recorded revision.", "directness"),
                ("A visible page only proves something when its recorded revision matches.", "skepticism"),
            ]
            return {
                "voice_candidates_schema_version": "1.0.0",
                "run_id": run_id,
                "article_register": {"technical_depth": "moderate"},
                "candidates": [{
                    "passage": passage,
                    "intended_dimensions": [dimension],
                    "preserved_claim_ids": [],
                } for passage, dimension in passages],
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


class SourceResolutionRegressionTests(TemporaryRuntime):
    def test_malformed_source_url_fails_closed_instead_of_crashing(self):
        """A model may join several URLs into one source field.

        ``urlopen`` raises ``http.client.InvalidURL`` for that, which derives
        from ``ValueError`` rather than ``OSError``, so it used to escape
        ``fetch_url`` and abort the whole run with an unhandled traceback.
        """
        joined = "https://example.com/a ; https://example.com/b"
        status, body, headers = af.fetch_url(joined, timeout=1)
        self.assertEqual(status, -1)
        self.assertEqual(body, b"")
        self.assertEqual(headers, {})
        self.assertEqual(af.fetch_url("not-a-url", timeout=1)[0], -1)

        run_id = self.start()
        directory, run = af.load_run(run_id)
        run["state"] = "CLAIM_VERIFICATION"
        ledger = self.runtime / "malformed-source-ledger.json"
        ledger.write_text(json.dumps({
            "claim_ledger_schema_version": "1.0.0",
            "run_id": run_id,
            "generated_at": af.utc_now(),
            "claims": [{
                "claim_id": "C1", "exact_claim": "A joined-source claim.", "class": "fact", "risk": "medium",
                "source_tier": "primary", "source_url_or_local_id": joined,
                "source_title_and_publisher": "Example", "exact_locator_or_supporting_excerpt": "Supporting text",
                "checked_at": af.utc_now(), "freshness_horizon": "one year", "contradiction_status": "none_found",
                "allowed_wording": "A joined-source claim.", "confidence": 0.8, "disposition": "use",
            }],
        }), encoding="utf-8")
        outcome, findings = af.automatic_gate(directory, run, "CLAIM_VERIFICATION", ledger)
        self.assertEqual(outcome, "REPAIR", findings)
        resolution = [item for item in findings if item["criterion"] == "source_resolution"]
        self.assertEqual(len(resolution), 1, findings)
        self.assertIn("not a single well-formed URL", resolution[0]["finding"])

        # An unreachable host stays transport-impossible and is still accepted.
        with mock.patch.object(af, "fetch_url", return_value=(0, b"", {})):
            outcome, findings = af.automatic_gate(directory, run, "CLAIM_VERIFICATION", ledger)
        self.assertNotIn("source_resolution", {item["criterion"] for item in findings})


class DraftCoverageRegressionTests(TemporaryRuntime):
    CLAIMS = [
        "Model upgrades do not automatically update the schemas and counters that surround a model.",
        "An output schema fixed at integration time can outlive the capability that motivated it.",
        "A turn budget chosen for an earlier model can persist as an unexamined default.",
        "Recognizing a fossilized assumption requires evidence of an explicit application-layer constraint.",
    ]

    def draft_run(self, claims):
        run_id = self.start("Coverage must be checked against the brief.")
        directory, run = af.load_run(run_id)
        self.record_json(directory, run, "brief", {
            "brief_schema_version": "1.0.0",
            "run_id": run_id,
            "title": "Fossilized defaults",
            "slug": "fossilized-defaults",
            "description": "Diagnosing inherited application-layer constraints.",
            "reader_job": "Recognize a stale default.",
            "scope": "Diagnosis only.",
            "exclusions": [],
            "claims_to_support": claims,
            "acceptance_criteria": ["Every required claim is argued."],
        })
        run["state"] = "DRAFT"
        return directory, run

    def test_unwritten_draft_is_repaired_instead_of_passing_coverage(self):
        directory, run = self.draft_run(self.CLAIMS)
        stub = self.root / "stub-draft.md"
        stub.write_text(
            "Unresolved: required commit permalink for a mutable source-code citation is missing, "
            "so the DRAFT stage cannot complete without guessing.\n",
            encoding="utf-8",
        )
        outcome, findings = af.automatic_gate(directory, run, "DRAFT", stub)
        self.assertEqual(outcome, "REPAIR")
        coverage = [item for item in findings if item["criterion"] == "brief_claim_coverage"]
        self.assertEqual(len(coverage), len(self.CLAIMS) + 1, findings)
        self.assertIn("covers 0 of the 4 claims", coverage[0]["finding"])
        self.assertEqual(coverage[1]["location"], "claims_to_support[0]")

    def test_draft_that_argues_the_brief_passes_coverage(self):
        directory, run = self.draft_run(self.CLAIMS)
        article = self.root / "real-draft.md"
        article.write_text(
            "# Fossilized defaults\n"
            "\n"
            "Model upgrades do not automatically update the schemas and counters that\n"
            "surround a model. An output schema fixed at integration time can outlive the\n"
            "capability that motivated it, and a turn budget chosen for an earlier model\n"
            "can persist as an unexamined default long after anyone examined it.\n"
            "\n"
            "Recognizing a fossilized assumption requires evidence of an explicit\n"
            "application-layer constraint, not merely a disappointing result.\n",
            encoding="utf-8",
        )
        outcome, findings = af.automatic_gate(directory, run, "DRAFT", article)
        self.assertEqual(outcome, "PASS", findings)

    def test_brief_without_declared_claims_keeps_prior_behaviour(self):
        directory, run = self.draft_run([])
        stub = self.root / "unclaimed-draft.md"
        stub.write_text("# Short\n\nA brief that declares no claims cannot fail coverage.\n", encoding="utf-8")
        outcome, findings = af.automatic_gate(directory, run, "DRAFT", stub)
        self.assertEqual(outcome, "PASS", findings)
        self.assertEqual([item for item in findings if item["criterion"] == "brief_claim_coverage"], [])


class NaturalizationCitationLockTests(TemporaryRuntime):
    """A required citation the draft never carried must be addable.

    Claim verification can accept a claim the draft did not cite. The article
    then has to add that source link, but ``urls`` is a locked token category,
    so an exact-token rule makes the citation gate and the lock unsatisfiable
    together and burns the whole naturalization window.
    """

    DRAFT = (
        "# Fossilized defaults\n"
        "\n"
        "A turn budget can outlive its cause. See https://example.com/docs/turns for the recorded default.\n"
    )
    KEPT_URL = "https://example.com/docs/turns"
    NEW_URL = "https://example.com/papers/reasoning.pdf"

    def edit_run(self, *, record_additions=True):
        run_id = self.start("Naturalization must be able to add a required citation.")
        directory, run = af.load_run(run_id)
        draft_path = self.record_text(directory, run, "draft", self.DRAFT, "draft.md")
        self.record_json(directory, run, "article-recipe", {"citation_mode": "links"}, "article-recipe.json")
        locked = {
            "locked_fields_schema_version": "1.0.0",
            "run_id": run_id,
            "source_sha256": af.sha256_path(draft_path),
            "tokens": af.find_locked_tokens(self.DRAFT),
            "claims": [
                {"claim_id": "CL-1", "risk": "high", "allowed_wording": "A turn budget can outlive its cause.",
                 "source_url_or_local_id": self.KEPT_URL, "checked_at": af.utc_now()},
                {"claim_id": "CL-2", "risk": "high", "allowed_wording": "The reasoning result is documented.",
                 "source_url_or_local_id": self.NEW_URL, "checked_at": af.utc_now()},
            ],
        }
        if record_additions:
            locked["citation_additions"] = [self.NEW_URL]
        self.record_json(directory, run, "locked-fields", locked, "locked-fields.json")
        run["state"] = "EDIT"
        return directory, run

    def article(self, *, keep_locked_url=True, extra_line=""):
        first = (
            "A turn budget can outlive the constraint that produced it. See %s for the recorded default.\n"
            % self.KEPT_URL
        ) if keep_locked_url else "A turn budget can outlive the constraint that produced it.\n"
        return (
            "# Fossilized defaults\n"
            "\n"
            + first
            + "The reasoning result is recorded in [the linked paper](%s).\n" % self.NEW_URL
            + extra_line
        )

    def gate(self, directory, run, text):
        path = self.root / "edited-article.md"
        path.write_text(text, encoding="utf-8")
        return af.automatic_gate(directory, run, "EDIT", path)

    def test_naturalization_may_add_a_required_citation_the_draft_lacked(self):
        directory, run = self.edit_run()
        outcome, findings = self.gate(directory, run, self.article())
        self.assertEqual(outcome, "PASS", findings)

    def test_locked_fields_without_recorded_additions_derives_them(self):
        directory, run = self.edit_run(record_additions=False)
        outcome, findings = self.gate(directory, run, self.article())
        self.assertEqual(outcome, "PASS", findings)

    def test_repeating_a_locked_value_is_not_a_change(self):
        """Naturalization rewrites sentences, so mention counts move."""
        # A value the draft never carried is still an introduction.
        directory, run = self.edit_run()
        introduced = self.article(
            extra_line="The recorded default has stood since 2019.\n"
        )
        outcome, findings = self.gate(directory, run, introduced)
        self.assertEqual(outcome, "REPAIR")
        self.assertIn("locked_fields", {item["criterion"] for item in findings})

        # Saying an already verified value one more time is not a change.
        directory, run = self.edit_run()
        repeated = self.article(
            extra_line="See %s once more for that same recorded default.\n" % self.KEPT_URL
        )
        outcome, findings = self.gate(directory, run, repeated)
        self.assertEqual(outcome, "PASS", findings)

    def test_a_permitted_citation_never_strips_a_locked_url_that_extends_it(self):
        """Only whole URL tokens may be removed before locked tokens compare.

        A required citation can be a prefix of a URL the draft already carried.
        Removing it as a bare substring would destroy the locked URL and report
        it as deleted, rejecting an article that changed nothing.
        """
        parent = "https://example.com/docs/guide"
        deep = "https://example.com/docs/guide/turns"
        article = "Draft cites [deep](%s) and required [parent](%s).\n" % (deep, parent)
        stripped = af.strip_citation_additions(article, {parent})
        urls = af.find_locked_tokens(stripped)["urls"]
        self.assertEqual(urls, [deep])

        # The reverse nesting must also survive.
        stripped = af.strip_citation_additions(
            "Draft cites [parent](%s) and required [deep](%s).\n" % (parent, deep), {deep})
        self.assertEqual(af.find_locked_tokens(stripped)["urls"], [parent])

    def test_an_unverified_locked_url_may_be_replaced_by_the_verified_one(self):
        """The draft's address is not evidence; the ledger's is.

        A draft may cite a legacy host while verification records the current
        one. Locking the draft's variant made the citation gate and the lock
        unsatisfiable together, and editorial QA then asked for the deletion
        the lock forbade.
        """
        legacy = "https://proceedings.nips.cc/paper/2015/file/abc-Paper.pdf"
        verified = "https://proceedings.neurips.cc/paper_files/paper/2015/file/abc-Paper.pdf"
        draft_text = (
            "# Fossilized defaults\n"
            "\n"
            "A turn budget can outlive its cause, as noted [in the paper](%s).\n" % legacy
        )
        run_id = self.start("An unverified locked URL must not block the verified one.")
        directory, run = af.load_run(run_id)
        draft_path = self.record_text(directory, run, "draft", draft_text, "draft.md")
        self.record_json(directory, run, "article-recipe", {"citation_mode": "links"},
                         "article-recipe.json")
        self.record_json(directory, run, "locked-fields", {
            "locked_fields_schema_version": "1.0.0",
            "run_id": run_id,
            "source_sha256": af.sha256_path(draft_path),
            "tokens": af.find_locked_tokens(draft_text),
            "claims": [{
                "claim_id": "CL-1", "risk": "high", "allowed_wording": "A turn budget can outlive its cause.",
                "source_url_or_local_id": verified, "checked_at": af.utc_now(),
            }],
            "citation_additions": [verified],
        }, "locked-fields.json")
        run["state"] = "EDIT"

        self.assertEqual(
            af.unverified_locked_urls(af.json_artifact(directory, run, "locked-fields")),
            {legacy},
        )

        replaced = self.root / "replaced-article.md"
        replaced.write_text(
            "# Fossilized defaults\n"
            "\n"
            "A turn budget can outlive its cause, as noted [in the paper](%s).\n" % verified,
            encoding="utf-8",
        )
        outcome, findings = af.automatic_gate(directory, run, "EDIT", replaced)
        self.assertEqual(outcome, "PASS", findings)

        # The verified address itself still may not be dropped.
        dropped = self.root / "dropped-article.md"
        dropped.write_text(
            "# Fossilized defaults\n\nA turn budget can outlive its cause.\n", encoding="utf-8")
        outcome, findings = af.automatic_gate(directory, run, "EDIT", dropped)
        self.assertEqual(outcome, "REPAIR")
        self.assertIn("claim_citation_mapping", {item["criterion"] for item in findings})

    def test_removing_a_locked_url_still_fails(self):
        directory, run = self.edit_run()
        outcome, findings = self.gate(directory, run, self.article(keep_locked_url=False))
        self.assertEqual(outcome, "REPAIR")
        self.assertIn("locked_fields", {item["criterion"] for item in findings})

    def test_locked_field_findings_name_the_values_that_changed(self):
        """The finding is the writer's whole instruction on the next attempt."""
        directory, run = self.edit_run()
        text = self.article(keep_locked_url=False,
                            extra_line="Background lives at https://example.com/unrelated/page.\n")
        outcome, findings = self.gate(directory, run, text)
        self.assertEqual(outcome, "REPAIR")
        locked = [item for item in findings if item["criterion"] == "locked_fields"]
        urls = next(item for item in locked if item["location"] == "urls")
        self.assertIn(self.KEPT_URL, urls["finding"])
        self.assertIn("removed", urls["finding"])
        self.assertIn("https://example.com/unrelated/page", urls["finding"])
        self.assertIn("added", urls["finding"])
        self.assertIn("citation", urls["repair_instruction"])

    def test_adding_an_unrelated_url_still_fails(self):
        directory, run = self.edit_run()
        text = self.article(extra_line="Background lives at https://example.com/unrelated/page.\n")
        outcome, findings = self.gate(directory, run, text)
        self.assertEqual(outcome, "REPAIR")
        locked = [item for item in findings if item["criterion"] == "locked_fields"]
        self.assertEqual([item["location"] for item in locked], ["urls"], findings)


class DisplayTextAmendmentTests(TemporaryRuntime):
    """The brief owns public display text and no later stage can repair it.

    Editorial QA reports a bad title or description but repairs to EDIT, which
    rewrites only the article, so the finding could never be cleared.
    """

    def brief_value(self, run_id, description):
        return {
            "brief_schema_version": "1.0.0",
            "run_id": run_id,
            "title": "Is the model limiting you, or the product around it",
            "slug": "is-the-model-limiting-you",
            "description": description,
            "reader_job": "Recognize an inherited default.",
            "scope": "Diagnosis only.",
            "exclusions": [],
            "claims_to_support": [],
            "acceptance_criteria": ["Every required claim is argued."],
        }

    def test_brief_gate_rejects_forbidden_display_characters(self):
        run_id = self.start("Display text is checked where it can still be repaired.")
        directory, run = af.load_run(run_id)
        path = self.root / "brief-with-em-dash.json"
        af.write_json(path, self.brief_value(
            run_id, "A teardown of inherited defaults—and the evidence needed."))
        outcome, findings = af.automatic_gate(directory, run, "BRIEF", path)
        self.assertEqual(outcome, "REPAIR")
        display = [item for item in findings if item.get("location") == "description"]
        self.assertTrue(display, findings)
        self.assertIn("em dash", display[0]["finding"])

    def test_brief_gate_passes_clean_display_text(self):
        run_id = self.start("Clean display text passes the brief gate.")
        directory, run = af.load_run(run_id)
        path = self.root / "clean-brief.json"
        af.write_json(path, self.brief_value(
            run_id, "A teardown of inherited defaults, and the evidence needed."))
        outcome, findings = af.automatic_gate(directory, run, "BRIEF", path)
        self.assertEqual(outcome, "PASS", findings)

    def amend_run(self, state):
        run_id = self.start("Display text stays correctable while the article is reviewed.")
        directory, run = af.load_run(run_id)
        self.record_json(directory, run, "brief",
                         self.brief_value(run_id, "Inherited defaults, and the evidence needed."),
                         "brief.json")
        self.record_text(directory, run, "article", "# Title\n\nBody text.\n", "article.md")
        af.transition(directory, run, state, "test", "exercise display-text amendment")
        return run_id, directory

    def test_display_text_amendment_before_packaging_keeps_the_state(self):
        run_id, directory = self.amend_run("EDITORIAL_QA")
        with mock.patch.object(af, "emit"):
            code = af.command_amend(namespace(
                run_id=run_id, title=None, description="A clean replacement description.", article=None))
        self.assertEqual(code, af.EXIT_OK)
        _, after = af.load_run(run_id)
        # Advancing to PACKAGE here would skip the gate that asked for the fix.
        self.assertEqual(after["state"], "EDITORIAL_QA")
        self.assertEqual(
            af.json_artifact(directory, after, "brief")["description"],
            "A clean replacement description.",
        )

    def test_article_amendment_still_requires_packaging(self):
        run_id, _ = self.amend_run("EDITORIAL_QA")
        replacement = self.root / "replacement-article.md"
        replacement.write_text("# Title\n\nReplacement body.\n", encoding="utf-8")
        with self.assertRaises(af.FlowError) as caught:
            af.command_amend(namespace(
                run_id=run_id, title=None, description=None, article=str(replacement)))
        self.assertIn("PACKAGE", str(caught.exception))

    def test_display_text_amendment_at_publish_approval_rebuilds_the_package(self):
        run_id, _ = self.amend_run("PUBLISH_APPROVAL")
        with mock.patch.object(af, "emit"):
            af.command_amend(namespace(
                run_id=run_id, title=None, description="Another clean description.", article=None))
        _, after = af.load_run(run_id)
        self.assertEqual(after["state"], "PACKAGE")

    def test_amended_display_text_is_validated_before_it_is_recorded(self):
        run_id, _ = self.amend_run("EDITORIAL_QA")
        with self.assertRaises(af.FlowError) as caught:
            af.command_amend(namespace(
                run_id=run_id, title=None,
                description="Still inherited defaults—and the evidence needed.", article=None))
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)


class RepairDestinationTests(TemporaryRuntime):
    """A gate rejects for two different reasons and they need different repairs."""

    def ledger(self, run_id, source):
        return {
            "claim_ledger_schema_version": "1.0.0",
            "run_id": run_id,
            "generated_at": af.utc_now(),
            "claims": [{
                "claim_id": "C1", "exact_claim": "A supported claim.", "class": "fact",
                "risk": "medium", "source_tier": "primary", "source_url_or_local_id": source,
                "source_title_and_publisher": "Example",
                "exact_locator_or_supporting_excerpt": "Supporting text",
                "checked_at": af.utc_now(), "freshness_horizon": "one year",
                "contradiction_status": "none_found", "allowed_wording": "A supported claim.",
                "confidence": 0.8, "disposition": "use",
            }],
        }

    def test_post_edit_ledger_findings_repair_the_ledger_not_the_article(self):
        run_id = self.start("A malformed ledger must not rewrite the article.")
        directory, run = af.load_run(run_id)
        run["state"] = "POST_EDIT_CLAIM_VERIFICATION"
        path = self.root / "joined-source-ledger.json"
        path.write_text(
            json.dumps(self.ledger(run_id, "https://example.com/a ; https://example.com/b")),
            encoding="utf-8",
        )
        outcome, findings = af.automatic_gate(directory, run, "POST_EDIT_CLAIM_VERIFICATION", path)
        self.assertEqual(outcome, "REPAIR")
        self.assertTrue(findings)
        self.assertEqual({item["repair_state"] for item in findings}, {"POST_EDIT_CLAIM_VERIFICATION"})

        definition = af.state_definition("POST_EDIT_CLAIM_VERIFICATION", run)
        # The workflow declaration is deliberately unchanged.
        self.assertEqual(definition["repair_state"], "EDIT")
        self.assertEqual(
            af.effective_repair_state(definition, findings), "POST_EDIT_CLAIM_VERIFICATION")

    def test_the_declared_state_still_governs_without_directed_findings(self):
        run_id = self.start("Operator escalation still reaches the article.")
        _, run = af.load_run(run_id)
        definition = af.state_definition("POST_EDIT_CLAIM_VERIFICATION", run)
        # An operator repair after the window is spent carries no directed
        # findings, so it still escalates to the article.
        self.assertEqual(af.effective_repair_state(definition, []), "EDIT")
        # Findings that disagree fall back to the declaration rather than
        # guessing which one wins.
        mixed = [{"repair_state": "EDIT"}, {"repair_state": "POST_EDIT_CLAIM_VERIFICATION"}]
        self.assertEqual(af.effective_repair_state(definition, mixed), "EDIT")

    def test_a_receipt_without_a_destination_recovers_one_from_its_criteria(self):
        """Runs recorded before findings carried a destination still route."""
        run_id = self.start("A legacy receipt still names ledger criteria.")
        _, run = af.load_run(run_id)
        definition = af.state_definition("POST_EDIT_CLAIM_VERIFICATION", run)
        legacy = [
            {"criterion": "source_resolution", "artifact": "x", "location": "C1",
             "finding": "Source URL is not a single well-formed URL.",
             "repair_instruction": "Give exactly one direct source URL."},
        ]
        self.assertEqual(
            af.effective_repair_state(definition, legacy), "POST_EDIT_CLAIM_VERIFICATION")

        # A finding about anything else keeps the declared escalation.
        other = [
            {"criterion": "operator_review", "artifact": "x", "location": None,
             "finding": "The article overstates the case.",
             "repair_instruction": "Soften the claim."},
        ]
        self.assertEqual(af.effective_repair_state(definition, other), "EDIT")

        # A mixture is ambiguous, so it falls back rather than guessing.
        self.assertEqual(af.effective_repair_state(definition, legacy + other), "EDIT")

    def test_a_model_may_not_choose_where_its_rejection_is_repaired(self):
        """Repair routing is a controller decision, not an assessment's.

        Editorial QA findings come from the model and are relayed verbatim. A
        live run returned `repair_state: "unresolved-attempt-exhausted"`, which
        is not a workflow state at all, and routing followed it.
        """
        run_id = self.start("A model must not choose the repair destination.")
        directory, run = af.load_run(run_id)
        run["state"] = "EDITORIAL_QA"
        assessment = self.root / "editorial-qa.json"
        assessment.write_text(json.dumps({
            "editorial_assessment_schema_version": "1.0.0",
            "run_id": run_id,
            "outcome": "REPAIR",
            "findings": [{
                "criterion": "naturalness",
                "artifact": "article",
                "location": "body",
                "finding": "A passage reads as assembled.",
                "repair_instruction": "Rewrite the affected passage.",
                "repair_state": "unresolved-attempt-exhausted",
            }],
        }), encoding="utf-8")
        _, findings = af.automatic_gate(directory, run, "EDITORIAL_QA", assessment)
        relayed = [item for item in findings if item.get("criterion") == "naturalness"]
        self.assertTrue(relayed)
        self.assertNotIn("repair_state", relayed[0])

        # Even if one reached the router, only the implicated stages are routable.
        definition = af.state_definition("EDITORIAL_QA", run)
        forged = [{"criterion": "x", "repair_state": "PUBLISH"}]
        self.assertEqual(af.effective_repair_state(definition, forged), definition["repair_state"])

    def test_claim_verification_is_unaffected(self):
        run_id = self.start("A stage that already self-repairs is unchanged.")
        directory, run = af.load_run(run_id)
        run["state"] = "CLAIM_VERIFICATION"
        path = self.root / "cv-ledger.json"
        path.write_text(
            json.dumps(self.ledger(run_id, "https://example.com/a ; https://example.com/b")),
            encoding="utf-8",
        )
        _, findings = af.automatic_gate(directory, run, "CLAIM_VERIFICATION", path)
        definition = af.state_definition("CLAIM_VERIFICATION", run)
        self.assertEqual(definition["repair_state"], "CLAIM_VERIFICATION")
        self.assertEqual(af.effective_repair_state(definition, findings), "CLAIM_VERIFICATION")


class PublicationAtomicityTests(TemporaryRuntime):
    """A refused publication must leave the target repository untouched.

    Publication copies approved files into the live site checkout. Checking
    and writing in one pass left it partially published when a later file had
    moved, and the resulting dirty checkout was then refused by the
    clean-checkout guard, so the run could neither finish nor retry.
    """

    def controller_source(self):
        return (SPEC_ROOT / "scripts" / "article_flow.py").read_text(encoding="utf-8")

    def test_every_target_is_verified_before_any_is_written(self):
        body = self.controller_source()
        self.assertLess(
            body.index("Publication target changed after planning"),
            body.index("atomic_write(repository / rel"),
            "verification must precede every write",
        )
        self.assertNotIn(
            "atomic_write(destination, source.read_bytes())",
            body,
            "writing inside the verification loop publishes partially",
        )

    def unbound_global_reads(self):
        """Names a function reads that resolve to a global that does not exist.

        Python binds such a name at call time, so an undefined local inside a
        rarely-taken branch compiles cleanly and raises NameError only when
        that branch is reached.  Both publication staleness recoveries shipped
        that way: their tests sliced the controller's source and matched the
        very lines that were broken.  CPython's symbol table answers the
        question the source text cannot.
        """
        source = (SPEC_ROOT / "scripts" / "article_flow.py").read_text(encoding="utf-8")
        table = symtable.symtable(source, "article_flow.py", "exec")
        known = {
            symbol.get_name()
            for symbol in table.get_symbols()
            if symbol.is_assigned() or symbol.is_imported()
        } | set(dir(builtins))
        found = set()

        def walk(scope, path):
            for symbol in scope.get_symbols():
                if (
                    scope.get_type() == "function"
                    and symbol.is_referenced()
                    and symbol.is_global()
                    and symbol.get_name() not in known
                ):
                    found.add((path, symbol.get_name()))
            for child in scope.get_children():
                walk(child, path + "." + child.get_name())

        walk(table, "<module>")
        return found

    def test_no_controller_function_reads_an_unbound_name(self):
        self.assertEqual(self.unbound_global_reads(), set())

    def test_the_scope_check_detects_an_unbound_name(self):
        """The guard is worthless if it cannot fail."""
        source = "def publish():\n    plan_path.unlink()\n"
        table = symtable.symtable(source, "sample.py", "exec")
        scope = table.get_children()[0]
        unbound = [
            symbol.get_name()
            for symbol in scope.get_symbols()
            if symbol.is_referenced() and symbol.is_global() and symbol.get_name() not in set(dir(builtins))
        ]
        self.assertEqual(unbound, ["plan_path"])

    def stale_publication_run(self):
        """A run at PUBLISH whose plan was built against an earlier head."""
        repository = self.root / "target-repo"
        (repository / "docs").mkdir(parents=True)
        (repository / "docs" / "article.html").write_text("<h1>old</h1>\n", encoding="utf-8")
        af.git(["init", "--quiet"], cwd=repository)
        # The publication lock derives its identity from the push remote.
        af.git(["remote", "add", "origin", "https://example.invalid/site.git"], cwd=repository)
        af.git(["-c", "user.email=t@example.com", "-c", "user.name=t", "add", "-A"], cwd=repository)
        af.git(["-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "--quiet", "-m", "base"], cwd=repository)

        run_id = self.start("A stale publication plan must not strand the run.")
        directory, run = af.load_run(run_id)
        af.transition(directory, run, "PUBLISH", "test", "exercise stale publication")
        plan_path = directory / "publication" / "plan.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        af.write_json(plan_path, {
            "package_revision": "rev-1",
            "target": "theproductiveprompter",
            "base_commit": "0" * 40,
            "changes": [{
                "path": "docs/article.html",
                "current_sha256": af.sha256_path(repository / "docs" / "article.html"),
            }],
        })
        approval_id = "AP-stale"
        (directory / "approvals").mkdir(parents=True, exist_ok=True)
        af.write_json(directory / "approvals" / f"{approval_id}.json", {
            "package_revision": "rev-1",
            "target": "theproductiveprompter",
            "plan_sha256": af.sha256_path(plan_path),
            "expires_at": (af.dt.datetime.now(af.dt.timezone.utc) + af.dt.timedelta(hours=1)).isoformat(),
        })
        return run_id, repository, plan_path, approval_id

    def test_a_moved_target_head_returns_to_approval(self):
        """The failure that stranded a live run, exercised end to end.

        Its predecessor asserted on the controller's source text and passed
        while the branch it described raised NameError on every call.
        """
        run_id, repository, plan_path, approval_id = self.stale_publication_run()
        args = namespace(run_id=run_id, approval=approval_id, commit=False, push=False, json=True)
        with mock.patch.object(af, "publication_repo_root", return_value=repository), \
                mock.patch.dict(os.environ, {"ARTICLE_FLOW_TEST_NO_PUBLISH": "0"}):
            with self.assertRaises(af.FlowError) as caught:
                af.command_publish_execute(args)
        self.assertEqual(caught.exception.code, af.EXIT_WAITING)
        self.assertIn("fresh plan is required", str(caught.exception))
        # Returning to approval is what makes the recovery reachable, and the
        # stale plan must not survive to be approved again verbatim.
        _, after = af.load_run(run_id)
        self.assertEqual(after["state"], "PUBLISH_APPROVAL")
        self.assertFalse(plan_path.is_file())
        self.assertEqual(str(af.git(["status", "--porcelain"], cwd=repository)).strip(), "")



class SoleHumanGateTests(TemporaryRuntime):
    """The voice choice must remain the only pause in an automated run."""

    def test_only_the_voice_gate_is_operator_owned(self):
        run_id = self.start("Exactly one gate may wait on a person.")
        _, run = af.load_run(run_id)
        overrides = run["run_overrides"]
        self.assertEqual(overrides["voice_probe_approval"], "required")
        for field in ("intent_approval", "recipe_approval", "editorial_approval"):
            self.assertEqual(overrides[field], "policy", field)
        human = [
            state["id"] for state in af.workflow_for_run(run)["states"]
            if state.get("normal_action") == "human_decision"
        ]
        self.assertEqual(human, ["VOICE_PROBE"])

    def test_soft_policy_review_is_eligible_for_automatic_acceptance(self):
        run_id = self.start("A spent soft review must not become a second stop.")
        _, run = af.load_run(run_id)
        # Editorial QA is soft and delegated to policy, so a spent window is
        # accepted with its findings recorded rather than blocking.
        self.assertEqual(af.gate_class("G-EDITORIAL-QA"), "soft")
        self.assertIn("EDITORIAL_QA", af.AUTO_REVIEW_STATES)
        # The voice probe is soft too but is never policy-owned, so it still
        # waits for the operator.
        self.assertEqual(af.gate_class("G-VOICE-PROBE"), "soft")
        self.assertNotIn("VOICE_PROBE", af.AUTO_REVIEW_STATES)
        # Every code-owned gate keeps blocking.
        for gate in ("G-POST-EDIT-CLAIMS", "G-CLAIMS-VERIFIED", "G-NATURALIZATION",
                     "G-PACKAGE-INTEGRITY", "G-PUBLISH-REVISION"):
            self.assertEqual(af.gate_class(gate), "hard", gate)


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


class WorkflowV31RegressionTests(TemporaryRuntime):
    def test_visual_plan_has_an_automatable_controller_route(self):
        registry = json.loads(
            (SPEC_ROOT / "evaluations" / "capability-registry.json").read_text(encoding="utf-8")
        )
        codex = next(item for item in registry["providers"] if item["provider_id"] == "codex-cli")
        sol = next(item for item in codex["models"] if item["model_id"] == "gpt-5.6-sol")
        self.assertIn("VISUAL_PLAN", sol["stages"])

        with (
            mock.patch.object(af, "evidenced_codex_canary_status", return_value="passed"),
            mock.patch.object(af.shutil, "which", return_value="/usr/bin/codex"),
        ):
            routes = af.route_candidates("VISUAL_PLAN")
            selected = af.prefer_controller_route(
                {"workflow_version": "3.1.0", "run_overrides": {"automation_mode": "active_session"}},
                "VISUAL_PLAN",
                routes,
            )
        self.assertEqual(selected["chosen"]["kind"], "codex-cli")
        self.assertEqual(selected["chosen"]["model"], "gpt-5.6-sol")

    def test_pending_agent_packet_refreshes_when_controller_route_becomes_available(self):
        run_id = self.start("Explain why a product default can lag a model.")
        directory, run = af.load_run(run_id)
        self.record_text(directory, run, "draft", "# A useful draft\n")
        for artifact_type in ("brief", "article-recipe", "claim-ledger"):
            self.record_json(directory, run, artifact_type, {"run_id": run_id})
        run["run_overrides"]["automation_mode"] = "active_session"
        af.save_run(directory, run)
        af.transition(directory, run, "VISUAL_PLAN", "test", "Exercise route refresh")

        hosted = {
            "provider": "active-host", "model": "active-capable-host", "kind": "agent-hosted",
            "eligible": True, "evaluation_score": None,
        }
        controller = {
            "provider": "codex-cli", "model": "gpt-5.6-sol", "kind": "codex-cli",
            "eligible": True, "evaluation_score": None,
        }

        def selection(chosen):
            return {
                "stage": "VISUAL_PLAN", "required_capabilities": ["structured-output"],
                "candidates": [chosen], "chosen": chosen, "fallbacks": [],
                "reason": "test route", "configuration_path": "test",
            }

        with mock.patch.object(af, "route_candidates", return_value=selection(hosted)):
            first_path, first_packet = af.task_packet(directory, run)
        self.assertEqual(first_packet["selected_route"]["chosen"]["kind"], "agent-hosted")

        directory, run = af.load_run(run_id)
        with mock.patch.object(af, "route_candidates", return_value=selection(controller)):
            second_path, second_packet = af.current_packet(directory, run)
        self.assertNotEqual(first_path, second_path)
        self.assertEqual(second_packet["attempt"], 2)
        self.assertEqual(second_packet["selected_route"]["chosen"]["kind"], "codex-cli")
        retry = next(
            event for event in reversed(af._read_jsonl(directory / "events.jsonl"))
            if event["type"] == "RETRY"
        )
        self.assertEqual(retry["payload"]["reason"], "controller_route_became_available")

    def live_verification_fixture(self, *, valid_article: bool = True):
        run_id = self.start("Verify a bounded live deployment.")
        directory, run = af.load_run(run_id)
        package_root = directory / "package"
        site_root = package_root / "site"
        public_root = package_root / "public"
        (site_root / "docs").mkdir(parents=True, exist_ok=True)
        public_root.mkdir(parents=True, exist_ok=True)
        target = af.load_json(SPEC_ROOT / "publication" / "theproductiveprompter.json")
        slug = "bounded-live-verification"
        article_url = target["canonical_url"].format(slug=slug)
        article_markdown = public_root / "article.md"
        af.atomic_write(article_markdown, b"# Bounded Live Verification\n")
        article_revision = af.sha256_path(article_markdown)
        if valid_article:
            article = (
                '<html><head><title>Bounded Live Verification</title>'
                f'<link rel="canonical" href="{article_url}">'
                f'<meta property="og:url" content="{article_url}">'
                f'<meta name="article-flow-revision" content="{article_revision}">'
                f'<script type="application/ld+json">{{"@type": "BlogPosting", "url": "{article_url}"}}</script>'
                '</head><body>Published</body></html>'
            ).encode("utf-8")
        else:
            article = b"<html><head><title>Bounded Live Verification</title></head><body>Published</body></html>"
        surfaces = {
            "article": site_root / "docs" / f"{slug}.html",
            "blog": site_root / "docs" / "blog.html",
            "homepage": site_root / "index.html",
            "feed": site_root / "feed.xml",
            "sitemap": site_root / "sitemap.xml",
        }
        af.atomic_write(surfaces["article"], article)
        for name in ("blog", "homepage", "feed", "sitemap"):
            af.atomic_write(surfaces[name], f'<a href="{article_url}">article</a>'.encode("utf-8"))
        af.write_json(package_root / "package.json", {"package_revision": "fixture-revision"})
        af.write_json(public_root / "metadata.json", {"slug": slug, "title": "Bounded Live Verification"})
        af.write_json(public_root / "assets.json", {"assets": []})
        af.transition(directory, run, "LIVE_VERIFICATION", "test", "Exercise bounded live verification")
        return run_id, directory, target, surfaces

    def test_markdown_tables_images_hard_breaks_and_entities_render_safely(self):
        rendered = af.markdown_to_html(
            "# Hidden title\n\nA&nbsp;B  \nnext line\n\n"
            "| Default | Review |\n| --- | --- |\n| Static | Contract |\n\n"
            "![Useful diagram](/assets/articles/example/diagram.svg)\n\n<script>alert(1)</script>"
        )
        self.assertIn("A\u00a0B<br>\nnext line", rendered)
        self.assertIn('<div class="article-table-wrap"><table>', rendered)
        self.assertIn('<img src="/assets/articles/example/diagram.svg" alt="Useful diagram"', rendered)
        self.assertNotIn("<script>alert", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_visual_plan_renders_hash_bound_assets_and_advances(self):
        run_id = self.start("Explain why a product default can lag a model.")
        directory, run = af.load_run(run_id)
        self.record_json(directory, run, "brief", {
            "brief_schema_version": "1.0.0", "run_id": run_id, "title": "A Useful Article",
            "slug": "useful-article", "description": "A concrete explanation.", "date": "2026-09-02",
            "tags": [], "reader_job": "See the gap", "scope": "One example", "exclusions": [],
            "claims_to_support": [], "acceptance_criteria": ["One visual is present."],
        })
        self.record_text(directory, run, "draft", "# A Useful Article\n\nAn opening paragraph with enough concrete language to make the point visible.\n\n## The gap\n\nThe default stays still while capability improves.\n")
        plan_path = self.record_json(directory, run, "visual-plan", {
            "visual_plan_schema_version": "1.0.0", "run_id": run_id,
            "visuals": [{
                "visual_id": "capability-gap", "kind": "trend_gap", "title": "The integration gap",
                "purpose": "Make the difference between available and used capability visible.",
                "placement": {"after_heading": "The gap"},
                "alt_text": "Model capability rises while the product default remains almost flat.",
                "caption": "Conceptual view of capability growth outrunning a static product default.",
                "claim_ids": [], "labels": ["Model capability", "Product default"],
            }],
        })
        self.assertEqual(af.automatic_gate(directory, run, "VISUAL_PLAN", plan_path)[0], "PASS")
        af.transition(directory, run, "VISUAL_RENDER", "test", "Exercise deterministic visual rendering")
        code, payload = call(af.command_visual_render, run_id=run_id)
        self.assertEqual(code, af.EXIT_OK, payload)
        directory, run = af.load_run(run_id)
        self.assertEqual(run["state"], "CLAIM_VERIFICATION")
        manifest = af.json_artifact(directory, run, "visual-manifest")
        self.assertEqual(len(manifest["assets"]), 1)
        asset = manifest["assets"][0]
        self.assertEqual(af.sha256_path(directory / asset["source_path"]), asset["sha256"])
        self.assertIn("<title", (directory / asset["source_path"]).read_text(encoding="utf-8"))

    def test_controller_owns_voice_ids_hashes_anchor_and_order(self):
        run_id = self.start("Test controller-owned voice metadata.")
        directory, run = af.load_run(run_id)
        self.record_text(directory, run, "draft", "# Title\n\nI noticed the same product asking the same four setup questions even after its underlying model became much more capable.\n\n## Why it matters\n\nThe interface can become the limit.\n")
        self.record_json(directory, run, "verified-claim-ledger", {"claims": []})
        run["state"] = "VOICE_PROBE"
        run["status"] = "ACTIVE"
        af.save_run(directory, run)
        anchor = af.ensure_voice_anchor(directory, run)
        self.assertEqual(anchor["id"], "voice-anchor")
        compact = directory / "artifacts" / "compact.json"
        af.write_json(compact, {
            "voice_candidates_schema_version": "1.0.0", "run_id": run_id,
            "article_register": {"audience": "senior engineers"},
            "candidates": [
                {"passage": "I kept seeing the same four setup questions, even though the model underneath had become much more capable.", "intended_dimensions": ["field-note"], "preserved_claim_ids": []},
                {"passage": "The odd part was not the model. It was the product asking four familiar questions as if nothing underneath had changed.", "intended_dimensions": ["conversational"], "preserved_claim_ids": []},
                {"passage": "The model improved; the product contract did not. Four fixed setup questions made that lag visible.", "intended_dimensions": ["engineering"], "preserved_claim_ids": []},
            ],
        })
        self.assertEqual(af.automatic_gate(directory, run, "VOICE_PROBE", compact)[0], "PASS")
        probe_path = af.materialize_voice_probe(directory, run, compact, 1)
        probe = af.load_json(probe_path)
        self.assertEqual([item["candidate_id"] for item in probe["candidates"]], ["A", "B", "C"])
        self.assertEqual(probe["comparison_orders"], [["A", "B", "C"], ["C", "B", "A"]])
        self.assertEqual(probe["source_anchor"]["source_passage_sha256"], af.sha256_bytes(probe["source_anchor"]["source_passage"].encode("utf-8")))
        self.assertTrue(all(item["passage_sha256"] == af.sha256_bytes(item["passage"].encode("utf-8")) for item in probe["candidates"]))

    def test_same_url_helpers_replace_in_place_without_promoting(self):
        original = '<div>before</div><article class="article-card" data-article-flow-slug="same"><h3>Old</h3></article><article class="article-card article-card--featured" data-article-flow-slug="new"><span class="article-card__badge">Latest</span></article>'
        replacement = '<article class="article-card article-card--featured" data-article-flow-slug="same"><span class="article-card__badge">Latest</span><h3>Corrected</h3></article>'
        updated = af.replace_existing_article_card(original, "same", replacement)
        self.assertLess(updated.index("Corrected"), updated.index('data-article-flow-slug="new"'))
        corrected = re.search(r'<article\b[^>]*data-article-flow-slug="same"[^>]*>.*?</article>', updated, flags=re.DOTALL).group(0)
        self.assertNotIn("Latest", corrected)
        self.assertNotIn("featured", corrected)

    def test_archived_v30_authority_remains_loadable(self):
        self.assertEqual(af.workflow_for_version("3.0.0")["workflow_version"], "3.0.0")
        self.assertEqual(af.workflow_for_version("3.1.0")["workflow_version"], "3.1.0")

    def test_live_verification_retries_propagation_on_a_bounded_schedule(self):
        run_id, directory, target, surfaces = self.live_verification_fixture()
        url_to_body = {
            target["canonical_url"].format(slug="bounded-live-verification"): surfaces["article"].read_bytes(),
            target["blog_url"]: surfaces["blog"].read_bytes(),
            target["homepage_url"]: surfaces["homepage"].read_bytes(),
            target["feed_url"]: surfaces["feed"].read_bytes() + b"stale",
            target["sitemap_url"]: surfaces["sitemap"].read_bytes(),
        }

        def fetched(url, timeout=30):
            return 200, url_to_body[url], {}

        observed = []
        with mock.patch.object(af, "fetch_url", side_effect=fetched):
            for _ in range(4):
                code, payload = call(af.command_verify_live, run_id=run_id)
                self.assertEqual(code, af.EXIT_FAILED, payload)
                observed.append((payload["classification"], payload["retry_after_seconds"]))
            with self.assertRaisesRegex(af.FlowError, "exhausted"):
                af.command_verify_live(namespace(run_id=run_id))

        self.assertEqual(observed, [
            ("deployment_propagation", 10),
            ("deployment_propagation", 20),
            ("deployment_propagation", 40),
            ("deployment_propagation", None),
        ])
        _, run = af.load_run(run_id)
        self.assertEqual(run["status"], "BLOCKED")
        self.assertEqual(len(list((directory / "receipts").glob("live-verification-*.json"))), 4)

    def test_live_verification_does_not_retry_permanent_markup_failure(self):
        run_id, _directory, target, surfaces = self.live_verification_fixture(valid_article=False)
        url_to_body = {
            target["canonical_url"].format(slug="bounded-live-verification"): surfaces["article"].read_bytes(),
            target["blog_url"]: surfaces["blog"].read_bytes(),
            target["homepage_url"]: surfaces["homepage"].read_bytes(),
            target["feed_url"]: surfaces["feed"].read_bytes(),
            target["sitemap_url"]: surfaces["sitemap"].read_bytes(),
        }

        with mock.patch.object(af, "fetch_url", side_effect=lambda url, timeout=30: (200, url_to_body[url], {})):
            code, payload = call(af.command_verify_live, run_id=run_id)

        self.assertEqual(code, af.EXIT_FAILED, payload)
        self.assertEqual(payload["classification"], "permanent_validation_failure")
        self.assertFalse(payload["retryable"])
        _, run = af.load_run(run_id)
        self.assertEqual(run["status"], "BLOCKED")

    def test_rejected_article_feedback_retires_provisional_learning_but_keeps_history(self):
        run_id = self.start("Record durable feedback about a published article.")
        directory, run = af.load_run(run_id)
        self.record_text(directory, run, "article", "# Generic article\n\nThis reads like generated copy.\n")
        self.record_json(directory, run, "live-verification", {"status": "VERIFIED"})
        af.transition(directory, run, "COMPLETE", "test", "Create a verified published-article fixture")
        voice_root = af.voice_state_root()
        prior, _prior_path, _pointer = af.active_voice_profile()
        prior = json.loads(json.dumps(prior))
        prior["version"] = "runtime-000002-fixture"
        prior["parent_version"] = "1.0.0-provisional"
        prior["base_profile_sha256"] = af.sha256_path(af.baseline_voice_profile_path())
        prior["source_learning_record_id"] = "VL-fixture-2"
        prior["provisional_guidance"] = [
            {"guidance_id": "VG-one", "text": "First stale rule", "status": "provisional", "source_record_id": "VL-one", "created_at": af.utc_now()},
            {"guidance_id": "VG-two", "text": "Second stale rule", "status": "provisional", "source_record_id": "VL-two", "created_at": af.utc_now()},
        ]
        prior["positive_examples"].extend([
            {"status": "trial", "source_record_id": "VL-one"},
            {"status": "trial", "source_record_id": "VL-two"},
        ])
        prior["accepted_rejected_pairs"] = [{"source_record_id": "VL-two"}]
        prior_path = voice_root / "profiles" / "runtime-000002-fixture.json"
        af.write_json(prior_path, prior)
        af.write_json(voice_root / "current.json", {
            "voice_profile_pointer_schema_version": "1.0.0",
            "profile_id": prior["profile_id"],
            "current_version": prior["version"],
            "profile_sha256": af.sha256_path(prior_path),
            "updated_at": af.utc_now(),
            "source_learning_record_id": "VL-fixture-2",
            "previous_version": "1.0.0-provisional",
        })
        feedback_path = self.root / "feedback.md"
        feedback_path.write_text("Use a concrete senior-engineer field-note voice with shorter paragraphs.", encoding="utf-8")

        code, payload = call(
            af.command_voice_feedback,
            run_id=run_id,
            outcome="rejected",
            feedback_file=str(feedback_path),
        )

        self.assertEqual(code, af.EXIT_OK, payload)
        self.assertEqual(payload["retired_guidance_ids"], ["VG-one", "VG-two"])
        self.assertTrue(prior_path.is_file())
        current, _current_path, pointer = af.active_voice_profile()
        self.assertEqual(len(current["provisional_guidance"]), 1)
        self.assertIn("senior-engineer field notes", current["provisional_guidance"][0]["text"])
        self.assertFalse(any(item.get("source_record_id") in {"VL-one", "VL-two"} for item in current["positive_examples"]))
        self.assertEqual(current["accepted_rejected_pairs"], [])
        self.assertTrue(any(item.get("run_id") == run_id for item in current["negative_examples"]))
        profile_count = len(list((voice_root / "profiles").glob("*.json")))
        evidence_count = len(af._read_jsonl(voice_root / "article-feedback.jsonl"))

        code, duplicate = call(
            af.command_voice_feedback,
            run_id=run_id,
            outcome="rejected",
            feedback_file=str(feedback_path),
        )
        self.assertEqual(code, af.EXIT_OK, duplicate)
        self.assertTrue(duplicate["idempotent"])
        self.assertEqual(pointer["current_version"], duplicate["current_version"])
        self.assertEqual(profile_count, len(list((voice_root / "profiles").glob("*.json"))))
        self.assertEqual(evidence_count, len(af._read_jsonl(voice_root / "article-feedback.jsonl")))

    def test_revision_creates_a_fresh_run_with_separate_precedence_bound_request(self):
        source_run_id = self.start("Historical seed that remains immutable.")
        source_directory, source_run = af.load_run(source_run_id)
        metadata_path = source_directory / "package" / "public" / "metadata.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        af.write_json(metadata_path, {
            "slug": "same-public-url",
            "date": "2026-08-31",
            "title": "Original title",
        })
        af.transition(source_directory, source_run, "COMPLETE", "test", "Create a completed revision source")
        request = self.root / "revision-request.md"
        request.write_text("Replace the generic prose with a concrete field note.\n", encoding="utf-8")

        code, payload = call(
            af.command_revise,
            source_run_id=source_run_id,
            request_file=str(request),
            draft_model=None,
            hold_before_publish=True,
            auto=False,
        )

        self.assertEqual(code, af.EXIT_OK, payload)
        directory, run = af.load_run(payload["run_id"])
        self.assertEqual(run["parent_run_id"], source_run_id)
        self.assertEqual(run["revision"]["slug"], "same-public-url")
        self.assertEqual(run["revision"]["original_published_date"], "2026-08-31")
        self.assertEqual(af.artifact_path(directory, run, "seed").read_text(encoding="utf-8"), "Historical seed that remains immutable.")
        self.assertEqual(af.artifact_path(directory, run, "revision-request").read_text(encoding="utf-8"), request.read_text(encoding="utf-8"))
        self.assertTrue(any(event["type"] == "REVISION_CREATED" for event in af._read_jsonl(directory / "events.jsonl")))

        route = {
            "provider": "fixture", "model": "fixture-model", "model_version": "test",
            "eligible": True, "exclusion_reason": None, "capability_assumptions": [],
            "evaluation_score": 1, "kind": "command", "privacy": "test", "locality": "local",
            "cost_class": "test", "latency_class": "test", "canary_status": "passed",
        }
        routes = {
            "stage": "RESEARCH_PLAN", "required_capabilities": ["structured-output"],
            "candidates": [route], "chosen": route, "fallbacks": [], "reason": "fixture", "configuration_path": "test",
        }
        with mock.patch.object(af, "route_candidates", return_value=routes):
            _path, packet = af.task_packet(directory, run)
        self.assertIn("revision-request", {item["id"] for item in packet["inputs"]})
        self.assertTrue(any("overrides conflicting assumptions" in item for item in packet["constraints"]))

    def test_voice_set_can_be_rejected_without_learning_and_regenerated(self):
        run_id = self.start("Regenerate an unsuitable voice set.")
        directory, run = af.load_run(run_id)
        self.record_text(directory, run, "draft", "# Title\n\nI kept seeing four fixed setup questions even after the model underneath became markedly more capable.\n")
        self.record_json(directory, run, "verified-claim-ledger", {"claims": []})
        af.transition(directory, run, "VOICE_PROBE", "test", "Prepare a voice decision")
        af.ensure_voice_anchor(directory, run)
        candidates = self.record_json(directory, run, "voice-candidates", {
            "voice_candidates_schema_version": "1.0.0", "run_id": run_id,
            "article_register": {"audience": "senior engineers"},
            "candidates": [
                {"passage": "I kept seeing the same four setup questions after the model underneath had become more capable.", "intended_dimensions": ["field-note"], "preserved_claim_ids": []},
                {"passage": "The strange part was the four familiar questions, still there after the model underneath improved.", "intended_dimensions": ["conversational"], "preserved_claim_ids": []},
                {"passage": "Model capability increased while the product retained a fixed four-question setup contract.", "intended_dimensions": ["engineering"], "preserved_claim_ids": []},
            ],
        })
        probe = af.materialize_voice_probe(directory, run, candidates, 1)
        af.write_gate_receipt(directory, run, "G-VOICE-PROBE", "ESCALATE", [], {"type": "code", "version": af.CONTROLLER_VERSION})
        run["status"] = "WAITING_HUMAN"
        af.save_run(directory, run)
        prior_pointer = af.active_voice_profile()[2]

        code, payload = call(
            af.command_regenerate_voice,
            run_id=run_id,
            feedback="All three feel formal; use a concrete first-person field note.",
            auto=False,
        )

        self.assertEqual(code, af.EXIT_OK, payload)
        self.assertFalse(payload["learning_applied"])
        directory, run = af.load_run(run_id)
        self.assertEqual(run["state"], "VOICE_PROBE")
        self.assertEqual(run["status"], "ACTIVE")
        rejection = af.json_artifact(directory, run, "voice-set-rejection:1")
        self.assertFalse(rejection["learning_applied"])
        self.assertEqual(rejection["voice_probe_sha256"], af.sha256_path(probe))
        self.assertEqual(af.active_voice_profile()[2]["current_version"], prior_pointer["current_version"])
        self.assertTrue(any(event["type"] == "VOICE_SET_REJECTED" for event in af._read_jsonl(directory / "events.jsonl")))


if __name__ == "__main__":
    unittest.main()
