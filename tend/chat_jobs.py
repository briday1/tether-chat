"""Durable, serialized chat jobs. Browser navigation never owns a provider call."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import copy_context
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4

from . import store

_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='tether-chat')
_LOCK = threading.RLock()
_INITIALIZED = set()
_LOG = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection(path):
    db = sqlite3.connect(str(path), timeout=15)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    finally:
        db.close()


def initialize():
    """Recover queued jobs once per server lifetime; never replay interrupted tools."""
    path = store.path().absolute()
    with _LOCK:
        if path in _INITIALIZED:
            return path
        store.init()
        with connection(path) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS chat_jobs(
                  id TEXT PRIMARY KEY, message TEXT NOT NULL, context TEXT NOT NULL,
                  status TEXT NOT NULL, progress TEXT NOT NULL, result TEXT,
                  error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                  user_message_id TEXT NOT NULL, assistant_message_id TEXT);
                CREATE INDEX IF NOT EXISTS chat_jobs_status ON chat_jobs(status);
            ''')
            db.execute("UPDATE chat_jobs SET status='interrupted',error=?,updated_at=? WHERE status='running'",
                       ('The server restarted during this request. Some changes may have been saved. Review the task before retrying.', now()))
            queued = [r['id'] for r in db.execute("SELECT id FROM chat_jobs WHERE status='queued' ORDER BY rowid")]
        _INITIALIZED.add(path)
        for job_id in queued:
            _POOL.submit(copy_context().run, _run, path, job_id)
    return path


def public(row):
    job = dict(row)
    job['context'] = json.loads(job['context'])
    job['progress'] = json.loads(job['progress'])
    job['result'] = json.loads(job['result']) if job['result'] else None
    return job


def submit(message, request_id=None, context=None):
    path = initialize()
    request_id = request_id or uuid4().hex
    if not isinstance(request_id, str) or not (8 <= len(request_id) <= 100) or not all(c.isalnum() or c in '-_' for c in request_id):
        raise ValueError('Invalid request ID')
    message = message.strip()
    if not message or len(message) > 50000:
        raise ValueError('A message of 1 to 50000 characters is required')
    encoded = json.dumps(context or {}, sort_keys=True)
    with _LOCK:
        with connection(path) as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM chat_jobs WHERE id=?', (request_id,)).fetchone()
            if existing:
                if existing['message'] != message or existing['context'] != encoded:
                    raise ValueError('Request ID is already used by a different message')
                return public(existing)
            count = db.execute("SELECT count(*) FROM chat_jobs WHERE status IN ('queued','running')").fetchone()[0]
            if count >= 20:
                raise ValueError('There are already 20 pending messages. Let the current requests finish.')
            stamp = now(); user_id = uuid4().hex
            db.execute('INSERT INTO conversation(id,role,body,created_at) VALUES(?,?,?,?)',
                       (user_id, 'user', message, stamp))
            db.execute('INSERT INTO chat_jobs(id,message,context,status,progress,created_at,updated_at,user_message_id) VALUES(?,?,?,?,?,?,?,?)',
                       (request_id, message, encoded, 'queued', '[]', stamp, stamp, user_id))
            row = db.execute('SELECT * FROM chat_jobs WHERE id=?', (request_id,)).fetchone()
        _POOL.submit(copy_context().run, _run, path, request_id)
    return public(row)


def _run(path, job_id):
    from . import ai, commands
    from .snapshot_intent import respond as snapshot_respond
    from .rendering import render
    with connection(path) as db:
        changed = db.execute("UPDATE chat_jobs SET status='running',updated_at=? WHERE id=? AND status='queued'", (now(), job_id)).rowcount
        if not changed:
            return
        job = public(db.execute('SELECT * FROM chat_jobs WHERE id=?', (job_id,)).fetchone())
        # Pending user messages are persisted immediately but must not be fed into
        # an earlier job. Only completed requests and ordinary history are context.
        history = [dict(r) for r in db.execute('''SELECT role,body FROM conversation
            WHERE id NOT IN (SELECT user_message_id FROM chat_jobs WHERE status!='done')
            ORDER BY rowid DESC LIMIT 10''')][::-1]
    progress = []
    def status(text):
        progress.append(str(text)[:300])
        with connection(path) as db:
            db.execute('UPDATE chat_jobs SET progress=?,updated_at=? WHERE id=?',
                       (json.dumps(progress[-30:]), now(), job_id))
    try:
        if store.path().absolute() != path:
            raise ValueError('The database changed. This request was not run; submit it again in the active database.')
        message = job['message']
        if job['context'].get('kind') == 'attention':
            from .attention import check_in
            result = check_in(job['context'], progress=status)
        else:
            result = snapshot_respond(message)
            if result is None:
                kwargs = {'task_context': job['context']['task_ids']} if job['context'].get('kind') == 'task_context' else {}
                result = commands.execute(message) if message.startswith('/') else ai.chat(message, progress=status, history=history, **kwargs)
            if result is None:
                raise ValueError('Unknown command. Type /help.')
        result = {**result, 'answer_html': render(result['answer'])}
        assistant_id = uuid4().hex; stamp = now()
        with connection(path) as db:
            db.execute('INSERT INTO conversation(id,role,body,created_at) VALUES(?,?,?,?)',
                       (assistant_id, 'assistant', result['answer'], stamp))
            db.execute("UPDATE chat_jobs SET status='done',result=?,assistant_message_id=?,updated_at=? WHERE id=?",
                       (json.dumps(result), assistant_id, stamp, job_id))
    except Exception as exc:
        _LOG.exception('Chat request %s failed', job_id)
        error = str(exc) if isinstance(exc, ValueError) else 'The assistant request failed. Check tether-chat server logs.'
        with connection(path) as db:
            db.execute("UPDATE chat_jobs SET status='error',error=?,updated_at=? WHERE id=?", (error, now(), job_id))


def state():
    """One SQLite snapshot prevents a completed reply disappearing during polling."""
    from .rendering import render
    path = initialize()
    with connection(path) as db:
        db.execute('BEGIN')
        messages = [dict(r) for r in db.execute('SELECT * FROM conversation ORDER BY rowid DESC LIMIT 200')][::-1]
        jobs = [public(r) for r in db.execute('''SELECT * FROM chat_jobs WHERE
            status IN ('queued','running') OR user_message_id IN
            (SELECT id FROM conversation ORDER BY rowid DESC LIMIT 200) ORDER BY rowid''')]
    for row in messages:
        row['html'] = render(row['body']) if row['role'] == 'assistant' else None
    from .locations import requests
    return {'messages': messages, 'jobs': jobs, 'locations': requests()}
