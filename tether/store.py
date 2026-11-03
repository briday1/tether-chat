from . import environment
from . import recurrence as recurrence_rules
import os, sqlite3, json
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from contextlib import contextmanager

def now(): return datetime.now(timezone.utc).isoformat()
def path():
    from .storage import active_path
    from .workspaces import database_path
    base = Path(environment.get("TETHER_DB")).expanduser() if environment.get("TETHER_DB") else active_path()
    return database_path(base)
@contextmanager
def conn():
    p=path();p.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(p);c.row_factory=sqlite3.Row;c.execute("PRAGMA foreign_keys=ON")
    try: yield c;c.commit()
    finally: c.close()
def init():
    with conn() as c:
        c.executescript("""
CREATE TABLE IF NOT EXISTS threads(id TEXT PRIMARY KEY,title TEXT NOT NULL,summary TEXT NOT NULL DEFAULT '',state TEXT NOT NULL DEFAULT 'open',revisit_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entries(id TEXT PRIMARY KEY,thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,kind TEXT NOT NULL,body TEXT NOT NULL,done INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS action_notes(id TEXT PRIMARY KEY,action_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,body TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS action_notes_action ON action_notes(action_id);
CREATE TABLE IF NOT EXISTS relations(a TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,b TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,PRIMARY KEY(a,b));
CREATE TABLE IF NOT EXISTS conversation(id TEXT PRIMARY KEY,role TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS activity(id TEXT PRIMARY KEY,thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,kind TEXT NOT NULL,body TEXT NOT NULL,occurred_at TEXT NOT NULL,recorded_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS thread_categories(thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,name TEXT NOT NULL,position INTEGER NOT NULL,PRIMARY KEY(thread_id,name));
CREATE TABLE IF NOT EXISTS user_preferences(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assistant_context(id INTEGER PRIMARY KEY CHECK(id=1),task_id TEXT);
""")
        from .decisions import DEFAULT_PREFERENCES
        c.execute('INSERT OR IGNORE INTO user_preferences(id,value) VALUES(1,?)',(json.dumps(DEFAULT_PREFERENCES),))
        entry_columns={row[1] for row in c.execute("PRAGMA table_info(entries)")}
        for name in ("due_at","revisit_at","notified_for","snoozed_until"):
            if name not in entry_columns:c.execute(f"ALTER TABLE entries ADD COLUMN {name} TEXT")
        if "completed_by_task" not in entry_columns:c.execute("ALTER TABLE entries ADD COLUMN completed_by_task INTEGER NOT NULL DEFAULT 0")
        columns={row[1] for row in c.execute("PRAGMA table_info(threads)") }
        if "category" not in columns:c.execute("ALTER TABLE threads ADD COLUMN category TEXT NOT NULL DEFAULT 'Unsorted'")
        if "notified_for" not in columns:c.execute("ALTER TABLE threads ADD COLUMN notified_for TEXT")
        if "due_at" not in columns:c.execute("ALTER TABLE threads ADD COLUMN due_at TEXT")
        if "recurrence" not in columns:c.execute("ALTER TABLE threads ADD COLUMN recurrence TEXT")
        for name in ("recurrence_end", "recurrence_anchor", "recurrence_timezone"):
            if name not in columns:c.execute(f"ALTER TABLE threads ADD COLUMN {name} TEXT")
        if "next_occurrence" not in columns:c.execute("ALTER TABLE threads ADD COLUMN next_occurrence TEXT")
        if "due_action" not in columns:c.execute("ALTER TABLE threads ADD COLUMN due_action TEXT")
        if "action_config" not in columns:c.execute("ALTER TABLE threads ADD COLUMN action_config TEXT")
        if "recurring_notified_for" not in columns:c.execute("ALTER TABLE threads ADD COLUMN recurring_notified_for TEXT")
        if "action_prompt" not in columns:c.execute("ALTER TABLE threads ADD COLUMN action_prompt TEXT")
        if "archived_at" not in columns:c.execute("ALTER TABLE threads ADD COLUMN archived_at TEXT")
        for name in ("snoozed_until", "deferred_occurrence"):
            if name not in columns:c.execute(f"ALTER TABLE threads ADD COLUMN {name} TEXT")
        # Existing single-category records migrate once; subsequent starts preserve memberships.
        c.execute("""INSERT INTO thread_categories(thread_id,name,position)
                     SELECT id,category,0 FROM threads t
                     WHERE NOT EXISTS(SELECT 1 FROM thread_categories tc WHERE tc.thread_id=t.id)""")
        _auto_archive(c, now())
def query(sql,args=()):
    with conn() as c: return [dict(r) for r in c.execute(sql,args)]

def is_snoozed(record, at=None):
    """Future attention suppresses every nudge, without changing a real deadline.

    The reminder fallback also respects older/imported records created before the
    explicit snooze field existed. Invalid legacy dates must not hide work forever.
    """
    stamp = record.get('snoozed_until') or record.get('revisit_at')
    if not stamp:return False
    try:recurrence_rules.parse(stamp)
    except (ValueError, TypeError):return False
    return not recurrence_rules.is_due(stamp, at or now())

