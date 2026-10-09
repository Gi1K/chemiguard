"""Local scheduling and evidence selection, independent of API classifications."""

import math

import cv2
import numpy as np

from .wearing import POSITIVE_STATES, VIOLATION_PARTS

WINDOW_SECONDS = 0.8
SCHEDULE = {'first': 0, 'confirm': 1, 'violation': 2, 'worn': 3, 'unknown': 2,
            'change': 1, 'error_max': 10}
OBSERVATION_CROP_VERSION = 'partial-person-crops-v1'


def observation_size_ok(height, width):
    # Partial shoulders/torso at the frame edge can still establish a visible violation.
    return min(height, width) >= 32 and height * width >= 2048


def image_quality(image, box, shape, confidence):
    if image is None or not observation_size_ok(*image.shape[:2]) or confidence < 0.45:
        return None
    gray = cv2.cvtColor(cv2.resize(image, (64, 128)), cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    height, width = shape[:2]
    clipped = sum((box[0] <= 1, box[1] <= 1, box[2] >= width-1, box[3] >= height-1))
    score = min(math.log1p(sharpness)/8, 1) + min(image.shape[0]/500, 1) + confidence - clipped*0.15
    return {'score': round(score, 4), 'sharpness': round(sharpness, 2),
            'clipped_edges': clipped, 'signature': gray,
            'width': image.shape[1], 'height': image.shape[0], 'gate_version': OBSERVATION_CROP_VERSION}


def request_due(track, captured, signature):
    elapsed = captured-track['last_requested']
    result = track.get('result') or {}
    if track['pending'] or captured-track.get('last_attempt', 0) < 0.8:
        return None
    if not track['last_requested']:
        return 'new_track'
    if result.get('error'):
        interval = min(SCHEDULE['error_max'], 2 ** min(track.get('errors', 1), 4))
        return 'error_retry' if elapsed >= interval else None
    previous = track.get('requested_signature')
    if previous is not None and elapsed >= SCHEDULE['change']:
        difference = float(np.abs(signature.astype(np.float32)-previous.astype(np.float32)).mean()/255)
        if difference >= 0.16:
            return 'appearance_change'
    wearing = result.get('wearing', 'UNKNOWN')
    if wearing in (*POSITIVE_STATES, 'NOT_WORN') and not track.get('confirmed'):
        interval, reason = SCHEDULE['confirm'], 'state_confirmation'
    elif track.get('active_violations'):
        interval, reason = SCHEDULE['violation'], 'unresolved_violation'
    elif wearing in POSITIVE_STATES:
        interval, reason = SCHEDULE['worn'], 'stable_worn'
    elif wearing == 'NOT_WORN':
        interval, reason = SCHEDULE['violation'], 'continuing_violation'
    else:
        interval, reason = SCHEDULE['unknown'], 'visibility_recheck'
    return reason if elapsed >= interval else None


def face_quality(body):
    if body is None or 'head' not in body['images']:
        return {'score': 0, 'method': 'no_associated_head', 'face_keypoints': [], 'visibility_proxy': 0}
    image = body['images']['head']
    info = body['head_region']
    height, width = image.shape[:2]
    scale = min(1, 160 / max(height, width))
    size = (max(1, round(width*scale)), max(1, round(height*scale)))
    gray = cv2.cvtColor(cv2.resize(image, size), cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    visibility = info['landmark_confidence']
    # Landmarks are only a visibility proxy, not an occlusion or PPE classifier.
    score = (min(math.log1p(sharpness)/8, 1) + min(min(width, height)/160, 1)
             + visibility - info['clipped_edges']*0.25) if info['face_keypoints'] else 0
    return {**info, 'score': round(max(0, score), 4), 'sharpness': round(sharpness, 2),
            'width': width, 'height': height, 'visibility_proxy': visibility}


def eligible_candidates(candidates, captured, last_observed):
    return [row for row in candidates if 0 <= captured-row['captured'] <= WINDOW_SECONDS
            and row['captured'] > last_observed]


def select_candidate(candidates, captured, last_observed, prefer_face=False):
    eligible = eligible_candidates(candidates, captured, last_observed)
    # Rank only image quality and recency, never the predicted clothing state.
    return max(eligible, key=lambda row: row['quality']['score']
               + (row.get('face_quality', {}).get('score', 0) if prefer_face else 0)
               - (captured-row['captured'])*0.5, default=None)


def combine_observation(track, result, observed, observation_id, ttl, consensus_window):
    visible_mode = result.get('wearing_assessment') == 'visible_regions'
    violations = set(result.get('violations', []))
    usable = not result.get('error') and (bool(violations) or
        result['wearing'] in POSITIVE_STATES and not result.get('review_required'))
    history = track['history']
    if (result.get('error') or not visible_mode and not usable or
            history and (observed <= history[-1]['time'] or observed-history[-1]['time'] > ttl)):
        history.clear()
    if usable or visible_mode and not result.get('error'):
        history.append({'violations': sorted(violations), 'wearing': result['wearing'],
                        'parts': result.get('parts', {}).copy(),
                        'time': observed, 'observation_id': observation_id})
        history[:] = history[-2:]
    consecutive = len(history) == 2 and history[-1]['time']-history[0]['time'] <= consensus_window
    sustained = violations.intersection(history[0]['violations']) if consecutive else set()
    confirmed = consecutive and (bool(sustained) or
        all(row['wearing'] in POSITIVE_STATES and not row['violations'] for row in history))
    track['confirmed'] = confirmed
    track['complete_confirmed'] = consecutive and all(row['wearing'] == 'WORN' for row in history)
    previous = set(track['active_violations'])
    new_violations = sustained-previous if confirmed else set()
    cleared = set()
    if visible_mode and consecutive:
        # Recovery must observe the exact previously violated part, never just another view.
        cleared = {violation for violation in previous if violation in VIOLATION_PARTS and
                   all(row['parts'].get(VIOLATION_PARTS[violation]) ==
                       ('closed' if VIOLATION_PARTS[violation] == 'closure' else 'covered') for row in history)}
    elif not visible_mode and confirmed and result['wearing'] == 'WORN':
        cleared = previous
    track['active_violations'] = sorted((previous | new_violations)-cleared)
    return {'usable': usable, 'new_violations': sorted(new_violations), 'cleared': bool(cleared),
            'cleared_violations': sorted(cleared),
            'supporting_observation_ids': [row['observation_id'] for row in history]}
