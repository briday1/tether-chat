"""Real-API browser tests for navigation, Attention submission, and compact styling.
Only the paid provider is replaced, in this test server process. No user data is used.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
BASE='http://127.0.0.1:18768'


def serve_fixture():
    from tend import ai,store
    from tend.app import app
    import uvicorn
    def fake(message,progress=None,history=None):
        if message=='Complete an Attention action before a simulated failure':
            task=next(task for task in store.list_threads() if task['title']=='Partial failure fixture')
            action=next(action for action in store.get(task['id'])['entries'] if action['kind']=='action')
            store.update_action(action['id'],{'done':True})
            if progress:progress('Action completion saved')
            raise ValueError('Synthetic failure after the action was saved')
        if progress:progress('Working on the requested update')
        time.sleep(4)
        return {'answer':'Finished: '+message,'actions':[]}
    ai.chat=fake
    ai.public_config=lambda:{'has_key':False}
    uvicorn.run(app,host='127.0.0.1',port=18768,log_level='warning')


def main():
    from playwright.sync_api import sync_playwright,expect
    from attention_ui_checks import check_attention_updates
    from tend import store
    with tempfile.TemporaryDirectory(prefix='tether-chat-session-') as folder:
        os.environ['TEND_DB']=str(Path(folder)/'session.sqlite3')
        os.environ['TEND_CONFIG']=str(Path(folder)/'provider.json')
        os.environ.pop('TEND_AI_API_KEY',None)
        store.init();task=store.create('Prepare briefing',summary='Confirm the access review before the briefing.',categories=['Projects'])
        action=store.add(task['id'],'action','Contact the review team')
        store.update_action(action['id'],{'revisit_at':'2020-01-01T12:00:00Z'})
        store.add(task['id'],'action','Check the attachment')
        server=subprocess.Popen([sys.executable,__file__,'--serve-fixture'],cwd=ROOT,env=os.environ.copy(),stdout=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    with urlopen(BASE+'/api/health',timeout=1):break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('Session fixture server did not start')
            with sync_playwright() as pw:
                browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':900})
                page=context.new_page();errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(BASE,wait_until='networkidle')
                page.locator('#message').fill('Keep this reply running while I work.')
                with page.expect_response(lambda r:r.url.endswith('/api/chat/jobs') and r.request.method=='POST'):
                    page.locator('#message').press('Enter')
                page.get_by_role('link',name='Tasks',exact=True).click()
                page.get_by_role('link',name='Conversation',exact=True).click()
                expect(page.locator('.chat-pending')).to_be_visible()
                expect(page.locator('.bubble.assistant').filter(has_text='Finished: Keep this reply running while I work.')).to_have_count(1,timeout=15000)
                page.reload(wait_until='networkidle')
                expect(page.locator('.bubble.user').filter(has_text='Keep this reply running while I work.')).to_have_count(1)
                expect(page.locator('.bubble.assistant').filter(has_text='Finished: Keep this reply running while I work.')).to_have_count(1)
                # Enter on an Attention button sends it once without destroying a draft.
                page.locator('#message').fill('Keep my unsent draft')
                button=page.locator('#due button').filter(has_text='Contact the review team');expect(button).to_be_visible();button.focus()
                with page.expect_response(lambda r:r.url.endswith('/api/chat/jobs') and r.request.method=='POST') as response:
                    page.keyboard.press('Enter')
                payload=response.value.request.post_data_json
                assert payload['attention']=={'task_id':task['id'],'action_id':action['id']}
                expect(page.locator('#message')).to_have_value('Keep my unsent draft')
                expect(page.locator('.bubble.assistant').filter(has_text='What is the latest on')).to_have_count(1,timeout=10000)
                current=store.get(task['id']);assert not current['revisit_at']
                assert not any(a['done'] for a in current['entries'])
                assert next(a for a in current['entries'] if a['id']==action['id'])['revisit_at']=='2020-01-01T12:00:00Z'
                # A single theme produces exactly the same wordmark on both pages.
                for theme in ['light','dark','sage','rose','dusk','ocean','sepia','solarized-light','solarized-dark']:
                    page.evaluate('(t)=>{localStorage.setItem("tend-ui-theme",t);document.documentElement.dataset.theme=t}',theme)
                    before=page.locator('.brand-word').evaluate('(e)=>[getComputedStyle(e).color,getComputedStyle(e.firstElementChild).color]')
                    page.get_by_role('link',name='Tasks',exact=True).click()
                    after=page.locator('.brand-word').evaluate('(e)=>[getComputedStyle(e).color,getComputedStyle(e.firstElementChild).color]')
                    assert before==after,(theme,before,after)
                    category=page.locator('.category-row').filter(has_text='Projects')
                    assert category.evaluate('(e)=>getComputedStyle(e).borderLeftWidth==="1px"')
                    pill=page.locator('.task-row .category-tag').first
                    assert pill.evaluate('(e)=>getComputedStyle(e,"::before").content==="none"')
                    page.get_by_role('link',name='Conversation',exact=True).click()
                page.goto(BASE+'/board',wait_until='networkidle');page.locator('.task-row').filter(has_text='Prepare briefing').click()
                edit=page.locator('.edit-task-button');expect(edit).to_be_visible();assert edit.bounding_box()['height']<=32
                page.locator('.action-list-row').first.click();close=page.locator('#actionDrawer .reference-close');assert close.bounding_box()['width']==38 and close.bounding_box()['height']==38;expect(close.locator('svg')).to_be_visible()
                # Notes saved in Tasks appear only on that action in Conversation.
                drawer=page.locator('#actionDrawer')
                drawer.get_by_label('Add action note',exact=True).fill('Spoke with the reviewer; awaiting confirmation.')
                drawer.get_by_role('button',name='Add note',exact=True).click()
                expect(drawer.locator('.action-note-body')).to_have_text('Spoke with the reviewer; awaiting confirmation.')
                page.keyboard.press('Escape')
                current=store.get(task['id']);chosen=next(a for a in current['entries'] if a['body']=='Contact the review team')
                assert len(chosen['notes'])==1 and all(not a.get('notes') for a in current['entries'] if a['id']!=chosen['id'])
                page.get_by_role('link',name='Conversation',exact=True).click()
                page.locator('#chat a[href="/board#action/'+task['id']+'/'+chosen['id']+'"]').first.click()
                drawer=page.locator('#chatSelection')
                expect(drawer.locator('.action-note-body')).to_have_text('Spoke with the reviewer; awaiting confirmation.')
                drawer.locator('.action-note').get_by_role('button',name='Edit',exact=True).click()
                drawer.get_by_label('Edit action note',exact=True).fill('Confirmation received.')
                drawer.get_by_role('button',name='Save note',exact=True).click()
                expect(drawer.locator('.action-note-body')).to_have_text('Confirmation received.')
                page.once('dialog',lambda dialog:dialog.accept())
                drawer.locator('.action-note').get_by_role('button',name='Delete',exact=True).click()
                expect(drawer.locator('.action-note-body')).to_have_count(0)
                page.keyboard.press('Escape')
                check_attention_updates(page,page,'/api',BASE+'/board','/board')
                failure=store.create('Partial failure fixture')
                failed_action=store.add(failure['id'],'action','Finish before provider failure')
                store.update_action(failed_action['id'],{'revisit_at':'2020-01-01T12:00:00Z'})
                notice=page.locator('#due button[data-action-id="'+failed_action['id']+'"]')
                expect(notice).to_be_visible(timeout=6000)
                page.get_by_label('Message tether').fill('Complete an Attention action before a simulated failure')
                page.get_by_role('button',name='Send',exact=True).click()
                expect(page.locator('.chat-pending').filter(has_text='Synthetic failure after the action was saved')).to_be_visible(timeout=6000)
                expect(notice).to_have_count(0,timeout=2000)
                assert not errors,errors
                browser.close()
            print('PASS: navigation-safe chat, scoped check-ins and notes, themes, and automatic Attention updates after drawer saves, other-tab edits, outside writes, and partial chat failures.')
        finally:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait()

if __name__=='__main__':
    if '--serve-fixture' in sys.argv:serve_fixture()
    else:main()
