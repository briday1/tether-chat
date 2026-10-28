"""Credential-free, portable JSON export for moving desktop data to the browser edition."""
from datetime import datetime, timezone
import json
from . import store


def _stamp(value):
    if not value:
        return value
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return date.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def export_data():
    """Read a consistent SQLite snapshot; provider settings and chat jobs are excluded."""
    store.init()
    with store.conn() as connection:
        connection.execute('BEGIN')
        read = lambda table: [dict(row) for row in connection.execute('SELECT * FROM ' + table)]
        tasks, memberships = read('threads'), read('thread_categories')
        for task in tasks:
            task['categories'] = [row['name'] for row in sorted(memberships, key=lambda r: r['position'])
                                  if row['thread_id'] == task['id']] or [task.get('category') or 'Unsorted']
            task['action_config'] = json.loads(task.get('action_config') or '{}')
        entries = read('entries')
        for entry in entries:
            entry['done'] = bool(entry['done'])
        data = {'tasks': tasks, 'entries': entries, 'notes': read('action_notes'),
                'activity': read('activity'), 'relations': read('relations'), 'messages': read('conversation')}
    for table in data.values():
        for row in table:
            for key in ('created_at', 'updated_at', 'occurred_at', 'recorded_at', 'due_at', 'revisit_at',
                        'next_occurrence', 'archived_at'):
                if key in row:
                    row[key] = _stamp(row[key])
    data['preferences']=store.preferences()
    return {'format': 'tether-chat', 'version': 1, 'exported_at': _stamp(store.now()), 'data': data}
