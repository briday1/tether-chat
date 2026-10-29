"""Recurrences are bounded calendar projections, not additional persisted tasks."""
import sqlite3
import pytest
from fastapi.testclient import TestClient
from tether import store
from tether.app import app
from tether.recurrence import at, occurrences, next_after
from tether.snapshots import snapshot

@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv('TETHER_DB', str(tmp_path/'recurrence.sqlite3'))
    store.init()
    monkeypatch.setattr(store, 'now', lambda: '2026-01-31T13:00:00+00:00')


def task(**extra):
    return {'state':'open','recurrence':'monthly','next_occurrence':'2026-01-31T12:00:00+00:00', **extra}


def test_month_end_anchor_and_leap_year():
    assert at('2026-01-31', 'monthly', 1) == '2026-02-28'
    assert at('2026-01-31', 'monthly', 2) == '2026-03-31'
    assert at('2024-02-29', 'yearly', 1) == '2025-02-28'
    assert at('2024-02-29', 'yearly', 4) == '2028-02-29'
    assert at('2026-01-31', 'quarterly', 1) == '2026-04-30'
    assert at('2026-01-31', 'quarterly', 2) == '2026-07-31'


def test_weekly_and_daily_date_only_stay_date_only():
    assert list(occurrences(task(recurrence='weekly',next_occurrence='2026-10-26'), '2026-11-01','2026-11-30')) == ['2026-11-02','2026-11-09','2026-11-16','2026-11-23','2026-11-30']
    assert list(occurrences(task(recurrence='daily',next_occurrence='2026-01-01',recurrence_end='2026-01-03'),'2026-01-01','2026-01-05')) == ['2026-01-01','2026-01-02','2026-01-03']


def test_dst_named_zone_gap_fold_and_legacy_offset():
    assert at('2026-03-07T09:00:00-05:00','daily',1,'America/New_York') == '2026-03-08T09:00:00-04:00'
    assert at('2026-03-07T02:30:00-05:00','daily',1,'America/New_York') == '2026-03-08T03:30:00-04:00'
    assert at('2026-03-07T02:30:00-05:00','daily',2,'America/New_York') == '2026-03-09T02:30:00-04:00'
    assert at('2026-10-31T01:30:00-04:00','daily',1,'America/New_York') == '2026-11-01T01:30:00-04:00'
    assert at('2026-03-07T09:00:00-05:00','daily',1) == '2026-03-08T09:00:00-05:00'


def test_old_daily_rules_seek_without_backlog():
    values=list(occurrences(task(recurrence='daily',next_occurrence='1900-01-01'), '2026-11-01','2026-11-30'))
    assert len(values)==30 and values[0]=='2026-11-01'
    assert next_after(task(recurrence='daily',next_occurrence='1900-01-01'), '2026-11-30T15:00:00+00:00') == '2026-12-01'


def test_projection_snapshot_has_one_identity_no_writes(database):
    t=store.create('Rent')
    store.update(t['id'],{'recurrence':'monthly','next_occurrence':'2026-01-31','recurrence_end':'2026-04-30'})
    before=store.get(t['id'])
    rows=[t for day in snapshot('2026-01-01','2026-05-31')['days'] for t in day['tasks']]
    assert [r['date'] for r in rows]==['2026-01-31','2026-02-28','2026-03-31','2026-04-30']
    assert {r['task_id'] for r in rows}=={t['id']}
    assert rows[1]['occurrence_at']=='2026-02-28' and rows[1]['is_projection']
    assert rows[0]['schedule_kinds']==['recurrence']
    assert store.get(t['id'])==before and len(store.list_threads())==1
    store.update(t['id'],{'state':'settled'})
    assert snapshot('2026-02-01','2026-02-28')['insights']['scheduled_due']==0


def test_completion_keeps_anchor_and_stops_at_inclusive_end(database,monkeypatch):
    t=store.create('Monthly')
    t=store.update(t['id'],{'recurrence':'monthly','next_occurrence':'2026-01-31','recurrence_end':'2026-03-31'})
    t=store.complete_occurrence(t['id'],occurrence_at=t['next_occurrence'])
    assert t['next_occurrence']=='2026-02-28' and t['recurrence_anchor']=='2026-01-31'
    # A routine form save must not reset the anchor to February 28.
    t=store.update(t['id'],{'recurrence':'monthly','next_occurrence':'2026-02-28','summary':'Edited'})
    t=store.complete_occurrence(t['id'],occurrence_at=t['next_occurrence'])
    assert t['next_occurrence']=='2026-03-31'
    t=store.complete_occurrence(t['id'],occurrence_at=t['next_occurrence'])
    assert t['next_occurrence'] is None and t['recurrence']=='monthly'
    assert len(t['activity'])==3
    assert snapshot('2026-04-01','2026-04-30')['insights']['scheduled_due']==0


