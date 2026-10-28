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
                screen.get_by_role('button',name='Today',exact=True).click()
                expect(screen.locator('#display-quick')).to_contain_text('9 scheduled items')
                calendar=screen.frame_locator('#display-calendar')
                expect(calendar.locator('.task')).to_have_count(9)
                heights=calendar.locator('.day').evaluate_all('(nodes)=>nodes.map(n=>n.getBoundingClientRect().height)')
                assert len(set(heights))==1,heights
                calendar.locator('.task').first.hover()
                expect(calendar.locator('#calendar-preview')).to_be_visible()
                assert calendar.locator('.day-items').evaluate_all('(nodes)=>nodes.some(n=>n.scrollHeight>n.clientHeight)')
                calendar.locator('.today .day-date').click()
                expect(calendar.locator('#day-dialog')).to_be_visible()
                expect(calendar.locator('#day-dialog .task')).to_have_count(9)
                calendar.get_by_role('button',name='Close date details').click()
                screen.get_by_role('button',name='Month',exact=True).click()
                expect(screen.locator('#view-month')).to_have_attribute('aria-pressed','true')
                page.reload()
                screen=page.frame_locator('#app-frame')
                expect(screen.locator('#view-month')).to_have_attribute('aria-pressed','true')
                page.set_viewport_size({'width':390,'height':844})
                calendar=screen.frame_locator('#display-calendar')
                expect(calendar.locator('.task')).to_have_count(9)
                assert screen.locator('body').evaluate('(node)=>node.scrollWidth<=innerWidth'), 'Display overflows mobile width'
                calendar.locator('.today .day-date').click()
                expect(calendar.locator('#day-dialog')).to_be_visible()
                calendar.locator('#day-dialog .task').first.click()
                expect(screen.locator('#panel')).to_be_visible()
                # Switching workspaces must preserve this release and never expose Work data.
                release=page.evaluate('window.TETHER_CONFIG.version')
                screen.get_by_role('combobox',name='Work or Home').select_option('home')
                expect(screen.get_by_role('combobox',name='Work or Home')).to_have_value('home')
                screen.get_by_role('link',name='Display',exact=True).click()
                expect(screen.locator('#display-quick')).to_contain_text('0 scheduled items')
                assert page.evaluate('window.TETHER_CONFIG.version')==release
                screen.get_by_role('combobox',name='Work or Home').select_option('work')
                expect(screen.locator('#display-quick')).to_contain_text('9 scheduled items')
                page.go_back()
                expect(screen.get_by_role('combobox',name='Work or Home')).to_have_value('home')
                expect(screen.locator('#display-quick')).to_contain_text('0 scheduled items')
                assert not errors, errors
                browser.close()
                print('Display UI checks passed: fixed cells, overflow, previews, date dialog, persistent month, mobile, task navigation.')
        finally:server.shutdown()


if __name__=='__main__':main()
