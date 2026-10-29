"""Browser regressions against isolated data, never the user's task database.

Default: start the real FastAPI app. --mock-api: test only the frontend using
API fixtures, for offline environments lacking application dependencies.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
THEMES=['light','dark','solarized-light','solarized-dark','sepia','sage','rose','dusk','ocean']


def seed(folder):
    os.environ['TETHER_DB']=str(folder/'ui.sqlite3')
    os.environ['TETHER_CONFIG']=str(folder/'provider.json')
    from tether import store
    store.init()
    task=store.create('Prepare briefing',summary='Keep the supporting documents together.',categories=['Projects'])
    first=store.add(task['id'],'action','Contact the review team')
    store.add_action_note(first['id'],'Request sent; waiting for the review team to confirm access.')
    store.update_action(first['id'],{'due_at':'2030-10-27T12:00:00+00:00','revisit_at':'2030-10-26T09:00:00+00:00'})
    second=store.add(task['id'],'action','Check the draft attachment')
    store.update_action(second['id'],{'due_at':'2030-11-02T12:00:00+00:00'})
    store.create('Renew certificate',categories=['Operations'])
    text=f'In [Projects](/board#category/Projects), [Prepare briefing](/board#task/{task["id"]}) includes *Contact the review team*.'
    store.remember('assistant',text)
    return task['id'],first['id'],second['id']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mock-api',action='store_true');args=parser.parse_args()
    from playwright.sync_api import sync_playwright,expect
    out=ROOT/'docs'/'screenshots';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tether-chat-ui-') as temp:
        folder=Path(temp);task_id,action_id,sibling_id=seed(folder)
        from tether import store
        server=None;base='http://127.0.0.1:18767'
        if not args.mock_api:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','tether.app:app','--host','127.0.0.1','--port','18767'],cwd=ROOT,env=os.environ.copy(),stdout=subprocess.DEVNULL)
            for _ in range(100):
                try:
                    with urlopen(base+'/api/health',timeout=1) as r:
                        if r.status==200:break
                except OSError:time.sleep(.2)
            else:raise RuntimeError('Test server did not start')
        try:
            with sync_playwright() as pw:
                executable=os.environ.get('TETHER_TEST_CHROMIUM')
                browser=pw.chromium.launch(**({'executable_path':executable} if executable else {}))
                page=browser.new_page(viewport={'width':1440,'height':900}, timezone_id='America/New_York', locale='en-US')
                errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
                if args.mock_api:
                    def route(request):
                        from urllib.parse import urlparse
                        path=urlparse(request.request.url).path
                        if path.startswith('/api/'):
                            if path=='/api/board':data=store.board()
                            elif path=='/api/archived':data=[]
                            elif path=='/api/mentions':
                                tasks=store.list_threads()
                                data={'categories':sorted({c for t in tasks for c in t['categories']}),'tasks':tasks,'actions':store.query("SELECT * FROM entries WHERE kind='action'")}
                            elif path=='/api/chat/state':data={'jobs':[],'messages':[{'id':'sample','role':'assistant','body':'Example','html':f'<p>In <a href="/board#category/Projects">Projects</a>, <a href="/board#task/{task_id}">Prepare briefing</a> includes <em>Contact the review team</em>.</p>'}]}
                            elif path.startswith('/api/threads/'):data=store.get(path.split('/')[-1])
                            elif path.startswith('/api/actions/') and request.request.method=='PATCH':data=store.update_action(path.split('/')[-1],request.request.post_data_json)
                            else:data={'items':[]}
                            request.fulfill(status=200,content_type='application/json',body=json.dumps(data));return
                        file={'/':'index.html','/board':'board.html'}.get(path,path.lstrip('/'))
                        if file not in {'index.html','board.html','theme.css','theme.js','chat.js','action-notes.js','voice.js','updates.js','notes.js','notes.css','provider-models.js','preferences.js','locations.js','favicon.svg'}:request.fulfill(status=404);return
                        mime='text/css' if file.endswith('.css') else 'application/javascript' if file.endswith('.js') else 'text/html'
                        request.fulfill(status=200,content_type=mime,body=(ROOT/'tether'/file).read_text(encoding='utf-8'))
                    page.route('**/*',route)
                else:page.route('**/api/attention*',lambda route:route.fulfill(status=200,content_type='application/json',body='{"items":[]}'))
                page.goto(base+'/',wait_until='networkidle')
                from provider_ui_checks import check_provider_settings
                check_provider_settings(page)
                expect(page.locator('.brand-word')).to_have_text('tether.')
                assert page.title()=='tether-chat'
                assert page.locator('#chatCategories').count()==0
                category=page.locator('#chat a[href="/board#category/Projects"]')
                expect(category).to_have_count(1)
                for theme in THEMES:
                    page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
                    assert category.evaluate('(a)=>getComputedStyle(a).color')==page.evaluate("()=>{const s=document.createElement('span');s.style.color='var(--accent)';document.body.append(s);const c=getComputedStyle(s).color;s.remove();return c}")
                page.evaluate("document.documentElement.dataset.theme='light'")
                category.click()
                drawer=page.locator('#chatSelection');expect(drawer).to_be_visible();expect(drawer.locator('h2')).to_have_text('Projects')
                assert drawer.evaluate('(d)=>getComputedStyle(d).position')=='fixed'
                box=drawer.bounding_box();assert box['x']>=900 and box['x']+box['width']==1440,box
                drawer.get_by_role('button',name='Prepare briefing').click()
                drawer.get_by_role('button',name='Contact the review team').click()
                expect(drawer.locator('h2')).to_have_text('Contact the review team')
                page.screenshot(path=str(out/'chat-action-drawer.png'))
                page.keyboard.press('Escape');expect(drawer).to_be_hidden()
                # Explicit model Markdown links must use the same drawer, not navigate away.
                page.locator('#chat a[href="/board#task/'+task_id+'"]').click()
                expect(drawer.locator('h2')).to_have_text('Prepare briefing')
                assert page.url==base+'/'
                page.keyboard.press('Escape')
                page.goto(base+'/board',wait_until='networkidle')
                check_provider_settings(page)
                expect(page.locator('.brand-word')).to_have_text('tether.')
                page.locator('.task-row').filter(has_text='Prepare briefing').click()
                expect(page.locator('.action-list-row')).to_have_count(2)
                bounds=[page.locator(s).bounding_box() for s in ['.category-section','.task-section','.actions-section']]
                assert bounds[0]['x']<bounds[1]['x']<bounds[2]['x'],bounds
                assert max(b['y'] for b in bounds)-min(b['y'] for b in bounds)<5,bounds
                assert page.locator('.actions-section input').count()==0
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(out/'task-action-columns.png'))
                page.locator('.action-list-row').filter(has_text='Contact the review team').click()
                action_drawer=page.locator('#actionDrawer');expect(action_drawer).to_be_visible()
                assert action_drawer.evaluate('(d)=>getComputedStyle(d).position')=='fixed'
                action_drawer.locator('input[name="due_at"]').fill('2030-10-28T09:30')
                action_drawer.locator('input[name="revisit_at"]').fill('2030-10-27T10:00')
                action_drawer.get_by_role('button',name='Save changes').click()
                expect(action_drawer).to_be_hidden()
                updated=store.get(task_id)
                assert not updated['due_at'] and not updated['revisit_at']
                assert next(a for a in updated['entries'] if a['id']==sibling_id)['due_at']=='2030-11-02T12:00:00+00:00'
                assert next(a for a in updated['entries'] if a['id']==action_id)['due_at'].startswith('2030-10-28')
                page.goto(base+f'/board#action/{task_id}/{action_id}',wait_until='networkidle')
                expect(page.locator('#actionDrawer h2')).to_have_text('Contact the review team')
                page.keyboard.press('Escape')
                page.set_viewport_size({'width':390,'height':844})
                page.goto(base+'/',wait_until='networkidle');page.locator('#chat a[href="/board#category/Projects"]').click()
                expect(drawer).to_be_visible();box=drawer.bounding_box();assert box['x']>=-1 and box['width']<=390
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.keyboard.press('Escape')
                if not args.mock_api:
                    # Real installed Work chat uses the same inline date panel as Home.
                    page.set_viewport_size({'width':1280,'height':900})
                    page.locator('#message').fill('/snapshot 2030-10-01 to 2030-10-31')
                    page.get_by_role('button',name='Send',exact=True).click()
                    calendar=page.frame_locator('.snapshot-frame').last
                    expect(calendar.locator('.day[data-date="2030-10-28"] .task-marker')).to_have_count(1)
                    calendar.locator('.day[data-date="2030-10-28"] .day-date').click()
                    expect(calendar.locator('#date-panel')).to_have_attribute('data-date','2030-10-28')
                    expect(calendar.locator('#date-panel-items')).to_contain_text('Contact the review team')
                    expect(drawer).to_be_hidden()
                    expect(calendar.locator('#png, #svg, #details, #day-dialog')).to_have_count(0)
                    page.locator('#message').fill('/snapshot 2030-10-28 to 2030-11-03')
                    page.get_by_role('button',name='Send',exact=True).click()
                    calendar=page.frame_locator('.snapshot-frame').last
                    expect(calendar.locator('.day-items .task').filter(has_text='Check the draft attachment')).to_have_count(1)
                    expect(calendar.locator('.task-marker')).to_have_count(0)
                    calendar.locator('.day-items .task').filter(has_text='Check the draft attachment').click()
                    expect(calendar.locator('#date-panel-items')).to_contain_text('Check the draft attachment')
                    # A weekend task includes weekend columns, not a hidden sixth item.
                    expect(calendar.locator('#weekdays span')).to_have_count(7)
                    from datetime import datetime, timezone
                    from display_ui_checks import check_display_header
                    page.clock.install(time=datetime(2026,10,28,21,28,tzinfo=timezone.utc))
                    page.goto(base+'/display?workspace=work',wait_until='networkidle')
                    check_display_header(page, page)
                    calendar=page.frame_locator('#display-calendar')
                    expect(calendar.locator('#date-panel-title')).to_have_text('Today')
                    expect(page.locator('#view-week, #view-month')).to_have_count(0)
                    assert calendar.locator('body').evaluate('()=>new URL(location.href).searchParams.get("workspace")')=='work'
                    from recurrence_ui_checks import check_recurrence
                    check_recurrence(page, page)
                    page.goto(base+'/',wait_until='networkidle')
                # Reproduce a desktop upgrade with an old script still in the
                # WebView cache. Its matchReferences hook must remain harmless.
                legacy=(ROOT/'tests/fixtures/legacy-chat-2026-16.js').read_text()
                page.route('**/chat.js*',lambda route:route.fulfill(status=200,content_type='application/javascript',body=legacy))
                page.reload(wait_until='networkidle')
                expect(page.locator('#chat a[href="/board#task/'+task_id+'"]').first).to_be_visible()
                if not args.mock_api:
                    page.locator('#message').fill('/brief')
                    page.get_by_role('button',name='Send',exact=True).click()
                    expect(page.locator('.bubble.assistant').filter(has_text='Daily brief')).to_have_count(1,timeout=15000)
                assert not errors,errors
                browser.close()
            print('PASS: header, 9 themes, category/task/action drawers, three columns, action-specific saves, deep links, mobile sizing, no JS errors.'+(' FRONTEND FIXTURES ONLY.' if args.mock_api else ' Real API.'))
        finally:
            if server:
                server.terminate()
                try:server.wait(timeout=5)
                except subprocess.TimeoutExpired:server.kill();server.wait()

if __name__=='__main__':main()
