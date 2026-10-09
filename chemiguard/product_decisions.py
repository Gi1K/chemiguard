"""Product-only Decisions requests. Reference people never enter the PPE request."""
import base64
import hashlib
import json
import os
import time

import cv2
import httpx

from .config import API_ENDPOINT, API_MODEL, DATA
from .decisions import IMAGE_DETAIL, parse_answers
from .products import product_profile
from .vision import observation_image

VERSION = 'product-decisions-site-standard-v2'
RULES = (
    'Classify only the coverall WORN on the central OBSERVED TARGET torso into the registered SITE STANDARDS. '
    'References are catalog examples, NOT observations of the target. Never classify a helper, '
    'a helper sleeve across the target, a held garment, or a garment lowered below the torso. '
    'Use the target person image for ownership and the target torso crop for visible fabric details. '
    'This site standardizes one representative garment per color. Use dominant fabric color and general '
    'protective-coverall form, not exact brand, texture, seams, flap layout or SKU. Similar white coveralls '
    'belong to the same registered white standard even if their real manufacturer/model differs. '
    'Ignore background, pose, gloves, respirator, shoes and wearer identity. Allow lighting shadows. '
    'A reference ID means a SITE STANDARD ASSIGNMENT only, not physical product identification, '
    'chemical protection or safety. Never infer protection from color. '
    'none means visible color or general garment form outside ALL site standards. '
    'uncertain means insufficient pixels, occlusion, ambiguous color/form or ambiguous ownership, '
    'NOT inability to distinguish similar models of the same standardized color. '
    'no_coverall means ordinary clothes or skin clearly replace the worn coverall on the target torso. '
    'Do not force a reference ID. Do not infer hidden construction or chemical resistance.'
)


def image_input(image, label):
    encoded, extension = observation_image(image, 'torso')
    return ([{'type': 'input_text', 'text': label},
             {'type': 'input_image', 'detail': IMAGE_DETAIL,
              'image_url': 'data:image/jpeg;base64,' + base64.b64encode(encoded).decode('ascii')}],
            {'label': label, 'width': image.shape[1], 'height': image.shape[0], 'bytes': len(encoded),
             'sha256': hashlib.sha256(encoded).hexdigest(), 'format': extension})


def prepare_catalog(references, registrations):
    active = sorted({row['product_id'] for row in registrations if row['enabled']})
    catalog = {'content': [], 'image_inputs': [], 'aliases': {}, 'error': None}
    for index, product_id in enumerate(active):
        alias = f'R{index+1}'
        photos = sorted([r for r in references if r['product_id'] == product_id
                         and r.get('reference_kind') == 'product_photo' and r.get('region') == 'torso'],
                        key=lambda r: r['id'])
        if not photos:
            catalog['error'] = '활성 제품 참고 사진 부족'
            break
        catalog['aliases'][alias] = {'product_id': product_id, 'product': product_profile(product_id),
                                    'name': (product_profile(product_id) or {}).get('family') or photos[0]['product_name'],
                                    'designation_basis': 'site_standard_color_and_form',
                                    'registered_colors': sorted({r['color'] for r in registrations if r['enabled'] and r['product_id'] == product_id}),
                                    'reference_url': photos[0]['crop_url'], 'reference_ids': [r['id'] for r in photos]}
        for photo in photos:
            path = (DATA / photo['crop_url'].removeprefix('/media/')).resolve()
            if not path.is_relative_to((DATA/'references').resolve()):
                catalog['error'] = '참고 사진 경로 오류'
                break
            image = cv2.imread(str(path))
            if image is None:
                catalog['error'] = '참고 사진 읽기 실패'
                break
            colors = ', '.join(catalog['aliases'][alias]['registered_colors'])
            content, metadata = image_input(image, f'REGISTERED REFERENCE {alias}. Site standard colors: {colors}. Catalog only, NOT the target.')
            catalog['content'].extend(content)
            catalog['image_inputs'].append(metadata | {'reference_id': photo['id'], 'alias': alias})
    if len(catalog['image_inputs']) > 24:
        catalog['error'] = '제품 비교 사진 상한 24장 초과'
    return catalog


def gate(ppe):
    if ppe.get('error'):
        return 'uncertain', '착용 관찰 오류 · 제품 판정 보류'
    if ppe.get('parts', {}).get('torso') == 'uncovered':
        return 'no_coverall', '몸통 미착용 관찰 우선 · 제품 판정 제외'
    if ppe.get('parts', {}).get('torso') != 'covered':
        return 'uncertain', '몸통 착용 근거 부족 · 제품 판정 보류'
    return None


