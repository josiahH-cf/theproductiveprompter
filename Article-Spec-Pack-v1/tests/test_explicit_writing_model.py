"""Explicit models use qualified provider routes without changing the experiment pool."""
from unittest import mock
import copy
import os

from test_article_flow_v3 import TemporaryRuntime, af, call


class ExplicitWritingModelTests(TemporaryRuntime):
    def routes(self, stage, eligible=True):
        return {'candidates': [{'provider': 'codex-cli', 'model': 'gpt-6.1-sol',
                               'eligible': eligible, 'exclusion_reason': None if eligible else 'canary invalid-evidence'}]}

    def test_parser_accepts_explicit_current_model_on_all_entrypoints(self):
        parser = af.build_parser()
        for argv in (['start', '--seed', 'seed'], ['capture', 'seed'],
                     ['revise', 'AF-existing', '--request-file', 'request.md']):
            self.assertEqual(parser.parse_args([*argv, '--draft-model', 'gpt-6.1-sol']).draft_model, 'gpt-6.1-sol')

    def test_qualified_explicit_model_does_not_change_rotation(self):
        original = list(af.writing_model_policy()['ordered_models'])
        with mock.patch.object(af, 'route_candidates', side_effect=self.routes):
            chosen = af.reserve_draft_model('AF-explicit', override='gpt-6.1-sol')
        following = af.reserve_draft_model('AF-following')
        self.assertEqual(chosen['assigned_model_id'], 'gpt-6.1-sol')
        self.assertFalse(chosen['consumes_rotation'])
        self.assertEqual(following['assigned_model_id'], original[0])
        self.assertEqual(af.writing_model_policy()['ordered_models'], original)

    def test_unqualified_or_partial_model_is_refused_before_assignment_write(self):
        for failed_stage in ('DRAFT', 'VOICE_PROBE', 'EDIT'):
            with mock.patch.object(af, 'route_candidates', side_effect=lambda stage: self.routes(stage, stage != failed_stage)):
                with self.assertRaises(af.FlowError):
                    af.reserve_draft_model('AF-unqualified', override='gpt-6.1-sol')
            self.assertFalse((af.model_state_root()/'assignments.jsonl').exists())

    def test_explicit_pin_is_held_when_exact_model_becomes_unavailable(self):
        run = {'workflow_version': '3.2.0', 'model_experiment': {
            'provider_id': 'codex-cli', 'assigned_model_id': 'gpt-6.1-sol',
            'active_model_id': 'gpt-6.1-sol', 'operator_model_override': True}}
        routes = {'candidates': [*self.routes('DRAFT', False)['candidates'],
                  {'provider':'codex-cli','model':'gpt-5.6-sol','eligible':True}], 'chosen':None}
        selected = af.pin_writing_route(run, 'DRAFT', routes)
        self.assertIsNone(selected['chosen'])
        self.assertEqual(selected['fallbacks'], [])
        self.assertIn('explicit', selected['reason'])

    def test_available_explicit_pin_exposes_no_substitution_routes(self):
        run = {'workflow_version':'3.2.0','model_experiment':{
            'provider_id':'codex-cli','assigned_model_id':'gpt-6.1-sol',
            'operator_model_override':True}}
        routes={'candidates':[*self.routes('DRAFT')['candidates'],
                {'provider':'codex-cli','model':'gpt-5.6-sol','eligible':True}]}
        result=af.pin_writing_route(run,'DRAFT',routes)
        self.assertEqual(result['chosen']['model'],'gpt-6.1-sol')
        self.assertEqual(result['fallbacks'],[])

    def test_unqualified_start_creates_no_article_directory(self):
        with mock.patch.object(af,'route_candidates',side_effect=lambda stage:self.routes(stage,False)):
            with self.assertRaises(af.FlowError):
                call(af.command_start,seed='Synthetic fixture only',seed_file=None,slug=None,
                     draft_model='gpt-6.1-sol')
        self.assertFalse((self.runtime/'runs').exists())

    def test_new_nonpool_assignment_is_frozen_as_an_explicit_pin(self):
        with mock.patch.object(af,'route_candidates',side_effect=self.routes):
            ident=self.start(draft_model='gpt-6.1-sol')
        _,run=af.load_run(ident)
        self.assertEqual(run['model_experiment']['assigned_model_id'],'gpt-6.1-sol')
        self.assertTrue(run['model_experiment']['operator_model_override'])

    def test_provider_and_model_parser_preserves_exact_values(self):
        for argv in (['start', '--seed', 'seed'], ['capture', 'seed'],
                     ['revise', 'AF-existing', '--request-file', 'request.md']):
            args = af.build_parser().parse_args([
                *argv, '--draft-provider', 'active-host', '--draft-model', 'claude-opus-5-5'])
            self.assertEqual((args.draft_provider, args.draft_model), ('active-host', 'claude-opus-5-5'))

    def host_config(self, model='claude-opus-5-5', stages=None):
        path = self.runtime / 'host-providers.json'
        af.write_json(path, {'provider_config_schema_version': '1.0.0', 'providers': [{
            'provider_id': 'active-host', 'kind': 'agent-hosted', 'enabled': True,
            'reasoning_effort': 'xhigh', 'models': [{
                'model_id': model, 'stages': stages or ['DRAFT', 'VOICE_PROBE', 'EDIT'],
                'capabilities': ['structured-output', 'long-form'],
            }],
        }]})
        return mock.patch.dict(os.environ, {'ARTICLE_FLOW_PROVIDER_CONFIG': str(path)})

    def test_real_registry_freezes_qualified_host_without_consuming_rotation(self):
        original = copy.deepcopy(af.writing_model_policy())
        with self.host_config():
            ident = self.start(draft_model='claude-opus-5-5', draft_provider='active-host')
            _, run = af.load_run(ident)
            for stage in ('DRAFT', 'VOICE_PROBE', 'EDIT'):
                selected = af.pin_writing_route(run, stage, af.route_candidates(stage))
                self.assertEqual((selected['chosen']['provider'], selected['chosen']['model']),
                                 ('active-host', 'claude-opus-5-5'))
                self.assertEqual(selected['fallbacks'], [])
            self.assertTrue(run['model_experiment']['operator_model_override'])
            assignment = af.json_artifact(af.run_dir(ident), run, 'model-assignment')
            self.assertFalse(assignment['consumes_rotation'])
            self.assertEqual(assignment['provider_id'], 'active-host')
        self.assertEqual(af.writing_model_policy(), original)
        following = af.reserve_draft_model('AF-following-host-pin')
        self.assertEqual(following['provider_id'], original['provider_id'])
        self.assertEqual(following['assigned_model_id'], original['ordered_models'][0])

    def test_provider_choice_requires_exact_model_before_any_run(self):
        for provider in ('active-host', '../active-host', 'active-host:other'):
            with self.assertRaises(af.FlowError):
                self.start(draft_provider=provider)
        self.assertFalse((self.runtime / 'runs').exists())
        self.assertFalse((af.model_state_root() / 'assignments.jsonl').exists())

    def test_each_stage_must_qualify_for_the_exact_provider(self):
        for missing in ('DRAFT', 'VOICE_PROBE', 'EDIT'):
            with self.host_config(stages=[s for s in ('DRAFT', 'VOICE_PROBE', 'EDIT') if s != missing]):
                with self.assertRaises(af.FlowError):
                    self.start(draft_model='claude-opus-5-5', draft_provider='active-host')
        self.assertFalse((self.runtime / 'runs').exists())

    def test_provider_assignment_cannot_change_on_retry(self):
        with self.host_config(model='gpt-6.1-sol'):
            af.reserve_draft_model('AF-same-model-other-provider', override='gpt-6.1-sol',
                                   provider_override='active-host')
        with mock.patch.object(af, 'route_candidates', side_effect=self.routes):
            with self.assertRaisesRegex(af.FlowError, 'draft-provider'):
                af.reserve_draft_model('AF-same-model-other-provider', override='gpt-6.1-sol',
                                       provider_override='codex-cli')

    def test_explicit_provider_closes_fallback_even_for_an_existing_pool_model(self):
        model = af.writing_model_policy()['ordered_models'][0]
        with mock.patch.object(af, 'route_candidates', return_value={'candidates': [{
                'provider': 'codex-cli', 'model': model, 'eligible': True}]}):
            ident = self.start(draft_model=model, draft_provider='codex-cli')
        _, run = af.load_run(ident)
        self.assertTrue(run['model_experiment']['operator_model_override'])
        selected = af.pin_writing_route(run, 'DRAFT', {'candidates': [{
            'provider': 'codex-cli', 'model': 'other-model', 'eligible': True}]})
        self.assertIsNone(selected['chosen'])
        self.assertEqual(selected['fallbacks'], [])

    def test_explicit_provider_loses_no_identity_when_route_disappears(self):
        with self.host_config():
            ident = self.start(draft_model='claude-opus-5-5', draft_provider='active-host')
            _, run = af.load_run(ident)
        before = copy.deepcopy(run['model_experiment'])
        for stage in ('DRAFT', 'VOICE_PROBE', 'EDIT'):
            selected = af.pin_writing_route(run, stage, af.route_candidates(stage))
            self.assertIsNone(selected['chosen'])
            self.assertEqual(selected['fallbacks'], [])
            self.assertIn('explicit', selected['reason'])
        self.assertEqual(run['model_experiment'], before)
