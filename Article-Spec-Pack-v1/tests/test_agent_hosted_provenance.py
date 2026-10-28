"""Packaging accepts real host submissions without pretending to call an API."""
import contextlib
import copy
import io
from pathlib import Path
from unittest import mock

import test_article_flow_v3 as fixtures
import test_editorial_system as editorial_fixtures

af = fixtures.af


class AgentHostedProvenanceTests(fixtures.TemporaryRuntime):
    def route_set(self, stage):
        routes = fixtures.NoPublishAutomationTests.route_set(self, stage)
        if stage in af.V3_WRITING_STATES:
            chosen = {**routes['chosen'], 'provider': 'active-host', 'model': 'claude-opus-5-5',
                      'kind': 'agent-hosted', 'reasoning_effort': 'xhigh'}
            routes.update(candidates=[chosen], chosen=chosen, fallbacks=[])
        return routes

    def stage_value(self, stage, directory, run):
        return editorial_fixtures.CurrentAutomationTests().stage_value(stage, directory, run)

    def execute_fixture_stage(self, args):
        directory, run = af.load_run(args.run_id)
        if run['state'] not in af.V3_WRITING_STATES:
            return fixtures.NoPublishAutomationTests.execute_fixture_stage(self, args)
        _, packet = af.current_packet(directory, run)
        output = Path(packet['expected_outputs'][0]['path'])
        value = self.stage_value(run['state'], directory, run)
        if isinstance(value, dict):
            af.write_json(output, value)
        else:
            af.atomic_write(output, value.encode('utf-8'))
        # This is a synthetic host-authored fixture, not a provider/API call.
        with contextlib.redirect_stdout(io.StringIO()):
            return af.command_submit(fixtures.namespace(run_id=run['run_id'], stage=run['state'], file=str(output)))

    def test_host_submissions_package_with_bound_private_evidence_and_no_api_metrics(self):
        with mock.patch.object(af, 'route_candidates', side_effect=lambda stage, excluded_routes=None: self.route_set(stage)), \
             mock.patch.object(af, 'command_execute_stage', side_effect=self.execute_fixture_stage), \
             mock.patch.object(af, 'command_publish_execute', side_effect=AssertionError('must not publish')) as publish:
            run_id = editorial_fixtures.CurrentAutomationTests.start(self, draft_provider='active-host', draft_model='claude-opus-5-5',
                                                 hold_before_publish=True)
            code, waiting = fixtures.call(af.command_advance, run_id=run_id)
            self.assertEqual((code, waiting['state'], waiting['action']),
                             (af.EXIT_WAITING, 'VOICE_PROBE', 'human_decision'))
            command = af.build_parser().parse_args(['choose-voice', run_id, 'B', '--json'])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(af.command_choose_voice(command), af.EXIT_WAITING)
        publish.assert_not_called()
        directory, run = af.load_run(run_id)
        self.assertEqual(run['state'], 'PUBLISH_APPROVAL')
        evidence = af.package_writing_provenance(directory, run)
        host = evidence['agent_hosted_acceptances']
        self.assertEqual({item['stage'] for item in host}, af.V3_WRITING_STATES)
        self.assertEqual(len(host), 3)
        self.assertEqual({item['model_id'] for item in host}, {'claude-opus-5-5'})
        self.assertEqual({item['configured_reasoning_effort'] for item in host}, {'xhigh'})
        self.assertFalse(any(any(item['type'].startswith(f'model-call:{stage}:') for stage in af.V3_WRITING_STATES)
                             for item in run['artifact_index']))
        package = af.load_json(directory / 'package/package.json')
        self.assertEqual(set(package['model_attribution']['source_receipt_hashes']),
                         {item['gate_receipt']['sha256'] for item in host})
        self.assertEqual(af.load_json(directory / 'package/private/writing-provenance.json'), evidence)
        archive = af.load_json(directory / 'package/private/archive-index.json')
        self.assertIn('writing-provenance.json', {item['path'] for item in archive['files']})
        self.assertFalse((directory / 'package/public/writing-provenance.json').exists())
        self.assertEqual(af.validate_json_schema(directory / 'package/package.json', 'package.schema.json', run), [])
        self.assertIsNone(af.summarize_model_experiment(directory, run)['elapsed_milliseconds'])
        self.assertEqual(af.summarize_model_experiment(directory, run)['token_usage'], {})
        history = af.record_experiment_outcome(directory, run)
        self.assertIsNone(history['elapsed_milliseconds'])
        self.assertEqual(history['token_usage'], {})
        wrong_attribution = copy.deepcopy(run)
        wrong_attribution['model_experiment']['actual_models'] = ['other-model']
        with self.assertRaises(af.FlowError):
            af.package_writing_provenance(directory, wrong_attribution)

        for kind in ('task', 'output', 'gate_receipt'):
            path = directory / host[-1][kind]['path']
            before = path.read_bytes()
            try:
                path.write_bytes(before + b'\nchanged')
                with self.subTest(tampered=kind), self.assertRaises(af.FlowError):
                    af.package_writing_provenance(directory, run)
            finally:
                path.write_bytes(before)
        # A copied acceptance or route mismatch in a *valid* event chain is
        # rejected too; it is not enough to pass the chain/hash verifier.
        real_verify = af.verify_event_log
        ok, error, state, events = real_verify(directory, run)
        for field, value in (('actual_model_id', 'other-model'), ('provider_id', 'other-provider'),
                             ('assigned_model_id', 'other-model')):
            altered = copy.deepcopy(events)
            event = next(item for item in reversed(altered) if item['type'] == 'WRITING_MODEL_ACCEPTED')
            event['payload'][field] = value
            with self.subTest(mismatched=field), \
                 mock.patch.object(af, 'verify_event_log', return_value=(ok, error, state, altered)), \
                 self.assertRaises(af.FlowError):
                af.package_writing_provenance(directory, run)
        with mock.patch.object(af, 'verify_event_log', return_value=(False, 'changed chain', state, events)), \
             self.assertRaises(af.FlowError):
            af.package_writing_provenance(directory, run)
        altered = copy.deepcopy(events)
        next(item for item in reversed(altered) if item['type'] == 'WRITING_MODEL_ACCEPTED')['run_id'] = 'AF-foreign'
        with mock.patch.object(af, 'verify_event_log', return_value=(ok, error, state, altered)), \
             self.assertRaises(af.FlowError):
            af.package_writing_provenance(directory, run)
        altered = copy.deepcopy(events)
        output = next(item['payload']['artifact'] for item in reversed(altered)
                      if item['type'] == 'ARTIFACT_RECORDED'
                      and item['payload']['artifact']['path'] == host[-1]['output']['path'])
        output['producer']['route']['kind'] = 'command'
        with mock.patch.object(af, 'verify_event_log', return_value=(ok, error, state, altered)), \
             self.assertRaises(af.FlowError):
            af.package_writing_provenance(directory, run)

    def test_mutable_model_cache_cannot_replace_receipt_evidence(self):
        run_id = self.start()
        directory, run = af.load_run(run_id)
        run['model_experiment'].update(actual_models=['claude-opus-5-5'], stage_routes={
            'DRAFT': {'provider_id': 'active-host', 'actual_model_id': 'claude-opus-5-5'}})
        with self.assertRaisesRegex(af.FlowError, 'lacks writing-model'):
            af.package_writing_provenance(directory, run)
