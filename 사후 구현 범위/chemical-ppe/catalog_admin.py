"""Local maintenance CLI. No web write endpoint; never edits the prework files."""
import argparse
import asyncio
from dataclasses import asdict
import fcntl
import json
from pathlib import Path
import sys

import httpx
from catalog_sources import WATCH, checked_url, compact, fetch_page, now, verified_product
from catalog_store import CatalogStore, ROOT, public_data


async def apply_report(store, report, fetcher=fetch_page):
    if not isinstance(report, dict) or set(report) - {'sources', 'products', 'search_notes'}:
        raise ValueError('sources, products, search_notes로 실행 결과를 입력하세요.')
    sources, products = report.get('sources', []), report.get('products', [])
    if not isinstance(sources, list) or not isinstance(products, list) or len(products) > 10:
        raise ValueError('한 번에 신규 제품 최대 10개를 반영합니다.')
    if not isinstance(report.get('search_notes', ''), str):
        raise ValueError('search_notes는 짧은 실행 설명이어야 합니다.')
    requests = {}
    for source in sources + products:
        if not isinstance(source, dict):
            raise ValueError('제조사와 출처 URL이 필요합니다.')
        brand = source.get('manufacturer', '')
        url = checked_url(source.get('source_url', ''), brand)
        requests[(brand, url)] = None
    if not 1 <= len(requests) <= WATCH['max_pages_per_run']:
        raise ValueError(f"실제 확인할 페이지는 1~{WATCH['max_pages_per_run']}개여야 합니다.")
    started = now()
    failures, pages, verified = [], [], []
    for brand, url in requests:
        try:
            page = await fetcher(url, brand)
            requests[(brand, url)] = page
            pages.append(page)
        except (ValueError, httpx.HTTPError) as error:
            # No headers, request body, credentials or HTML in the public report.
            reason = str(error) if isinstance(error, ValueError) else type(error).__name__
            failures.append({'url': url, 'manufacturer': brand, 'reason': reason[:250]})
    seen = set()
    for item in products:
        key = (item['manufacturer'], checked_url(item['source_url'], item['manufacturer']))
        page = requests[key]
        if not page:
            continue
        try:
            clean = verified_product(item, page)
            identity = (compact(clean['manufacturer']), compact(clean['model']))
            if identity in seen:
                continue
            seen.add(identity)
            verified.append((clean, page))
        except ValueError as error:
            failures.append({'url': key[1], 'manufacturer': key[0], 'reason': str(error)[:250]})
    return store.apply(verified, pages, failures, started, report.get('search_notes', ''))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT / '.runtime/catalog.sqlite3')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    commands.add_parser('export')
    commands.add_parser('watchlist')
    inspect = commands.add_parser('inspect-url')
    inspect.add_argument('manufacturer')
    inspect.add_argument('url')
    inspect.add_argument('--model', default='')
    apply = commands.add_parser('apply')
    apply.add_argument('--input', required=True, type=Path)
    schedule = commands.add_parser('set-schedule')
    schedule.add_argument('--automation-id', required=True)
    history = commands.add_parser('history')
    history.add_argument('product_id')
    args = parser.parse_args()
    store = CatalogStore(args.db)
    if args.command == 'status':
        result = store.status()
    elif args.command == 'export':
        result = public_data(store.catalog())
    elif args.command == 'watchlist':
        result = WATCH
    elif args.command == 'inspect-url':
        page = asyncio.run(fetch_page(args.url, args.manufacturer))
        result = asdict(page)
        if args.model:
            index = compact(page.text).find(compact(args.model))
            result['text'] = compact(page.text)[max(0,index-300):max(0,index)+1700] if index >= 0 else '모델 문자열 없음'
        else:
            result['text'] = page.text[:2400]
        result['links'] = page.links[:100]
    elif args.command == 'apply':
        if args.input.stat().st_size > 64_000:
            raise ValueError('관리 입력 파일은 64KB까지 허용합니다.')
        with store.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = asyncio.run(apply_report(store, json.loads(args.input.read_text())))
    elif args.command == 'set-schedule':
        store.set_schedule(args.automation_id)
        result = store.status()
    else:
        with store.connect() as db:
            result = [dict(r) for r in db.execute('SELECT * FROM history WHERE product_id=? ORDER BY seq', (args.product_id,))]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == 'apply' and result['status'] != 'completed':
        return 2
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except BlockingIOError:
        print('다른 제품 수집이 진행 중입니다. 중복 실행하지 않습니다.', file=sys.stderr)
        sys.exit(3)
    except (ValueError, httpx.HTTPError) as error:
        print(str(error) if isinstance(error, ValueError) else type(error).__name__, file=sys.stderr)
        sys.exit(1)
