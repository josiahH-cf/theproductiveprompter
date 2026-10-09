"""Meaningful publication and voice authorization boundaries, without live calls."""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"Article-Spec-Pack-v1/scripts"))
import article_flow as af
import model_experiment as m
import model_release_article as bridge
import model_experiment_views as views


class PublicationTests(unittest.TestCase):
    def test_campaign_forwards_exact_retry_settings(self):
        args=argparse.Namespace(release_action="update",model="claude-opus-5-5",variant=["effort-max"],
                                retry_failed=True,timeout=1200,matrix="components",workers=1,limit=1)
        command=bridge.experiment_command(args)
        self.assertEqual(command,["update","--matrix","components","--workers","1",
            "--model","claude-opus-5-5","--variant","effort-max","--retry-failed","--timeout","1200","--limit","1"])
        args.variant=[]
        with self.assertRaisesRegex(m.ExperimentError,"requires update"):
            bridge.experiment_command(args)

    def test_host_fallback_returns_the_actual_task_protocol(self):
        failure=af.FlowError("No controller-hosted route is eligible; the active host must perform the task packet")
        with patch.object(bridge,"captured_call",side_effect=failure), \
             patch.object(af,"load_run",return_value=(Path("run"),{})), \
             patch.object(af,"next_state_payload",return_value={"action":"perform_task","task_packet":"packet.json"}):
            code,payload=bridge.advance_article(af,argparse.Namespace(run_id="r"))
            self.assertEqual(code,af.EXIT_WAITING)
            self.assertEqual(payload["task_packet"],"packet.json")

    def test_same_url_revision_is_reconciled_without_starting_another_article(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(af,"runs_root",return_value=Path(temporary)), \
             patch.object(bridge,"CAMPAIGN",Path(temporary)/"campaign.json"):
            child = Path(temporary)/"AF-child"
            child.mkdir()
            af.write_json(child/"run.json",{"run_id":"child","parent_run_id":"source",
                "run_overrides":{"model_release":"model-release-v1","model_release_campaign_id":"campaign"}})
            value={"articles":[],"pending_article":{"id":"campaign","run_id":"source","models":["m"]}}
            bridge.reconcile_article_revision(af,value)
            self.assertEqual(value["pending_article"]["run_id"],"child")
            self.assertEqual(value["pending_article"]["replaces_run_id"],"source")
            self.assertEqual(value["pending_article"]["models"],["m"])

    def test_wsl_campaign_dispatch_keeps_arguments_literal(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(af,"windows_user_root",return_value=Path(temporary)), \
             patch.dict(os.environ,{"WSL_DISTRO_NAME":"Ubuntu"}):
            launcher=Path(temporary)/"AppData/Local/Microsoft/WindowsApps/article-flow.cmd"
            launcher.parent.mkdir(parents=True)
            launcher.write_text("rem article-flow managed launcher",encoding="utf-8")
            args=["model-release","status","--model","name';$(secret)","--json"]
            command=af.wsl_model_release_command(args)
            script=base64.b64decode(command[-1]).decode("utf-16-le")
            self.assertIn("'name'';$(secret)'",script)
            self.assertIsNone(af.wsl_model_release_command(["status"]))

    def test_wsl_reads_windows_worktree_with_native_git(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ,{"WSL_DISTRO_NAME":"Ubuntu"}), \
             patch.object(af.shutil,"which",return_value="git.exe"), patch.object(af.subprocess,"run") as invoke:
            root=Path(temporary)
            (root/".git").write_text("gitdir: C:/repo/.git/worktrees/feature",encoding="utf-8")
            invoke.return_value.stdout="commit\n"
            self.assertEqual(af.git(["rev-parse","HEAD"],cwd=root),"commit\n")
            self.assertEqual(invoke.call_args.args[0][0],"git.exe")

    def test_controller_source_integrity_does_not_follow_publication_checkout(self):
        with patch.object(af,"publication_repo_root",return_value=Path("another-checkout")):
            self.assertEqual(af.source_bytes("scripts/model_experiment.py","worktree","source"),
                             (ROOT/"scripts/model_experiment.py").read_bytes())

    def test_publication_repair_precedes_catalog_and_generation(self):
        value = {"publication": {"status": "verification pending", "registry_snapshot": "saved.json"}}
        with tempfile.TemporaryDirectory() as temporary, patch.object(bridge,"STATE",Path(temporary)), \
             patch.object(bridge,"campaign",return_value=value), patch.object(m,"load",return_value={}), \
             patch.object(m,"freeze_prompt",return_value=b"prompt"), \
             patch.object(m,"verify_registry"), patch.object(bridge,"publication_checkout",return_value=Path(temporary)), \
             patch.object(bridge,"publish_results",return_value={"status":"verified"}) as publish, \
             patch.object(m,"discover") as discover, patch.object(m,"main") as generate, patch.object(af,"emit"), \
             patch.dict(os.environ,{"ARTICLE_FLOW_TEST_NO_PUBLISH":"0"}):
            result = bridge.coordinate(af,argparse.Namespace(release_action="update",json=True))
            self.assertEqual(result,0)
            publish.assert_called_once()
            discover.assert_not_called()
            generate.assert_not_called()

    def test_seed_contains_exact_challenge_as_unexecuted_reference(self):
        seed = bridge.article_seed([],initial=True)
        self.assertIn(m.freeze_prompt().decode("utf-8"),seed)
        self.assertIn("do not execute it while writing the article",seed)

    def test_unverified_article_never_reaches_generation(self):
        with patch.object(af,"load_run",return_value=(Path("run"),{"run_id":"r","state":"PUBLISH"})), \
             patch.object(af,"verify_event_log",return_value=(True,None,None,[])), \
             patch.object(af,"json_artifact",return_value={"status":"FAILED"}), \
             patch.object(m,"run_once") as launch:
            with self.assertRaisesRegex(m.ExperimentError,"published and verified"):
                bridge.require_verified_article(af,{"run_id":"r"})
            launch.assert_not_called()

    def test_results_attachment_preserves_prose_and_replaces_only_owned_section(self):
        original = "<article>Original author prose.\n<!-- GENERATED_ARTICLE_END --></article>"
        first = bridge.augment_article(original,bridge.START+"one"+bridge.END)
        second = bridge.augment_article(first,bridge.START+"two"+bridge.END)
        self.assertIn("Original author prose.",second)
        self.assertEqual(second.count(bridge.START),1)
        self.assertNotIn("one",second)
        self.assertEqual(bridge.augment_article(second,bridge.START+"two"+bridge.END),second)
        with self.assertRaises(m.ExperimentError):
            bridge.augment_article(first+bridge.START,"new")

    def test_source_prompt_and_original_response_are_preserved_in_public_bundle(self):
        registry=m.load(m.PACK/"registry.json")
        m.verify_registry(registry)
        files=views.site_bundle(m,registry,m.PACK,views.SITE+"/docs/example.html")
        self.assertEqual(files[views.PUBLIC+"/prompt.txt"],m.freeze_prompt())
        record=registry["records"][0]
        expected=(m.PACK/f"records/{record['key']}/response.txt").read_bytes()
        self.assertEqual(files[f"{views.PUBLIC}/runs/{record['key']}.txt"],expected)

    def test_approved_voice_flag_is_scoped_to_model_release(self):
        with self.assertRaisesRegex(af.FlowError,"authorized model-release"):
            af.command_start(argparse.Namespace(approved_voice=True,model_release=False))

    def test_readonly_campaign_status_does_not_discover_generate_or_publish(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(bridge,"CAMPAIGN",Path(temporary)/"campaign.json"), \
             patch.object(m,"discover") as discovery, patch.object(m,"run_once") as launch, \
             patch.object(bridge,"publish_results") as publish, patch.object(af,"emit") as emit:
            self.assertEqual(bridge.coordinate(af,argparse.Namespace(release_action="status",json=True)),0)
            discovery.assert_not_called()
            launch.assert_not_called()
            publish.assert_not_called()


class ApprovedVoiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        environment = patch.dict(os.environ,{"ARTICLE_FLOW_HOME":str(root),
            "ARTICLE_FLOW_RUNS_ROOT":str(root/"runs"),"ARTICLE_FLOW_TEST_NO_PUBLISH":"1"})
        environment.start()
        self.addCleanup(environment.stop)
        integrity = patch.object(af,"check_manifest",return_value={"ok":True,"failures":[]})
        integrity.start()
        self.addCleanup(integrity.stop)

    def start_at_voice(self):
        code,result = bridge.captured_call(af.command_start,argparse.Namespace(seed="Introduce the model experiment.",
            seed_file=None,slug=None,auto=False,draft_model=None,hold_before_publish=False,
            model_release=True,approved_voice=True,json=True))
        self.assertEqual(code,0)
        directory,run = af.load_run(result["run_id"])
        af.transition(directory,run,"VOICE_PROBE","test","Exercise the authorized voice reuse boundary")
        return directory,run

    def test_reuse_pins_profile_and_creates_no_new_preference(self):
        directory,run = self.start_at_voice()
        before = af.voice_history()
        with patch.object(af,"next_state_payload",return_value={"action":"test_stop"}):
            bridge.captured_call(af.command_advance,argparse.Namespace(run_id=run["run_id"],max_steps=1,json=True))
        _,updated = af.load_run(run["run_id"])
        self.assertEqual(updated["state"],"EDIT")
        receipt = af.load_json(directory/"receipts/approved-voice-reuse.json")
        self.assertFalse(receipt["new_preference_evidence"])
        self.assertEqual(receipt["profile_sha256"],af.artifact(updated,"voice-profile")["sha256"])
        self.assertEqual(af.voice_history(),before)
        self.assertIsNone(af.artifact(updated,"voice-selection"))

    def test_changed_snapshot_blocks_reuse(self):
        directory,run = self.start_at_voice()
        profile = af.artifact_path(directory,run,"voice-profile")
        profile.write_bytes(profile.read_bytes()+b" ")
        with self.assertRaises(af.FlowError), patch.object(af,"next_state_payload"):
            bridge.captured_call(af.command_advance,argparse.Namespace(run_id=run["run_id"],max_steps=1,json=True))
        _,updated = af.load_run(run["run_id"])
        self.assertEqual(updated["state"],"VOICE_PROBE")

    def test_revision_preserves_authorized_voice_and_campaign_scope(self):
        directory,run=self.start_at_voice()
        for kind, value, suffix in (("article", "# Existing article\n\nPreserve this passage.\n", ".md"),
                                    ("brief", {"title":"Existing article","slug":"model-release-experiment"}, ".json"),
                                    ("post-edit-claim-ledger", {"claims":[]}, ".json")):
            path=directory/"artifacts"/(kind+suffix)
            if isinstance(value,dict): af.write_json(path,value)
            else: path.write_text(value,encoding="utf-8")
            af.record_artifact(directory,run,path,kind,{"actor":"test"})
        af.transition(directory,run,"COMPLETE","test","Fixture only; no publication")
        af.write_json(directory/"package/public/metadata.json",{"slug":"model-release-experiment","date":"2026-10-02"})
        request=directory/"request.txt"
        request.write_text("Keep the introduction concise.",encoding="utf-8")
        # Campaign inheritance is tested after the verified-source seam; its
        # Git/live and timestamp behavior has real integration regressions.
        source=b"<html>Existing article</html>"
        snapshot={"bytes":source,"sha256":af.sha256_bytes(source),"commit":"a"*40,"observed_at":af.utc_now(),
                  "metadata":{"slug":"model-release-experiment","date":"2026-10-02","date_iso":"2026-10-02T12:00:00-05:00"}}
        with patch.object(af.revision_sources,"checked_snapshot",return_value=snapshot):
            code,result=bridge.captured_call(af.command_revise,argparse.Namespace(source_run_id=run["run_id"],
                request_file=str(request),draft_model=None,hold_before_publish=False,auto=False,json=True))
        self.assertEqual(code,0)
        _,revision=af.load_run(result["run_id"])
        self.assertEqual(revision["run_overrides"]["model_release"],"model-release-v1")
        self.assertIn("reuse_approved_voice",revision["run_overrides"])
        self.assertEqual(revision["parent_run_id"],run["run_id"])
        for kind in ("previous-article","previous-brief","previous-claims"):
            self.assertIsNotNone(af.artifact(revision,kind))

    def test_campaign_verifier_receives_the_frozen_challenge_source(self):
        directory,run=self.start_at_voice()
        with patch.object(af,"state_definition",return_value={"required_inputs":[]}):
            for state in ("CLAIM_VERIFICATION","POST_EDIT_CLAIM_VERIFICATION"):
                inputs=af.packet_inputs(directory,run,state)
                self.assertIn("seed",[item["id"] for item in inputs])

    def test_campaign_research_receives_the_pinned_approved_voice(self):
        directory,run=self.start_at_voice()
        with patch.object(af,"state_definition",return_value={"required_inputs":[]}):
            for state in ("RESEARCH_PLAN","RESEARCH"):
                voice=next(item for item in af.packet_inputs(directory,run,state) if item["id"] == "voice-profile")
                self.assertEqual(voice["sha256"],run["run_overrides"]["reuse_approved_voice"]["profile_sha256"])

    def test_campaign_research_rejects_another_voice_profile(self):
        directory,run=self.start_at_voice()
        run["run_overrides"]["reuse_approved_voice"]["profile_sha256"]="0"*64
        with patch.object(af,"state_definition",return_value={"required_inputs":[]}):
            with self.assertRaisesRegex(af.FlowError,"pinned profile"):
                af.packet_inputs(directory,run,"RESEARCH")

    def test_regular_research_does_not_receive_campaign_voice_inputs(self):
        directory,run=self.start_at_voice()
        run["run_overrides"].pop("model_release")
        run["run_overrides"].pop("reuse_approved_voice")
        with patch.object(af,"state_definition",return_value={"required_inputs":[]}):
            self.assertEqual(af.packet_inputs(directory,run,"RESEARCH"),[])


if __name__ == "__main__":
    unittest.main()
