import threading
import time
import unittest
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

from chemiguard.monitor import Run


class TrackingPreparationTests(unittest.TestCase):
    def bare_run(self):
        run = Run.__new__(Run)
        run.lock = threading.RLock()
        run.state, run.generation, run.scene_epoch = 'RUNNING', 1, 0
        run.metrics = dict(preparation_jobs=0, preparation_busy_skipped=0,
                           preparation_errors=0, api_calls=0)
        run.preparation_future = None
        run.tracks = {}
        return run

    def test_busy_preparation_does_not_block_or_queue_tracking_ticks(self):
        run = self.bare_run()
        entered, release = threading.Event(), threading.Event()

        def prepare(*args):
            entered.set()
            self.assertTrue(release.wait(3))

        run._observe_people = Mock(side_effect=prepare)
        with ThreadPoolExecutor(max_workers=1) as run.preparation_pool:
            try:
                run._schedule_observations(None, [object()], 1, 0)
                self.assertTrue(entered.wait(2))
                first = run.preparation_future
                for _ in range(5):
                    run._schedule_observations(None, [object()], 1, 0)
                self.assertIs(run.preparation_future, first)
                self.assertFalse(first.done())
                self.assertEqual(run.metrics['preparation_busy_skipped'], 5)
            finally:
                release.set()
            first.result(timeout=2)
        run._observe_people.assert_called_once()
        self.assertEqual(run.metrics['preparation_jobs'], 1)

    def test_invalid_generation_scene_and_halted_run_never_schedule(self):
        run = self.bare_run()
        run.preparation_pool = Mock()
        run._schedule_observations(None, [object()], 2, 0)
        run._schedule_observations(None, [object()], 1, 1)
        run.state = 'STOPPED'
        run._schedule_observations(None, [object()], 1, 0)
        run.preparation_pool.submit.assert_not_called()

    def test_preparation_failures_are_recorded(self):
        run = self.bare_run()
        run._observe_people = Mock(side_effect=ValueError('private detail'))
        run._prepare_observations(None, [], 1, 0)
        self.assertEqual(run.metrics['preparation_errors'], 1)
        self.assertEqual(run.metrics['preparation_last_error'], 'ValueError')
        self.assertEqual(run.metrics['preparation_jobs'], 1)

    def test_invalidation_during_evidence_save_cannot_dispatch_to_old_target(self):
        for invalidation in ('generation', 'scene', 'token', 'expired', 'stopped'):
            with self.subTest(invalidation=invalidation):
                run = self.bare_run()
                run.policy = dict(coverall_required=True, hood_required=False, revision=1, reference_revision=1)
                run.references, run.future = [], None
                moment = time.monotonic()
                candidate = dict(captured=moment, seq=1, timestamp=1, bbox=[0, 0, 100, 200],
                                 confidence=1, frame=None, image=None, quality={'signature': [1], 'score': 1})
                person = dict(track_id=1, token='original', last_seen=moment, confidence=1, signature=[1],
                              last_identity=0, last_observed=0, candidates=deque([candidate]))
                run.tracks[1] = person
                body = dict(images={}, boxes={}, route='test', reason='', keypoints=[], keypoint_confidence=[])
                vision = Mock()
                vision.body.return_value = body
                run._dispatch_decisions = Mock()

                def evidence(*args):
                    if invalidation == 'generation':
                        run.generation += 1
                    elif invalidation == 'scene':
                        run.scene_epoch += 1
                    elif invalidation == 'token':
                        run.tracks[1] = person | {'token': 'replacement'}
                    elif invalidation == 'expired':
                        person['last_seen'] -= 10
                    else:
                        run.state = 'STOPPED'
                    return {}

                run._evidence = Mock(side_effect=evidence)
                with patch('chemiguard.monitor.request_due', return_value='new_target'), \
                     patch('chemiguard.monitor.select_candidate', return_value=candidate), \
                     patch('chemiguard.monitor.eligible_candidates', return_value=[candidate]), \
                     patch('chemiguard.monitor.face_quality', return_value={}):
                    run._observe_people(vision, [person], 1, 0)
                run._evidence.assert_called_once()
                run._dispatch_decisions.assert_not_called()
                self.assertEqual(run.metrics['api_calls'], 0)


if __name__ == '__main__':
    unittest.main()
