"""Persistent catalog overlay. Prework stays immutable; updates are versioned."""
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from catalog_sources import identity, manufacturer, now

ROOT = Path(__file__).resolve().parent
BASELINE_PATH = ROOT.parent.parent / '사전 구현 범위/04_화학보호복_기존페이지/demo/video-gallery/kit-catalog/catalog-data.json'
PRIVATE_KEYS = {'path', 'preview_path', 'local_path', 'local_file', 'media_url', 'cell_html'}


def public_data(value):
    if isinstance(value, list):
        return [public_data(v) for v in value]
    if isinstance(value, dict):
        return {k: public_data(v) for k, v in value.items() if k not in PRIVATE_KEYS}
    if isinstance(value, str) and value.startswith(('file:', '/home/', '/tmp/')):
        return '[로컬 자료 경로 비공개]'
    return value


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def identity_key(brand, model):
    m = manufacturer(brand)
    return identity(m['name'] if m else brand) + ':' + identity(model)


class CatalogStore:
    def __init__(self, path, baseline=None):
        self.path = Path(path)
        self.baseline = baseline or json.loads(BASELINE_PATH.read_text())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY, identity_key TEXT UNIQUE,
                    origin TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS aliases(identity_key TEXT PRIMARY KEY, product_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS history(seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL, run_id TEXT NOT NULL, recorded_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS pages(url TEXT PRIMARY KEY, sha256 TEXT, checked_at TEXT, manufacturer TEXT);
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT);
            ''')
            db.execute('BEGIN IMMEDIATE')
            if not db.execute("SELECT 1 FROM metadata WHERE key='revision'").fetchone():
                for p in self.baseline['products']:
                    pid = p['product_id']
                    key = identity_key(p['manufacturer'], p['identity']['model'])
                    db.execute('INSERT INTO products VALUES (?, ?, ?, ?)', (pid, key, 'prework', dump(p)))
                    for name in (p['identity'].get('model'), p['identity'].get('manufacturer_reference')):
                        if name:
                            db.execute('INSERT OR IGNORE INTO aliases VALUES (?,?)', (identity_key(p['manufacturer'], name), pid))
                for source in self.baseline['product_sources']:
                    db.execute('INSERT INTO sources VALUES (?,?)', (source['id'], dump(source)))
                db.execute("INSERT INTO metadata VALUES ('revision','1')")
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def catalog(self):
        with self.connect() as db:
            db.execute('BEGIN')
            catalog = deepcopy(self.baseline)
            catalog['products'] = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM products ORDER BY rowid')]
            catalog['product_sources'] = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM sources ORDER BY rowid')]
            catalog['catalog_meta'] = self._status(db)
            return catalog

    def _status(self, db):
        recent = db.execute('SELECT payload FROM runs ORDER BY rowid DESC LIMIT 1').fetchone()
        schedule = db.execute("SELECT value FROM metadata WHERE key='schedule'").fetchone()
        return {'revision': int(db.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()[0]),
                'product_count': db.execute('SELECT count(*) FROM products').fetchone()[0],
                'discovered_count': db.execute("SELECT count(*) FROM products WHERE origin='discovery'").fetchone()[0],
                'last_run': json.loads(recent[0]) if recent else None,
                'schedule': json.loads(schedule[0]) if schedule else None}

    def status(self):
        with self.connect() as db:
            return self._status(db)

    def set_schedule(self, automation_id):
        with self.connect() as db:
            db.execute("INSERT INTO metadata VALUES ('schedule', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (dump({'automation_id': automation_id, 'label': '매일 오전 9시', 'timezone': 'Asia/Seoul',
                              'configured_at': now(), 'executor': 'Codex 데스크톱 관리 자동화',
                              'requires_running_app': True}),))

    def apply(self, verified, pages, failures, started_at, search_notes=''):
        run_id = str(uuid.uuid4())
        report = {'id': run_id, 'started_at': started_at, 'finished_at': now(), 'added': [], 'updated': [],
                  'unchanged': [], 'source_changes': [], 'checked_sources': [], 'failures': failures,
                  'search_notes': search_notes[:1000]}
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for page in pages:
                old = db.execute('SELECT sha256 FROM pages WHERE url=?', (page.url,)).fetchone()
                if old and old[0] != page.sha256:
                    report['source_changes'].append({'url': page.url, 'manufacturer': page.manufacturer})
                db.execute('INSERT INTO pages VALUES (?,?,?,?) ON CONFLICT(url) DO UPDATE SET sha256=excluded.sha256, checked_at=excluded.checked_at',
                           (page.url, page.sha256, page.checked_at, page.manufacturer))
                report['checked_sources'].append({'url': page.url, 'manufacturer': page.manufacturer,
                                                  'checked_at': page.checked_at, 'sha256': page.sha256})
            for item, page in verified:
                key = identity_key(item['manufacturer'], item['model'])
                alias = db.execute('SELECT product_id FROM aliases WHERE identity_key=?', (key,)).fetchone()
                old = db.execute('SELECT * FROM products WHERE id=?', (alias[0],)).fetchone() if alias else None
                if old and old['origin'] == 'prework':
                    report['unchanged'].append(old['id'])
                    continue  # Observations never overwrite prework's richer evidence.
                pid = old['id'] if old else 'DISC_' + hashlib.sha256(key.encode()).hexdigest()[:16].upper()
                previous = json.loads(old['payload']) if old else None
                source_id = 'SRC_' + pid
                first_seen = previous['discovery']['first_seen_at'] if previous else now()
                product = {
                    'product_id': pid, 'display_name': f"{item['name']} · {item['model']}",
                    'manufacturer': item['manufacturer'], 'category': item['category'],
                    'candidate_status': 'discovered_basic_identity_only', 'company_type_assignment': None,
                    'identity': {'model': item['model'], 'manufacturer_reference': item['model'],
                                 'model_identity_status': 'manufacturer_text_verified', 'seller_aliases': [],
                                 'identity_notes': ['제조사 공식 페이지의 제품명·모델을 확인한 신규 발견 자료입니다.']},
                    'appearance': {'color': {'id': 'unknown', 'label': '색상 확인 전'},
                                   'hood': None, 'garment_form': 'unverified', 'closure_location': 'unverified'},
                    'domestic_purchase': [], 'certifications': [], 'images': [], 'set_components': {},
                    'chemical_suitability': {'status': 'not_assessed', 'task_approval': False},
                    'uncertainties': ['국내 인증·판매 실물·구매 경로 미확인', '화학물질별 성능과 현장 적용 미검토',
                                      '제조사 원문 사용 제한을 확인해야 합니다.'],
                    'source_ids': [source_id], 'checked_at': page.checked_at[:10],
                    'discovery': {'first_seen_at': first_seen, 'last_checked_at': page.checked_at,
                                  'release_date': None, 'status': 'basic_info_verified',
                                  'source_url': page.url, 'source_sha256': page.sha256,
                                  'recommendation_eligible': False},
                }
                source = {'id': source_id, 'title': f"{item['manufacturer']} {item['model']} 공식 제품 페이지",
                          'url': page.url, 'kind': 'manufacturer_product_page', 'checked_at': page.checked_at,
                          'reading': '정확한 모델·제품명·품목의 원문 일치 확인',
                          'source_excerpt': f"{item['model']} · {item['name']}",
                          'limits': ['출시일 미확인. 새 발견은 신제품 출시를 뜻하지 않습니다.', '인증·성능·구매 가능 여부 미검토']}
                # An identical source check only updates freshness, not the version.
                changed = not previous or any(previous['discovery'].get(k) != product['discovery'][k]
                            for k in ('source_url', 'source_sha256')) or previous['display_name'] != product['display_name'] or previous['category'] != product['category']
                db.execute('INSERT INTO products VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                           (pid, key, 'discovery', dump(product)))
                db.execute('INSERT OR IGNORE INTO aliases VALUES (?,?)', (key, pid))
                db.execute('INSERT INTO sources VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (source_id, dump(source)))
                report['added' if not old else 'updated' if changed else 'unchanged'].append(pid)
                if changed:
                    db.execute('INSERT INTO history(product_id,run_id,recorded_at,payload) VALUES (?,?,?,?)',
                               (pid, run_id, now(), dump({'product': product, 'source': source})))
            if report['added'] or report['updated']:
                db.execute("UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")
            report['status'] = 'partial' if failures and pages else 'failed' if failures else 'completed'
            db.execute('INSERT INTO runs VALUES (?,?,?,?)', (run_id, started_at, report['finished_at'], dump(report)))
        return report
