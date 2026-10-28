"""Explicit selected-task context is visible, durable, and dismissible."""
from playwright.sync_api import expect


def check_task_context(page, ui, title):
    ui.get_by_role('link',name='Tasks',exact=True).click()
    ui.locator('.task-row').filter(has_text=title).click()
    ui.get_by_role('button',name='Use as chat context',exact=True).click()
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
