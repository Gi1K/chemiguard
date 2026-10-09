"""Separate visible garment observations from complete required-part coverage."""

PARTS = ('torso', 'left_arm', 'right_arm', 'left_leg', 'right_leg')
PART_NAMES = {'torso': '몸통', 'left_arm': '왼팔', 'right_arm': '오른팔',
              'left_leg': '왼다리', 'right_leg': '오른다리', 'hood': '후드', 'closure': '여밈'}
VIOLATION_PARTS = {PART_NAMES[name] + ' 미착용 관찰': name for name in PARTS} | {
    '필수 후드 미착용': 'hood', '필수 여밈 열림': 'closure'}
POSITIVE_STATES = ('WORN', 'VISIBLE_WORN')


def summarize_parts(parts, policy):
    required = list(PARTS)
    if policy['hood_required']:
        required.append('hood')
    if policy['closure_required']:
        required.append('closure')
    visible_mode = policy.get('wearing_assessment') == 'visible_regions'
    observed = [name for name in required if parts.get(name) in ('covered', 'closed')]
    hidden = [name for name in required if parts.get(name) == 'not_visible']
    uncertain = [name for name in required if parts.get(name) in (None, 'uncertain', 'unobservable')]
    violations = [label for label, name in VIOLATION_PARTS.items()
                  if name in required and parts.get(name) == ('open' if name == 'closure' else 'uncovered')]
    complete = len(observed) == len(required)
    # A hood or a small isolated sleeve alone cannot establish a worn coverall.
    sufficient = parts.get('torso') == 'covered' and any(parts.get(name) == 'covered' for name in PARTS[1:])
    wearing = ('NOT_WORN' if violations else 'WORN' if complete else
               'VISIBLE_WORN' if visible_mode and sufficient and not uncertain else 'UNKNOWN')
    if violations:
        reason = ' · '.join(violations)
    elif wearing == 'WORN':
        reason = '필수 부위 착용 관찰'
    elif wearing == 'VISIBLE_WORN':
        reason = '보이는 범위 착용 · 미확인: ' + ', '.join(PART_NAMES[name] for name in hidden)
    elif uncertain or hidden:
        reason = '확인 불가: ' + ', '.join(PART_NAMES[name] for name in required if name in uncertain or name in hidden)
    else:
        reason = '보호복 착용을 확인할 영상 근거 부족'
    return {'wearing': wearing, 'violations': violations, 'reason': reason,
            'observed_parts': observed, 'unobserved_parts': hidden, 'uncertain_parts': uncertain,
            'all_required_observed': complete,
            'review_required': wearing == 'UNKNOWN' if visible_mode else bool(uncertain or hidden)}
