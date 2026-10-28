"""Installed tether-chat exposes no household sharing or Google configuration."""
from fastapi.testclient import TestClient

def test_installed_app_has_no_drive_routes_or_config(tmp_path,monkeypatch):
    monkeypatch.setenv('TETHER_DB',str(tmp_path/'work.sqlite3'))
    from tether.app import app
    with TestClient(app,base_url='http://localhost') as client:
        for path in ['/api/drive-sync/local','/drive-sharing','/drive-config.json','/drive-sync-core.mjs','/drive-setup.mjs']:
            assert client.get(path).status_code==404,path
        assert client.post('/api/drive-sync/local',json={}).status_code==404
        assert client.post('/api/drive-sync/open-browser',json={}).status_code==404