def test_schedule_edit_resets_anchor_and_clear_resets_fields(database):
    t=store.create('Edit repeat')
    store.update(t['id'],{'recurrence':'monthly','next_occurrence':'2026-01-31'})
    changed=store.update(t['id'],{'next_occurrence':'2026-02-15'})
    assert changed['recurrence_anchor']=='2026-02-15'
    cleared=store.update(t['id'],{'recurrence':None})
    assert all(cleared[key] is None for key in ('recurrence','next_occurrence','recurrence_anchor','recurrence_end','recurrence_timezone'))


def test_api_date_only_and_validation(database):
    client=TestClient(app,base_url='http://127.0.0.1')
    t=store.create('API repeat');url='/api/threads/'+t['id']
    response=client.patch(url,json={'recurrence':'daily','next_occurrence':'2026-02-01','recurrence_end':'2026-02-03'})
    assert response.status_code==200 and response.json()['next_occurrence']=='2026-02-01'
    for fields in ({'recurrence_end':'2026-02-30'},{'recurrence_end':'2026-01-31'},{'recurrence_timezone':'Invalid/Zone'},{'next_occurrence':'2026-02-01T09:00:00'},{'recurrence':'weekdays'}):
        assert client.patch(url,json=fields).status_code==422


def test_migration_old_task_no_anchor(database):
    t=store.create('Legacy')
    with store.conn() as c:
        c.execute("UPDATE threads SET recurrence='monthly',next_occurrence='2026-01-31' WHERE id=?",(t['id'],))
        for column in ('recurrence_anchor','recurrence_end','recurrence_timezone'):
            c.execute(f'ALTER TABLE threads DROP COLUMN {column}')
    store.init()
    assert store.get(t['id'])['recurrence_anchor'] is None
    rows=[r for d in snapshot('2026-03-01','2026-03-31')['days'] for r in d['tasks']]
    assert rows[0]['date']=='2026-03-31'
    assert store.complete_occurrence(t['id'])['recurrence_anchor']=='2026-01-31'


def test_offset_due_order_and_equivalent_edit(database,monkeypatch):
    monkeypatch.setattr(store,'now',lambda:'2026-01-31T12:00:00+00:00')
    t=store.create('Offset')
    store.update(t['id'],{'recurrence':'daily','next_occurrence':'2026-01-31T09:00:00-05:00'})
    assert not store.list_threads()[0]['recurring_due']
    assert not store.recurring_due()
    store.update(t['id'],{'next_occurrence':'2026-01-31T14:00:00+05:00'})
    assert store.list_threads()[0]['recurring_due']
    assert store.recurring_due()[0]['id']==t['id']
    original=store.get(t['id'])['recurrence_anchor']
    store.update(t['id'],{'next_occurrence':'2026-01-31T09:00:00Z'})
    assert store.get(t['id'])['recurrence_anchor']==original
    store.archive_thread(t['id'])
    assert not store.list_threads()[0]['recurring_due']
    assert not store.recurring_due()


def test_second_fold_anchor_is_not_lost():
    anchor='2026-11-01T01:30:00-05:00'
    assert at(anchor,'daily',0,'America/New_York')==anchor
    rows=list(occurrences(task(recurrence='daily',next_occurrence=anchor,recurrence_timezone='America/New_York'),'2026-11-01','2026-11-02'))
    assert rows==[anchor,'2026-11-02T01:30:00-05:00']


def test_legacy_next_without_rule_remains_a_reminder(database):
    t=store.create('Legacy next')
    with store.conn() as c:c.execute('UPDATE threads SET next_occurrence=? WHERE id=?',('2026-02-03',t['id']))
    rows=[r for d in snapshot('2026-02-01','2026-02-28')['days'] for r in d['tasks']]
    assert len(rows)==1 and rows[0]['next_occurrence']=='2026-02-03'
    assert rows[0]['schedule_kinds']==['reminder']


def test_end_is_schedule_local_date_not_viewer_utc_day():
    rule=task(recurrence='daily',next_occurrence='2026-10-31T23:30:00-04:00',recurrence_timezone='America/New_York',recurrence_end='2026-11-01')
    values=list(occurrences(rule,'2026-10-31','2026-11-03'))
    assert values==['2026-10-31T23:30:00-04:00','2026-11-01T23:30:00-05:00']


