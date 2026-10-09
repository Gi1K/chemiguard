"""Focused offline check: untrusted photos cannot bypass label confirmation."""
import asyncio
import base64
from io import BytesIO
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import httpx
from PIL import Image
import server
from photo_inputs import prepare_photos, MAX_PHOTO_BODY


def fixture_photo():
    # Synthetic pixels, not a user's photo. Metadata must not leave the server.
    output = BytesIO()
    photo = Image.new('RGB', (40, 30), 'white')
    exif = Image.Exif()
    exif[270] = 'private fixture metadata'
    photo.save(output, format='JPEG', exif=exif)
    return 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode()


async def main():
    original = fixture_photo()
    clean = prepare_photos([original])[0]
    with Image.open(BytesIO(base64.b64decode(clean.split(',')[1]))) as image:
        assert not image.getexif() and image.format == 'JPEG'
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        settings = server.Settings('offline-key', 'gpt-6-luna', 'offline-demo-code-12345',
            ['http://localhost:34402'], True, 30, 30, 3_000_000, 5000,
            root / 'usage.db', root / 'STOP', backend='agents')
        app = server.create_app(settings)
        counselor = app.state.counselor
        calls, mode = [], ['readable']
        reading = {'status': 'partial', 'visible_text': '제품명: TEST CLEANER\n성분: 읽기 어려움',
                   'uncertainty': '성분 글자가 선명하지 않아요.'}

        async def generate(**kwargs):
            calls.append(kwargs)
            if kwargs.get('images'):
                assert kwargs['images'] == [clean]
                return reading if mode[0] == 'readable' else {
                    'status': 'unreadable', 'visible_text': '', 'uncertainty': '흐린 사진이에요.'}
            assert 'TEST CLEANER' not in json.dumps(kwargs['messages'], ensure_ascii=False)
            if 'cas_numbers' in kwargs['schema']['properties']:
                return {'cas_numbers': []}
            assert kwargs['schema']['properties']['questions']['maxItems'] == 1
            return {'reply': '담당자에게 안전보건자료를 요청할 수 있어요.',
                    'questions': ['제품을 구매한 담당자가 누구인지 알고 계신가요?'],
                    'candidates': [], 'kits': [], 'source_ids': [], 'live_sources': []}

        headers = {'Authorization': 'Bearer ' + settings.demo_token, 'Origin': settings.origins[0]}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=settings.origins[0]) as client:
            with patch.object(counselor.agents, 'generate', generate), patch.object(
                    server.lookup_module, 'lookup_chemicals', side_effect=AssertionError('Unknown substance was queried')):
                for photos in ([original] * 3, ['https://example.com/image.jpg'],
                               ['data:image/jpeg;base64,YmFk'], [original.replace('jpeg', 'png')]):
                    result = await client.post('/api/ppe/chat', headers=headers, json={'photos': photos})
                    assert result.status_code == 400, result.text
                huge = await client.post('/api/ppe/chat', headers=headers,
                    content=b'x' * (MAX_PHOTO_BODY + 1))
                assert huge.status_code == 415  # Must be JSON before considering its size.
                huge = await client.post('/api/ppe/chat', headers={**headers, 'Content-Type': 'application/json'},
                    content=b'x' * (MAX_PHOTO_BODY + 1))
                assert huge.status_code == 413
                assert not calls

                result = await client.post('/api/ppe/chat', headers=headers, json={'photos': [original]})
                assert result.status_code == 200, result.text
                photo_answer = result.json()
                sid = photo_answer['session_id']
                review_id = photo_answer['photo_reading']['review_id']
                assert photo_answer['candidates'] == photo_answer['kits'] == []
                assert photo_answer['approved'] is False and len(calls) == 1
                assert 'data:image' not in json.dumps(counselor.sessions)
                assert 'TEST CLEANER' not in json.dumps(counselor.sessions[sid]['history'])

                # Ordinary questions do not silently accept the pending OCR text.
                followup = await client.post('/api/ppe/chat', headers=headers,
                    json={'session_id': sid, 'message': '글자를 직접 고칠 수 있나요?'})
                assert followup.status_code == 200 and counselor.sessions[sid]['pending_photo']
                before = len(calls)
                payload = {'session_id': sid, 'message': '확인했어요.',
                    'photo_confirmation': {'review_id': '0' * 36, 'text': '제품명: CORRECTED CLEANER'}}
                assert (await client.post('/api/ppe/chat', headers=headers, json=payload)).status_code == 409
                assert len(calls) == before
                payload['photo_confirmation']['review_id'] = review_id
                confirmed = await client.post('/api/ppe/chat', headers=headers, json=payload)
                assert confirmed.status_code == 200, confirmed.text
                assert 'CORRECTED CLEANER' in calls[-2]['messages'][-1]['content']
                assert 'CORRECTED CLEANER' in calls[-1]['messages'][-1]['content']
                assert counselor.sessions[sid]['pending_photo'] is None
                assert (await client.post('/api/ppe/chat', headers=headers, json=payload)).status_code == 409

                mode[0] = 'unreadable'
                unreadable = await client.post('/api/ppe/chat', headers=headers, json={'photos': [original]})
                assert unreadable.status_code == 200
                assert unreadable.json()['photo_reading']['review_id'] is None
                assert unreadable.json()['candidates'] == unreadable.json()['kits'] == []
        assert {path.name for path in root.iterdir()} == {'usage.db', 'catalog.sqlite3'}
    print('PASS: image-only input; real image validation; metadata removed; no OCR/pixels in conversation before confirmation; corrected text used; expired confirmation rejected; unreadable photo has no recommendations. Paid calls: 0.')


if __name__ == '__main__':
    asyncio.run(main())
