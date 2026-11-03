"""Task-list mutations use the same lifecycle rules as assistant tools."""
import pytest
from fastapi.testclient import TestClient

from tether import ai, store
from tether.app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('TETHER_DB', str(tmp_path / 'task-controls.sqlite3'))
    monkeypatch.setattr(ai, 'public_config', lambda: {'has_key': False})
    store.init()
    return TestClient(app, base_url='http://127.0.0.1')


def test_list_completion_archives_and_undo_restores_only_open_actions(client):
    task = store.create('Finish the application')
    pending = store.add(task['id'], 'action', 'Attach supporting documents')
    finished = store.add(task['id'], 'action', 'Fill out the form')
    store.update_action(finished['id'], {'done': True})
    store.add_action_note(pending['id'], 'Keep the originals for reference.')
    store.update(task['id'], {'due_at': '2035-01-06'})

    response = client.post(f"/api/threads/{task['id']}/complete", json={'done': True})
    assert response.status_code == 200
    assert response.json()['state'] == 'settled'
    assert response.json()['archived_at']
    assert all(entry['done'] for entry in response.json()['entries'])
    assert not any(task['id'] == item['id'] for group in client.get('/api/board').json()
                   for item in group['threads'])
    assert client.get('/api/archived').json()[0]['id'] == task['id']

    reopened = client.post(f"/api/threads/{task['id']}/complete", json={'done': False}).json()
    assert reopened['state'] == 'open' and not reopened['archived_at']
    assert reopened['due_at'] == '2035-01-06'
    entries = {entry['id']: entry for entry in reopened['entries']}
    assert not entries[pending['id']]['done'] and entries[finished['id']]['done']
    assert entries[pending['id']]['notes'][0]['body'] == 'Keep the originals for reference.'


def test_defer_endpoints_preserve_deadlines_and_scope(client):
    task = store.create('Prepare the review')
    store.update(task['id'], {'due_at': '2020-01-01', 'revisit_at': '2020-01-01T09:00:00Z'})
    first = store.add(task['id'], 'action', 'Review the draft')
    sibling = store.add(task['id'], 'action', 'Send the packet')
    for action in (first, sibling):
        store.update_action(action['id'], {'due_at': '2020-01-01', 'revisit_at': '2020-01-01T09:00:00Z'})
    original = store.get(task['id'])

    response = client.post(f"/api/threads/{task['id']}/defer", json={'when': '2035-03-02T09:00:00-05:00'})
    assert response.status_code == 200
    deferred = response.json()
    assert deferred['due_at'] == original['due_at']
    assert deferred['snoozed_until'] == deferred['revisit_at'] == '2035-03-02T14:00:00+00:00'
    assert deferred['entries'] == original['entries']
    assert not any(item['task_id'] == task['id'] for item in client.get('/api/attention').json()['items'])

    resumed = client.post(f"/api/threads/{task['id']}/defer", json={'when': None}).json()
    assert not resumed['snoozed_until'] and resumed['due_at'] == '2020-01-01'
    parent_reminder = resumed['revisit_at']
    response = client.post(f"/api/actions/{first['id']}/defer", json={'when': '2035-03-03T14:00:00Z'})
    assert response.status_code == 200
    assert response.json()['due_at'] == '2020-01-01'
    assert response.json()['snoozed_until']
    result = store.get(task['id'])
    assert result['revisit_at'] == parent_reminder
    assert next(a for a in result['entries'] if a['id'] == sibling['id']) == original['entries'][1]
    ids = {item.get('action_id') for item in client.get('/api/attention').json()['items']}
    assert first['id'] not in ids and sibling['id'] in ids


def test_invalid_list_mutations_fail_without_changing_data(client):
    task = store.create('Recurring check-in')
    store.update(task['id'], {'recurrence': 'weekly', 'next_occurrence': '2035-01-01'})
    original = store.get(task['id'])
    assert client.post(f"/api/threads/{task['id']}/complete", json={'done': True}).status_code == 422
    assert client.post(f"/api/threads/{task['id']}/defer", json={}).status_code == 422
    assert client.post(f"/api/threads/{task['id']}/defer", json={'when': 'not a date'}).status_code == 422
    assert client.post('/api/threads/missing/complete', json={'done': True}).status_code == 404
    assert client.post('/api/actions/missing/defer', json={'when': None}).status_code == 404
    assert store.get(task['id']) == original
