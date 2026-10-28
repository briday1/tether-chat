"""Home-only local persistence for Drive sync. No network or OAuth credentials.

The adapter exports an explicit allowlist and commits materialized records and
sync metadata together. Callers must supply both snapshot and revision so edits
or another sync window cannot be overwritten between read and apply.
"""
import json
import re
from datetime import datetime
from . import store, workspaces

MAX_RECORDS = 10000
MAX_BYTES = 20 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$')
ID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')
FIELDS = {
    'task': ('id', 'title', 'summary', 'state', 'categories', 'revisit_at', 'due_at',
             'recurrence', 'next_occurrence', 'archived_at', 'created_at', 'updated_at'),
    'entry': ('id', 'thread_id', 'kind', 'body', 'done', 'due_at', 'revisit_at', 'created_at'),
    'note': ('id', 'action_id', 'body', 'created_at', 'updated_at'),
}
TABLES = {'task': 'threads', 'entry': 'entries', 'note': 'action_notes'}


class SyncError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def _home():
    if workspaces.current() != 'home':
        raise SyncError('Drive sharing is available only in Home', 403)


def _table(c):
    c.execute('CREATE TABLE IF NOT EXISTS drive_sync_local (id INTEGER PRIMARY KEY CHECK(id=1), metadata TEXT NOT NULL, revision INTEGER NOT NULL)')
    c.execute("INSERT OR IGNORE INTO drive_sync_local VALUES(1,'{}',0)")


def _records(c):
    result = {}
    memberships = {}
    for row in c.execute('SELECT thread_id,name FROM thread_categories ORDER BY position,name'):
        memberships.setdefault(row['thread_id'], []).append(row['name'])
    for kind, table in TABLES.items():
        for row in c.execute('SELECT * FROM ' + table):
            record = {field: row[field] for field in FIELDS[kind] if field != 'categories'}
            if kind == 'task':
                record['categories'] = memberships.get(row['id'], [row['category'] or 'Unsorted'])
            result[kind + ':' + row['id']] = record
    return result


def snapshot():
    _home()
    with store.conn() as c:
        c.execute('BEGIN IMMEDIATE')
        _table(c)
        row = c.execute('SELECT metadata,revision FROM drive_sync_local WHERE id=1').fetchone()
        return {'records': _records(c), 'metadata': json.loads(row['metadata']), 'revision': row['revision']}


def _json(value, limit, label):
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise SyncError('Invalid ' + label) from None
    if len(text.encode('utf-8')) > limit:
        raise SyncError(label + ' is too large')
    return text


