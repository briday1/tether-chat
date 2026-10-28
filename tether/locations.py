"""Prepare locally; only the user's confirmation endpoint may perform a search."""
import json
import re
import uuid
from datetime import datetime,timezone,timedelta
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from . import store

SEARCH_URL='https://photon.komoot.io/api/'
def maps_url(query):return 'https://www.google.com/maps/search/?'+urlencode({'api':'1','query':query})
def initialize():
    with store.conn() as c:c.execute('CREATE TABLE IF NOT EXISTS location_requests(id TEXT PRIMARY KEY,value TEXT NOT NULL)')
def _all(c):return [json.loads(row['value']) for row in c.execute('SELECT value FROM location_requests ORDER BY rowid')]
def _put(c,row):c.execute('INSERT OR REPLACE INTO location_requests(id,value) VALUES(?,?)',(row['id'],json.dumps(row)))
def _target(c,id):
    row=c.execute('SELECT value FROM location_requests WHERE id=?',(id,)).fetchone()
    if not row:raise ValueError('Location request not found')
    row=json.loads(row['value'])
    if not c.execute('SELECT id FROM threads WHERE id=? AND archived_at IS NULL',(row['task_id'],)).fetchone():raise ValueError('Task not found or archived')
    return row
def _query(value):
    if not isinstance(value,str) or not value.strip() or len(value)>500:raise ValueError('Enter a place and town/city (up to 500 characters)')
    return value.strip()
def requests():
    initialize()
    with store.conn() as c:
        tasks={r['id']:r['title'] for r in c.execute('SELECT id,title FROM threads WHERE archived_at IS NULL')}
        return [{**r,'task_title':tasks[r['task_id']],'maps_search_url':maps_url(r['query'])} for r in _all(c) if r['task_id'] in tasks][-10:]
def prepare(id,query):
    initialize();query=_query(query)
    with store.conn() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT id FROM threads WHERE id=? AND archived_at IS NULL',(id,)).fetchone():raise ValueError('Task not found or archived')
        for row in _all(c):
            if row['task_id']==id and row['query'].casefold()==query.casefold():return {**row,'confirmation_required':row['status']=='pending'}
        row={'id':uuid.uuid4().hex,'task_id':id,'query':query,'status':'pending','results':[],'created_at':store.now(),'searched_at':None,'saved_entry_id':None}
        _put(c,row)
    return {**row,'confirmation_required':True,'message':'A confirmation card is ready. No address lookup has run. The user must confirm the place/city, search, and choose the correct result.'}
def parse_places(data):
    if not isinstance(data,dict) or not isinstance(data.get('features'),list):raise ValueError('Address search returned an invalid response. Try Google Maps below.')
    results=[]
    for feature in data['features'][:8]:
        if not isinstance(feature,dict):continue
        p=feature.get('properties') or {};coordinates=(feature.get('geometry') or {}).get('coordinates') or []
        if len(coordinates)!=2:continue
        lon,lat=coordinates
        if type(lat) not in (int,float) or type(lon) not in (int,float) or not -90<=lat<=90 or not -180<=lon<=180:continue
        def clean(value):return value.strip()[:200] if isinstance(value,str) else ''
        street=' '.join(filter(None,[clean(p.get('housenumber')),clean(p.get('street'))]))
        parts=[clean(p.get('name')),street,clean(p.get('city') or p.get('town') or p.get('village') or p.get('district')),clean(p.get('state')),clean(p.get('postcode')),clean(p.get('country'))]
        address=', '.join(dict.fromkeys(part for part in parts if part))
        if not address:continue
        id=str(p.get('osm_type') or 'place')+':'+str(p.get('osm_id') or f'{lat},{lon}')
        if any(r['id']==id for r in results):continue
        results.append({'id':id,'address':address,'lat':lat,'lon':lon,'maps_url':maps_url(address),'has_street':bool(street)})
    return results
def search(id,query):
    initialize();query=_query(query);stamp=store.now();token=uuid.uuid4().hex
    with store.conn() as c:
        c.execute('BEGIN IMMEDIATE');row=_target(c,id)
        if row['status']=='saved':raise ValueError('This location is already saved')
        all_rows=_all(c);now=datetime.now(timezone.utc)
        cached=next((r for r in all_rows if r['query'].casefold()==query.casefold() and r.get('searched_at') and now-datetime.fromisoformat(r['searched_at'])<timedelta(days=1) and r['status'] in ('ready','saved')),None)
        if cached:
            row.update(query=query,status='ready',results=cached['results'],searched_at=cached['searched_at'],error=None);_put(c,row);return row
        last=max((r.get('search_started_at') or '' for r in all_rows),default='')
        if last and now-datetime.fromisoformat(last)<timedelta(seconds=2):raise ValueError('Wait a moment before another address search')
        row.update(query=query,status='searching',search_token=token,search_started_at=stamp,error=None);_put(c,row)
    error=None;results=[]
    try:
        request=Request(SEARCH_URL+'?'+urlencode({'q':query,'limit':5}),headers={'Accept':'application/json','User-Agent':'tether-chat address lookup (https://github.com/briday1/tether-chat)'})
        with urlopen(request,timeout=15) as response:data=json.loads(response.read(1000000))
        results=parse_places(data)
    except Exception:
        error='Address search is unavailable. Try again later or open Google Maps below.'
    with store.conn() as c:
        c.execute('BEGIN IMMEDIATE');row=_target(c,id)
        if row.get('search_token')==token:
            row.update(status='pending' if error else 'ready',results=results,error=error,searched_at=None if error else store.now(),search_token=None);_put(c,row)
    return row

def save(id,result_id):
    initialize()
    with store.conn() as c:
        c.execute('BEGIN IMMEDIATE');row=_target(c,id)
        if row.get('saved_entry_id'):return {'request':row,'entry':dict(c.execute('SELECT * FROM entries WHERE id=?',(row['saved_entry_id'],)).fetchone())}
        result=next((r for r in row['results'] if r['id']==result_id),None)
        if row['status']!='ready' or not result:raise ValueError('Choose a result from the confirmed search')
        address=re.sub(r'([\\`*_{}\[\]()<>|])',r'\\\1',result['address']).replace('\n',' ').replace('\r',' ')
        body='Location: '+address+'\n\n[Google Maps]('+result['maps_url']+')\n\nAddress data: [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), via Photon. Selected by you.'
        entry={'id':uuid.uuid4().hex,'thread_id':row['task_id'],'kind':'thought','body':body,'done':0,'created_at':store.now()}
        c.execute('INSERT INTO entries(id,thread_id,kind,body,done,created_at) VALUES(:id,:thread_id,:kind,:body,:done,:created_at)',entry)
        c.execute('UPDATE threads SET updated_at=? WHERE id=?',(entry['created_at'],row['task_id']))
        row.update(status='saved',saved_entry_id=entry['id'],selected=result);_put(c,row)
    return {'request':row,'entry':entry}
