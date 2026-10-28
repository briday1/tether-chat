"""Local workspace boundaries must survive navigation and background execution."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import pytest
from tether import store, workspaces

@pytest.fixture
def local_db(tmp_path,monkeypatch):
    monkeypatch.setenv('TETHER_DB',str(tmp_path/'existing.sqlite3'))
    store.init()
    return tmp_path

def test_existing_work_data_untouched_and_home_separate(local_db):
    work=store.create('Work plan');store.remember('user','Work message')
    with workspaces.use('home'):
        store.init()
        assert store.path().name=='existing.home.sqlite3'
        assert store.list_threads()==[] and store.conversation()==[]
        store.create('Grocery list');store.remember('user','Home message')
    assert store.get(work['id'])['title']=='Work plan'
    assert [t['title'] for t in store.list_threads()]==['Work plan']
    assert [m['body'] for m in store.conversation()]==['Work message']
    with workspaces.use('home'):
        assert [t['title'] for t in store.list_threads()]==['Grocery list']

def test_parallel_requests_and_worker_context(local_db):
    def task(mode):
        with workspaces.use(mode):
            store.init();store.create(mode)
            with ThreadPoolExecutor() as pool:
                return pool.submit(copy_context().run,lambda:store.list_threads()).result()
    with ThreadPoolExecutor() as pool:
        a=pool.submit(task,'work');b=pool.submit(task,'home')
        assert [t['title'] for t in a.result()]==['work']
        assert [t['title'] for t in b.result()]==['home']
    assert workspaces.current()=='work'

def test_api_mode_scope_and_invalid_mode(local_db):
    from fastapi.testclient import TestClient
    from tether.app import app
    with TestClient(app,base_url='http://localhost') as client:
        client.post('/api/threads',json={'title':'Work'})
        client.post('/api/threads',json={'title':'Home'},headers={'X-Tether-Workspace':'home'})
        assert [t['title'] for t in client.get('/api/threads').json()]==['Work']
        assert [t['title'] for t in client.get('/api/threads?workspace=home').json()]==['Home']
        assert client.get('/api/threads',headers={'X-Tether-Workspace':'../escape'}).status_code==422

def test_portable_export_identifies_only_selected_workspace(local_db):
    from tether.portable import export_data
    store.create('Private work')
    with workspaces.use('home'):
        store.init();store.create('Home')
        data=export_data()
        assert data['workspace']=='home'
        assert [t['title'] for t in data['data']['tasks']]==['Home']

def test_work_relocation_keeps_existing_home_attached(tmp_path,monkeypatch):
    from tether import storage
    monkeypatch.delenv('TETHER_DB',raising=False)
    monkeypatch.setattr(storage,'config_path',lambda:tmp_path/'storage.json')
    old=tmp_path/'work.sqlite3';new=tmp_path/'new.sqlite3'
    storage._write({'active':str(old)})
    store.init();store.create('Work')
    with workspaces.use('home'):
        store.init();store.create('Home');home_path=store.path()
    storage.stage(str(new));storage.activate_pending()
    assert store.path()==new
    with workspaces.use('home'):
        assert store.path()==home_path
        assert [t['title'] for t in store.list_threads()]==['Home']
        with pytest.raises(ValueError):storage.stage(str(tmp_path/'other.sqlite3'))

def test_dynamic_conversation_snapshot_has_workspace():
    from pathlib import Path
    source=(Path(__file__).parents[1]/'tether/index.html').read_text(encoding='utf-8')
    assert "url.searchParams.set('workspace',window.tetherWorkspace||'work');frame.src=" in source
