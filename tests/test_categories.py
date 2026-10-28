"""Exercise migrations and overlapping memberships through the public data/API surfaces."""
import sqlite3
import pytest
from fastapi.testclient import TestClient
from tether import store
from tether.app import app
from tether.snapshots import snapshot

@pytest.fixture
def database(tmp_path,monkeypatch):
    path=tmp_path/'tasks.sqlite3'
    monkeypatch.setenv('TETHER_DB',str(path));store.init()
    return path

def test_existing_database_migrates_without_losing_memberships(database):
    task=store.create('Existing task')
    # Simulate a database from before the membership table existed.
    with sqlite3.connect(database) as connection:
        connection.execute('DROP TABLE thread_categories')
        connection.execute('UPDATE threads SET category=? WHERE id=?',('Projects',task['id']))
    store.init()
    assert store.get(task['id'])['categories']==['Projects']
    store.set_categories(task['id'],['Operations'],'add')
    store.init();store.init()
    assert store.get(task['id'])['categories']==['Projects','Operations']
    assert store.get(task['id'])['category']=='Projects'

def test_shared_task_stays_one_record_with_distinct_category_counts(database):
    client=TestClient(app,base_url='http://127.0.0.1')
    task=client.post('/api/threads',json={'title':'Ship & review <draft>','categories':[' Projects ','Operations','projects']}).json()
    assert task['categories']==['Projects','Operations']
    client.patch('/api/threads/'+task['id'],json={'due_at':'2026-10-27T12:00:00Z'})
    assert len(client.get('/api/threads').json())==1
    groups=client.get('/api/board').json()
    assert {g['name']:len(g['threads']) for g in groups}=={'Operations':1,'Projects':1}
    report=snapshot('2026-10-26','2026-11-01')
    assert report['insights']['scheduled_due']==1
    assert report['insights']['categories']=={'Operations':1,'Projects':1}
    assert snapshot('2026-10-26','2026-11-01','Operations')['insights']['scheduled_due']==1
    assert len(store.list_threads('Operations'))==1
    # Existing clients can still intentionally move a task to one category.
    moved=client.patch('/api/threads/'+task['id'],json={'category':'Product'}).json()
    assert moved['categories']==['Product']
    assert store.query('SELECT name FROM thread_categories')==[{'name':'Product'}]

def test_category_add_remove_report_filter_and_archive(database):
    from tether import ai,mcp_server
    task=store.create('Shared work',categories=['Projects'])
    result=mcp_server.set_task_categories(task['id'],['Product'],'add')
    assert result['categories']==['Projects','Product']
    result=ai.dispatch('set_categories',{'id':task['id'],'categories':['Operations'],'mode':'add'})
    assert result['categories']==['Projects','Product','Operations']
    store.record_activity(task['id'],'Finished review','progress','2026-10-27T12:00:00Z')
    scheduled=store.create('Weekly report')
    store.configure_due_action(scheduled['id'],'activity_report','week','Operations')
    assert store.report_for_task(scheduled['id'],'2026-10-29T12:00:00Z')['count']==1
    assert mcp_server.get_snapshot('2026-10-26','2026-11-01','Operations')['insights']['activity_events']==1
    result=mcp_server.set_task_categories(task['id'],['product'],'remove')
    assert result['categories']==['Projects','Operations']
    store.archive_thread(task['id'])
    assert all(task['id']!=t['id'] for g in store.board() for t in g['threads'])
    assert store.archived_threads()[0]['categories']==['Projects','Operations']
    store.archive_thread(task['id'],False)
    assert len(store.list_threads())==2
    assert store.set_categories(task['id'],[],'replace')['categories']==['Unsorted']

@pytest.mark.parametrize('categories',[None,'Projects',[None],[''],['x'*81],['x']*21])
def test_invalid_categories_leave_saved_memberships_intact(database,categories):
    task=store.create('Keep me',categories=['Projects','Product'])
    with pytest.raises(ValueError):store.update(task['id'],{'categories':categories})
    assert store.get(task['id'])['categories']==['Projects','Product']
