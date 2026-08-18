from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SPEC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPEC_ROOT / "scripts"))
import article_flow as af  # noqa: E402


def namespace(**values):
    defaults = {
        "json": True,
        "selection": None,
        "feedback": None,
        "finding": None,
        "artifact": None,
        "route": None,
        "canary": False,
        "redirect_to": None,
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
        self.runtime = Path(self.temp.name) / "runtime"
        self.environment = mock.patch.dict(os.environ, {"ARTICLE_FLOW_HOME": str(self.runtime), "ARTICLE_FLOW_TEST_NO_PUBLISH": "1"}, clear=False)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.integrity = mock.patch.object(af, "check_manifest", return_value={"ok": True, "source": "test", "failures": []})
        self.integrity.start()
        self.addCleanup(self.integrity.stop)


class AuthorityTests(unittest.TestCase):
    def test_machine_authority_and_generated_view_are_consistent(self):
        result = subprocess.run([sys.executable, str(SPEC_ROOT / "scripts" / "render_workflow_docs.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        workflow = json.loads((SPEC_ROOT / "workflow" / "workflow.json").read_text())
        self.assertTrue(workflow["authority"])
        self.assertEqual(workflow["precedence"], ["run_overrides", "approved_article_recipe", "workflow_schema", "house_policy", "examples"])
        rules = {item["id"]: item["text"] for item in workflow["rules"]}
        self.assertIn("no grammatical person is universal", rules["AF-PERSON-001"])
        self.assertIn("house bands are never pass/fail gates", rules["AF-LENGTH-001"])
        self.assertIn("Do not require a universal article skeleton", rules["AF-SHAPE-001"])
        lint = af.normative_lint()
        self.assertTrue(lint["ok"], lint["issues"])
        self.assertEqual(lint["conflicting_normative_statement_count"], 0)

    def test_every_legacy_rule_document_has_machine_readable_redirect(self):
        registry = json.loads((SPEC_ROOT / "workflow" / "document-registry.json").read_text())
        for item in registry["non_authoritative_documents"]:
            text = (SPEC_ROOT / item["path"]).read_text(encoding="utf-8")[:800]
            self.assertIn("article_flow_authority: false", text, item["path"])
            self.assertIn(f"article_flow_document_status: {item['status']}", text, item["path"])
            self.assertIn(f'article_flow_removal_version: "{item["removal_version"]}"', text, item["path"])

    def test_all_json_and_json_schemas_parse(self):
        for path in SPEC_ROOT.rglob("*.json"):
            with self.subTest(path=path):
                json.loads(path.read_text(encoding="utf-8"))
        health = af.schema_health()
        self.assertTrue(health["ok"], [item for item in health["checks"] if not item["ok"]])


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.spec = self.repo / "Article-Spec-Pack-v1"
        (self.spec / "workflow").mkdir(parents=True)
        (self.spec / "schemas").mkdir(parents=True)
        shutil.copy2(SPEC_ROOT / "schemas" / "manifest.schema.json", self.spec / "schemas" / "manifest.schema.json")
        self.control = self.spec / "workflow" / "control.json"
        self.control.write_text('{"value":1}\n', encoding="utf-8")
        protected = {
            "protected_set_schema_version": "1.0.0",
            "workflow_version": "test",
            "watched_roots": ["workflow"],
            "excluded_prefixes": [],
            "entries": [
                {"path": "workflow/control.json", "role": "normative", "rule_set": "test"},
                {"path": "workflow/protected-paths.json", "role": "runtime", "rule_set": "integrity"},
            ],
        }
        (self.spec / "workflow" / "protected-paths.json").write_text(json.dumps(protected, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "core.autocrlf", "false"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "add", "Article-Spec-Pack-v1/workflow"], check=True)
        self.patches = [
            mock.patch.object(af, "SPEC_ROOT", self.spec),
            mock.patch.object(af, "REPO_ROOT", self.repo),
            mock.patch.object(af, "MANIFEST_PATH", self.spec / "manifest.json"),
            mock.patch.object(af, "PROTECTED_PATHS_PATH", self.spec / "workflow" / "protected-paths.json"),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        payload = af.manifest_payload_from_index()
        af.write_json(self.spec / "manifest.json", payload)
        subprocess.run(["git", "-C", str(self.repo), "add", "Article-Spec-Pack-v1/manifest.json"], check=True)

    def test_hash_mutation_delete_unexpected_and_restoration(self):
        self.assertTrue(af.check_manifest("index")["ok"])
        original = self.control.read_bytes()
        self.control.write_bytes(original + b" ")
        failure = af.check_manifest("worktree")
        self.assertFalse(failure["ok"])
        self.assertIn("hash_mismatch", {item["kind"] for item in failure["failures"]})
        self.control.write_bytes(original)
        self.assertTrue(af.check_manifest("worktree")["ok"])
        self.control.unlink()
        self.assertIn("missing_file", {item["kind"] for item in af.check_manifest("worktree")["failures"]})
        self.control.write_bytes(original)
        unexpected = self.spec / "workflow" / "unexpected.json"
        unexpected.write_text("{}\n", encoding="utf-8")
        self.assertIn("unexpected_protected_file", {item["kind"] for item in af.check_manifest("worktree")["failures"]})

    def test_algorithm_and_traversal_are_rejected(self):
        manifest = json.loads((self.spec / "manifest.json").read_text())
        manifest["hash_algorithm"] = "md5"
        af.write_json(self.spec / "manifest.json", manifest)
        self.assertIn("hash_algorithm", {item["kind"] for item in af.check_manifest("worktree")["failures"]})
        with self.assertRaises(af.FlowError):
            af.safe_relative("../outside")


class RunAndSmokeTests(TemporaryRuntime):
    def start(self, seed="A small idea about reliable article workflows."):
        code, payload = call(af.command_start, seed=seed, seed_file=None, slug=None)
        self.assertEqual(code, af.EXIT_OK)
        return payload["run_id"]

    def write_submission(self, run_id, state, value, suffix="json"):
        path = self.runtime / f"{state.lower()}.{suffix}"
        if suffix == "json":
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        else:
            path.write_text(value, encoding="utf-8")
        return call(af.command_submit, run_id=run_id, stage=state, file=str(path))

    def next(self, run_id):
        return call(af.command_next, run_id=run_id)

    def gate(self, run_id, gate_id, **extra):
        return call(af.command_gate, run_id=run_id, gate_id=gate_id, outcome="PASS", **extra)

    def walk_to_package(self):
        run_id = self.start()
        _, first = self.next(run_id)
        _, second = self.next(run_id)
        self.assertEqual(first["task_packet"], second["task_packet"])
        directory, run = af.load_run(run_id)
        self.assertEqual(run["attempts"]["RESEARCH_PLAN"], 1)
        self.write_submission(run_id, "RESEARCH_PLAN", {
            "research_plan_schema_version": "1.0.0", "run_id": run_id,
            "questions": [{"question": "What changed?", "why_it_matters": "It bounds the article.", "intent_changing": True}],
            "source_strategy": ["Use the repository and direct primary documentation."], "claim_risks": [], "no_search_behavior": "not-applicable",
        })
        self.next(run_id)
        ledger = {"claim_ledger_schema_version": "1.0.0", "run_id": run_id, "generated_at": af.utc_now(), "claims": []}
        self.write_submission(run_id, "RESEARCH", ledger)
        self.next(run_id)
        self.write_submission(run_id, "INTENT_REVIEW", {
            "intent_schema_version": "1.0.0", "run_id": run_id, "reader": "A person building a repeatable article flow", "reader_job": "Understand the proof boundary", "purpose": "Show how the checks fit together", "scope": "One MVP and its checks", "position": None,
            "explicit_seed_content": ["reliable article workflows"], "assumptions": [], "remaining_unknowns": [], "research_that_shaped_candidate": [],
        })
        self.gate(run_id, "G-INTENT-FIDELITY")
        self.next(run_id)
        self.write_submission(run_id, "ARTICLE_RECIPE", {
            "recipe_version": "1.0.0", "status": "candidate", "archetype": "case-study", "reader_job": "Understand the proof boundary", "scope_boundary": "The MVP, not a platform comparison",
            "length": {"mode": "brief", "target_words": {"minimum": 500, "maximum": 900}, "stop_when": "The reader can explain the checks."},
            "opening": {"strategy": "artifact", "reason": "The URL makes the result inspectable."}, "ending": {"strategy": "decision-rule", "reason": "The reader needs a reusable rule."},
            "summary": {"policy": "never", "form": None}, "narrative_person": "mixed", "evidence_posture": "documentary", "citation_mode": "links",
            "components": {"diagram": "off", "checklist": "optional", "mental_models": "off", "workflow_count": None, "activation_header": "off"},
            "outline_candidates": [{"id": "artifact-first"}, {"id": "failure-first"}], "selection_reason": "Artifact-first serves the reader job with the available evidence.",
            "recent_post_comparison": {"observed": [], "unknowns": ["older recipe metadata unavailable"]},
            "variation_budget": {"macro_dimensions": ["archetype", "opening"], "recent_post_comparison": True, "experiment_seed": "smoke-1"},
        })
        self.gate(run_id, "G-RECIPE-FIT")
        self.next(run_id)
        self.write_submission(run_id, "BRIEF", {
            "brief_schema_version": "1.0.0", "run_id": run_id, "title": "A Test Article", "slug": "a-test-article", "description": "A bounded test of the article workflow.", "date": "2026-08-18", "tags": ["workflow"],
            "reader_job": "Understand the proof boundary", "scope": "One MVP", "exclusions": ["provider rankings"], "claims_to_support": [], "acceptance_criteria": ["The package is reproducible."],
        })
        self.next(run_id)
        self.write_submission(run_id, "VOICE_PROBE", {
            "voice_probe_schema_version": "1.0.0", "run_id": run_id, "article_register": {"technical_depth": "moderate"},
            "candidates": [{"candidate_id": "A", "passage": "The page is live, and the hash tells us which page.", "intended_dimensions": ["directness"]}, {"candidate_id": "B", "passage": "A live page only proves something when its bytes match.", "intended_dimensions": ["precision"]}],
            "comparison_orders": [["A", "B"], ["B", "A"]], "held_out_plan": "Retest the chosen trait on a field note.", "operator_selection": None,
        })
        self.gate(run_id, "G-VOICE-PROBE", selection="A", feedback="It is more direct without overstating the result.")
        self.next(run_id)
        article = "# A Test Article\n\nThe page is live, and the hash tells us which page.\n\n## What the check proves\n\nThe package keeps public output separate from private receipts.\n"
        self.write_submission(run_id, "DRAFT", article, suffix="md")
        self.next(run_id)
        self.write_submission(run_id, "CLAIM_VERIFICATION", ledger)
        self.next(run_id)
        self.write_submission(run_id, "EDIT", article, suffix="md")
        self.next(run_id)
        self.write_submission(run_id, "POST_EDIT_CLAIM_VERIFICATION", ledger)
        self.next(run_id)
        dimensions = {key: {} for key in ["intent_fidelity", "clarity_utility", "voice_fit", "naturalness", "structural_interest", "proportional_length"]}
        self.write_submission(run_id, "EDITORIAL_QA", {"editorial_assessment_schema_version": "1.0.0", "run_id": run_id, "outcome": "PASS", "dimensions": dimensions, "findings": [], "calibration_status": "uncalibrated-advisory"})
        self.gate(run_id, "G-EDITORIAL-QA")
        directory, run = af.load_run(run_id)
        self.assertEqual(run["state"], "PACKAGE")
        return run_id

    def test_similar_slugs_are_collision_safe(self):
        first = self.start("Same seed")
        second = self.start("Same seed")
        self.assertNotEqual(first, second)
        self.assertNotEqual(af.run_dir(first), af.run_dir(second))
        code, status = call(af.command_status, run_id=None)
        self.assertEqual(code, af.EXIT_OK)
        self.assertEqual(status["run_id"], second)

    def test_task_packet_is_complete_and_schema_rejects_hidden_context(self):
        run_id = self.start()
        _, action = self.next(run_id)
        packet_path = Path(action["task_packet"])
        packet = json.loads(packet_path.read_text())
        for field in ["workflow_version", "run_id", "stage", "attempt", "objective", "inputs", "reader_job", "article_recipe", "allowed_tools", "side_effect_policy", "constraints", "expected_outputs", "success_criteria", "non_authorities", "stop_conditions", "escalation_question"]:
            self.assertIn(field, packet)
        packet.pop("escalation_question")
        broken = Path(self.temp.name) / "broken-packet.json"
        broken.write_text(json.dumps(packet), encoding="utf-8")
        self.assertTrue(af.validate_json_schema(broken, "task-packet.schema.json"))

    def test_event_corruption_is_detected(self):
        run_id = self.start()
        directory, _ = af.load_run(run_id)
        events = directory / "events.jsonl"
        events.write_text(events.read_text(encoding="utf-8").replace("RUN_CREATED", "RUN_CORRUPTED", 1), encoding="utf-8")
        with self.assertRaises(af.FlowError):
            af.load_run(run_id)

    def test_stale_lock_is_recovered_and_recorded(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        af.write_json(directory / ".lock", {"pid": 99999999, "created_at": "2000-01-01T00:00:00Z"})
        with af.run_lock(directory, run):
            self.assertTrue((directory / ".lock").exists())
        self.assertTrue(list(directory.glob(".lock.recovered-*")))
        af.load_run(run_id)

    def test_end_to_end_smoke_packages_without_publishing(self):
        run_id = self.walk_to_package()
        code, payload = call(af.command_package, run_id=run_id)
        self.assertEqual(code, af.EXIT_OK, payload)
        directory, run = af.load_run(run_id)
        self.assertEqual(run["state"], "PUBLISH_APPROVAL")
        package = json.loads((directory / "package" / "package.json").read_text())
        self.assertEqual(package["canonical_article_file"], "public/article.md")
        self.assertTrue((directory / "package" / "site" / "docs" / "a-test-article.html").is_file())
        for surface in [directory / "package" / "site" / "docs" / "blog.html", directory / "package" / "site" / "feed.xml", directory / "package" / "site" / "sitemap.xml"]:
            text = surface.read_text(encoding="utf-8")
            self.assertIn("a-test-article.html", text)
            self.assertIn("from-idea-to-verified-url.html", text)
        repository = af.publication_repo_root(required=True)
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in [repository / "index.html", repository / "docs" / "blog.html", repository / "feed.xml", repository / "sitemap.xml"]}
        _, first = call(af.command_publish_plan, run_id=run_id)
        _, second = call(af.command_publish_plan, run_id=run_id)
        self.assertTrue(second["idempotent"])
        self.assertEqual(first["package_revision"], second["package_revision"])
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before}
        self.assertEqual(before, after)

    def test_protected_drift_blocks_package_and_conformance_blocks_execute(self):
        run_id = self.walk_to_package()
        with mock.patch.object(af, "check_manifest", return_value={"ok": False, "failures": [{"kind": "hash_mismatch"}]}):
            with self.assertRaises(af.FlowError) as caught:
                call(af.command_package, run_id=run_id)
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        with self.assertRaises(af.FlowError) as caught:
            af.command_publish_execute(namespace(run_id="AF-20000101T000000Z-test-00000000", approval="none", commit=False, push=False, json=True))
        self.assertEqual(caught.exception.code, af.EXIT_APPROVAL)

    def test_memory_citation_and_naturalization_drift_fail(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        run["state"] = "RESEARCH"
        ledger_path = Path(self.temp.name) / "ledger.json"
        ledger_path.write_text(json.dumps({
            "claim_ledger_schema_version": "1.0.0", "run_id": run_id, "generated_at": af.utc_now(), "claims": [{
                "claim_id": "C1", "exact_claim": "A current number is 42.", "class": "fact", "risk": "high", "source_tier": "memory", "source_url_or_local_id": "model-memory", "source_title_and_publisher": None, "exact_locator_or_supporting_excerpt": "remembered", "checked_at": af.utc_now(), "freshness_horizon": "one day", "contradiction_status": "none_found", "allowed_wording": "42", "confidence": 0.5, "disposition": "use"
            }]
        }), encoding="utf-8")
        outcome, findings = af.automatic_gate(directory, run, "RESEARCH", ledger_path)
        self.assertEqual(outcome, "REPAIR")
        self.assertIn("no_memory_citations", {item["criterion"] for item in findings})
        locked = directory / "artifacts" / "locked-fields.json"
        af.write_json(locked, {"locked_fields_schema_version": "1.0.0", "run_id": run_id, "source_sha256": "0" * 64, "tokens": af.find_locked_tokens("The value is 42 on 2026-08-18.\n"), "claims": []})
        af.record_artifact(directory, run, locked, "locked-fields", {"actor": "test"})
        changed = Path(self.temp.name) / "changed.md"
        changed.write_text("The value is 43 on 2026-08-18.\n", encoding="utf-8")
        outcome, findings = af.automatic_gate(directory, run, "EDIT", changed)
        self.assertEqual(outcome, "REPAIR")
        self.assertIn("locked_fields", {item["criterion"] for item in findings})

    def test_wrong_live_revision_fails_even_with_http_200(self):
        run_id = self.walk_to_package()
        call(af.command_package, run_id=run_id)
        directory, run = af.load_run(run_id)
        af.transition(directory, run, "LIVE_VERIFICATION", "test", "simulate a completed deployment without performing one")
        with mock.patch.object(af, "fetch_url", return_value=(200, b"older cached page", {})):
            code, payload = call(af.command_verify_live, run_id=run_id)
        self.assertEqual(code, af.EXIT_FAILED)
        self.assertFalse(next(item for item in payload["checks"] if item["name"] == "article_revision")["ok"])
        _, current = af.load_run(run_id)
        self.assertEqual(current["state"], "LIVE_VERIFICATION")

    def test_lifecycle_changes_are_plans_and_archive_requires_a_redirect(self):
        run_id = self.start("A completed article that later needs archiving.")
        directory, run = af.load_run(run_id)
        af.transition(directory, run, "COMPLETE", "test", "exercise lifecycle planning")
        with self.assertRaises(af.FlowError):
            call(af.command_lifecycle, run_id=run_id, action="archive", reason="Retired", redirect_to=None)
        code, payload = call(af.command_lifecycle, run_id=run_id, action="archive", reason="Retired", redirect_to="https://example.com/replacement")
        self.assertEqual(code, af.EXIT_OK)
        self.assertEqual(payload["lifecycle"]["status"], "PLANNED_NOT_APPLIED")
        self.assertTrue(any("redirect verified" in item for item in payload["lifecycle"]["required_checks"]))


class AdapterTests(TemporaryRuntime):
    def test_install_is_content_idempotent_and_drift_is_detected(self):
        fake_home = Path(self.temp.name) / "home"
        fake_windows = Path(self.temp.name) / "windows-user"
        python_exe = fake_windows / "AppData" / "Local" / "Programs" / "Python" / "Python312" / "python.exe"
        python_exe.parent.mkdir(parents=True)
        python_exe.write_bytes(b"test")
        with (
            mock.patch.object(Path, "home", return_value=fake_home),
            mock.patch.object(af, "windows_user_root", return_value=fake_windows),
            mock.patch.dict(os.environ, {"ARTICLE_FLOW_HOME": ""}),
        ):
            args = namespace(hosts="windows,wsl", providers="auto", user=True, development=True)
            call(af.command_install, **vars(args))
            tracked = [fake_home / ".agents" / "skills" / "start-article" / "SKILL.md", fake_windows / ".agents" / "skills" / "start-article" / "SKILL.md", fake_windows / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "article-flow.cmd"]
            hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked}
            call(af.command_install, **vars(args))
            self.assertEqual(hashes, {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked})
            self.assertIn("article-flow managed launcher", tracked[-1].read_text())
            installed_script = fake_home / ".local" / "share" / "article-flow" / "releases" / af.CONTROLLER_VERSION / "Article-Spec-Pack-v1" / "scripts" / "article_flow.py"
            unrelated = Path(self.temp.name) / "unrelated"
            unrelated.mkdir()
            result = subprocess.run([sys.executable, str(installed_script), "--version"], cwd=unrelated, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(af.CONTROLLER_VERSION, result.stdout)
            nested_runtime = Path(self.temp.name) / "nested-runtime"
            nested_environment = os.environ.copy()
            nested_environment["ARTICLE_FLOW_HOME"] = str(nested_runtime)
            nested_environment["ARTICLE_FLOW_REPO_ROOT"] = str(af.REPO_ROOT)
            nested = subprocess.run(
                [sys.executable, str(installed_script), "install", "--hosts", "wsl", "--development", "--json"],
                cwd=unrelated,
                env=nested_environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(nested.returncode, 0, nested.stderr)
            nested_record = json.loads((nested_runtime / "current.json").read_text())
            self.assertTrue(nested_record["source_commit"])
            verification = af.verify_adapters()
            self.assertTrue(verification["ok"], verification)
            tracked[0].write_text("drift", encoding="utf-8")
            verification = af.verify_adapters()
            failed = [item for item in verification["checks"] if not item["ok"]]
            self.assertEqual(len(failed), 1)
            self.assertIn("install", failed[0]["repair_command"])

    def test_conformance_forwards_the_publication_checkout_and_retains_history(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="tests passed", stderr="")
        with (
            mock.patch.object(af, "release_source_commit", return_value="a" * 40),
            mock.patch.object(af, "publication_repo_root", return_value=af.REPO_ROOT),
            mock.patch.object(af.subprocess, "run", return_value=completed) as executed,
        ):
            code, first = call(af.command_conformance)
            self.assertEqual(code, af.EXIT_OK)
            self.assertEqual(executed.call_args.kwargs["env"]["ARTICLE_FLOW_REPO_ROOT"], str(af.REPO_ROOT))
            code, second = call(af.command_conformance)
            self.assertEqual(code, af.EXIT_OK)
        self.assertEqual(first["commit"], second["commit"])
        self.assertTrue(list((self.runtime / "conformance" / "history").glob("*.json")))


class MCPTests(TemporaryRuntime):
    def exchange(self, *requests):
        source = io.StringIO("".join(json.dumps(item) + "\n" for item in requests))
        destination = io.StringIO()
        with mock.patch.object(sys, "stdin", source), contextlib.redirect_stdout(destination):
            self.assertEqual(af.command_mcp(namespace()), af.EXIT_OK)
        return [json.loads(line) for line in destination.getvalue().splitlines()]

    def test_mcp_discovers_tools_starts_resumes_and_records_a_human_gate(self):
        initialized, listed, started = self.exchange(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "start", "arguments": {"seed": "An MCP-started article idea."}}},
        )
        self.assertEqual(initialized["result"]["serverInfo"]["version"], af.CONTROLLER_VERSION)
        self.assertEqual({item["name"] for item in listed["result"]["tools"]}, {"start", "status", "next", "resume", "gate"})
        start_payload = json.loads(started["result"]["content"][0]["text"])
        run_id = start_payload["run_id"]

        directory, run = af.load_run(run_id)
        candidate = directory / "artifacts" / "intent-candidate.json"
        af.write_json(candidate, {"intent_schema_version": "1.0.0", "run_id": run_id})
        af.record_artifact(directory, run, candidate, "intent-candidate", {"actor": "test"})
        af.transition(directory, run, "INTENT_REVIEW", "test", "exercise the MCP human-gate adapter")

        status, resumed, gated = self.exchange(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "status", "arguments": {"run_id": run_id}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "resume", "arguments": {"run_id": run_id}}},
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "gate", "arguments": {"run_id": run_id, "gate_id": "G-INTENT-FIDELITY", "outcome": "PASS"}}},
        )
        self.assertEqual(json.loads(status["result"]["content"][0]["text"])["state"], "INTENT_REVIEW")
        self.assertEqual(json.loads(resumed["result"]["content"][0]["text"])["action"], "human_decision")
        self.assertEqual(json.loads(gated["result"]["content"][0]["text"])["state"], "ARTICLE_RECIPE")
        af.load_run(run_id)


