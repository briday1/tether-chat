"""Attention deferral, completion and archival share one durable task lifecycle."""
import json
import pytest
from tether import ai, attention, store


@pytest.fixture
def records(tmp_path, monkeypatch):
    clock = ['2026-11-03T14:00:00+00:00']
    monkeypatch.setenv('TETHER_DB', str(tmp_path / 'lifecycle.sqlite3'))
    monkeypatch.setattr(store, 'now', lambda: clock[0])
    monkeypatch.setattr(ai, '_attention_cache', {})
    monkeypatch.setattr(ai, 'public_config', lambda: {'has_key': False})
    store.init()
    return clock


def test_task_defer_hides_all_attention_but_keeps_deadlines_and_child_dates(records):
    task = store.create('Prepare report')
    store.update(task['id'], {'due_at':'2026-11-02', 'revisit_at':'2026-11-03T13:59:00Z'})
    action = store.add(task['id'], 'action', 'Collect notes')
    store.update_action(action['id'], {'due_at':'2026-11-02', 'revisit_at':'2026-11-03T13:59:30Z'})
    before = store.get(task['id'])
    assert len(attention.items()['items']) == 2

    deferred = store.defer_task(task['id'], '2026-11-04T09:00:00-05:00')
    assert deferred['due_at'] == before['due_at']
    assert deferred['entries'] == before['entries']
    assert store.is_snoozed(deferred)
    assert store.list_threads()[0]['deadline_due']
    assert not store.list_threads()[0]['attention_due']
    assert attention.items()['items'] == []
    assert store.claim_notifications() == []

    records[0] = '2026-11-04T13:59:59Z'
    assert attention.items()['items'] == []
    records[0] = '2026-11-04T14:00:00Z'
    assert {i['id'] for i in attention.items()['items']} == {task['id'], action['id']}
    notices = store.claim_notifications()
    assert len(notices) == 1 and notices[0]['id'] == task['id']
    assert store.claim_notifications() == []


def test_action_defer_is_scoped_and_curation_cannot_undo_it(records, monkeypatch):
    task = store.create('Project')
    first = store.add(task['id'], 'action', 'First')
    second = store.add(task['id'], 'action', 'Second')
    for action in (first, second):store.update_action(action['id'], {'due_at':'2026-11-02'})
    before = store.get(task['id'])
    store.defer_action(first['id'], '2026-11-04T09:00:00-05:00')
    assert [i['id'] for i in attention.items()['items']] == [second['id']]
    after = store.get(task['id'])
    assert after['revisit_at'] == before['revisit_at']
    before_entries = {e['id']:e for e in before['entries']}
    after_entries = {e['id']:e for e in after['entries']}
    assert after_entries[second['id']] == before_entries[second['id']]
    assert after_entries[first['id']]['due_at'] == '2026-11-02'
    store.update_action(second['id'], {'done':True})
    monkeypatch.setattr(ai, 'public_config', lambda: {'has_key':True})
    monkeypatch.setattr(ai, 'request', lambda *a, **k: {'choices':[{'message':{'content':json.dumps({'items':[{'id':task['id'],'reason':'First is overdue'}]})}}]})
    assert attention.items(True)['items'] == []


def test_future_reminder_updates_and_capture_override_overdue_attention(records):
    task = store.create('Send form')
    store.update(task['id'], {'due_at':'2026-11-01'})
    store.update(task['id'], {'revisit_at':'2026-11-04T14:00:00Z'})
    assert store.get(task['id'])['snoozed_until'] == '2026-11-04T14:00:00Z'
    assert attention.items()['items'] == []
    store.defer_task(task['id'], None)
    assert [i['id'] for i in attention.items()['items']] == [task['id']]
    reused = store.capture('Send form', remind_at='2026-11-04T14:00:00Z', existing_id=task['id'])
    assert reused['reused'] and store.is_snoozed(reused)
    assert reused['due_at'] == '2026-11-01' and attention.items()['items'] == []
    store.update(task['id'], {'revisit_at':None})
    action = store.add(task['id'], 'action', 'Attachment')
    store.update_action(action['id'], {'due_at':'2026-11-01', 'revisit_at':'2026-11-04T14:00:00Z'})
    assert not any(i.get('action_id') == action['id'] for i in attention.items()['items'])


