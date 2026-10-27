"""Explicit models use qualified provider routes without changing the experiment pool."""
from unittest import mock

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
