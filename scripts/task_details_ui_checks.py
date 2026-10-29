"""Shared real-data sidebar task details checks, without provider or place lookups."""
from pathlib import Path


def check_task_details(page, screen):
    from playwright.sync_api import expect
    calendar = screen.frame_locator('#display-calendar')
    fixture = screen.locator('body').evaluate('''async()=>{
      const request=async(path,method='GET',body)=>{
        const response=await fetch(new URL('api/'+path,location.href).href,{method,
          headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
        if(!response.ok)throw Error('Details fixture failed: '+response.status);
        return response.json();
      };
      const task=await request('threads','POST',{title:'Appointment details fixture',categories:['Personal'],
        summary:'Bring the appointment documents. <img src=x onerror="window.detailInjection=true"> '+('Useful saved context. '.repeat(90))});
      await request('threads/'+task.id,'PATCH',{due_at:'2026-10-30T18:30:00Z',revisit_at:'2026-10-30T16:00:00Z'});
      await request('threads/'+task.id+'/entries','POST',{kind:'thought',body:'Ask about the follow-up appointment. <script>window.detailInjection=true</script>'});
      return {id:task.id};
    }''')
    # Location persistence is covered by engine tests. Inject one valid saved-place
    # snapshot field here so UI coverage never performs an external place search.
    calendar.locator('body').evaluate('''(node,id)=>{const w=node.ownerDocument.defaultView;
      w.detailsOriginalFetch=w.fetch;w.fetch=async(...args)=>{
        const response=await w.detailsOriginalFetch(...args);
        const path=new URL(typeof args[0]==='string'?args[0]:args[0].url,w.location.href).pathname;
        if(!path.endsWith('/api/snapshot')||!response.ok)return response;
        const data=await response.clone().json();
        for(const day of data.days||[])for(const task of day.tasks||[])if(task.id===id)task.location='123 Example Street, Sampletown';
        return new Response(JSON.stringify(data),{status:response.status,headers:response.headers});
      };
    }''', fixture['id'])
    screen.locator('#display-today').click()
    date = calendar.locator('[data-date="2026-10-30"] .day-date')
    expect(date).to_be_visible()
    date.click()
    card = calendar.locator('#date-panel-items button.task').filter(has_text='Appointment details fixture')
    expect(card).to_be_visible()
    expect(card).to_contain_text('Due')
    expect(card).to_contain_text('2:30 PM')
    expect(card).to_contain_text('Attention')
    expect(card).to_contain_text('12:00 PM')
    expect(card).to_contain_text('Bring the appointment documents.')
    expect(card).to_contain_text('123 Example Street, Sampletown')
    assert card.locator('img, script').count() == 0
    card.focus()
    page.keyboard.press('Enter')
    dialog = calendar.locator('#task-detail')
    expect(dialog).to_be_visible()
    expect(screen.locator('.display-bar')).to_have_js_property('inert', True)
    expect(screen.locator('#display-quick-chat')).to_have_js_property('inert', True)
    expect(calendar.locator('#task-detail-title')).to_have_text('Appointment details fixture')
    expect(calendar.locator('#task-detail-body')).to_contain_text('Ask about the follow-up appointment.')
    assert calendar.locator('#task-detail-body').inner_text().count('Useful saved context.') == 90
    assert dialog.locator('img, script').count() == 0
    # Reading task details must not replace the selected date at the 15s timeout,
    # nor lose the dialog during an automatic snapshot refresh.
    page.clock.fast_forward(61000)
    expect(dialog).to_be_visible()
    expect(calendar.locator('#date-panel')).to_have_attribute('data-date', '2026-10-30')
    expect(screen.locator('#display-settings-dialog')).to_be_hidden()
    expect(screen.locator('#display-chat-dialog')).to_be_hidden()
    artifacts = Path('artifacts'); artifacts.mkdir(exist_ok=True)
    workspace = screen.locator('body').evaluate("()=>window.tetherWorkspace||'work'")
    for width, height in [(1024, 768), (320, 640)]:
        page.set_viewport_size({'width': width, 'height': height})
        assert dialog.evaluate('n=>{const b=n.getBoundingClientRect();return b.left>=0&&b.right<=innerWidth+1&&b.top>=0&&b.bottom<=innerHeight+1&&n.scrollWidth<=n.clientWidth+1}'), (width, height)
        expect(calendar.locator('#task-detail-close')).to_be_in_viewport()
        page.screenshot(path=str(artifacts / f'display-{workspace}-task-details-{width}.png'))
    page.set_viewport_size({'width': 1280, 'height': 900})
    calendar.locator('#task-detail-close').focus()
    calendar.locator('body').evaluate('''()=>{window.detailEvents=[];for(const type of ['keydown','cancel','popstate'])addEventListener(type,e=>detailEvents.push({type:e.type,key:e.key,state:history.state}),true)}''')
    page.keyboard.press('Escape')
    try:
        expect(dialog).to_be_hidden()
    except AssertionError:
        print('Task detail dismissal diagnostics:', calendar.locator('body').evaluate('()=>({events:window.detailEvents,state:history.state,focus:document.activeElement?.id,open:document.querySelector("#task-detail").open})'))
        raise
    expect(card).to_be_focused()
    card.click()
    expect(dialog).to_be_visible()
    calendar.locator('body').evaluate('()=>history.back()')
    expect(dialog).to_be_hidden()
    expect(card).to_be_focused()
    calendar.locator('body').evaluate('()=>history.forward()')
    expect(dialog).to_be_visible()
    calendar.locator('#task-detail-close').click()
    expect(dialog).to_be_hidden()
    expect(card).to_be_focused()
    expect(screen.locator('.display-bar')).to_have_js_property('inert', False)
    expect(screen.locator('#display-quick-chat')).to_have_js_property('inert', False)
    page.clock.fast_forward(16000)
    expect(calendar.locator('#date-panel-title')).to_have_text('Today')
    # Closing the information popup leaves normal Display overlays usable.
    screen.locator('#display-settings').click()
    expect(screen.locator('#display-settings-dialog')).to_be_visible()
    screen.frame_locator('#display-settings-frame').locator('#closeSettings').click()
    expect(screen.locator('#display-settings-dialog')).to_be_hidden()
    assert calendar.locator('body').evaluate('()=>!window.detailInjection')
    calendar.locator('body').evaluate('()=>{window.fetch=window.detailsOriginalFetch;delete window.detailsOriginalFetch}')
    # A document reload must not leave a stale detail history marker or lock
    # the parent's controls. The next detail can still be opened and dismissed.
    date.click()
    card.click()
    expect(dialog).to_be_visible()
    calendar.locator('body').evaluate('()=>location.reload()')
    expect(dialog).to_be_hidden()
    expect(screen.locator('.display-bar')).to_have_js_property('inert', False)
    expect(screen.locator('#display-quick-chat')).to_have_js_property('inert', False)
    date.click()
    card.click()
    expect(dialog).to_be_visible()
    calendar.locator('#task-detail-close').click()
    expect(dialog).to_be_hidden()
    expect(card).to_be_focused()
    screen.locator('#display-today').click()
    expect(calendar.locator('#date-panel-title')).to_have_text('Today')