def _text(value, field, limit, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise SyncError('Invalid ' + field)


def _date(value, field, nullable=True):
    if value is None and nullable:
        return
    if not isinstance(value, str) or len(value) > 64 or not ISO_DATE.fullmatch(value):
        raise SyncError('Invalid ' + field)
    try:
        if datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is None:
            raise ValueError()
    except ValueError:
        raise SyncError(field + ' needs a timezone-aware ISO datetime') from None


def validate_records(records):
    if not isinstance(records, dict) or len(records) > MAX_RECORDS:
        raise SyncError('Invalid shared records')
    _json(records, MAX_BYTES, 'Shared records')
    for key, record in records.items():
        if not isinstance(key, str) or ':' not in key:
            raise SyncError('Invalid record key')
        kind, identity = key.split(':', 1)
        if kind not in FIELDS or not ID.fullmatch(identity):
            raise SyncError('Invalid record key')
        if not isinstance(record, dict) or set(record) != set(FIELDS[kind]) or record.get('id') != identity:
            raise SyncError('Unexpected or missing shared fields')
        for field in ('created_at', 'updated_at'):
            if field in record:
                _date(record[field], field, False)
        for field in ('due_at', 'revisit_at', 'next_occurrence', 'archived_at'):
            if field in record:
                _date(record[field], field)
        if kind == 'task':
            _text(record['title'], 'title', 300, True)
            _text(record['summary'], 'summary', 20000)
            if record['state'] not in ('open', 'waiting', 'paused', 'settled'):
                raise SyncError('Invalid task state')
            if record['recurrence'] not in (None, 'daily', 'weekly', 'monthly', 'quarterly', 'yearly'):
                raise SyncError('Invalid recurrence')
            cats = record['categories']
            if not isinstance(cats, list) or not 1 <= len(cats) <= 20:
                raise SyncError('Invalid categories')
            for cat in cats:
                _text(cat, 'category', 80, True)
            if len({cat.lower() for cat in cats}) != len(cats):
                raise SyncError('Duplicate categories')
        elif kind == 'entry':
            _text(record['body'], 'entry body', 20000, True)
            if record['kind'] not in ('thought', 'question', 'action', 'decision', 'update'):
                raise SyncError('Invalid entry kind')
            if not isinstance(record['done'], (int, bool)) or record['done'] not in (0, 1):
                raise SyncError('Invalid completion value')
            parent = record['thread_id']
            if not isinstance(parent, str) or 'task:' + parent not in records:
                raise SyncError('Entry references a missing task')
        else:
            _text(record['body'], 'note body', 20000, True)
            parent = record['action_id']
            entry = records.get('entry:' + parent) if isinstance(parent, str) else None
            if not entry or entry.get('kind') != 'action':
                raise SyncError('Note references a missing action')
    return records


def apply(expected, records, metadata, expected_revision):
    """CAS all shared fields and local sync state; nothing is written on conflict."""
    _home()
    if not isinstance(expected, dict) or not isinstance(metadata, dict):
        raise SyncError('Expected records and metadata must be objects')
    if type(expected_revision) is not int or expected_revision < 0:
        raise SyncError('Invalid local revision')
    _json(expected, MAX_BYTES, 'Expected records')
    encoded = _json(metadata, MAX_METADATA_BYTES, 'Sync metadata')
    validate_records(records)
    with store.conn() as c:
        c.execute('BEGIN IMMEDIATE')
        _table(c)
        revision = c.execute('SELECT revision FROM drive_sync_local WHERE id=1').fetchone()[0]
        current = _records(c)
        if revision != expected_revision or current != expected:
            raise SyncError('Home changed while syncing; retry with a fresh snapshot', 409)
        # Delete children first; foreign-key cascades clean local per-task state.
        for kind in ('note', 'entry', 'task'):
            for key, old in current.items():
                if key.startswith(kind + ':') and key not in records:
                    c.execute('DELETE FROM ' + TABLES[kind] + ' WHERE id=?', (old['id'],))
        for kind in ('task', 'entry', 'note'):
            for key, record in records.items():
                if not key.startswith(kind + ':'):
                    continue
                old = current.get(key)
                if old == record:
                    continue
                values = {name: value for name, value in record.items() if name != 'categories'}
                if kind == 'task':
                    values['category'] = record['categories'][0]
                if old is None:
                    fields = list(values)
                    c.execute('INSERT INTO ' + TABLES[kind] + '(' + ','.join(fields) + ') VALUES(' + ','.join('?' for _ in fields) + ')', tuple(values.values()))
                else:
                    values.pop('id')
                    c.execute('UPDATE ' + TABLES[kind] + ' SET ' + ','.join(field + '=?' for field in values) + ' WHERE id=?', (*values.values(), record['id']))
                if kind == 'task':
                    c.execute('DELETE FROM thread_categories WHERE thread_id=?', (record['id'],))
                    c.executemany('INSERT INTO thread_categories(thread_id,name,position) VALUES(?,?,?)', [(record['id'], name, index) for index, name in enumerate(record['categories'])])
                if kind in ('task', 'entry') and (old is None or old['revisit_at'] != record['revisit_at']):
                    c.execute('UPDATE ' + TABLES[kind] + ' SET notified_for=NULL WHERE id=?', (record['id'],))
                if kind == 'task' and (old is None or old['next_occurrence'] != record['next_occurrence']):
                    c.execute('UPDATE threads SET recurring_notified_for=NULL WHERE id=?', (record['id'],))
        revision += 1
        c.execute('UPDATE drive_sync_local SET metadata=?,revision=? WHERE id=1', (encoded, revision))
        return {'records': _records(c), 'metadata': metadata, 'revision': revision}
