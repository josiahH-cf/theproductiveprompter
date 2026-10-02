"""Meaningful publication and voice authorization boundaries, without live calls."""
import argparse
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


if __name__ == "__main__":
    unittest.main()
