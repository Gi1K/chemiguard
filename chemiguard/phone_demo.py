"""One combined call per authorized receiver run, using real contact decisions."""
import asyncio
from datetime import datetime, timezone

from .contact_routing import POLICY, event_context, evidence_problem
from .store import now

SOURCE_ID = '766a49b5bfcb725f'
KINDS = ('VIOLATION_SUSPECTED', 'RELEASE_SUSPECTED')
PENDING = {'armed', 'collecting', 'deciding'}


def age(timestamp):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)).total_seconds()


class PhoneDemo:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def latest(self):
        rows = self.store.list('phone_demo', 1)
        return rows[0] if rows else None

    def status(self):
        row = self.latest() or {'status': 'disarmed', 'source_id': SOURCE_ID}
        call = self.store.get('phone_call', row.get('call_id'))
        policy = self.store.get('phone_demo_policy', 'receiver') or {}
        return {**row, 'per_run_enabled': bool(policy.get('enabled')),
                'call_status': call['status'] if call else None}

    def configure(self, enabled):
        if enabled and (not self.service.status()['ready'] or self.service.settings.automatic):
            raise ValueError('전화 설정을 확인하고 일반 자동 발신은 꺼 주세요.')
        self.store.put('phone_demo_policy', {'id': 'receiver', 'enabled': enabled}, replace=True)
        if not enabled:
            self.cancel()
        return self.status()

    def on_run(self, run_id):
        policy = self.store.get('phone_demo_policy', 'receiver') or {}
        run = self.store.get('run', run_id)
        if not policy.get('enabled') or not run or run['source_id'] != SOURCE_ID:
            return
        reservation_id = 'demo_run_' + run_id
        if self.store.get('phone_demo', reservation_id):
            return
        # Called only after a new explicit start, never by page loads or restart recovery.
        self.cancel()
        self.store.put('phone_demo', {
            'id': reservation_id, 'source_id': SOURCE_ID, 'run_id': run_id,
            'eligible_since': run['created_at'], 'status': 'collecting',
            'event_ids': [], 'decision_ids': [], 'call_id': None,
            'error_code': None, 'max_calls': 1, 'per_run': True,
        })

    def update(self, row, **changes):
        row = {**row, **changes, 'updated_at': now()}
        self.store.put('phone_demo', row, replace=True)
        return row

    def reset_after_restart(self):
        for row in self.store.list('phone_demo'):
            if row['status'] in PENDING:
                self.update(row, status='canceled', error_code='server_restarted_no_retry')

    def arm(self, request_id):
        existing = self.store.get('phone_demo', 'demo_' + str(request_id))
        if existing:
            return existing
        if not self.service.status()['ready']:
            raise ValueError('전화 연결 설정을 먼저 확인해 주세요.')
        if self.service.settings.automatic:
            raise ValueError('일반 자동 발신을 끈 상태에서만 한 통 시연을 예약할 수 있습니다.')
        current = self.latest()
        if current and current['status'] in PENDING:
            return current
        if any(row['status'] in {'queued', 'connecting', 'ringing', 'in-progress'}
               for row in self.store.list('phone_call')):
            raise ValueError('현재 전화가 끝난 후 예약해 주세요.')
        return self.store.put('phone_demo', {
            'id': 'demo_' + str(request_id), 'source_id': SOURCE_ID,
            'status': 'armed', 'run_id': None, 'event_ids': [], 'decision_ids': [],
            'call_id': None, 'error_code': None, 'max_calls': 1,
        })

    def cancel(self):
        row = self.latest()
        if row and row['status'] in PENDING:
            self.update(row, status='canceled', error_code='operator_canceled')
        return self.status()

    def validate(self, row, events):
        run = self.store.get('run', row['run_id'])
        if (not run or run['source_id'] != SOURCE_ID or run['created_at'] < row.get('eligible_since', row['created_at'])
                or run['status'] not in {'RUNNING', 'FINISHED'}):
            raise ValueError('demo_run_invalid')
        if len(events) != 2 or {event['kind'] for event in events} != set(KINDS):
            raise ValueError('demo_events_incomplete')
        for event in events:
            context = event_context(self.store, event)
            if (event['run_id'] != run['id'] or evidence_problem(context)
                    or context['zone_id'] != self.service.settings.zone_id
                    or self.store.related('review', 'event_id', event['id'])
                    or not 0 <= age(event['created_at']) <= self.service.settings.max_age_s
                    or any(obs.get('generation', 1) != run.get('generation', 1)
                           for obs in context['observations'])):
                raise ValueError('demo_evidence_invalid')

    async def tick(self):
        row = self.latest()
        if not row or row['status'] not in {'armed', 'collecting'}:
            return
        if age(row['created_at']) > 3600:
            self.update(row, status='expired', error_code='reservation_expired')
            return
        if row['status'] == 'armed':
            runs = [run for run in self.store.related('run', 'source_id', SOURCE_ID)
                    if run['created_at'] >= row['created_at']]
            if not runs:
                return
            run = min(runs, key=lambda value: value['created_at'])
            row = self.update(row, status='collecting', run_id=run['id'])
        run = self.store.get('run', row['run_id'])
        if not run or run['status'] in {'STOPPED', 'ERROR', 'INTERRUPTED'}:
            self.update(row, status='canceled', error_code='demo_stopped')
            return
        if run['status'] not in {'RUNNING', 'FINISHED'}:
            return
        candidates = self.store.related('event', 'run_id', row['run_id'])
        events = []
        for kind in KINDS:
            for event in candidates:
                if event['kind'] != kind:
                    continue
                try:
                    self.service.router.event(event['id'])
                    context = event_context(self.store, event)
                    if (0 <= age(event['created_at']) <= self.service.settings.max_age_s
                            and all(obs.get('generation', 1) == run.get('generation', 1)
                                    for obs in context['observations'])):
                        events.append(event)
                        break
                except ValueError:
                    continue
        if len(events) != 2:
            if run['status'] == 'FINISHED':
                self.update(row, status='incomplete', error_code='both_events_not_observed')
            return
        # Persist the one-shot claim before any API await; never retry an ambiguous attempt.
        row = self.update(row, status='deciding', event_ids=[event['id'] for event in events])
        try:
            self.validate(row, events)
            decisions = []
            for event in events:
                decision = await self.service.router.decide(event['id'])
                rule = POLICY[event['kind']]
                if (decision['status'] != 'decisions' or decision['applied_role'] != rule[0]
                        or decision.get('evidence_state') != 'sufficient'):
                    raise ValueError('decisions_not_confirmed')
                decisions.append(decision)
            if self.store.get('phone_demo', row['id'])['status'] != 'deciding':
                return
            self.validate(row, events)
            row = self.update(row, decision_ids=[decision['id'] for decision in decisions])
            call = self.service.enqueue_demo(row, events)
            self.update(row, status='submitted', call_id=call['id'])
        except ValueError as error:
            self.update(row, status='failed', error_code=str(error) if str(error).startswith(('demo_', 'decisions_')) else 'demo_queue_unavailable')

    async def watch(self):
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                row = self.latest()
                if row and row['status'] in PENDING:
                    self.update(row, status='failed', error_code='demo_worker_failed_no_retry')
            await asyncio.sleep(1)
