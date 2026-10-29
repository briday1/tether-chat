"""Shared Display date panel: tablet, touch, inactivity and real chat snapshots."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone
import importlib.util
import os
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]


def main():
    from playwright.sync_api import sync_playwright, expect
    spec = importlib.util.spec_from_file_location('build_web', ROOT / 'scripts/build_web.py')
    builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    with tempfile.TemporaryDirectory(prefix='tether-display-') as temp:
        builder.build(Path(temp) / 'tether-chat', '/tether-chat/')
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=temp))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}/tether-chat/'
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path=os.environ.get('TETHER_TEST_CHROMIUM'), args=['--no-sandbox'])
                page = browser.new_page(viewport={'width': 1280, 'height': 900}, has_touch=True, reduced_motion='reduce', timezone_id='America/New_York', locale='en-US')
                page.clock.install(time=datetime(2026, 10, 28, 21, 28, tzinfo=timezone.utc))
                errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '?view=display')
                page.wait_for_function('!!window.tetherFetch')
                dates = page.evaluate('''async()=>{const runtime=await window.tetherReady;
                  const format=d=>[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
                  const date=new Date(),today=format(date);date.setDate(date.getDate()+1);const other=format(date);
                  for(let n=0;n<9;n++){
                    const r=await runtime.fetch('/tether-chat/api/threads',{method:'POST',body:JSON.stringify({title:'Calendar item '+n,categories:['Personal']})});const task=await r.json();
                    await runtime.fetch('/tether-chat/api/threads/'+task.id,{method:'PATCH',body:JSON.stringify({due_at:today})});
                  }
                  for(let n=0;n<7;n++){const r=await runtime.fetch('/tether-chat/api/threads',{method:'POST',body:JSON.stringify({title:'Other date '+n+' '+('Long task text '.repeat(8))})});const task=await r.json();await runtime.fetch('/tether-chat/api/threads/'+task.id,{method:'PATCH',body:JSON.stringify({due_at:other})})}
                  for(let n=0;n<8;n++){const r=await runtime.fetch('/tether-chat/api/threads',{method:'POST',body:JSON.stringify({title:'Six row busy date '+n})});const task=await r.json();await runtime.fetch('/tether-chat/api/threads/'+task.id,{method:'PATCH',body:JSON.stringify({due_at:'2027-05-16'})})}
                  return {today,other};}''')
                screen = page.frame_locator('#app-frame')
                from display_ui_checks import check_display_header
                check_display_header(page, screen)
                screen.locator('#display-today').click()
                calendar = screen.frame_locator('#display-calendar')
                expect(calendar.locator('#date-panel-title')).to_have_text('Today')
                expect(calendar.locator('#date-panel-items .task')).to_have_count(9)
                expect(calendar.locator('.today .task-marker')).to_have_count(3)
                expect(calendar.locator('.today .day-more')).to_have_text('+6 more')
                expect(screen.locator('#view-week, #view-month')).to_have_count(0)
                expect(calendar.locator('.downloads, #png, #svg')).to_have_count(0)
                heights = calendar.locator('.day').evaluate_all('(nodes)=>nodes.map(n=>n.getBoundingClientRect().height)')
                assert max(heights) - min(heights) <= 1, heights
                # Hover and focus do not select; explicit click updates only the fixed sidebar.
                other = calendar.locator('[data-date="'+dates['other']+'"] .day-date')
                if other.count():
                    before = calendar.locator('#grid').bounding_box()
                    other.hover()
                    expect(calendar.locator('#date-panel-title')).to_have_text('Today')
                    other.focus()
                    expect(calendar.locator('#date-panel-title')).to_have_text('Today')
                    other.click()
                    expect(calendar.locator('#date-panel')).to_have_attribute('data-date', dates['other'])
                    expect(calendar.locator('#date-panel-items .task')).to_have_count(7)
                    expect(calendar.locator('[data-date="'+dates['other']+'"] .day-more')).to_have_text('+4 more')
                    assert calendar.locator('#grid').bounding_box() == before
                    expect(calendar.locator('#calendar-preview:visible, #day-dialog:visible, #details:visible')).to_have_count(0)
                    page.clock.fast_forward(10000)
                    calendar.locator('#date-panel-items').dispatch_event('scroll')
                    page.clock.fast_forward(10000)
                    expect(calendar.locator('#date-panel')).to_have_attribute('data-date', dates['other'])
                    page.clock.fast_forward(6000)
                    expect(calendar.locator('#date-panel-title')).to_have_text('Today')
                    expect(calendar.locator('#date-panel-items .task')).to_have_count(9)
                    # Keyboard selection and sidebar interaction preserve an active reading session.
                    other.hover()
                    other.focus()
                    expect(calendar.locator('#date-panel-title')).to_have_text('Today')
                    page.keyboard.press('Space')
                    expect(calendar.locator('#date-panel')).to_have_attribute('data-date', dates['other'])
                    calendar.locator('#date-panel').dispatch_event('keydown', {'key': 'ArrowDown'})
                    page.clock.fast_forward(16000)
                    expect(calendar.locator('#date-panel-title')).to_have_text('Today')
                # Six-row historical month stays fixed, while Today is fetched outside its range.
                for _ in range(7):
                    screen.locator('#display-next').click()
                calendar = screen.frame_locator('#display-calendar')
                expect(calendar.locator('.day')).to_have_count(42)
                expect(calendar.locator('#date-panel-title')).to_have_text('Today')
                expect(calendar.locator('#date-panel-items .task')).to_have_count(9)
                for size in [{'width':1024,'height':600},{'width':1024,'height':768},{'width':1180,'height':820},{'width':768,'height':1024}]:
                    page.set_viewport_size(size)
                    assert screen.locator('body').evaluate('(node)=>node.scrollHeight<=innerHeight+1 && node.scrollWidth<=innerWidth'), size
                    assert calendar.locator('#grid').evaluate('(node)=>node.getBoundingClientRect().bottom<=innerHeight+1'), size
                    heights = calendar.locator('.day').evaluate_all('(nodes)=>nodes.map(n=>Math.round(n.getBoundingClientRect().height))')
                    assert max(heights)-min(heights)<=1, heights
                    busy=calendar.locator('.day[data-date="2027-05-16"]')
                    expect(busy.locator('.task-marker')).to_have_count(3)
                    expect(busy.locator('.day-more')).to_have_text('+5 more')
                    assert busy.evaluate('(day)=>{const box=day.getBoundingClientRect(),items=day.querySelector(".day-items").getBoundingClientRect();return [...day.querySelectorAll(".task-marker")].every(node=>node.getBoundingClientRect().bottom<=items.bottom+1)&&day.querySelector(".day-more").getBoundingClientRect().bottom<=box.bottom+1}'), size
                calendar.locator('[data-date="2027-05-15"] .day-date').click()
                expect(calendar.locator('#date-panel')).to_have_attribute('data-date', '2027-05-15')
                expect(calendar.locator('#date-panel-items')).to_contain_text('No scheduled items')
                page.clock.fast_forward(16000)
                expect(calendar.locator('#date-panel-title')).to_have_text('Today')
                # Reopening always starts in the current month, not a persisted historical month.
                page.reload()
                screen = page.frame_locator('#app-frame')
                calendar = screen.frame_locator('#display-calendar')
                expect(screen.locator('#display-title')).to_have_text('October 2026')
                expect(calendar.locator('#date-panel')).to_have_attribute('data-date', dates['today'])
                expect(screen.locator('#view-week')).to_have_count(0)
                # Chat week/month embeds use the same date panel, with expanded week cards.
                screen.locator('#display-menu').click()
                screen.get_by_role('link', name='Conversation', exact=True).click()
                expect(screen.get_by_label('Message tether')).to_be_visible()
                def snapshot(command):
                    screen.get_by_label('Message tether').fill(command)
                    screen.get_by_role('button', name='Send', exact=True).click()
                    return screen.frame_locator('.snapshot-frame').last
                # Explicit dates avoid assumptions about model calls or current week preferences.
                first=dates['today'][:8]+'01'
                last=page.evaluate('(s)=>{const d=new Date(s+"T12:00:00");d.setMonth(d.getMonth()+1,0);return [d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),String(d.getDate()).padStart(2,"0")].join("-")}', first)
                month=snapshot('/snapshot '+first+' to '+last)
                expect(month.locator('.today .task-marker')).to_have_count(3)
                expect(month.locator('.today .day-more')).to_have_text('+6 more')
                expect(month.locator('#date-panel-items .task')).to_have_count(9)
                expect(month.locator('#png, #svg')).to_have_count(0)
                page.set_viewport_size({'width':390,'height':844})
                month.locator('.today .day-date').tap()
                expect(month.locator('#date-panel-title')).to_have_text('Today')
                assert month.locator('body').evaluate('()=>document.documentElement.scrollWidth<=innerWidth'), 'Chat month horizontal overflow'
                week=snapshot('/snapshot '+dates['today']+' to '+dates['other'])
                expect(week.locator('.today .day-items .task')).to_have_count(9)
                expect(week.locator('.today .task-marker')).to_have_count(0)
                week_other=week.locator('[data-date="'+dates['other']+'"] .day-date')
                week_other.hover()
                week_other.focus()
                expect(week.locator('#date-panel-title')).to_have_text('Today')
                page.keyboard.press('Enter')
                expect(week.locator('#date-panel-items .task')).to_have_count(7)
                expect(week.locator('#date-panel')).to_have_attribute('data-date', dates['other'])
                # Midnight changes the default Today panel without requiring a reload.
                page.clock.set_system_time(datetime(2026, 10, 29, 4, 1, tzinfo=timezone.utc))
                page.clock.fast_forward(61000)
                expect(week.locator('#date-panel-title')).to_have_text('Today')
                expect(week.locator('#date-panel')).to_have_attribute('data-date', dates['other'])
                expect(week.locator('#date-panel-items .task')).to_have_count(7)
                from recurrence_ui_checks import check_recurrence
                screen.get_by_role('link', name='Display', exact=True).click()
                expect(screen.locator('#display-title')).to_be_visible()
                check_recurrence(page, screen)
                assert not errors, errors
                browser.close()
                print('Month Display and chat snapshots passed: fixed markers, all sidebar items, 15s return, navigation, tablet/phone, no exports/popups.')
        finally:
            server.shutdown(); server.server_close()


if __name__ == '__main__': main()
