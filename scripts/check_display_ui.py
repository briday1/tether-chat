"""Persistent Display and fixed calendar regressions with synthetic browser data."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import importlib.util
import os
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]


def main():
    from playwright.sync_api import sync_playwright, expect
    spec=importlib.util.spec_from_file_location('build_web',ROOT/'scripts/build_web.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    with tempfile.TemporaryDirectory(prefix='tether-display-') as temp:
        builder.build(Path(temp)/'tether-chat','/tether-chat/')
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=temp))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=os.environ.get('TETHER_TEST_CHROMIUM'),args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':1280,'height':900})
                page.add_init_script("const originalInterval=window.setInterval;window.setInterval=(fn,ms,...args)=>originalInterval(fn,ms===60000?250:ms,...args)")
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/tether-chat/?view=display')
                page.wait_for_function('!!window.tetherFetch')
                page.evaluate('''async()=>{const runtime=await window.tetherReady;
                  const date=new Date(),today=[date.getFullYear(),String(date.getMonth()+1).padStart(2,'0'),String(date.getDate()).padStart(2,'0')].join('-');
                  for(let n=0;n<9;n++){
                    const response=await runtime.fetch('/tether-chat/api/threads',{method:'POST',body:JSON.stringify({title:'Calendar item '+n,categories:['Personal']})});const task=await response.json();
                    await runtime.fetch('/tether-chat/api/threads/'+task.id,{method:'PATCH',body:JSON.stringify({due_at:today})});
                  }}''')
                screen=page.frame_locator('#app-frame')
                screen.get_by_role('button',name='View settings and navigation').click()
                screen.get_by_role('button',name='Today',exact=True).click()
                screen.locator('#display-close').click()
                expect(screen.locator('#display-quick')).to_contain_text('9 scheduled items')
                calendar=screen.frame_locator('#display-calendar')
                expect(calendar.locator('.task')).to_have_count(9)
                heights=calendar.locator('.day').evaluate_all('(nodes)=>nodes.map(n=>n.getBoundingClientRect().height)')
                assert max(heights)-min(heights)<=1,heights
                calendar.locator('.task').first.hover()
                expect(calendar.locator('#calendar-preview')).to_be_visible()
                expect(calendar.locator('.today .day-more')).to_have_text('9 items')
                calendar.locator('.today .day-date').click()
                expect(calendar.locator('#day-dialog')).to_be_visible()
                expect(calendar.locator('#day-dialog .task')).to_have_count(9)
                calendar.get_by_role('button',name='Close date details').click()
                screen.locator('#display-menu').click()
                screen.get_by_role('button',name='Month',exact=True).click()
                expect(screen.locator('#view-month')).to_have_attribute('aria-pressed','true')
                page.reload()
                screen=page.frame_locator('#app-frame')
                expect(screen.locator('#view-month')).to_have_attribute('aria-pressed','true')
                # A six-row month fits in landscape tablets, including an expanded date drawer.
                screen.locator('#display-menu').click()
                screen.locator('#display-date').fill('2027-05-15')
                screen.locator('#display-date').dispatch_event('change')
                screen.locator('#display-close').click()
                calendar=screen.frame_locator('#display-calendar')
                expect(calendar.locator('.day')).to_have_count(42)
                for size in [{'width':1024,'height':768},{'width':1180,'height':820},{'width':768,'height':1024}]:
                    page.set_viewport_size(size)
                    assert screen.locator('body').evaluate('(node)=>node.scrollHeight<=innerHeight+1 && node.scrollWidth<=innerWidth'), size
                    assert calendar.locator('#grid').evaluate('(node)=>node.getBoundingClientRect().bottom<=innerHeight+1'), size
                    heights=calendar.locator('.day').evaluate_all('(nodes)=>nodes.map(n=>Math.round(n.getBoundingClientRect().height))')
                    assert max(heights)-min(heights)<=1,heights
                screen.locator('#display-menu').click()
                screen.get_by_role('button',name='Today',exact=True).click()
                screen.locator('#display-close').click()
                # New local/synced data appears on the automatic refresh without interaction.
                page.evaluate('''async()=>{const runtime=await window.tetherReady;const date=new Date();const today=[date.getFullYear(),String(date.getMonth()+1).padStart(2,'0'),String(date.getDate()).padStart(2,'0')].join('-');const r=await runtime.fetch('/tether-chat/api/threads',{method:'POST',body:JSON.stringify({title:'Automatic refresh item'})});const t=await r.json();await runtime.fetch('/tether-chat/api/threads/'+t.id,{method:'PATCH',body:JSON.stringify({due_at:today})})}''')
                expect(screen.locator('#display-quick')).to_contain_text('10 scheduled items')
                page.set_viewport_size({'width':390,'height':844})
                calendar=screen.frame_locator('#display-calendar')
                expect(calendar.locator('.task')).to_have_count(10)
                assert screen.locator('body').evaluate('(node)=>node.scrollWidth<=innerWidth'), 'Display overflows mobile width'
                calendar.locator('.today .day-date').click()
                expect(calendar.locator('#day-dialog')).to_be_visible()
                calendar.locator('#day-dialog .task').first.click()
                expect(screen.get_by_role('button',name='Edit task',exact=True)).to_be_visible()
                expect(screen.get_by_role('button',name='Use as chat context',exact=True)).to_be_visible()
                # Browser is Home-only, including old Work routes and history.
                expect(screen.get_by_role('combobox',name='Work or Home')).to_have_count(0)
                screen.get_by_role('link',name='Display',exact=True).click()
                expect(screen.locator('#display-quick')).to_contain_text('10 scheduled items')
                page.go_back()
                expect(screen.get_by_role('button',name='Edit task',exact=True)).to_be_visible()
                page.go_forward()
                expect(screen.locator('#display-quick')).to_contain_text('10 scheduled items')
                page.goto(f'http://127.0.0.1:{server.server_port}/tether-chat/?view=display&workspace=work')
                expect(page.frame_locator('#app-frame').locator('#display-quick')).to_contain_text('10 scheduled items')
                assert 'workspace=home' in page.url
                assert not errors, errors
                browser.close()
                print('Display UI checks passed: fixed cells, overflow, previews, date dialog, persistent month, mobile, task navigation.')
        finally:server.shutdown()


if __name__=='__main__':main()
