import unittest

from chemiguard.decisions import parse_answers
from chemiguard.observation import combine_observation
from chemiguard.wearing import PARTS, summarize_parts


def parse(distribution, name='respirator', choice=None):
    question = {'name': name, 'choices': [{'value': value} for value in distribution]}
    answer = {'type': 'choice', 'name': name,
              'choice': choice if choice is not None else max(distribution, key=distribution.get),
              'probabilities': [{'value': value, 'probability': probability}
                                for value, probability in distribution.items()]}
    return parse_answers({'answers': [answer]}, [question])


class DecisionSelection(unittest.TestCase):
    def test_small_margin_is_not_a_veto_for_any_ppe_choice(self):
        states = ('covered', 'uncovered', 'not_visible', 'uncertain')
        for winner in states:
            distribution = {state: .25 if state != winner else .26 for state in states}
            distribution[next(state for state in states if state != winner)] = .24
            parts, scores = parse(distribution)
            self.assertEqual(parts['respirator'], winner)
            self.assertEqual(scores['respirator']['selected'], winner)
            self.assertFalse(scores['respirator']['top_tied'])
        parts, _ = parse({'closed': .44, 'open': .19, 'not_visible': .08, 'uncertain': .29}, 'closure')
        self.assertEqual(parts['closure'], 'closed')

    def test_uses_actual_top_probability_and_preserves_api_choice(self):
        parts, scores = parse({'covered': .44, 'uncovered': .19, 'not_visible': .08, 'uncertain': .29},
                              choice='uncertain')
        self.assertEqual(parts['respirator'], 'covered')
        self.assertEqual(scores['respirator']['choice'], 'uncertain')
        self.assertEqual(scores['respirator']['selected'], 'covered')

    def test_ties_stay_unknown_in_visible_and_legacy_policies(self):
        for distribution, fallback in [
            ({'covered': .4, 'uncovered': .4, 'not_visible': .1, 'uncertain': .1}, 'uncertain'),
            ({'covered': .5, 'uncovered': .5, 'unobservable': 0}, 'unobservable')]:
            parts, scores = parse(distribution)
            self.assertEqual(parts['respirator'], fallback)
            self.assertTrue(scores['respirator']['top_tied'])

    def test_invalid_probabilities_and_refusals_are_not_top_choices(self):
        for distribution in ({'covered': float('nan'), 'uncertain': .2},
                             {'covered': 1.1, 'uncertain': -.1},
                             {'covered': .4, 'uncertain': .1}):
            with self.assertRaises(ValueError):
                parse(distribution, choice='covered')
        with self.assertRaises(ValueError):
            parse_answers({'answers': [{'type': 'refusal', 'name': 'respirator'}]},
                          [{'name': 'respirator', 'choices': [{'value': 'covered'}, {'value': 'uncertain'}]}])

    def test_unrelated_color_rule_is_unchanged(self):
        parts, scores = parse({'white': .44, 'gray': .4, 'uncertain': .16}, 'garment_color')
        self.assertEqual(parts['garment_color'], 'uncertain')
        self.assertEqual(scores['garment_color']['selection_method'], 'choice-margin-0.2')

    def test_low_margin_still_needs_two_observations_and_direct_recovery(self):
        policy = {'hood_required': True, 'closure_required': True, 'respirator_required': True,
                  'wearing_assessment': 'visible_regions'}
        track = {'history': [], 'active_violations': []}
        def see(winner, moment):
            distribution = {state: probability for state, probability in
                            zip([winner] + [state for state in ('covered', 'uncovered', 'not_visible', 'uncertain')
                                            if state != winner], (.44, .29, .19, .08))}
            face, _ = parse(distribution)
            parts = {name: 'covered' for name in (*PARTS, 'hood')} | {'closure': 'not_visible'} | face
            result = summarize_parts(parts, policy) | {'parts': parts, 'wearing_assessment': 'visible_regions'}
            return combine_observation(track, result, moment, str(moment), 5, 10)
        see('covered', 1)
        self.assertFalse(track['confirmed'])
        see('covered', 2)
        self.assertTrue(track['confirmed'])
        self.assertFalse(see('uncovered', 3)['new_violations'])
        self.assertEqual(see('uncovered', 4)['new_violations'], ['필수 전면형 방독면 미착용'])
        for moment in (5, 6):
            self.assertFalse(see('not_visible', moment)['cleared'])
        self.assertFalse(see('covered', 7)['cleared'])
        self.assertEqual(see('covered', 8)['cleared_violations'], ['필수 전면형 방독면 미착용'])


if __name__ == '__main__':
    unittest.main()