def _attention_time(value):
    if value is None:return None
    try:
        _, date_only = recurrence_rules.parse(value)
        if date_only:raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Bring to attention needs a timezone-aware ISO datetime') from None
    return value

def _snooze_for(value, at):
    return value if value and not recurrence_rules.is_due(value, at) else None

def _auto_archive(connection, stamp, task_id=None):
    """Archive only completed one-off work, retaining every dependent record."""
    rows = connection.execute("""SELECT t.id FROM threads t
        WHERE t.state='settled' AND t.archived_at IS NULL AND t.recurrence IS NULL
        AND NOT EXISTS(SELECT 1 FROM entries e WHERE e.thread_id=t.id AND e.kind='action' AND e.done=0)
        """ + (" AND t.id=?" if task_id else ""), (task_id,) if task_id else ()).fetchall()
    ids = [row['id'] for row in rows]
    connection.executemany('UPDATE threads SET archived_at=?,updated_at=? WHERE id=?',
                           [(stamp, stamp, ident) for ident in ids])
    return {'archived': len(ids), 'task_ids': ids}

def auto_archive():
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        return _auto_archive(c, now())

def _undo_task_completion(connection, task_id):
    # A task checkbox records which child actions it completed. Undo must not
    # reopen actions the user had already finished independently.
    connection.execute("UPDATE entries SET done=0,completed_by_task=0 WHERE thread_id=? AND kind='action' AND completed_by_task=1", (task_id,))

def complete_task(thread_id, done=True):
    """Finish a whole one-off task atomically, or undo its bulk completion."""
    if not isinstance(done, bool):raise ValueError('Completion must be true or false')
    stamp = now()
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        task = c.execute('SELECT * FROM threads WHERE id=?', (thread_id,)).fetchone()
        if not task:return None
        if done:
            if task['recurrence']:raise ValueError('Complete the current recurring occurrence instead of the whole task')
            c.execute("UPDATE entries SET done=1,completed_by_task=1 WHERE thread_id=? AND kind='action' AND done=0", (thread_id,))
            c.execute("UPDATE threads SET state='settled',updated_at=? WHERE id=?", (stamp, thread_id))
            _auto_archive(c, stamp, thread_id)
        else:
            _undo_task_completion(c, thread_id)
            c.execute("UPDATE threads SET state='open',archived_at=NULL,updated_at=? WHERE id=?", (stamp, thread_id))
    return get(thread_id)

def _defer_time(when, stamp):
    # Null is an explicit resume operation, not an indefinite hidden state.
    if when is None:return stamp
    _attention_time(when)
    if recurrence_rules.is_due(when, stamp):raise ValueError('Choose a future Bring to attention time')
    return when

def defer_task(thread_id, when):
    """Postpone this task and its child nudges; preserve deadlines and cadence."""
    stamp = now(); when = _defer_time(when, stamp)
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT * FROM threads WHERE id=?', (thread_id,)).fetchone()
        if not row:return None
        if row['archived_at'] or row['state']=='settled':raise ValueError('Reopen this task before changing its attention time')
        c.execute('UPDATE threads SET revisit_at=?,snoozed_until=?,deferred_occurrence=?,notified_for=NULL,updated_at=? WHERE id=?',
                  (when, _snooze_for(when, stamp), row['next_occurrence'] if row['recurrence'] else None, stamp, thread_id))
    return get(thread_id)

def defer_action(action_id, when):
    """Postpone one action only; unrelated sibling and parent schedules survive."""
    stamp = now(); when = _defer_time(when, stamp)
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute("SELECT e.*,t.state,t.archived_at FROM entries e JOIN threads t ON t.id=e.thread_id WHERE e.id=? AND e.kind='action'", (action_id,)).fetchone()
        if not row:return None
        if row['done'] or row['archived_at'] or row['state']=='settled':raise ValueError('Reopen this action before changing its attention time')
        c.execute('UPDATE entries SET revisit_at=?,snoozed_until=?,notified_for=NULL WHERE id=?', (when, _snooze_for(when, stamp), action_id))
        c.execute('UPDATE threads SET updated_at=? WHERE id=?', (stamp, row['thread_id']))
        return dict(c.execute('SELECT * FROM entries WHERE id=?', (action_id,)).fetchone())
def normalize_categories(names):
    if not isinstance(names,list) or len(names)>20:raise ValueError("Use a list of at most 20 categories")
    result=[];seen=set()
    for name in names:
        if not isinstance(name,str) or not name.strip() or len(name.strip())>80:raise ValueError("Invalid category")
        name=name.strip()
        if name.casefold() not in seen:result.append(name);seen.add(name.casefold())
    if len(result)>1:result=[name for name in result if name.casefold()!="unsorted"]
    return result or ["Unsorted"]
def category_names(thread):
    return thread.get("categories") or [thread.get("category") or "Unsorted"]
def with_categories(rows,key="id"):
    if not rows:return rows
    memberships={}
    for row in query("SELECT thread_id,name FROM thread_categories ORDER BY position,name"):
        memberships.setdefault(row["thread_id"],[]).append(row["name"])
    for row in rows:row["categories"]=memberships.get(row[key],[row.get("category") or "Unsorted"])
    return rows
