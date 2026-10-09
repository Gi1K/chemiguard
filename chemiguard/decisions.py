import base64
import hashlib
import json
import math
import os
import time

import httpx

from .config import API_ENDPOINT, API_MODEL
from .vision import observation_image
from .wearing import PARTS, summarize_parts

IMAGE_DETAIL = 'original'
INPUT_VERSION = 'original-crops-lossless-head-v1'
PPE_SELECTION_VERSION = 'ppe-top1-v1'
PPE_QUESTIONS = frozenset((*PARTS, 'hood', 'closure', 'respirator'))

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


def questions_for(policy, product_check=False):
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

    if policy.get('respirator_required', False):
        questions.append({'type': 'choice', 'name': 'respirator',
                          'instructions': (
                              'Independently from the hood, is a full-face respirator visibly worn on the target face? '
                              'For this question covered means a worn full-face respirator facepiece with a visor '
                              'covering the eyes and a connected facepiece over the nose and mouth. '
                              'A half-face respirator plus goggles, face shield alone, hood alone, '
                              'ordinary glasses or disposable mask does not satisfy this full-face requirement. '
                              'Choose uncovered only when a visible face region clearly shows the full-face respirator '
                              'is absent, lifted, hanging, or not covering that region. '
                              'Do not mistake a transparent respirator visor with visible eyes for absence. '
                              'Use the person image for context when the head crop is incomplete. '
                              'Do not require a frontal view if the visible profile establishes the worn facepiece. '
                              'Do not infer presence or absence from a rear-facing hood or hidden face. '
                              + hidden_instruction + ' If the visible equipment type cannot be distinguished, choose '
                              + ('uncertain. ' if visible else 'unobservable. ')
                              + 'Observe external wearing only, not cartridge suitability, certification, fit, '
                              'seal, breathing-air supply or chemical protection.'),
                          'choices': [{'value': state} for state in ('covered', 'uncovered', *unknown_states)]})
    if product_check:
        questions.append({'type': 'choice', 'name': 'garment_color', 'instructions': (
            'What is the dominant fabric color of the protective coverall WORN by the central target? '
            'Ignore skin, gloves, respirator, boots, logos, seams, helpers and background. '
            'Use the visible torso and limbs; white fabric in local shadows remains white. '
            'Use gray only if the material itself is distinguishably gray. '
            'Choose no_coverall if no protective coverall is visibly worn, not_visible if the fabric is hidden, '
            'other includes clearly multicolored/patterned fabric (such as camouflage) or an unlisted color; '
            'uncertain is for ambiguous lighting, blur or insufficient pixels. '
            'Do not infer the color from a brand, product model or expected registration.'),
            'choices': [{'value': value} for value in ('white', 'gray', 'yellow', 'orange', 'green',
                        'blue', 'black', 'other', 'no_coverall', 'not_visible', 'uncertain')]})
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
        top_probability = max(distribution.values())
        leaders = [value for value, probability in distribution.items() if probability == top_probability]
        tied = len(leaders) != 1
        if name in PPE_QUESTIONS:
            parsed[name] = fallback if tied else leaders[0]
            method = PPE_SELECTION_VERSION
        else:
            parsed[name] = chosen if margin >= 0.2 else fallback
            method = 'choice-margin-0.2'
        scores[name] = {'choice': chosen, 'margin': round(margin, 4), 'probabilities': probabilities,
                        'selected': parsed[name], 'selection_method': method, 'top_tied': tied}
    return parsed, scores


def observe(images, policy, product_check=False):
    start = time.monotonic()
    visible = policy.get('wearing_assessment') == 'visible_regions'
    respirator_required = policy.get('respirator_required', False)
    result = {'backend': 'decisions', 'model': API_MODEL, 'wearing': 'UNKNOWN', 'parts': {},
              'processing_state': 'ERROR', 'raw_result': None, 'usage': None,
              'prompt_version': 'ppe-observation-v5' if respirator_required else (
                  'ppe-observation-v4' if visible else 'ppe-observation-v3'),
              'respirator_assessment': 'full_face_external_appearance' if respirator_required else 'not_requested',
              'wearing_assessment': policy.get('wearing_assessment', 'all_required'),
              'closure_assessment': policy.get('closure_assessment', 'visible_components')}
    result.update(input_version=INPUT_VERSION, image_detail=IMAGE_DETAIL, image_inputs=[], timings_ms={},
                  ppe_selection_version=PPE_SELECTION_VERSION)
    if product_check:
        result.update(prompt_version='ppe-observation-v6-color', garment_color='uncertain')
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        return result | {'error': 'OPENAI_API_KEY 미설정', 'latency_ms': 0}
    questions = questions_for(policy, product_check)
    content = [{'type': 'input_text', 'text': VISIBLE_RULES if visible else RULES}]
    for name in ('person', 'torso', 'legs', 'head'):
        if name not in images or (name == 'head' and not (policy['hood_required'] or respirator_required)):
            continue
        encoded, extension = observation_image(images[name], name)
        mime = 'image/png' if extension == 'png' else 'image/jpeg'
        result['image_inputs'].append({'region': name, 'mime_type': mime, 'detail': IMAGE_DETAIL,
                                       'width': images[name].shape[1], 'height': images[name].shape[0],
                                       'bytes': len(encoded), 'sha256': hashlib.sha256(encoded).hexdigest()})
        content.extend([
            {'type': 'input_text', 'text': f'Image: {name}. Same observation; region label does not establish visibility.'},
            {'type': 'input_image', 'detail': IMAGE_DETAIL,
             'image_url': f'data:{mime};base64,' + base64.b64encode(encoded).decode('ascii')},
        ])
    body = {'model': API_MODEL, 'input': [{'role': 'user', 'content': content}], 'questions': questions}
    payload = json.dumps(body, separators=(',', ':')).encode()
    result['request_sha256'] = hashlib.sha256(payload).hexdigest()
    result['request_bytes'] = len(payload)
    result['timings_ms']['input_encoding'] = round((time.monotonic()-start)*1000, 1)
    request_start = time.monotonic()
    try:
        response = httpx.post(API_ENDPOINT, content=payload, timeout=httpx.Timeout(5, connect=3),
                              headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        result['timings_ms']['api_roundtrip'] = round((time.monotonic()-request_start)*1000, 1)
        parse_start = time.monotonic()
        result['http_status'] = response.status_code
        result['request_id'] = response.headers.get('x-request-id')
        if response.status_code != 200:
            result['error'] = f'Decisions API HTTP {response.status_code}'
        else:
            data = response.json()
            result['raw_result'] = data
            result['usage'] = data.get('usage')
            parts, scores = parse_answers(data, questions)
            if product_check:
                result['garment_color'] = parts.pop('garment_color')
            result.update(summarize_parts(parts, policy), parts=parts, choice_scores=scores,
                          processing_state='RUNNING', error=None)
        result['timings_ms']['response_processing'] = round((time.monotonic()-parse_start)*1000, 1)
    except httpx.TimeoutException:
        result['error'] = 'Decisions 응답 시간 초과'
    except httpx.HTTPError:
        result['error'] = 'Decisions 연결 실패'
    except (ValueError, KeyError, TypeError, AttributeError):
        result['error'] = 'Decisions 응답 형식 오류'
    if 'api_roundtrip' not in result['timings_ms']:
        result['timings_ms']['api_roundtrip'] = round((time.monotonic()-request_start)*1000, 1)
    result['latency_ms'] = round((time.monotonic() - start) * 1000, 1)
    return result
