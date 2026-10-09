"""Bounded read-only probe: sequential, parallel and combined Decisions requests.

Uses a private manifest like compare_product_decisions.py. Never applies results
to the monitor or mutates the registration. Outputs contain private evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx

from chemiguard import decisions, product_decisions
from chemiguard.config import API_ENDPOINT, API_MODEL
from chemiguard.wearing import summarize_parts
from compare_product_decisions import append_image, read_image


def combined(images, policy, catalog):
    started = time.perf_counter()
    content = [{'type': 'input_text', 'text': decisions.VISIBLE_RULES if
                policy.get('wearing_assessment') == 'visible_regions' else decisions.RULES}]
    metadata = []
    for name in ('person', 'torso', 'legs', 'head'):
        if name in images:
            append_image(content, metadata,
                         f'Image: {name}. Same observation; region label does not establish visibility.', images[name], name)
    content.append({'type': 'input_text', 'text': product_decisions.RULES})
    target, target_meta = product_decisions.image_input(images['identity_torso'], 'OBSERVED TARGET torso. Same central person and moment.')
    content.extend(target)
    metadata.append(target_meta)
    content.extend(catalog['content'])
    metadata.extend(catalog['image_inputs'])
    questions = decisions.questions_for(policy, True) + [product_decisions.product_question(catalog)]
    payload = json.dumps({'model': API_MODEL, 'input': [{'role': 'user', 'content': content}],
                          'questions': questions}, separators=(',', ':')).encode()
    result = {'error': None, 'image_inputs': metadata, 'request_sha256': hashlib.sha256(payload).hexdigest(),
              'request_bytes': len(payload), 'api_called': True}
    try:
        response = httpx.post(API_ENDPOINT, content=payload, timeout=httpx.Timeout(5, connect=3),
                              headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'],
                                       'Content-Type': 'application/json'})
        result.update(http_status=response.status_code, request_id=response.headers.get('x-request-id'))
        if response.status_code != 200:
            result['error'] = f'HTTP {response.status_code}'
        else:
            result['raw_result'] = response.json()
            parts, scores = decisions.parse_answers(result['raw_result'], questions)
            choice = parts.pop('product_membership')
            color = parts.pop('garment_color')
            result.update(parts=parts, garment_color=color, choice_scores=scores,
                          membership='candidate' if choice in catalog['aliases'] else choice,
                          candidate=catalog['aliases'].get(choice), usage=result['raw_result'].get('usage'),
                          **summarize_parts(parts, policy))
    except httpx.HTTPError as exc:
        result['error'] = type(exc).__name__
    except (ValueError, KeyError, TypeError, AttributeError):
        result['error'] = 'invalid_response'
    result['latency_ms'] = round((time.perf_counter()-started)*1000, 1)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cases', nargs='+', required=True)
    args = parser.parse_args()
    if not os.getenv('OPENAI_API_KEY', '').strip():
        parser.error('OPENAI_API_KEY is required')
    manifest = json.loads(args.manifest.read_bytes())
    cases = [case for case in manifest['cases'] if case['id'] in args.cases]
    if not 1 <= len(cases) <= 6 or len(cases) != len(args.cases):
        parser.error('Choose 1-6 unique existing cases')
    catalog = product_decisions.prepare_catalog(manifest['references'], manifest['site_products'])
    if catalog['error']:
        parser.error(catalog['error'])
    args.output.mkdir(parents=True, exist_ok=False)
    jobs = [(case, mode) for case in cases for mode in ('sequential', 'parallel', 'combined')]
    random.Random(20261009).shuffle(jobs)
    rows = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for case, mode in jobs:
            images = {name: read_image(path) for name, path in case['context'].items()}
            images['identity_torso'] = read_image(case['query'])
            started = time.perf_counter()
            if mode == 'combined':
                ppe = product = combined(images, manifest['policy'], catalog)
                ppe_ready = ppe['latency_ms']
            elif mode == 'parallel':
                ppe_future = pool.submit(decisions.observe, images, manifest['policy'], True)
                product_future = pool.submit(product_decisions.observe_product, images, catalog)
                ppe = ppe_future.result()
                ppe_ready = (time.perf_counter()-started)*1000
                product = product_future.result()
            else:
                ppe = decisions.observe(images, manifest['policy'], True)
                ppe_ready = (time.perf_counter()-started)*1000
                # All modes perform both tasks, even on absent torso, for a fair timing comparison.
                product = product_decisions.observe_product(images, catalog)
            elapsed = (time.perf_counter()-started)*1000
            gate = product_decisions.gate(ppe)
            results = [ppe] if mode == 'combined' else [ppe, product]
            row = {'case_id': case['id'], 'mode': mode, 'completed_at': datetime.now(timezone.utc).isoformat(),
                   'wall_ms': round(elapsed, 1), 'ppe_ready_ms': round(ppe_ready, 1),
                   'ppe': ppe, 'product': product if mode != 'combined' else None,
                   'gate': gate, 'effective_membership': gate[0] if gate else product.get('membership'),
                   'raw_membership': product.get('membership'),
                   'input_tokens': sum((r.get('usage') or {}).get('input_tokens', 0) for r in results),
                   'errors': [r['error'] for r in results if r.get('error')]}
            rows.append(row)
            with (args.output/'results.jsonl').open('a') as out:
                out.write(json.dumps(row, ensure_ascii=False)+'\n')
            print(json.dumps({k: row[k] for k in ('case_id', 'mode', 'wall_ms', 'ppe_ready_ms',
                                                 'raw_membership', 'effective_membership', 'errors')} |
                             {'torso': ppe.get('parts', {}).get('torso'),
                              'candidate': (product.get('candidate') or {}).get('product_id')}, ensure_ascii=False), flush=True)
    summary = {'version': 'decision-routing-probe-v1', 'product_version': product_decisions.VERSION,
               'manifest_sha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
               'api_calls': len(cases)*5, 'catalog': catalog['aliases'],
               'note': 'Small paired development sample; not an accuracy benchmark or latency guarantee.',
               'modes': {mode: {key: {'median': statistics.median([r[key] for r in rows if r['mode'] == mode]),
                                     'min': min(r[key] for r in rows if r['mode'] == mode),
                                     'max': max(r[key] for r in rows if r['mode'] == mode)}
                               for key in ('wall_ms', 'ppe_ready_ms', 'input_tokens')}
                         for mode in ('sequential', 'parallel', 'combined')},
               'errors': sum(len(r['errors']) for r in rows)}
    (args.output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary['modes'], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
