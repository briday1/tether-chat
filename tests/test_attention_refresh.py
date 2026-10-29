"""Live Attention reflects saved changes without calling the provider."""
import json
import pytest
from tether import ai, attention, store


@pytest.fixture
def records(tmp_path, monkeypatch):
    monkeypatch.setenv('TETHER_DB', str(tmp_path/'attention.sqlite3'))
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


def test_attention_suggestions_do_not_cross_database_paths(tmp_path,monkeypatch):
    """Copied/imported IDs must not leak suggestions between Home and Work."""
    task={'id':'same-imported-id','title':'Shared old title','summary':'','state':'open','due':False,'updated_at':'2026-01-01','revisit_at':None,'recurrence':None}
    monkeypatch.setattr(store,'list_threads',lambda:[task])
    monkeypatch.setattr(store,'query',lambda *a,**k:[])
    monkeypatch.setattr(ai,'public_config',lambda:{'has_key':True})
    monkeypatch.setattr(ai,'request',lambda *a,**k:{'choices':[{'message':{'content':'{"items":[{"id":"same-imported-id","reason":"Work-only suggestion"}]}'}}]})
    monkeypatch.setattr(store,'path',lambda:tmp_path/'work.sqlite3')
    assert ai.attention(force=True)['items'][0]['reason']=='Work-only suggestion'
    monkeypatch.setattr(store,'path',lambda:tmp_path/'home.sqlite3')
    assert ai.attention()['items']==[]


def test_completed_children_cannot_be_reselected_as_parent_attention(records):
    task=store.create('Parent', 'Follow up on the child action')
    action=store.add(task['id'], 'action', 'Child')
    store.update_action(action['id'], {'done': True})
    records.setattr(ai, 'request', lambda *a, **k: {'choices':[{'message':{'content':json.dumps({'items':[{'id':task['id'],'reason':'Child needs attention'}]})}}]})
    assert attention.items(True)['items']==[]
    store.update(task['id'], {'revisit_at':'2020-01-01T12:00:00Z'})
    assert [i['id'] for i in attention.items()['items']]==[task['id']]


def test_future_scheduled_task_cannot_be_promoted_by_curation(records):
    task=store.create('Tomorrow, not today')
    store.update(task['id'], {'recurrence':'daily','next_occurrence':'2035-01-01'})
    records.setattr(ai, 'request', lambda *a, **k: {'choices':[{'message':{'content':json.dumps({'items':[{'id':task['id'],'reason':'Due today'}]})}}]})
    assert attention.items(True)['items']==[]
    store.update(task['id'], {'due_at':'2020-01-01'})
    assert [i['id'] for i in attention.items()['items']]==[task['id']]


def test_child_change_invalidates_parent_suggestion_even_with_same_clock(records):
    records.setattr(store, 'now', lambda:'2026-10-29T18:00:00+00:00')
    task=store.create('Parent')
    action=store.add(task['id'],'action','Child')
    records.setattr(ai, 'request', lambda *a, **k: {'choices':[{'message':{'content':json.dumps({'items':[{'id':task['id'],'reason':'Child needs attention'}]})}}]})
    assert attention.items(True)['items']
    store.update_action(action['id'], {'revisit_at':'2035-01-01T12:00:00Z'})
    assert attention.items()['items']==[]


def test_rescheduled_children_do_not_recreate_parent_attention(records):
    task=store.create('Parent')
    child=store.add(task['id'],'action','Child')
    store.update_action(child['id'],{'revisit_at':'2035-01-01T12:00:00Z'})
    records.setattr(ai,'request',lambda *a,**k:{'choices':[{'message':{'content':json.dumps({'items':[{'id':task['id'],'reason':'Child due'}]})}}]})
    assert attention.items(True)['items']==[]
