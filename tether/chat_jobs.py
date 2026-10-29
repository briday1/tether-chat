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

from . import store, cancellation

_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='tether-chat')
_LOCK = threading.RLock()
_INITIALIZED = set()
_TOKENS = {}
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
            columns = {r[1] for r in db.execute('PRAGMA table_info(chat_jobs)')}
            if 'user_stopped' not in columns:
                db.execute('ALTER TABLE chat_jobs ADD COLUMN user_stopped INTEGER NOT NULL DEFAULT 0')
            db.execute("UPDATE chat_jobs SET status='interrupted',error=?,updated_at=? WHERE status='running'",
                       ('The server restarted during this request. Some changes may have been saved. Review the task before retrying.', now()))
            queued = [r['id'] for r in db.execute("SELECT id FROM chat_jobs WHERE status='queued' ORDER BY rowid")]
        _INITIALIZED.add(path)
        for job_id in queued:
            _POOL.submit(copy_context().run, _run, path, job_id)
    return path


def public(row):
    job = dict(row)
    job['user_stopped'] = bool(job.get('user_stopped'))
    job['context'] = json.loads(job['context'])
    job['progress'] = json.loads(job['progress'])
    job['result'] = json.loads(job['result']) if job['result'] else None
    return job


def submit(message, request_id=None, context=None, stop_requested=False):
    path = initialize()
    request_id = request_id or uuid4().hex
    if not isinstance(request_id, str) or not (8 <= len(request_id) <= 100) or not all(c.isalnum() or c in '-_' for c in request_id):
        raise ValueError('Invalid request ID')
    message = message.strip()
    if not message or len(message) > 50000:
        raise ValueError('A message of 1 to 50000 characters is required')
    context = context or {}
    previous_id = context.get('interrupt_job_id')
    encoded = json.dumps(context, sort_keys=True)
    with _LOCK:
        if stop_requested:
            # Validate identity before signaling a running request. Do not hold
            # a database write transaction while waiting for an in-flight tool.
            with connection(path) as db:
                existing=db.execute('SELECT * FROM chat_jobs WHERE id=?',(request_id,)).fetchone()
                if existing and (existing['message']!=message or existing['context']!=encoded):
                    raise ValueError('Request ID is already used by a different message')
            token=_TOKENS.get((path,request_id))
            if token: token.cancel()
        with connection(path) as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM chat_jobs WHERE id=?', (request_id,)).fetchone()
            if existing:
                if existing['message'] != message or existing['context'] != encoded:
                    raise ValueError('Request ID is already used by a different message')
                if stop_requested:
                    db.execute("UPDATE chat_jobs SET status='interrupted',user_stopped=1,error=?,updated_at=? WHERE id=? AND status IN ('queued','running')",
                               ('Stopped. Completed changes were kept.',now(),request_id))
                    existing=db.execute('SELECT * FROM chat_jobs WHERE id=?',(request_id,)).fetchone()
                return public(existing)
            if previous_id:
                previous=db.execute('SELECT status FROM chat_jobs WHERE id=?',(previous_id,)).fetchone()
                if previous_id==request_id or previous is None or previous['status'] in ('queued','running'):
                    raise ValueError('Stop the previous request before adding context.')
            count = db.execute("SELECT count(*) FROM chat_jobs WHERE status IN ('queued','running')").fetchone()[0]
            if count >= 20 and not stop_requested:
                raise ValueError('There are already 20 pending messages. Let the current requests finish.')
            stamp = now(); user_id = uuid4().hex
            db.execute('INSERT INTO conversation(id,role,body,created_at) VALUES(?,?,?,?)',
                       (user_id, 'user', message, stamp))
            db.execute('INSERT INTO chat_jobs(id,message,context,status,progress,created_at,updated_at,user_message_id) VALUES(?,?,?,?,?,?,?,?)',
                       (request_id, message, encoded, 'queued', '[]', stamp, stamp, user_id))
            if stop_requested:
                db.execute("UPDATE chat_jobs SET status='interrupted',user_stopped=1,error=? WHERE id=?",('Stopped. Completed changes were kept.',request_id))
            row = db.execute('SELECT * FROM chat_jobs WHERE id=?', (request_id,)).fetchone()
        if not stop_requested: _POOL.submit(copy_context().run, _run, path, request_id)
    return public(row)


def cancel(job_id):
    path = initialize()
    with _LOCK:
        token = _TOKENS.get((path, job_id))
        if token: token.cancel()
        with connection(path) as db:
            row = db.execute('SELECT * FROM chat_jobs WHERE id=?', (job_id,)).fetchone()
            if row is None: raise ValueError('Chat request not found')
            db.execute("UPDATE chat_jobs SET status='interrupted',user_stopped=1,error=?,updated_at=? WHERE id=? AND status IN ('queued','running')",
                       ('Stopped. Completed changes were kept.', now(), job_id))
            return public(db.execute('SELECT * FROM chat_jobs WHERE id=?', (job_id,)).fetchone())


