"""Shared real-API checks for automatic Attention updates in both editions."""
from playwright.sync_api import expect


def check_attention_updates(page, ui, api_base, board_url, board_path, embedded=False):
    def api(path, method='GET', body=None):
        return ui.locator('body').evaluate('''async (_, args)=>{
          const response=await fetch(args[0],{method:args[1],headers:{'Content-Type':'application/json'},body:args[2]===null?undefined:JSON.stringify(args[2])});
          const data=await response.json();if(!response.ok)throw Error(JSON.stringify(data));return data;
        }''', [api_base+path, method, body])

    # Fixtures use the real runtime/API, and contain no user data or credentials.
    task=api('/threads','POST',{'title':'Live Attention fixture'})
    api('/threads/'+task['id'],'PATCH',{'revisit_at':'2020-01-01T12:00:00Z'})
    actions=[api('/threads/'+task['id']+'/entries','POST',{'kind':'action','body':name})
             for name in ('Finish this Attention action','Reschedule its sibling')]
    for action in actions:api('/actions/'+action['id'],'PATCH',{'revisit_at':'2020-01-01T12:00:00Z'})
    first=ui.locator('#due button[data-action-id="'+actions[0]['id']+'"]')
    second=ui.locator('#due button[data-action-id="'+actions[1]['id']+'"]')
    expect(first).to_be_visible(timeout=6000);expect(second).to_be_visible()
    ui.get_by_label('Message tether').fill('Keep my unsent Attention draft')
    first.click()
    link=ui.locator('#chat a[href="'+board_path+'#action/'+task['id']+'/'+actions[0]['id']+'"]')
    expect(link).to_be_visible(timeout=6000);link.click()
    drawer=ui.locator('#chatSelection')
    drawer.get_by_label('Completed',exact=True).check()
    drawer.get_by_role('button',name='Save changes',exact=True).click()
    expect(first).to_have_count(0,timeout=2000);expect(second).to_be_visible()
    expect(ui.get_by_label('Message tether')).to_have_value('Keep my unsent Attention draft')
    page.keyboard.press('Escape')

    # Saving in a second tab updates the original tab when it is viewed again.
    other=page.context.new_page();other.goto(board_url)
    other_ui=other.frame_locator('#app-frame') if embedded else other
    other_ui.locator('.task-row').filter(has_text='Live Attention fixture').click()
    other_ui.locator('[data-action-id="'+actions[1]['id']+'"]').click()
    other_ui.get_by_label('Bring to attention',exact=True).fill('2035-01-01T12:00')
    other_ui.get_by_role('button',name='Save changes',exact=True).click()
    expect(other_ui.locator('#actionDrawer')).to_be_hidden()
    page.bring_to_front();expect(second).to_have_count(0,timeout=2000)
    other.close()

    # Direct/outside writes have no UI event: the fallback must still pick them up.
    api('/threads/'+task['id'],'PATCH',{'title':'Current Attention title'})
    parent=ui.locator('#due button[data-task-id="'+task['id']+'"]').filter(has_text='Current Attention title')
    expect(parent).to_be_visible(timeout=6000)
    api('/threads/'+task['id'],'PATCH',{'revisit_at':'2035-01-01T12:00:00Z'})
    expect(parent).to_have_count(0,timeout=6000)
    expect(ui.get_by_label('Message tether')).to_have_value('Keep my unsent Attention draft')

    # Child-only attention disappears without creating parent urgency; independent
    # parent reminders above remain intact. A future projected cycle is not due.
    child_only=api('/threads','POST',{'title':'Child-only attention regression'})
    child=api('/threads/'+child_only['id']+'/entries','POST',{'kind':'action','body':'Dismiss this child'})
    api('/actions/'+child['id'],'PATCH',{'revisit_at':'2020-01-01T12:00:00Z'})
    child_card=ui.locator('#due button[data-action-id="'+child['id']+'"]')
    expect(child_card).to_be_visible(timeout=6000)
    api('/actions/'+child['id'],'PATCH',{'done':True})
    expect(child_card).to_have_count(0,timeout=6000)
    expect(ui.locator('#due button[data-task-id="'+child_only['id']+'"]')).to_have_count(0)
    repeating=api('/threads','POST',{'title':'Future occurrence attention regression'})
    api('/threads/'+repeating['id'],'PATCH',{'recurrence':'daily','next_occurrence':'2035-01-01'})
    result=api('/threads/'+repeating['id']+'/complete-occurrence','POST',{})
    assert not result['completion']['completed'] and result['next_occurrence']=='2035-01-01'
    assert not any(item['task_id']==repeating['id'] for item in api('/attention')['items'])