def test_date_only_follows_viewer_local_day(monkeypatch):
    import os,time
    from tether.recurrence import is_due
    if not hasattr(time,'tzset'):pytest.skip('tzset unavailable on Windows')
    original=os.environ.get('TZ')
    try:
        monkeypatch.setenv('TZ','America/Los_Angeles');time.tzset()
        assert not is_due('2026-11-01','2026-11-01T01:00:00+00:00')
        assert next_after(task(recurrence='daily',next_occurrence='2026-10-01'),'2026-11-01T01:00:00+00:00')=='2026-11-01'
        assert list(occurrences(task(recurrence='daily',next_occurrence='2026-11-01'),'2026-11-01','2026-11-02'))==['2026-11-01','2026-11-02']
    finally:
        if original is None:os.environ.pop('TZ',None)
        else:os.environ['TZ']=original
        time.tzset()


def test_completion_retry_does_not_consume_tomorrow(database):
    t=store.create('Daily')
    store.update(t['id'],{'recurrence':'daily','next_occurrence':'2026-01-31'})
    first=store.complete_occurrence(t['id'],occurrence_at=t['next_occurrence'])
    repeated=store.complete_occurrence(t['id'])
    assert first['next_occurrence']==repeated['next_occurrence']=='2026-02-01'
    assert len(repeated['activity'])==1
    assert repeated['completion']['completed'] is False


def test_explicit_occurrence_identity_is_idempotent_and_preserves_independent_dates(database):
    t=store.create('Monthly identity')
    store.update(t['id'],{'recurrence':'monthly','next_occurrence':'2026-01-31','recurrence_end':'2026-02-28',
                         'due_at':'2026-01-31','revisit_at':'2026-01-31T12:00:00+00:00'})
    first=store.complete_occurrence(t['id'],occurrence_at='2026-01-31')
    repeated=store.complete_occurrence(t['id'],occurrence_at='2026-01-31')
    assert repeated['next_occurrence']=='2026-02-28' and len(repeated['activity'])==1
    assert first['completion']['occurrence_at']=='2026-01-31'
    assert repeated['due_at']=='2026-01-31' and repeated['revisit_at']=='2026-01-31T12:00:00+00:00'
    done=store.complete_occurrence(t['id'],occurrence_at='2026-02-28')
    assert done['next_occurrence'] is None
    assert len(store.complete_occurrence(t['id'],occurrence_at='2026-02-28')['activity'])==2


def test_explicit_future_attention_wins_over_due_recurrence(database):
    t=store.create('Evening reminder')
    store.update(t['id'],{'recurrence':'daily','next_occurrence':'2026-01-31','revisit_at':'2026-01-31T21:00:00+00:00'})
    assert store.list_threads()[0]['due'] is False
    assert store.recurring_due()==[]
    store.update(t['id'],{'revisit_at':None})
    assert store.list_threads()[0]['due'] is True


def test_due_flags_compare_instants_not_offset_text(database):
    t=store.create('Offset')
    store.update(t['id'],{'due_at':'2026-01-31T10:00:00-05:00','revisit_at':'2026-01-31T10:00:00-05:00'})
    assert not store.list_threads()[0]['due'] and store.list_threads()[0]['deadline_due']
    store.update(t['id'],{'due_at':'2026-01-31T15:00:00+05:00','revisit_at':'2026-01-31T15:00:00+05:00'})
    assert store.list_threads()[0]['due'] and store.list_threads()[0]['deadline_due']


def test_deadline_date_survives_api_and_is_due_all_day(database):
    t=store.create('Date deadline')
    client=TestClient(app,base_url='http://127.0.0.1')
    result=client.patch('/api/threads/'+t['id'],json={'due_at':'2026-01-31'})
    assert result.status_code==200 and result.json()['due_at']=='2026-01-31'
    action=store.add(t['id'],'action','Date action')
    result=client.patch('/api/actions/'+action['id'],json={'due_at':'2026-02-01'})
    assert result.status_code==200 and result.json()['due_at']=='2026-02-01'
    assert store.list_threads()[0]['deadline_due']


@pytest.mark.parametrize('zone,stamp,due_day,future_day',[
    ('America/Los_Angeles','2026-11-01T06:30:00+00:00','2026-10-31','2026-11-01'),
    ('Pacific/Kiritimati','2026-10-31T10:30:00+00:00','2026-11-01','2026-11-02'),
])
def test_calendar_due_uses_local_rollover_even_at_dst(zone,stamp,due_day,future_day,monkeypatch):
    import os,time
    from tether.recurrence import is_due,deadline_due
    if not hasattr(time,'tzset'):pytest.skip('Process timezone switching unavailable')
    previous=os.environ.get('TZ')
    try:
        os.environ['TZ']=zone;time.tzset()
        assert is_due(due_day,stamp) and deadline_due(due_day,stamp)
        assert not is_due(future_day,stamp) and not deadline_due(future_day,stamp)
    finally:
        if previous is None:os.environ.pop('TZ',None)
        else:os.environ['TZ']=previous
        time.tzset()
