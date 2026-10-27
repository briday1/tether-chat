"""Live Attention reflects saved changes without calling the provider."""
import json
import pytest
from tend import ai, attention, store


@pytest.fixture
def records(tmp_path, monkeypatch):
    monkeypatch.setenv('TEND_DB', str(tmp_path/'attention.sqlite3'))
    store.init()
    monkeypatch.setattr(ai, '_attention_cache', {'items': [], 'revisions': {}})
    monkeypatch.setattr(ai, 'public_config', lambda: {'has_key': True})
    return monkeypatch


def test_live_refresh_uses_current_schedules_and_never_calls_ai(records):
    def unexpected(*args, **kwargs):raise AssertionError('Live refresh contacted AI')
    records.setattr(ai, 'request', unexpected)
    task=store.create('Original title')
    store.update(task['id'], {'revisit_at': '2020-01-01T12:00:00Z'})
    first=store.add(task['id'], 'action', 'First action')
    second=store.add(task['id'], 'action', 'Sibling action')
    for action in (first, second):store.update_action(action['id'], {'revisit_at': '2020-01-01T12:00:00Z'})
    assert len(attention.items()['items'])==3
    store.update_action(first['id'], {'done': True})
    store.update(task['id'], {'title': 'Current title'})
    current=attention.items()['items']
    assert not any(item.get('action_id')==first['id'] for item in current)
    assert next(item for item in current if item.get('action_id')==second['id'])['task_title']=='Current title'
    assert next(item for item in current if item['id']==task['id'])['title']=='Current title'
    store.update_action(second['id'], {'revisit_at': '2035-01-01T12:00:00Z'})
    store.update(task['id'], {'revisit_at': '2035-01-01T12:00:00Z'})
    assert attention.items()['items']==[]


def test_changed_suggestions_expire_without_hiding_other_items_or_due_reminders(records):
    first=store.create('Needs an update', 'Waiting for feedback')
    second=store.create('Another decision')
    calls=[]
    def choose(*args, **kwargs):
        calls.append(1)
        return {'choices': [{'message': {'content': json.dumps({'items': [
            {'id': first['id'], 'reason': 'Waiting for feedback'},
            {'id': second['id'], 'reason': 'Decision needed'}]})}}]}
    records.setattr(ai, 'request', choose)
    assert len(attention.items(True)['items'])==2
    store.update(first['id'], {'summary': 'Feedback received'})
    assert [item['id'] for item in attention.items()['items']]==[second['id']]
    store.update(first['id'], {'revisit_at': '2020-01-01T12:00:00Z'})
    assert len(attention.items()['items'])==2 and len(calls)==1


def test_reconsideration_cannot_restore_a_task_completed_during_the_request(records):
    task=store.create('Complete while reconsidering')
    def finish(*args, **kwargs):
        store.update(task['id'], {'state': 'settled'})
        return {'choices': [{'message': {'content': json.dumps({'items': [{'id': task['id'], 'reason': 'Old reason'}]})}}]}
    records.setattr(ai, 'request', finish)
    assert attention.items(True)['items']==[]
