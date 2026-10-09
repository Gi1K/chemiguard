"""Manufacturer facts are separate from visual candidates and work approval."""
import copy
import numpy as np


PRODUCTS = {
    'P11': {'name': 'Tychem 4000 S CHZ5', 'family': 'Tychem 4000 S', 'model_code': 'SLCHZ5TWH00',
            'types': ['3-B', '4-B', '5-B', '6-B'],
            'source_url': 'https://www.dupont.co.uk/products/tychem-4000-s-slchz5twh00.html'},
    'P04': {'name': 'Tychem 6000 F CHA5', 'family': 'Tychem 6000 F', 'model_code': 'TFCHA5TGY00',
            'types': ['3-B', '4-B', '5-B', '6-B'],
            'source_url': 'https://www.dupont.co.uk/products/tychem-6000-f-tfcha5tgy00.html'},
    'P12': {'name': 'Tyvek 500 Xpert CHF5', 'family': 'Tyvek 500 Xpert', 'model_code': 'TYCHF5SWHXP / TYCHF5SWHXB',
            'types': ['5-B', '6-B'],
            'source_url': 'https://www.dupont.co.uk/products/tyvek-500-xpert-tychf5swhxp-tychf5swhxb.html'},
}

PURPOSES = {'acid': '내산', 'alkali': '내염기', 'acid_alkali': '내산·내염기', 'other': '기타'}


def site_product_slot(row):
    if row.get('registration_mode') == 'color':
        return ('color', row['color'])
    return ('purpose_type', row['purpose'], row['protection_type'])


def current_site_products(rows):
    latest = {}
    for row in sorted(rows, key=lambda item: item['revision']):
        latest[site_product_slot(row)] = row
    return list(latest.values())


def product_profile(product_id):
    row = PRODUCTS.get(product_id)
    if row is None:
        return None
    # All three pages report these fabric penetration/repellency tests, not safe wear times.
    return copy.deepcopy(row) | {
        'product_id': product_id, 'manufacturer': 'DuPont', 'verified_on': '2026-10-09',
        'source_title': 'DuPont SafeSPEC 제조사 제품 자료', 'revision': 1,
        'chemical_tests': [
            {'category': '산', 'chemical': '황산', 'concentration': '30%',
             'method': 'EN ISO 6530', 'penetration': '<1%', 'repellency': '>95%'},
            {'category': '염기', 'chemical': '수산화나트륨', 'concentration': '10%',
             'method': 'EN ISO 6530', 'penetration': '<1%', 'repellency': '>95%'},
        ],
        'limitation': '원단 침투·반발 시험. 투과 파과시간·안전 착용시간·모든 산/염기 내성을 뜻하지 않음.',
        'suitability': 'NOT_ASSESSED', 'suitability_reason': '작업 조건 미입력 · 적합성 미판정',
    }


def rank_references(vector, references, model_hash, site_products=None):
    vector = np.asarray(vector, dtype=np.float32)
    assignments = [row for row in site_products or [] if row['enabled']]
    allowed = {row['product_id'] for row in assignments}
    products = {}
    for reference in references:
        if (reference.get('reference_kind') != 'product_photo'
                or reference.get('model_sha256') != model_hash or reference.get('region') != 'torso'):
            continue
        embedding = np.asarray(reference.get('embedding', []), dtype=np.float32)
        if embedding.shape != vector.shape or not np.isfinite(embedding).all():
            continue
        score = float(np.clip(np.dot(vector, embedding), -1, 1))
        product = products.setdefault(reference['product_id'], {
            'product_id': reference['product_id'], 'name': reference['product_name'], 'matches': []})
        product['matches'].append({'score': score, 'reference_id': reference['id'],
                                   'reference_url': reference['crop_url'], 'view': reference['view']})
    candidates = []
    for product in products.values():
        matches = sorted(product.pop('matches'), key=lambda row: row['score'], reverse=True)
        product.update(score=float(np.mean([row['score'] for row in matches[:2]])),
                       reference_count=len(matches), reference_url=matches[0]['reference_url'],
                       best_reference_id=matches[0]['reference_id'], best_view=matches[0]['view'],
                       supporting_references=matches[:2], product=product_profile(product['product_id']))
        if product['product']:
            product['name'] = product['product']['family'] + ' 계열'
        product['site_assignments'] = [row | {'purpose_label': PURPOSES.get(row.get('purpose'), '용도 미지정')}
                                       for row in assignments if row['product_id'] == product['product_id']]
        candidates.append(product)
    candidates.sort(key=lambda row: row['score'], reverse=True)
    outside = next((row for row in candidates if row['product_id'] not in allowed), None) if site_products else None
    if site_products:
        candidates = [row for row in candidates if row['product_id'] in allowed]
    gap = candidates[0]['score'] - candidates[1]['score'] if len(candidates) > 1 else None
    # Review-only heuristic, never a calibrated model-identification threshold.
    ambiguous = gap is None or gap < 0.03
    return {'state': 'CANDIDATE' if candidates else 'UNAVAILABLE', 'candidates': candidates[:3],
            'product_count': len(candidates), 'reference_count': sum(row['reference_count'] for row in candidates),
            'gap': gap, 'ambiguous': ambiguous, 'review_gap_threshold': 0.03,
            'score_kind': 'cosine_top2_mean', 'model': 'siglip2-base-patch16-384',
            'outside_candidate': outside,
            'outside_gap': outside['score']-candidates[0]['score'] if outside and candidates else None,
            'comparison_scope': 'site_registered' if site_products else 'reference_library',
            'reason': ('계열 구분 보류' if ambiguous else '계열 후보 · 제품 미확정') if candidates else '비교 가능한 제품 사진 없음',
            'suitability': 'NOT_ASSESSED'}
