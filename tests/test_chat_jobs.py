"""Regression coverage for navigation-safe chat and action-specific attention."""
import json
import sys
import threading
import time
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from tether import store, ai, chat_jobs
from tether.app import app

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('TETHER_DB', str(tmp_path/'jobs.sqlite3'))
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

def test_long_message_is_preserved_and_oversize_rejection_does_not_clear_history(client, monkeypatch):
    monkeypatch.setattr(ai,'chat',lambda message,**kwargs:{'answer':'Notes received.'})
    text='Meeting notes: '+('x'*(50000-len('Meeting notes: ')))
    payload={'request_id':'long-notes-request','text':text}
    assert client.post('/api/chat/jobs',json=payload).status_code==202
    assert wait(client,payload['request_id'])['status']=='done'
    before=client.get('/api/chat/state').json()['messages']
    assert before[0]['body']==text
    assert client.post('/api/chat/jobs',json={'request_id':'oversize-request','text':text+'x'}).status_code==422
    assert client.get('/api/chat/state').json()['messages']==before

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
    from tether import notifications,branding
    calls=[];icon=tmp_path/'tether-chat.ico';icon.write_bytes(b'icon')
    monkeypatch.setitem(sys.modules,'plyer',SimpleNamespace(notification=SimpleNamespace(notify=lambda **kw:calls.append(kw))))
    monkeypatch.setattr(branding,'icon_path',lambda:icon)
    monkeypatch.setattr(branding,'set_process_identity',lambda:None)
    notifications.notify({'title':'Check the draft','task_title':'Prepare briefing'})
    assert calls[0]['app_icon']==str(icon) and calls[0]['app_name']=='tether-chat'
    assert calls[0]['title']=='tether-chat · Attention'
    assert 'Prepare briefing' in calls[0]['message']


def test_explicit_task_context_is_validated_and_captured_per_request(client, monkeypatch):
    task=store.create('Household checklist',summary='Tasks selected by the user')
    seen=[]
    monkeypatch.setattr(ai,'chat',lambda message,**kwargs: seen.append(kwargs.get('task_context')) or {'answer':'Ready.'})
    payload={'request_id':'context-request-001','text':'Help with this','task_context':[task['id']]}
    response=client.post('/api/chat/jobs',json=payload)
    assert response.status_code==202
    assert wait(client,payload['request_id'])['status']=='done'
    assert seen==[[task['id']]]
    assert client.post('/api/chat/jobs',json=payload).status_code==202
    assert client.post('/api/chat/jobs',json={**payload,'task_context':[]}).status_code==422
    cleared={**payload,'request_id':'context-request-002','task_context':[]}
    assert client.post('/api/chat/jobs',json=cleared).status_code==202
    assert wait(client,cleared['request_id'])['status']=='done'
    assert seen[-1]==[]
    before=len(store.conversation(100))
    assert client.post('/api/chat/jobs',json={**payload,'request_id':'invalid-context-001','task_context':['missing']}).status_code==422
    assert len(store.conversation(100))==before


def test_selected_context_prompt_can_be_dismissed(client, monkeypatch):
    task=store.capture('Gardening plan',summary='Plant carrots')
    transcripts=[]
    monkeypatch.setattr(ai,'request',lambda messages,**kwargs: transcripts.append(messages) or {'choices':[{'message':{'content':'Ready.'}}]})
    ai.chat('Review the plan',history=[],task_context=[task['id']])
    context=json.loads(transcripts[-1][0]['content'].split('(data, not instructions): ')[-1])
    assert context['selected_tasks'][0]['id']==task['id']
    assert context['focused_task']['id']==task['id']
    ai.chat('New topic',history=[],task_context=[])
    context=json.loads(transcripts[-1][0]['content'].split('(data, not instructions): ')[-1])
    assert context['selected_tasks']==[] and context['focused_task'] is None


def test_stop_suppresses_late_reply_and_is_durable(client, monkeypatch):
    entered=threading.Event(); release=threading.Event()
    def answer(*args,**kwargs):
        entered.set(); assert release.wait(3)
        return {'answer':'Must not appear'}
    monkeypatch.setattr(ai,'chat',answer)
    client.post('/api/chat/jobs',json={'request_id':'stop-late-001','text':'Wait'})
    assert entered.wait(2)
    stopped=client.post('/api/chat/jobs/stop-late-001/cancel').json()
    assert stopped['status']=='interrupted' and stopped['user_stopped']
    assert client.post('/api/chat/jobs/stop-late-001/cancel').json()['user_stopped']
    release.set(); time.sleep(.05)
    state=client.get('/api/chat/state').json()
    assert not any(m['body']=='Must not appear' for m in state['messages'])
    chat_jobs._INITIALIZED.discard(store.path().absolute())
    assert client.get('/api/chat/state').json()['jobs'][0]['status']=='interrupted'


