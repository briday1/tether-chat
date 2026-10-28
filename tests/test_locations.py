import io
import json
import pytest
from tether import store,locations,ai

FEATURE={'type':'Feature','geometry':{'type':'Point','coordinates':[-0.12,51.5]},'properties':{'osm_type':'N','osm_id':123,'name':'Example Dental','housenumber':'12','street':'High Street','city':'London','country':'United Kingdom'}}

def test_confirm_search_choose_and_save_is_idempotent(tmp_path,monkeypatch):
    monkeypatch.setenv('TETHER_DB',str(tmp_path/'tasks.sqlite3'));store.init()
    task=store.capture('Dentist appointment');calls=[]
    def network(request,timeout):
        calls.append(request)
        assert 'Authorization' not in request.headers
        assert request.full_url.startswith(locations.SEARCH_URL)
        return io.BytesIO(json.dumps({'features':[FEATURE]}).encode())
    monkeypatch.setattr(locations,'urlopen',network)
    request=ai.dispatch('request_location_lookup',{'id':task['id'],'query':'Example Dental London'})
    assert request['confirmation_required'] and not calls
    assert locations.requests()[0]['status']=='pending'
    assert not any(t['function']['name'] in ('search_location','save_location') for t in ai.TOOLS)
    result=locations.search(request['id'],'Example Dental London')
    assert len(calls)==1 and result['status']=='ready'
    with pytest.raises(ValueError):locations.save(request['id'],'invented-result')
    saved=locations.save(request['id'],result['results'][0]['id'])
    again=locations.save(request['id'],result['results'][0]['id'])
    assert saved['entry']['id']==again['entry']['id']
    assert len(store.get(task['id'])['entries'])==1
    assert '12 High Street' in saved['entry']['body'] and 'https://www.google.com/maps/search/?api=1&query=' in saved['entry']['body']
    assert locations.requests()[0]['selected']['address'].startswith('Example Dental')
    other=store.capture('Checkup for child');request2=locations.prepare(other['id'],'Example Dental London')
    assert locations.search(request2['id'],'Example Dental London')['status']=='ready'
    assert len(calls)==1 # Cache repeated confirmed searches, never run in the background.


def test_failed_lookup_is_retryable_and_has_google_maps_fallback(tmp_path,monkeypatch):
    monkeypatch.setenv('TETHER_DB',str(tmp_path/'tasks.sqlite3'));store.init();task=store.create('Visit office')
    request=locations.prepare(task['id'],'Office London')
    def offline(*a,**k):raise OSError('offline')
    monkeypatch.setattr(locations,'urlopen',offline)
    result=locations.search(request['id'],'Office London')
    assert result['status']=='pending' and result['error']
    assert 'maps/search' in locations.requests()[0]['maps_search_url']
    assert store.get(task['id'])['entries']==[]


def test_confirmation_endpoints_and_cards(tmp_path,monkeypatch):
    monkeypatch.setenv('TETHER_DB',str(tmp_path/'tasks.sqlite3'))
    from fastapi.testclient import TestClient
    from tether.app import app
    store.init();task=store.capture('Dentist appointment');request=locations.prepare(task['id'],'Example Dental London')
    monkeypatch.setattr(locations,'urlopen',lambda *a,**k:io.BytesIO(json.dumps({'features':[FEATURE]}).encode()))
    client=TestClient(app,base_url='http://127.0.0.1')
    assert client.get('/api/chat/state').json()['locations'][0]['status']=='pending'
    searched=client.post('/api/locations/'+request['id']+'/search',json={'query':'Example Dental London'})
    assert searched.status_code==200 and searched.json()['status']=='ready'
    selected=searched.json()['results'][0]['id']
    assert client.post('/api/locations/'+request['id']+'/save',json={'result_id':selected}).status_code==200
    assert client.post('/api/locations/'+request['id']+'/save',json={'result_id':selected}).status_code==200
    assert len(store.get(task['id'])['entries'])==1
    assert client.get('/locations.js').status_code==200
