import copy
import json
import unittest
from unittest.mock import patch

import numpy as np

from chemiguard.product_decisions import apply_ppe_gate, gate, observe_product, product_question, RULES
from chemiguard.product_alerts import assess_decisions_product, combine_product_check

SITE = [{'enabled': True, 'product_id': 'P11', 'color': 'white'},
        {'enabled': True, 'product_id': 'P04', 'color': 'gray'}]
PPE = {'parts': {'torso': 'covered', 'hood': 'uncovered'}, 'garment_color': 'white', 'error': None}


class ProductDecisionsTests(unittest.TestCase):
    def test_standardization_does_not_require_exact_white_model(self):
        self.assertIn('Similar white coveralls', RULES)
        question = product_question({'aliases': {'R1': {}}})
        self.assertIn('do not require exact product identity', question['instructions'])
        self.assertEqual([choice['value'] for choice in question['choices']], ['R1', 'none', 'uncertain', 'no_coverall'])

    def test_parallel_candidate_is_suppressed_but_raw_answer_and_usage_survive(self):
        decision = {'membership': 'candidate', 'candidate': {'product_id': 'P04'},
                    'api_called': True, 'usage': {'input_tokens': 123}, 'raw_result': {'id': 'original'}}
        before = copy.deepcopy(decision)
        result = apply_ppe_gate(PPE | {'parts': {'torso': 'uncovered'}}, decision)
        self.assertEqual(result['membership'], 'no_coverall')
        self.assertIsNone(result['candidate'])
        self.assertEqual(result['raw_candidate'], decision['candidate'])
        self.assertEqual(result['raw_result'], decision['raw_result'])
        self.assertTrue(result['api_called'])
        self.assertEqual(result['usage'], decision['usage'])
        self.assertEqual(decision, before)
        self.assertEqual(apply_ppe_gate(PPE | {'error': 'timeout'}, decision)['membership'], 'uncertain')

    def test_ppe_gate_blocks_absent_hidden_and_failed_torso(self):
        self.assertIsNone(gate(PPE))
        self.assertEqual(gate(PPE | {'parts': {'torso': 'uncovered'}})[0], 'no_coverall')
        for parts in ({}, {'torso': 'not_visible'}, {'torso': 'uncertain'}):
            self.assertEqual(gate(PPE | {'parts': parts})[0], 'uncertain')
        self.assertEqual(gate(PPE | {'error': 'timeout'})[0], 'uncertain')

    def test_siglip_cannot_decide_or_clear_product(self):
        matching = {'outside_candidate': {'name': 'P12', 'product_id': 'P12'}, 'outside_gap': .8}
        decision = {'membership': 'candidate', 'candidate': {'product_id': 'P11'}}
        self.assertEqual(assess_decisions_product(PPE, decision, matching, SITE)['signals']['product']['state'], 'clear')
        self.assertEqual(assess_decisions_product(PPE, {'membership': 'uncertain'}, matching, SITE)['signals']['product']['state'], 'unknown')
        self.assertEqual(assess_decisions_product(PPE, {'membership': 'none'}, {}, SITE)['signals']['product']['state'], 'mismatch')

    def test_ppe_and_color_have_precedence_without_mutating_observation(self):
        decision = {'membership': 'candidate', 'candidate': {'product_id': 'P04'}}
        before = copy.deepcopy(PPE)
        check = assess_decisions_product(PPE, decision, {}, SITE)
        self.assertIsNone(check['candidate'])
        self.assertEqual(check['membership'], 'uncertain')
        self.assertEqual(PPE, before)
        unworn = PPE | {'parts': {'torso': 'uncovered'}}
        check = assess_decisions_product(unworn, {'membership': 'no_coverall'}, {}, SITE)
        self.assertEqual(check['state'], 'NOT_WORN')
        self.assertTrue(all(s['state'] == 'unknown' for s in check['signals'].values()))

    def test_none_latches_unknown_and_errors_cannot_clear(self):
        track = {}
        def apply(decision, moment):
            return combine_product_check(track, assess_decisions_product(PPE, decision, {}, SITE), moment, str(moment))
        self.assertFalse(apply({'membership': 'none'}, 1)['new_alerts'])
        self.assertEqual(apply({'membership': 'none'}, 2)['new_alerts'], ['product'])
        for moment, decision in [(3, {'membership': 'uncertain'}), (4, {'error': 'timeout'})]:
            self.assertFalse(apply(decision, moment)['cleared_alerts'])
            self.assertIn('product', track['product_alerts'])
        candidate = {'membership': 'candidate', 'candidate': {'product_id': 'P11'}}
        apply(candidate, 5)
        self.assertEqual(apply(candidate, 6)['cleared_alerts'], ['product'])

    def test_product_request_never_asks_ppe_questions(self):
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        catalog = {'aliases': {'R1': {'product_id': 'P11'}}, 'content': [], 'image_inputs': [], 'error': None}
        values = ('R1', 'none', 'uncertain', 'no_coverall')
        raw = {'answers': [{'name': 'product_membership', 'type': 'choice', 'choice': 'none',
                           'probabilities': [{'value': v, 'probability': int(v == 'none')} for v in values]}]}
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'offline-test'}), patch('chemiguard.product_decisions.httpx.post') as post:
            post.return_value.status_code = 200
            post.return_value.headers = {}
            post.return_value.json.return_value = raw
            result = observe_product({'person': image, 'identity_torso': image}, catalog)
            body = json.loads(post.call_args.kwargs['content'])
        self.assertEqual([q['name'] for q in body['questions']], ['product_membership'])
        self.assertEqual(result['membership'], 'none')
        self.assertNotIn('parts', result)
        self.assertTrue(result['api_called'])
        self.assertEqual(result['raw_result'], raw)

    def test_missing_reference_or_crop_does_not_call_api(self):
        catalog = {'aliases': {'R1': {'product_id': 'P11'}}, 'content': [], 'image_inputs': [], 'error': 'missing reference'}
        with patch('chemiguard.product_decisions.httpx.post') as post:
            self.assertFalse(observe_product({}, catalog)['api_called'])
            self.assertFalse(observe_product({}, catalog | {'error': None})['api_called'])
            post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
