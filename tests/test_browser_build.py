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
    before={p:p.read_bytes() for p in (ROOT/'tether').glob('*') if p.is_file()}
    output=builder.build(tmp_path/'web',base)
    manifest=json.loads((output/'manifest.webmanifest').read_text(encoding='utf-8'))
    assert manifest['start_url']==manifest['scope']==base
    assert manifest['name']=='tether-home'
    assert "const workspace = 'home'" in (output/'workspace.js').read_text(encoding='utf-8')
    assert (output/'legacy-recovery.mjs').is_file()
    config_text=(output/'app-config.js').read_text(encoding='utf-8')
    config=json.loads(config_text.split('=',1)[1].strip().rstrip(';'))
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
    assert "TETHER_ACTIVATE_UPDATE" in worker and "TETHER_FINISH_UPDATE" in worker and "event.request.method!=='GET'" in worker
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
    from tether import store
    from tether.portable import export_data
    monkeypatch.setenv('TETHER_DB',str(tmp_path/'desktop.sqlite3'))
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


def test_public_policy_pages_are_static_and_linked(tmp_path):
    output=builder.build(tmp_path/'web','/tether-chat/')
    about=(output/'about.mjs').read_text(encoding='utf-8')
    assert 'about.mjs' in (output/'conversation.html').read_text(encoding='utf-8')
    for name in ('privacy.html','terms.html'):
        page=(output/name).read_text(encoding='utf-8')
        assert '<script' not in page
        assert 'October 28, 2026' in page
        assert "'"+name+"'" in about
        assert 'optional experimental integration' in page
    assert 'drive.file' in (output/'privacy.html').read_text(encoding='utf-8')


def test_household_sharing_is_inside_settings_not_navigation(tmp_path):
    output=builder.build(tmp_path/'web','/tether-chat/')
    for name in ('conversation.html','board.html'):
        text=(output/name).read_text(encoding='utf-8')
        assert text.index('id="settings"') < text.index('id="householdSettings"') < text.index('id="provider"') < text.index('id="sharingSettings"')
        assert 'Earlier browser Work data' not in text
        assert 'id="inspectLegacy"' not in text
        assert 'id="householdAIReview"' in text
        assert 'type="module" src="./drive-sharing.mjs"' in text
        assert 'Create shared household' in text
        assert 'id="householdInvitation"' in text
        assert 'Copy household invitation link' in text
    assert (output/'household-invite.mjs').is_file()
    workspace=(output/'workspace.js').read_text(encoding='utf-8')
    assert 'data-drive-nav' not in workspace
    assert "searchParams.get('settings')==='sharing'" in workspace
    bridge=(output/'bridge.js').read_text(encoding='utf-8')
    assert "query.set('settings','sharing')" in bridge
    assert 'Create shared household' not in (output/'drive-sharing.html').read_text(encoding='utf-8')


def test_privacy_discloses_opt_in_encrypted_household_ai():
    text=(ROOT/'web/privacy.html').read_text(encoding='utf-8')
    assert 'If you choose Share AI connection' in text
    assert 'does not upload the plaintext key' in text
    assert 'decrypt, use and extract the key' in text
    assert 'changing the passphrase alone does not revoke copies' in text
    assert 'not included in the task Journal' in text
    assert 'Provider keys and connection settings are excluded from' not in text
