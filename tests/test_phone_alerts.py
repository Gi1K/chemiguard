import asyncio
import base64
import json
import sqlite3
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from chemiguard.phone_alerts import PhoneAlerts, PhoneSettings, PHONE_MODEL, normalize_number
from chemiguard.store import Store, now
from chemiguard.contact_routing import POLICY, QUESTIONS


class MemoryStore(Store):
    def __init__(self, path=':memory:'):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE IF NOT EXISTS records(kind TEXT,id TEXT,created_at TEXT,payload TEXT,PRIMARY KEY(kind,id))')


SETTINGS = PhoneSettings(enabled=True, automatic=True, api_key='private-claw-key', openai_key='private-openai-key',
                         account_id='ACtest', from_number='07000000000', to_number='01000000000', zone_id='테스트 개소')


def add_event(store, event_id='e1', **extra):
    if not store.get('policy', 'p1'):
        store.put('policy', {'id': 'p1', 'zone_id': SETTINGS.zone_id, 'name': '시험 기준', 'revision': 1})
    observation_id = extra.get('observation_id', 'o_' + event_id)
    if not store.get('observation', observation_id):
        store.put('observation', {'id': observation_id, 'run_id': 'r1', 'applied': True,
                                 'result': {'processing_state': 'RUNNING', 'parts': {'hood': 'uncovered'}}})
    return store.put('event', {'id': event_id, 'run_id': 'r1', 'policy_id': 'p1', 'severity': 'HIGH',
                              'observation_id': observation_id,
                              'kind': 'VIOLATION_SUSPECTED', 'reason': '필수 후드 미착용 의심', **extra})


def routing_response(context, **overrides):
    rule = POLICY[context['event']['kind']]
    values = {'contact_role': rule[0], 'evidence_state': 'sufficient', 'reason_code': rule[1], **overrides}
    return {'raw_result': {'answers': [
        {'type': 'choice', 'name': q['name'], 'choice': values[q['name']], 'confidence': .99,
         'probabilities': [{'value': c['value'], 'probability': 1 if c['value'] == values[q['name']] else 0}
                           for c in q['choices']]} for q in QUESTIONS]}, 'http_status': 200}


async def fake_decider(context, key):
    return routing_response(context)


def queue_event(service, event):
    """Outbox unit fixture; real requests prepare plans through the async router."""
    plan = service.store.get('notification_plan', 'p_' + event['id'])
    if not plan:
        plan = service.store.put('notification_plan', {'id': 'p_' + event['id'], 'event_id': event['id'],
            'role': POLICY.get(event['kind'], ('site_safety_manager',))[0], 'revision': 1,
            'decision_id': 'fixture', 'selected_by': 'decisions'})
    return service.enqueue(event, plan=plan)


class PhoneOutboxTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = MemoryStore()
        self.transport = AsyncMock()
        self.service = PhoneAlerts(self.store, SETTINGS, self.transport, decider=fake_decider)

    async def asyncTearDown(self):
        await self.service.stop()
        self.store.db.close()

    async def test_disabled_and_missing_keys_never_queue(self):
        for config in (replace(SETTINGS, enabled=False), replace(SETTINGS, api_key='')):
            service = PhoneAlerts(self.store, config, self.transport)
            with self.assertRaises(ValueError):
                service.enqueue(request_id='test')
        self.transport.assert_not_called()
        self.assertEqual(self.store.list('phone_call'), [])

    async def test_start_does_not_call_historical_events(self):
        add_event(self.store)
        await self.service.start()
        await asyncio.sleep(.02)
        self.transport.assert_not_called()
        self.assertEqual(self.store.list('phone_call'), [])

    async def test_event_claim_is_persistent_and_idempotent(self):
        event = add_event(self.store)
        first = queue_event(self.service, event)
        self.assertEqual(queue_event(self.service, event)['id'], first['id'])
        other = PhoneAlerts(self.store, SETTINGS, self.transport)
        self.assertEqual(queue_event(other, event)['id'], first['id'])
        self.assertEqual(other.queue.qsize(), 0)
        self.assertEqual(self.service.queue.qsize(), 1)

    async def test_wrong_zone_review_and_nonurgent_are_excluded(self):
        self.store.put('policy', {'id': 'p2', 'zone_id': '다른 개소'})
        for i, extra in enumerate(({'policy_id': 'p2'}, {'severity': 'REVIEW'}, {'kind': 'REVIEW_REQUIRED'})):
            self.assertIsNone(queue_event(self.service, add_event(self.store, str(i), **extra)))
        event = add_event(self.store)
        self.store.put('review', {'event_id': event['id'], 'action': 'ACKNOWLEDGED'})
        self.assertIsNone(queue_event(self.service, event))
        self.assertEqual(self.service.queue.qsize(), 0)

    async def test_cooldown_and_stale_events_are_recorded_without_calls(self):
        queue_event(self.service, add_event(self.store))
        self.assertEqual(queue_event(self.service, add_event(self.store, 'e2'))['status'], 'suppressed')
        old = (datetime.now(timezone.utc)-timedelta(minutes=4)).isoformat()
        self.assertEqual(queue_event(self.service, add_event(self.store, 'e3', created_at=old))['status'], 'expired')
        self.assertEqual(self.service.queue.qsize(), 1)

    async def test_manual_retry_same_request_is_idempotent_but_new_request_is_limited(self):
        first = self.service.enqueue(request_id='request-one')
        self.assertEqual(first, self.service.enqueue(request_id='request-one'))
        with self.assertRaises(ValueError):
            self.service.enqueue(request_id='request-two')

    async def test_restart_does_not_retry_ambiguous_calls(self):
        row = self.service.enqueue(request_id='test')
        self.service.update(row['id'], status='connecting')
        self.service.queue.get_nowait()
        self.service.queue.task_done()
        await self.service.start()
        self.assertEqual(self.store.get('phone_call', row['id'])['status'], 'interrupted')
        self.transport.assert_not_called()

    async def test_new_event_dispatches_once_and_ack_is_separate_from_review(self):
        async def transport(service, row):
            self.assertFalse(service.acknowledge(row['id'], 'openai_voice_tool'))
            service.update(row['id'], status='in-progress')
            self.assertTrue(service.acknowledge(row['id'], 'dtmf_1'))
            service.update(row['id'], status='completed')
        self.transport.side_effect = transport
        await self.service.start()
        add_event(self.store)
        self.service.scan()
        await asyncio.wait_for(self.service.routing_queue.join(), 1)
        await asyncio.wait_for(self.service.queue.join(), 1)
        self.service.scan()
        self.transport.assert_awaited_once()
        row = self.store.list('phone_call')[0]
        self.assertIsNotNone(row['acknowledged_at'])
        self.assertEqual(row['status'], 'completed')
        self.assertEqual(self.store.list('review'), [])
        self.assertEqual(len(self.store.list('phone_call_log')), 4)

    async def test_uncertain_dispatch_is_not_retried_or_logged_verbatim(self):
        self.transport.side_effect = RuntimeError('private-claw-key 01000000000')
        await self.service.start()
        self.service.enqueue(request_id='test')
        await asyncio.wait_for(self.service.queue.join(), 1)
        row = self.store.list('phone_call')[0]
        self.assertEqual(row['status'], 'unknown')
        self.transport.assert_awaited_once()
        output = json.dumps(self.service.status())
        self.assertNotIn(SETTINGS.api_key, output)
        self.assertNotIn(SETTINGS.openai_key, output)
        self.assertNotIn(SETTINGS.to_number, output)
        self.assertNotIn(SETTINGS.api_key, repr(SETTINGS))

    async def test_pending_event_review_cancels_before_dispatch(self):
        event = add_event(self.store)
        row = queue_event(self.service, event)
        self.store.put('review', {'event_id': event['id'], 'action': 'DISMISSED'})
        task = asyncio.create_task(self.service._dispatch())
        self.service.tasks = [task]
        await asyncio.wait_for(self.service.queue.join(), 1)
        self.transport.assert_not_called()
        self.assertEqual(self.store.get('phone_call', row['id'])['status'], 'canceled')

    async def test_multiple_process_workers_cannot_drain_same_database(self):
        with tempfile.TemporaryDirectory() as folder:
            first_store = MemoryStore(str(Path(folder)/'test.sqlite'))
            second_store = MemoryStore(str(Path(folder)/'test.sqlite'))
            first = PhoneAlerts(first_store, SETTINGS, self.transport)
            second = PhoneAlerts(second_store, SETTINGS, self.transport)
            try:
                await first.start()
                await second.start()
                self.assertFalse(second.status()['ready'])
                self.assertEqual(second.worker_error, 'another_phone_worker_running')
            finally:
                await first.stop()
                await second.stop()
                first_store.db.close()
                second_store.db.close()

    async def test_env_file_loads_keys_without_exposing_them(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'shared.env').write_text('OPENAI_API_KEY=shared-key\n')
            (root/'.env.clawops').write_text('CHEMIGUARD_ENV_FILE=shared.env\nCLAWOPS_API_KEY=private\nCLAWOPS_ENABLED=true\nCLAWOPS_TO_NUMBER=+82-10-0000-0000\n')
            settings = PhoneSettings.load(root, {})
            self.assertEqual(settings.openai_key, 'shared-key')
            self.assertEqual(settings.to_number, '01000000000')
            self.assertTrue(settings.enabled)
        self.assertEqual(normalize_number('bad-number'), '')


class OpenAITransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from chemiguard import phone_transport
        self.module = phone_transport
        self.store = MemoryStore()
        self.service = PhoneAlerts(self.store, SETTINGS, AsyncMock())
        self.row = self.service.enqueue(request_id='test')

    async def asyncTearDown(self):
        await self.service.stop()
        self.store.db.close()

    async def test_agent_has_only_openai_no_hosted_ai_recording_or_transfer(self):
        agent, session = self.module.build_agent(self.service, self.row)
        self.assertIsInstance(session, self.module.OpenAIOnlySession)
        self.assertEqual(session._config.model, PHONE_MODEL)
        self.assertEqual(agent._base_url, 'https://api.claw-ops.com')
        self.assertFalse(agent._recording)
        self.assertFalse(agent._prewarm_enabled)
        self.assertIsNone(agent._machine_detection)
        self.assertEqual({t.value for t in agent._builtin_tools}, {'hang_up'})
        self.assertEqual(agent._mcp_servers, [])
        self.assertEqual(list(agent._tool_registry._tools), ['acknowledge_notification'])

    async def test_openai_endpoint_is_pinned_despite_environment_overrides(self):
        _, session = self.module.build_agent(self.service, self.row)
        client = MagicMock()
        client.realtime.connect.return_value.enter = AsyncMock(return_value=object())
        with patch.dict('os.environ', {'OPENAI_BASE_URL': 'https://other.invalid', 'OPENAI_WEBSOCKET_BASE_URL': 'wss://other.invalid'}), patch.object(self.module, 'AsyncOpenAI', return_value=client) as factory:
            await session._open_connection()
        self.assertEqual(factory.call_args.kwargs['base_url'], 'https://api.openai.com/v1')
        self.assertEqual(factory.call_args.kwargs['api_key'], SETTINGS.openai_key)
        self.assertEqual(factory.call_args.kwargs['websocket_base_url'], 'wss://api.openai.com/v1')
        client.realtime.connect.assert_called_once_with(model=PHONE_MODEL)

    async def test_sdk_outbound_body_has_no_managed_ai_or_machine_detection(self):
        agent, _ = self.module.build_agent(self.service, self.row)
        response = MagicMock(status=201)
        response.json = AsyncMock(return_value={'callId': 'CAtest'})
        response.__aenter__ = AsyncMock(return_value=response)
        http = MagicMock()
        http.post.return_value = response
        http.__aenter__ = AsyncMock(return_value=http)
        with patch.object(agent, 'connect', new=AsyncMock()), patch('aiohttp.ClientSession', return_value=http):
            call = await agent.call(SETTINGS.to_number, timeout=30)
        self.assertEqual(call.call_id, 'CAtest')
        self.assertEqual(http.post.call_args.kwargs['json'], {'To': SETTINGS.to_number, 'From': SETTINGS.from_number, 'Timeout': 30})

    async def test_audio_is_relayed_without_external_synthesis(self):
        _, session = self.module.build_agent(self.service, self.row)
        session._connection = MagicMock()
        session._connection.input_audio_buffer.append = AsyncMock()
        session._call = MagicMock()
        session._call.send_audio = AsyncMock()
        audio = b'\xff' * 160
        await session.feed_audio(audio, 20)
        self.assertEqual(session._connection.input_audio_buffer.append.call_args.kwargs['audio'], base64.b64encode(audio).decode())
        await session._handle_event(SimpleNamespace(type='response.output_audio.delta', item_id='i1', delta=base64.b64encode(audio).decode()))
        session._call.send_audio.assert_awaited_once_with(audio)

    async def test_openai_error_fails_closed(self):
        _, session = self.module.build_agent(self.service, self.row)
        await session._handle_event(SimpleNamespace(type='error', error='sensitive upstream error'))
        self.assertTrue(session.failure.is_set())
        self.assertEqual(session.failure_code, 'openai_session_failed')

    async def test_realtime_evidence_requires_upstream_session_and_counts_audio(self):
        _, session = self.module.build_agent(self.service, self.row)
        self.assertIsNone(session.evidence['session_updated_at'])
        await session.feed_audio(b'\xff' * 160, 20)
        self.assertEqual(session.evidence['input_audio_bytes'], 0)
        await session._handle_event(SimpleNamespace(type='session.updated', session=SimpleNamespace(model=PHONE_MODEL)))
        session._connection = MagicMock()
        session._connection.input_audio_buffer.append = AsyncMock()
        session._call = MagicMock()
        session._call.send_audio = AsyncMock()
        session._call.clear_audio = AsyncMock()
        session._call.emit = AsyncMock()
        await session.feed_audio(b'\xff' * 160, 20)
        await session._handle_event(SimpleNamespace(type='response.output_audio.delta', item_id='i1', delta=base64.b64encode(b'\xff' * 320).decode()))
        await session._handle_event(SimpleNamespace(type='response.done', response=SimpleNamespace(status='completed')))
        evidence = self.store.get('phone_call', self.row['id'])['realtime']
        self.assertTrue(evidence['session_updated_at'])
        self.assertEqual(evidence['model'], PHONE_MODEL)
        self.assertEqual(evidence['input_audio_bytes'], 160)
        self.assertEqual(evidence['output_audio_bytes'], 320)
        self.assertEqual(evidence['completed_responses'], 1)
        self.assertEqual(evidence['speech_turns'], 0)
        self.assertNotIn(SETTINGS.openai_key, json.dumps(evidence))

    async def test_unexpected_realtime_model_is_not_verified(self):
        _, session = self.module.build_agent(self.service, self.row)
        await session._handle_event(SimpleNamespace(type='session.updated', session=SimpleNamespace(model='unexpected-model')))
        self.assertTrue(session.failure.is_set())
        self.assertEqual(session.failure_code, 'openai_unexpected_model')
        self.assertIsNone(session.evidence['session_updated_at'])

    async def test_untrusted_media_endpoint_is_rejected(self):
        agent, session = self.module.build_agent(self.service, self.row)
        await agent._handle_outbound_ready({'callId': 'CA1', 'mediaUrl': 'wss://other.invalid/media'})
        self.assertTrue(session.failure.is_set())

    async def test_no_answer_is_not_treated_as_acknowledgment(self):
        agent = MagicMock()
        call = SimpleNamespace(call_id='CAtest', status='queued', ended_status='no-answer', wait=AsyncMock())
        agent.call = AsyncMock(return_value=call)
        agent.disconnect = AsyncMock()
        session = SimpleNamespace(failure=asyncio.Event(), last_activity=None)
        with patch.object(self.module, 'build_agent', return_value=(agent, session)):
            await self.module.place_call(self.service, self.row)
        row = self.store.get('phone_call', self.row['id'])
        self.assertEqual(row['status'], 'no-answer')
        self.assertIsNone(row['acknowledged_at'])
        agent.disconnect.assert_awaited_once()

    async def test_openai_failure_terminates_carrier_without_fallback(self):
        agent = MagicMock()
        async def wait_forever():
            await asyncio.Event().wait()
        call = SimpleNamespace(call_id='CAtest', status='in-progress', wait=wait_forever)
        agent.call = AsyncMock(return_value=call)
        agent.disconnect = AsyncMock()
        failure = asyncio.Event()
        failure.set()
        session = SimpleNamespace(failure=failure, failure_code='openai_session_failed', last_activity=None)
        with patch.object(self.module, 'build_agent', return_value=(agent, session)), patch.object(self.module, 'finish_at_carrier', new=AsyncMock()) as finish:
            await self.module.place_call(self.service, self.row)
        finish.assert_awaited_once_with(SETTINGS, 'CAtest')
        self.assertEqual(self.store.get('phone_call', self.row['id'])['status'], 'failed')


