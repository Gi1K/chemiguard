import base64
import hashlib
import json
import math
import os
import time

import httpx

from .config import API_ENDPOINT, API_MODEL
from .vision import jpeg

PARTS = ('torso', 'left_arm', 'right_arm', 'left_leg', 'right_leg')
PART_NAMES = {'torso': '몸통', 'left_arm': '왼팔', 'right_arm': '오른팔', 'left_leg': '왼다리', 'right_leg': '오른다리'}
RULES = (
    'Inspect only the central tracked person in the first image. All detail crops show the same moment. '
    'Ignore helpers, other people, equipment and background. Crop labels and pose estimates do not prove visibility. '
    'Observe whether each body region is visibly inside a protective coverall. '
    'covered: the region and its garment coverage are directly distinguishable. '
    'uncovered: exposed skin or ordinary clothing clearly establishes missing coverall coverage, '
    'including a shirt above a suit at the waist, an arm removed from a sleeve, carrying or removing the suit. '
    'unobservable: hidden, cropped, small, blurred or ambiguous. Occlusion alone is not a violation. '
    'For an arm, upper arm and forearm must be distinguishable for covered; for a leg, thigh and lower leg. '
    'A directly exposed segment suffices for uncovered. Trace each distinct target limb independently; '
    'do not infer a hidden far-side limb from symmetry. Hands, gloves, feet, boots, head and hood are separate. '
    'Do not identify people or infer product model, chemical resistance, certification, chemical type or safety.'
)


def questions_for(policy):
    questions = [
        {'type': 'choice', 'name': name,
         'instructions': f'Which coverall coverage state is directly observable on the target\'s own {name.replace("_", " ")}?',
         'choices': [{'value': state} for state in ('covered', 'uncovered', 'unobservable')]}
        for name in PARTS
    ]
    if policy['hood_required']:
        questions.append({'type': 'choice', 'name': 'hood', 'instructions': 'Is the protective hood worn over the target head? If hidden use unobservable.',
                          'choices': [{'value': state} for state in ('covered', 'uncovered', 'unobservable')]})
    if policy['closure_required']:
        questions.append({'type': 'choice', 'name': 'closure',
                          'instructions': 'Observe the garment closure at this specified location: ' + policy['closure_location'] + '. '
                          'If its location is unknown or hidden choose unobservable. Never assume a front zipper.',
                          'choices': [{'value': state} for state in ('closed', 'open', 'unobservable')]})
    return questions


def parse_answers(data, questions):
    answers = data.get('answers')
    if not isinstance(answers, list) or len(answers) != len(questions):
        raise ValueError('질문 수와 응답 수 불일치')
    expected = {question['name']: {choice['value'] for choice in question['choices']} for question in questions}
    if len({answer.get('name') for answer in answers}) != len(expected):
        raise ValueError('응답 이름 중복')
    parsed, scores = {}, {}
    for answer in answers:
        name = answer.get('name')
        if name not in expected or answer.get('type') != 'choice' or answer.get('choice') not in expected[name]:
            raise ValueError('거절 또는 잘못된 선택 응답')
        probabilities = answer.get('probabilities', [])
        if len(probabilities) != len(expected[name]) or {p.get('value') for p in probabilities} != expected[name]:
            raise ValueError('선택 점수 형식 불일치')
        values = [p.get('probability') for p in probabilities]
        if any(not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1 for value in values):
            raise ValueError('잘못된 선택 점수')
        if abs(sum(values) - 1) > 0.02:
            raise ValueError('선택 점수 합계 오류')
        distribution = {p['value']: p['probability'] for p in probabilities}
        chosen = answer['choice']
        margin = distribution[chosen] - max(value for key, value in distribution.items() if key != chosen)
        parsed[name] = chosen if margin >= 0.2 else 'unobservable'
        scores[name] = {'choice': chosen, 'margin': round(margin, 4), 'probabilities': probabilities}
    return parsed, scores


def observe(images, policy):
    start = time.monotonic()
    result = {'backend': 'decisions', 'model': API_MODEL, 'wearing': 'UNKNOWN', 'parts': {},
              'processing_state': 'ERROR', 'raw_result': None, 'usage': None}
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        return result | {'error': 'OPENAI_API_KEY 미설정', 'latency_ms': 0}
    questions = questions_for(policy)
    content = [{'type': 'input_text', 'text': RULES}]
    for name in ('person', 'torso', 'legs', 'head'):
        if name not in images or (name == 'head' and not policy['hood_required']):
            continue
        content.extend([
            {'type': 'input_text', 'text': f'Image: {name}. Same observation; region label does not establish visibility.'},
            {'type': 'input_image', 'image_url': 'data:image/jpeg;base64,' + base64.b64encode(jpeg(images[name])).decode('ascii')},
        ])
    body = {'model': API_MODEL, 'input': [{'role': 'user', 'content': content}], 'questions': questions}
    payload = json.dumps(body, separators=(',', ':')).encode()
    result['request_sha256'] = hashlib.sha256(payload).hexdigest()
    try:
        response = httpx.post(API_ENDPOINT, content=payload, timeout=httpx.Timeout(5, connect=3),
                              headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        result['http_status'] = response.status_code
        result['request_id'] = response.headers.get('x-request-id')
        if response.status_code != 200:
            result['error'] = f'Decisions API HTTP {response.status_code}'
        else:
            data = response.json()
            result['raw_result'] = data
            result['usage'] = data.get('usage')
            parts, scores = parse_answers(data, questions)
            uncovered = [name for name in PARTS if parts[name] == 'uncovered']
            wearing = 'NOT_WORN' if uncovered else 'WORN' if all(parts[name] == 'covered' for name in PARTS) else 'UNKNOWN'
            violations = [PART_NAMES[name] + ' 미착용 관찰' for name in uncovered]
            if policy['hood_required'] and parts.get('hood') == 'uncovered':
                violations.append('필수 후드 미착용')
            if policy['closure_required'] and parts.get('closure') == 'open':
                violations.append('필수 여밈 열림')
            unknown = [PART_NAMES.get(name, {'hood': '후드', 'closure': '여밈'}.get(name, name))
                       for name, state in parts.items() if state == 'unobservable']
            result.update(parts=parts, choice_scores=scores, wearing=wearing, violations=violations,
                          reason=' · '.join(violations) if violations else '확인 불가: ' + ', '.join(unknown) if unknown else '필수 부위 착용 관찰',
                          processing_state='RUNNING', review_required=bool(unknown), error=None)
    except httpx.TimeoutException:
        result['error'] = 'Decisions 응답 시간 초과'
    except httpx.HTTPError:
        result['error'] = 'Decisions 연결 실패'
    except (ValueError, KeyError, TypeError, AttributeError):
        result['error'] = 'Decisions 응답 형식 오류'
    result['latency_ms'] = round((time.monotonic() - start) * 1000, 1)
    return result
