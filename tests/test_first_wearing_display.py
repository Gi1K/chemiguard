import unittest

from chemiguard.monitor import Run
from chemiguard.observation import combine_observation
from chemiguard.wearing import PARTS, summarize_parts


POLICY = dict(coverall_required=True, hood_required=True, closure_required=True,
              respirator_required=True, wearing_assessment='visible_regions')
PART_STATES = dict.fromkeys((*PARTS, 'hood', 'respirator'), 'covered') | {'closure': 'closed'}


class FirstWearingDisplayTests(unittest.TestCase):
    def setUp(self):
        self.run = Run.__new__(Run)
        self.run.state, self.run.policy = 'RUNNING', POLICY
        self.track = dict(track_id=1, token='person', bbox=[0, 0, 100, 200], confidence=.9,
                          pending=False, last_seen=10, processing_state='RUNNING', identity={},
                          history=[], active_violations=[], reason='')
        self.run.tracks = {1: self.track}

    def observe(self, parts=PART_STATES, at=10):
        result = summarize_parts(parts, POLICY) | dict(parts=parts, wearing_assessment='visible_regions',
                                                     observed_monotonic=at, source_time_s=at)
        transition = combine_observation(self.track, result, at, str(at), 5, 10)
        self.track.update(result=result, last_seen=at, reason=result['reason'])
        return self.run._public_tracks(at, at)[0], transition

    def test_first_full_and_visible_observations_are_not_hidden_until_consensus(self):
        first, _ = self.observe()
        self.assertEqual(first['wearing'], 'WORN')
        self.assertTrue(first['all_required_observed'])
        self.assertFalse(first['confirmed'])
        self.assertFalse(first['complete_confirmed'])
        self.track['history'].clear()
        side, _ = self.observe(PART_STATES | {'closure': 'not_visible'}, 11)
        self.assertEqual(side['wearing'], 'VISIBLE_WORN')
        self.assertFalse(side['all_required_observed'])
        self.assertFalse(side['confirmed'])

    def test_alarm_still_needs_two_missing_observations_and_two_direct_recoveries(self):
        missing = PART_STATES | {'hood': 'uncovered'}
        first, transition = self.observe(missing)
        self.assertEqual(first['wearing'], 'NOT_WORN')
        self.assertEqual(transition['new_violations'], [])
        second, transition = self.observe(missing, 11)
        self.assertEqual(transition['new_violations'], ['필수 후드 미착용'])
        recovery, transition = self.observe(at=12)
        self.assertEqual(recovery['wearing'], 'WORN')
        self.assertEqual(recovery['active_violations'], ['필수 후드 미착용'])
        self.assertFalse(transition['cleared'])
        recovery, transition = self.observe(at=13)
        self.assertTrue(transition['cleared'])
        self.assertEqual(recovery['active_violations'], [])

    def test_hidden_part_cannot_clear_old_alarm_even_with_immediate_visible_wearing(self):
        self.track['active_violations'] = ['필수 여밈 열림']
        for at in (10, 11):
            side, transition = self.observe(PART_STATES | {'closure': 'not_visible'}, at)
            self.assertEqual(side['wearing'], 'VISIBLE_WORN')
            self.assertEqual(side['active_violations'], ['필수 여밈 열림'])
            self.assertFalse(transition['cleared'])

    def test_invalid_evidence_never_becomes_wearing(self):
        self.observe()
        for reason in ('expired', 'future', 'error', 'processing_error', 'paused', 'disabled'):
            with self.subTest(reason=reason):
                self.run.state, self.run.policy = 'RUNNING', POLICY
                self.observe()
                current, source_time = 10, 10
                if reason == 'expired':
                    current = self.track['last_seen'] = 16
                elif reason == 'future':
                    source_time = 9
                elif reason == 'error':
                    self.track['result']['error'] = 'timeout'
                elif reason == 'processing_error':
                    self.track['processing_state'] = 'ERROR'
                elif reason == 'paused':
                    self.run.state = 'PAUSED'
                else:
                    self.run.policy = POLICY | {'coverall_required': False}
                self.assertEqual(self.run._public_tracks(current, source_time)[0]['wearing'], 'UNKNOWN')
                self.track['processing_state'] = 'RUNNING'


if __name__ == '__main__':
    unittest.main()
