"""Transactional SQLite storage, with a one-time, lossless legacy migration."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class MemoryDatabase:
    def __init__(self, path, legacy_path):
        self.path = Path(path)
        self.legacy_path = Path(legacy_path)

    @contextmanager
    def transaction(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.path.chmod(0o600)
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('BEGIN IMMEDIATE')
            self._initialize(connection)
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self, con):
        # Each fact has its own indexed row. JSON payloads retain legacy value
        # types/metadata; the database is not one opaque serialized snapshot.
        for sql in (
            'CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
            'CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY)',
            '''CREATE TABLE IF NOT EXISTS memory_entries (
                category TEXT NOT NULL REFERENCES categories(name) ON DELETE CASCADE,
                key TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(category,key))''',
            'CREATE TABLE IF NOT EXISTS extra_values (key TEXT PRIMARY KEY, payload TEXT NOT NULL)',
            '''CREATE TABLE IF NOT EXISTS session_summaries (
                id INTEGER PRIMARY KEY, payload TEXT NOT NULL, consumed_at TEXT)''',
            '''CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY, session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                content TEXT NOT NULL, created_at TEXT NOT NULL)''',
            'CREATE INDEX IF NOT EXISTS messages_session ON conversation_messages(session_id,id)',
        ):
            con.execute(sql)
        if con.execute("SELECT value FROM metadata WHERE key='legacy_imported'").fetchone():
            return
        data = {}
        if self.legacy_path.exists():
            raw = self.legacy_path.read_bytes()
            data = json.loads(raw.decode('utf-8'))
            if not isinstance(data, dict):
                raise ValueError('Memória antiga inválida: esperado um objeto JSON. Migração cancelada.')
            backup = self.legacy_path.with_name(self.legacy_path.name + '.pre-sqlite.bak')
            try:
                with backup.open('xb') as handle:
                    handle.write(raw)
                backup.chmod(0o600)
            except FileExistsError:
                pass
        self._write(con, data)
        con.execute("INSERT INTO metadata VALUES ('legacy_imported',?)", (now(),))
        con.execute("INSERT INTO metadata VALUES ('schema_version','1')")

    @staticmethod
    def _read(con):
        data = {name: {} for (name,) in con.execute('SELECT name FROM categories ORDER BY name')}
        for category, key, payload in con.execute('SELECT category,key,payload FROM memory_entries ORDER BY category,key'):
            data[category][key] = json.loads(payload)
        for key, payload in con.execute('SELECT key,payload FROM extra_values'):
            data[key] = json.loads(payload)
        if con.execute("SELECT 1 FROM metadata WHERE key='has_sessions'").fetchone():
            data['sessions'] = [json.loads(row[0]) for row in con.execute(
                'SELECT payload FROM session_summaries WHERE consumed_at IS NULL ORDER BY id')]
        return data

    @staticmethod
    def _write(con, data):
        if 'sessions' not in data:
            con.execute('UPDATE session_summaries SET consumed_at=? WHERE consumed_at IS NULL', (now(),))
        con.execute('DELETE FROM memory_entries')
        con.execute('DELETE FROM categories')
        con.execute('DELETE FROM extra_values')
        for category, entries in data.items():
            if category == 'sessions' and isinstance(entries, list):
                wanted = [encode(entry) for entry in entries]
                current = [row[0] for row in con.execute('SELECT payload FROM session_summaries WHERE consumed_at IS NULL ORDER BY id')]
                if wanted != current:
                    # Keep summaries as history, even when an old API consumes them.
                    con.execute('UPDATE session_summaries SET consumed_at=? WHERE consumed_at IS NULL', (now(),))
                    con.executemany('INSERT INTO session_summaries(payload) VALUES (?)', [(x,) for x in wanted])
                con.execute("INSERT OR IGNORE INTO metadata VALUES ('has_sessions','1')")
            elif isinstance(entries, dict):
                con.execute('INSERT INTO categories VALUES (?)', (category,))
                con.executemany('INSERT INTO memory_entries VALUES (?,?,?)',
                                [(category,key,encode(value)) for key,value in entries.items()])
            else:
                con.execute('INSERT INTO extra_values VALUES (?,?)', (category,encode(entries)))

    def load(self):
        with self.transaction() as con:
            return self._read(con)

    def replace(self, data):
        if not isinstance(data, dict):
            raise TypeError('Memory must be a dictionary')
        with self.transaction() as con:
            self._write(con, data)

    def mutate(self, change):
        """Read/modify/write under one cross-process write lock; no lost updates."""
        with self.transaction() as con:
            data = self._read(con)
            result = change(data)
            self._write(con, data)
            return result

    def save_summary(self, entry):
        with self.transaction() as con:
            con.execute('INSERT INTO session_summaries(payload) VALUES (?)', (encode(entry),))
            con.execute("INSERT OR IGNORE INTO metadata VALUES ('has_sessions','1')")

    def pop_summary(self):
        with self.transaction() as con:
            row = con.execute('SELECT id,payload FROM session_summaries WHERE consumed_at IS NULL ORDER BY id DESC LIMIT 1').fetchone()
            if row is None:
                return None
            con.execute('UPDATE session_summaries SET consumed_at=? WHERE id=?', (now(),row[0]))
            return json.loads(row[1])

    def add_message(self, session_id, role, content):
        if not content.strip():
            return
        with self.transaction() as con:
            con.execute('INSERT INTO conversation_messages(session_id,role,content,created_at) VALUES (?,?,?,?)',
                        (session_id,role,content,now()))

    def search_messages(self, query, limit=8):
        escaped = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        with self.transaction() as con:
            count = max(1, min(int(limit), 50))
            pattern = '%' + escaped + '%'
            rows = con.execute("SELECT role,content,created_at FROM conversation_messages WHERE content LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ?",
                               (pattern, count)).fetchall()
            summaries = con.execute("SELECT payload FROM session_summaries WHERE payload LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ?",
                                    (pattern, count)).fetchall()
            for (payload,) in summaries:
                entry = json.loads(payload)
                if isinstance(entry, dict):
                    rows.append(('summary', str(entry.get('summary', '')), str(entry.get('date', ''))))
            return sorted(rows, key=lambda row: row[2], reverse=True)[:count]
