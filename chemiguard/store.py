import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from .config import DATA


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return f'{prefix}_{uuid.uuid4().hex[:16]}'


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(DATA / 'chemiguard.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS records (
                kind TEXT NOT NULL, id TEXT NOT NULL, created_at TEXT NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY(kind, id)
            );
            CREATE INDEX IF NOT EXISTS records_recent ON records(kind, created_at DESC);
        ''')
        self.db.commit()

    def put(self, kind, value, replace=False):
        value = dict(value)
        value.setdefault('id', uid(kind))
        value.setdefault('created_at', now())
        command = 'INSERT OR REPLACE' if replace else 'INSERT'
        with self.lock, self.db:
            self.db.execute(f'{command} INTO records VALUES (?, ?, ?, ?)',
                            (kind, value['id'], value['created_at'], json.dumps(value, ensure_ascii=False, allow_nan=False)))
        return value

    def get(self, kind, record_id):
        with self.lock:
            row = self.db.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind, record_id)).fetchone()
        return json.loads(row['payload']) if row else None

    def list(self, kind, limit=1000):
        with self.lock:
            rows = self.db.execute('SELECT payload FROM records WHERE kind=? ORDER BY created_at DESC LIMIT ?',
                                   (kind, limit)).fetchall()
        return [json.loads(row['payload']) for row in rows]

    def revision(self):
        with self.lock:
            return self.db.execute("SELECT count(*) FROM records WHERE kind='reference'").fetchone()[0]


store = Store()
