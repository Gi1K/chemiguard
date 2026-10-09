"""One bounded offline smoke check of the public contract; never a paid call."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import httpx
import server


async def main():
    real_client = httpx.AsyncClient
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        settings = server.Settings('offline-test-key', 'offline-test-model', 'offline-demo-code-12345',
            ['http://localhost:34402'], True, 30, 30, 3_000_000, 5000, root / 'usage.db', root / 'STOP')
        app = server.create_app(settings)
        pid = 'TYCHEM_2000_YELLOW'
        source_url = server.lookup_module.PRODUCT_PAGES[pid]['url']
        answer = {'reply': '계약 검증용 응답입니다. 실제 보호구 선정 결과가 아닙니다.',
                  'candidates': [{'product_id': pid, 'selection_status': 'review_candidate', 'reason': '검증용 부분 조합입니다.'}],
                  'kits': [{'name': '검증용 초안', 'work_context': '황산 30% 별도 이송, 20℃ 비말', 'work_group': '검증용 이송',
                            'use_type': 3, 'comparison_note': '검증용 조합입니다.', 'product_ids': [pid],
                            'selection_reason': '계약 동작 검증입니다.', 'colour_note': '등록 색상 노랑입니다.',
                            'missing_information': ['장갑·장화·호흡 조건을 확인해야 합니다.']}],
                  'questions': ['노출 조건을 확인해 주세요.'], 'source_ids': [next(iter(server.contract.sources))],
                  'live_sources': [{'url': source_url, 'title': '검증용', 'evidence': '검증용 원문 행입니다.'}]}
        evidence = {'queries': ['7664-93-9'], 'sources': [{'product_id': pid, 'title': '검증용 DuPont', 'url': source_url,
                    'status': 'matched', 'retrieved_at': '2026-10-09T00:00:00Z', 'revision': 'fixture',
                    'rows': [{'cas': '7664-93-9', 'concentration': '30%', 'temperature': '20°C',
                              'raw_values': {'CAS': '7664-93-9', 'BT 1.0': 'fixture'}, 'cell_html': {}}],
                    'notes': ['Fixture only'], 'queries': [{'cas': '7664-93-9', 'status': 'matched'}]}]}
        calls, mode = [], ['success']

        def provider(request):
            assert str(request.url) == 'https://api.openai.com/v1/responses'
            payload = json.loads(request.content)
            assert payload['store'] is False and payload['text']['format']['strict'] is True
            assert payload['model'] == settings.model
            calls.append(payload)
            if mode[0] == 'timeout':
                raise httpx.ReadTimeout('private internal diagnostic must not leak')
            plan = 'cas_numbers' in payload['text']['format']['schema']['properties']
            value = {'cas_numbers': ['7664-93-9']} if plan else deepcopy(answer)
            if mode[0] == 'missing':
                value = {'cas_numbers': []} if plan else {**answer, 'candidates': [], 'kits': [], 'live_sources': []}
            if mode[0] == 'unknown_id' and not plan:
                value['candidates'][0]['product_id'] = 'NOT_IN_CATALOG'
            return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': json.dumps(value, ensure_ascii=False)}]}]})

        def client_factory(**kwargs):
            return real_client(transport=httpx.MockTransport(provider), **kwargs)

        headers = {'Authorization': 'Bearer ' + settings.demo_token, 'Origin': settings.origins[0]}
        body = {'message': '황산 30%, CAS 7664-93-9, 실외 20℃ 별도 이송입니다.', 'existing_kits': []}
        async with real_client(transport=httpx.ASGITransport(app=app), base_url='http://localhost:34402') as client:
            with patch.object(server.httpx, 'AsyncClient', client_factory), patch.object(server.lookup_module, 'lookup_chemicals', lambda _: deepcopy(evidence)):
                assert (await client.post('/api/ppe/chat', json=body)).status_code == 401
                assert (await client.post('/api/ppe/chat', json=body, headers={**headers, 'Origin': 'https://denied.example'})).status_code == 403
                assert (await client.post('/api/ppe/chat', content='x' * 33000, headers={**headers, 'Content-Type': 'application/json'})).status_code == 413
                assert not calls
                first = await client.post('/api/ppe/chat', json=body, headers=headers)
                assert first.status_code == 200, first.text
                result = first.json()
                assert result['kits'][0]['product_ids'] == [pid] and result['approved'] is False
                assert result['live_lookup']['sources'][0]['rows'][0]['concentration'] == '30%'
                followup = await client.post('/api/ppe/chat', json={**body, 'session_id': result['session_id'], 'message': '같은 작업이며 노출 시간은 10분입니다.'}, headers=headers)
                assert followup.status_code == 200 and followup.json()['session_id'] == result['session_id']
                assert len(calls[-1]['input']) == 3 and body['message'] in calls[-1]['input'][0]['content']
                mode[0] = 'missing'
                partial = await client.post('/api/ppe/chat', json={'message': '미상 혼합물입니다.'}, headers=headers)
                assert partial.status_code == 200 and partial.json()['kits'] == [] and partial.json()['questions']
                mode[0] = 'timeout'
                failed = await client.post('/api/ppe/chat', json=body, headers=headers)
                assert failed.status_code == 504 and 'private internal' not in failed.text
                assert failed.headers['access-control-allow-origin'] == settings.origins[0]
                mode[0] = 'unknown_id'
                invalid = await client.post('/api/ppe/chat', json=body, headers=headers)
                assert invalid.status_code == 502
                mode[0] = 'success'
                before_stop = len(calls)
                settings.stop_file.touch()
                assert (await client.post('/api/ppe/chat', json=body, headers=headers)).status_code == 503
                assert len(calls) == before_stop
                settings.stop_file.unlink()
                settings.daily_requests = 1
                assert (await client.post('/api/ppe/chat', json=body, headers=headers)).status_code == 429
                # A restart still observes the already-reserved budget/counters.
                ledger = server.UsageLedger(settings)
                try:
                    ledger.reserve(request=True)
                    raise AssertionError('Usage reset on restart')
                except server.PublicError as error:
                    assert error.status == 429
        assert not list(root.glob('*.json'))
    print('PASS: offline request → Responses payload → evidence → follow-up; missing input; timeout; invalid ID; authentication/origin/body limits; persistent quota; stop switch. Paid calls: 0.')


if __name__ == '__main__':
    asyncio.run(main())
