"""Import explicitly selected local PoC photos; never change the source manifests."""
import argparse
import json
from pathlib import Path

import cv2
import httpx

from chemiguard.vision import Vision, crop


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', action='append', type=Path, required=True)
    parser.add_argument('--assets', nargs='+', required=True)
    parser.add_argument('--server', default='http://127.0.0.1:8765')
    args = parser.parse_args()
    rows = {row['asset_id']: row for path in args.manifest for row in json.loads(path.read_text())}
    selected = [rows[key] for key in args.assets]
    with httpx.Client(base_url=args.server, timeout=120) as client:
        active = client.get('/api/runs/active').raise_for_status().json()
        if active and active['status'] in ('RUNNING', 'PAUSED', 'LOADING'):
            raise SystemExit('Stop the active run before importing references.')
        existing = client.get('/api/references').raise_for_status().json()
        vision = Vision('large', False)
        for row in selected:
            source = f"{row['source_page']} | asset={row['asset_id']}"
            if any(ref['source'] == source and ref.get('reference_kind') == 'product_photo' for ref in existing):
                print(json.dumps({'asset': row['asset_id'], 'status': 'already_registered'}))
                continue
            if not row.get('allow_embedding') or row.get('review_scope') != 'local_poc_only':
                raise ValueError(f"Unapproved local embedding scope: {row['asset_id']}")
            path = Path(row['local_path'])
            original = cv2.imread(str(path))
            if original is None:
                raise ValueError(f'Unreadable image: {path}')
            box = row['bbox_xyxy']
            body = vision.body(crop(original, box))
            if body is None or 'identity_torso' not in body['boxes']:
                raise ValueError(f"Insufficient target-associated torso: {row['asset_id']}")
            x1, y1, x2, y2 = body['boxes']['identity_torso']
            metadata = {'product_id': row['product_id'], 'product_name': row['product_name'],
                        'reference_kind': 'product_photo', 'source': source,
                        'usage_scope': f"local_poc_only; {row['rights_status']}; no redistribution; "
                                       f"source_group={row['source_group']}; pose-torso-context-v1",
                        'view': 'front' if row['view'] == 'front' else 'side', 'region': 'torso',
                        'bbox': [box[0]+x1, box[1]+y1, box[0]+x2, box[1]+y2]}
            with path.open('rb') as image:
                response = client.post('/api/references', files={'image': (path.name, image)},
                                       data={'metadata': json.dumps(metadata)})
            response.raise_for_status()
            print(json.dumps({'asset': row['asset_id'], 'reference': response.json()['id'],
                              'bbox': metadata['bbox']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
