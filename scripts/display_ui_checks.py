"""Shared Home/Work Display header regressions in a non-UTC browser timezone."""
from datetime import datetime, timezone
from pathlib import Path


def check_display_header(page, screen):
    from playwright.sync_api import expect
    clock = screen.locator('#display-clock')
    calendar = screen.frame_locator('#display-calendar')

    def settled_today():
        # The title/clock update before refresh's asynchronous snapshot request.
        # Await its completion before skipping fake time, so the interval is not
        # coalesced while refresh still has its in-flight guard set.
        status = screen.locator('#display-status')
        status.evaluate('(node)=>node.textContent=""')
        screen.locator('#display-today').click()
        expect(status).to_contain_text('Updated ')

    expect(screen.locator('#display-clock-date')).to_have_text('Wednesday, October 28')
    expect(screen.locator('#display-clock-time')).to_have_text('5:28 PM')
    expect(screen.locator('#display-title')).to_have_text('October 2026')
    expect(screen.locator('#display-sidebar')).to_be_hidden()
    expect(screen.locator('#display-previous')).to_have_attribute('aria-label', 'Previous month')
    expect(screen.locator('#display-next')).to_have_attribute('aria-label', 'Next month')
    # Native buttons work with keyboard without opening settings or reloading the app.
    screen.locator('body').evaluate('(node)=>node.dataset.headerTest="retained"')
    screen.locator('#display-next').focus()
    page.keyboard.press('Enter')
    expect(screen.locator('#display-title')).to_have_text('November 2026')
    screen.locator('#display-next').click()
    expect(screen.locator('#display-title')).to_have_text('December 2026')
    screen.locator('#display-next').click()
    expect(screen.locator('#display-title')).to_have_text('January 2027')
    screen.locator('#display-previous').focus()
    page.keyboard.press('Space')
    expect(screen.locator('#display-title')).to_have_text('December 2026')
    expect(screen.locator('body')).to_have_attribute('data-header-test', 'retained')
    expect(screen.locator('#display-sidebar')).to_be_hidden()
    screen.locator('#display-today').click()
    expect(screen.locator('#display-title')).to_have_text('October 2026')
    expect(calendar.locator('#date-panel-title')).to_have_text('Today')
    expect(calendar.locator('.today .day-date')).to_have_attribute('aria-current', 'date')
    date = calendar.locator('[data-date="2026-10-29"] .day-date')
    date.hover()
    expect(calendar.locator('#date-panel')).to_have_attribute('data-date', '2026-10-28')
    date.focus()
    expect(calendar.locator('#date-panel')).to_have_attribute('data-date', '2026-10-28')
    page.keyboard.press('Enter')
    expect(calendar.locator('#date-panel')).to_have_attribute('data-date', '2026-10-29')
    expect(calendar.locator('#date-panel-hint')).to_have_count(0)
    # Selected date does not steal actual Today's visual/accessible identity.
    expect(calendar.locator('.today')).to_have_attribute('data-date', '2026-10-28')
    expect(calendar.locator('[aria-current="date"]')).to_have_count(1)
    screen.locator('#display-today').click()
    expect(calendar.locator('#date-panel-title')).to_have_text('Today')
    # Browsing can cross years without duplicate controls in the navigation drawer.
    for _ in range(16):
        screen.locator('#display-next').click()
    expect(screen.locator('#display-title')).to_have_text('February 2028')
    expect(calendar.locator('[data-date="2028-02-29"]')).to_have_count(1)
    expect(calendar.locator('[data-date="2028-02-30"]')).to_have_count(0)
    page.clock.fast_forward(16000)
    expect(calendar.locator('#date-panel-title')).to_have_text('Today')
    expect(screen.locator('#display-title')).to_have_text('February 2028')
    # Reopening ignores stale historical anchors; Today is the first rendered panel.
    screen.locator('body').evaluate("()=>{const key=`tether-display:${location.pathname}:${window.tetherWorkspace||'work'}`;localStorage.setItem(key,JSON.stringify({anchor:'2028-02-01',followingToday:false,density:'compact'}));location.reload()}")
    expect(screen.locator('#display-title')).to_have_text('October 2026')
    expect(calendar.locator('#date-panel-title')).to_have_text('Today')
    expect(calendar.locator('#date-panel')).to_have_attribute('data-date', '2026-10-28')
    expect(screen.locator('.display-footer, #display-quick')).to_have_count(0)
    expect(screen.locator('#display-sync')).to_be_hidden()
    screen.locator('#display-menu').click()
    expect(screen.locator('#display-sidebar nav a')).to_have_text(['Conversation', 'Tasks', 'Display'])
    expect(screen.locator('#display-sidebar input, #display-sidebar select')).to_have_count(0)
    screen.locator('#display-close').click()
    expect(screen.locator('#display-date, #display-density, #previous, #next, #today')).to_have_count(0)
    assert screen.locator('.display-calendar').evaluate('(n)=>getComputedStyle(n).borderTopWidth==="0px"')
    assert calendar.locator('#date-panel').evaluate('(n)=>getComputedStyle(n).borderLeftWidth==="0px"')
    assert calendar.locator('#date-panel .task').evaluate_all('(nodes)=>nodes.every(n=>getComputedStyle(n).borderLeftWidth==="0px")')
    assert calendar.locator('.weekdays span').first.evaluate('(n)=>parseFloat(getComputedStyle(n).fontSize)>=14')
    assert calendar.locator('.day-date').first.evaluate('(n)=>parseFloat(getComputedStyle(n).fontSize)>=16')
    assert screen.locator('#display-clock-date').evaluate('(n)=>parseFloat(getComputedStyle(n).fontSize)>=16')
    page.set_viewport_size({'width':1280,'height':900})
    artifacts=Path('artifacts');artifacts.mkdir(exist_ok=True)
    workspace=screen.locator('body').evaluate("()=>window.tetherWorkspace||'work'")
    page.screenshot(path=str(artifacts/f'display-{workspace}-1280.png'))
    # Fit the complete clock and navigation at dock, portrait-tablet and phone sizes.
    for width, height in [(1024, 600), (768, 1024), (390, 844), (320, 640)]:
        page.set_viewport_size({'width': width, 'height': height})
        assert screen.locator('body').evaluate('()=>document.documentElement.scrollWidth<=innerWidth'), (width, height)
        for selector in ['#display-previous', '#display-title', '#display-next', '#display-today', '#display-clock', '#display-settings']:
            assert screen.locator(selector).evaluate('(node)=>{const b=node.getBoundingClientRect();return b.left>=0&&b.right<=innerWidth&&b.top>=0&&b.bottom<=innerHeight&&node.scrollWidth<=node.clientWidth+1}'), (width, height, selector)
    page.screenshot(path=str(artifacts/f'display-{workspace}-320.png'))
    page.set_viewport_size({'width': 1280, 'height': 900})
    check_display_settings(page, screen)
    page.clock.set_system_time(datetime(2026, 10, 28, 21, 28, tzinfo=timezone.utc))
    page.clock.fast_forward(75000)
    expect(screen.locator('#display-clock-date')).to_have_text('Wednesday, October 28')
    expect(screen.locator('#display-clock-time')).to_have_text('5:29 PM')
    # UTC is already October 29; the UI still shows October 28 until local midnight.
    page.clock.set_system_time(datetime(2026, 10, 29, 3, 59, 45, tzinfo=timezone.utc))
    settled_today()
    expect(screen.locator('#display-clock-date')).to_have_text('Wednesday, October 28')
    expect(screen.locator('#display-clock-time')).to_have_text('11:59 PM')
    page.clock.fast_forward(30000)
    expect(screen.locator('#display-clock-date')).to_have_text('Thursday, October 29')
    expect(screen.locator('#display-clock-time')).to_have_text('12:00 AM')
    page.clock.fast_forward(61000)
    expect(calendar.locator('.today')).to_have_attribute('data-date', '2026-10-29')
    expect(calendar.locator('.today .day-date')).to_have_attribute('aria-current', 'date')
    expect(calendar.locator('#date-panel')).to_have_attribute('data-date', '2026-10-29')
    page.clock.set_system_time(datetime(2026, 11, 1, 3, 59, 45, tzinfo=timezone.utc))
    settled_today()
    expect(screen.locator('#display-title')).to_have_text('October 2026')
    page.clock.fast_forward(90000)
    expect(screen.locator('#display-title')).to_have_text('November 2026')
    expect(calendar.locator('.today')).to_have_attribute('data-date', '2026-11-01')
    # Restore the test fixture's original day for the remaining calendar scenarios.
    page.clock.set_system_time(datetime(2026, 10, 28, 21, 28, tzinfo=timezone.utc))
    screen.locator('#display-today').click()
    expect(screen.locator('#display-clock-date')).to_have_text('Wednesday, October 28')
    expect(screen.locator('#display-clock-time')).to_have_text('5:28 PM')
    expect(calendar.locator('#date-panel')).to_have_attribute('data-date', '2026-10-28')

    check_calendar_week_preference(page, screen)

    from task_details_ui_checks import check_task_details
    check_task_details(page, screen)
    from display_packing_ui_checks import check_display_packing
    check_display_packing(page, screen)


