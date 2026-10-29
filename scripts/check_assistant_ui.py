"""Phone regressions for decisions, saved defaults, calendar reminders and confirmed addresses."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import importlib.util
import json
import os
import sys
import tempfile
import threading
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    from playwright.sync_api import sync_playwright,expect
    spec=importlib.util.spec_from_file_location('build_web',ROOT/'scripts/build_web.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    with tempfile.TemporaryDirectory(prefix='tether-assistant-ui-') as temp:
        folder=Path(temp);builder.build(folder/'tether-chat','/tether-chat/')
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(folder)))
        threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}/tether-chat/'
        try:
            with sync_playwright() as pw:
                executable=os.environ.get('TETHER_TEST_CHROMIUM');browser=pw.chromium.launch(**({'executable_path':executable} if executable else {}))
                context=browser.new_context(viewport={'width':390,'height':844},timezone_id='America/New_York');page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                calls=[];lookups=[];task_id=None;asked=False
                def provider(route):
                    nonlocal asked
                    if route.request.method=='OPTIONS':route.fulfill(status=204,headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'authorization,content-type'});return
                    body=route.request.post_data_json;calls.append(body);tools=[m for m in body['messages'] if m['role']=='tool'];user=next(m['content'] for m in reversed(body['messages']) if m['role']=='user')
                    if not tools:
                        if user.startswith('Remind me') and not asked:asked=True;message={'content':'Which day next week?'}
                        elif user.startswith('Find the address'):message={'tool_calls':[{'id':'location','type':'function','function':{'name':'request_location_lookup','arguments':json.dumps({'id':task_id,'query':'Example Dental London'})}}]}
                        else:message={'tool_calls':[{'id':'capture','type':'function','function':{'name':'capture','arguments':json.dumps({'title':'Dentist appointment next Monday' if user=='Just figure it out' else 'Dentist appointment',**({'remind_at':'next year','categories':['Unsorted']} if user=='Just figure it out' else {})})}}]}
                    elif user.startswith('Find the address'):message={'content':'Confirm the place and city in the address card, then choose the correct location.'}
                    else:message={'content':'Scheduled [Dentist appointment](/board#task/'+json.loads(tools[-1]['content'])['id']+').'}
                    route.fulfill(content_type='application/json',headers={'Access-Control-Allow-Origin':'*'},body=json.dumps({'choices':[{'message':{'role':'assistant',**message}}]}))
                def models(route):
                    if route.request.method=='OPTIONS':route.fulfill(status=204,headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'authorization,content-type'});return
                    route.fulfill(content_type='application/json',headers={'Access-Control-Allow-Origin':'*'},body=json.dumps({'data':[{'id':'tool-mini','supported_parameters':['tools']},{'id':'text-only'},{'id':'embedding-model','supported_parameters':['tools']}]}))
                def photon(route):
                    lookups.append(route.request);assert 'authorization' not in route.request.headers
                    route.fulfill(content_type='application/json',headers={'Access-Control-Allow-Origin':'*'},body=json.dumps({'features':[{'type':'Feature','geometry':{'type':'Point','coordinates':[-0.12,51.5]},'properties':{'name':'Example Dental','street':'High Street','housenumber':'12','city':'London','country':'United Kingdom','osm_type':'N','osm_id':123}}]}))
                context.route('https://provider.example/v1/chat/completions',provider);context.route('https://provider.example/v1/models',models);context.route('https://photon.komoot.io/api/**',photon)
                page.goto(base);frame=page.frame_locator('#app-frame')
                def api(path,method='GET',body=None):
                    page.wait_for_function("document.querySelector('#app-frame')?.contentWindow?.tetherBeforeChat")
                    return page.locator('#app-frame').evaluate('(e,args)=>e.contentWindow.fetch("/tether-chat/api"+args.path,{method:args.method,headers:{"Content-Type":"application/json"},body:args.body===null?undefined:JSON.stringify(args.body)}).then(r=>r.json())',{'path':path,'method':method,'body':body})
                def send(text):frame.get_by_label('Message tether').fill(text);frame.get_by_role('button',name='Send',exact=True).click()
                frame.get_by_role('button',name='Settings',exact=True).click()
                expect(frame.get_by_label('First day of the week')).to_have_value('1');expect(frame.get_by_label('Morning',exact=True)).to_have_value('09:00');expect(frame.get_by_label('Night',exact=True)).to_have_value('21:00')
                frame.get_by_label('Provider API base URL').fill('https://provider.example/v1');frame.get_by_label('API key',exact=True).fill('synthetic-key')
                expect(frame.locator('#modelStatus')).to_contain_text('1 tool-calling model');expect(frame.get_by_label('Model',exact=True)).to_have_value('tool-mini')
                expect(frame.locator('select#model')).to_be_visible();expect(frame.locator('#model option')).to_have_count(1)
                expect(frame.locator('input#model, datalist#modelOptions')).to_have_count(0)
                if os.environ.get('TETHER_MODEL_PICKER_SCREENSHOT'):frame.locator('#provider').screenshot(path=os.environ['TETHER_MODEL_PICKER_SCREENSHOT'])
                frame.get_by_role('button',name='Save AI connection',exact=True).click();expect(frame.locator('#providerStatus')).to_contain_text('saved')
                frame.locator('#otherSettings > summary').click()
                frame.get_by_label('First day of the week').select_option('0');frame.get_by_label('Morning',exact=True).fill('10:30');frame.get_by_label('Night',exact=True).fill('22:15');frame.get_by_role('button',name='Save preferences',exact=True).click();expect(frame.locator('#preferencesStatus')).to_contain_text('saved')
                frame.get_by_role('button',name='Close settings',exact=True).click();page.reload()
                assert api('/preferences')=={'week_start':0,'morning_time':'10:30','night_time':'22:15'}
                send('Remind me to make a dentist appointment next week')
                expect(frame.locator('.bubble.assistant').filter(has_text='Scheduled Dentist appointment')).to_have_count(1,timeout=15000)
                tasks=api('/threads');assert len(tasks)==1;task=tasks[0];task_id=task['id'];assert task['categories']==['Health'];assert task['due_at'] is None
                local_date=page.evaluate('(s)=>{const d=new Date(s);return [d.getDay(),d.getHours(),d.getMinutes()]}',task['revisit_at']);assert local_date==[0,10,30],local_date
                send('Just figure it out');expect(frame.locator('.bubble.assistant').filter(has_text='Scheduled Dentist appointment')).to_have_count(2,timeout=15000)
                tasks=api('/threads');assert len(tasks)==1 and tasks[0]['id']==task_id and tasks[0]['revisit_at']!=task['revisit_at'],tasks;task=tasks[0]
                date=page.evaluate('(s)=>{const d=new Date(s);return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0")}',task['revisit_at'])
                action=api('/threads/'+task_id+'/entries','POST',{'kind':'action','body':'Call reception'});api('/actions/'+action['id'],'PATCH',{'revisit_at':task['revisit_at']})
                send('/snapshot '+date+' to '+date);calendar=frame.frame_locator('.snapshot-frame');expect(calendar.locator('.day-items .task-title').filter(has_text='Dentist appointment')).to_be_visible(timeout=15000);expect(calendar.locator('.day-items .task-title').filter(has_text='Call reception')).to_be_visible();expect(calendar.locator('.day-items .task-context').filter(has_text='Attention')).to_have_count(2)
                calendar.locator('.day-items .task').filter(has_text='Call reception').click();expect(calendar.locator('#date-panel-items')).to_contain_text('Call reception');expect(frame.locator('#chatSelection')).to_be_hidden()
                send('Find the address for my dentist appointment')
                card=frame.locator('.location-card');expect(card).to_contain_text('Confirm the place and city',timeout=15000);assert not lookups
                card.get_by_label('Place and town/city').fill('Example Dental London UK');card.get_by_role('button',name='Confirm and find address',exact=True).click();expect(card).to_contain_text('12 High Street');assert len(lookups)==1
                card.get_by_role('button',name='Use this location',exact=True).click();expect(card).to_contain_text('Saved with the task.')
                expect(card.get_by_role('link',name='Open in Google Maps',exact=True)).to_have_attribute('href',__import__('re').compile(r'^https://www.google.com/maps/search/\?api=1&query=.*12\+High\+Street'))
                detail=api('/threads/'+task_id);assert sum('Location:' in e['body'] for e in detail['entries'])==1
                assert page.locator('#app-frame').evaluate('(e)=>e.contentDocument.documentElement.scrollWidth<=e.contentWindow.innerWidth'),'Mobile horizontal overflow'
                screenshot=os.environ.get('TETHER_ASSISTANT_SCREENSHOT')
                if screenshot:page.screenshot(path=screenshot)
                assert not errors,errors
                browser.close();print('Phone assistant decisions, saved defaults, reminder snapshots and confirmed address selection passed.')
        finally:server.shutdown();server.server_close()
if __name__=='__main__':main()