def test_legacy_future_reminders_suppress_attention_without_new_metadata(records):
    task = store.create('Imported reminder')
    with store.conn() as connection:
        connection.execute('UPDATE threads SET due_at=?,revisit_at=?,snoozed_until=NULL WHERE id=?', ('2026-11-02','2026-11-04T14:00:00Z',task['id']))
    assert store.is_snoozed(store.get(task['id']))
    assert attention.items()['items'] == []


@pytest.mark.parametrize('current,until', [
    ('2026-11-01T05:30:00Z','2026-11-01T01:15:00-05:00'),
    ('2026-12-31T18:59:59Z','2027-01-01T09:00:00+14:00'),
])
def test_defer_expiry_compares_instants_across_offsets_dst_and_year_boundary(records,current,until):
    records[0] = current
    task = store.create('Time boundary')
    store.update(task['id'], {'due_at':'2026-01-01'})
    store.defer_task(task['id'], until)
    assert attention.items()['items'] == []
    records[0] = until
    assert [i['id'] for i in attention.items()['items']] == [task['id']]


@pytest.mark.parametrize('when', ['yesterday','2026-11-04','2026-11-04T09:00:00','2026-11-03T13:59:59Z','2026-11-03T14:00:00Z'])
def test_invalid_or_past_deferral_is_atomic(records,when):
    task = store.create('Leave alone')
    action = store.add(task['id'],'action','Leave action alone')
    before = store.get(task['id'])
    for fn,ident in ((store.defer_task,task['id']),(store.defer_action,action['id'])):
        with pytest.raises(ValueError):fn(ident,when)
        assert store.get(task['id']) == before


def test_complete_and_undo_archive_preserve_data_and_independent_child_completion(records):
    task = store.create('One-time report')
    earlier = store.add(task['id'], 'action', 'Already finished')
    open_action = store.add(task['id'], 'action', 'Send report')
    store.update_action(earlier['id'], {'done':True})
    store.add_action_note(open_action['id'], 'Reviewed with the team')
    store.record_activity(task['id'], 'Draft prepared')
    store.update(task['id'], {'due_at':'2026-11-03','revisit_at':'2026-11-03T13:59:00Z'})
    before = store.get(task['id'])
    completed = store.complete_task(task['id'])
    assert completed['state'] == 'settled' and completed['archived_at']
    by_id = {e['id']:e for e in completed['entries']}
    assert all(e['done'] for e in completed['entries'])
    assert not by_id[earlier['id']]['completed_by_task']
    assert by_id[open_action['id']]['completed_by_task']
    assert completed['activity'] == before['activity']
    assert by_id[open_action['id']]['notes'][0]['body'] == 'Reviewed with the team'
    assert store.board() == [] and attention.items()['items'] == [] and store.claim_notifications() == []
    store.complete_task(task['id'])  # A retry cannot erase the undo information.
    reopened = store.complete_task(task['id'], False)
    by_id = {e['id']:e for e in reopened['entries']}
    assert reopened['state'] == 'open' and reopened['archived_at'] is None
    assert by_id[earlier['id']]['done'] and not by_id[open_action['id']]['done']
    assert reopened['revisit_at'] == before['revisit_at'] and reopened['due_at'] == before['due_at']
    assert reopened['activity'] == before['activity']


def test_archive_restore_reopens_and_individual_undo_restores_visibility(records):
    task = store.create('Restore me')
    action = store.add(task['id'], 'action', 'Do it')
    sibling = store.add(task['id'], 'action', 'Sibling')
    store.complete_task(task['id'])
    restored = store.archive_thread(task['id'], False)
    assert restored['state'] == 'open' and restored['archived_at'] is None
    assert all(not e['done'] for e in restored['entries'])
    assert not store.list_threads()[0]['archived_at']
    store.complete_task(task['id'])
    store.update_action(action['id'], {'done':False})
    reopened = store.get(task['id'])
    assert reopened['state'] == 'open' and reopened['archived_at'] is None
    by_id = {e['id']:e for e in reopened['entries']}
    assert not by_id[action['id']]['done'] and by_id[sibling['id']]['done']


def test_last_child_completion_does_not_assume_parent_subject_is_finished(records):
    task = store.create('Ongoing project')
    action = store.add(task['id'], 'action', 'First milestone')
    store.update_action(action['id'], {'done':True})
    assert store.get(task['id'])['state'] == 'open' and not store.get(task['id'])['archived_at']
    store.update(task['id'], {'state':'settled'})
    assert store.get(task['id'])['archived_at']