class ProviderTests(TemporaryRuntime):
    def test_command_provider_consumes_the_same_packet(self):
        helper = Path(self.temp.name) / "provider.py"
        helper.write_text(
            "import json,sys\n"
            "p=json.load(open(sys.argv[1],encoding='utf-8'))\n"
            "o={'research_plan_schema_version':'1.0.0','run_id':p['run_id'],'questions':[{'question':'Q','why_it_matters':'B','intent_changing':True}],'source_strategy':['primary sources'],'claim_risks':[],'no_search_behavior':'not-applicable'}\n"
            "open(sys.argv[2],'w',encoding='utf-8').write(json.dumps(o))\n",
            encoding="utf-8",
        )
        config = self.runtime / "config" / "providers.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"provider_config_schema_version": "1.0.0", "providers": [{
            "provider_id": "fixture", "kind": "command", "enabled": True,
            "command": [sys.executable, str(helper), "{packet}", "{output}"],
            "models": [{"model_id": "fixture-model", "version": "1", "capabilities": ["structured-output", "long-form", "research"], "stages": ["RESEARCH_PLAN"], "locality": "local", "canary_status": "passed"}],
        }]}), encoding="utf-8")
        code, started = call(af.command_start, seed="test command route", seed_file=None, slug=None)
        self.assertEqual(code, 0)
        run_id = started["run_id"]
        call(af.command_next, run_id=run_id)
        code, result = call(af.command_execute_stage, run_id=run_id, route="fixture:fixture-model")
        self.assertEqual(code, 0, result)
        _, run = af.load_run(run_id)
        self.assertEqual(run["state"], "RESEARCH")
        receipt = next(item for item in run["artifact_index"] if item["type"].startswith("model-call:"))
        receipt_value = json.loads((af.run_dir(run_id) / receipt["path"]).read_text())
        self.assertNotIn("credential", json.dumps(receipt_value).lower())

    def test_required_canary_cannot_become_default_but_can_run_explicitly(self):
        helper = Path(self.temp.name) / "canary-provider.py"
        helper.write_text(
            "import json,sys\n"
            "p=json.load(open(sys.argv[1],encoding='utf-8'))\n"
            "o={'research_plan_schema_version':'1.0.0','run_id':p['run_id'],'questions':[{'question':'Q','why_it_matters':'B','intent_changing':True}],'source_strategy':['primary sources'],'claim_risks':[],'no_search_behavior':'not-applicable'}\n"
            "open(sys.argv[2],'w',encoding='utf-8').write(json.dumps(o))\n",
            encoding="utf-8",
        )
        config = self.runtime / "config" / "providers.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"provider_config_schema_version": "1.0.0", "providers": [{
            "provider_id": "canary-fixture", "kind": "command", "enabled": True,
            "command": [sys.executable, str(helper), "{packet}", "{output}"],
            "models": [{"model_id": "new-version", "version": "2", "capabilities": ["structured-output", "long-form", "research"], "stages": ["RESEARCH_PLAN"], "locality": "local", "canary_status": "required"}],
        }]}), encoding="utf-8")
        code, started = call(af.command_start, seed="test canary route", seed_file=None, slug=None)
        self.assertEqual(code, 0)
        run_id = started["run_id"]
        call(af.command_next, run_id=run_id)
        with self.assertRaises(af.FlowError):
            call(af.command_execute_stage, run_id=run_id, route="canary-fixture:new-version", canary=False)
        code, result = call(af.command_execute_stage, run_id=run_id, route="canary-fixture:new-version", canary=True)
        self.assertEqual(code, 0, result)
        self.assertTrue(result["model_call"]["canary_execution"])

    def test_routing_promotion_requires_human_calibration(self):
        source = Path(self.temp.name) / "evaluation.json"
        source.write_text(json.dumps({
            "evaluation_schema_version": "1.0.0", "evaluation_id": "eval-no-human", "fixture_id": "fixture-1",
            "workflow_version": af.workflow()["workflow_version"], "stage": "DRAFT", "provider": "fixture", "model": "model", "model_version": "1",
            "grader": {"order_reversal_passed": True}, "candidate_order": ["A", "B"], "metrics": {"overall": 0.9},
            "human_calibration": None, "promotion_status": "promoted", "canary": {"status": "passed"}, "created_at": af.utc_now(),
        }), encoding="utf-8")
        with self.assertRaises(af.FlowError) as caught:
            call(af.command_evaluation_record, file=str(source))
        self.assertIn("human calibration", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
