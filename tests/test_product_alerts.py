import unittest

from chemiguard.decisions import parse_answers, questions_for
from chemiguard.product_alerts import assess_product, combine_product_check
from chemiguard.products import rank_references

SITE = [{'enabled': True, 'color': 'white', 'product_id': 'P11'},
        {'enabled': True, 'color': 'gray', 'product_id': 'P04'}]
POLICY = {'hood_required': True, 'closure_required': True, 'closure_location': 'front',
          'wearing_assessment': 'visible_regions'}


class ProductAlertTests(unittest.TestCase):
    def test_unknown_color_does_not_force_a_match(self):
        check = assess_product('yellow', {}, SITE)
        self.assertEqual(check['state'], 'MISMATCH')
        self.assertEqual(check['signals']['color']['state'], 'mismatch')
        self.assertEqual(check['suitability'], 'NOT_ASSESSED')
        for color in ('white', 'uncertain', 'no_coverall', 'not_visible'):
            self.assertNotEqual(assess_product(color, {}, SITE)['state'], 'MISMATCH')

    def test_archived_reference_is_contrast_not_an_allowed_candidate(self):
        refs = [{'id': product, 'product_id': product, 'product_name': product, 'embedding': vector,
                 'reference_kind': 'product_photo', 'region': 'torso', 'model_sha256': 'm',
                 'view': 'front', 'crop_url': '/'+product+'.jpg'}
                for product, vector in [('P11', [0.6, 0.8]), ('P04', [0, 1]), ('P12', [1, 0])]]
        matching = rank_references([1, 0], refs, 'm', SITE)
        self.assertEqual(matching['product_count'], 2)
        self.assertEqual(matching['outside_candidate']['product_id'], 'P12')
        self.assertAlmostEqual(matching['outside_gap'], .4)
        self.assertEqual(assess_product('white', matching, SITE)['signals']['product']['state'], 'mismatch')
        self.assertEqual(assess_product('uncertain', matching, SITE, 'API error')['state'], 'UNKNOWN')
        self.assertEqual(assess_product('white', matching, [])['state'], 'DISABLED')
        self.assertEqual(assess_product('white', matching, [row | {'enabled': False} for row in SITE])['state'], 'UNKNOWN')

    def test_consecutive_alarm_latches_and_clears_only_observed_dimension(self):
        track = {}
        bad = {'outside_candidate': {'product_id': 'P12', 'name': 'Tyvek'}, 'outside_gap': .1}
        good = bad | {'outside_gap': -.1}
        def apply(color, matching, at, error=None):
            return combine_product_check(track, assess_product(color, matching, SITE, error), at, f'o{at}')
        self.assertFalse(apply('yellow', bad, 1)['new_alerts'])
        alarm = apply('yellow', bad, 2)
        self.assertEqual(set(alarm['new_alerts']), {'color', 'product'})
        self.assertEqual(alarm['supporting_observation_ids'], ['o1', 'o2'])
        self.assertFalse(apply('yellow', bad, 3)['new_alerts'])
        self.assertFalse(apply('white', good, 4, 'timeout')['cleared_alerts'])
        apply('white', {}, 5)
        self.assertEqual(apply('white', {}, 6)['cleared_alerts'], ['color'])
        self.assertIn('product', track['product_alerts'])
        apply('white', good, 7)
        self.assertEqual(apply('white', good, 8)['cleared_alerts'], ['product'])
        apply('yellow', bad, 9)
        self.assertEqual(len(apply('yellow', bad, 10)['new_alerts']), 2)

    def test_gaps_unknown_and_new_track_break_confirmation(self):
        track = {}
        def apply(color, at):
            return combine_product_check(track, assess_product(color, {}, SITE), at, str(at))
        apply('yellow', 1)
        self.assertFalse(apply('yellow', 8)['new_alerts'])
        apply('uncertain', 9)
        self.assertFalse(apply('yellow', 10)['new_alerts'])
        self.assertFalse(combine_product_check({}, assess_product('yellow', {}, SITE), 11, 'new')['new_alerts'])
        self.assertEqual(apply('yellow', 11)['new_alerts'], ['color'])

    def test_color_question_opt_in_and_low_margin_fallback(self):
        self.assertNotIn('garment_color', [q['name'] for q in questions_for(POLICY)])
        question = questions_for(POLICY, True)[-1]
        choices = [c['value'] for c in question['choices']]
        probabilities = [{'value': v, 'probability': .5 if v in ('white', 'gray') else 0} for v in choices]
        parsed, scores = parse_answers({'answers': [{'name': 'garment_color', 'type': 'choice',
            'choice': 'white', 'probabilities': probabilities}]}, [question])
        self.assertEqual(parsed['garment_color'], 'uncertain')
        self.assertEqual(scores['garment_color']['choice'], 'white')


if __name__ == '__main__':
    unittest.main()
