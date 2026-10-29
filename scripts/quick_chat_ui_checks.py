"""Exercise the real embedded composer in both products without provider calls."""


def check_quick_chat(page, screen):
    from playwright.sync_api import expect
    button = screen.locator('#display-quick-chat')
    dialog = screen.locator('#display-chat-dialog')
    chat = screen.frame_locator('#display-chat-frame')
    title = screen.locator('#display-title').inner_text()
    button.click()
    expect(dialog).to_be_visible()
    field = chat.locator('#message')
    expect(field).to_be_visible()
    expect(chat.locator('#voiceInput')).to_have_attribute('aria-pressed', 'false')
    expect(chat.locator('.topnav')).to_be_hidden()
    expect(chat.locator('#right')).to_be_hidden()
    expect(chat.get_by_text('Enter to send · Shift+Enter for new line', exact=True)).to_have_count(0)
    # Input grows rather than hiding the draft, then scrolls within a bounded height.
    field.fill('Line one')
    field.press('Shift+Enter')
    field.press('Shift+Enter')
    expect(field).to_have_value('Line one\n\n')
    assert field.evaluate('(n)=>n.getBoundingClientRect().height>44')
    field.fill('A long draft line\n' * 40)
    assert field.evaluate('''n=>{const w=n.ownerDocument.defaultView;return n.scrollHeight>n.clientHeight&&n.getBoundingClientRect().height<=Math.min(200,w.innerHeight*.3)+1&&w.getComputedStyle(n).overflowY==='auto'}''')
    assert chat.locator('#chat').evaluate('(n)=>n.clientHeight>100')
    field.fill('Keep this unsent quick chat draft')
    assert field.evaluate('(n)=>n.getBoundingClientRect().height<=45')
    field.evaluate('(n)=>n.ownerDocument.body.dataset.retainedChat="yes"')
    screen.get_by_role('button', name='Close quick chat', exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(button).to_be_focused()
    expect(screen.locator('#display-title')).to_have_text(title)
    button.click()
    expect(field).to_have_value('Keep this unsent quick chat draft')
    expect(chat.locator('body')).to_have_attribute('data-retained-chat', 'yes')
    # Mock browser voice; never prompt for a microphone or download a model.
    field.evaluate('''n=>{const w=n.ownerDocument.defaultView;
      w.voiceStarts=0;w.voiceStops=0;
      w.SpeechRecognition=class {start(){w.voiceStarts++;this.onstart();this.onresult({results:[[{transcript:'spoken draft'}]]})}abort(){w.voiceStops++}stop(){this.abort();this.onend()}};
      const mode=n.ownerDocument.querySelector('#voiceMode');mode.value='browser';mode.dispatchEvent(new Event('change'));
    }''')
    chat.locator('#voiceInput').click()
    expect(field).to_have_value('Keep this unsent quick chat draft spoken draft')
    screen.get_by_role('button', name='Close quick chat', exact=True).click()
    expect(chat.locator('#voiceInput')).to_have_attribute('aria-pressed', 'false')
    assert field.evaluate('(n)=>n.ownerDocument.defaultView.voiceStarts===1&&n.ownerDocument.defaultView.voiceStops===1')
    button.click()
    expect(field).to_have_value('Keep this unsent quick chat draft spoken draft')
    # Exercise the actual durable submit path, mocking ONLY provider queue results.
    field.evaluate('''n=>{const w=n.ownerDocument.defaultView,original=w.fetch;
      w.quickOriginalFetch=original;w.quickPosts=[];w.quickState={messages:[],jobs:[]};
      w.quickBefore=w.tetherBeforeChat;w.tetherBeforeChat=async()=>true;
      w.fetch=async(input,options={})=>{const path=new URL(typeof input==='string'?input:input.url,w.location.href).pathname;
        if(path.endsWith('/api/chat/jobs')&&options.method==='POST'){
          const payload=JSON.parse(options.body);w.quickPosts.push(payload);
          w.quickState={messages:[{id:'quick-user',role:'user',body:payload.text}],jobs:[{id:payload.request_id,user_message_id:'quick-user',status:'running',updated_at:'1',progress:[]}]};
          return new Response(JSON.stringify({id:payload.request_id}),{status:200});
        }
        if(path.endsWith('/api/chat/state'))return new Response(JSON.stringify(w.quickState),{status:200});
        return original(input,options);
      };
    }''')
    field.fill('Mock quick chat request')
    field.press('Enter')
    expect(chat.locator('.bubble.user').filter(has_text='Mock quick chat request')).to_have_text('Mock quick chat request')
    expect(field).to_have_value('')
    assert field.evaluate('(n)=>n.getBoundingClientRect().height<=45')
    expect(chat.locator('.chat-pending')).to_contain_text('Working on your request')
    screen.get_by_role('button', name='Close quick chat', exact=True).click()
    button.click()
    assert field.evaluate('(n)=>n.ownerDocument.defaultView.quickPosts.length===1')
    expect(chat.locator('.bubble.user').filter(has_text='Mock quick chat request')).to_have_count(1)
    # Completed queue state notifies Display without replacing its calendar iframe.
    screen.locator('#display-calendar').evaluate('(n)=>n.dataset.retainedCalendar="yes"')
    field.evaluate('''n=>{const w=n.ownerDocument.defaultView;w.quickState.jobs[0].status='done';w.quickState.jobs[0].updated_at='2';w.dispatchEvent(new Event('online'))}''')
    expect(chat.locator('.chat-pending')).to_have_count(0)
    # Simulate a committed chat tool write through the product's real task store.
    field.evaluate('''async n=>{const w=n.ownerDocument.defaultView,base=w.TETHER_CONFIG?.base||'/';
      const response=await w.quickOriginalFetch(base+'api/threads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'Quick chat calendar regression'})});
      const task=await response.json();w.quickTask=task.id;const d=new Date(),date=[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
      await w.quickOriginalFetch(base+'api/threads/'+task.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({due_at:date})});
      w.dispatchEvent(new Event('tether:chat-state-changed'));
    }''')
    expect(screen.frame_locator('#display-calendar').locator('#date-panel-items')).to_contain_text('Quick chat calendar regression')
    field.evaluate('''async n=>{const w=n.ownerDocument.defaultView;await w.quickOriginalFetch((w.TETHER_CONFIG?.base||'/')+'api/threads/'+w.quickTask,{method:'DELETE'});w.dispatchEvent(new Event('tether:chat-state-changed'))}''')
    expect(screen.frame_locator('#display-calendar').locator('#date-panel-items')).not_to_contain_text('Quick chat calendar regression')
    expect(screen.locator('#display-calendar')).to_have_attribute('data-retained-calendar', 'yes')
    field.focus()
    page.keyboard.press('Escape')
    expect(dialog).not_to_be_visible()
    button.click()
    screen.locator('body').evaluate('n=>n.ownerDocument.defaultView.history.back()')
    expect(dialog).not_to_be_visible()
    expect(button).to_be_focused()
    screen.locator('body').evaluate('n=>n.ownerDocument.defaultView.history.forward()')
    expect(dialog).to_be_visible()
    field.evaluate('''n=>{const w=n.ownerDocument.defaultView;w.fetch=w.quickOriginalFetch;w.tetherBeforeChat=w.quickBefore;const mode=n.ownerDocument.querySelector('#voiceMode');mode.value='local';mode.dispatchEvent(new Event('change'));w.dispatchEvent(new Event('online'))}''')
    field.fill('')
    page.set_viewport_size({'width':320,'height':640})
    expect(field).to_be_visible()
    box=dialog.bounding_box()
    assert box and box['width']<=320 and box['height']<=640,box
    field.fill('Mobile draft line\n' * 40)
    assert field.evaluate('''n=>{const w=n.ownerDocument.defaultView;return n.scrollHeight>n.clientHeight&&n.getBoundingClientRect().height<=Math.min(200,w.innerHeight*.3)+1}''')
    assert chat.locator('#chat').evaluate('(n)=>n.clientHeight>80')
    field.fill('')
    page.set_viewport_size({'width':1280,'height':900})
    screen.get_by_role('button', name='Close quick chat', exact=True).click()
    expect(screen.locator('#display-title')).to_have_text(title)