def test_migration_and_live_sweep_archive_only_finished_nonrecurring_tasks(records):
    finished = store.create('Old finished task')
    blocked = store.create('Old settled task with unfinished work')
    action = store.add(blocked['id'], 'action', 'Still open')
    repeated = store.create('Recurring commitment')
    store.update(repeated['id'], {'recurrence':'weekly','next_occurrence':'2026-11-03'})
    with store.conn() as connection:
        connection.execute("UPDATE threads SET state='settled'")
        for column in ('snoozed_until','deferred_occurrence'):connection.execute(f'ALTER TABLE threads DROP COLUMN {column}')
        for column in ('snoozed_until','completed_by_task'):connection.execute(f'ALTER TABLE entries DROP COLUMN {column}')
    store.init()
    assert store.get(finished['id'])['archived_at']
    assert not store.get(blocked['id'])['archived_at']
    assert not store.get(repeated['id'])['archived_at']
    assert store.get(blocked['id'])['entries'][0]['completed_by_task'] == 0
    store.update_action(action['id'], {'done':True})
    assert store.get(blocked['id'])['archived_at']
    later = store.create('Completed by an older client')
    with store.conn() as connection:connection.execute("UPDATE threads SET state='settled' WHERE id=?", (later['id'],))
    assert next(t for t in store.list_threads() if t['id'] == later['id'])['archived_at']
    assert store.auto_archive()['archived'] == 0


def test_recurring_defer_keeps_identity_and_completion_consumes_only_linked_reminder(records):
    task = store.create('Daily review')
    store.update(task['id'], {'recurrence':'daily','next_occurrence':'2026-11-03','due_at':'2026-11-02'})
    deferred = store.defer_task(task['id'], '2026-11-04T14:00:00Z')
    assert deferred['next_occurrence'] == deferred['deferred_occurrence'] == '2026-11-03'
    assert store.recurring_due() == [] and attention.items()['items'] == []
    records[0] = '2026-11-04T14:00:00Z'
    complete = store.complete_occurrence(task['id'])
    assert complete['completion']['completed'] and complete['next_occurrence'] == '2026-11-05'
    assert all(complete[field] is None for field in ('revisit_at','snoozed_until','deferred_occurrence'))
    assert complete['due_at'] == '2026-11-02'
    assert complete['state'] == 'open' and not complete['archived_at']
    assert not store.complete_occurrence(task['id'])['completion']['completed']

    store.defer_task(task['id'], '2026-11-06T14:00:00Z')
    store.update(task['id'], {'revisit_at':'2026-11-07T14:00:00Z'})
    early = store.complete_occurrence(task['id'], occurrence_at=complete['next_occurrence'])
    assert early['revisit_at'] == '2026-11-07T14:00:00Z' and early['deferred_occurrence'] is None


def test_deferred_recurring_cycle_notifies_once_and_cannot_be_bulk_completed(records):
    task = store.create('Hourly review')
    store.update(task['id'], {'recurrence':'daily','next_occurrence':'2026-11-03T13:59:00Z'})
    before = store.get(task['id'])
    with pytest.raises(ValueError):store.complete_task(task['id'])
    assert store.get(task['id']) == before
    store.defer_task(task['id'], '2026-11-03T15:00:00Z')
    records[0] = '2026-11-03T15:00:00Z'
    notices = store.claim_notifications()
    assert len(notices) == 1 and notices[0]['revisit_at'] == '2026-11-03T15:00:00Z'
    assert store.claim_notifications() == []


def test_action_edit_validates_before_writing_and_refreshes_parent_revision(records):
    task = store.create('Parent')
    action = store.add(task['id'], 'action', 'Old text')
    before = store.get(task['id'])
    for fields in ({'body':' '},{'done':'false'},{'body':'Valid','revisit_at':'bad'}):
        with pytest.raises(ValueError):store.update_action(action['id'],fields)
        assert store.get(task['id']) == before
    records[0] = '2026-11-03T14:01:00Z'
    assert store.update_action(action['id'], {'body':'New text'})['body'] == 'New text'
    assert store.get(task['id'])['updated_at'] == records[0]
