from datetime import datetime,timezone
import json
import pytest
from tend import store,ai
from tend.decisions import DEFAULT_PREFERENCES,resolve_reminder,reminder_intent,task_key
from tend.snapshots import snapshot
from tend.snapshot_export import svg
from tend.portable import export_data
from tend.tool_models import compatible_models,options

@pytest.fixture
def database(tmp_path,monkeypatch):
    monkeypatch.setenv('TEND_DB',str(tmp_path/'tasks.sqlite3'));store.init()


def test_default_choices_and_explicit_time():
    now=datetime(2026,10,28,15,tzinfo=timezone.utc)
    for text,expected in [('next day','2026-10-29T09:00:00+00:00'),('next week','2026-11-02T09:00:00+00:00'),('next month','2026-11-01T09:00:00+00:00'),('next year','2027-01-01T09:00:00+00:00')]:
        assert resolve_reminder(text,reference=now)==expected
    prefs={'week_start':0,'morning_time':'10:30','night_time':'22:15'}
    assert resolve_reminder('next week',prefs,now)=='2026-11-01T10:30:00+00:00'
    assert resolve_reminder('tomorrow night',prefs,now)=='2026-10-29T22:15:00+00:00'
    assert resolve_reminder('next week at 3pm',prefs,now)=='2026-11-01T15:00:00+00:00'
    assert reminder_intent('Remind me to call the dentist next week at 3pm')=='next week at 3pm'
    assert reminder_intent('What happened next week?') is None
    assert task_key('Book my dental appt')==task_key('Dentist appointment')


def test_preferences_persist_and_invalid_save_is_atomic(database):
    assert store.preferences()==DEFAULT_PREFERENCES
    store.set_preferences({'week_start':0,'morning_time':'10:30','night_time':'22:15'});store.init()
    assert store.preferences()['week_start']==0
    previous=store.preferences()
    with pytest.raises(ValueError):store.set_preferences({'morning_time':'25:00','week_start':4})
    assert store.preferences()==previous
    assert export_data()['data']['preferences']==previous
    assert store.assistant_context()['preferences']==previous


def test_capture_uses_existing_category_and_reuses_task(database):
    store.create('Annual checkup',categories=['Medical'])
    result=store.capture('Make a dentist appointment',remind_at='next week')
    assert result['categories']==['Medical'] and result['revisit_at'] and result['due_at'] is None
    same=store.capture('Dentist appointment',remind_at='next month')
    assert same['id']==result['id'] and same['reused'] is True
    assert len(store.list_threads())==2
    assert same['revisit_at']!=result['revisit_at']
    other=store.capture('Repair garden fence',categories=['Unsorted'])
    assert other['categories']==['Home']
    old=store.create('Prescription pickup')
    assert store.capture('Prescription pickup')['id']==old['id']
    assert store.get(old['id'])['categories']==['Medical']
    store.update(old['id'],{'categories':['Errands']})
    assert store.capture('Prescription pickup',categories=['Medical'])['categories']==['Errands']


def test_followup_cannot_capture_a_second_copy(database,monkeypatch):
    task=store.capture('Dentist appointment')
    replies=iter([
        {'choices':[{'message':{'content':None,'tool_calls':[{'id':'one','function':{'name':'capture','arguments':json.dumps({'title':'Dentist appointment next Monday','remind_at':'next week'})}}]}}]},
        {'choices':[{'message':{'content':'Scheduled.'}}]},
    ])
    monkeypatch.setattr(ai,'request',lambda *a,**k:next(replies))
    ai.chat('Just figure it out',history=[])
    assert len(store.list_threads())==1
    assert store.get(task['id'])['revisit_at']
    assert store.get(task['id'])['categories']==['Health']


def test_reminder_request_recovers_from_an_unnecessary_question(database,monkeypatch):
    replies=iter([
        {'choices':[{'message':{'content':'Which day next week?'}}]},
        {'choices':[{'message':{'content':None,'tool_calls':[{'id':'one','function':{'name':'capture','arguments':'{"title":"Dentist appointment"}'}}]}}]},
        {'choices':[{'message':{'content':'Scheduled.'}}]},
    ])
    monkeypatch.setattr(ai,'request',lambda *a,**k:next(replies))
    result=ai.chat('Remind me to make a dentist appointment next week',history=[])
    assert result['answer']=='Scheduled.'
    task=store.list_threads()[0]
    assert task['categories']==['Health'] and task['revisit_at'] and not task['due_at']


def test_snapshots_include_task_action_and_recurring_reminders(database):
    t=store.create('Dentist',categories=['Health'])
    store.update(t['id'],{'revisit_at':'2026-11-02T09:00:00Z','due_at':'2026-11-02T12:00:00Z','recurrence':'monthly','next_occurrence':'2026-11-03T09:00:00Z'})
    a=store.add(t['id'],'action','Call reception');store.update_action(a['id'],{'revisit_at':'2026-11-04T09:00:00Z'})
    store.set_preferences({'week_start':0})
    result=snapshot('2026-11-01','2026-11-07');rows=[r for d in result['days'] for r in d['tasks']]
    assert len(rows)==3 and result['week_start']==0
    combined=next(r for r in rows if r['date']=='2026-11-02')
    assert combined['schedule_label']=='Due · Reminder'
    action=next(r for r in rows if r['action_id'])
    assert action['title']=='Call reception' and action['href'].endswith('/'+a['id'])
    assert action['categories']==['Health'] and action['schedule_label']=='Reminder'
    assert 'Reminder' in svg('2026-11-01','2026-11-07')
    store.archive_thread(t['id'])
    assert snapshot('2026-11-01','2026-11-07')['insights']['scheduled_due']==0


def test_model_list_only_advertises_compatible_tool_models():
    models=[{'id':'gpt-4.1-mini'},{'id':'gpt-4.1-mini-2025-04-14'},{'id':'gpt-6-luna'},{'id':'gpt-6.1-sol'},{'id':'gpt-6.1-terra'},{'id':'text-embedding-3-small'},{'id':'unknown-model'},{'id':'gpt-4o','capabilities':{'tool_calling':False}}]
    assert compatible_models(models,'https://api.openai.com/v1')==['gpt-4.1-mini','gpt-4.1-mini-2025-04-14','gpt-6-luna']
    assert options('https://api.openai.com/v1','gpt-6-luna')=={'reasoning_effort':'none'}
    custom=[{'id':'gpt-4.1-mini'},{'id':'gpt-4o','supports_tool_calling':False},{'id':'unknown'},{'id':'supported','supported_parameters':['tools']},{'id':'capable','capabilities':{'function_calling':True}},{'id':'disabled','supports_tool_calling':False,'supported_parameters':['tools']}]
    assert compatible_models(custom,'https://provider.test/v1')==['capable','gpt-4.1-mini','supported']
