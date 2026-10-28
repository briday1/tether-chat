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
    from tether import store
    from tether.portable import export_data
    from voice_ui_checks import MOCKS,check_dictation,check_recording
    from attention_ui_checks import check_attention_updates
    from note_ui_checks import check_note_replies
    from provider_ui_checks import check_settings_appearance
    from context_ui_checks import check_task_context
    spec=importlib.util.spec_from_file_location('build_web',ROOT/'scripts/build_web.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    with tempfile.TemporaryDirectory(prefix='tether-web-ui-') as temp:
        folder=Path(temp);builder.build(folder/'tether-chat','/tether-chat/')
        os.environ['TETHER_DB']=str(folder/'fixture.sqlite3');store.init()
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
                executable=os.environ.get('TETHER_TEST_CHROMIUM')
                browser=pw.chromium.launch(**({'executable_path':executable} if executable else {}));context=browser.new_context(viewport={'width':1280,'height':900})
                context.add_init_script(MOCKS)
                context.add_init_script("""const originalFetch=window.fetch.bind(window);
                  window.fetch=async(input,options)=>{const response=await originalFetch(input,options);
                    if(String(input).startsWith('https://provider.example/') && typeof options?.body==='string'){
                      const body=JSON.parse(options.body);
                      if(body.tools && !body.messages.some(m=>m.role==='tool'))await new Promise(resolve=>setTimeout(resolve,1800));
                    }return response};""")
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base);frame=page.frame_locator('#app-frame')
                page.wait_for_function('!!window.tetherFetch')
                about_trigger=frame.get_by_role('button',name='About tether',exact=True)
                about_trigger.click()
                about_dialog=frame.get_by_role('dialog',name='About tether',exact=True)
                expect(about_dialog).to_be_visible()
                expect(about_dialog).to_contain_text('Version ')
                expect(about_dialog.get_by_role('link',name='Privacy policy')).to_have_attribute('href',base+'privacy.html')
                expect(about_dialog.get_by_role('link',name='Terms of service')).to_have_attribute('href',base+'terms.html')
                expect(page.locator('#legal')).to_have_count(0)
                page.keyboard.press('Escape')
                expect(about_dialog).not_to_be_visible()
                expect(about_trigger).to_be_focused()
                about_trigger.press('Enter')
                expect(about_dialog).to_be_visible()
                about_dialog.get_by_role('button',name='Close',exact=True).click()
                expect(about_trigger).to_be_focused()
                page.evaluate("""async()=>{const {Database,Model}=await import('./store.mjs');const db=await new Database('tether-chat-web:/tether-chat/').open();await db.write(s=>{new Model(s).create('Private legacy Work');s.settings={base_url:'https://old.example',model:'old',encrypted_key:{ciphertext:'retained'}};s.jobs=[{id:'old-pending',status:'queued'}]});db.db.close();localStorage.setItem('tether-web-draft:/tether-chat/','Old private draft')}""")
                check_dictation(page,frame)
                frame.get_by_label('Message tether').fill('Keep this draft while I connect.')
                frame.get_by_role('button',name='Send',exact=True).click()
                expect(frame.get_by_role('dialog',name='Settings',exact=True)).to_be_visible()
                check_settings_appearance(frame)
                expect(frame.locator('#inspectLegacy')).to_have_count(0)
                expect(frame.locator('#home-product-notice')).to_have_count(0)
                assert page.evaluate("localStorage.getItem('tether-web-draft:/tether-chat/')")=='Old private draft'
                assert page.evaluate("async()=>{const r=await (await window.tetherReady).fetch('/tether-chat/api/threads');return (await r.json()).length}")==0
                expect(frame.locator('#connectionMode')).to_contain_text('Requests go directly to your AI provider')
                expect(frame.locator('#providerStatus')).to_contain_text('Your message is still in the draft')
                expect(frame.get_by_label('Message tether')).to_have_value('Keep this draft while I connect.')
                expect(frame.locator('.bubble.user')).to_have_count(0)
                frame.get_by_role('button',name='Save AI connection',exact=True).click()
                expect(frame.locator('#providerStatus')).to_contain_text('Enter your API key')
                frame.get_by_role('button',name='Close settings').click()
                frame.get_by_label('Message tether').fill('/brief');frame.get_by_role('button',name='Send',exact=True).click()
                expect(frame.get_by_role('heading',name='Daily brief')).to_be_visible(timeout=15000)
                frame.get_by_role('button',name='Settings',exact=True).click()
                page.once('dialog',lambda dialog:dialog.accept())
                frame.locator('#otherSettings > summary').click()
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

                check_task_context(page,frame,'Prepare briefing')
                frame.get_by_role('link',name='Tasks',exact=True).click()

                # Fake only the remote paid provider; the UI, IndexedDB and tool runner are real.
                requests=[];model_requests=[];provider_error=None
                # An unexpected destination must never receive even the synthetic key.
                context.route('https://**/*',lambda route:route.fulfill(status=418,body='Unexpected provider URL'))
                def provider(route):
                    if route.request.method=='OPTIONS':
                        route.fulfill(status=204,headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'authorization,content-type'});return
                    body=route.request.post_data_json;requests.append(body)
                    if provider_error:
                        route.fulfill(status=429,content_type='application/json',headers={'Access-Control-Allow-Origin':'*'},body=json.dumps({'error':{'code':provider_error,'type':'insufficient_quota'}}));return
                    if body['messages'][-1]['content']=='Respond with OK.':message={'role':'assistant','content':'OK'}
                    elif body['messages'][-1]['content']=='Check the saved connection without reloading.':
                        assert route.request.headers['authorization']=='Bearer rotated-synthetic-key'
                        message={'role':'assistant','content':'Ready using the saved connection.'}
                    elif len([m for m in body['messages'] if m['role']=='tool'])==0:
                        message={'role':'assistant','content':None,'tool_calls':[{'id':'capture-test-001','type':'function',
                          'function':{'name':'capture','arguments':json.dumps({'title':'Created in browser'})}}]}
                    else:
                        result=json.loads(next(m['content'] for m in body['messages'] if m['role']=='tool'))
                        message={'role':'assistant','content':'Saved [Created in browser](/board#task/'+result['id']+').'}
                    route.fulfill(status=200,content_type='application/json',headers={'Access-Control-Allow-Origin':'*'},
                                  body=json.dumps({'choices':[{'message':message}]}))
                context.route('https://provider.example/v1/chat/completions',provider)
                def models(route):
                    if route.request.method=='OPTIONS':
                        route.fulfill(status=204,headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'authorization,content-type'});return
                    assert route.request.method=='GET'
                    model_requests.append(route.request.headers['authorization'])
                    route.fulfill(status=200,content_type='application/json',headers={'Access-Control-Allow-Origin':'*'},
                                  body=json.dumps({'data':[{'id':id,'supported_parameters':[] if id=='text-embedding-fixture' else ['tools']} for id in ['test-model','test-mini','changed-test-model','text-embedding-fixture']]}))
                context.route('https://provider.example/v1/models',models)

                frame.get_by_role('button',name='Settings',exact=True).click()
                frame.get_by_label('Provider API base URL').fill('https://provider.example/v1')
                frame.get_by_label('API key',exact=True).fill('synthetic-test-key')
                expect(frame.locator('#modelStatus')).to_contain_text('3 tool-calling models available')
                expect(frame.get_by_label('Model',exact=True)).to_have_value('test-mini')
                assert model_requests==['Bearer synthetic-test-key'] and requests==[]
                frame.get_by_label('Model',exact=True).select_option('test-model')
                frame.locator('#providerAdvanced').evaluate('(e)=>e.open=true')
                frame.get_by_label('Save encrypted key on this device').check()
                frame.locator('#providerAdvanced').evaluate('(e)=>e.open=true')
                frame.get_by_label('Unlock passphrase',exact=True).fill('synthetic-passphrase')
                # Test must save the newly entered key and fields, with no prior Save click.
                frame.locator('#providerActions').evaluate('(e)=>e.open=true')
                frame.get_by_role('button',name='Test connection',exact=True).click()
                expect(frame.locator('#providerStatus')).to_contain_text('Connection successful')
                # A billing error keeps the saved key usable and must not be retried.
                page.set_viewport_size({'width':1280,'height':1400})
                frame.locator('#provider').screenshot(path=str(folder/'connection.jpg'),type='jpeg',quality=90)
                page.set_viewport_size({'width':1280,'height':900})
                before=len(requests);provider_error='credit_balance_exhausted'
                frame.locator('#providerActions').evaluate('(e)=>e.open=true')
                frame.get_by_role('button',name='Test connection',exact=True).click()
                expect(frame.locator('#providerStatus')).to_contain_text('API credit balance is empty')
                expect(frame.locator('#keyStatus')).to_contain_text('Key is unlocked')
                assert len(requests)==before+1
                provider_error=None
                expect(frame.get_by_label('Provider API base URL')).to_have_value('https://provider.example/v1')
                frame.get_by_label('Provider API base URL').fill('https://wrong-provider.example/v1')
                assert frame.locator('#model option').evaluate_all('(options)=>options.map(o=>o.value)')==['']
                frame.locator('#providerActions').evaluate('(e)=>e.open=true')
                frame.get_by_role('button',name='Test connection',exact=True).click()
                expect(frame.locator('#providerStatus')).to_contain_text('Re-enter your API key')
                frame.get_by_label('Provider API base URL').fill('https://provider.example/v1')
                frame.get_by_label('Model',exact=True).select_option('changed-test-model')
                frame.locator('#providerActions').evaluate('(e)=>e.open=true')
                frame.get_by_role('button',name='Test connection',exact=True).click()
                expect(frame.locator('#providerStatus')).to_contain_text('Connection successful')
                frame.locator('#providerActions').evaluate('(e)=>e.open=true')
                frame.get_by_role('button',name='Lock key',exact=True).click()
                expect(frame.locator('#keyStatus')).to_contain_text('Saved key is locked')
                frame.locator('#providerAdvanced').evaluate('(e)=>e.open=true')
                frame.get_by_label('Unlock passphrase',exact=True).fill('synthetic-passphrase')
                frame.locator('#providerActions').evaluate('(e)=>e.open=true')
                frame.get_by_role('button',name='Unlock saved key',exact=True).click()
                expect(frame.locator('#providerStatus')).to_contain_text('Saved key unlocked')
                frame.locator('#providerActions').evaluate('(e)=>e.open=true')
                frame.get_by_role('button',name='Test connection',exact=True).click()
                expect(frame.locator('#providerStatus')).to_contain_text('Connection successful')
                # Save and close immediately, then chat while encryption/save is still pending.
                frame.get_by_role('button',name='Close settings').click()
                frame.get_by_role('link',name='Conversation',exact=True).click()
                frame.get_by_role('button',name='Settings',exact=True).click()
                frame.get_by_label('API key',exact=True).fill('rotated-synthetic-key')
                frame.locator('#providerAdvanced').evaluate('(e)=>e.open=true')
                frame.get_by_label('Unlock passphrase',exact=True).fill('synthetic-passphrase')
                frame.locator('#provider').evaluate('(form)=>form.requestSubmit()')
                frame.get_by_role('button',name='Close settings').click()
                frame.get_by_label('Message tether').fill('Check the saved connection without reloading.')
                frame.get_by_role('button',name='Send',exact=True).click()
                expect(frame.locator('.bubble.assistant').filter(has_text='Ready using the saved connection.')).to_have_count(1,timeout=15000)
                expect(frame.get_by_role('dialog',name='Settings',exact=True)).to_be_hidden()
                frame.get_by_role('button',name='Settings',exact=True).click()
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
                assert len([request for request in requests if 'tools' in request])==3,requests

                frame.get_by_role('link',name='Conversation',exact=True).click()
                frame.get_by_label('Message tether').fill('/snapshot 2026-10-26 to 2026-11-01')
                frame.get_by_role('button',name='Send',exact=True).click()
                calendar=frame.frame_locator('.snapshot-frame')
                expect(calendar.locator('.day-items .task-title').filter(has_text='Prepare briefing')).to_be_visible(timeout=15000)
                expect(calendar.locator('.dot')).to_have_count(0)
                calendar_height=frame.locator('.snapshot-frame').evaluate('(e)=>e.getBoundingClientRect().height')
                calendar.locator('.day-items .task').filter(has_text='Prepare briefing').first.click()
                expect(calendar.locator('#date-panel-items')).to_contain_text('Prepare briefing')
                expect(frame.locator('#chatSelection')).to_be_hidden()
                expect(calendar.locator('#details, #day-dialog, #calendar-preview, #png, #svg')).to_have_count(0)
                assert abs(frame.locator('.snapshot-frame').evaluate('(e)=>e.getBoundingClientRect().height')-calendar_height)<2
                frame.get_by_role('button',name='Settings',exact=True).click()
                frame.locator('#otherSettings').evaluate('(e)=>e.open=true')
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
                page.set_viewport_size({'width':1280,'height':900})
                frame.get_by_role('button',name='Settings',exact=True).click()
                frame.locator('#providerActions').evaluate('(e)=>e.open=true')
                frame.get_by_role('button',name='Forget key',exact=True).click()
                expect(frame.locator('#providerStatus')).to_contain_text('Saved key removed')
                frame.get_by_role('button',name='Close settings').click()
                check_attention_updates(page,frame,'/tether-chat/api',base+'?view=board','/tether-chat/board.html',embedded=True)
                check_note_replies(page,frame,'/tether-chat/api')
                assert not errors,errors
                browser.close()
                print('Browser edition: shared UI, voice, imports, scoped actions, encrypted keys, durable chat, backup, calendar, mobile, offline, and automatic Attention updates passed.')
        finally:server.shutdown();server.server_close()


if __name__=='__main__':main()
