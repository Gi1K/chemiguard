import unittest

from chemiguard.decisions import parse_answers, questions_for
from chemiguard.observation import combine_observation, request_due
from chemiguard.wearing import PARTS, summarize_parts


POLICY = {'hood_required': True, 'closure_required': True, 'closure_location': 'front flap',
          'closure_assessment': 'external_appearance', 'wearing_assessment': 'visible_regions'}
SIDE = {name: 'covered' for name in PARTS} | {'hood': 'covered', 'closure': 'not_visible'}


class VisibleWearingRules(unittest.TestCase):
    def test_hidden_closure_is_not_full_completion(self):
        result = summarize_parts(SIDE, POLICY)
        self.assertEqual(result['wearing'], 'VISIBLE_WORN')
        self.assertFalse(result['all_required_observed'])
        self.assertFalse(result['review_required'])
        self.assertEqual(result['unobserved_parts'], ['closure'])
        self.assertEqual(summarize_parts(SIDE | {'closure': 'closed'}, POLICY)['wearing'], 'WORN')

    def test_visible_ambiguity_and_missing_evidence_are_not_positive(self):
        self.assertEqual(summarize_parts(SIDE | {'closure': 'uncertain'}, POLICY)['wearing'], 'UNKNOWN')
        tiny = {name: 'not_visible' for name in SIDE} | {'hood': 'covered'}
        self.assertEqual(summarize_parts(tiny, POLICY)['wearing'], 'UNKNOWN')
        self.assertEqual(summarize_parts({}, POLICY)['wearing'], 'UNKNOWN')
        side = tiny | {'torso': 'covered', 'left_arm': 'covered'}
        self.assertEqual(summarize_parts(side, POLICY)['wearing'], 'VISIBLE_WORN')

    def test_visible_violation_overrides_other_covered_parts(self):
        result = summarize_parts(SIDE | {'hood': 'uncovered'}, POLICY)
        self.assertEqual(result['wearing'], 'NOT_WORN')
        self.assertEqual(result['violations'], ['필수 후드 미착용'])
        self.assertEqual(summarize_parts(SIDE | {'closure': 'open'}, POLICY)['wearing'], 'NOT_WORN')

    def test_legacy_policy_keeps_all_parts_requirement(self):
        legacy = {key: value for key, value in POLICY.items() if key != 'wearing_assessment'}
        result = summarize_parts(SIDE | {'closure': 'unobservable'}, legacy)
        self.assertEqual(result['wearing'], 'UNKNOWN')
        self.assertTrue(result['review_required'])
        self.assertEqual(len(questions_for(legacy)[0]['choices']), 3)

    def test_weak_not_visible_answer_becomes_uncertain_not_positive(self):
        question = questions_for(POLICY)[-1]
        answer = {'type': 'choice', 'name': 'closure', 'choice': 'not_visible',
                  'probabilities': [{'value': value, 'probability': score} for value, score in
                                    [('closed', .35), ('open', .01), ('not_visible', .45), ('uncertain', .19)]]}
        parts, scores = parse_answers({'answers': [answer]}, [question])
        self.assertEqual(parts['closure'], 'uncertain')
        self.assertEqual(scores['closure']['choice'], 'not_visible')

    def test_turning_away_does_not_clear_open_closure(self):
        track = {'history': [], 'active_violations': []}
        def observe(parts, moment, error=None):
            result = summarize_parts(parts, POLICY) | {'parts': parts, 'wearing_assessment': 'visible_regions', 'error': error}
            return combine_observation(track, result, moment, str(moment), 5, 10)
        observe(SIDE | {'closure': 'open'}, 1)
        observe(SIDE | {'closure': 'open'}, 2)
        for moment in (3, 4):
            self.assertFalse(observe(SIDE, moment)['cleared'])
        self.assertTrue(track['confirmed'])
        self.assertFalse(track['complete_confirmed'])
        self.assertEqual(track['active_violations'], ['필수 여밈 열림'])
        self.assertFalse(observe(SIDE | {'closure': 'closed'}, 5)['cleared'])
        observe(SIDE | {'closure': 'closed'}, 6, error='timeout')
        self.assertFalse(observe(SIDE | {'closure': 'closed'}, 7)['cleared'])
        recovery = observe(SIDE | {'closure': 'closed'}, 8)
        self.assertEqual(recovery['cleared_violations'], ['필수 여밈 열림'])
        self.assertEqual(recovery['supporting_observation_ids'], ['7', '8'])
        self.assertTrue(track['complete_confirmed'])

    def test_recovery_is_per_part_and_expiry_breaks_it(self):
        track = {'history': [], 'active_violations': ['필수 후드 미착용', '필수 여밈 열림']}
        result = summarize_parts(SIDE, POLICY) | {'parts': SIDE, 'wearing_assessment': 'visible_regions'}
        for moment in (1, 7):
            combine_observation(track, result, moment, str(moment), 5, 10)
        self.assertEqual(len(track['active_violations']), 2)
        transition = combine_observation(track, result, 8, '8', 5, 10)
        self.assertEqual(transition['cleared_violations'], ['필수 후드 미착용'])
        self.assertEqual(track['active_violations'], ['필수 여밈 열림'])

    def test_visible_confirmation_cadence_and_unresolved_alarm(self):
        track = {'pending': False, 'last_requested': 10, 'confirmed': False, 'result': {'wearing': 'VISIBLE_WORN'}}
        self.assertEqual(request_due(track, 11, None), 'state_confirmation')
        track['confirmed'] = True
        self.assertIsNone(request_due(track, 12, None))
        self.assertEqual(request_due(track, 13, None), 'stable_worn')
        track['active_violations'] = ['필수 여밈 열림']
        self.assertEqual(request_due(track, 12, None), 'unresolved_violation')


if __name__ == '__main__':
    unittest.main()