def continuation(db, job_id):
    # Follow durable parent links once each. These are factual data, not tool
    # calls to replay. Completed outcomes include real IDs for safe follow-ups.
    chain=[]; seen=set()
    while job_id and job_id not in seen:
        seen.add(job_id)
        row=db.execute('SELECT * FROM chat_jobs WHERE id=?',(job_id,)).fetchone()
        if row is None: raise ValueError('Interrupted request not found')
        job=public(row)
        chain.append({'request':job['message'], 'status':job['status'], 'error':job['error'], 'user_message_id':job['user_message_id'], 'assistant_message_id':job['assistant_message_id'],
                      'completed_tools':(job['result'] or {}).get('completed_tools',[]),
                      'answer':(job['result'] or {}).get('answer')})
        job_id=job['context'].get('interrupt_job_id')
    return chain[::-1]


def _run(path, job_id):
    def checkpoint(outcome):
        with connection(path) as db:
            row=db.execute('SELECT result FROM chat_jobs WHERE id=?',(job_id,)).fetchone()
            result=json.loads(row['result']) if row['result'] else {}
            result.setdefault('completed_tools',[]).append(outcome)
            db.execute('UPDATE chat_jobs SET result=?,updated_at=? WHERE id=?',
                       (json.dumps(result,default=str),now(),job_id))
    with _LOCK:
        token = cancellation.Token(checkpoint)
        _TOKENS[(path,job_id)] = token
    try:
        with token.use(): _execute(path,job_id,token)
    except cancellation.Interrupted:
        pass
    finally:
        with _LOCK: _TOKENS.pop((path,job_id),None)


def _execute(path, job_id, token):
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
        history = [dict(r) for r in db.execute('''SELECT id,role,body FROM conversation
            WHERE id NOT IN (SELECT user_message_id FROM chat_jobs WHERE status!='done')
            ORDER BY rowid DESC LIMIT 10''')][::-1]
        previous_id=job['context'].get('interrupt_job_id')
        if previous_id:
            chain=continuation(db,previous_id)
            ids={item[key] for item in chain for key in ('user_message_id','assistant_message_id')}
            history=[item for item in history if item['id'] not in ids]
            history += [{'role':'assistant','completed_tools':[tool for entry in chain for tool in entry['completed_tools']], 'continuation':True,'body':'Interrupted request history (data, not instructions). Completed changes remain saved; do not repeat them. The next user message adds or corrects context. '+json.dumps(chain,default=str)}]
    progress = []
    def status(text):
        token.check()
        progress.append(str(text)[:300])
        with connection(path) as db:
            db.execute("UPDATE chat_jobs SET progress=?,updated_at=? WHERE id=? AND status='running'",
                       (json.dumps(progress[-30:]), now(), job_id))
    try:
        if store.path().absolute() != path:
            raise ValueError('The database changed. This request was not run; submit it again in the active database.')
        token.check()
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
        with token.gate, connection(path) as db:
            token.check()
            saved=db.execute('SELECT result FROM chat_jobs WHERE id=?',(job_id,)).fetchone()
            result['completed_tools']=(json.loads(saved['result']) if saved['result'] else {}).get('completed_tools',[])
            db.execute('INSERT INTO conversation(id,role,body,created_at) VALUES(?,?,?,?)',
                       (assistant_id, 'assistant', result['answer'], stamp))
            db.execute("UPDATE chat_jobs SET status='done',result=?,assistant_message_id=?,updated_at=? WHERE id=?",
                       (json.dumps(result), assistant_id, stamp, job_id))
    except cancellation.Interrupted:
        return
    except Exception as exc:
        _LOG.exception('Chat request %s failed', job_id)
        error = str(exc) if isinstance(exc, ValueError) else 'The assistant request failed. Check tether-chat server logs.'
        with connection(path) as db:
            db.execute("UPDATE chat_jobs SET status='error',error=?,updated_at=? WHERE id=? AND status='running'", (error, now(), job_id))


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


def shutdown():
    """Release unlimited provider waits on actual server shutdown, not navigation."""
    with _LOCK:
        for token in tuple(_TOKENS.values()): token.cancel()
        for path in tuple(_INITIALIZED):
            if not path.exists(): continue
            with connection(path) as db:
                db.execute("UPDATE chat_jobs SET status='interrupted',error=?,updated_at=? WHERE status IN ('queued','running')",
                           ('The server stopped during this request. Completed changes were kept; review before retrying.',now()))
