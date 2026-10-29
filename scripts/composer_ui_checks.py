"""Shared icon composer contract in Conversation and Display (synthetic queue only)."""
from pathlib import Path


def check_composer_controls(page, chat, variant):
    from playwright.sync_api import expect
    field = chat.locator('#message')
    send = chat.locator('#send')
    stop = chat.locator('#stop-chat')
    interrupt = chat.locator('#interrupt-chat')
    expect(field).to_be_visible()
    saved_viewport = page.viewport_size
    field.evaluate('''n=>{const w=n.ownerDocument.defaultView;
      w.composerCheck={fetch:w.fetch,before:w.tetherBeforeChat,draft:n.value,
        theme:n.ownerDocument.documentElement.dataset.theme,posts:[],cancels:[],
        failStop:false,rejectSend:false,state:{messages:[],jobs:[]}};
      const c=w.composerCheck;w.tetherBeforeChat=async()=>true;
      w.fetch=async(input,options={})=>{const path=new URL(typeof input==='string'?input:input.url,w.location.href).pathname;
        if(path.endsWith('/api/chat/state'))return Response.json(c.state);
        if(path.endsWith('/api/chat/jobs')&&options.method==='POST'){
          const p=JSON.parse(options.body);c.posts.push(p);
          if(c.rejectSend)return Response.json({detail:'Synthetic rejected message'},{status:400});
          c.state={messages:[{id:'composer-user',role:'user',body:p.text}],jobs:[{id:p.request_id,user_message_id:'composer-user',status:'running',updated_at:String(c.posts.length),progress:[]}]};
          return Response.json({id:p.request_id});
        }
        if(path.includes('/api/chat/jobs/')&&path.endsWith('/cancel')&&options.method==='POST'){
          c.cancels.push(path);if(c.failStop)return Response.json({detail:'offline'},{status:503});
          const job=c.state.jobs[0];job.status='interrupted';job.user_stopped=true;job.updated_at='stop-'+c.cancels.length;return Response.json(job);
        }
        return c.fetch(input,options);
      };w.dispatchEvent(new Event('online'));
    }''')
    field.fill('')
    expect(send).to_be_visible()
    expect(send).to_have_attribute('aria-label', 'Send')
    expect(stop).to_be_hidden()
    expect(interrupt).to_be_hidden()
    assert send.inner_text() == ''
    assert send.get_attribute('title')
    assert send.locator('svg[aria-hidden="true"]').count() == 1

    def state(code):
        return field.evaluate('(n)=>{const w=n.ownerDocument.defaultView,c=w.composerCheck;' + code + '}')

    def geometry():
        return field.evaluate('''n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}}''')

    def assert_same(first, second):
        assert first and second
        for key in ['x', 'y', 'width', 'height']:
            assert abs(first[key] - second[key]) <= 1, (key, first, second)

    # Idle, busy and typed busy all keep the primary control and draft geometry.
    for theme in ['light', 'dark']:
        for width in [1280, 320]:
            page.set_viewport_size({'width':width,'height':900 if width > 320 else 640})
            state("n.ownerDocument.documentElement.dataset.theme='" + theme + "'")
            field.fill('Hi')
            idle = send.bounding_box()
            input_box = geometry()
            assert idle['width'] >= 44 and idle['height'] >= 44, idle
            assert send.evaluate('n=>getComputedStyle(n).borderRadius') in ['50%', '999px', '9999px', '22px']
            page.keyboard.press('Tab')
            send.focus()
            expect(send).to_be_focused()
            assert send.evaluate("n=>getComputedStyle(n).outlineStyle!=='none'"), 'Send keyboard focus must be visible'
            send.click()
            expect(field).to_have_value('')
            expect(stop).to_be_visible()
            expect(send).to_be_hidden()
            expect(stop).to_have_attribute('aria-label', 'Stop')
            assert stop.inner_text() == '' and stop.get_attribute('title')
            assert stop.locator('svg[aria-hidden="true"] rect').count() == 1
            assert_same(idle, stop.bounding_box())
            assert_same(input_box, geometry())
            field.fill('More')
            expect(interrupt).to_be_visible()
            expect(interrupt).to_have_attribute('aria-label', 'Interrupt with added context')
            assert interrupt.get_attribute('title')
            assert_same(idle, stop.bounding_box())
            assert_same(input_box, geometry())
            page.keyboard.press('Tab')
            stop.focus()
            expect(stop).to_be_focused()
            assert stop.evaluate("n=>getComputedStyle(n).outlineStyle!=='none'"), 'Stop keyboard focus must be visible'
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path=f'artifacts/display-composer-{variant}-{theme}-{width}-busy.png', full_page=True)
            before = state('return c.posts.length')
            interrupt.click()
            expect(field).to_have_value('')
            assert state('return c.posts.length') == before + 1
            assert state('return c.posts.at(-1).interrupt_job_id===c.posts.at(-2).request_id')
            field.fill('Draft')
            stop.click()
            expect(stop).to_be_hidden()
            expect(send).to_be_visible()
            expect(field).to_have_value('Draft')
            expect(interrupt).to_be_hidden()
            assert_same(idle, send.bounding_box())
            page.screenshot(path=f'artifacts/display-composer-{variant}-{theme}-{width}-idle.png', full_page=True)
            field.fill('')

    # Enter still interrupts. Repeated synchronous submissions cannot duplicate it.
    field.fill('Keyboard request')
    field.press('Enter')
    expect(stop).to_be_visible()
    field.fill('Keyboard added context')
    before = state('return c.posts.length')
    field.press('Enter')
    expect(field).to_have_value('')
    assert state('return c.posts.length') == before + 1
    assert state('return c.posts.at(-1).interrupt_job_id===c.posts.at(-2).request_id')
    field.fill('Submit only once')
    before = state('return c.posts.length')
    field.evaluate("n=>{const form=n.closest('form');form.requestSubmit();form.requestSubmit()}")
    expect(field).to_have_value('')
    assert state('return c.posts.length') == before + 1
    assert state('return c.posts.at(-1).interrupt_job_id===c.posts.at(-2).request_id')

    # Failed Stop leaves the draft intact, exposes an error and never sends context.
    state('c.failStop=true')
    field.fill('Preserve offline context')
    before = state('return c.posts.length')
    interrupt.click()
    expect(chat.locator('#composer [role="alert"]')).to_contain_text('Could not confirm Stop')
    expect(field).to_have_value('Preserve offline context')
    expect(stop).to_be_visible()
    expect(stop).to_be_enabled()
    assert state('return c.posts.length') == before
    state('c.failStop=false')
    stop.click()
    expect(send).to_be_visible()
    expect(stop).to_be_hidden()
    expect(field).to_have_value('Preserve offline context')

    # A rejected send restores text, then the same field can submit successfully.
    state('c.rejectSend=true')
    field.fill('Rejected draft')
    send.click()
    expect(chat.locator('.chat-pending').filter(has_text='Synthetic rejected message')).to_be_visible()
    expect(field).to_have_value('Rejected draft')
    expect(send).to_be_visible()
    state('c.rejectSend=false')
    send.click()
    expect(stop).to_be_visible()
    state("c.state.jobs[0].status='done';c.state.jobs[0].updated_at='done';w.dispatchEvent(new Event('online'))")
    expect(send).to_be_visible()
    expect(stop).to_be_hidden()
    expect(interrupt).to_be_hidden()
    field.fill('')
    state('w.fetch=c.fetch;w.tetherBeforeChat=c.before;n.ownerDocument.documentElement.dataset.theme=c.theme||"";n.value=c.draft;n.dispatchEvent(new Event("input",{bubbles:true}));w.dispatchEvent(new Event("online"))')
    if saved_viewport:
        page.set_viewport_size(saved_viewport)
