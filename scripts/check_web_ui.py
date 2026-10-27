"""Hosted-runner browser regressions against a static Pages build and synthetic data."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import importlib.util
import json
import os
import tempfile
import threading
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from playwright.sync_api import sync_playwright,expect
    from tend import store
    from tend.portable import export_data
    from voice_ui_checks import MOCKS,check_dictation,check_recording
    spec=importlib.util.spec_from_file_location('build_web',ROOT/'scripts/build_web.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    with tempfile.TemporaryDirectory(prefix='tether-web-ui-') as temp:
        folder=Path(temp);builder.build(folder/'tether-chat','/tether-chat/')
        os.environ['TEND_DB']=str(folder/'fixture.sqlite3');store.init()
        task=store.create('Prepare briefing','Keep the supporting documents together.',['Projects','Writing'])
        first=store.add(task['id'],'action','Contact the review team')
        second=store.add(task['id'],'action','Check the draft attachment')
        store.add_action_note(first['id'],'Request sent; waiting for a response.')
        store.update_action(first['id'],{'revisit_at':'2020-01-01T12:00:00Z'})
        store.update(task['id'],{'due_at':'2026-10-27T12:00:00Z'})
        backup=folder/'portable.json';backup.write_text(json.dumps(export_data()),encoding='utf-8')
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(folder)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}/tether-chat/'
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1280,'height':900})
                context.add_init_script(MOCKS)
                context.add_init_script("""const originalFetch=window.fetch.bind(window);
                  window.fetch=async(input,options)=>{const response=await originalFetch(input,options);
                    if(String(input).startsWith('https://provider.example/') && typeof options?.body==='string'){
                      const body=JSON.parse(options.body);
                      if(body.tools && !body.messages.some(m=>m.role==='tool'))await new Promise(resolve=>setTimeout(resolve,1800));
                    }return response};""")
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base);frame=page.frame_locator('#app-frame')
                check_dictation(page,frame)
                frame.get_by_label('Message tether').fill('/brief');frame.get_by_role('button',name='Send',exact=True).click()
                expect(frame.get_by_role('heading',name='Daily brief')).to_be_visible(timeout=15000)
                frame.get_by_role('button',name='Settings',exact=True).click()
                frame.locator('#importData').set_input_files(backup)
                expect(frame.locator('#storageStatus')).to_contain_text('Imported 1 tasks')
                frame.get_by_role('button',name='Close settings').click()
                frame.get_by_role('link',name='Tasks',exact=True).click()
                expect(frame.get_by_role('heading',name='All Tasks (1)',exact=True)).to_be_visible()
                frame.locator('.task-row').filter(has_text='Prepare briefing').click()
                frame.locator('[data-action-id="'+first['id']+'"]').click()
                expect(frame.locator('#actionDrawer')).to_contain_text('Request sent; waiting for a response.')
                frame.get_by_label('Add action note').fill('A browser update under this action.')
                frame.get_by_role('button',name='Add note',exact=True).click()
                expect(frame.locator('#actionDrawer')).to_contain_text('A browser update under this action.')
                frame.get_by_label('Completed',exact=True).check()
                frame.get_by_role('button',name='Save changes',exact=True).click()
                expect(frame.locator('#actionDrawer')).to_be_hidden()
                frame.locator('[data-action-id="'+second['id']+'"]').click()
                expect(frame.get_by_label('Completed',exact=True)).not_to_be_checked()
                expect(frame.locator('#actionDrawer')).not_to_contain_text('A browser update under this action.')
                frame.get_by_role('button',name='Close action item').click()

                # Fake only the remote paid provider; the UI, IndexedDB and tool runner are real.
                requests=[]
                # An unexpected destination must never receive even the synthetic key.
                context.route('https://**/*',lambda route:route.fulfill(status=418,body='Unexpected provider URL'))
                def provider(route):
                    if route.request.method=='OPTIONS':
                        route.fulfill(status=204,headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'authorization,content-type'});return
                    body=route.request.post_data_json;requests.append(body)
                    if body['messages'][-1]['content']=='Respond with OK.':message={'role':'assistant','content':'OK'}
                    elif len([m for m in body['messages'] if m['role']=='tool'])==0:
                        message={'role':'assistant','content':None,'tool_calls':[{'id':'capture-test-001','type':'function',
                          'function':{'name':'capture','arguments':json.dumps({'title':'Created in browser'})}}]}
                    else:
                        result=json.loads(next(m['content'] for m in body['messages'] if m['role']=='tool'))
                        message={'role':'assistant','content':'Saved [Created in browser](/board#task/'+result['id']+').'}
                    route.fulfill(status=200,content_type='application/json',headers={'Access-Control-Allow-Origin':'*'},
                                  body=json.dumps({'choices':[{'message':message}]}))
                context.route('https://provider.example/v1/chat/completions',provider)
                context.route('https://provider.example/v1/audio/transcriptions',lambda route:route.fulfill(status=200,
                  content_type='application/json',headers={'Access-Control-Allow-Origin':'*'},body=json.dumps({'text':'Recorded voice draft.'})))
                frame.get_by_role('button',name='Settings',exact=True).click()
                frame.get_by_label('Provider API base URL').fill('https://provider.example/v1')
                frame.get_by_label('Model',exact=True).fill('test-model')
                frame.get_by_label('API key',exact=True).fill('synthetic-test-key')
                frame.get_by_label('Save encrypted key on this device').check()
                frame.get_by_label('Unlock passphrase',exact=True).fill('synthetic-passphrase')
                frame.get_by_role('button',name='Save connection',exact=True).click()
                expect(frame.locator('#providerStatus')).to_contain_text('Connection saved')
                expect(frame.get_by_label('Provider API base URL')).to_have_value('https://provider.example/v1')
                frame.get_by_role('button',name='Lock key',exact=True).click()
                expect(frame.locator('#keyStatus')).to_contain_text('Saved key is locked')
                frame.get_by_label('Unlock passphrase',exact=True).fill('synthetic-passphrase')
                frame.get_by_role('button',name='Unlock saved key',exact=True).click()
                expect(frame.locator('#providerStatus')).to_contain_text('Saved key unlocked')
                frame.get_by_role('button',name='Test connection',exact=True).click()
                expect(frame.locator('#providerStatus')).to_contain_text('Connection successful')
                frame.get_by_role('button',name='Close settings').click()
                frame.get_by_role('link',name='Conversation',exact=True).click()
                check_recording(page,frame)
                frame.get_by_label('Message tether').fill('Capture a new task for me.')
                frame.get_by_role('button',name='Send',exact=True).click()
                expect(frame.locator('.chat-pending')).to_be_visible()
                frame.get_by_role('link',name='Tasks',exact=True).click()
                frame.get_by_role('link',name='Conversation',exact=True).click()
                expect(frame.locator('.bubble.assistant').filter(has_text='Saved Created in browser')).to_have_count(1,timeout=15000)
                frame.get_by_role('link',name='Tasks',exact=True).click()
                expect(frame.locator('.task-row').filter(has_text='Created in browser')).to_have_count(1)
                assert len([request for request in requests if 'tools' in request])==2,requests

                frame.get_by_role('link',name='Conversation',exact=True).click()
                frame.get_by_label('Message tether').fill('/snapshot 2026-10-26 to 2026-11-01')
                frame.get_by_role('button',name='Send',exact=True).click()
                calendar=frame.frame_locator('.snapshot-frame')
                expect(calendar.locator('.task-title').filter(has_text='Prepare briefing')).to_be_visible(timeout=15000)
                with page.expect_download() as download:calendar.get_by_role('button',name='SVG',exact=True).click()
                assert download.value.suggested_filename.endswith('.svg')
                frame.get_by_role('button',name='Settings',exact=True).click()
                with page.expect_download() as download:frame.get_by_role('button',name='Download backup',exact=True).click()
                exported=json.loads(Path(download.value.path()).read_text())
                assert len(exported['data']['tasks'])==2
                assert 'synthetic-test-key' not in json.dumps(exported)
                assert len(exported['data']['notes'])==2
                frame.get_by_role('button',name='Close settings').click()
                page.reload();expect(frame.locator('.bubble.user').filter(has_text='Capture a new task for me.')).to_have_count(1)
                expect(frame.locator('.bubble.assistant').filter(has_text='Saved Created in browser')).to_have_count(1)
                # On a secure localhost origin the service worker must support a fresh offline load.
                page.wait_for_function('navigator.serviceWorker.controller !== null')
                context.set_offline(True);page.reload()
                expect(frame.get_by_role('link',name='Tasks',exact=True)).to_be_visible()
                frame.get_by_role('link',name='Tasks',exact=True).click()
                expect(frame.get_by_role('heading',name='All Tasks (2)',exact=True)).to_be_visible()
                context.set_offline(False)
                page.set_viewport_size({'width':390,'height':844})
                expect(frame.locator('#board')).to_be_visible()
                assert page.locator('#app-frame').evaluate('(e)=>e.contentDocument.documentElement.scrollWidth<=e.contentWindow.innerWidth'), 'Mobile horizontal overflow'
                frame.get_by_role('link',name='Conversation',exact=True).click()
                expect(frame.get_by_role('button',name='Attention',exact=True)).to_be_visible()
                frame.get_by_role('button',name='Attention',exact=True).click()
                expect(frame.locator('#right')).to_be_visible()
                assert not errors,errors
                browser.close()
                print('Browser edition: shared UI, voice dictation and recording, desktop import, action scope, encrypted keys, navigation during AI, backup, calendar, mobile, and offline checks passed.')
        finally:server.shutdown();server.server_close()


if __name__=='__main__':main()
