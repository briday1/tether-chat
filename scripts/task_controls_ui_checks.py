"""Real task-list completion, snoozing, archive and recovery in both editions."""
from pathlib import Path


def check_task_controls(page, screen):
    from playwright.sync_api import expect

    def api(path, method='GET', body=None):
        return screen.locator('body').evaluate('''async(_,a)=>{
          const response=await fetch(new URL('api/'+a.path,location.href).href,{method:a.method,
            headers:{'Content-Type':'application/json'},body:a.body===null?undefined:JSON.stringify(a.body)});
          const data=await response.json();if(!response.ok)throw Error(JSON.stringify(data));return data;
        }''', {'path': path, 'method': method, 'body': body})

    page.keyboard.press('Escape')
    screen.get_by_role('link', name='Tasks', exact=True).click()
    expect(screen.locator('#board')).to_be_visible()
    task = api('threads', 'POST', {'title': 'Task controls regression', 'categories': ['Task controls']})
    first = api('threads/'+task['id']+'/entries', 'POST', {'kind': 'action', 'body': 'Check this action in the list'})
    finished = api('threads/'+task['id']+'/entries', 'POST', {'kind': 'action', 'body': 'Already finished before the task'})
    api('actions/'+finished['id'], 'PATCH', {'done': True})
    api('threads/'+task['id'], 'PATCH', {'due_at': '2020-01-01', 'revisit_at': '2020-01-01T09:00:00Z'})
    api('actions/'+first['id'], 'PATCH', {'due_at': '2020-01-02', 'revisit_at': '2020-01-01T09:00:00Z'})
    api('actions/'+first['id']+'/notes', 'POST', {'body': 'Preserve this action note through completion.'})
    screen.get_by_role('link', name='Tasks', exact=True).click()
    row = screen.locator('.task-row[data-task-id="'+task['id']+'"]')
    expect(row.get_by_role('checkbox', name='Complete task '+task['title'], exact=True)).to_be_visible()
    row.locator('.task-row-open').click()
    action = screen.locator('.action-list-row[data-action-id="'+first['id']+'"]')
    checkbox = action.get_by_role('checkbox', name='Complete action '+first['body'], exact=True)
    checkbox.focus();page.keyboard.press('Space')
    expect(action.get_by_role('checkbox', name='Reopen action '+first['body'], exact=True)).to_be_checked()
    expect(screen.locator('#actionDrawer')).to_be_hidden()
    data = api('threads/'+task['id'])
    assert not data['archived_at'] and data['state'] == 'open'
    assert data['due_at'] == '2020-01-01'
    action.get_by_role('checkbox').uncheck()
    expect(action.get_by_role('checkbox', name='Complete action '+first['body'], exact=True)).not_to_be_checked()

    # A write from chat, MCP or another process has no event in this window.
    # Visible task lists still refresh while retaining keyboard focus.
    action.get_by_role('checkbox').focus()
    api('actions/'+first['id'], 'PATCH', {'done': True})
    expect(action.get_by_role('checkbox', name='Reopen action '+first['body'], exact=True)).to_be_checked(timeout=7000)
    expect(action.get_by_role('checkbox')).to_be_focused()
    api('actions/'+first['id'], 'PATCH', {'done': False})
    expect(action.get_by_role('checkbox', name='Complete action '+first['body'], exact=True)).not_to_be_checked(timeout=7000)

    # A rejected save must leave the visible checkbox and stored task untouched.
    screen.locator('body').evaluate('''(_,id)=>{
      const original=window.fetch;let failed=false;
      window.restoreTaskControlFetch=()=>{window.fetch=original};
      window.fetch=(input,init)=>{
        if(!failed&&init?.method==='POST'&&new URL(input,location.href).pathname.endsWith('/threads/'+id+'/complete')){
          failed=true;return Promise.resolve(new Response(JSON.stringify({detail:'Simulated save failure'}),{status:503,headers:{'Content-Type':'application/json'}}));
        }return original(input,init);
      };
    }''', task['id'])
    task_checkbox = row.get_by_role('checkbox')
    task_checkbox.click()
    expect(screen.locator('#error')).to_contain_text('Simulated save failure')
    expect(task_checkbox).not_to_be_checked();expect(task_checkbox).to_be_enabled()
    assert api('threads/'+task['id'])['state'] == 'open'
    screen.locator('body').evaluate('()=>window.restoreTaskControlFetch()')

    # Tomorrow pauses every attention reason for this task, including overdue
    # deadlines and child actions, while the actual deadlines stay visible.
    # Read it in the legacy shape (future reminder without snoozed_until), which
    # the task engine already understands. The list must use the same schedule.
    screen.locator('body').evaluate('''(_,id)=>{
      const original=window.fetch;window.restoreTaskControlFetch=()=>{window.fetch=original};
      window.fetch=async(input,init={})=>{
        const response=await original(input,init),path=new URL(typeof input==='string'?input:input.url,location.href).pathname;
        if((init.method||'GET')!=='GET'||!response.ok||!(/\\/api\\/board$/.test(path)||path.endsWith('/api/threads/'+id)))return response;
        const data=await response.json(),legacy=task=>{if(task.id===id)delete task.snoozed_until};
        if(Array.isArray(data)){for(const group of data)for(const task of group.threads)legacy(task)}else legacy(data);
        return new Response(JSON.stringify(data),{status:response.status,headers:response.headers});
      };
    }''', task['id'])
    screen.get_by_role('button', name='Bring '+task['title']+' to attention tomorrow', exact=True).click()
    expect(row.locator('.task-row-state')).to_have_text('Later')
    expect(screen.locator('.task-deadline')).to_contain_text('2020')
    expect(screen.locator('.category-row').filter(has_text='Task controls').locator('.category-flag')).to_have_count(0)
    data = api('threads/'+task['id'])
    assert data['due_at'] == '2020-01-01' and data['revisit_at'] and 'snoozed_until' not in data
    assert not any(item['task_id'] == task['id'] for item in api('attention')['items'])
    screen.get_by_role('button', name='Resume attention for '+task['title'], exact=True).click()
    expect(screen.get_by_role('button', name='Resume attention for '+task['title'], exact=True)).to_have_count(0)
    screen.locator('body').evaluate('()=>window.restoreTaskControlFetch()')
    assert not api('threads/'+task['id'])['snoozed_until']

    # The same control on an action leaves the parent and its siblings intact.
    parent_reminder = api('threads/'+task['id'])['revisit_at']
    action.locator('.action-row-open').click()
    screen.get_by_role('button', name='Bring '+first['body']+' to attention tomorrow', exact=True).click()
    expect(screen.locator('#actionDrawer')).to_be_hidden()
    data = api('threads/'+task['id'])
    assert data['revisit_at'] == parent_reminder and not data['snoozed_until']
    entries = {a['id']: a for a in data['entries']}
    assert entries[first['id']]['snoozed_until'] and entries[first['id']]['due_at'] == '2020-01-02'
    assert entries[finished['id']]['done']

    # Finishing a whole task archives it. Undo preserves notes and restores only
    # actions that were unfinished before the whole-task completion.
    row.get_by_role('checkbox').focus();page.keyboard.press('Space')
    expect(row).to_have_count(0)
    expect(screen.locator('#task-status')).to_contain_text('Moved to the archive')
    data = api('threads/'+task['id'])
    assert data['archived_at'] and all(entry['done'] for entry in data['entries'])
    screen.locator('#task-status').get_by_role('button', name='Undo', exact=True).click()
    expect(row.get_by_role('checkbox')).not_to_be_checked()
    data = api('threads/'+task['id'])
    assert not data['archived_at'] and data['state'] == 'open'
    entries = {a['id']: a for a in data['entries']}
    assert not entries[first['id']]['done'] and entries[finished['id']]['done']
    assert entries[first['id']]['notes'][0]['body'] == 'Preserve this action note through completion.'

    # Archive remains accessible even after the last active item is finished.
    screen.locator('#board-search').fill(task['title'])
    row.get_by_role('checkbox').check();expect(row).to_have_count(0)
    screen.get_by_role('button', name='View archive', exact=True).click()
    expect(row.get_by_role('checkbox', name='Reopen task '+task['title'], exact=True)).to_be_checked()
    row.get_by_role('checkbox').uncheck()
    expect(screen.get_by_role('button', name='View archive', exact=True)).to_be_visible()
    expect(row.get_by_role('checkbox')).not_to_be_checked()
    screen.locator('#board-search').fill('')

    # A rapid duplicate change for a recurring checkbox must only consume the
    # captured occurrence. The next date remains an active recurring task.
    recurring = api('threads', 'POST', {'title': 'Recurring task checkbox regression'})
    api('threads/'+recurring['id'], 'PATCH', {'recurrence': 'weekly', 'next_occurrence': '2099-01-01', 'recurrence_end': '2099-01-15'})
    screen.get_by_role('link', name='Tasks', exact=True).click()
    repeated = screen.locator('.task-row[data-task-id="'+recurring['id']+'"]')
    screen.locator('body').evaluate('''(_,id)=>{
      const original=window.fetch;window.taskControlOccurrences=[];
      window.restoreTaskControlFetch=()=>{window.fetch=original};
      window.fetch=async(input,init)=>{
        if(init?.method==='POST'&&new URL(input,location.href).pathname.endsWith('/threads/'+id+'/complete-occurrence')){
          window.taskControlOccurrences.push(JSON.parse(init.body).occurrence_at);
          await new Promise(resolve=>setTimeout(resolve,180));
        }return original(input,init);
      };
    }''', recurring['id'])
    repeated.get_by_role('checkbox').evaluate("node=>{node.checked=true;node.dispatchEvent(new Event('change'));node.dispatchEvent(new Event('change'))}")
    expect(screen.locator('#task-status')).to_contain_text('Completed this occurrence')
    expect(repeated.get_by_role('checkbox')).not_to_be_checked()
    expect(repeated.get_by_role('checkbox')).to_be_enabled()
    assert screen.locator('body').evaluate('()=>window.taskControlOccurrences') == ['2099-01-01']
    screen.locator('body').evaluate('()=>window.restoreTaskControlFetch()')
    data = api('threads/'+recurring['id'])
    assert data['next_occurrence'] == '2099-01-08' and not data['archived_at'] and data['state'] == 'open'

    # Controls remain visible and usable on a narrow screen; no horizontal scroll.
    row.locator('.task-row-open').click()
    original_size = page.viewport_size
    workspace = screen.locator('body').evaluate("()=>window.tetherWorkspace||'work'")
    Path('artifacts').mkdir(exist_ok=True)
    for width in (1280, 320):
        page.set_viewport_size({'width': width, 'height': 900})
        expect(row.get_by_role('checkbox')).to_be_visible()
        assert screen.locator('body').evaluate('()=>document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path=f'artifacts/task-controls-{workspace}-{width}.png')
    page.set_viewport_size(original_size)
    screen.get_by_role('link', name='Conversation', exact=True).click()

    # A check-in establishes the selected action for the next short reply. It
    # survives leaving the conversation, requires no provider call, and never
    # changes the parent deadline or a sibling reminder.
    followup = api('threads', 'POST', {'title': 'Contextual tomorrow regression'})
    selected = api('threads/'+followup['id']+'/entries', 'POST', {'kind': 'action', 'body': 'Discuss this attention action'})
    sibling = api('threads/'+followup['id']+'/entries', 'POST', {'kind': 'action', 'body': 'Keep this sibling in attention'})
    for entry in (selected, sibling):
        api('actions/'+entry['id'], 'PATCH', {'due_at': '2020-01-01', 'revisit_at': '2020-01-01T09:00:00Z'})
    selected_card = screen.locator('#due button[data-action-id="'+selected['id']+'"]')
    sibling_card = screen.locator('#due button[data-action-id="'+sibling['id']+'"]')
    expect(selected_card).to_be_visible(timeout=7000)
    selected_card.click()
    expect(screen.locator('.chat-context-chip').filter(has_text=selected['body'])).to_be_visible()
    expect(screen.locator('.chat-pending')).to_have_count(0, timeout=10000)
    screen.get_by_role('link', name='Tasks', exact=True).click()
    screen.get_by_role('link', name='Conversation', exact=True).click()
    expect(screen.locator('.chat-context-chip').filter(has_text=selected['body'])).to_be_visible()
    screen.get_by_label('Message tether').fill("Let's do that tomorrow")
    screen.get_by_role('button', name='Send', exact=True).click()
    expect(selected_card).to_have_count(0, timeout=10000)
    expect(sibling_card).to_be_visible()
    expect(screen.locator('#settings')).to_be_hidden()
    data = api('threads/'+followup['id'])
    assert not data['revisit_at'] and not data['snoozed_until']
    actions = {entry['id']: entry for entry in data['entries']}
    assert actions[selected['id']]['snoozed_until'] and actions[selected['id']]['due_at'] == '2020-01-01'
    assert not actions[sibling['id']]['snoozed_until'] and actions[sibling['id']]['revisit_at'].startswith('2020-01-01')
    assert len([item for item in api('threads') if item['title'] == followup['title']]) == 1
    while screen.locator('.chat-context-chip button').count():
        screen.locator('.chat-context-chip button').first.click()


def main():
    """Run focused controls checks locally without any real AI provider."""
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    import importlib.util
    import os
    import socket
    import subprocess
    import sys
    import tempfile
    import threading
    import time
    from urllib.request import urlopen
    from playwright.sync_api import sync_playwright

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    with tempfile.TemporaryDirectory(prefix='tether-controls-ui-') as temp:
        folder = Path(temp)
        environment = {**os.environ, 'TETHER_DB': str(folder/'desktop.sqlite3'), 'TETHER_CONFIG': str(folder/'provider.json')}
        environment.pop('TETHER_AI_API_KEY', None)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0));port = sock.getsockname()[1]
        desktop = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'tether.app:app', '--host', '127.0.0.1', '--port', str(port)],
                                   cwd=root, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        desktop_url = f'http://127.0.0.1:{port}'
        static = None
        try:
            for _ in range(100):
                try:
                    with urlopen(desktop_url+'/api/health', timeout=1):break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('The isolated desktop server did not start')
            spec = importlib.util.spec_from_file_location('build_web', root/'scripts/build_web.py')
            builder = importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
            builder.build(folder/'tether-chat', '/tether-chat/')
            class QuietHandler(SimpleHTTPRequestHandler):
                def log_message(self, *args):pass
            static = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(folder)))
            threading.Thread(target=static.serve_forever, daemon=True).start()
            browser_url = f'http://127.0.0.1:{static.server_port}/tether-chat/?view=board'
            with sync_playwright() as pw:
                executable = os.environ.get('TETHER_TEST_CHROMIUM')
                browser = pw.chromium.launch(**({'executable_path': executable} if executable else {}))
                for name, url, embedded in [('desktop', desktop_url+'/board', False), ('browser', browser_url, True)]:
                    context = browser.new_context(viewport={'width': 1280, 'height': 900}, timezone_id='America/New_York')
                    page = context.new_page();errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(url)
                    screen = page.frame_locator('#app-frame') if embedded else page
                    check_task_controls(page, screen)
                    assert not errors, errors
                    context.close()
                    print(name+': task/action checkboxes, keyboard completion, save failure recovery, scoped deferral, archive/Undo, recurring identity and mobile layout passed.')
                browser.close()
        finally:
            desktop.terminate()
            try:desktop.wait(timeout=5)
            except subprocess.TimeoutExpired:desktop.kill();desktop.wait()
            if static:static.shutdown();static.server_close()


if __name__ == '__main__':main()
