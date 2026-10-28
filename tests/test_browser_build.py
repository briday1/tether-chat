"""Browser builds must reuse desktop sources without altering desktop packaging."""
from pathlib import Path
import importlib.util
import json
import re
import tomllib
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('web_build',ROOT/'scripts/build_web.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.mark.parametrize('base',['/','/tether-chat/'])
def test_build_reuses_screens_and_scopes_every_asset(tmp_path,base):
    before={p:p.read_bytes() for p in (ROOT/'tend').glob('*') if p.is_file()}
    output=builder.build(tmp_path/'web',base)
    manifest=json.loads((output/'manifest.webmanifest').read_text(encoding='utf-8'))
    assert manifest['start_url']==manifest['scope']==base
    config_text=(output/'app-config.js').read_text(encoding='utf-8')
    config=json.loads(config_text.removeprefix('window.TETHER_CONFIG=').rstrip(';\n'))
    assert config['version']==tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    tools,system=builder.shared_ai()
    assert config['tools']==tools and config['system']==system
    assert len(tools)>20
    for page in ('conversation.html','board.html','snapshots.html'):
        text=(output/page).read_text(encoding='utf-8')
        assert base+'bridge.js' in text and base+'app-config.js' in text
        assert 'Database location' not in text and 'Credentials are stored by the local server' not in text
        assert "api('/board')" in text if page!='snapshots.html' else True
        for asset in re.findall(r'(?:src|href)="([^"#?]+)',text):
            if asset.startswith('https:'):continue
            path=asset.removeprefix(base) if asset.startswith(base) else asset.removeprefix('./')
            assert (output/path).is_file(),(page,asset)
    worker=(output/'sw.js').read_text(encoding='utf-8')
    assert "event.data?.type!=='TETHER_ACTIVATE_UPDATE'" in worker and "event.request.method!=='GET'" in worker
    assert "source.pathname!==BASE+'update.html'" in worker
    assert "path===BASE+'update.html'" in worker
    update=(output/'update.html').read_text(encoding='utf-8')
    assert '__VERSION__' not in update and config['version'] in update
    assert '<script src=' not in update and 'indexedDB.deleteDatabase' not in update
    assert 'tether-web:'+base in worker
    assert all(p.read_bytes()==value for p,value in before.items())
    meta=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']
    assert set(meta['scripts'])=={'tether-chat'} and set(meta['gui-scripts'])=={'tether-chat-desktop'}


def test_build_rejects_unsafe_output_and_invalid_scope(tmp_path):
    with pytest.raises(ValueError):builder.build(ROOT,'/')
    with pytest.raises(ValueError):builder.build(tmp_path/'web','/../')
    existing=tmp_path/'existing';existing.mkdir();(existing/'keep.txt').write_text('keep')
    with pytest.raises(ValueError):builder.build(existing)
    assert (existing/'keep.txt').read_text()=='keep'


def test_desktop_portable_export_contains_data_and_excludes_credentials(tmp_path,monkeypatch):
    from tend import store
    from tend.portable import export_data
    monkeypatch.setenv('TEND_DB',str(tmp_path/'desktop.sqlite3'))
    store.init();task=store.create('Release','Details',['Work','Software'])
    action=store.add(task['id'],'action','Run checks');store.add_action_note(action['id'],'A scoped detail')
    store.record_activity(task['id'],'Tests passed');store.remember('user','Hello')
    data=export_data()
    assert data['format']=='tether-chat' and data['version']==1
    assert data['data']['tasks'][0]['categories']==['Work','Software']
    assert data['data']['notes'][0]['action_id']==action['id']
    assert len(data['data']['messages'])==1
    assert 'settings' not in data['data'] and 'jobs' not in data['data']
    assert data['data']['tasks'][0]['created_at'].endswith('Z')
