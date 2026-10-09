"""Bounded offline check of public-origin authorization and private photo isolation."""

import asyncio
from pathlib import Path
import tempfile
from unittest.mock import patch

import httpx
import server


async def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        public_origin = 'https://catalog-preview-test.trycloudflare.com'
        private_origin = 'https://private.example.ts.net:9443'
        settings = server.Settings('offline-key', 'offline-model', 'offline-demo-code-12345',
            ['http://localhost:34402', private_origin], True, 30, 30, 10000, 100,
            root / 'usage.db', root / 'STOP')
        pid = 'TYCHEM_2000_YELLOW'
        photo_path = root / server.contract.products[pid]['images'][0]['preview_path']
        photo_path.parent.mkdir(parents=True, exist_ok=True)
        photo_path.write_bytes(b'private-fixture-not-for-public-delivery')
        with patch.dict(server.os.environ, {
            'PPE_LOCAL_PHOTOS_DIR': str(root),
            'PPE_TAILSCALE_ORIGIN': private_origin,
            'PPE_TAILSCALE_USER_LOGIN': 'private-fixture-user',
        }):
            app = server.create_app(settings)

        async def offline_chat(_body):
            return {'reply': 'offline route check; no model request'}

        state = root / '.runtime/public-preview/origin.txt'
        state.parent.mkdir(parents=True)
        state.write_text(public_origin + '\n')
        auth = {'Authorization': 'Bearer ' + settings.demo_token}
        public = {'Host': 'public-preview.invalid', 'Origin': public_origin}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 12345)),
                                     base_url='http://localhost:34402') as client:
            with patch.object(server, 'ROOT', root), patch.object(app.state.counselor, 'chat', offline_chat):
                assert (await client.get(f'/api/ppe/local-media/{pid}')).status_code == 200
                for extra in ({}, {'tailscale-user-login': 'private-fixture-user',
                                   'x-forwarded-host': 'private.example.ts.net:9443'}):
                    headers = {**public, **extra}
                    assert (await client.get('/api/ppe/status', headers=headers)).json()['local_photos'] == {}
                    assert (await client.get(f'/api/ppe/local-media/{pid}', headers=headers)).status_code == 404
                assert (await client.post('/api/ppe/chat', headers=public, json={})).status_code == 401
                assert (await client.post('/api/ppe/chat', headers={**public, **auth}, json={})).status_code == 200
                assert (await client.post('/api/ppe/chat', headers={**public, **auth, 'Origin': 'https://other.trycloudflare.com'}, json={})).status_code == 403
                assert (await client.post('/api/ppe/chat', headers={**public, **auth, 'Host': 'localhost:34402'}, json={})).status_code == 403
                state.unlink()
                assert (await client.post('/api/ppe/chat', headers={**public, **auth}, json={})).status_code == 403
                assert (await client.post('/api/ppe/chat', headers={**auth, 'Origin': settings.origins[0]}, json={})).status_code == 200
        print('Public origin, authentication, photo isolation, stopped tunnel, and local access checks passed; paid calls: 0.')


if __name__ == '__main__':
    asyncio.run(main())