def check_display_settings(page, screen):
    """General settings overlay preserves the dock and never resumes chat work."""
    from playwright.sync_api import expect
    page.add_init_script('''if(new URLSearchParams(location.search).get('settings')==='display'){
      window.__settingsRequests=[];let delegate=window.fetch;
      Object.defineProperty(window,'fetch',{configurable:true,get:()=>{const target=delegate;return function(input,options){window.__settingsRequests.push({url:String(input?.url||input),method:options?.method||input?.method||'GET'});return target.apply(this,arguments)}},set:value=>{delegate=value}});
    }''')
    calendar=screen.frame_locator('#display-calendar')
    screen.locator('#display-next').click()
    expect(screen.locator('#display-title')).to_have_text('November 2026')
    expect(calendar.locator('[data-date="2026-11-01"]')).to_have_count(1)
    calendar.locator('body').evaluate('(node)=>node.dataset.overlayTest="retained"')
    original_theme=screen.locator('html').get_attribute('data-theme') or 'light'
    dialog=screen.locator('#display-settings-dialog')
    settings=screen.frame_locator('#display-settings-frame')
    screen.locator('#display-settings').click()
    expect(dialog).to_be_visible()
    expect(settings.locator('#settings')).to_be_visible()
    expect(settings.locator('#provider')).to_be_visible()
    expect(settings.locator('#composer')).to_be_hidden()
    expect(settings.locator('.topnav')).to_be_hidden()
    settings.locator('#closeSettings').focus()
    page.keyboard.press('Shift+Tab')
    assert settings.locator('#settings').evaluate("n=>{const controls=[...n.querySelectorAll('button,a[href],input,select,textarea,[tabindex]')].filter(x=>!x.disabled&&x.tabIndex>=0&&x.getClientRects().length);return document.activeElement===controls.at(-1)}")
    page.keyboard.press('Tab')
    expect(settings.locator('#closeSettings')).to_be_focused()
    if screen.locator('body').evaluate('()=>window.tetherWorkspace')=='home':
        expect(settings.locator('#householdSettings')).to_be_visible()
    else:
        expect(settings.locator('#storageForm')).to_be_visible()
    settings.locator('#settingsTheme').select_option('dark' if original_theme!='dark' else 'light')
    expect(screen.locator('html')).to_have_attribute('data-theme', 'dark' if original_theme!='dark' else 'light')
    expect(calendar.locator('html')).to_have_attribute('data-theme', 'dark' if original_theme!='dark' else 'light')
    settings.locator('#settingsTheme').select_option(original_theme)
    expect(screen.locator('html')).to_have_attribute('data-theme', original_theme)
    requests=settings.locator('body').evaluate('()=>window.__settingsRequests||[]')
    assert any('/api/settings' in r['url'] for r in requests), requests
    assert not [r for r in requests if '/api/chat' in r['url'] or '/api/attention' in r['url']], requests
    settings.locator('#closeSettings').click()
    expect(dialog).to_be_hidden()
    expect(screen.locator('#display-settings')).to_be_focused()
    expect(screen.locator('#display-title')).to_have_text('November 2026')
    expect(calendar.locator('body')).to_have_attribute('data-overlay-test','retained')
    # Repeated opening and Escape dismiss the same overlay without navigation.
    screen.locator('#display-settings').click()
    expect(settings.locator('#settings')).to_be_visible()
    settings.locator('#closeSettings').focus()
    page.keyboard.press('Escape')
    expect(dialog).to_be_hidden()
    expect(screen.locator('#display-title')).to_have_text('November 2026')
    # Browser Back consumes only the overlay history entry.
    screen.locator('#display-settings').click()
    expect(settings.locator('#settings')).to_be_visible()
    # Same-document iframe history has no top-level load event to await.
    screen.locator('body').evaluate('()=>history.back()')
    expect(dialog).to_be_hidden()
    expect(screen.locator('#display-title')).to_have_text('November 2026')
    expect(calendar.locator('body')).to_have_attribute('data-overlay-test','retained')
    screen.locator('body').evaluate('()=>history.forward()')
    expect(dialog).to_be_visible()
    expect(settings.locator('#settings')).to_be_visible()
    settings.locator('#closeSettings').click()
    expect(dialog).to_be_hidden()
    expect(calendar.locator('body')).to_have_attribute('data-overlay-test','retained')
    screen.locator('#display-today').click()
    expect(screen.locator('#display-title')).to_have_text('October 2026')

    from quick_chat_ui_checks import check_quick_chat
    check_quick_chat(page, screen)


