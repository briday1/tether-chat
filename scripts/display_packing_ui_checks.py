"""Shared Home/Work month cell packing, geometry, and selection regressions."""
from pathlib import Path


def check_packed_day(cell, total):
    """Visible rows plus the honest overflow count always cover every record."""
    from playwright.sync_api import expect
    expect(cell.locator('.day-date')).to_be_visible()
    expect(cell).to_have_attribute('data-total-count',str(total))
    cell.evaluate('n=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
    result=cell.evaluate('''day=>{
      const box=day.getBoundingClientRect(),items=day.querySelector('.day-items'),area=items.getBoundingClientRect();
      const rows=[...items.querySelectorAll('.display-item')].filter(n=>!n.hidden);
      const more=day.querySelector('.day-more'), visibleMore=more&&!more.hidden?more:null;
      const inside=(n,b)=>{const r=n.getBoundingClientRect();return r.left>=b.left-.5&&r.right<=b.right+.5&&r.top>=b.top-.5&&r.bottom<=b.bottom+.5};
      return {visible:rows.length,more:visibleMore?.textContent||'',allInside:rows.every(n=>inside(n,area)),
        moreInside:!visibleMore||inside(visibleMore,box),
        moreReadable:!visibleMore||(visibleMore.clientWidth>=visibleMore.scrollWidth&&parseFloat(getComputedStyle(visibleMore).fontSize)>=11&&visibleMore.getBoundingClientRect().height>=14),
        numberInside:inside(day.querySelector('.day-date'),box),
        noOverflow:day.scrollWidth<=day.clientWidth+1,
        titleFonts:rows.filter(n=>n.querySelector('.display-item-title')).map(n=>parseFloat(getComputedStyle(n.querySelector('.display-item-title')).fontSize)),
        titles:rows.filter(n=>n.querySelector('.display-item-title')&&getComputedStyle(n.querySelector('.display-item-title')).display!=='none').map(n=>n.querySelector('.display-item-title').textContent)};
    }''')
    hidden=int(result['more'].split()[0].lstrip('+')) if result['more'] else 0
    assert result['visible']+hidden==total,(total,result)
    assert result['allInside'] and result['moreInside'] and result['numberInside'],result
    assert result['moreReadable'] and result['noOverflow'],result
    return result


def check_display_packing(page,screen):
    from playwright.sync_api import expect
    resize_errors=[]
    def capture_resize_error(message):
        if 'ResizeObserver loop' in message.text:resize_errors.append(message.text)
    def capture_resize_pageerror(error):
        if 'ResizeObserver loop' in str(error):resize_errors.append(str(error))
    page.on('console',capture_resize_error)
    page.on('pageerror',capture_resize_pageerror)
    # A separate future date avoids disturbing existing Today/quick-chat fixtures.
    screen.locator('body').evaluate('''async()=>{
      const request=async(path,method,body)=>{const r=await fetch(new URL('api/'+path,location.href).href,
        {method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        if(!r.ok)throw Error('Packing fixture '+r.status);return r.json()};
      for(let i=0;i<18;i++){
        const task=await request('threads','POST',{title:'Packing appointment '+String(i).padStart(2,'0')+' with useful longer context',categories:['Home planning']});
        await request('threads/'+task.id,'PATCH',{due_at:'2026-11-10T14:30:00Z'});
      }
      const sparse=await request('threads','POST',{title:'Packing sparse appointment',summary:'Bring the blue folder',categories:['Home planning']});
      await request('threads/'+sparse.id,'PATCH',{due_at:'2026-11-11T14:30:00Z'});
    }''')
    screen.locator('#display-today').click()
    expect(screen.locator('#display-title')).to_have_text('October 2026')
    screen.locator('#display-next').click()
    expect(screen.locator('#display-title')).to_have_text('November 2026')
    calendar=screen.frame_locator('#display-calendar')
    busy=calendar.locator('.day[data-date="2026-11-10"]')
    expect(busy.locator('.day-date')).to_be_visible()
    busy.locator('.day-date').click()
    expect(calendar.locator('#date-panel')).to_have_attribute('data-date','2026-11-10')
    expect(calendar.locator('#date-panel-items .task')).to_have_count(18)
    artifacts=Path('artifacts');artifacts.mkdir(exist_ok=True)
    workspace=screen.locator('body').evaluate("()=>window.tetherWorkspace||'work'")
    capacities=[]
    for width,height in [(1920,1200),(1280,900),(1024,600),(768,1024),(320,640),(568,320),(1280,900)]:
        # Keep the reading session active while hosted screenshots are captured.
        calendar.locator('#date-panel').dispatch_event('pointerdown')
        page.set_viewport_size({'width':width,'height':height})
        packed=check_packed_day(busy,18);capacities.append(packed['visible'])
        expect(calendar.locator('#date-panel')).to_have_attribute('data-date','2026-11-10')
        expect(calendar.locator('.day.selected')).to_have_attribute('data-date','2026-11-10')
        assert screen.locator('body').evaluate('()=>document.documentElement.scrollWidth<=innerWidth&&document.body.scrollHeight<=innerHeight+1'),(width,height)
        assert calendar.locator('body').evaluate('()=>document.documentElement.scrollWidth<=innerWidth'),(width,height)
        assert calendar.locator('#grid').evaluate('(n)=>{const r=n.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight+1}'),(width,height)
        heights=calendar.locator('.day').evaluate_all('(nodes)=>nodes.map(n=>n.getBoundingClientRect().height)')
        assert max(heights)-min(heights)<=1,(width,height,heights)
        if width>=1280:
            assert packed['titles'] and all('Packing appointment' in title for title in packed['titles']),packed
            assert packed['titleFonts'] and min(packed['titleFonts'])>=11,packed
            sparse=calendar.locator('.day[data-date="2026-11-11"]')
            check_packed_day(sparse,1)
            expect(sparse.locator('.display-item-context')).to_contain_text('9:30 AM')
            expect(sparse.locator('.display-item-context')).to_contain_text('Bring the blue folder')
        if width==1920:
            assert packed['visible']>3,packed
        page.screenshot(path=str(artifacts/f'display-{workspace}-packing-{width}x{height}.png'))
    assert capacities[1]==capacities[-1],capacities
    # Repacking must retain keyboard focus within the selected day, even when
    # the focused last row disappears and only a header overflow can fit.
    busy.locator('.display-item').last.focus()
    page.set_viewport_size({'width':568,'height':320})
    check_packed_day(busy,18)
    assert busy.evaluate('(n)=>n.contains(document.activeElement)'), 'Focused task was lost during compact packing'
    expect(calendar.locator('#date-panel')).to_have_attribute('data-date','2026-11-10')
    page.set_viewport_size({'width':1280,'height':900})
    restored=check_packed_day(busy,18)
    assert restored['visible']==capacities[1],restored
    assert busy.evaluate('(n)=>n.contains(document.activeElement)'), 'Focused date was lost after expansion'
    busy.locator('.day-more').click()
    expect(calendar.locator('#date-panel-items .task')).to_have_count(18)
    expect(calendar.locator('#task-detail')).to_be_hidden()
    screen.locator('#display-today').click()
    expect(screen.locator('#display-title')).to_have_text('October 2026')
    expect(calendar.locator('.today')).to_have_attribute('data-date','2026-10-28')
    expect(calendar.locator('.today .day-date')).to_have_attribute('aria-current','date')
    expect(calendar.locator('#date-panel-title')).to_have_text('Today')
    page.remove_listener('console',capture_resize_error)
    page.remove_listener('pageerror',capture_resize_pageerror)
    assert not resize_errors,resize_errors
