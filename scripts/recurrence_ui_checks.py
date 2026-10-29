"""Real shared recurrence editor and bounded calendar projection regressions."""
from datetime import datetime, timezone
from pathlib import Path


def check_recurrence(page, screen):
    from playwright.sync_api import expect
    page.clock.set_system_time(datetime(2026, 10, 28, 21, 28, tzinfo=timezone.utc))

    def api(path, method='GET', body=None):
        return screen.locator('body').evaluate('''async(_,a)=>{
          const r=await fetch(new URL('api/'+a.path,location.href).href,{method:a.method,
            headers:{'Content-Type':'application/json'},body:a.body===null?undefined:JSON.stringify(a.body)});
          if(!r.ok)throw Error('Recurrence fixture API '+r.status);return r.json();
        }''', {'path':path,'method':method,'body':body})

    def task(title):
        return next(t for t in api('threads') if t['title']==title)

    def tasks_view():
        screen.locator('#display-menu').click()
        screen.get_by_role('link',name='Tasks',exact=True).click()
        expect(screen.locator('#board')).to_be_visible()

    def open_editor(title):
        screen.locator('.task-row').filter(has_text=title).first.click()
        screen.locator('.edit-task-button').click()
        expect(screen.locator('#panel')).to_be_visible()
        expect(screen.locator('#heading')).to_have_text(title)
        expect(screen.locator('#title')).to_have_value(title)

    def create(title, frequency, next_date, end=''):
        page.once('dialog',lambda dialog:dialog.accept(title))
        screen.locator('#new').click()
        expect(screen.locator('#panel')).to_be_visible()
        expect(screen.locator('#title')).to_have_value(title)
        screen.locator('#recurrence').select_option(frequency)
        screen.locator('#nextOccurrence').fill(next_date)
        screen.locator('#recurrenceEnd').fill(end)
        screen.locator('#edit button.primary').click()
        expect(screen.locator('#edit')).to_have_attribute('aria-busy','false')
        # Reopen from the board after a real save, avoiding assumptions about
        # whether Home's bridge or desktop's HTTP mutation finishes first.
        expect(screen.locator('#error')).to_be_empty()
        screen.locator('#close').click()
        open_editor(title)
        expect(screen.locator('#nextOccurrence')).to_have_value(next_date)
        expect(screen.locator('#recurrenceEnd')).to_have_value(end)
        screen.locator('#close').click()
        return task(title)

    tasks_view()
    baseline=len(api('threads'))
    bounded=create('Bounded recurrence UI fixture','daily','2026-10-29T09:15','2026-10-31')
    unlimited=create('Unlimited recurrence UI fixture','weekly','2026-10-30T14:30')
    assert bounded['recurrence_end']=='2026-10-31'
    assert bounded['recurrence_timezone']=='America/New_York'
    assert unlimited['recurrence_end'] is None
    screen.get_by_role('link',name='Display',exact=True).click()
    expect(screen.locator('#display-title')).to_have_text('October 2026')
    calendar=screen.frame_locator('#display-calendar')

    def select(date,title):
        calendar.locator('[data-date="'+date+'"] .day-date').click()
        expect(calendar.locator('#date-panel')).to_have_attribute('data-date',date)
        card=calendar.locator('#date-panel-items button.task').filter(has_text=title)
        expect(card).to_have_count(1)
        return card

    for day in ['2026-10-29','2026-10-30','2026-10-31']:
        card=select(day,bounded['title'])
        expect(card).to_contain_text('Occurrence')
        expect(card).to_contain_text('9:15 AM')
    card.click()
    expect(calendar.locator('#task-detail')).to_be_visible()
    expect(calendar.locator('#task-detail-body')).to_contain_text('Oct 31')
    expect(calendar.locator('#task-detail-body')).to_contain_text('9:15 AM')
    calendar.locator('#task-detail-close').click()
    expect(calendar.locator('#task-detail')).to_be_hidden()
    screen.locator('#display-next').click()
    expect(screen.locator('#display-title')).to_have_text('November 2026')
    for day in ['2026-11-06','2026-11-13','2026-11-20','2026-11-27']:
        card=select(day,unlimited['title'])
        # The New York wall time remains stable across November's DST change.
        expect(card).to_contain_text('2:30 PM')
        expect(calendar.locator('#date-panel-items')).not_to_contain_text(bounded['title'])
    data=api('snapshot?start=2026-11-01&end=2026-11-30')
    assert not any(t['id']==bounded['id'] for d in data['days'] for t in d['tasks'])
    assert sum(t['id']==unlimited['id'] for d in data['days'] for t in d['tasks'])==4
    assert len(api('threads'))==baseline+2, 'Calendar projection must not persist duplicate tasks'
    artifacts=Path('artifacts');artifacts.mkdir(exist_ok=True)
    workspace=screen.locator('body').evaluate("()=>window.tetherWorkspace||'work'")
    page.screenshot(path=str(artifacts/f'display-{workspace}-recurrence.png'))
    # A future schedule makes completion checks independent of the CI machine's
    # present date. Each completion advances the same task, then ends inclusively.
    tasks_view()
    future=create('Completion recurrence UI fixture','weekly','2099-01-01T09:15','2099-01-08')
    open_editor(future['title'])
    screen.locator('#completeOccurrence').click()
    expect(screen.locator('#nextOccurrence')).to_have_value('2099-01-08T09:15')
    screen.locator('#completeOccurrence').click()
    expect(screen.locator('#nextOccurrence')).to_have_value('')
    expect(screen.locator('#completeOccurrence')).to_be_disabled()
    assert task(future['title'])['id']==future['id']
    assert len(api('threads'))==baseline+3
    # Editing can remove an end date without duplicating or resetting its anchor.
    screen.locator('#close').click()
    open_editor(bounded['title'])
    screen.locator('#recurrenceEnd').fill('')
    screen.locator('#edit button.primary').click()
    expect(screen.locator('#edit')).to_have_attribute('aria-busy','false')
    screen.locator('#close').click()
    open_editor(bounded['title'])
    expect(screen.locator('#recurrenceEnd')).to_have_value('')
    assert task(bounded['title'])['recurrence_anchor']==bounded['recurrence_anchor']
    # Date-only repeats retain their calendar date without a midnight UTC shift.
    screen.locator('#occurrenceAllDay').check()
    screen.locator('#nextOccurrence').fill('2026-10-29')
    screen.locator('#edit button.primary').click()
    expect(screen.locator('#edit')).to_have_attribute('aria-busy','false')
    expect(screen.locator('#nextOccurrence')).to_have_attribute('type','date')
    expect(screen.locator('#nextOccurrence')).to_have_value('2026-10-29')
    assert task(bounded['title'])['next_occurrence']=='2026-10-29'
    page.set_viewport_size({'width':320,'height':640})
    assert screen.locator('#panel').evaluate('(n)=>n.scrollWidth<=n.clientWidth+1'), 'Recurrence editor horizontal overflow'
    screen.locator('#recurrenceEnd').scroll_into_view_if_needed()
    expect(screen.locator('#occurrenceAllDay')).to_be_visible()
    expect(screen.locator('#recurrenceEnd')).to_be_in_viewport()
    page.screenshot(path=str(artifacts/f'display-{workspace}-recurrence-editor-320.png'))
    page.set_viewport_size({'width':1280,'height':900})
    screen.locator('#close').click()
    # Chat snapshots use the same projected data and selected occurrence context.
    screen.get_by_role('link',name='Conversation',exact=True).click()
    screen.get_by_label('Message tether').fill('/snapshot 2026-11-01 to 2026-11-30')
    screen.get_by_role('button',name='Send',exact=True).click()
    chat_calendar=screen.frame_locator('.snapshot-frame').last
    chat_calendar.locator('[data-date="2026-11-06"] .day-date').click()
    expect(chat_calendar.locator('#date-panel-items')).to_contain_text(unlimited['title'])
    expect(chat_calendar.locator('#date-panel-items')).to_contain_text('2:30 PM')
    screen.get_by_role('link',name='Display',exact=True).click()
    expect(screen.locator('#display-title')).to_have_text('October 2026')
