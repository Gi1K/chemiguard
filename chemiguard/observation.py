"""Local scheduling and evidence selection, independent of API classifications."""

import math

import cv2
import numpy as np

WINDOW_SECONDS = 0.8
SCHEDULE = {'first': 0, 'confirm': 1, 'violation': 2, 'worn': 3, 'unknown': 2,
            'change': 1, 'error_max': 10}


def image_quality(image, box, shape, confidence):
    if image is None or image.shape[0] < 100 or image.shape[1] < 35 or confidence < 0.45:
        return None
    gray = cv2.cvtColor(cv2.resize(image, (64, 128)), cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    height, width = shape[:2]
    clipped = sum((box[0] <= 1, box[1] <= 1, box[2] >= width-1, box[3] >= height-1))
    score = min(math.log1p(sharpness)/8, 1) + min(image.shape[0]/500, 1) + confidence - clipped*0.15
    return {'score': round(score, 4), 'sharpness': round(sharpness, 2),
            'clipped_edges': clipped, 'signature': gray}


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
    if wearing in ('WORN', 'NOT_WORN') and not track.get('confirmed'):
        interval, reason = SCHEDULE['confirm'], 'state_confirmation'
    elif wearing == 'WORN':
        interval, reason = SCHEDULE['worn'], 'stable_worn'
    elif wearing == 'NOT_WORN':
        interval, reason = SCHEDULE['violation'], 'continuing_violation'
    else:
        interval, reason = SCHEDULE['unknown'], 'visibility_recheck'
    return reason if elapsed >= interval else None


def select_candidate(candidates, captured, last_observed):
    eligible = [row for row in candidates if 0 <= captured-row['captured'] <= WINDOW_SECONDS
                and row['captured'] > last_observed]
    # Rank only image quality and recency, never the predicted clothing state.
    return max(eligible, key=lambda row: row['quality']['score'] - (captured-row['captured'])*0.5, default=None)


def combine_observation(track, result, observed, observation_id, ttl, consensus_window):
    violations = set(result.get('violations', []))
    usable = not result.get('error') and (bool(violations) or
        result['wearing'] == 'WORN' and not result.get('review_required'))
    history = track['history']
    if not usable or history and observed-history[-1]['time'] > ttl:
        history.clear()
    if usable:
        history.append({'violations': sorted(violations), 'wearing': result['wearing'],
                        'time': observed, 'observation_id': observation_id})
        history[:] = history[-2:]
    sustained = violations.intersection(history[0]['violations']) if len(history) == 2 else set()
    confirmed = len(history) == 2 and history[-1]['time']-history[0]['time'] <= consensus_window and (
        bool(sustained) or all(row['wearing'] == 'WORN' and not row['violations'] for row in history))
    track['confirmed'] = confirmed
    previous = set(track['active_violations'])
    new_violations = sustained-previous if confirmed else set()
    cleared = bool(previous) and confirmed and result['wearing'] == 'WORN'
    if sustained and confirmed:
        track['active_violations'] = sorted(previous | sustained)
    elif cleared:
        track['active_violations'] = []
    return {'usable': usable, 'new_violations': sorted(new_violations), 'cleared': cleared,
            'supporting_observation_ids': [row['observation_id'] for row in history]}
