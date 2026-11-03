"""Portable exports retain deferred timing and reversible task completion."""
from tether import store
from tether.portable import export_data


def test_desktop_export_preserves_lifecycle_and_calendar_identity(tmp_path, monkeypatch):
    monkeypatch.setenv('TETHER_DB', str(tmp_path/'portable.sqlite3'))
    store.init()
    task = store.create('Weekly paperwork')
    action = store.add(task['id'], 'action', 'Get signature')
    prior = store.add(task['id'], 'action', 'Find the form')
    with store.conn() as connection:
        connection.execute("""UPDATE threads SET recurrence='weekly', next_occurrence='2026-11-03',
            due_at='2026-11-03', snoozed_until='2026-11-04T09:00:00-05:00',
            deferred_occurrence='2026-11-03' WHERE id=?""", (task['id'],))
        connection.execute("""UPDATE entries SET done=1, completed_by_task=1,
            snoozed_until='2026-11-04T09:00:00-05:00', due_at='2026-11-03' WHERE id=?""", (action['id'],))
        connection.execute('UPDATE entries SET done=1 WHERE id=?', (prior['id'],))
    data = export_data()['data']
    saved = data['tasks'][0]
    assert saved['snoozed_until'] == '2026-11-04T14:00:00.000Z'
    assert saved['deferred_occurrence'] == saved['next_occurrence'] == '2026-11-03'
    assert saved['due_at'] == '2026-11-03'
    entries = {entry['id']: entry for entry in data['entries']}
    assert entries[action['id']]['snoozed_until'] == '2026-11-04T14:00:00.000Z'
    assert entries[action['id']]['completed_by_task'] is True
    assert entries[prior['id']]['completed_by_task'] is False
    assert entries[action['id']]['done'] is True
    assert entries[action['id']]['due_at'] == '2026-11-03'


def test_desktop_export_normalizes_linked_occurrence_instants_together(tmp_path, monkeypatch):
    monkeypatch.setenv('TETHER_DB', str(tmp_path/'portable-instant.sqlite3'))
    store.init()
    task = store.create('Timed review')
    with store.conn() as connection:
        connection.execute("""UPDATE threads SET recurrence='weekly',
            next_occurrence='2026-11-03T09:00:00-05:00',
            deferred_occurrence='2026-11-03T09:00:00-05:00' WHERE id=?""", (task['id'],))
    saved = export_data()['data']['tasks'][0]
    assert saved['deferred_occurrence'] == saved['next_occurrence'] == '2026-11-03T14:00:00.000Z'
