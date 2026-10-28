"""Provider setup and error recovery use synthetic credentials and no paid requests."""
import io
import json
from urllib.error import HTTPError
import pytest
from tether import ai
from tether.provider import failure,retry_delay


@pytest.fixture
def connection(tmp_path,monkeypatch):
    monkeypatch.setenv('TETHER_CONFIG',str(tmp_path/'provider.json'))
    for name in ('TETHER_AI_BASE_URL','TETHER_AI_MODEL','TETHER_AI_API_KEY'):monkeypatch.delenv(name,raising=False)
    vault={}
    monkeypatch.setattr(ai.secrets,'get',lambda:vault.get('key'))
    monkeypatch.setattr(ai.secrets,'set_key',lambda key:vault.update(key=key.strip()))
    monkeypatch.setattr(ai.secrets,'delete_key',lambda:vault.clear())
    return vault


def response(value):return io.BytesIO(json.dumps(value).encode())


def test_discovery_uses_typed_credentials_without_saving_and_keeps_provider_boundary(connection,monkeypatch):
    calls=[]
    def network(req,timeout):
        calls.append(req)
        return response({'data':[{'id':'tool-mini','supported_parameters':['tools']},{'id':'tool-mini','supported_parameters':['tools']},{'id':'another','capabilities':{'tool_calling':True}},{'id':None}]})
    monkeypatch.setattr(ai,'urlopen',network)
    assert ai.models('https://provider.test/v1/',' typed-key ')['models']==['another','tool-mini']
    assert calls[0].get_method()=='GET' and calls[0].full_url=='https://provider.test/v1/models'
    assert calls[0].get_header('Authorization')=='Bearer typed-key'
    assert not ai.config_path().exists() and connection=={}
    ai.save('https://provider.test/v1','model','saved-key')
    ai.models();assert calls[1].get_header('Authorization')=='Bearer saved-key'
    with pytest.raises(ValueError,match='Enter your API key'):ai.models('https://another.test/v1')
    assert len(calls)==2


@pytest.mark.parametrize('code',['insufficient_quota','credit_balance_exhausted','organization_spend_limit_exceeded','project_spend_limit_exceeded','organization_usage_limit_exceeded'])
def test_billing_429_is_not_retried_and_key_remains_ready(connection,monkeypatch,code):
    ai.save('https://api.openai.com/v1','test-model','synthetic-key');calls=[]
    def network(req,timeout):
        calls.append(req)
        raise HTTPError(req.full_url,429,'quota',{},response({'error':{'code':code,'type':'insufficient_quota'}}))
    monkeypatch.setattr(ai,'urlopen',network)
    monkeypatch.setattr(ai.time,'sleep',lambda delay:pytest.fail('Billing errors must not be retried'))
    with pytest.raises(ValueError,match=code) as error:ai.request([{'role':'user','content':'Hello'}])
    assert 'ChatGPT subscriptions do not include API credit' in str(error.value)
    assert len(calls)==1 and ai.public_config()['has_key']


def test_temporary_rate_limit_retries_but_long_delay_never_retries_early(connection,monkeypatch):
    ai.save('https://provider.test/v1','test-model','synthetic-key');calls=[];pauses=[]
    def network(req,timeout):
        calls.append(req)
        if len(calls)==1:raise HTTPError(req.full_url,429,'rate limited',{'Retry-After':'3'},response({'error':{'code':'rate_limit_exceeded'}}))
        return response({'choices':[{'message':{'content':'OK'}}]})
    monkeypatch.setattr(ai,'urlopen',network);monkeypatch.setattr(ai.time,'sleep',pauses.append)
    assert ai.request([{'role':'user','content':'Hello'}])['choices']
    assert len(calls)==2 and pauses==[3]
    calls.clear();pauses.clear()
    def slow(req,timeout):
        calls.append(req);raise HTTPError(req.full_url,429,'slow down',{'Retry-After':'120'},response({'error':{'code':'slow_down'}}))
    monkeypatch.setattr(ai,'urlopen',slow)
    with pytest.raises(ValueError,match='120 seconds'):ai.request([])
    assert len(calls)==1 and pauses==[]


def test_key_rotation_applies_without_restarting_and_errors_are_redacted(connection,monkeypatch):
    ai.save('https://provider.test/v1','first-model','old-key')
    ai.save('https://provider.test/v1','second-model','new-key')
    def network(req,timeout):
        assert req.get_header('Authorization')=='Bearer new-key'
        assert json.loads(req.data)['model']=='second-model'
        return response({'choices':[{'message':{'content':'OK'}}]})
    monkeypatch.setattr(ai,'urlopen',network);assert ai.request([])['choices']
    message,retryable=failure(400,json.dumps({'error':{'message':'Bad request new-key sk-another-secret'}}),'new-key')
    assert 'new-key' not in message and 'sk-another-secret' not in message and not retryable
    assert retry_delay('120')==120


def test_model_discovery_route_and_connection_test_use_the_current_fields(connection,monkeypatch,tmp_path):
    from fastapi.testclient import TestClient
    from tether.app import app
    client=TestClient(app,base_url='http://127.0.0.1')
    calls=[]
    def network(req,timeout):
        calls.append(req)
        if req.get_method()=='GET':return response({'data':[{'id':'tool-mini','supported_parameters':['tools']}]})
        assert 'max_tokens' not in json.loads(req.data)
        assert req.get_header('Authorization')=='Bearer new-key'
        return response({'choices':[{'message':{'content':'OK'}}]})
    monkeypatch.setattr(ai,'urlopen',network)
    assert client.post('/api/settings/models',json={'base_url':'https://provider.test/v1','api_key':'new-key'}).json()['models']==['tool-mini']
    assert client.post('/api/settings',json={'base_url':'https://provider.test/v1','model':'tool-mini','api_key':'new-key'}).json()['has_key']
    assert client.post('/api/settings/test').status_code==200
    assert len(calls)==2


@pytest.mark.parametrize('model',['gpt-5.4','gpt-5.4-mini','gpt-5.5','gpt-5.6-sol','gpt-6-sol','gpt-6-luna'])
def test_compatible_chat_models_send_required_reasoning_option(connection,monkeypatch,model):
    ai.save('https://api.openai.com/v1',model,'synthetic-key')
    def network(req,timeout):
        body=json.loads(req.data)
        assert body['model']==model and body['reasoning_effort']=='none'
        assert body['tools'] and body['tool_choice']=='auto'
        return response({'choices':[{'message':{'content':'OK'}}]})
    monkeypatch.setattr(ai,'urlopen',network)
    assert ai.request([{'role':'user','content':'Hi'}])['choices']
