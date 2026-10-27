"""Microphone recordings use the configured key, with no retries or saved audio."""
from io import BytesIO
import json
from urllib.error import URLError
import pytest


@pytest.fixture
def configured(monkeypatch):
    from tend import ai,secrets,voice
    monkeypatch.delenv('TEND_AI_BASE_URL',raising=False)
    monkeypatch.setattr(ai,'load',lambda:{'base_url':'https://provider.example/v1'})
    monkeypatch.setattr(secrets,'get',lambda:'synthetic-voice-key')
    return voice


def test_transcription_uses_multipart_and_current_provider(configured,monkeypatch):
    calls=[]
    def fake(request,timeout):
        calls.append(request)
        assert timeout==90
        return BytesIO(json.dumps({'text':'  A spoken message.  '}).encode())
    monkeypatch.setattr(configured,'urlopen',fake)
    result=configured.transcribe(b'synthetic audio','audio/webm;codecs=opus','test-transcriber','https://provider.example/v1')
    assert result=={'text':'A spoken message.'}
    assert len(calls)==1 and calls[0].full_url=='https://provider.example/v1/audio/transcriptions'
    assert calls[0].get_header('Authorization')=='Bearer synthetic-voice-key'
    assert b'name="model"' in calls[0].data and b'test-transcriber' in calls[0].data
    assert b'filename="voice.webm"' in calls[0].data and b'synthetic audio' in calls[0].data


def test_invalid_audio_and_changed_provider_never_contact_network(configured,monkeypatch):
    monkeypatch.setattr(configured,'urlopen',lambda *a,**kw:pytest.fail('Unexpected provider call'))
    for audio,mime in [(b'','audio/webm'),(b'not audio','text/html')]:
        with pytest.raises(ValueError):configured.transcribe(audio,mime)
    with pytest.raises(ValueError,match='changed'):configured.transcribe(b'audio','audio/mp4',expected_base='https://different.example/v1')
    with pytest.raises(ValueError,match='model'):configured.transcribe(b'audio','audio/mp4',model='invalid\r\nheader')


def test_ambiguous_transcription_failure_is_never_retried(configured,monkeypatch):
    calls=[]
    def fail(*args,**kwargs):calls.append(True);raise URLError('connection lost')
    monkeypatch.setattr(configured,'urlopen',fail)
    with pytest.raises(ValueError,match='not retried'):configured.transcribe(b'audio','audio/mp4')
    assert len(calls)==1


def test_voice_route_and_packaged_script(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from tend import store,voice
    from tend.app import app
    monkeypatch.setenv('TEND_DB',str(tmp_path/'voice.sqlite3'));store.init()
    calls=[]
    def fake(audio,mime,model,expected):calls.append((audio,mime,model,expected));return {'text':'Review this draft.'}
    monkeypatch.setattr(voice,'transcribe',fake)
    client=TestClient(app,base_url='http://127.0.0.1')
    response=client.post('/api/voice/transcribe',files={'file':('voice.webm',b'audio','audio/webm')},
                         data={'model':'transcriber','provider_base':'https://provider.example/v1'})
    assert response.status_code==200 and response.json()=={'text':'Review this draft.'}
    assert calls==[(b'audio','audio/webm','transcriber','https://provider.example/v1')]
    assert store.conversation()==[] and store.list_threads()==[]
    assert client.get('/voice.js').status_code==200
    assert 'voice.js' in client.get('/').text
