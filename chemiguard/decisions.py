import base64
import hashlib
import json
import math
import os
import time

import httpx

from .config import API_ENDPOINT, API_MODEL
from .vision import jpeg
from .wearing import PARTS, summarize_parts

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
VISIBLE_RULES = (
    'Inspect only the central tracked person in the first image. Detail crops show the same moment. '
    'Use the first person image for context; a detail crop can omit a visible body part. '
    'Ignore helpers and their limbs. Pose and crop labels do not establish visibility. '
    'Judge each target body region only to the extent directly visible from this camera viewpoint. '
    'covered: visible portions of this region are inside worn protective coverall fabric, with no visible uncovered segment. '
    'Do not require seeing the hidden side or the entire length of a limb. '
    'uncovered: a visible segment of the named region is outside the suit, showing skin or ordinary clothes. '
    'not_visible: the region cannot be seen due to viewpoint, occlusion or framing. '
    'uncertain: it is in view but blur, small size, ambiguous fabric or target association prevents judgment. '
    'For arms judge shoulder to wrist, not hands or gloves. Bare hands do not mean uncovered arms. '
    'For legs judge hip to ankle, not feet or boots. A bent limb is not uncovered merely because it is bent. '
    'Never infer a hidden limb from symmetry or label a hidden closure closed. '
    'Do not identify people or infer product model, protection level, internal fastening, leak tightness or safety.'
)


def questions_for(policy):
    visible = policy.get('wearing_assessment') == 'visible_regions'
    unknown_states = ('not_visible', 'uncertain') if visible else ('unobservable',)
    hidden_instruction = ('If hidden by viewpoint or occlusion choose not_visible; if visible but ambiguous choose uncertain.'
                          if visible else 'If hidden or ambiguous choose unobservable.')
    questions = [
        {'type': 'choice', 'name': name,
         'instructions': f'Which coverall coverage state is directly observable on the target\'s own {name.replace("_", " ")}?',
         'choices': [{'value': state} for state in ('covered', 'uncovered', *unknown_states)]}
        for name in PARTS
    ]
    if policy['hood_required']:
        hood_instruction = ('Is a protective hood worn around the target head? A face opening or respirator does not mean the hood is off. '
                            'Use the person image if the head detail is cut off. A visibly bare crown means uncovered. ' + hidden_instruction
                            if visible else 'Is the protective hood worn over the target head? If hidden use unobservable.')
        questions.append({'type': 'choice', 'name': 'hood',
                          'instructions': hood_instruction,
                          'choices': [{'value': state} for state in ('covered', 'uncovered', *unknown_states)]})
    if policy['closure_required']:
        external = policy.get('closure_assessment') == 'external_appearance'
        instructions = 'Observe the garment closure at this specified location: ' + policy['closure_location'] + '. '
        if external:
            instructions += ('Judge visible external closure only. A visibly closed outer flap covering the zipper counts as closed; '
                             'do not require seeing the zipper underneath. Choose open for a visible opening, undone zipper, '
                             'or open required flap. This does not verify hidden fastening or leak tightness. '
                             + (hidden_instruction + ' ' if visible else
                                'If the external closure area itself is hidden or ambiguous choose unobservable. '))
        else:
            instructions += hidden_instruction + ' ' if visible else 'If its location is unknown or hidden choose unobservable. '
        questions.append({'type': 'choice', 'name': 'closure',
                          'instructions': instructions + 'Never assume a front zipper.',
                          'choices': [{'value': state} for state in ('closed', 'open', *unknown_states)]})
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
        fallback = 'uncertain' if 'uncertain' in expected[name] else 'unobservable'
        parsed[name] = chosen if margin >= 0.2 else fallback
        scores[name] = {'choice': chosen, 'margin': round(margin, 4), 'probabilities': probabilities}
    return parsed, scores


def observe(images, policy):
    start = time.monotonic()
    visible = policy.get('wearing_assessment') == 'visible_regions'
    result = {'backend': 'decisions', 'model': API_MODEL, 'wearing': 'UNKNOWN', 'parts': {},
              'processing_state': 'ERROR', 'raw_result': None, 'usage': None,
              'prompt_version': 'ppe-observation-v4' if visible else 'ppe-observation-v3',
              'wearing_assessment': policy.get('wearing_assessment', 'all_required'),
              'closure_assessment': policy.get('closure_assessment', 'visible_components')}
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        return result | {'error': 'OPENAI_API_KEY 미설정', 'latency_ms': 0}
    questions = questions_for(policy)
    content = [{'type': 'input_text', 'text': VISIBLE_RULES if visible else RULES}]
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
            result.update(summarize_parts(parts, policy), parts=parts, choice_scores=scores,
                          processing_state='RUNNING', error=None)
    except httpx.TimeoutException:
        result['error'] = 'Decisions 응답 시간 초과'
    except httpx.HTTPError:
        result['error'] = 'Decisions 연결 실패'
    except (ValueError, KeyError, TypeError, AttributeError):
        result['error'] = 'Decisions 응답 형식 오류'
    result['latency_ms'] = round((time.monotonic() - start) * 1000, 1)
    return result
