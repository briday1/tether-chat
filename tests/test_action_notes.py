"""An action owns its notes independently of task notes and sibling actions."""
import pytest
from fastapi.testclient import TestClient
from tether import store, ai
from tether.app import app

@pytest.fixture
def fixture(tmp_path,monkeypatch):
    monkeypatch.setenv('TETHER_DB',str(tmp_path/'notes.sqlite3'))
    store.init()
    task=store.create('Prepare briefing',categories=['Projects'])
    first=store.add(task['id'],'action','Confirm access')
    other=store.add(task['id'],'action','Review attachment')
    return TestClient(app,base_url='http://127.0.0.1'),task,first,other

def test_action_notes_roundtrip_and_scope(fixture):
    client,task,first,other=fixture
    base=f'/api/actions/{first["id"]}/notes'
    response=client.post(base,json={'body':'Waiting on approval','note_id':'note-request-1'})
    assert response.status_code==201
    note=response.json()
    assert client.post(base,json={'body':'Waiting on approval','note_id':'note-request-1'}).json()['id']==note['id']
    assert len(client.get(base).json())==1
    assert client.get(f'/api/actions/{other["id"]}/notes').json()==[]
    assert client.patch(f'/api/actions/{other["id"]}/notes/{note["id"]}',json={'body':'Wrong action'}).status_code==404
    assert client.delete(f'/api/actions/{other["id"]}/notes/{note["id"]}').status_code==404
    assert client.patch(base+'/'+note['id'],json={'body':'Approval received'}).json()['body']=='Approval received'
    current=store.get(task['id']);a=next(e for e in current['entries'] if e['id']==first['id'])
    assert a['notes'][0]['body']=='Approval received'
    assert a['done']==0 and a['revisit_at'] is None and a['due_at'] is None
    assert current['revisit_at'] is None and current['due_at'] is None
    assert all(e['kind']=='action' for e in current['entries'])
    assert any(t['id']==task['id'] for t in store.list_threads('Approval received'))
    assert client.delete(base+'/'+note['id']).json()=={'deleted':True}
    assert client.get(base).json()==[]

def test_validation_cascade_and_migration(fixture):
    client,task,first,other=fixture
    assert client.post(f'/api/actions/{first["id"]}/notes',json={'body':'  '}).status_code==422
    assert client.post('/api/actions/missing/notes',json={'body':'Note'}).status_code==404
    task_note=store.add(task['id'],'thought','This is task-level')
    assert store.action_notes(task_note['id']) is None
    note=store.add_action_note(first['id'],'Preserved through migrations')
    store.init();store.init()
    assert store.action_notes(first['id'])[0]['id']==note['id']
    assert store.delete(task['id'])
    assert store.query('SELECT * FROM action_notes')==[]

def test_ai_and_attention_use_action_notes_only(fixture,monkeypatch):
    from tether import attention
    client,task,first,other=fixture
    result=ai.dispatch('add_action_note',{'action_id':first['id'],'text':'The request was sent on Monday.'})
    ai.dispatch('add_action_note',{'action_id':other['id'],'text':'This sibling detail must not leak.'})
    monkeypatch.setattr(ai,'public_config',lambda:{'has_key':False})
    answer=attention.check_in({'task_id':task['id'],'action_id':first['id']})['answer']
    assert 'request was sent on Monday' in answer and 'must not leak' not in answer
    ai.dispatch('update_action_note',{'action_id':first['id'],'note_id':result['id'],'text':'Revised detail'})
    assert store.action_notes(first['id'])[0]['body']=='Revised detail'
    ai.dispatch('delete_action_note',{'action_id':first['id'],'note_id':result['id']})
    assert store.action_notes(first['id'])==[]