def get(id):
    rows=with_categories(query("SELECT * FROM threads WHERE id=?",(id,)))
    if not rows:return None
    t=rows[0];t["action_config"]=json.loads(t["action_config"] or "{}");t["entries"]=query("SELECT * FROM entries WHERE thread_id=? ORDER BY created_at,id",(id,))
    notes={}
    for note in query("SELECT n.* FROM action_notes n JOIN entries e ON e.id=n.action_id WHERE e.thread_id=? ORDER BY n.created_at,n.id",(id,)):
        notes.setdefault(note["action_id"],[]).append(note)
    for entry in t["entries"]:
        if entry["kind"]=="action":entry["notes"]=notes.get(entry["id"],[])
    t["activity"]=query("SELECT * FROM activity WHERE thread_id=? ORDER BY occurred_at DESC,recorded_at DESC",(id,))
    t["related"]=query("SELECT t.id,t.title FROM relations r JOIN threads t ON t.id=CASE WHEN r.a=? THEN r.b ELSE r.a END WHERE r.a=? OR r.b=?",(id,id,id))
    return t
def list_threads(q=""):
    auto_archive()
    rows=with_categories(query("SELECT t.*,(SELECT COUNT(*) FROM entries e WHERE e.thread_id=t.id) entry_count FROM threads t WHERE title LIKE ? OR summary LIKE ? OR EXISTS(SELECT 1 FROM entries e WHERE e.thread_id=t.id AND e.body LIKE ?) OR EXISTS(SELECT 1 FROM thread_categories tc WHERE tc.thread_id=t.id AND tc.name LIKE ?) OR EXISTS(SELECT 1 FROM action_notes n JOIN entries e ON e.id=n.action_id WHERE e.thread_id=t.id AND n.body LIKE ?) ORDER BY updated_at DESC",("%"+q+"%",)*5))
    for t in rows:
        active = t["state"]!="settled" and not t.get("archived_at")
        t["snoozed"] = is_snoozed(t)
        t["attention_due"]=bool(active and not t['snoozed'] and t["revisit_at"] and recurrence_rules.is_due(t["revisit_at"],now()))
        t["deadline_due"]=bool(active and t.get("due_at") and recurrence_rules.deadline_due(t["due_at"],now()))
        t["recurring_due"]=bool(active and not t['snoozed'] and t.get("recurrence") and t.get("next_occurrence") and recurrence_rules.is_due(t["next_occurrence"],now()))
        t["due"]=t["attention_due"] or (t["recurring_due"] and not t.get("revisit_at"))
    for t in rows:t["action_config"]=json.loads(t["action_config"] or "{}")
    return sorted(rows,key=lambda t:not t["due"])
def create(title,summary="",categories=None):
    if not title.strip():raise ValueError("Title required")
    names=normalize_categories(categories if categories is not None else [])
    id=uuid4().hex;t=now()
    with conn() as c:
        c.execute("INSERT INTO threads(id,title,summary,category,created_at,updated_at) VALUES(?,?,?,?,?,?)",(id,title.strip(),summary,names[0],t,t))
        c.executemany("INSERT INTO thread_categories(thread_id,name,position) VALUES(?,?,?)",[(id,name,i) for i,name in enumerate(names)])
    return get(id)

def preferences():
    from .decisions import preferences as normalize
    rows=query('SELECT value FROM user_preferences WHERE id=1')
    return normalize(json.loads(rows[0]['value']) if rows else {})

def set_preferences(fields):
    from .decisions import preferences as normalize
    with conn() as c:
        c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT value FROM user_preferences WHERE id=1').fetchone()
        value=normalize({**(json.loads(row['value']) if row else {}),**fields})
        c.execute('INSERT OR REPLACE INTO user_preferences(id,value) VALUES(1,?)',(json.dumps(value),))
    return value

def category_list():return sorted({row['name'] for row in query('SELECT DISTINCT name FROM thread_categories') if row['name'].casefold()!='unsorted'})

def focus(id=None):
    from .decisions import task_key
    if id and get(id):
        with conn() as c:c.execute('INSERT OR REPLACE INTO assistant_context(id,task_id) VALUES(1,?)',(id,))
    rows=query('SELECT task_id FROM assistant_context WHERE id=1');task=get(rows[0]['task_id']) if rows else None
    if task and not task.get('archived_at') and task['state']!='settled':return task
    import re
    for message in reversed(conversation(10)):
        if message['role']!='assistant':continue
        ids=set(re.findall(r'#task/([A-Za-z0-9_-]+)',message['body']))
        if len(ids)==1:
            task=get(next(iter(ids)))
            if task and not task.get('archived_at') and task['state']!='settled':return task
    active=[task for task in list_threads() if not task.get('archived_at') and task['state']!='settled']
    return get(active[0]['id']) if active and len({task_key(t['title']) for t in active})==1 else None

def assistant_context():
    from .decisions import resolve_reminder
    p=preferences();focused=focus()
    return {'preferences':p,'available_categories':category_list(),'focused_task':({key:focused[key] for key in ('id','title','categories','revisit_at','due_at')}|{'summary':focused['summary'][:300]}) if focused else None,
      'recent_tasks':[{key:task[key] for key in ('id','title','categories','revisit_at')}|{'summary':task['summary'][:200]} for task in list_threads() if not task.get('archived_at') and task['state']!='settled'][:12],
      'default_reminder_choices':{period:resolve_reminder(period,p) for period in ('tomorrow','next week','next month','next year')}}

