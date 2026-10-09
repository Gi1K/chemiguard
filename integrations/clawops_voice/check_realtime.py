"""Live OpenAI-only loopback check. No ClawOps connection or telephone call.

Uses the production phone session and existing server key. Generated test audio
is fed back as synthetic input in memory; this does not test a human microphone.
"""
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from chemiguard.phone_alerts import PHONE_MODEL, PhoneSettings
from chemiguard.phone_transport import OpenAIOnlySession


async def wait_for_responses(session, count):
    async with asyncio.timeout(25):
        while session.evidence['completed_responses'] < count:
            if session.failure.is_set():
                raise RuntimeError(session.failure_code)
            await asyncio.sleep(.05)


async def check():
    logging.disable(logging.CRITICAL)
    settings = PhoneSettings.load()
    if not settings.openai_key:
        raise RuntimeError('openai_key_missing')
    session = OpenAIOnlySession(
        api_key=settings.openai_key, model=PHONE_MODEL, voice='marin', language='ko',
        greeting=False, system_prompt='한국어 음성 연결 시험이다. 첫 요청에는 연결 시험입니다라고 짧게 말한다. '
        '이후 사용자가 말하면 음성이 전달됐습니다라고 한 문장으로 답한다.')
    result = {'started_at': datetime.now(timezone.utc).isoformat(),
              'test': 'synthetic_audio_loopback', 'key_source': 'production_phone_settings',
              'telephone_call': False, 'recorded_audio': False}
    try:
        await session.prewarm()
        await session._connection.conversation.item.create(item={
            'type': 'message', 'role': 'user',
            'content': [{'type': 'input_text', 'text': '연결 시험입니다라고 말하세요.'}]})
        await session._connection.response.create()
        await wait_for_responses(session, 1)
        audio = b''.join(session._call.drain_buffer())
        if not audio:
            raise RuntimeError('no_generated_audio')
        result['synthetic_input_speech_bytes'] = len(audio)
        # Telephone codec is G.711 mu-law, 8 kHz: 160 bytes per 20 ms frame.
        timestamp = 0
        for offset in range(0, len(audio), 160):
            await session.feed_audio(audio[offset:offset+160], timestamp)
            timestamp += 20
            await asyncio.sleep(.02)
        for _ in range(75):
            await session.feed_audio(b'\xff' * 160, timestamp)
            timestamp += 20
            await asyncio.sleep(.02)
        await wait_for_responses(session, 2)
        result['passed'] = bool(session.evidence['session_updated_at'] and session.evidence['speech_turns'] > 0)
    except Exception as error:
        result['passed'] = False
        result['error_type'] = type(error).__name__
    finally:
        await session.stop()
        result['realtime'] = dict(session.evidence)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination = ROOT / '.data' / f'realtime-check-{stamp}.json'
    destination.parent.mkdir(exist_ok=True)
    with destination.open('x', encoding='utf-8') as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write('\n')
    print(json.dumps(result, ensure_ascii=False))
    print(f'Evidence: {destination}')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(check()))
