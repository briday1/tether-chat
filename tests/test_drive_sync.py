import copy
import json
import pytest
from tend import drive_sync as sync, store, workspaces


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv('TEND_DB', str(tmp_path / 'test.sqlite3'))
    store.init()
    with workspaces.use('home'):
        store.init()
        yield


def commit(snap, records=None, metadata=None):
    return sync.apply(snap['records'], records if records is not None else snap['records'], metadata if metadata is not None else snap['metadata'], snap['revision'])


def test_work_never_exports_or_applies(tmp_path, monkeypatch):
    monkeypatch.setenv('TEND_DB', str(tmp_path / 'test.sqlite3'))
    store.init(); store.create('Private work')
    with pytest.raises(sync.SyncError) as error:
        sync.snapshot()
    assert error.value.status == 403
    with pytest.raises(sync.SyncError) as error:
        sync.apply({}, {}, {}, 0)
    assert error.value.status == 403
    assert store.list_threads()[0]['title'] == 'Private work'


def test_whitelist_and_preserves_private_fields(home):
    task = store.create('Milk', 'Two cartons', ['Shopping'])
    store.update(task['id'], {'action_prompt': 'Private instruction', 'due_action': 'activity_report', 'action_config': {'period': 'month'}})
    store.remember('user', 'Private chat')
    snap = sync.snapshot(); key = 'task:' + task['id']
    assert set(snap['records'][key]) == set(sync.FIELDS['task'])
    assert 'Private' not in json.dumps(snap)
    changed = copy.deepcopy(snap['records']); changed[key]['title'] = 'Oat milk'
    result = commit(snap, changed, {'pending': ['example']})
    assert result['revision'] == 1
    saved = store.get(task['id'])
    assert saved['title'] == 'Oat milk'
    assert saved['action_prompt'] == 'Private instruction'
    assert saved['action_config'] == {'period': 'month'}
    assert store.conversation()[0]['body'] == 'Private chat'


def test_local_edit_cas_does_not_lose_edit_or_metadata(home):
    task = store.create('Milk')
    snap = sync.snapshot()
    store.update(task['id'], {'title': 'Bread'})
    with pytest.raises(sync.SyncError) as error:
        commit(snap, metadata={'lost': 'no'})
    assert error.value.status == 409
    current = sync.snapshot()
    assert current['records']['task:' + task['id']]['title'] == 'Bread'
    assert current['metadata'] == {} and current['revision'] == 0


def test_metadata_only_race_is_rejected(home):
    snap = sync.snapshot()
    commit(snap, metadata={'pending': ['one']})
    with pytest.raises(sync.SyncError) as error:
        commit(snap, metadata={'pending': ['two']})
    assert error.value.status == 409
    assert sync.snapshot()['metadata']['pending'] == ['one']


def test_roundtrip_entries_notes_and_deletion(home):
    task = store.create('Chores')
    entry = store.add(task['id'], 'action', 'Take trash out')
    with store.conn() as c:
        c.execute('INSERT INTO action_notes VALUES(?,?,?,?,?)', ('note1', entry['id'], 'Before dinner', store.now(), store.now()))
    snap = sync.snapshot()
    assert len(snap['records']) == 3
    records = copy.deepcopy(snap['records'])
    records['entry:' + entry['id']]['done'] = 1
    records['note:note1']['body'] = 'After dinner'
    result = commit(snap, records)
    assert store.get(task['id'])['entries'][0]['done'] == 1
    assert store.get(task['id'])['entries'][0]['notes'][0]['body'] == 'After dinner'
    commit(result, {})
    assert store.list_threads() == []
    assert store.query('SELECT * FROM action_notes') == []


def test_insert_remote_records_with_references(home):
    task = store.create('Source')
    entry = store.add(task['id'], 'action', 'Remote action')
    snap = sync.snapshot(); records = copy.deepcopy(snap['records'])
    commit(snap, {})
    result = commit(sync.snapshot(), records)
    assert result['records'] == records
    assert store.get(task['id'])['entries'][0]['id'] == entry['id']


@pytest.mark.parametrize('field,value', [('action_prompt','secret'), ('notified_for','now'), ('api_key','key'), ('__proto__',{})])
def test_unknown_fields_rejected(home, field, value):
    task = store.create('Safe'); snap = sync.snapshot()
    records = copy.deepcopy(snap['records']); records['task:' + task['id']][field] = value
    with pytest.raises(sync.SyncError): commit(snap, records)
    assert sync.snapshot() == snap


@pytest.mark.parametrize('field,value', [('title', ''), ('title', 23), ('state', []), ('categories', ['A', 'a']), ('categories', []), ('due_at', 'yesterday'), ('summary', 'x' * 20001)])
def test_malformed_tasks_rejected(home, field, value):
    task = store.create('Safe'); snap = sync.snapshot()
    records = copy.deepcopy(snap['records']); records['task:' + task['id']][field] = value
    with pytest.raises(sync.SyncError): commit(snap, records)
    assert sync.snapshot() == snap


def test_missing_parent_and_id_mismatch_rejected(home):
    task = store.create('Safe'); entry = store.add(task['id'], 'action', 'Action'); snap = sync.snapshot()
    records = copy.deepcopy(snap['records']); records['entry:' + entry['id']]['thread_id'] = 'missing'
    with pytest.raises(sync.SyncError): commit(snap, records)
    records = copy.deepcopy(snap['records']); records['task:' + task['id']]['id'] = 'other'
    with pytest.raises(sync.SyncError): commit(snap, records)
    assert sync.snapshot() == snap


def test_bounded_metadata_and_revision(home, monkeypatch):
    snap = sync.snapshot()
    monkeypatch.setattr(sync, 'MAX_METADATA_BYTES', 30)
    with pytest.raises(sync.SyncError): commit(snap, metadata={'large': 'x' * 31})
    with pytest.raises(sync.SyncError): commit(snap, metadata={'nan': float('nan')})
    with pytest.raises(sync.SyncError): sync.apply({}, {}, {}, True)
    assert sync.snapshot() == snap
