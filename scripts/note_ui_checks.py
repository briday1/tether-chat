"""Exercise Note rendering through each edition's real chat queue and data API."""
from playwright.sync_api import expect


def check_note_replies(page, ui, api_base):
    def api(path, method='GET', body=None):
        return ui.locator('body').evaluate('''async (_, args)=>{
          const response=await fetch(args[0],{method:args[1],headers:{'Content-Type':'application/json'},body:args[2]===null?undefined:JSON.stringify(args[2])});
          const data=await response.json();if(!response.ok)throw Error(JSON.stringify(data));return data;
        }''', [api_base+path, method, body])

    title='Note [A] | fixture'
    task=api('/threads','POST',{'title':title,'summary':'Keep the decision context.'})
    api('/threads/'+task['id'],'PATCH',{'due_at':'2020-01-01T12:00:00Z','revisit_at':'2035-01-02T12:00:00Z'})
    action=api('/threads/'+task['id']+'/entries','POST',{'kind':'action','body':'Check | attachment'})
    api('/actions/'+action['id'],'PATCH',{'due_at':'2030-05-03T12:00:00Z','revisit_at':'2030-05-04T12:00:00Z'})
    finished=api('/threads/'+task['id']+'/entries','POST',{'kind':'action','body':'Finished Note action'})
    api('/actions/'+finished['id'],'PATCH',{'done':True})
    before=api('/threads/'+task['id'])
    draft=ui.get_by_label('Message tether').input_value()
    viewport=page.viewport_size
    ui.get_by_label('Message tether').fill('/brief')
    ui.get_by_role('button',name='Send',exact=True).click()
    message=ui.locator('.bubble.assistant').filter(has_text=title)
    expect(message).to_have_count(1,timeout=15000)
    row=message.locator('.note-rows tbody tr').filter(has_text=title)
    expect(row).to_have_count(1)
    cells=row.locator('td');expect(cells).to_have_count(3)
    expect(cells.nth(0)).to_have_text(title)
    expect(cells.nth(1)).to_contain_text('Keep the decision context.')
    expect(cells.nth(1)).to_contain_text('Check | attachment (due 2030-05-03; Bring to attention 2030-05-04)')
    expect(cells.nth(2)).to_have_text('Due 2020-01-01; Bring to attention 2035-01-02')
    expect(message).not_to_contain_text('Finished Note action')
    assert ui.locator('html').evaluate('(e)=>e.scrollHeight<=e.clientHeight+1'),'Note table headers must stay inside the chat scroll area'
    assert cells.nth(0).get_by_role('link',name=title,exact=True).evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgba(0, 0, 0, 0)'
    for width in (390,320):
        page.set_viewport_size({'width':width,'height':900})
        assert ui.locator('html').evaluate('(e)=>e.scrollWidth<=e.clientWidth'),width
        assert ui.locator('html').evaluate('(e)=>e.scrollHeight<=e.clientHeight+1'),width
        assert message.locator('.note-table-wrap').first.evaluate('(e)=>e.scrollWidth<=e.clientWidth+1'),width
        assert row.evaluate('(e)=>e.children[1].getBoundingClientRect().top>e.children[0].getBoundingClientRect().top'),width
    page.set_viewport_size(viewport)
    cells.nth(0).get_by_role('link',name=title,exact=True).click()
    drawer=ui.locator('#chatSelection')
    expect(drawer.get_by_role('heading',name=title,exact=True)).to_be_visible()
    ui.get_by_role('button',name='Close details',exact=True).click()
    assert api('/threads/'+task['id'])==before,'Rendering a Note must not alter its task or actions'
    cells.nth(0).get_by_role('link',name=title,exact=True).click()
    drawer.get_by_label('Task note type').select_option('meeting')
    drawer.get_by_label('Meeting title',exact=True).fill('Review meeting')
    drawer.get_by_label('Add task note',exact=True).fill('Decision: verify access Friday.')
    drawer.get_by_role('button',name='Save note',exact=True).click()
    expect(drawer.get_by_role('status')).to_contain_text('Note saved on this task.')
    saved=api('/threads/'+task['id'])
    assert any(e['body']=='Meeting notes — Review meeting\n\nDecision: verify access Friday.' for e in saved['entries'])
    ui.get_by_role('button',name='Close details',exact=True).click()
    cells.nth(0).get_by_role('link',name=title,exact=True).click()
    expect(drawer.locator('.action-note-body')).to_contain_text('Decision: verify access Friday.')
    ui.get_by_role('button',name='Close details',exact=True).click()
    ui.get_by_label('Message tether').fill(draft)
