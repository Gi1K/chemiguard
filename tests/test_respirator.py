import copy
import json
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from chemiguard.app import PolicyInput, lifespan
from chemiguard.decisions import observe, questions_for
from chemiguard.observation import combine_observation
from chemiguard.wearing import PARTS, summarize_parts


POLICY = {'hood_required': True, 'closure_required': True, 'closure_location': 'front flap',
          'closure_assessment': 'external_appearance', 'wearing_assessment': 'visible_regions',
          'respirator_required': True}
COVERED = {name: 'covered' for name in (*PARTS, 'hood', 'respirator')} | {'closure': 'closed'}


class RespiratorRules(unittest.TestCase):
    def test_visible_missing_hidden_and_uncertain_face_are_distinct(self):
        self.assertEqual(summarize_parts(COVERED, POLICY)['wearing'], 'WORN')
        missing = summarize_parts(COVERED | {'respirator': 'uncovered'}, POLICY)
        self.assertEqual(missing['wearing'], 'NOT_WORN')
        self.assertEqual(missing['violations'], ['필수 전면형 방독면 미착용'])
        hidden = summarize_parts(COVERED | {'respirator': 'not_visible'}, POLICY)
        self.assertEqual(hidden['wearing'], 'VISIBLE_WORN')
        self.assertFalse(hidden['all_required_observed'])
        self.assertIn('respirator', hidden['unobserved_parts'])
        for state in ('uncertain', None):
            self.assertEqual(summarize_parts(COVERED | {'respirator': state}, POLICY)['wearing'], 'UNKNOWN')

    def test_old_and_disabled_policies_do_not_gain_a_face_requirement(self):
        for policy in ({k: v for k, v in POLICY.items() if k != 'respirator_required'},
                       POLICY | {'respirator_required': False}):
            self.assertNotIn('respirator', [row['name'] for row in questions_for(policy)])
            self.assertEqual(summarize_parts(COVERED | {'respirator': 'uncovered'}, policy)['wearing'], 'WORN')
        question = next(row for row in questions_for(POLICY) if row['name'] == 'respirator')
        self.assertEqual({row['value'] for row in question['choices']},
                         {'covered', 'uncovered', 'not_visible', 'uncertain'})
        self.assertIn('half-face respirator plus goggles', question['instructions'])
        strict = POLICY | {'wearing_assessment': 'all_required'}
        self.assertEqual(summarize_parts(COVERED | {'respirator': 'unobservable'}, strict)['wearing'], 'UNKNOWN')

    def test_face_alarm_requires_direct_face_recovery_twice(self):
        track = {'history': [], 'active_violations': []}
        def see(face, moment):
            parts = COVERED | {'respirator': face}
            result = summarize_parts(parts, POLICY) | {'parts': parts, 'wearing_assessment': 'visible_regions'}
            return combine_observation(track, result, moment, str(moment), 5, 10)
        see('uncovered', 1)
        self.assertEqual(see('uncovered', 2)['new_violations'], ['필수 전면형 방독면 미착용'])
        for moment in (3, 4):
            self.assertFalse(see('not_visible', moment)['cleared'])
        self.assertFalse(see('covered', 5)['cleared'])
        recovered = see('covered', 6)
        self.assertEqual(recovered['cleared_violations'], ['필수 전면형 방독면 미착용'])
        self.assertEqual(recovered['supporting_observation_ids'], ['5', '6'])

    def test_head_input_is_sent_when_hood_is_disabled_but_face_is_required(self):
        policy = POLICY | {'hood_required': False}
        questions = questions_for(policy)
        answers = [{'type': 'choice', 'name': row['name'], 'choice': COVERED[row['name']],
                    'probabilities': [{'value': choice['value'], 'probability':
                                       1.0 if choice['value'] == COVERED[row['name']] else 0.0}
                                      for choice in row['choices']]} for row in questions]
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'offline-test-key'}), \
                patch('chemiguard.decisions.jpeg', return_value=b'offline-test-image'), \
                patch('chemiguard.decisions.httpx.post') as post:
            post.return_value.status_code = 200
            post.return_value.headers = {}
            post.return_value.json.return_value = {'answers': answers}
            result = observe({'person': object(), 'head': object()}, policy)
            request = json.loads(post.call_args.kwargs['content'])
        labels = [part['text'] for part in request['input'][0]['content'] if part['type'] == 'input_text']
        self.assertTrue(any(text.startswith('Image: head.') for text in labels))
        self.assertEqual(result['parts']['respirator'], 'covered')
        self.assertEqual(result['prompt_version'], 'ppe-observation-v5')
        self.assertEqual(result['respirator_assessment'], 'full_face_external_appearance')
        self.assertIsNone(result['error'])

    def test_policy_default_and_disabled_observation_validation(self):
        self.assertTrue(PolicyInput(name='test', zone_id='test').respirator_required)
        with self.assertRaises(ValidationError):
            PolicyInput(name='test', zone_id='test', coverall_required=False,
                        hood_required=False, closure_required=False)
        self.assertFalse(PolicyInput(name='test', zone_id='test', coverall_required=False,
                                     hood_required=False, closure_required=False,
                                     respirator_required=False).respirator_required)


class RespiratorMigration(unittest.IsolatedAsyncioTestCase):
    async def test_default_upgrade_is_append_only_and_idempotent(self):
        for enabled in (True, False):
            old = PolicyInput(name='화학보호복 기본 관찰', zone_id='test', coverall_required=enabled,
                              hood_required=enabled, closure_required=enabled,
                              respirator_required=enabled).model_dump()
            old.pop('respirator_required')
            old.update(id='old', revision=4, reference_revision=0)
            original = copy.deepcopy(old)
            rows = [old]
            def save(kind, row):
                rows.append(row | {'id': 'new'})
                return rows[-1]
            with patch('chemiguard.app.store') as store, patch('chemiguard.app.monitor') as monitor:
                store.list.side_effect = lambda kind: rows
                store.revision.return_value = 0
                store.put.side_effect = save
                monitor.busy.return_value = False
                async with lifespan(None):
                    pass
                async with lifespan(None):
                    pass
            self.assertEqual(old, original)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]['supersedes'], 'old')
            self.assertEqual(rows[1]['revision'], 5)
            self.assertEqual(rows[1]['respirator_required'], enabled)


if __name__ == '__main__':
    unittest.main()
