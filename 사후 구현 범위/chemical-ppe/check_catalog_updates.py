"""Bounded offline checks of persistence, provenance and the recommendation gate."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile

import httpx
from jsonschema import validate, ValidationError
from catalog_admin import apply_report
from catalog_sources import Page, checked_url, now
from catalog_store import CatalogStore, BASELINE_PATH, public_data
import server


async def main():
    baseline_hash = hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        store = CatalogStore(root / 'catalog.sqlite3')
        baseline = store.catalog()
        assert len(baseline['products']) == 44
        for url in ('http://www.dupont.com/product', 'https://dupont.com.evil.test/',
                    'https://localhost/', 'https://user:pass@dupont.com/', 'https://dupont.com:8443/'):
            try:
                checked_url(url, 'DuPont')
                raise AssertionError('Untrusted URL accepted')
            except ValueError:
                pass
        title = 'Fixture Test Coverall'
        item = {'manufacturer': 'DuPont', 'model': 'FIXTURE 123', 'name': title,
                'category': 'chemical_protective_coverall', 'source_url': 'https://www.dupont.com/fixture',
                'category_evidence': 'chemical coverall'}
        async def fetcher(url, brand):
            if url.endswith('blocked'):
                raise ValueError('공식 페이지 HTTP 403; 접근 우회 없이 보류')
            text = 'FIXTURE 123 Fixture Test Coverall chemical coverall. ' + 'Official fixture. ' * 10
            return Page(brand, url, now(), text, hashlib.sha256(text.encode()).hexdigest(), [])
        report = {'products': [item], 'sources': [], 'search_notes': 'synthetic fixture'}
        first = await apply_report(store, report, fetcher)
        assert first['status'] == 'completed' and len(first['added']) == 1
        pid = first['added'][0]
        snapshot = store.catalog()
        product = next(p for p in snapshot['products'] if p['product_id'] == pid)
        assert product['discovery']['release_date'] is None
        assert product['chemical_suitability']['task_approval'] is False and not product['certifications']
        assert product['discovery']['recommendation_eligible'] is False
        assert all(p == baseline['products'][i] for i, p in enumerate(snapshot['products'][:44]))
        rerun = await apply_report(CatalogStore(store.path), report, fetcher)
        assert not rerun['added'] and not rerun['updated'] and len(store.catalog()['products']) == 45
        assert store.status()['revision'] == 2
        invalid = deepcopy(item)
        invalid['name'] = 'Invented model name'
        rejected = await apply_report(store, {'products': [invalid]}, fetcher)
        assert rejected['status'] == 'partial' and not rejected['added'] and rejected['failures']
        partial = await apply_report(store, {'products': [item], 'sources': [
            {'manufacturer': 'DuPont', 'source_url': 'https://www.dupont.com/blocked'}]}, fetcher)
        assert partial['status'] == 'partial' and partial['checked_sources'] and partial['failures']
        live_contract = server.make_contract(snapshot)
        answer = {'reply': '검토용 가상 응답', 'questions': [], 'candidates': [
            {'product_id': pid, 'selection_status': 'review_candidate', 'reason': 'fixture'}],
            'kits': [], 'source_ids': [], 'live_sources': []}
        try:
            validate(answer, server.answer_schema(live_contract))
            raise AssertionError('Unreviewed discovery became a recommendation')
        except ValidationError:
            pass
        assert pid in live_contract.instructions()  # Identity can still be discussed.
        settings = server.Settings('offline-key', 'gpt-6-luna', 'offline-demo-code-12345',
            ['http://localhost:34402'], True, 30, 30, 3_000_000, 5000, root/'usage.db', root/'STOP')
        app = server.create_app(settings)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=settings.origins[0]) as client:
            response = await client.get('/api/ppe/catalog')
            assert response.status_code == 200
            assert response.json()['catalog_meta']['product_count'] == 45
            assert 'preview_path' not in response.text and 'media_url' not in response.text
            assert response.headers['cache-control'] == 'no-store'
            assert (await client.get('/api/ppe/catalog/status')).json()['last_run']['status'] == 'partial'
        with store.connect() as db:
            assert db.execute('SELECT count(*) FROM history WHERE product_id=?', (pid,)).fetchone()[0] == 1
    assert hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest() == baseline_hash
    print('PASS: persistent 44→45 catalog, duplicate prevention, source evidence rejection, partial failure, original baseline preservation, discovery excluded from recommendations, sanitized live API. External/paid calls: 0.')


if __name__ == '__main__':
    asyncio.run(main())
