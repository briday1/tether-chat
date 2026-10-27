"""Voice must not send recordings, keys or task content to a chat provider."""
from fastapi.testclient import TestClient


def test_retired_provider_audio_route_never_loads_a_key_or_sends_audio(tmp_path,monkeypatch):
    from tend import ai,secrets,store
    from tend.app import app
    monkeypatch.setenv('TEND_DB',str(tmp_path/'voice.sqlite3'));store.init()
    def forbidden(*args,**kwargs):raise AssertionError('Voice input must not use the AI connection')
    monkeypatch.setattr(ai,'load',forbidden);monkeypatch.setattr(secrets,'get',forbidden)
    client=TestClient(app,base_url='http://127.0.0.1')
    result=client.post('/api/voice/transcribe',files={'file':('voice.wav',b'audio','audio/wav')})
    assert result.status_code==410 and 'this device' in result.json()['detail']
    assert store.conversation()==[] and store.list_threads()==[]
    assert client.get('/voice.js').status_code==200
    assert client.get('/speech.mjs').status_code==200
    assert 'voice.js' in client.get('/').text
