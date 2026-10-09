import asyncio
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock

from chemiguard.phone_alerts import PhoneAlerts
from chemiguard.phone_demo import SOURCE_ID
from chemiguard.phone_transport import instructions
from test_phone_alerts import MemoryStore, SETTINGS, add_event, fake_decider, routing_response


class DemoPhoneTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = MemoryStore()
        self.transport = AsyncMock()
        self.service = PhoneAlerts(self.store, replace(SETTINGS, automatic=False),
                                   self.transport, decider=fake_decider)
        self.service.demo.arm('request1')

    async def asyncTearDown(self):
        await self.service.stop()
        self.store.db.close()

    def run_record(self, source=SOURCE_ID, **values):
        return self.store.put('run', {'id': 'r1', 'source_id': source,
                                     'status': 'RUNNING', 'generation': 1, **values})

    def events(self):
        ppe = add_event(self.store)
        leak = add_event(self.store, 'leak', kind='RELEASE_SUSPECTED', severity='REVIEW', reason='누출 징후')
        observation = self.store.get('observation', 'o_leak')
        observation['result'] = {'processing_state': 'RUNNING', 'native_class': 'smoke',
                                 'scene_detections': [{'native_class': 'smoke', 'confidence': .8}]}
        self.store.put('observation', observation, replace=True)
        return ppe, leak

    async def test_both_real_decisions_one_call_with_both_details(self):
        self.run_record()
        ppe, leak = self.events()
        await self.service.demo.tick()
        await self.service.demo.tick()
        calls = self.store.list('phone_call')
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(set(call['event_ids']), {ppe['id'], leak['id']})
        self.assertEqual(len(call['decision_ids']), 2)
        self.assertEqual(call['role'], 'safety_control_room')
        self.assertEqual(call['status'], 'queued')
        self.assertIn('필수 후드 미착용 의심', instructions(call))
        self.assertIn('누출 징후', instructions(call))
        self.assertEqual(self.service.calls_for_event(ppe['id'])[0]['id'], call['id'])
        self.assertFalse(self.service.settings.automatic)

    async def test_per_run_setting_arms_each_new_receiver_once(self):
        self.service.demo.configure(True)
        self.run_record()
        self.service.demo.on_run('r1')
        self.events()
        await self.service.demo.tick()
        self.assertEqual(len(self.store.list('phone_call')), 1)
        self.service.demo.on_run('r1')
        await self.service.demo.tick()
        self.assertEqual(len(self.store.list('phone_call')), 1)
        run = self.store.get('run', 'r1')
        self.store.put('run', {**run, 'id': 'r2'})
        self.service.demo.on_run('r2')
        for event in self.store.related('event', 'run_id', 'r1'):
            observation = self.store.get('observation', event['observation_id'])
            self.store.put('observation', {**observation, 'id': observation['id']+'2', 'run_id': 'r2'})
            self.store.put('event', {**event, 'id': event['id']+'2', 'run_id': 'r2',
                                     'observation_id': observation['id']+'2'})
        await self.service.demo.tick()
        self.assertEqual(len(self.store.list('phone_call')), 2)

    async def test_disabled_or_other_source_does_not_auto_arm(self):
        self.service.demo.cancel()
        self.run_record(source='two_people')
        self.service.demo.configure(True)
        self.service.demo.on_run('r1')
        self.assertEqual(len(self.store.list('phone_demo')), 1)
        self.service.demo.configure(False)
        self.run_record(source=SOURCE_ID, id='r2')
        self.service.demo.on_run('r2')
        self.assertEqual(len(self.store.list('phone_demo')), 1)

    async def test_other_videos_and_past_runs_do_not_claim(self):
        self.run_record(source='two_people')
        self.events()
        await self.service.demo.tick()
        self.assertEqual(self.service.demo.status()['status'], 'armed')
        self.assertFalse(self.store.list('phone_call'))
        run = self.store.get('run', 'r1')
        self.store.put('run', {**run, 'source_id': SOURCE_ID, 'created_at': '2020-01-01T00:00:00+00:00'}, replace=True)
        await self.service.demo.tick()
        self.assertEqual(self.service.demo.status()['status'], 'armed')

    async def test_one_event_waits_and_finish_does_not_invent_second(self):
        run = self.run_record()
        add_event(self.store)
        await self.service.demo.tick()
        self.assertEqual(self.service.demo.status()['status'], 'collecting')
        self.store.put('run', {**run, 'status': 'FINISHED'}, replace=True)
        await self.service.demo.tick()
        self.assertEqual(self.service.demo.status()['status'], 'incomplete')
        self.assertFalse(self.store.list('phone_call'))

    async def test_fallback_never_calls_or_retries(self):
        self.run_record()
        self.events()
        self.service.router.request = AsyncMock(side_effect=TimeoutError)
        await self.service.demo.tick()
        await self.service.demo.tick()
        self.assertEqual(self.service.router.request.await_count, 1)
        self.assertEqual(self.service.demo.status()['status'], 'failed')
        self.assertFalse(self.store.list('phone_call'))

    async def test_reviewed_ppe_cancels_even_when_primary_leak_valid(self):
        self.run_record()
        ppe, _ = self.events()
        await self.service.demo.tick()
        self.store.put('review', {'event_id': ppe['id']})
        task = asyncio.create_task(self.service._dispatch())
        await asyncio.wait_for(self.service.queue.join(), 1)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.transport.assert_not_awaited()
        self.assertEqual(self.store.list('phone_call')[0]['status'], 'canceled')

    async def test_generation_change_cancels_dispatch(self):
        run = self.run_record()
        self.events()
        await self.service.demo.tick()
        self.store.put('run', {**run, 'generation': 2}, replace=True)
        task = asyncio.create_task(self.service._dispatch())
        await asyncio.wait_for(self.service.queue.join(), 1)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.transport.assert_not_awaited()

    async def test_restart_cancels_reservation_and_never_rearms_same_request(self):
        self.service.demo.reset_after_restart()
        self.run_record()
        self.events()
        self.service.demo.arm('request1')
        await self.service.demo.tick()
        self.assertEqual(self.service.demo.status()['status'], 'canceled')
        self.assertFalse(self.store.list('phone_call'))

    async def test_cancel_while_decisions_in_flight(self):
        self.run_record()
        self.events()
        async def cancel(context, key):
            self.service.demo.cancel()
            return routing_response(context)
        self.service.router.request = cancel
        await self.service.demo.tick()
        self.assertFalse(self.store.list('phone_call'))
        self.assertEqual(self.service.demo.status()['status'], 'canceled')

    async def test_combined_dispatch_uses_existing_real_transport_boundary_once(self):
        self.run_record()
        self.events()
        await self.service.demo.tick()
        task = asyncio.create_task(self.service._dispatch())
        await asyncio.wait_for(self.service.queue.join(), 1)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.transport.assert_awaited_once()
        self.assertEqual(self.transport.call_args.args[1]['kind'], 'PPE_AND_RELEASE')
