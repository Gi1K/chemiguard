import unittest

import numpy as np

from chemiguard.observation import combine_observation, image_quality, request_due, select_candidate


class ObservationRules(unittest.TestCase):
    def test_schedule_and_error_backoff(self):
        track = {'pending': False, 'last_requested': 10, 'confirmed': True, 'result': {'wearing': 'WORN'}}
        self.assertIsNone(request_due(track, 12.9, None))
        self.assertEqual(request_due(track, 13, None), 'stable_worn')
        track['confirmed'] = False
        self.assertEqual(request_due(track, 11, None), 'state_confirmation')
        track.update(confirmed=True, result={'wearing': 'NOT_WORN'})
        self.assertEqual(request_due(track, 12, None), 'continuing_violation')
        track.update(result={'wearing': 'UNKNOWN'})
        self.assertEqual(request_due(track, 12, None), 'visibility_recheck')
        track.update(result={'error': 'timeout'}, errors=3)
        self.assertIsNone(request_due(track, 17, None))
        self.assertEqual(request_due(track, 18, None), 'error_retry')
        track.update(last_requested=0, result={})
        self.assertEqual(request_due(track, 20, None), 'new_track')
        track['pending'] = True
        self.assertIsNone(request_due(track, 20, None))

    def test_changed_image_can_request_early_but_not_bypass_backoff(self):
        track = {'pending': False, 'last_requested': 10, 'confirmed': True,
                 'result': {'wearing': 'WORN'}, 'requested_signature': np.zeros((2, 2), dtype=np.uint8)}
        image = np.full((2, 2), 255, dtype=np.uint8)
        self.assertIsNone(request_due(track, 10.9, image))
        self.assertEqual(request_due(track, 11, image), 'appearance_change')
        track.update(result={'error': 'timeout'}, errors=2)
        self.assertIsNone(request_due(track, 11, image))

    def test_evidence_is_recent_distinct_and_quality_ranked(self):
        rows = [{'captured': moment, 'quality': {'score': score}} for moment, score in
                [(8, 100), (9.3, 2), (9.8, 3), (10, 1), (11, 100)]]
        self.assertEqual(select_candidate(rows, 10, 9.3)['captured'], 9.8)
        self.assertIsNone(select_candidate(rows, 10, 10))
        self.assertIsNone(image_quality(np.zeros((99, 50, 3), dtype=np.uint8), [0, 0, 50, 99], (500, 500), .9))

    def test_alarm_needs_two_observations_and_two_for_recovery(self):
        track = {'history': [], 'active_violations': []}
        def observe(wearing, moment, violations=()):
            return combine_observation(track, {'wearing': wearing, 'violations': list(violations)},
                                       moment, str(moment), 5, 10)
        self.assertFalse(observe('NOT_WORN', 1, ['hood'])['new_violations'])
        self.assertEqual(observe('NOT_WORN', 2, ['hood', 'closure'])['new_violations'], ['hood'])
        self.assertFalse(observe('NOT_WORN', 3, ['hood'])['new_violations'])
        observe('UNKNOWN', 4)
        self.assertEqual(track['active_violations'], ['hood'])
        self.assertFalse(observe('WORN', 5)['cleared'])
        self.assertTrue(observe('WORN', 6)['cleared'])
        self.assertEqual(track['active_violations'], [])
        observe('NOT_WORN', 7, ['hood'])
        self.assertEqual(observe('NOT_WORN', 8, ['hood'])['new_violations'], ['hood'])

    def test_expiry_breaks_consensus(self):
        track = {'history': [], 'active_violations': ['hood']}
        for moment in (1, 7):
            combine_observation(track, {'wearing': 'WORN'}, moment, str(moment), 5, 10)
        self.assertFalse(track['confirmed'])
        self.assertEqual(track['active_violations'], ['hood'])


if __name__ == '__main__':
    unittest.main()
