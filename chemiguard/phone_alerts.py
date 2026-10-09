"""Opt-in phone outbox. No network traffic until an enabled job is dispatched."""
import asyncio
import fcntl
import hashlib
import importlib.metadata
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

from .config import ROOT
from .contact_routing import ContactRouter, POLICY, ROLES, ROUTING_MODEL, event_context, evidence_problem
from .store import now
from .phone_demo import PhoneDemo

PHONE_MODEL = 'gpt-realtime-2'
ALERT_KINDS = set(POLICY)
ACTIVE = {'queued', 'connecting', 'ringing', 'in-progress'}


def normalize_number(value):
    value = re.sub(r'[\s()-]', '', value or '')
    if value.startswith('+82'):
        value = '0' + value[3:]
    return value if re.fullmatch(r'0\d{8,10}', value) else ''


@dataclass(frozen=True)
class PhoneSettings:
    enabled: bool = False
    automatic: bool = False
    api_key: str = field(default='', repr=False)
    openai_key: str = field(default='', repr=False)
    account_id: str = field(default='', repr=False)
    from_number: str = field(default='', repr=False)
    to_number: str = field(default='', repr=False)
    zone_id: str = ''
    cooldown_s: int = 50
    max_age_s: int = 120
    ring_timeout_s: int = 30
    session_limit_s: int = 180

    @classmethod
    def load(cls, root=ROOT, environ=None):
        env = dict(os.environ if environ is None else environ)
        private = dict(dotenv_values(root / '.env.clawops'))
        inherited = env.get('CHEMIGUARD_ENV_FILE') or private.get('CHEMIGUARD_ENV_FILE')
        shared = dict(dotenv_values(Path(inherited) if Path(inherited).is_absolute() else root / inherited)) if inherited else {}
        values = {**dotenv_values(root / '.env'), **shared, **private, **env}
        get = lambda key: (values.get(key) or '').strip()
        return cls(enabled=get('CLAWOPS_ENABLED').lower() == 'true',
                   automatic=get('CLAWOPS_AUTO_CALL').lower() == 'true',
                   api_key=get('CLAWOPS_API_KEY'), openai_key=get('OPENAI_API_KEY'),
                   account_id=get('CLAWOPS_ACCOUNT_ID'),
                   from_number=normalize_number(get('CLAWOPS_FROM_NUMBER')),
                   to_number=normalize_number(get('CLAWOPS_TO_NUMBER')),
                   zone_id=get('CLAWOPS_ZONE_ID'))

    def missing(self):
        fields = {'CLAWOPS_API_KEY': self.api_key, 'OPENAI_API_KEY': self.openai_key,
                  'CLAWOPS_ACCOUNT_ID': self.account_id if re.fullmatch(r'[A-Za-z0-9_-]+', self.account_id) else '',
                  'CLAWOPS_FROM_NUMBER': self.from_number, 'CLAWOPS_TO_NUMBER': self.to_number,
                  'CLAWOPS_ZONE_ID': self.zone_id}
        missing = [key for key, value in fields.items() if not value]
        if self.from_number and self.from_number == self.to_number:
            missing.append('수신번호와 발신번호는 달라야 합니다')
        return missing


def dependency_ready():
    try:
        return (importlib.metadata.version('clawops') == '0.38.0'
                and bool(importlib.metadata.version('openai')) and bool(importlib.metadata.version('aiohttp')))
    except importlib.metadata.PackageNotFoundError:
        return False


def public_call(row):
    return {key: value for key, value in row.items() if key not in {'recipient_hash'}}


