import tempfile
import threading
import time
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import Mock, patch

from chemiguard.monitor import Run


class DecisionRoutingTests(unittest.TestCase):
    def bare_run(self):
        run = Run.__new__(Run)
        run.lock = threading.RLock()
        run.site_products = [{'enabled': True, 'product_id': 'P11', 'color': 'white'}]
        run.policy = {}
        run.product_catalog = {}
        run.metrics = {'product_busy_skipped': 0}
        run.product_future = None
        run.pool, run.product_pool = Mock(), Mock()
        return run

    def test_both_requests_start_without_waiting_for_ppe(self):
        run = self.bare_run()
        ppe, product = Future(), Future()
        run.pool.submit.return_value = ppe
        run.product_pool.submit.return_value = product
        run._answer = Mock()
        envelope, images = {'id': 'same-frame'}, {'person': object()}
        run._dispatch_decisions(envelope, images)
        self.assertEqual(run.pool.submit.call_count, 1)
        self.assertEqual(run.product_pool.submit.call_count, 1)
        run._answer.assert_not_called()
        ppe.set_result({'parts': {'torso': 'covered'}})
        run._answer.assert_called_once_with(ppe, envelope, product)
        self.assertFalse(product.done())

    def test_busy_product_does_not_queue_or_block_ppe(self):
        run = self.bare_run()
        run.product_future = Future()
        run.pool.submit.return_value = Future()
        run._answer = Mock()
        run._dispatch_decisions({}, {})
        run.product_pool.submit.assert_not_called()
        self.assertEqual(run.metrics['product_busy_skipped'], 1)
        run.pool.submit.assert_called_once()

    def test_join_keeps_same_parent_and_handles_either_completion_order(self):
        for product_first in (True, False):
            run = self.bare_run()
            run._product_answer = Mock()
            product, envelope, ppe = Future(), {'id': 'ppe-1'}, {'parts': {'torso': 'covered'}}
            if product_first:
                product.set_result({'membership': 'candidate'})
            run._join_product(product, envelope, ppe, 'scene_changed')
            if not product_first:
                run._product_answer.assert_not_called()
                product.set_result({'membership': 'candidate'})
            run._product_answer.assert_called_once_with(product, envelope, ppe, ppe_discard_reason='scene_changed')

    def test_discarded_parent_product_is_saved_but_cannot_apply_or_alarm(self):
        run = self.bare_run()
        moment = time.monotonic()
        run.state, run.generation, run.scene_epoch = 'RUNNING', 1, 0
        run.tracks = {1: {'token': 'same', 'last_seen': moment}}
        run._event = Mock()
        run.metrics.update(api_calls=0, product_api_calls=0, product_api_latency_ms=[],
                           paired_ready_ms=[], api_latency_ms=[], input_tokens=0, output_tokens=0,
                           product_api_errors=0, api_errors=0, product_api_discarded=0, api_discarded=0)
        envelope = {'id': 'ppe-parent', 'track_id': 1, 'track_token': 'same', 'generation': 1,
                    'scene_epoch': 0, 'requested_monotonic': moment, 'observed_monotonic': moment,
                    'source_time_s': 1, 'images': {}}
        ppe = {'parts': {'torso': 'covered'}, 'garment_color': 'white'}
        decision = {'membership': 'none', 'api_called': True, 'latency_ms': 100}
        with tempfile.TemporaryDirectory() as path, patch('chemiguard.monitor.store.put') as put:
            run.path = Path(path)
            run._product_answer(None, envelope, ppe, decision, 'scene_changed')
            observation = put.call_args.args[1]
        self.assertFalse(observation['applied'])
        self.assertEqual(observation['ppe_observation_id'], 'ppe-parent')
        self.assertEqual(observation['discard_reason'], 'ppe_scene_changed')
        self.assertNotIn('product_result', run.tracks[1])
        self.assertEqual(run.metrics['product_api_calls'], 1)
        self.assertEqual(run.metrics['product_api_discarded'], 1)
        run._event.assert_not_called()


if __name__ == '__main__':
    unittest.main()
