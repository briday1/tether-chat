"""Regression coverage for navigation-safe chat and action-specific attention."""
import json
import sys
import threading
import time
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from tend import store, ai, chat_jobs
from tend.app import app

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('TEND_DB', str(tmp_path/'jobs.sqlite3'))
    monkeypatch.setattr(ai, 'public_config', lambda: {'has_key': False})
    store.init()
    return TestClient(app, base_url='http://127.0.0.1')

def wait(client, request_id):
    for _ in range(150):
        state=client.get('/api/chat/state').json()
        job=next(j for j in state['jobs'] if j['id']==request_id)
        if job['status'] not in ('queued','running'):return job
        time.sleep(.02)
    raise AssertionError('Job never completed')

def test_pending_chat_survives_navigation_and_same_id_is_not_repeated(client, monkeypatch):
    entered=threading.Event();release=threading.Event();calls=[]
    def answer(message, progress=None, history=None):
        calls.append(message);progress('Reading task context');entered.set()
        assert release.wait(3)
        return {'answer':'Reply survived the page change.'}
    monkeypatch.setattr(ai,'chat',answer)
    payload={'request_id':'navigation-request-1','text':'Keep working while I use Tasks'}
    try:
        first=client.post('/api/chat/jobs',json=payload)
        assert first.status_code==202 and entered.wait(2)
        assert client.get('/board').status_code==200
        second=TestClient(app,base_url='http://127.0.0.1')
        state=second.get('/api/chat/state').json()
        assert state['jobs'][0]['status']=='running'
        assert state['messages'][0]['body']==payload['text']
        assert second.post('/api/chat/jobs',json=payload).json()['id']==first.json()['id']
    finally:release.set()
    assert wait(client,payload['request_id'])['status']=='done'
    messages=client.get('/api/chat/state').json()['messages']
    assert [m['role'] for m in messages]==['user','assistant'] and len(calls)==1

def test_queue_is_serial_and_future_messages_do_not_leak_into_context(client, monkeypatch):
    histories=[]
    def answer(message, progress=None, history=None):
        histories.append((message,history));return {'answer':'Reply to '+message}
    monkeypatch.setattr(ai,'chat',answer)
    for n in (1,2):assert client.post('/api/chat/jobs',json={'request_id':f'queued-request-{n}','text':f'Message {n}'}).status_code==202
    assert wait(client,'queued-request-2')['status']=='done'
    assert [r[0] for r in histories]==['Message 1','Message 2']
    assert not any(r['body']=='Message 2' for _,history in histories for r in history)
    assert any(r['body']=='Reply to Message 1' for r in histories[1][1])

def test_attention_is_scoped_and_click_does_not_modify_items(client):
    task=store.create('S3 bucket setup',summary='Confirm the contract and access status.',categories=['Projects'])
    action=store.add(task['id'],'action','Contact the review team')
    sibling=store.add(task['id'],'action','Prepare the document')
    store.update_action(action['id'],{'revisit_at':'2020-01-01T12:00:00Z'})
    items=client.get('/api/attention').json()['items']
    notice=next(i for i in items if i.get('action_id')==action['id'])
    assert notice['task_id']==task['id']
    before=store.get(task['id'])
    payload={'request_id':'attention-request-1','attention':{'task_id':task['id'],'action_id':action['id']}}
    assert client.post('/api/chat/jobs',json=payload).status_code==202
    result=wait(client,'attention-request-1')
    assert result['status']=='done'
    assert action['id'] in result['result']['answer'] and '?' in result['result']['answer']
    assert store.get(task['id'])==before
    other=store.create('Another task')
    invalid={**payload,'request_id':'attention-request-2','attention':{'task_id':other['id'],'action_id':action['id']}}
    assert client.post('/api/chat/jobs',json=invalid).status_code==422

def test_failed_and_interrupted_requests_are_not_automatically_replayed(client, monkeypatch):
    def fail(*args,**kwargs):raise ValueError('Provider timed out')
    monkeypatch.setattr(ai,'chat',fail)
    client.post('/api/chat/jobs',json={'request_id':'failed-request-1','text':'Check task'})
    assert wait(client,'failed-request-1')['status']=='error'
    path=store.path().absolute()
    with chat_jobs.connection(path) as db:db.execute("UPDATE chat_jobs SET status='running' WHERE id='failed-request-1'")
    chat_jobs._INITIALIZED.discard(path)
    state=client.get('/api/chat/state').json()
    assert state['jobs'][0]['status']=='interrupted'
    assert 'may have been saved' in state['jobs'][0]['error']

def test_notification_has_tether_icon_and_brand(monkeypatch,tmp_path):
    from tend import notifications,branding
    calls=[];icon=tmp_path/'tether-chat.ico';icon.write_bytes(b'icon')
    monkeypatch.setitem(sys.modules,'plyer',SimpleNamespace(notification=SimpleNamespace(notify=lambda **kw:calls.append(kw))))
    monkeypatch.setattr(branding,'icon_path',lambda:icon)
    monkeypatch.setattr(branding,'set_process_identity',lambda:None)
    notifications.notify({'title':'Check the draft','task_title':'Prepare briefing'})
    assert calls[0]['app_icon']==str(icon) and calls[0]['app_name']=='tether-chat'
    assert calls[0]['title']=='tether-chat · Attention'
    assert 'Prepare briefing' in calls[0]['message']
