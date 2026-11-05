"""External candidates retain one owner, honest provenance and publication gates."""
from __future__ import annotations

import json
import subprocess
import sys
from unittest import mock

from test_article_flow_v3 import TemporaryRuntime, af, call
import external_revision as external
import revision_import as imported
import revision_sources as sources


class ExternalRevisionImportTests(TemporaryRuntime):
    def setUp(self):
        super().setUp()
        self.repo = self.root / "publication"
        self.repo.mkdir()
        af.git(["init"], cwd=self.repo)
        af.git(["config", "user.name", "Revision test"], cwd=self.repo)
        af.git(["config", "user.email", "test@example.invalid"], cwd=self.repo)
        self.slug = "external-revision"
        self.url = f"https://theproductiveprompter.com/docs/{self.slug}.html"
        self.stamp = "2026-09-15T09:04:24Z"
        self.markdown = "A concrete explanation with [its source](https://example.com/reference).\n\n## Next step\n\nKeep the useful parts.\n"
        self.pages = {}
        self.write_page(self.markdown)
        self.write_discovery()
        self.commit()
        self.root_patch = mock.patch.object(af, "publication_repo_root", return_value=self.repo)
        self.fetch_patch = mock.patch.object(af, "fetch_url", side_effect=lambda url, timeout=30: (200, self.pages.get(url, b""), {}))
        self.root_patch.start(); self.fetch_patch.start()
        self.addCleanup(self.root_patch.stop); self.addCleanup(self.fetch_patch.stop)
        self.feedback = self.root / "feedback.md"
        self.feedback.write_bytes("I mean it needs to feel useful\nKeep my exact words here, including this private author note.\n".encode())
        self.candidate = self.root / "candidate.md"
        self.candidate.write_bytes(self.markdown.replace("concrete explanation", "clearer explanation").encode())
        self.envelope = self.root / "source.json"
        self.refresh_identity()

    def write_page(self, markdown):
        post = {"@type": "BlogPosting", "headline": "Original title", "datePublished": self.stamp}
        data = (f'<html><head><link rel="canonical" href="{self.url}"><meta name="description" content="Description">'
                f'<script type="application/ld+json">{json.dumps(post)}</script></head><body>'
                + external.START + af.markdown_to_html(markdown) + external.END + '</body></html>').encode()
        path = self.repo / f"docs/{self.slug}.html"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        self.pages[self.url] = data

    def write_discovery(self):
        card = (f'<article class="article-card" data-article-flow-slug="{self.slug}">'
                f'<h3><a class="article-card__link" href="{self.slug}.html">Original title</a></h3>'
                '<p class="article-card__summary">Description</p>'
                '<time class="article-card__date" datetime="2026-09-15">September 15, 2026</time>'
                '<span class="article-card__reading-time">1 min read</span></article>')
        (self.repo / 'docs/blog.html').write_text(card, encoding='utf-8')
        (self.repo / 'index.html').write_text(card.replace(f'href="{self.slug}.html"', f'href="docs/{self.slug}.html"'), encoding='utf-8')
        (self.repo / 'feed.xml').write_text(f'<rss><channel><lastBuildDate>old</lastBuildDate><item><link>{self.url}</link><pubDate>old</pubDate></item></channel></rss>', encoding='utf-8')
        (self.repo / 'sitemap.xml').write_text(f'<urlset><url><loc>{self.url}</loc></url></urlset>', encoding='utf-8')

    def commit(self):
        af.git(["add", "."], cwd=self.repo)
        af.git(["commit", "-m", "Published source"], cwd=self.repo)

    def refresh_identity(self):
        snapshot = sources.checked_snapshot(af, self.slug)
        markdown, _ = external.material(af, snapshot)
        self.envelope.write_text(json.dumps(external.identity(snapshot, markdown)), encoding="utf-8")

    def revise(self, **kw):
        args = {"source_file": str(self.envelope), "candidate_file": str(self.candidate),
                "request_file": str(self.feedback), "source_run_id": None, "published_slug": None,
                "expected_source_sha256": None, "unattended_editorial": True,
                "authorization": "Automatically validate and publish this requested GPT revision.",
                "hold_before_publish": False, "auto": False}
        args.update(kw)
        code, result = call(af.command_revise, **args)
        return code, result

    def opened(self):
        code, result = self.revise()
        self.assertEqual(code, af.EXIT_OK, result)
        return af.load_run(result['run_id'])

    def move(self, directory, run, state):
        af.transition(directory, run, state, 'test', 'Reach the stage under test')

    def carry(self, directory, run, state):
        self.move(directory, run, state)
        with af.run_lock(directory, run):
            self.assertTrue(imported.adopt(af, directory, run))

    def accepted(self):
        directory, run = self.opened()
        self.carry(directory, run, 'DRAFT')
        self.assertEqual(run['state'], 'DEVELOPMENT_REVIEW')
        self.carry(directory, run, 'EDIT')
        self.assertEqual(run['state'], 'POST_EDIT_CLAIM_VERIFICATION')
        return directory, run

    def add_image(self):
        self.image = b'<svg xmlns="http://www.w3.org/2000/svg"><title>Bound image</title></svg>'
        self.image_path = self.repo / 'assets/articles/external-revision/diagram.svg'
        self.image_path.parent.mkdir(parents=True)
        self.image_path.write_bytes(self.image)
        self.image_url = 'https://theproductiveprompter.com/assets/articles/external-revision/diagram.svg'
        self.pages[self.image_url] = self.image
        self.markdown += '\n![Exact alt](/assets/articles/external-revision/diagram.svg)\n'
        self.write_page(self.markdown)
        self.commit()
        self.candidate.write_text(self.markdown.replace('concrete explanation', 'clearer explanation'), encoding='utf-8')
        self.refresh_identity()

    def test_intake_separates_exact_author_feedback_from_generated_candidate(self):
        directory, run = self.opened()
        self.assertEqual(af.artifact_path(directory, run, 'revision-request').read_bytes(), self.feedback.read_bytes())
        self.assertEqual(af.artifact(run, 'revision-request')['producer']['actor'], 'operator')
        self.assertEqual(af.artifact_path(directory, run, 'external-revision-candidate').read_bytes(), self.candidate.read_bytes())
        producer = af.artifact(run, 'external-revision-candidate')['producer']
        self.assertEqual(producer['actor'], 'external_assistant')
        self.assertFalse(producer['human_original'])
        self.assertEqual(producer['model_identity'], 'unverified')
        self.assertEqual(run['revision']['canonical_url'], self.url)
        self.assertEqual(run['revision']['original_published_timestamp'], self.stamp)
        self.assertNotIn('parent_run_id', run)

    def test_intake_from_exact_completed_package_preserves_ancestor_and_timestamp(self):
        source_id = self.start('An intact source article seed.')
        source_dir, source_run = af.load_run(source_id)
        self.record_text(source_dir, source_run, 'article', self.markdown)
        self.record_json(source_dir, source_run, 'brief', {'title': 'Original title', 'slug': self.slug})
        self.record_json(source_dir, source_run, 'post-edit-claim-ledger', {'claims': []})
        public_md = source_dir / 'package/public/article.md'
        af.atomic_write(public_md, self.markdown.encode())
        public_html = source_dir / f'package/site/docs/{self.slug}.html'
        af.atomic_write(public_html, self.pages[self.url])
        af.write_json(source_dir / 'package/public/metadata.json', {'slug': self.slug, 'date': '2026-09-15'})
        package_path = source_dir / 'package/package.json'
        af.write_json(package_path, {'public_files': [
            {'path': 'public/article.md', 'sha256': af.sha256_path(public_md)},
            {'path': f'site/docs/{self.slug}.html', 'sha256': af.sha256_path(public_html)}]})
        af.record_artifact(source_dir, source_run, package_path, 'package', {'actor': 'test'})
        af.transition(source_dir, source_run, 'COMPLETE', 'test', 'Exact completed package fixture')
        before = (source_dir / 'run.json').read_bytes()
        self.refresh_identity()
        directory, run = self.opened()
        self.assertEqual(run['parent_run_id'], source_id)
        self.assertEqual(run['revision']['source_kind'], 'completed_run')
        self.assertEqual(run['revision']['original_published_timestamp'], self.stamp)
        self.assertEqual((source_dir / 'run.json').read_bytes(), before)
        self.assertEqual(af.artifact_path(directory, run, 'previous-article').read_text(), self.markdown)

    def test_carries_preserve_candidate_and_do_not_fabricate_writer_tasks(self):
        directory, run = self.accepted()
        for kind in ('draft', 'article'):
            self.assertEqual(af.artifact_path(directory, run, kind).read_bytes(), self.candidate.read_bytes())
            self.assertEqual(af.artifact(run, kind)['producer']['actor'], 'external_assistant')
        events = [json.loads(line) for line in (directory / 'events.jsonl').read_text().splitlines()]
        self.assertFalse(any(e['type'] in {'TASK_DISPATCHED', 'WRITING_MODEL_ACCEPTED'} for e in events))
        self.assertEqual(run['model_experiment']['actual_models'], [])
        report = af.package_writing_provenance(directory, run)
        self.assertEqual(report['evidence_kind'], 'validated_external_assistant_candidate')
        self.assertEqual(report['agent_hosted_acceptances'], [])
        self.assertEqual([x['stage'] for x in report['external_revision_acceptances']], ['DRAFT', 'EDIT'])

    def test_committed_carry_finishes_interrupted_transition_without_repeating_acceptance(self):
        directory, run = self.opened()
        self.move(directory, run, 'DRAFT')
        with mock.patch.object(af, 'transition', side_effect=af.FlowError('Fixture interruption after acceptance')):
            with self.assertRaisesRegex(af.FlowError, 'Fixture interruption'):
                with af.run_lock(directory, run):
                    imported.adopt(af, directory, run)
        directory, run = af.load_run(run['run_id'])
        self.assertEqual(run['state'], 'DRAFT')
        acceptance = dict(af.artifact(run, 'external-revision-acceptance:DRAFT'))
        self.assertEqual(af.artifact_path(directory, run, 'draft').read_bytes(), self.candidate.read_bytes())
        with mock.patch.object(af, 'automatic_gate') as gate, mock.patch.object(af, 'task_packet') as writer:
            with af.run_lock(directory, run):
                self.assertTrue(imported.adopt(af, directory, run))
        self.assertEqual(run['state'], 'DEVELOPMENT_REVIEW')
        self.assertNotEqual(run['status'], 'BLOCKED')
        self.assertEqual(af.artifact(run, 'external-revision-acceptance:DRAFT'), acceptance)
        events = [json.loads(line) for line in (directory / 'events.jsonl').read_text().splitlines()]
        accepted = [event for event in events if event['type'] == 'ARTIFACT_RECORDED'
                    and (event.get('payload', {}).get('artifact') or {}).get('artifact_id') == acceptance['artifact_id']]
        self.assertEqual(len(accepted), 1)
        self.assertFalse(any(event['type'] in {'TASK_DISPATCHED', 'WRITING_MODEL_ACCEPTED'} for event in events))
        self.assertEqual(af.load_run(run['run_id'])[1]['state'], 'DEVELOPMENT_REVIEW')
        gate.assert_not_called(); writer.assert_not_called()

    def test_failed_real_draft_check_blocks_without_rewriting_or_publication(self):
        self.candidate.write_text(self.candidate.read_text() + '\nTODO: finish this thought.\n', encoding='utf-8')
        directory, run = self.opened()
        with mock.patch.object(af, 'command_publish_execute') as publish:
            self.carry(directory, run, 'DRAFT')
        self.assertEqual(run['state'], 'DRAFT')
        self.assertEqual(run['status'], 'BLOCKED')
        self.assertEqual(af.artifact_path(directory, run, 'external-revision-candidate').read_bytes(), self.candidate.read_bytes())
        gate = af.json_artifact(directory, run, 'gate-receipt:G-DRAFT-COVERAGE')
        self.assertNotEqual(gate['outcome'], 'PASS')
        self.assertTrue(any(x['criterion'] == 'no_placeholders_or_private_paths' for x in gate['findings']))
        publish.assert_not_called()
        _, durable = af.load_run(run['run_id'])
        self.assertEqual(durable['status'], 'BLOCKED')
        with mock.patch.object(af, 'command_publish_execute') as publish, mock.patch.object(af, 'task_packet') as writer:
            code, result = call(af.command_advance, run_id=run['run_id'], max_steps=2)
        self.assertEqual(code, af.EXIT_WAITING)
        self.assertEqual(result['action'], 'repair_required')
        publish.assert_not_called(); writer.assert_not_called()

    def test_failed_downstream_review_does_not_rewrite_or_repeat_carry(self):
        directory, run = self.accepted()
        original = self.candidate.read_bytes()
        for state in ('DRAFT', 'EDIT'):
            with self.subTest(state=state):
                self.carry(directory, run, state)
                self.assertEqual(run['status'], 'BLOCKED')
                self.assertEqual(run['state'], state)
                self.assertEqual(af.artifact_path(directory, run, 'external-revision-candidate').read_bytes(), original)
                self.assertEqual(af.artifact_path(directory, run, 'article').read_bytes(), original)
                self.assertEqual(af.load_run(run['run_id'])[1]['status'], 'BLOCKED')

    def test_exact_retry_returns_original_owner_without_resuming_blocked_work(self):
        directory, run = self.opened()
        self.move(directory, run, 'DRAFT')
        run['status'] = 'BLOCKED'
        af.save_run(directory, run)
        before = (directory / 'run.json').read_bytes()
        with mock.patch.object(af, 'command_start') as start, mock.patch.object(af, 'command_advance') as advance:
            code, result = self.revise(auto=True)
        self.assertEqual(code, af.EXIT_WAITING)
        self.assertTrue(result['idempotent'])
        self.assertEqual(result['run_id'], run['run_id'])
        self.assertFalse(result['execution_started'])
        self.assertEqual((directory / 'run.json').read_bytes(), before)
        self.assertEqual(len(list(af.runs_root().glob('*/run.json'))), 1)
        start.assert_not_called(); advance.assert_not_called()

    def test_empty_visual_plan_does_not_claim_nonexistent_source_images(self):
        directory, run = self.opened()
        self.carry(directory, run, 'VISUAL_PLAN')
        plan = af.json_artifact(directory, run, 'visual-plan')
        self.assertEqual(plan['visuals'], [])
        self.assertIn('contains no illustrations', plan['omission_reason'])
        self.assertIn('Original title', plan['omission_reason'])

    def test_only_legacy_false_empty_plan_metadata_can_be_repaired_in_place(self):
        directory, run = self.opened()
        self.record_json(directory, run, 'visual-plan', {
            'visuals': [], 'omission_reason': 'This prose revision preserves the existing published illustrations in place and introduces no new diagrams.'})
        self.record_json(directory, run, 'editorial-repair-obligations', {'pending': [{
            'finding': {'criterion': 'visual', 'location': 'omission_reason'}}]})
        self.move(directory, run, 'VISUAL_PLAN')
        self.assertTrue(imported.legacy_empty_plan_repair(af, directory, run))
        self.record_json(directory, run, 'editorial-repair-obligations', {'pending': [{
            'finding': {'criterion': 'clarity', 'location': 'body'}}]})
        self.assertFalse(imported.legacy_empty_plan_repair(af, directory, run))

    def test_legacy_empty_plan_repair_preserves_bytes_and_renews_plan_binding(self):
        directory, run = self.opened()
        old_reason = 'This prose revision preserves the existing published illustrations in place and introduces no new diagrams.'
        with mock.patch.object(imported, 'empty_plan_reason', return_value=old_reason):
            self.carry(directory, run, 'VISUAL_PLAN')
        old_plan = af.artifact_path(directory, run, 'visual-plan')
        old_bytes = old_plan.read_bytes()
        self.record_json(directory, run, 'editorial-repair-obligations', {'pending': [{
            'finding': {'criterion': 'visual', 'location': 'omission_reason'}}]})
        self.carry(directory, run, 'VISUAL_PLAN')
        self.assertEqual(run['state'], 'VISUAL_RENDER')
        self.assertEqual(old_plan.read_bytes(), old_bytes)
        self.assertNotEqual(af.artifact_path(directory, run, 'visual-plan'), old_plan)
        self.assertEqual(af.artifact_path(directory, run, 'external-revision-candidate').read_bytes(), self.candidate.read_bytes())
        gate = af.json_artifact(directory, run, 'gate-receipt:G-VISUAL-PLAN')
        self.assertEqual(gate['outcome'], 'PASS')
        self.carry(directory, run, 'VISUAL_PLAN')
        self.assertEqual(run['status'], 'BLOCKED')

    def test_metadata_recheck_reuses_existing_edit_acceptance_without_rewriting(self):
        directory, run = self.accepted()
        original_acceptance = dict(af.artifact(run, 'external-revision-acceptance:EDIT'))
        af.append_event(directory, run, 'REPAIR', 'controller', {'reason': 'legacy_empty_visual_plan_metadata'})
        self.carry(directory, run, 'EDIT')
        self.assertEqual(run['state'], 'POST_EDIT_CLAIM_VERIFICATION')
        self.assertEqual(af.artifact(run, 'external-revision-acceptance:EDIT'), original_acceptance)
        self.assertEqual(af.artifact_path(directory, run, 'article').read_bytes(), self.candidate.read_bytes())
        self.move(directory, run, 'EDITORIAL_QA')
        self.carry(directory, run, 'EDIT')
        self.assertEqual(run['status'], 'BLOCKED')

    def test_early_interrupted_intake_cannot_resume_as_an_ordinary_article(self):
        with mock.patch.object(imported, 'install', side_effect=OSError('storage interruption')):
            with self.assertRaises(OSError):
                self.revise()
        owner = next(af.runs_root().glob('*/run.json'))
        directory, run = af.load_run(owner.parent.name)
        self.assertTrue(imported.enabled(af, run))
        self.assertEqual(af.next_state_payload(directory, run)['action'], 'reconciliation_required')
        before = owner.read_bytes()
        with mock.patch.object(af, 'command_execute_stage') as execute:
            with self.assertRaisesRegex(af.FlowError, 'intake is incomplete'):
                call(af.command_advance, run_id=run['run_id'], max_steps=1)
            with self.assertRaisesRegex(af.FlowError, 'intake is incomplete'):
                af.task_packet(directory, run)
        execute.assert_not_called()
        self.assertEqual(owner.read_bytes(), before)
        self.assertEqual(af.model_history()['count'], 0)

    def test_two_simultaneous_processes_create_one_owner(self):
        worker = r'''
import argparse, json, os, sys, time
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit
scripts, runtime, repo, source, candidate, feedback, ready, index = sys.argv[1:]
sys.path.insert(0, scripts)
os.environ.update(ARTICLE_FLOW_HOME=runtime, ARTICLE_FLOW_RUNS_ROOT=str(Path(runtime)/'runs'),
                  ARTICLE_FLOW_TEST_NO_PUBLISH='1', PYTHONDONTWRITEBYTECODE='1')
import article_flow as af
repository = Path(repo)
original_start = af.command_start
def slow_start(args):
    time.sleep(0.25)  # Both requests overlap the original check/create window.
    return original_start(args)
def fetch(url, timeout=30):
    path = repository / urlsplit(url).path.lstrip('/')
    return (200, path.read_bytes(), {})
Path(ready, index).touch()
deadline = time.monotonic()+30
while len(list(Path(ready).iterdir())) != 2:
    if time.monotonic() > deadline:
        raise RuntimeError('second intake process did not start')
    time.sleep(0.01)
args = argparse.Namespace(source_file=source, candidate_file=candidate, request_file=feedback,
    source_run_id=None, published_slug=None, expected_source_sha256=None,
    unattended_editorial=True, authorization='Automatically validate this fixture revision.',
    hold_before_publish=False, auto=False, json=True)
with mock.patch.object(af,'check_manifest',return_value={'ok':True}), \
     mock.patch.object(af,'publication_repo_root',return_value=repository), \
     mock.patch.object(af,'fetch_url',side_effect=fetch), \
     mock.patch.object(af,'command_start',side_effect=slow_start):
    raise SystemExit(af.command_revise(args))
'''
        ready = self.root / 'ready'
        ready.mkdir()
        command = [sys.executable, '-B', '-c', worker, str(af.SPEC_ROOT / 'scripts'),
                   str(self.runtime), str(self.repo), str(self.envelope), str(self.candidate),
                   str(self.feedback), str(ready)]
        children = []
        try:
            for index in ('one', 'two'):
                children.append(subprocess.Popen([*command, index], stdout=subprocess.PIPE,
                                                  stderr=subprocess.PIPE, text=True))
            results = []
            for child in children:
                stdout, stderr = child.communicate(timeout=90)
                self.assertEqual(child.returncode, af.EXIT_OK, stdout + stderr)
                results.append(json.loads(stdout))
            self.assertEqual(results[0]['run_id'], results[1]['run_id'])
            self.assertEqual(sum(bool(value.get('idempotent')) for value in results), 1)
            self.assertEqual(len(list(af.runs_root().glob('*/run.json'))), 1)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.communicate()

    def test_retry_before_intake_marker_keeps_the_original_owner(self):
        with mock.patch.object(imported, 'install', side_effect=OSError('storage interruption')):
            with self.assertRaisesRegex(OSError, 'storage interruption'):
                self.revise()
        owners = list(af.runs_root().glob('*/run.json'))
        self.assertEqual(len(owners), 1)
        directory, run = af.load_run(owners[0].parent.name)
        self.assertIsNone(af.artifact(run, 'external-revision-intake'))
        before = (directory / 'run.json').read_bytes()
        with mock.patch.object(af, 'command_start') as start, mock.patch.object(af, 'command_advance') as advance:
            with self.assertRaisesRegex(af.FlowError, 'interrupted installation') as caught:
                self.revise(auto=True)
        self.assertEqual(caught.exception.details['run_id'], run['run_id'])
        self.assertEqual(caught.exception.details['action'], 'reconciliation_required')
        self.assertEqual((directory / 'run.json').read_bytes(), before)
        self.assertEqual(len(list(af.runs_root().glob('*/run.json'))), 1)
        start.assert_not_called(); advance.assert_not_called()

    def test_retry_after_reservation_before_run_creation_does_not_create_another_run(self):
        with mock.patch.object(af, 'run_dir', side_effect=OSError('interrupted before mkdir')):
            with self.assertRaisesRegex(OSError, 'interrupted before mkdir'):
                self.revise()
        self.assertEqual(list(af.runs_root().glob('*/run.json')), [])
        records = list((af.runs_root() / '.external-revisions').glob('*.json'))
        self.assertEqual(len(records), 1)
        owner = af.load_json(records[0])
        with mock.patch.object(af, 'command_start') as start:
            with self.assertRaisesRegex(af.FlowError, 'interrupted installation') as caught:
                self.revise()
        self.assertEqual(caught.exception.details['run_id'], owner['run_id'])
        self.assertEqual(list(af.runs_root().glob('*/run.json')), [])
        self.assertEqual(af.load_json(records[0]), owner)
        start.assert_not_called()

    def test_damaged_owner_record_blocks_without_replacing_it(self):
        directory, run = self.opened()
        path = next((af.runs_root() / '.external-revisions').glob('*.json'))
        path.write_bytes(b'{partial owner')
        with mock.patch.object(af, 'command_start') as start:
            with self.assertRaisesRegex(af.FlowError, 'damaged owner'):
                self.revise()
        self.assertEqual(path.read_bytes(), b'{partial owner')
        self.assertEqual(len(list(af.runs_root().glob('*/run.json'))), 1)
        start.assert_not_called()

    def test_legacy_import_without_reservation_returns_its_existing_owner(self):
        directory, run = self.opened()
        next((af.runs_root() / '.external-revisions').glob('*.json')).unlink()
        run['run_overrides'].pop('external_revision_intake')
        af.save_run(directory, run)
        with mock.patch.object(af, 'command_start') as start:
            code, result = self.revise()
        self.assertEqual(code, af.EXIT_OK)
        self.assertEqual(result['run_id'], run['run_id'])
        self.assertTrue(result['idempotent'])
        start.assert_not_called()

    def interrupted_install(self):
        immutable_write = af.immutable_write

        def interrupt(path, data):
            if path.name == 'external-revision-candidate.md':
                raise af.FlowError('Fixture interruption before candidate installation')
            return immutable_write(path, data)

        with mock.patch.object(af, 'immutable_write', side_effect=interrupt):
            with self.assertRaisesRegex(af.FlowError, 'Fixture interruption'):
                self.revise()
        owners = list(af.runs_root().glob('*/run.json'))
        self.assertEqual(len(owners), 1)
        directory, run = af.load_run(owners[0].parent.name)
        intake = af.json_artifact(directory, run, 'external-revision-intake')
        self.assertEqual(intake, {
            'source_file_sha256': af.sha256_path(self.envelope),
            'candidate_sha256': af.sha256_path(self.candidate),
            'author_feedback_sha256': af.sha256_path(self.feedback),
        })
        self.assertIsNone(af.artifact(run, 'external-revision'))
        return directory, run

    def test_matching_partial_install_requires_original_owner_reconciliation(self):
        directory, run = self.interrupted_install()
        before = (directory / 'run.json').read_bytes()
        with mock.patch.object(af, 'command_start') as start, mock.patch.object(af, 'command_advance') as advance:
            with self.assertRaisesRegex(af.FlowError, 'interrupted installation') as caught:
                self.revise(auto=True)
        self.assertEqual(caught.exception.code, af.EXIT_INTEGRITY)
        self.assertEqual(caught.exception.details, {'run_id': run['run_id'], 'action': 'reconciliation_required'})
        self.assertEqual((directory / 'run.json').read_bytes(), before)
        self.assertEqual(len(list(af.runs_root().glob('*/run.json'))), 1)
        start.assert_not_called(); advance.assert_not_called()

    def test_unrelated_partial_install_does_not_block_another_candidate(self):
        directory, partial = self.interrupted_install()
        before = (directory / 'run.json').read_bytes()
        self.candidate.write_bytes(self.candidate.read_bytes().replace(b'clearer explanation', b'more useful explanation'))
        with mock.patch.object(af, 'command_publish_execute') as publish:
            code, result = self.revise()
        self.assertEqual(code, af.EXIT_OK, result)
        self.assertNotEqual(result['run_id'], partial['run_id'])
        self.assertEqual((directory / 'run.json').read_bytes(), before)
        self.assertEqual(len(list(af.runs_root().glob('*/run.json'))), 2)
        self.assertTrue(imported.enabled(af, af.load_run(result['run_id'])[1]))
        publish.assert_not_called()

    def test_completed_external_revision_is_excluded_from_writer_history(self):
        directory, run = self.accepted()
        self.move(directory, run, 'COMPLETE')
        assignment = af.json_artifact(directory, run, 'model-assignment')
        self.assertTrue(assignment['assigned_model_id'])
        history = af.model_state_root() / 'history.jsonl'
        before = history.read_bytes() if history.exists() else None
        self.assertIsNone(af.record_experiment_outcome(directory, run))
        self.assertEqual(history.read_bytes() if history.exists() else None, before)
        summary = af.summarize_model_experiment(directory, run)
        self.assertIsNone(summary['actual_model_id'])
        self.assertIsNone(summary['provider_id'])
        self.assertTrue(summary['excluded_external_revision'])
        self.assertEqual(summary['writing_stages'], [])
        evidence = af.model_history()
        self.assertEqual(evidence['count'], 0)
        self.assertEqual(evidence['runs'], [])
        self.assertEqual(evidence['comparison']['models'], [])
        comparison = af.model_comparison_summary([
            {**assignment, **summary, 'run_id': run['run_id'], 'state': 'COMPLETE'}
        ], [])
        self.assertEqual(comparison['models'], [])

    def test_rejected_stale_input_creates_no_run(self):
        self.write_page(self.markdown + '\nA correction published while GPT was editing.\n')
        self.commit()
        with mock.patch.object(af, 'command_start') as start:
            with self.assertRaises(af.FlowError):
                self.revise()
        start.assert_not_called()
        self.assertEqual(list(af.runs_root().glob('*/run.json')), [])

    def test_candidate_cannot_be_dispatched_as_an_assigned_writer_response(self):
        directory, run = self.opened()
        self.move(directory, run, 'DRAFT')
        next_action = af.next_state_payload(directory, run)
        self.assertEqual(next_action['command'], ['article-flow', 'advance', run['run_id']])
        with self.assertRaisesRegex(af.FlowError, 'not a model task'):
            af.task_packet(directory, run)

    def test_existing_images_are_bound_and_asset_drift_stops_the_update(self):
        self.add_image()
        directory, run = self.opened()
        bound = imported.assets(af, directory, run)
        self.assertEqual(len(bound), 1)
        self.assertEqual((directory / bound[0]['source_path']).read_bytes(), self.image)
        imported.assert_current_assets(af, run)
        self.image_path.write_bytes(b'changed without touching the article')
        with self.assertRaisesRegex(af.FlowError, 'asset changed'):
            imported.assert_current_assets(af, run)

    def test_image_survives_empty_new_visual_plan_and_actual_publication_render(self):
        self.add_image()
        directory, run = self.accepted()
        self.carry(directory, run, 'VISUAL_PLAN')
        self.assertEqual(run['state'], 'VISUAL_RENDER')
        code, result = call(af.command_visual_render, run_id=run['run_id'], refresh=False)
        self.assertEqual(code, af.EXIT_OK, result)
        directory, run = af.load_run(run['run_id'])
        self.record_json(directory, run, 'brief', {'title': 'Original title', 'slug': self.slug, 'date': '2026-09-15', 'description': 'A clearer explanation', 'tags': []})
        metadata = af.package_metadata(directory, run)
        package = directory / 'rendered-test-package'
        files = af.render_publication_files(directory, run, package, metadata)
        target = package / 'site/assets/articles/external-revision/diagram.svg'
        self.assertIn(target, files)
        self.assertEqual(target.read_bytes(), self.image)
        rendered = (package / f'site/docs/{self.slug}.html').read_text(encoding='utf-8')
        self.assertIn('src="/assets/articles/external-revision/diagram.svg"', rendered)
        self.assertIn('alt="Exact alt"', rendered)
        self.assertEqual(af.unplanned_visual_reference_findings(directory, run, self.candidate.read_text(), 'candidate'), [])

    def test_actual_rendered_public_handoff_binds_source_and_excludes_feedback(self):
        directory, run = self.accepted()
        self.record_json(directory, run, 'brief', {'title': 'Original title', 'slug': self.slug, 'date': '2026-09-15', 'description': 'A clearer explanation', 'tags': []})
        metadata = af.package_metadata(directory, run)
        self.assertEqual(metadata['date_iso'], self.stamp)
        self.assertEqual(metadata['drafting_models'], [])
        self.assertEqual(metadata['external_revision'], {'source': 'external_assistant', 'exact_model': None, 'human_original': False})
        package = directory / 'rendered-test-package'
        files = af.render_publication_files(directory, run, package, metadata)
        rendered = package / f'site/docs/{self.slug}.html'
        handoff = package / f'site/docs/{self.slug}.revision.json'
        self.assertIn(handoff, files)
        value = af.load_json(handoff)
        self.assertEqual(value['source']['source_html_sha256'], af.sha256_path(rendered))
        self.assertEqual(value['source']['source_markdown_sha256'], af.sha256_bytes(value['article_markdown'].encode()))
        self.assertEqual(value['article_markdown'].encode(), self.candidate.read_bytes())
        self.assertIsNone(value['source']['source_commit'])
        self.assertNotIn('private author note', handoff.read_text())
        self.assertNotIn(str(self.root), handoff.read_text())
        self.assertIn(f'href="{self.slug}.revision.json"', rendered.read_text(encoding='utf-8'))
        self.assertIn('Revision text supplied in GPT; exact model unverified.', rendered.read_text(encoding='utf-8'))

    def test_public_source_hash_binds_rendered_body_and_excludes_private_frontmatter(self):
        private = 'Sensitive internal revision note retained only in the candidate artifact'
        raw = ('---\ntitle: Original title\nprivate_revision_note: ' + private + '\n---\n\n').encode() + self.candidate.read_bytes()
        self.candidate.write_bytes(raw)
        directory, run = self.accepted()
        self.record_json(directory, run, 'brief', {'title': 'Original title', 'slug': self.slug, 'date': '2026-09-15', 'description': 'A clearer explanation', 'tags': []})
        metadata = af.package_metadata(directory, run)
        package = directory / 'rendered-test-package'
        af.render_publication_files(directory, run, package, metadata)
        rendered = package / f'site/docs/{self.slug}.html'
        handoff = package / f'site/docs/{self.slug}.revision.json'
        value = af.load_json(handoff)
        public_body = external.public_markdown(af, raw)
        self.assertNotEqual(public_body, raw)
        self.assertEqual(value['article_markdown'].encode(), public_body)
        digest = af.sha256_bytes(public_body)
        self.assertEqual(value['source']['source_markdown_sha256'], digest)
        self.assertEqual(value['source']['source_html_sha256'], af.sha256_path(rendered))
        self.assertIn(f'<meta name="article-flow-revision-source-sha256" content="{digest}">', rendered.read_text(encoding='utf-8'))
        self.assertNotIn(private, rendered.read_text(encoding='utf-8'))
        self.assertNotIn(private, handoff.read_text(encoding='utf-8'))
        self.assertNotIn('private author note', handoff.read_text(encoding='utf-8'))
        self.assertEqual(af.artifact_path(directory, run, 'external-revision-candidate').read_bytes(), raw)

    def test_actual_package_binds_external_provenance_and_every_public_handoff_byte(self):
        directory, run = self.accepted()
        self.carry(directory, run, 'VISUAL_PLAN')
        code, result = call(af.command_visual_render, run_id=run['run_id'], refresh=False)
        self.assertEqual(code, af.EXIT_OK, result)
        directory, run = af.load_run(run['run_id'])
        self.record_json(directory, run, 'brief', {'title': 'Original title', 'slug': self.slug, 'date': '2026-09-15', 'description': 'A clearer explanation', 'tags': []})
        for name in ('script.js', 'projects.html', 'reach-out.html'):
            (self.repo / name).write_text('A public supporting file.', encoding='utf-8')
        self.move(directory, run, 'PACKAGE')
        with mock.patch.object(af, 'command_publish_execute') as publish:
            code, result = call(af.command_package, run_id=run['run_id'])
        self.assertEqual(code, af.EXIT_OK, result)
        directory, run = af.load_run(run['run_id'])
        self.assertEqual(run['state'], 'PUBLISH_APPROVAL')
        package = af.load_json(directory / 'package/package.json')
        self.assertIn('exact model unverified', package['model_attribution']['public_display_name'])
        self.assertTrue(package['model_attribution']['source_receipt_hashes'])
        self.assertNotIn('external-assistant-unverified', json.dumps(package))
        entries = {item['path']: item['sha256'] for item in package['public_files']}
        for suffix in ('.html', '.revision.json'):
            relative = f'site/docs/{self.slug}{suffix}'
            self.assertEqual(entries[relative], af.sha256_path(directory / 'package' / relative))
        self.assertNotIn('private author note', (directory / f'package/site/docs/{self.slug}.revision.json').read_text())
        publish.assert_not_called()

    def test_no_edit_path_stays_complete_and_creates_no_revision_wait(self):
        run_id = self.start('An ordinary published article.')
        directory, run = af.load_run(run_id)
        run['publication'] = {'status': 'VERIFIED', 'url': self.url}
        af.transition(directory, run, 'COMPLETE', 'test', 'Existing verified publication')
        before = (directory / 'run.json').read_bytes()
        code, result = call(af.command_advance, run_id=run_id, max_steps=10)
        self.assertEqual(code, af.EXIT_OK)
        self.assertEqual(result['action'], 'complete')
        self.assertTrue(result['optional_revision']['optional'])
        self.assertIsNone(result['optional_revision']['source_url'])
        self.assertEqual((directory / 'run.json').read_bytes(), before)
        self.assertEqual(len(list(af.runs_root().glob('*/run.json'))), 1)
        self.assertEqual(af.next_state_payload(directory, run)['action'], 'complete')

    def live_fixture(self):
        self.add_image()
        directory, run = self.accepted()
        self.record_json(directory, run, 'brief', {'title': 'Original title', 'slug': self.slug, 'date': '2026-09-15', 'description': 'A clearer explanation', 'tags': []})
        metadata = af.package_metadata(directory, run)
        package = directory / 'package'
        af.atomic_write(package / 'public/article.md', self.candidate.read_bytes())
        af.write_json(package / 'public/metadata.json', metadata)
        af.write_json(package / 'public/assets.json', {'assets': []})
        files = af.render_publication_files(directory, run, package, metadata)
        af.write_json(package / 'package.json', {'package_revision': 'f' * 64,
                     'public_files': [{'path': path.relative_to(package).as_posix(), 'sha256': af.sha256_path(path)} for path in files]})
        for path in files:
            relative = path.relative_to(package / 'site').as_posix()
            self.pages['https://theproductiveprompter.com/' + relative] = path.read_bytes()
        self.pages['https://theproductiveprompter.com/'] = (package / 'site/index.html').read_bytes()
        expected = {key: (package / 'site' / relative).read_bytes() for key, relative in
                    {'blog': 'docs/blog.html', 'homepage': 'index.html', 'feed': 'feed.xml', 'sitemap': 'sitemap.xml'}.items()}
        self.move(directory, run, 'LIVE_VERIFICATION')
        return directory, run, expected

    def test_mismatched_live_source_handoff_does_not_complete_publication(self):
        directory, run, expected = self.live_fixture()
        self.pages[self.url.removesuffix('.html') + '.revision.json'] = b'Wrong deployed handoff bytes'
        with mock.patch.object(af, 'live_discovery_scope', return_value=(expected, None)):
            code, result = call(af.command_verify_live, run_id=run['run_id'])
        self.assertEqual(code, af.EXIT_FAILED)
        failed = [item for item in result['checks'] if not item['ok']]
        self.assertEqual([item['name'] for item in failed], ['revision_source'])
        durable = af.load_run(run['run_id'])[1]
        self.assertEqual(durable['state'], 'LIVE_VERIFICATION')
        self.assertNotEqual(durable.get('publication', {}).get('status'), 'VERIFIED')

    def test_mismatched_live_preserved_image_does_not_complete_publication(self):
        directory, run, expected = self.live_fixture()
        self.pages[self.image_url] = b'Changed deployed diagram without changing the page'
        with mock.patch.object(af, 'live_discovery_scope', return_value=(expected, None)):
            code, result = call(af.command_verify_live, run_id=run['run_id'])
        self.assertEqual(code, af.EXIT_FAILED)
        failed = [item for item in result['checks'] if not item['ok']]
        self.assertEqual([item['name'] for item in failed], ['visual_asset'])
        self.assertEqual(failed[0]['url'], self.image_url)
        durable = af.load_run(run['run_id'])[1]
        self.assertEqual(durable['state'], 'LIVE_VERIFICATION')
        self.assertNotEqual(durable.get('publication', {}).get('status'), 'VERIFIED')
