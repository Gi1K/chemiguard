"""Read-only, opt-in product comparison probe; never updates monitoring state.

Usage: PYTHONPATH=. .venv/bin/python scripts/compare_product_decisions.py \
    --manifest .data/product-comparison/manifest.json --output .data/product-comparison/run-1
The private manifest contains cases (query, optional context image paths), frozen
references, site_products, policy, and product_order. API calls send images only,
not case names, expected labels, filenames, catalog model names, or source titles.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import time
from datetime import datetime, timezone

import cv2
import httpx
import torch

from chemiguard.config import API_ENDPOINT, API_MODEL, DEVICE
from chemiguard.decisions import (IMAGE_DETAIL, RULES, VISIBLE_RULES, observe,
                                 parse_answers, questions_for)
from chemiguard.vision import identity, observation_image

VERSION = 'reference-membership-probe-v1'
MEMBERSHIP_RULES = (
    'Compare the observed target coverall with the REGISTERED REFERENCE pictures. '
    'Reference pictures are NOT observations of the target and must never answer PPE wearing questions. '
    'Different reference views with the same ID belong to one registered family. '
    'Compare visible fabric color, texture, construction and seam/flap layout; ignore wearer identity, '
    'pose, background, gloves, boots and respirator. Do not read model identity from a brand logo. '
    'Allow lighting shadows, viewpoint changes and minor variants within the same visual family. '
    'A registered ID means a visual family candidate, not exact SKU, chemical resistance or safety. '
    'Matching white color alone is not sufficient to distinguish similar white families. '
    'Choose none when a worn coverall has visible distinguishing differences from ALL references. '
    'Choose uncertain when the garment is hidden, blurred, too small, or several families remain '
    'visually plausible; absence of evidence is not evidence of none. '
    'Choose no_coverall only if ordinary clothes or bare skin clearly replace the coverall '
    'on the observed torso, including a suit removed down to the waist.'
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_image(path):
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f'Unreadable input image: {path}')
    return image


def append_image(content, metadata, label, image, region='torso'):
    encoded, extension = observation_image(image, region)
    mime = 'image/png' if extension == 'png' else 'image/jpeg'
    metadata.append({'label': label, 'sha256': digest(encoded), 'bytes': len(encoded),
                     'width': image.shape[1], 'height': image.shape[0], 'mime': mime})
    content.extend([
        {'type': 'input_text', 'text': label},
        {'type': 'input_image', 'detail': IMAGE_DETAIL,
         'image_url': f'data:{mime};base64,' + base64.b64encode(encoded).decode('ascii')},
    ])


def compare_decisions(query, reference_images, aliases, policy, context=None):
    start = time.perf_counter()
    content, metadata = [], []
    questions = []
    if context:
        rules = VISIBLE_RULES if policy.get('wearing_assessment') == 'visible_regions' else RULES
        content.append({'type': 'input_text', 'text': rules})
        for name in ('person', 'torso', 'legs', 'head'):
            if name in context:
                append_image(content, metadata, f'OBSERVED TARGET: {name}. Same person and moment.',
                             context[name], name)
        questions = questions_for(policy, product_check=True)
    content.append({'type': 'input_text', 'text': MEMBERSHIP_RULES})
    append_image(content, metadata, 'OBSERVED TARGET: torso to compare.', query)
    for alias, image in reference_images:
        append_image(content, metadata, f'REGISTERED REFERENCE {alias}. Catalog only, NOT the target.', image)
    questions.append({'type': 'choice', 'name': 'product_membership',
                      'instructions': 'Which registered visual family matches the OBSERVED TARGET? '
                      'Use none for visible mismatch with all, uncertain for insufficient evidence, '
                      'and no_coverall for clearly absent torso coverall. Do not force a registered ID.',
                      'choices': [{'value': value} for value in (*aliases, 'none', 'uncertain', 'no_coverall')]})
    payload = json.dumps({'model': API_MODEL, 'input': [{'role': 'user', 'content': content}],
                          'questions': questions}, separators=(',', ':')).encode()
    result = {'prompt_version': VERSION, 'model': API_MODEL, 'request_sha256': digest(payload),
              'request_bytes': len(payload), 'image_inputs': metadata, 'error': None,
              'timings_ms': {'input_encoding': (time.perf_counter()-start)*1000}}
    network_start = time.perf_counter()
    try:
        # Match production's one-shot HTTP transport and timeout; no hidden retries.
        response = httpx.post(API_ENDPOINT, content=payload, timeout=httpx.Timeout(5, connect=3),
                              headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'],
                                       'Content-Type': 'application/json'})
        result['timings_ms']['api_roundtrip'] = (time.perf_counter()-network_start)*1000
        result.update(http_status=response.status_code, request_id=response.headers.get('x-request-id'))
        if response.status_code == 200:
            result['raw_result'] = response.json()
            result['usage'] = result['raw_result'].get('usage')
            result['selected'], result['choice_scores'] = parse_answers(result['raw_result'], questions)
        else:
            result['error'] = f'HTTP {response.status_code}'
    except httpx.TimeoutException:
        result['error'] = 'timeout'
    except httpx.HTTPError:
        result['error'] = 'connection_error'
    except (ValueError, KeyError, TypeError, AttributeError):
        result['error'] = 'invalid_response'
    result['timings_ms'].setdefault('api_roundtrip', (time.perf_counter()-network_start)*1000)
    result['latency_ms'] = (time.perf_counter()-start)*1000
    return result


def stats(values):
    return {'n': len(values), 'min': min(values), 'median': statistics.median(values),
            'mean': statistics.mean(values), 'max': max(values)} if values else {'n': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=2, choices=(1, 2, 3))
    args = parser.parse_args()
    if not os.getenv('OPENAI_API_KEY', '').strip():
        parser.error('OPENAI_API_KEY is required; configure the existing environment locally.')
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not manifest['cases'] or len(manifest['cases']) > 20:
        parser.error('Use 1-20 cases for this bounded probe.')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'manifest.json').write_bytes(manifest_bytes)
    aliases = {f'R{i+1}': product for i, product in enumerate(manifest['product_order'])}
    reference_images = [(alias, read_image(row['image_path'])) for alias, product in aliases.items()
                        for row in manifest['references'] if row['product_id'] == product
                        and row.get('reference_kind') == 'product_photo']
    if not all(any(a == alias for a, _ in reference_images) for alias in aliases):
        parser.error('Each candidate requires a reference photo.')
    queries = {row['id']: read_image(row['query']) for row in manifest['cases']}
    contexts = {row['id']: {name: read_image(path) for name, path in row.get('context', {}).items()}
                for row in manifest['cases']}
    jobs = [(row, trial) for trial in range(args.repeats) for row in manifest['cases']]
    random.Random(20261009).shuffle(jobs)
    run = {'version': VERSION, 'started_at': datetime.now(timezone.utc).isoformat(),
           'manifest_sha256': digest(manifest_bytes), 'aliases': aliases, 'repeats': args.repeats,
           'device': DEVICE, 'gpu': torch.cuda.get_device_name() if DEVICE.startswith('cuda') else None,
           'case_order': [(row['id'], trial) for row, trial in jobs],
           'api_call_budget': len(jobs) + 2 * args.repeats * sum(bool(r.get('combined')) for r in manifest['cases'])}
    start = time.perf_counter()
    identity.load()
    run['siglip_model_load_ms'] = (time.perf_counter()-start)*1000
    start = time.perf_counter()
    identity.search(next(iter(queries.values())), manifest['references'], manifest['site_products'])
    run['siglip_first_inference_ms'] = (time.perf_counter()-start)*1000
    run['siglip_model_sha256'] = identity.model_hash
    rows = []

    def record(row):
        rows.append(row)
        with (args.output / 'results.jsonl').open('a') as output:
            output.write(json.dumps(row, ensure_ascii=False) + '\n')
        info = {key: row[key] for key in ('case_id', 'trial', 'mode', 'latency_ms')}
        info['selected'] = row.get('selected')
        info['error'] = row.get('error')
        if row['mode'] == 'siglip':
            info['top'] = [(x['product_id'], round(x['score'], 4)) for x in row['matching']['candidates']]
            info['outside_gap'] = row['matching']['outside_gap']
        print(json.dumps(info, ensure_ascii=False), flush=True)

    for case, trial in jobs:
        query = queries[case['id']]
        common = {'case_id': case['id'], 'trial': trial}
        start = time.perf_counter()
        matching = identity.search(query, manifest['references'], manifest['site_products'])
        record(common | {'mode': 'siglip', 'latency_ms': (time.perf_counter()-start)*1000, 'matching': matching})
        record(common | {'mode': 'membership'} | compare_decisions(query, reference_images, aliases, manifest['policy']))
        if case.get('combined'):
            # Alternate order to reduce consistently favoring the first network request.
            modes = ('baseline', 'combined') if trial % 2 == 0 else ('combined', 'baseline')
            for mode in modes:
                result = (observe(contexts[case['id']], manifest['policy'], product_check=True) if mode == 'baseline'
                          else compare_decisions(query, reference_images, aliases, manifest['policy'], contexts[case['id']]))
                record(common | {'mode': mode} | result)
    run['finished_at'] = datetime.now(timezone.utc).isoformat()
    run['timings_ms'] = {mode: stats([r['latency_ms'] for r in rows if r['mode'] == mode and not r.get('error')])
                         for mode in ('siglip', 'membership', 'baseline', 'combined')}
    run['errors'] = [{k: r.get(k) for k in ('case_id', 'trial', 'mode', 'error')}
                     for r in rows if r.get('error')]
    (args.output / 'summary.json').write_text(json.dumps(run, ensure_ascii=False, indent=2))
    print(json.dumps(run, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