class PhoneAlerts:
    def __init__(self, store, settings=None, transport=None, decider=None):
        self.store = store
        self.settings = settings or PhoneSettings.load()
        self.transport = transport
        self.router = ContactRouter(store, self.settings.openai_key, decide=decider)
        self.queue = asyncio.Queue(maxsize=4)
        self.routing_queue = asyncio.Queue(maxsize=8)
        self.routing_error = None
        self.tasks = []
        self.cursor = 0
        self.worker_error = None
        self.stopping = False
        self.process_lock = None
        self.demo = PhoneDemo(self)

    def status(self):
        missing = self.settings.missing()
        dependencies = dependency_ready() if self.transport is None else True
        ready = self.settings.enabled and not missing and dependencies and not self.stopping
        calls = self.store.list('phone_call', 50)
        return {'enabled': self.settings.enabled, 'automatic': self.settings.automatic,
                'ready': ready, 'missing': missing, 'dependencies_ready': dependencies,
                'ai_provider': 'OpenAI', 'model': PHONE_MODEL, 'carrier': 'ClawOps',
                'mode': 'demo', 'zone_id': self.settings.zone_id,
                'roles': ROLES, 'routing_model': ROUTING_MODEL,
                'routing_error': self.routing_error,
                'routing_rules': {kind: rule[0] for kind, rule in POLICY.items()},
                'cooldown_scope': 'recipient',
                'demo': self.demo.status(),
                'recipient': ('***' + self.settings.to_number[-4:]) if self.settings.to_number else '',
                'cooldown_s': self.settings.cooldown_s, 'worker_error': self.worker_error,
                'calls': [public_call(row) for row in calls]}

    async def start(self):
        database = self.store.db.execute('PRAGMA database_list').fetchone()[2]
        if database:
            self.process_lock = open(Path(database).with_suffix('.phone.lock'), 'a')
            try:
                fcntl.flock(self.process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self.process_lock.close()
                self.process_lock = None
                self.stopping = True
                self.worker_error = 'another_phone_worker_running'
                return
        with self.store.lock:
            self.cursor = self.store.db.execute("SELECT coalesce(max(rowid),0) FROM records WHERE kind='event'").fetchone()[0]
        # Never replay an ambiguous call or drain an old queue after a restart.
        for row in self.store.list('phone_call', 1000):
            if row['status'] in ACTIVE:
                self.update(row['id'], status='interrupted', error_code='server_restarted_no_retry')
        self.demo.reset_after_restart()
        self.tasks = [asyncio.create_task(self._watch()), asyncio.create_task(self._route_events()),
                      asyncio.create_task(self.demo.watch()),
                      asyncio.create_task(self._dispatch())]

    async def stop(self):
        self.stopping = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        while not self.queue.empty():
            call_id = self.queue.get_nowait()
            self.update(call_id, status='canceled', error_code='server_stopped_before_dispatch')
            self.queue.task_done()
        self.tasks = []
        if self.process_lock:
            self.process_lock.close()
            self.process_lock = None

    def update(self, call_id, **changes):
        with self.store.lock:
            row = self.store.get('phone_call', call_id)
            if not row:
                return None
            row.update(changes, updated_at=now())
            self.store.put('phone_call', row, replace=True)
            self.store.put('phone_call_log', {'phone_call_id': call_id, **changes})
            return row

    def acknowledge(self, call_id, method):
        row = self.store.get('phone_call', call_id)
        if not row or row['status'] != 'in-progress':
            return False
        if not row.get('acknowledged_at'):
            self.update(call_id, acknowledged_at=now(), acknowledgment_method=method)
        # Delivery acknowledgment is deliberately NOT a PPE review or alarm clearance.
        return True

    def enqueue_plan(self, plan_id, revision, request_id):
        plan = self.store.get('notification_plan', plan_id)
        if not plan or plan['revision'] != revision:
            raise ValueError('발신 계획을 다시 확인해 주세요.')
        plans = self.store.related('notification_plan', 'event_id', plan['event_id'])
        if revision != max(p['revision'] for p in plans):
            raise ValueError('연락 대상이 변경되었습니다. 최신 계획을 확인해 주세요.')
        event = self.router.event(plan['event_id'])
        return self.enqueue(event, request_id, plan=plan, manual=True)

    def cooldown_remaining(self, recipient_hash, exclude=None, dispatched_only=False):
        remaining = 0
        current = datetime.now(timezone.utc)
        for row in self.store.list('phone_call', 1000):
            if (row['id'] == exclude or row.get('recipient_hash') != recipient_hash
                    or row.get('status') in {'suppressed', 'expired', 'canceled'}):
                continue
            if dispatched_only and row.get('status') == 'queued':
                continue
            timestamp = row.get('dial_accepted_at') or row.get('dispatched_at') or row['created_at']
            remaining = max(remaining, self.settings.cooldown_s -
                            (current - datetime.fromisoformat(timestamp)).total_seconds())
        return max(0, remaining)

    def enqueue(self, event=None, request_id=None, *, plan=None, manual=None, role='site_safety_manager'):
        status = self.status()
        if not status['ready']:
            raise ValueError('전화 연결이 비활성화되었거나 서버 설정이 부족합니다.')
        manual = event is None if manual is None else manual
        if event:
            if not plan or plan.get('event_id') != event['id']:
                raise ValueError('사건의 연락 대상 계획이 필요합니다.')
            role = plan['role']
        if role not in ROLES:
            raise ValueError('연락 역할을 확인해 주세요.')
        recipient_hash = hashlib.sha256(self.settings.to_number.encode()).hexdigest()
        source_id = f"{event['id']}:{role}" if event else str(request_id)
        call_id = 'phone_' + hashlib.sha256(f'{source_id}:{recipient_hash}'.encode()).hexdigest()[:32]
        existing = self.store.get('phone_call', call_id)
        if existing:
            if existing.get('role', 'site_safety_manager') != role:
                raise ValueError('같은 요청의 연락 대상을 변경할 수 없습니다.')
            return public_call(existing)
        policy = self.store.get('policy', event.get('policy_id')) if event else None
        zone = policy.get('zone_id') if policy else self.settings.zone_id
        if event:
            invalid = evidence_problem(event_context(self.store, event))
            reviewed = self.store.related('review', 'event_id', event['id'])
            if invalid or reviewed or zone != self.settings.zone_id:
                if manual:
                    raise ValueError('담당 개소의 유효하고 미검토된 사건만 전화할 수 있습니다.')
                return None
            if not manual and (not self.settings.automatic or role != POLICY[event['kind']][0]
                               or plan['selected_by'] == 'operator' or plan.get('demo_replay')):
                return None
        demo_replay = bool(manual and plan and plan.get('demo_replay'))
        dispatch_created_at = now() if not event or demo_replay else event['created_at']
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(dispatch_created_at)).total_seconds()
        recent = self.store.list('phone_call', 1000)
        if request_id and any(row.get('request_id') == str(request_id) for row in recent):
            raise ValueError('이미 다른 발신에 사용한 요청입니다.')
        # Legacy event calls predate roles; do not redial them after upgrading.
        legacy = next((r for r in recent if event and r.get('event_id') == event['id'] and not r.get('role')), None)
        if legacy:
            return public_call(legacy)
        cooling = self.cooldown_remaining(recipient_hash) > 0
        limit_reason = ('recipient_cooldown' if cooling
                        else 'queue_full' if self.queue.full() else None)
        if manual and limit_reason:
            raise ValueError({'recipient_cooldown': f'등록번호에는 {self.settings.cooldown_s}초 간격으로 발신합니다. 잠시 후 다시 시도해 주세요.',
                              'queue_full': '전화 대기열이 가득 찼습니다. 잠시 후 다시 시도해 주세요.'}[limit_reason])
        if manual and (age > self.settings.max_age_s or age < 0):
            raise ValueError('120초가 지난 사건입니다. 이전 사건 시연을 선택해 주세요.')
        state = 'expired' if age > self.settings.max_age_s or age < 0 else 'suppressed' if limit_reason else 'queued'
        row = {'id': call_id, 'event_id': event['id'] if event else None, 'run_id': event['run_id'] if event else None,
               'plan_id': plan['id'] if plan else None, 'plan_revision': plan['revision'] if plan else None,
               'decision_id': plan['decision_id'] if plan else None, 'role': role, 'role_label': ROLES[role],
               'request_id': str(request_id) if request_id else None,
               'demo_replay': demo_replay, 'dispatch_created_at': dispatch_created_at,
               'error_code': 'event_expired' if state == 'expired' else limit_reason,
               'event_created_at': event['created_at'] if event else now(),
               'kind': event['kind'] if event else 'PHONE_TEST',
               'reason': event['reason'][:500] if event else '전화 연결 및 OpenAI 음성 대화 시험입니다.',
               'zone_id': zone, 'recipient_hash': recipient_hash, 'recipient': status['recipient'],
               'mode': 'demo', 'manual': manual, 'status': state, 'provider_call_id': None,
               'acknowledged_at': None, 'ai_provider': 'OpenAI', 'model': PHONE_MODEL}
        try:
            row = self.store.put('phone_call', row)
        except sqlite3.IntegrityError:
            return public_call(self.store.get('phone_call', call_id))
        if state == 'queued':
            self.queue.put_nowait(call_id)
        if plan:
            self.store.put('notification_plan_log', {'plan_id': plan['id'], 'phone_call_id': call_id, 'status': state})
        return public_call(row)

    def enqueue_demo(self, reservation, events):
        self.demo.validate(reservation, events)
        current = self.store.get('phone_demo', reservation['id'])
        if not current or current['status'] != 'deciding' or not self.status()['ready']:
            raise ValueError('demo_not_armed')
        call_id = 'phone_' + reservation['id']
        existing = self.store.get('phone_call', call_id)
        if existing:
            return public_call(existing)
        if self.queue.full():
            raise ValueError('demo_queue_full')
        if any(call.get('run_id') == reservation['run_id'] for call in self.store.list('phone_call')):
            raise ValueError('demo_run_already_called')
        # Leak routing takes priority; PPE remains a separately evidenced observation.
        leak = next(event for event in events if event['kind'] == 'RELEASE_SUSPECTED')
        summary = [{key: event.get(key) for key in ('id', 'kind', 'reason', 'source_time_s', 'created_at')}
                   for event in events]
        row = self.store.put('phone_call', {
            'id': call_id, 'event_id': leak['id'], 'event_ids': [event['id'] for event in events],
            'events': summary, 'run_id': reservation['run_id'], 'reservation_id': reservation['id'],
            'decision_ids': reservation['decision_ids'], 'kind': 'PPE_AND_RELEASE',
            'role': 'safety_control_room', 'role_label': ROLES['safety_control_room'],
            'reason': '미착용 · 누출 통합 안내', 'mode': 'demo', 'manual': False, 'demo_replay': False,
            'event_created_at': min(event['created_at'] for event in events),
            'dispatch_created_at': min(event['created_at'] for event in events),
            'zone_id': self.settings.zone_id, 'recipient': self.status()['recipient'],
            'recipient_hash': hashlib.sha256(self.settings.to_number.encode()).hexdigest(),
            'status': 'queued', 'error_code': None, 'provider_call_id': None,
            'acknowledged_at': None, 'ai_provider': 'OpenAI', 'model': PHONE_MODEL,
        })
        self.queue.put_nowait(call_id)
        return public_call(row)

    def calls_for_event(self, event_id):
        return [public_call(row) for row in self.store.list('phone_call', 1000)
                if row.get('event_id') == event_id or event_id in row.get('event_ids', [])]

    def scan(self):
        with self.store.lock:
            rows = self.store.db.execute("SELECT rowid,payload FROM records WHERE kind='event' AND rowid>? ORDER BY rowid LIMIT 100", (self.cursor,)).fetchall()
        for record in rows:
            self.cursor = record['rowid']
            event = json.loads(record['payload'])
            if self.status()['ready'] and event.get('kind') in ALERT_KINDS:
                if self.routing_queue.full():
                    self.store.put('contact_routing_log', {'event_id': event['id'], 'status': 'routing_queue_full'})
                    self.routing_error = 'routing_queue_full'
                else:
                    self.routing_queue.put_nowait(event['id'])

    async def _route_events(self):
        while True:
            event_id = await self.routing_queue.get()
            try:
                event = self.router.event(event_id)
                context = event_context(self.store, event)
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(event['created_at'])).total_seconds()
                if context['zone_id'] != self.settings.zone_id or not 0 <= age <= self.settings.max_age_s:
                    continue
                plan = await self.router.prepare(event_id, automatic=True)
                if self.settings.automatic:
                    self.enqueue(event, plan=plan, manual=False)
                self.routing_error = None
            except ValueError:
                self.store.put('contact_routing_log', {'event_id': event_id, 'status': 'ineligible_event'})
            except Exception:
                self.routing_error = 'routing_worker_failed'
                self.store.put('contact_routing_log', {'event_id': event_id, 'status': 'routing_worker_failed'})
            finally:
                self.routing_queue.task_done()

    async def _watch(self):
        while True:
            try:
                self.scan()
                self.worker_error = None
            except Exception:
                self.worker_error = 'event_scan_failed'
            await asyncio.sleep(1)

    async def _dispatch(self):
        while True:
            call_id = await self.queue.get()
            try:
                row = self.store.get('phone_call', call_id)
                remaining = self.cooldown_remaining(row['recipient_hash'], exclude=call_id, dispatched_only=True)
                if remaining:
                    await asyncio.sleep(remaining)
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(row.get('dispatch_created_at', row['event_created_at']))).total_seconds()
                if age > self.settings.max_age_s or age < 0:
                    self.update(call_id, status='expired')
                    continue
                if row.get('reservation_id'):
                    try:
                        reservation = self.store.get('phone_demo', row['reservation_id'])
                        events = [self.store.get('event', event_id) for event_id in row['event_ids']]
                        if not all(events):
                            raise ValueError('demo_evidence_missing')
                        self.demo.validate(reservation, events)
                    except ValueError:
                        self.update(call_id, status='canceled', error_code='event_evidence_invalid_before_dispatch')
                        continue
                if row['event_id'] and self.store.related('review', 'event_id', row['event_id']):
                    self.update(call_id, status='canceled', error_code='event_reviewed_before_dispatch')
                    continue
                if row['event_id']:
                    event = self.store.get('event', row['event_id'])
                    if not event or evidence_problem(event_context(self.store, event)):
                        self.update(call_id, status='canceled', error_code='event_evidence_invalid_before_dispatch')
                        continue
                self.update(call_id, status='connecting', dispatched_at=now())
                if self.transport is None:
                    from .phone_transport import place_call
                    transport = place_call
                else:
                    transport = self.transport
                await transport(self, row)
            except asyncio.CancelledError:
                self.update(call_id, status='interrupted', error_code='server_stopped_no_retry')
                raise
            except Exception:
                # Never persist SDK exception text: it can contain keys, URLs or phone numbers.
                self.update(call_id, status='unknown', error_code='dispatch_uncertain_no_retry')
            finally:
                self.queue.task_done()
