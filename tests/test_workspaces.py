"""The installed app must reject Home even when callers bypass the UI."""
from pathlib import Path
import pytest
from tether import store,workspaces

@pytest.fixture
def local_db(tmp_path,monkeypatch):
    monkeypatch.setenv('TETHER_DB',str(tmp_path/'existing.sqlite3'))
    store.init()
    return tmp_path

def test_work_data_and_legacy_home_file_are_untouched(local_db):
    work=store.create('Work plan');store.remember('user','Work message')
    legacy=local_db/'existing.home.sqlite3';legacy.write_bytes(b'legacy home data untouched')
    with pytest.raises(ValueError,match='Work only'):
        with workspaces.use('home'):store.init()
    assert store.get(work['id'])['title']=='Work plan'
    assert [m['body'] for m in store.conversation()]==['Work message']
    assert legacy.read_bytes()==b'legacy home data untouched'
    assert workspaces.current()=='work'

def test_api_rejects_home_in_header_or_query(local_db):
    from fastapi.testclient import TestClient
    from tether.app import app
    with TestClient(app,base_url='http://localhost') as client:
        assert client.post('/api/threads',json={'title':'Work'}).status_code==201
        for path,headers in [('/api/threads',{'X-Tether-Workspace':'home'}),('/api/threads?workspace=home',{}),('/api/threads?workspace=home',{'X-Tether-Workspace':'work'}),('/api/threads',{'X-Tether-Workspace':'../escape'})]:
            assert client.get(path,headers=headers).status_code==422
            assert client.post(path,headers=headers,json={'title':'Wrong space'}).status_code==422
        assert [t['title'] for t in client.get('/api/threads').json()]==['Work']

def test_export_is_always_work(local_db):
    from tether.portable import export_data
    store.create('Work task')
    data=export_data()
    assert data['workspace']=='work'
    assert [t['title'] for t in data['data']['tasks']]==['Work task']

def test_desktop_has_no_mode_selector_or_share_link():
    source=(Path(__file__).parents[1]/'tether/workspace.js').read_text()
    assert "const workspace = 'work'" in source
    assert 'workspace-picker' not in source and 'Share Home' not in source
    assert "select.add" not in source
