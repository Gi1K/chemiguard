import unittest

from chemiguard.products import current_site_products, product_profile, rank_references


class ProductComparisonTests(unittest.TestCase):
    def test_ranking_excludes_demo_and_uses_best_matching_photo(self):
        def ref(key, product, vector, kind='product_photo', model='model'):
            return {'id': key, 'product_id': product, 'product_name': product, 'embedding': vector,
                    'reference_kind': kind, 'model_sha256': model, 'region': 'torso',
                    'crop_url': key+'.jpg', 'view': 'front'}
        result = rank_references([1, 0], [ref('demo', 'DEMO', [1, 0], 'scene_demo'),
            ref('first', 'P11', [0.6, 0.8]), ref('best', 'P11', [0.8, 0.6]),
            ref('second', 'P12', [0.65, 0.759934]), ref('wrong', 'P04', [1, 0], model='other')], 'model')
        self.assertEqual([row['product_id'] for row in result['candidates']], ['P11', 'P12'])
        self.assertEqual(result['candidates'][0]['reference_url'], 'best.jpg')
        self.assertAlmostEqual(result['candidates'][0]['score'], 0.7)
        self.assertAlmostEqual(result['gap'], 0.05)
        self.assertEqual(result['state'], 'CANDIDATE')
        self.assertEqual(result['suitability'], 'NOT_ASSESSED')

    def test_unknown_product_and_no_eligible_reference(self):
        self.assertIsNone(product_profile('UNKNOWN'))
        self.assertEqual(rank_references([1, 0], [], 'model')['state'], 'UNAVAILABLE')

    def test_facts_do_not_assert_chemical_suitability(self):
        profile = product_profile('P11')
        self.assertEqual(profile['suitability'], 'NOT_ASSESSED')
        self.assertEqual(profile['chemical_tests'][0]['concentration'], '30%')
        self.assertEqual(profile['chemical_tests'][0]['method'], 'EN ISO 6530')
        profile['chemical_tests'].clear()
        self.assertEqual(len(product_profile('P11')['chemical_tests']), 2)

    def test_site_slots_keep_latest_revision_without_deleting_history(self):
        rows = [{'purpose': 'acid', 'protection_type': 'Type 3', 'revision': 2, 'product_id': 'P04'},
                {'purpose': 'acid', 'protection_type': 'Type 3', 'revision': 1, 'product_id': 'P11'},
                {'purpose': 'alkali', 'protection_type': 'Type 3', 'revision': 1, 'product_id': 'P11'}]
        current = current_site_products(rows)
        self.assertEqual(len(current), 2)
        self.assertEqual(next(row for row in current if row['purpose'] == 'acid')['product_id'], 'P04')
        self.assertEqual(len(rows), 3)

    def test_site_scope_filters_candidates_without_forcing_a_match(self):
        references = [{'id': 'ref', 'product_id': 'P11', 'product_name': 'test', 'embedding': [0, 1],
                       'reference_kind': 'product_photo', 'model_sha256': 'model', 'region': 'torso',
                       'crop_url': '/photo.jpg', 'view': 'front'}]
        assigned = [{'enabled': True, 'product_id': 'P11', 'purpose': 'acid'}]
        result = rank_references([1, 0], references, 'model', assigned)
        self.assertEqual(result['candidates'][0]['score'], 0)
        self.assertTrue(result['ambiguous'])
        self.assertEqual(result['comparison_scope'], 'site_registered')
        self.assertEqual(result['suitability'], 'NOT_ASSESSED')
        assigned[0]['enabled'] = False
        self.assertFalse(rank_references([1, 0], references, 'model', assigned)['candidates'])

    def test_color_scope_keeps_two_families_and_excludes_unselected_white(self):
        refs = [{'id': product, 'product_id': product, 'product_name': product, 'embedding': [1, 0],
                 'reference_kind': 'product_photo', 'model_sha256': 'model', 'region': 'torso',
                 'crop_url': '/photo.jpg', 'view': 'front'} for product in ('P11', 'P04', 'P12')]
        selected = [{'registration_mode': 'color', 'color': color, 'product_id': product, 'enabled': True,
                     'purpose': None, 'protection_type': None, 'revision': 1}
                    for color, product in (('white', 'P11'), ('gray', 'P04'))]
        result = rank_references([1, 0], refs, 'model', current_site_products(selected))
        self.assertEqual({row['product_id'] for row in result['candidates']}, {'P11', 'P04'})
        self.assertEqual(result['product_count'], 2)
        self.assertEqual(result['candidates'][0]['site_assignments'][0]['purpose_label'], '용도 미지정')
        self.assertTrue(result['ambiguous'])


if __name__ == '__main__':
    unittest.main()