def check_calendar_week_preference(page, screen):
    """Reminder defaults never rotate Display or chat day/week/month calendars."""
    from playwright.sync_api import expect
    calendar=screen.frame_locator('#display-calendar')
    frame=screen.locator('#display-calendar')
    original_url=calendar.locator('body').evaluate('()=>location.href')
    original_viewport=page.viewport_size
    preferences=screen.locator('body').evaluate("async()=>await (await fetch(new URL('api/preferences',location.href))).json()")
    workspace=screen.locator('body').evaluate("()=>window.tetherWorkspace||'work'")
    artifacts=Path('artifacts');artifacts.mkdir(exist_ok=True)
    weekdays=['Sun','Mon','Tue','Wed','Thu','Fri','Sat']

    def save(value):
        result=screen.locator('body').evaluate("""async(_,value)=>{
          const r=await fetch(new URL('api/preferences',location.href),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
          if(!r.ok)throw Error('Preferences failed: '+r.status);
          return await (await fetch(new URL('api/preferences',location.href))).json();
        }""",value)
        assert result==value,result

    def open_calendar(query):
        frame.evaluate("(n,query)=>{const url=new URL(n.src);url.search=new URLSearchParams(query);n.src=url.href}",query)
        from urllib.parse import urlparse, parse_qs
        frame.element_handle().content_frame().wait_for_url(lambda url: parse_qs(urlparse(url).query).get('check')==[query['check']],wait_until='domcontentloaded')

    try:
        for preference in (0,1,3):
            save({**preferences,'week_start':preference})
            open_calendar({'start':'2026-10-01','end':'2026-10-31','embed':'1','layout':'display','workspace':workspace,'check':str(preference)})
            expect(calendar.locator('#weekdays span')).to_have_text(weekdays)
            expect(calendar.locator('#grid > .day').first).to_have_attribute('data-date','2026-09-27')
            expect(calendar.locator('#grid > .day').last).to_have_attribute('data-date','2026-10-31')
            expect(calendar.locator('#grid > .day')).to_have_count(35)
            if preference==3:
                for width,height in ((1280,900),(320,640)):
                    page.set_viewport_size({'width':width,'height':height})
                    assert calendar.locator('body').evaluate('()=>document.documentElement.scrollWidth<=innerWidth')
                    page.screenshot(path=str(artifacts/f'display-calendar-sunday-{workspace}-{width}.png'))
                page.set_viewport_size(original_viewport)
        # A bare snapshot uses the current local Sunday, not Wednesday's reminder default.
        open_calendar({'embed':'1','workspace':workspace,'check':'week'})
        expect(calendar.locator('#grid')).to_have_class('grid week')
        expect(calendar.locator('#weekdays span')).to_have_text(weekdays)
        expect(calendar.locator('#grid > .day')).to_have_count(7)
        expect(calendar.locator('#grid > .day').first).to_have_attribute('data-date','2026-10-25')
        expect(calendar.locator('#grid > .day').last).to_have_attribute('data-date','2026-10-31')
        expect(calendar.locator('.task-marker')).to_have_count(0)
        calendar.locator('.sheet').screenshot(path=str(artifacts/f'display-calendar-chat-week-{workspace}.png'))
        # Explicit single-day snapshots retain a single expanded day, without weekday headers.
        open_calendar({'start':'2026-10-28','end':'2026-10-28','embed':'1','workspace':workspace,'check':'day'})
        expect(calendar.locator('#grid')).to_have_class('grid single')
        expect(calendar.locator('#grid > .day')).to_have_count(1)
        expect(calendar.locator('#grid > .day')).to_have_attribute('data-date','2026-10-28')
        expect(calendar.locator('#weekdays')).to_be_hidden()
        expect(calendar.locator('.task-marker')).to_have_count(0)
        current=screen.locator('body').evaluate("async()=>await (await fetch(new URL('api/preferences',location.href))).json()")
        assert current=={**preferences,'week_start':3},current
    finally:
        save(preferences)
        page.set_viewport_size(original_viewport)
        frame.evaluate('(n,url)=>n.src=url',original_url)
    expect(calendar.locator('#weekdays span')).to_have_text(weekdays)
    expect(calendar.locator('#date-panel')).to_have_attribute('data-date','2026-10-28')
