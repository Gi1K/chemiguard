"""Visual mismatch evidence is independent of PPE coverage and chemical suitability."""

VERSION = 'registered-suit-mismatch-v1'
COLOR_NAMES = {'white': '흰색', 'gray': '회색', 'yellow': '노랑', 'orange': '주황',
               'green': '초록', 'blue': '파랑', 'black': '검정', 'other': '기타 색상'}
OUTSIDE_GAP = 0.03


def assess_product(color, matching, registrations, error=None):
    active = [row for row in registrations if row['enabled']]
    colors = sorted({row['color'] for row in active})
    signals = {key: {'state': 'unknown'} for key in ('color', 'product')}
    result = {'version': VERSION, 'observed_color': color, 'registered_colors': colors,
              'signals': signals, 'identity': matching, 'suitability': 'NOT_ASSESSED',
              'outside_gap_threshold': OUTSIDE_GAP}
    if not registrations:
        return result | {'state': 'DISABLED', 'reason': '현장 대표 제품 미등록'}
    if error or not active:
        return result | {'state': 'UNKNOWN', 'reason': '제품 관찰 오류' if error else '활성 등록 제품 없음'}
    if color in COLOR_NAMES:
        if color not in colors:
            signals['color'] = {'state': 'mismatch', 'reason': '등록 외 색상·무늬 관찰' if color == 'other'
                               else f'미등록 색상 {COLOR_NAMES[color]} 관찰'}
        else:
            signals['color'] = {'state': 'clear', 'reason': '등록 색상 범위 · 제품 일치 보증 아님'}
    outside = matching.get('outside_candidate') if matching else None
    gap = matching.get('outside_gap') if matching else None
    if outside and gap is not None and color != 'no_coverall':
        if gap >= OUTSIDE_GAP:
            signals['product'] = {'state': 'mismatch', 'reason': f'등록 외 {outside["name"]} 사진이 더 유사',
                                  'product_id': outside['product_id']}
        elif gap <= -OUTSIDE_GAP:
            signals['product'] = {'state': 'clear', 'reason': '등록 후보 우세 · 제품 일치 보증 아님'}
    reasons = [row['reason'] for row in signals.values() if row['state'] == 'mismatch']
    state = 'MISMATCH' if reasons else 'INCONCLUSIVE' if any(row['state'] == 'unknown' for row in signals.values()) else 'NO_MISMATCH_EVIDENCE'
    reason = ' · '.join(reasons) if reasons else ('제품 구분 보류 · 확인 필요' if state == 'INCONCLUSIVE'
                                                else '불일치 근거 없음 · 제품 미확정')
    return result | {'state': state, 'reason': reason}


def combine_product_check(track, check, observed, observation_id, ttl=5.0):
    history = track.setdefault('product_history', [])
    active = track.setdefault('product_alerts', {})
    if history and (observed <= history[-1]['time'] or observed-history[-1]['time'] > ttl):
        history.clear()
    history.append({'time': observed, 'observation_id': observation_id, 'signals': check['signals']})
    history[:] = history[-2:]
    new, cleared = [], []
    if len(history) == 2:
        for key, signal in check['signals'].items():
            states = [row['signals'][key]['state'] for row in history]
            if states == ['mismatch', 'mismatch'] and key not in active:
                active[key] = signal['reason']
                new.append(key)
            elif states == ['clear', 'clear'] and key in active:
                del active[key]
                cleared.append(key)
    check.update(active_alerts=dict(active), confirmed=bool(active))
    return {'new_alerts': new, 'cleared_alerts': cleared, 'active_alerts': dict(active),
            'supporting_observation_ids': [row['observation_id'] for row in history]}
