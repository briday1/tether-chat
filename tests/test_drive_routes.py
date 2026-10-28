from fastapi.testclient import TestClient
from tether import store,workspaces

def test_drive_local_routes_require_home_and_same_origin(tmp_path,monkeypatch):
    monkeypatch.setenv('TETHER_DB',str(tmp_path/'work.sqlite3'))
    from tether.app import app
    with TestClient(app,base_url='http://localhost') as client:
        assert client.get('/api/drive-sync/local').status_code==403
        headers={'X-Tether-Workspace':'home'}
        snap=client.get('/api/drive-sync/local',headers=headers).json()
        body={'expected':snap['records'],'records':snap['records'],'metadata':{},'expected_revision':snap['revision']}
        assert client.post('/api/drive-sync/local',headers=headers,json=body).status_code==403
        assert client.post('/api/drive-sync/local',headers={**headers,'Origin':'https://attacker.invalid'},json=body).status_code==403
        assert client.post('/api/drive-sync/local',headers={**headers,'Origin':'http://localhost'},json=body).status_code==200
        assert client.get('/drive-sharing?workspace=home').status_code==200
        assert client.get('/drive-sync-core.mjs').status_code==200
        assert client.get('/drive-setup.mjs').status_code==200
        config=client.get('/drive-config.json').json()
        assert set(config)=={'clientId','projectNumber','pickerKey'}
        assert all(isinstance(value,str) for value in config.values())
