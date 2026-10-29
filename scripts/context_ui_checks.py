"""Explicit selected-task context is visible, durable, and dismissible."""
from playwright.sync_api import expect
from pathlib import Path


def check_task_context(page, ui, title):
    ui.get_by_role('link',name='Tasks',exact=True).click()
    ui.locator('.task-row').filter(has_text=title).click()
    context=ui.get_by_role('button',name='Use as chat context',exact=True)
    edit=ui.get_by_role('button',name='Edit task',exact=True)
    expect(context).to_be_visible()
    saved_viewport=page.viewport_size
    saved_theme=ui.locator('body').evaluate('n=>n.ownerDocument.documentElement.dataset.theme')
    workspace=ui.locator('body').evaluate('n=>n.ownerDocument.defaultView.tetherWorkspace||"work"')
    Path('artifacts').mkdir(exist_ok=True)
    for theme in ('light','dark'):
        ui.locator('body').evaluate('(n,theme)=>n.ownerDocument.documentElement.dataset.theme=theme',theme)
        for width in (1280,320):
            page.set_viewport_size({'width':width,'height':900 if width>320 else 640})
            context.scroll_into_view_if_needed()
            expected=edit.bounding_box();actual=context.bounding_box()
            assert abs(actual['height']-expected['height'])<=1,(expected,actual)
            assert 28<=actual['height']<=30 and actual['width']<200,actual
            style="n=>{const s=getComputedStyle(n);return [s.padding,s.fontSize,s.lineHeight,s.borderRadius]}"
            assert context.evaluate(style)==edit.evaluate(style)
            assert context.evaluate('n=>n.scrollWidth<=n.clientWidth'), 'Context label is clipped'
            assert ui.locator('body').evaluate('n=>n.ownerDocument.documentElement.scrollWidth<=n.ownerDocument.defaultView.innerWidth')
            edit.focus()
            page.keyboard.press('Tab')
            expect(context).to_be_focused()
            assert context.evaluate("n=>getComputedStyle(n).outlineStyle!=='none'")
            ui.locator('.actions-section').screenshot(path=f'artifacts/display-context-buttons-{workspace}-{theme}-{width}.png')
    page.set_viewport_size(saved_viewport)
    ui.locator('body').evaluate('(n,theme)=>n.ownerDocument.documentElement.dataset.theme=theme',saved_theme)
    context.focus()
    page.keyboard.press('Enter')
    expect(ui.locator('.chat-context-chip')).to_contain_text(title)
    # Navigation retains the selection without sending an AI request.
    ui.get_by_label('Message tether').fill('Unsent context draft')
    ui.get_by_role('link',name='Tasks',exact=True).click()
    ui.get_by_role('link',name='Conversation',exact=True).click()
    expect(ui.locator('.chat-context-chip')).to_contain_text(title)
    expect(ui.get_by_label('Message tether')).to_have_value('Unsent context draft')
    ui.get_by_role('button',name='Remove '+title+' from chat context',exact=True).click()
    expect(ui.locator('.chat-context-chip')).to_have_count(0)
    ui.get_by_role('link',name='Tasks',exact=True).click()
    ui.get_by_role('link',name='Conversation',exact=True).click()
    expect(ui.locator('.chat-context-chip')).to_have_count(0)
    ui.get_by_label('Message tether').fill('')