def capture(title,summary='',categories=None,remind_at=None,existing_id=None):
    from .decisions import task_key,choose_categories,resolve_reminder
    if not isinstance(title,str) or not title.strip():raise ValueError('Title required')
    if categories is not None and not isinstance(categories,list):raise ValueError('Use a list of categories')
    reminder=resolve_reminder(remind_at,preferences()) if remind_at else None
    key=task_key(title);stamp=now()
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        rows=[dict(row) for row in c.execute("SELECT * FROM threads WHERE archived_at IS NULL AND state!='settled' ORDER BY created_at,id")]
        existing=next((row for row in rows if row['id']==existing_id),None) if existing_id else next((row for row in rows if key and task_key(row['title'])==key),None)
        if existing_id and existing is None:raise ValueError('Find an active existing task before changing it')
        available=[r['name'] for r in c.execute('SELECT DISTINCT name FROM thread_categories')]
        names=normalize_categories(choose_categories(title,summary,available,categories))
        id=existing['id'] if existing else uuid4().hex
        if existing:
            current=[r['name'] for r in c.execute('SELECT name FROM thread_categories WHERE thread_id=? ORDER BY position',(id,))]
            if any(name.casefold()!='unsorted' for name in current):names=current
            c.execute('UPDATE threads SET summary=?,revisit_at=?,snoozed_until=?,deferred_occurrence=?,notified_for=?,category=?,updated_at=? WHERE id=?',
              (existing['summary'] or summary,reminder or existing['revisit_at'],_snooze_for(reminder,stamp) if reminder else existing['snoozed_until'],None if reminder else existing['deferred_occurrence'],None if reminder else existing['notified_for'],names[0],stamp,id))
        else:c.execute('INSERT INTO threads(id,title,summary,category,revisit_at,snoozed_until,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(id,title.strip(),summary,names[0],reminder,_snooze_for(reminder,stamp),stamp,stamp))
        c.execute('DELETE FROM thread_categories WHERE thread_id=?',(id,))
        c.executemany('INSERT INTO thread_categories(thread_id,name,position) VALUES(?,?,?)',[(id,name,i) for i,name in enumerate(names)])
        c.execute('INSERT OR REPLACE INTO assistant_context(id,task_id) VALUES(1,?)',(id,))
    return {**get(id),'reused':existing is not None}
def update(id,fields):
    allowed={"archived_at","title","summary","state","revisit_at","snoozed_until","due_at","category","categories","recurrence","next_occurrence","recurrence_end","recurrence_anchor","recurrence_timezone","due_action","action_config","action_prompt"}
    fields={k:v for k,v in fields.items() if k in allowed}
    names=None
    if "categories" in fields:
        names=normalize_categories(fields.pop("categories"))
        fields["category"]=names[0]
    elif "category" in fields:
        names=normalize_categories([fields["category"]]);fields["category"]=names[0]
    if "archived_at" in fields and fields["archived_at"] not in (None,) and not isinstance(fields["archived_at"],str):raise ValueError("Invalid archive timestamp")
    if "recurrence" in fields and fields["recurrence"] not in (None,"daily","weekly","monthly","quarterly","yearly"):raise ValueError("Invalid recurrence")
    previous = get(id)
    if previous and any(key in fields for key in ('recurrence', 'next_occurrence', 'recurrence_end', 'recurrence_anchor', 'recurrence_timezone')):
        combined = {**previous, **fields}
        recurrence_rules.validate_zone(combined.get('recurrence_timezone'))
        recurrence_rules.validate_end(combined.get('recurrence_end'))
        for key in ('next_occurrence', 'recurrence_anchor'):
            if combined.get(key) is not None:recurrence_rules.parse(combined[key], combined.get('recurrence_timezone'))
        schedule_changed = any(key in fields and fields[key] != previous.get(key) for key in ('recurrence', 'recurrence_timezone')) or ('next_occurrence' in fields and not recurrence_rules.equivalent(fields['next_occurrence'], previous.get('next_occurrence')))
        if schedule_changed or not combined.get('recurrence_anchor'):
            fields['recurrence_anchor'] = combined.get('next_occurrence')
        if combined.get('recurrence') is None:
            fields.update(next_occurrence=None, recurrence_anchor=None, recurrence_end=None, recurrence_timezone=None)
        elif combined.get('next_occurrence') and recurrence_rules.ended(combined['next_occurrence'], combined.get('recurrence_end'), combined.get('recurrence_timezone')):
            raise ValueError('Repeat end cannot be before the next occurrence')
        if schedule_changed:fields['recurring_notified_for'] = None
        if schedule_changed and previous.get('deferred_occurrence'):
            # Replacing a repeating schedule cannot retain a nudge attached to
            # the removed cycle. An explicit new reminder remains independent.
            if 'revisit_at' not in fields:fields['revisit_at'] = None
            fields['deferred_occurrence'] = None
    if "action_prompt" in fields and fields["action_prompt"] is not None and (not isinstance(fields["action_prompt"],str) or len(fields["action_prompt"])>1000):raise ValueError("Action description too long")
    if "due_action" in fields and fields["due_action"] not in (None,"activity_report"):raise ValueError("Invalid due action")
    if "action_config" in fields:
        v=fields["action_config"]
        if not isinstance(v,dict):raise ValueError("Action config must be an object")
        if set(v)-{"period","category"}:raise ValueError("Unsupported action configuration")
        if v.get("period","week") not in ("week","month","quarter","year"):raise ValueError("Invalid reporting period")
        if "category" in v and (not isinstance(v["category"],str) or len(v["category"])>80):raise ValueError("Invalid report category")
        fields["action_config"]=json.dumps(v)
    if "category" in fields and (not isinstance(fields["category"],str) or not fields["category"].strip() or len(fields["category"])>80):raise ValueError("Invalid category")
    if "state" in fields and fields["state"] not in {"open","waiting","paused","settled"}:raise ValueError("Invalid state")
    if "title" in fields and not fields["title"].strip():raise ValueError("Title required")
    for key in ('revisit_at', 'snoozed_until'):
        if key in fields:_attention_time(fields[key])
    if fields:
        stamp = now()
        if "revisit_at" in fields:
            fields['notified_for']=None
            fields['snoozed_until']=_snooze_for(fields['revisit_at'],stamp)
            fields['deferred_occurrence']=None
        fields["updated_at"]=stamp
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            current = c.execute('SELECT state,archived_at FROM threads WHERE id=?', (id,)).fetchone()
            reopening = bool(current and (('state' in fields and fields['state']!='settled' and current['state']=='settled') or ('archived_at' in fields and fields['archived_at'] is None and current['state']=='settled')))
            if reopening:
                fields['state']=fields.get('state') if fields.get('state') in ('open','waiting','paused') else 'open'
                fields['archived_at']=None
                _undo_task_completion(c,id)
            changed=c.execute("UPDATE threads SET "+",".join(k+"=?" for k in fields)+" WHERE id=?",(*fields.values(),id)).rowcount
            if changed and names is not None:
                c.execute("DELETE FROM thread_categories WHERE thread_id=?",(id,))
                c.executemany("INSERT INTO thread_categories(thread_id,name,position) VALUES(?,?,?)",[(id,name,i) for i,name in enumerate(names)])
            if changed:_auto_archive(c,stamp,id)
    return get(id)
def set_categories(id,categories,mode="replace"):
    """Replace, add, or remove memberships without creating duplicate task records."""
    if mode not in ("replace","add","remove"):raise ValueError("Category mode must be replace, add, or remove")
    names=normalize_categories(categories)
    if not categories:names=[]
    # Hold a write transaction across the read and update so simultaneous edits do not lose memberships.
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        row=c.execute("SELECT category FROM threads WHERE id=?",(id,)).fetchone()
        if row is None:return None
        existing=[r[0] for r in c.execute("SELECT name FROM thread_categories WHERE thread_id=? ORDER BY position",(id,))] or [row[0]]
        if mode=="add":names=existing+[name for name in names if name.casefold() not in {v.casefold() for v in existing}]
        elif mode=="remove":names=[n for n in existing if n.casefold() not in {v.casefold() for v in names}]
        names=normalize_categories(names)
        c.execute("UPDATE threads SET category=?,updated_at=? WHERE id=?",(names[0],now(),id))
        c.execute("DELETE FROM thread_categories WHERE thread_id=?",(id,))
        c.executemany("INSERT INTO thread_categories(thread_id,name,position) VALUES(?,?,?)",[(id,name,i) for i,name in enumerate(names)])
    return get(id)
def add(id,kind,body):
    if kind not in {"thought","question","action","decision","update"}:raise ValueError("Invalid kind")
    if not body.strip():raise ValueError("Entry required")
    if not get(id):return None
    eid=uuid4().hex;t=now()
    with conn() as c:
        c.execute("INSERT INTO entries(id,thread_id,kind,body,created_at) VALUES(?,?,?,?,?)",(eid,id,kind,body.strip(),t))
        c.execute("UPDATE threads SET updated_at=? WHERE id=?",(t,id))
    return query("SELECT * FROM entries WHERE id=?",(eid,))[0]
def update_action(id,fields):
    """Update an individual action's dates or completion without changing its parent task."""
    allowed={"body","due_at","revisit_at","snoozed_until","done"}
    fields={k:v for k,v in fields.items() if k in allowed}
    if not fields:raise ValueError("No action fields")
    if 'body' in fields:
        if not isinstance(fields['body'],str) or not fields['body'].strip() or len(fields['body'])>20000:raise ValueError('Action text must contain 1 to 20000 characters')
        fields['body']=fields['body'].strip()
    for key in ("due_at","revisit_at","snoozed_until"):
        if key in fields and fields[key] is not None:
            stamp=fields[key]
            try:
                dt,date_only=recurrence_rules.parse(stamp)
                if date_only and key!="due_at":raise ValueError()
            except (ValueError,AttributeError):raise ValueError("Action date needs a timezone-aware ISO datetime")
    if "done" in fields:
        if not isinstance(fields['done'],bool):raise ValueError('Completion must be true or false')
        fields["done"]=int(fields["done"])
        fields['completed_by_task']=0
    stamp=now()
    if "revisit_at" in fields:
        fields["notified_for"]=None
        fields['snoozed_until']=_snooze_for(fields['revisit_at'],stamp)
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT thread_id FROM entries WHERE id=? AND kind='action'",(id,)).fetchone()
        if not row:return None
        c.execute("UPDATE entries SET "+",".join(k+"=?" for k in fields)+" WHERE id=?",(*fields.values(),id))
        c.execute("UPDATE threads SET updated_at=? WHERE id=?",(stamp,row["thread_id"]))
        if fields.get('done')==0:
            # Reopening one action must make it reachable, without undoing any
            # siblings that were completed by the task checkbox.
            c.execute("UPDATE threads SET state='open',archived_at=NULL WHERE id=? AND state='settled'", (row['thread_id'],))
        _auto_archive(c,stamp,row['thread_id'])
    return query("SELECT * FROM entries WHERE id=?",(id,))[0]

def find_action(task_id,text):
    for e in query("SELECT * FROM entries WHERE thread_id=? AND kind='action'",(task_id,)):
        if e["body"].strip().casefold()==text.strip().casefold():return e
    return None

def toggle(id,done):
    return update_action(id, {'done':done})
def link(a,b):
    if a==b:raise ValueError("Self-link")
    if not get(a) or not get(b):return False
    with conn() as c:c.execute("INSERT OR IGNORE INTO relations(a,b) VALUES(?,?)",tuple(sorted([a,b])))
    return True
def delete(id):
    with conn() as c:return bool(c.execute("DELETE FROM threads WHERE id=?",(id,)).rowcount)
def overview():
    rows=[t for t in list_threads() if not t.get("archived_at")]
    return {"deadlines":[t for t in rows if t["deadline_due"]],"due":[t for t in rows if t["due"]],"active":[t for t in rows if t["state"]=="open" and not t["due"]],"waiting":[t for t in rows if t["state"]=="waiting"],"paused":[t for t in rows if t["state"]=="paused"],"settled":[t for t in rows if t["state"]=="settled"]}

def conversation(limit=100):
    return list(reversed(query("SELECT * FROM conversation ORDER BY created_at DESC,id DESC LIMIT ?",(limit,))))
def remember(role,body):
    id=uuid4().hex
    with conn() as c:c.execute("INSERT INTO conversation(id,role,body,created_at) VALUES(?,?,?,?)",(id,role,body,now()))
    return id

def board():
    groups={}
    for t in list_threads():
        if t.get("archived_at"):continue
        for category in category_names(t):groups.setdefault(category,[]).append(t)
    return [{"name":name,"threads":items} for name,items in sorted(groups.items(),key=lambda x:(x[0]=="Unsorted",x[0].casefold()))]

def claim_notifications():
    """Claim one reminder for each due timestamp, including recurring tasks."""
    from datetime import timedelta
    current=datetime.fromisoformat(now().replace('Z','+00:00'))
    claimed=[]
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        _auto_archive(c, current.isoformat())
        rows=c.execute("""SELECT id,title,revisit_at,notified_for,recurrence,next_occurrence,
                              recurring_notified_for,due_action,snoozed_until,deferred_occurrence
                          FROM threads WHERE state!='settled' AND archived_at IS NULL
                          AND (revisit_at IS NOT NULL OR (recurrence IS NOT NULL AND next_occurrence IS NOT NULL))""").fetchall()
        for row in rows:
            item=dict(row)
            if is_snoozed(item,current.isoformat()):continue
            schedules=[("revisit_at","notified_for")]
            deferred_cycle = item.get('deferred_occurrence') and recurrence_rules.equivalent(item['deferred_occurrence'], item['next_occurrence'])
            if item["recurrence"] and not deferred_cycle and (not item["revisit_at"] or recurrence_rules.is_due(item["revisit_at"],current.isoformat())):schedules.append(("next_occurrence","recurring_notified_for"))
            for date_field,claim_field in schedules:
                stamp=item[date_field]
                if not stamp or item[claim_field]==stamp:continue
                try:
                    if date_field == 'next_occurrence' and len(stamp) == 10:
                        due=datetime.fromisoformat(stamp).astimezone()
                    else:due=datetime.fromisoformat(stamp.replace("Z","+00:00"))
                except ValueError:continue
                if due.tzinfo is None:continue
                if not (current-timedelta(hours=24)<=due<=current):continue
                if len(claimed)>=3:return claimed
                # Build content before marking the occurrence notified.
                notice={"id":item["id"],"title":item["title"],"revisit_at":stamp,"due_action":item["due_action"]}
                if item["due_action"]=="activity_report":
                    try:notice["report"]=report_for_task(item["id"],anchor=stamp)
                    except (ValueError,TypeError) as exc:notice["report_error"]=str(exc)
                c.execute(f"UPDATE threads SET {claim_field}=? WHERE id=?",(stamp,item["id"]))
                claimed.append(notice)
        for row in c.execute("""SELECT e.id,e.thread_id,e.body,e.revisit_at,e.notified_for,e.snoozed_until,t.title,
                   t.snoozed_until AS parent_snoozed_until,t.revisit_at AS parent_revisit_at
            FROM entries e JOIN threads t ON t.id=e.thread_id
            WHERE e.kind='action' AND e.done=0 AND e.revisit_at IS NOT NULL
            AND t.archived_at IS NULL AND t.state!='settled'""").fetchall():
            if is_snoozed(dict(row),current.isoformat()) or is_snoozed({'snoozed_until':row['parent_snoozed_until'],'revisit_at':row['parent_revisit_at']},current.isoformat()):continue
            stamp=row["revisit_at"]
            if stamp==row["notified_for"]:continue
            try:due=datetime.fromisoformat(stamp.replace("Z","+00:00"))
            except ValueError:continue
            if due.tzinfo is None or not (current-timedelta(hours=24)<=due<=current):continue
            if len(claimed)>=3:break
            claimed.append({"id":row["thread_id"],"action_id":row["id"],"title":row["body"],"task_title":row["title"],"revisit_at":stamp})
            c.execute("UPDATE entries SET notified_for=? WHERE id=?",(stamp,row["id"]))
    return claimed

def daily_brief():
    from .notes import brief
    return brief(overview(),get)

def record_activity(thread_id,body,kind="progress",occurred_at=None):
    if kind not in {"progress","feedback","decision","blocker","milestone","other"}:raise ValueError("Invalid activity type")
    if not isinstance(body,str) or not body.strip():raise ValueError("Activity description required")
    if not get(thread_id):return None
    when=occurred_at or now()
    dt=datetime.fromisoformat(when.replace("Z","+00:00"))
    if dt.tzinfo is None:raise ValueError("Activity time requires timezone")
    when=dt.astimezone(timezone.utc).isoformat()
    ident=uuid4().hex
    with conn() as c:
        c.execute("INSERT INTO activity(id,thread_id,kind,body,occurred_at,recorded_at) VALUES(?,?,?,?,?,?)",(ident,thread_id,kind,body.strip(),when,now()))
        c.execute("UPDATE threads SET updated_at=? WHERE id=?",(now(),thread_id))
    return query("SELECT * FROM activity WHERE id=?",(ident,))[0]

def activity_report(period="week",anchor=None):
    from datetime import timedelta
    if period not in ("week","month","quarter","year"):raise ValueError("Invalid reporting period")
    ref=datetime.fromisoformat(anchor.replace("Z","+00:00")) if anchor else datetime.now(timezone.utc)
    if ref.tzinfo is None:raise ValueError("Report anchor requires timezone")
    ref=ref.astimezone(timezone.utc)
    if period=="week":
        start=(ref-timedelta(days=ref.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
        end=start+timedelta(days=7)
    else:
        month=1 if period=="year" else ((ref.month-1)//3)*3+1 if period=="quarter" else ref.month
        start=ref.replace(month=month,day=1,hour=0,minute=0,second=0,microsecond=0)
        newmonth=start.month+(12 if period=="year" else 3 if period=="quarter" else 1)
        end=start.replace(year=start.year+(newmonth-1)//12,month=(newmonth-1)%12+1)
    rows=with_categories(query("SELECT a.*,t.title,t.category FROM activity a JOIN threads t ON t.id=a.thread_id WHERE occurred_at>=? AND occurred_at<? ORDER BY occurred_at DESC",(start.isoformat(),end.isoformat())),"thread_id")
    return {"period":period,"start":start.isoformat(),"end":end.isoformat(),"events":rows,"count":len(rows)}

def report_for_task(thread_id,anchor=None):
    """Return a reporting-period snapshot using logged activity; no AI calls."""
    from datetime import timedelta
    t=get(thread_id)
    if not t or t.get("due_action")!="activity_report":raise ValueError("No activity-report action configured")
    config=t.get("action_config") or {}
    ref=datetime.fromisoformat(anchor.replace("Z","+00:00")) if anchor else datetime.now(timezone.utc)
    if ref.tzinfo is None:raise ValueError("Report anchor requires timezone")
    # Include the most recently finished interval at the due instant.
    result=activity_report(config.get("period","week"),(ref-timedelta(microseconds=1)).isoformat())
    category=config.get("category")
    if category:result["events"]=[event for event in result["events"] if category in category_names(event)]
    result["count"]=len(result["events"])
    result["category"]=category or None
    result["thread_id"]=thread_id
    return result

def configure_due_action(thread_id,action="activity_report",period="week",category=""):
    if not get(thread_id):raise ValueError("Thread not found")
    if action=="none":return update(thread_id,{"due_action":None,"action_config":{}})
    if action!="activity_report":raise ValueError("Unsupported action")
    return update(thread_id,{"due_action":"activity_report","action_config":{"period":period,"category":category}})

def set_recurrence(thread_id,frequency,next_occurrence,attention_mode=None,**options):
    """Choose recurring attention explicitly; omission preserves independent reminders."""
    if attention_mode not in (None,'occurrence','independent'):raise ValueError('Invalid recurrence attention mode')
    if attention_mode=='occurrence' and (not frequency or not next_occurrence):
        raise ValueError('Occurrence attention requires a recurring schedule')
    fields={'recurrence':frequency,'next_occurrence':next_occurrence,**options}
    if attention_mode=='occurrence':fields['revisit_at']=None
    return update(thread_id,fields)

def advance_occurrence(value,frequency):
    return recurrence_rules.at(value, frequency, 1)

def recurring_due():
    return [t for t in list_threads() if t['recurring_due']]

def complete_occurrence(thread_id,description="Completed recurring occurrence",occurrence_at=None):
    """Complete one identified cycle atomically; an unscoped retry never eats tomorrow."""
    stamp=now()
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        row=c.execute("SELECT * FROM threads WHERE id=?",(thread_id,)).fetchone()
        if not row or not row['recurrence']:raise ValueError("Not a recurring thread")
        t=dict(row);original=t['next_occurrence']
        reason=None
        if occurrence_at is not None and not recurrence_rules.equivalent(occurrence_at,original):reason='occurrence_changed'
        elif not original:reason='no_remaining_occurrence'
        elif t['state']=='settled' or t.get('archived_at'):reason='inactive'
        elif occurrence_at is None and not recurrence_rules.is_due(original,stamp):reason='not_due'
        if reason:
            completion={'completed':False,'occurrence_at':occurrence_at,'reason':reason}
        else:
            if not isinstance(description,str) or not description.strip():raise ValueError('Completion description required')
            next_date=recurrence_rules.next_after(t,stamp)
            c.execute("UPDATE threads SET next_occurrence=?,recurrence_anchor=COALESCE(recurrence_anchor,?),recurring_notified_for=NULL,updated_at=? WHERE id=?",(next_date,original,stamp,thread_id))
            if t.get('deferred_occurrence') and recurrence_rules.equivalent(t['deferred_occurrence'], original):
                c.execute('UPDATE threads SET revisit_at=NULL,snoozed_until=NULL,deferred_occurrence=NULL,notified_for=NULL WHERE id=?', (thread_id,))
            c.execute("INSERT INTO activity(id,thread_id,kind,body,occurred_at,recorded_at) VALUES(?,?,?,?,?,?)",(uuid4().hex,thread_id,'milestone',description,stamp,stamp))
            completion={'completed':True,'occurrence_at':original,'next_occurrence':next_date}
    return {**get(thread_id),'completion':completion}

def archive_thread(thread_id,archive=True):
    if not get(thread_id):raise ValueError("Thread not found")
    return update(thread_id,{"archived_at":now() if archive else None})

def archived_threads(q=""):
    return [t for t in list_threads(q) if t.get("archived_at")]


def action_notes(action_id):
    """Return notes for one real action; None distinguishes a missing action."""
    if not query("SELECT id FROM entries WHERE id=? AND kind='action'",(action_id,)):return None
    return query("SELECT * FROM action_notes WHERE action_id=? ORDER BY created_at,id",(action_id,))


def _note_body(body):
    if not isinstance(body,str) or not body.strip() or len(body)>20000:
        raise ValueError("A note must contain 1 to 20000 characters")
    return body.strip()


def add_action_note(action_id,body,note_id=None):
    """Attach a note to one action, not to the parent task or its siblings."""
    body=_note_body(body)
    note_id=note_id or uuid4().hex
    if not isinstance(note_id,str) or not 8<=len(note_id)<=100 or not all(ch.isalnum() or ch in '-_' for ch in note_id):
        raise ValueError("Invalid note ID")
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        parent=c.execute("SELECT thread_id FROM entries WHERE id=? AND kind='action'",(action_id,)).fetchone()
        if not parent:return None
        existing=c.execute("SELECT * FROM action_notes WHERE id=?",(note_id,)).fetchone()
        if existing:
            if existing['action_id']!=action_id or existing['body']!=body:raise ValueError("Note ID already belongs to different content")
            return dict(existing)
        stamp=now()
        c.execute("INSERT INTO action_notes VALUES(?,?,?,?,?)",(note_id,action_id,body,stamp,stamp))
        c.execute("UPDATE threads SET updated_at=? WHERE id=?",(stamp,parent['thread_id']))
        return dict(c.execute("SELECT * FROM action_notes WHERE id=?",(note_id,)).fetchone())


def update_action_note(action_id,note_id,body):
    body=_note_body(body)
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        changed=c.execute("UPDATE action_notes SET body=?,updated_at=? WHERE id=? AND action_id=?",(body,now(),note_id,action_id)).rowcount
        if not changed:return None
        c.execute("UPDATE threads SET updated_at=? WHERE id=(SELECT thread_id FROM entries WHERE id=?)",(now(),action_id))
        return dict(c.execute("SELECT * FROM action_notes WHERE id=?",(note_id,)).fetchone())


def delete_action_note(action_id,note_id):
    with conn() as c:
        changed=c.execute("DELETE FROM action_notes WHERE id=? AND action_id=?",(note_id,action_id)).rowcount
        if changed:c.execute("UPDATE threads SET updated_at=? WHERE id=(SELECT thread_id FROM entries WHERE id=?)",(now(),action_id))
    return bool(changed)