class PhoneAPITests(unittest.TestCase):
    def test_status_test_call_csrf_and_recipient_restrictions(self):
        from fastapi.testclient import TestClient
        from chemiguard import app as module
        store = MemoryStore()
        service = PhoneAlerts(store, SETTINGS, AsyncMock(), decider=fake_decider)
        async def finish(service, row):
            service.update(row['id'], status='no-answer')
        service.transport.side_effect = finish
        try:
            with patch.object(module, 'store', store), patch.object(module, 'PhoneAlerts', return_value=service), TestClient(module.app) as client:
                status = client.get('/api/phone').json()
                self.assertTrue(status['ready'])
                self.assertNotIn(SETTINGS.api_key, json.dumps(status))
                request = {'request_id': '28530970-7a74-41d2-ae60-cbb081d1a0b9', 'confirm': True}
                self.assertEqual(client.post('/api/phone/test', json=request, headers={'Origin':'https://other.invalid'}).status_code, 403)
                self.assertEqual(client.post('/api/phone/test', json=request | {'to':'01012345678'}).status_code, 422)
                self.assertEqual(client.post('/api/phone/test', json=request | {'confirm':False}).status_code, 422)
                first = client.post('/api/phone/test', json=request)
                self.assertEqual(first.status_code, 200)
                self.assertEqual(client.post('/api/phone/test', json=request).json()['id'], first.json()['id'])
                self.assertEqual(len(store.list('phone_call')), 1)
                event = add_event(store, observation_id='o1')
                service.update(first.json()['id'], event_id=event['id'])
                detail = client.get('/api/events/e1').json()
                self.assertEqual(len(detail['phone_calls']), 1)
                self.assertNotIn('recipient_hash', detail['phone_calls'][0])
        finally:
            store.db.close()


if __name__ == '__main__':
    unittest.main()