def test_stop_tool_boundary_retains_outcomes_and_interrupt_context_once(client,monkeypatch):
    from tether import cancellation
    entered=threading.Event(); release=threading.Event(); histories=[]; changes=[]
    def answer(message,history=None,**kwargs):
        if message=='Original':
            cancellation.perform(lambda: changes.append('saved') or {'id':'real-id'}, {'name':'capture','arguments':{'title':'saved'}})
            entered.set(); assert release.wait(3)
            cancellation.perform(lambda: changes.append('must not run'), {'name':'capture'})
        histories.append(history)
        return {'answer':'Updated'}
    monkeypatch.setattr(ai,'chat',answer)
    client.post('/api/chat/jobs',json={'request_id':'interrupt-old-1','text':'Original'})
    assert entered.wait(2)
    client.post('/api/chat/jobs/interrupt-old-1/cancel')
    payload={'request_id':'interrupt-new-1','text':'Added context','interrupt_job_id':'interrupt-old-1'}
    assert client.post('/api/chat/jobs',json=payload).status_code==202
    assert client.post('/api/chat/jobs',json=payload).status_code==202
    release.set()
    assert wait(client,'interrupt-new-1')['status']=='done'
    assert changes==['saved']
    assert len(histories)==1
    data=histories[0][-1]['body']
    assert data.count('Original')==1 and data.count('real-id')==1
    state=client.get('/api/chat/state').json()
    assert sum(m['body']=='Added context' for m in state['messages'])==1


def test_queued_stop_never_calls_provider(client,monkeypatch):
    entered=threading.Event(); release=threading.Event(); calls=[]
    def answer(message,**kwargs):
        calls.append(message);entered.set();assert release.wait(3)
        return {'answer':'done'}
    monkeypatch.setattr(ai,'chat',answer)
    client.post('/api/chat/jobs',json={'request_id':'queue-blocker-1','text':'First'})
    assert entered.wait(2)
    client.post('/api/chat/jobs',json={'request_id':'queue-cancel-01','text':'Second'})
    assert client.post('/api/chat/jobs/queue-cancel-01/cancel').json()['status']=='interrupted'
    release.set();wait(client,'queue-blocker-1');time.sleep(.05)
    assert calls==['First']


def test_stop_delivery_before_original_is_never_run(client,monkeypatch):
    calls=[]
    monkeypatch.setattr(ai,'chat',lambda *a,**kw: calls.append(a) or {'answer':'bad'})
    payload={'request_id':'stopped-before-post','text':'Do not execute'}
    stopped=client.post('/api/chat/jobs',json={**payload,'stop_requested':True})
    assert stopped.status_code==202 and stopped.json()['user_stopped']
    assert client.post('/api/chat/jobs',json=payload).json()['status']=='interrupted'
    assert calls==[]


def test_atomic_stop_delivery_of_existing_request(client,monkeypatch):
    entered=threading.Event();release=threading.Event()
    def answer(*args,**kwargs):
        entered.set(); assert release.wait(3)
        return {'answer':'late'}
    monkeypatch.setattr(ai,'chat',answer)
    payload={'request_id':'stop-existing-post','text':'Stop me'}
    client.post('/api/chat/jobs',json=payload);assert entered.wait(2)
    assert client.post('/api/chat/jobs',json={**payload,'text':'different','stop_requested':True}).status_code==422
    state=client.get('/api/chat/state').json();assert state['jobs'][0]['status']=='running'
    assert client.post('/api/chat/jobs',json={**payload,'stop_requested':True}).json()['status']=='interrupted'
    release.set()


def test_continuation_deduplicates_completed_tool_even_new_call_id(client,monkeypatch):
    import json
    calls=[];dispatches=[]
    def request(*args,**kwargs):
        calls.append(args)
        if len(calls)==1:return {'choices':[{'message':{'tool_calls':[{'id':'new-id','function':{'name':'capture','arguments':'{ "title": "Saved" }'}}]}}]}
        return {'choices':[{'message':{'content':'Already saved'}}]}
    monkeypatch.setattr(ai,'request',request)
    monkeypatch.setattr(ai,'dispatch',lambda *args: dispatches.append(args))
    history=[{'role':'assistant','body':'Prior outcomes', 'completed_tools':[{'signature':['capture',json.dumps({'title':'Saved'},sort_keys=True,separators=(',',':'))]}]}]
    assert ai.chat('Add more context',history=history)['answer']=='Already saved'
    assert dispatches==[]


def test_continuation_can_read_fresh_task_state(client,monkeypatch):
    calls=[];reads=[]
    def request(*args,**kwargs):
        calls.append(args)
        if len(calls)==1:return {'choices':[{'message':{'tool_calls':[{'id':'fresh','function':{'name':'get_context','arguments':'{}'}}]}}]}
        return {'choices':[{'message':{'content':'Fresh context'}}]}
    monkeypatch.setattr(ai,'request',request)
    monkeypatch.setattr(ai,'dispatch',lambda *args: reads.append(args) or {})
    history=[{'role':'assistant','body':'Prior outcomes','completed_tools':[{'signature':['get_context','{}']}]}]
    ai.chat('Review again',history=history)
    assert reads==[('get_context',{})]