def apply_ppe_gate(ppe, decision):
    blocked = gate(ppe)
    if not blocked:
        return decision
    return decision | {'raw_membership': decision.get('membership'), 'raw_candidate': decision.get('candidate'),
                       'membership': blocked[0], 'candidate': None, 'reason': blocked[1],
                       'ppe_gate': True}


def timed_observe_product(images, catalog):
    started = time.monotonic()
    result = observe_product(images, catalog)
    return result | {'started_monotonic': started, 'completed_monotonic': time.monotonic()}


def product_question(catalog):
    return {'type': 'choice', 'name': 'product_membership',
            'instructions': 'Which registered SITE STANDARD color and coverall form matches the target torso? '
            'Similar white products share the white standard; do not require exact product identity. '
            'Choose none for a color/form outside all standards, uncertain for insufficient visible evidence, '
            'no_coverall for a visibly absent torso coverall. Helpers and references are not the target.',
            'choices': [{'value': value} for value in (*catalog['aliases'], 'none', 'uncertain', 'no_coverall')]}


def observe_product(images, catalog):
    started = time.monotonic()
    result = {'version': VERSION, 'backend': 'decisions', 'model': API_MODEL, 'membership': 'uncertain',
              'candidate': None, 'error': None, 'api_called': False, 'image_inputs': [], 'timings_ms': {},
              'alias_products': {alias: row['product_id'] for alias, row in catalog['aliases'].items()}}
    if catalog['error'] or not catalog['aliases']:
        return result | {'error': catalog['error'] or '활성 등록 제품 없음', 'latency_ms': 0}
    if not os.getenv('OPENAI_API_KEY', '').strip():
        return result | {'error': 'OPENAI_API_KEY 미설정', 'latency_ms': 0}
    query = images.get('identity_torso')
    if query is None or images.get('person') is None:
        return result | {'reason': '비교 가능한 동일 대상 몸통 부족', 'latency_ms': 0}
    content = [{'type': 'input_text', 'text': RULES}]
    for name, image in (('person', images['person']), ('torso', query)):
        parts, metadata = image_input(image, f'OBSERVED TARGET {name}. Same central person and moment.')
        content.extend(parts)
        result['image_inputs'].append(metadata)
    content.extend(catalog['content'])
    result['image_inputs'].extend(catalog['image_inputs'])
    questions = [product_question(catalog)]
    payload = json.dumps({'model': API_MODEL, 'input': [{'role': 'user', 'content': content}],
                          'questions': questions}, separators=(',', ':')).encode()
    result.update(request_sha256=hashlib.sha256(payload).hexdigest(), request_bytes=len(payload))
    result['timings_ms']['input_encoding'] = round((time.monotonic()-started)*1000, 1)
    if len(payload) > 12_000_000:
        return result | {'error': '제품 비교 요청 크기 초과', 'latency_ms': 0}
    request_start = time.monotonic()
    try:
        result['api_called'] = True
        response = httpx.post(API_ENDPOINT, content=payload, timeout=httpx.Timeout(5, connect=3),
                              headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'],
                                       'Content-Type': 'application/json'})
        result['timings_ms']['api_roundtrip'] = round((time.monotonic()-request_start)*1000, 1)
        result.update(http_status=response.status_code, request_id=response.headers.get('x-request-id'))
        if response.status_code != 200:
            result['error'] = f'제품 Decisions API HTTP {response.status_code}'
        else:
            result['raw_result'] = response.json()
            result['usage'] = result['raw_result'].get('usage')
            parsed, scores = parse_answers(result['raw_result'], questions)
            choice = parsed['product_membership']
            result['choice_scores'] = scores
            result['membership'] = 'candidate' if choice in catalog['aliases'] else choice
            result['candidate'] = catalog['aliases'].get(choice)
    except httpx.TimeoutException:
        result['error'] = '제품 Decisions 응답 시간 초과'
    except httpx.HTTPError:
        result['error'] = '제품 Decisions 연결 실패'
    except (ValueError, KeyError, TypeError, AttributeError):
        result['error'] = '제품 Decisions 응답 형식 오류'
    if result['error']:
        result.update(membership='uncertain', candidate=None)
    result['timings_ms'].setdefault('api_roundtrip', round((time.monotonic()-request_start)*1000, 1))
    result['latency_ms'] = round((time.monotonic()-started)*1000, 1)
    return result
