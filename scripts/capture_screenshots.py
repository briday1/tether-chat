"""Generate reproducible tether-chat UI screenshots from an isolated demo database.

Install: python -m pip install playwright
         python -m playwright install chromium
Run:     python scripts/capture_screenshots.py

Only synthetic sample records are used. Never reads the user's tether-chat database.
All screenshot examples use generic Projects, Operations, and Product categories.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from datetime import date, timedelta
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
PORT = 18765


def make_demo(db):
    os.environ["TETHER_DB"] = str(db)
    os.environ["TETHER_CONFIG"] = str(db.parent / "empty-provider.json")
    from tether import store
    store.init()
    report = store.create("Weekly activity report", "Summarize recent Projects.")
    store.update(report["id"], {
        "categories": ["Projects","Operations"], "recurrence": "weekly",
        "next_occurrence": "2027-01-08T17:00:00+00:00",
        "due_action": "activity_report",
        "action_prompt": "Summarize the week's recorded project activity.",
        "action_config": {"period": "week", "category": "Projects"},
    })
    for title, category, state in [
        ("Prepare briefing notes", "Projects", "open"),
        ("Review project milestones", "Projects", "waiting"),
        ("Renew development certificate", "Operations", "open"),
        ("Investigate dashboard bug", "Product", "open"),
        ("Update documentation", "Product", "paused"),
        ("Plan monthly review", "Operations", "open"),
    ]:
        summaries={
            'Prepare briefing notes':'Confirm attendees and assemble the supporting notes.',
            'Review project milestones':'Waiting for updated milestone dates.',
            'Renew development certificate':'Renew before the next deployment window.',
            'Investigate dashboard bug':'Reproduce the missing data with the saved view.',
            'Update documentation':'Paused until the new workflow is settled.',
            'Plan monthly review':'Coordinate availability and set the agenda.',
        }
        t = store.create(title, summaries[title])
        store.update(t["id"], {"category": category, "state": state})
    store.record_activity(report["id"], "Collected updates for the reporting period.")
    archived = store.create("Completed onboarding checklist")
    store.update(archived["id"], {"category": "Operations"})
    store.archive_thread(archived["id"])
    next_sunday=date.today()+timedelta(days=7-(date.today().weekday()+1)%7)
    for title,cat,offset in [("Prepare briefing notes","Projects",0),("Investigate dashboard bug","Product",2),("Renew development certificate","Operations",4)]:
        matches=[t for t in store.list_threads() if t["title"]==title]
        if matches:store.update(matches[0]["id"],{"due_at":(next_sunday+timedelta(days=offset)).isoformat()+"T12:00:00Z"})
    for title,categories,offset in [("Plan monthly review",["Operations","Projects"],0),
                                    ("Review project milestones",["Projects","Product"],2),
                                    ("Update documentation",["Product"],0)]:
        task=next(t for t in store.list_threads() if t["title"]==title)
        store.update(task["id"],{"categories":categories,"due_at":(next_sunday+timedelta(days=offset)).isoformat()+"T12:00:00Z"})
    from tether.notes import task_table
    tasks={t['title']:t for t in store.list_threads()}
    project_tasks=[tasks[title] for title in ('Prepare briefing notes','Review project milestones','Weekly activity report')]
    store.remember("user", "Give me an update on Projects.")
    store.remember("assistant", "Briefing preparation is open; milestone review is waiting for updated dates.\n\n### [Projects](/board#category/Projects)\n\n"+task_table(project_tasks,store.get))
    return report["id"]


def wait_for_server(base, proc):
    for _ in range(120):
        if proc.poll() is not None:
            raise RuntimeError("Screenshot server exited: " + str(proc.returncode))
        try:
            with urlopen(base + "/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError("Screenshot server never became ready")


def request_snapshot(page, message):
    count = page.locator('.snapshot-frame').count()
    page.locator('#message').fill(message)
    page.locator('#composer').evaluate('(form) => form.requestSubmit()')
    page.wait_for_function('(count) => document.querySelectorAll(".snapshot-frame").length > count', arg=count)
    page.locator('.snapshot-frame').last.content_frame.locator('.task').first.wait_for()
    page.wait_for_function("""() => [...document.querySelectorAll('.snapshot-frame')].every(f =>
        Math.abs(f.getBoundingClientRect().height-f.contentDocument.querySelector('.shell').getBoundingClientRect().height)<2)""")


def verify_snapshot_layers(page):
    theme = page.evaluate('document.documentElement.dataset.theme')
    for name in ['light','dark','solarized-light','solarized-dark','sepia','sage','rose','dusk','ocean']:
        page.evaluate('(name) => document.documentElement.dataset.theme=name', name)
        page.wait_for_function('(name) => [...document.querySelectorAll(".snapshot-frame")].every(f=>f.contentDocument.documentElement.dataset.theme===name)', arg=name)
        assert page.evaluate("""() => [...document.querySelectorAll('.snapshot-frame')].every(f => {
            const bubble=f.closest('.bubble.assistant'), style=getComputedStyle(bubble);
            const d=f.contentDocument, css=e=>f.contentWindow.getComputedStyle(e);
            const transparent=e=>css(e).backgroundColor==='rgba(0, 0, 0, 0)';
            return style.backgroundColor!=='rgba(0, 0, 0, 0)' && style.borderTopWidth==='1px'
                && ['html','body','.shell','.sheet','.calendar-head','.weekdays','.grid'].every(s=>transparent(d.querySelector(s)))
                && [...d.querySelectorAll('.day')].every(transparent)
                && [...d.querySelectorAll('.task')].every(t=>!transparent(t));
        })"""), 'Keep the chat bubble filled, calendar cells transparent, and project blocks colored in '+name
    page.evaluate('(theme) => document.documentElement.dataset.theme=theme', theme)
    page.wait_for_function('(theme) => [...document.querySelectorAll(".snapshot-frame")].every(f=>f.contentDocument.documentElement.dataset.theme===theme)', arg=theme)


def capture_calendar(page, filename):
    bubble = page.locator('.bubble.assistant:has(.snapshot-frame)').last
    viewport = page.viewport_size
    # The enclosing chat scroll area must fit the full bubble, including a month.
    page.set_viewport_size({**viewport, 'height': max(viewport['height'], round(bubble.bounding_box()['height']) + 350)})
    try:
        bubble.screenshot(path=str(OUT / filename))
    finally:
        page.set_viewport_size(viewport)


def main():
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tether-screenshots-") as scratch:
        scratch = Path(scratch)
        task_id = make_demo(scratch / "demo.sqlite3")
        env = os.environ.copy()
        env["TETHER_DB"] = str(scratch / "demo.sqlite3")
        env["TETHER_CONFIG"] = str(scratch / "empty-provider.json")
        env.pop("TETHER_AI_API_KEY", None)
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "tether.app:app",
             "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        base = "http://127.0.0.1:" + str(PORT)
        try:
            wait_for_server(base, server)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 900},
                                        device_scale_factor=2)
                # Never call a real AI provider during screenshot generation.
                page.route("**/api/attention*", lambda route: route.fulfill(
                    status=200, content_type="application/json",
                    body='{"items":[],"source":"demo"}'))
                page.goto(base + "/", wait_until="networkidle")
                page.locator('.note-rows').wait_for()
                page.screenshot(path=str(OUT / "conversation.png"), full_page=True)
                request_snapshot(page, "give me my next week snapshot")
                verify_snapshot_layers(page)
                capture_calendar(page, 'snapshot-week.png')
                week_start=date.today()+timedelta(days=7-(date.today().weekday()+1)%7)
                week_end=week_start+timedelta(days=6)
                page.goto(base + "/snapshots?start="+week_start.isoformat()+"&end="+week_end.isoformat(), wait_until="networkidle")
                page.locator(".day").first.wait_for()
                assert page.locator("#weekdays span").all_text_contents() == ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], "Calendars include every day, even empty weekends"
                assert page.locator(".summary, .stat, .eyebrow").count() == 0, "Snapshot must not include summary cards"
                assert page.locator('input,select').count()==0, "Calendars must be read-only"
                assert page.locator('.day').count()==7
                assert page.locator('.day-items .task').filter(has_text='Plan monthly review').locator('.task-categories').inner_text()=='Operations · Projects'
                assert page.locator('.day').first.locator('.task').count()==3, 'Show multiple tasks in one day'
                month_start=week_start.replace(day=1)
                following=(month_start.replace(year=month_start.year+1,month=1)
                           if month_start.month==12 else month_start.replace(month=month_start.month+1))
                month_end=following-timedelta(days=1)
                page.goto(base + "/snapshots?start="+month_start.isoformat()+"&end="+month_end.isoformat(), wait_until="networkidle")
                page.locator(".day").first.wait_for()
                assert page.locator("#weekdays span").all_text_contents() == ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
                assert page.locator(".task-marker").count()>0
                assert page.locator("#png, #svg, #details, #day-dialog").count()==0
                month_height=page.locator('.shell').bounding_box()['height']
                page.goto(base + "/snapshots?start="+week_start.isoformat()+"&end="+week_end.isoformat(), wait_until="networkidle")
                assert page.locator('.shell').bounding_box()['height']<month_height, "Week and month must size independently"
                assert page.locator('#png, #svg, #details, #day-dialog').count()==0
                page.locator('.day-items .task').first.click()
                assert page.locator('#date-panel').get_attribute('data-date')==week_start.isoformat()
                assert page.locator('#date-panel-items .task').count()==3
                assert page.locator('#date-panel input,#date-panel textarea').count()==0
                page.goto(base + '/', wait_until='networkidle')
                request_snapshot(page, f'/snapshot {month_start.isoformat()} to {month_end.isoformat()}')
                verify_snapshot_layers(page)
                capture_calendar(page, 'snapshot-month.png')
                page.goto(base + "/board", wait_until="networkidle")
                page.locator(".task-row").first.wait_for()
                assert page.locator('.task-row').count()==7, "Multi-category tasks must not create duplicate rows"
                assert page.locator('.task-section h2').inner_text()=='All Tasks (7)'
                page.screenshot(path=str(OUT / "tasks.png"), full_page=True)
                page.locator(".task-row").filter(has_text="Weekly activity report").click()
                page.locator(".actions-section").wait_for()
                page.locator(".actions-section button", has_text="Edit task").click()
                page.locator("#panel:not(.hidden)").wait_for()
                # Check adding and removing a membership through the actual editor.
                page.locator('#category').fill('Review')
                page.locator('#category').press('Enter')
                page.locator('#edit').evaluate('(form)=>form.requestSubmit()')
                page.wait_for_function("""() => document.querySelector('#category-tags').textContent.includes('Review')
                    && document.querySelector('.category-rows').textContent.includes('Review')""")
                page.locator('#category-tags button[aria-label="Remove Review"]').click()
                page.locator('#edit').evaluate('(form)=>form.requestSubmit()')
                page.wait_for_function("() => !document.querySelector('.category-rows').textContent.includes('Review')")
                page.screenshot(path=str(OUT / "task-details.png"), full_page=True)
                page.locator("#close").click()
                page.locator(".archive-switch").click()
                page.screenshot(path=str(OUT / "archive.png"), full_page=True)
                # Exercise the embedded calendar on a phone as well as desktop.
                page.set_viewport_size({'width':390,'height':844})
                page.goto(base+'/',wait_until='networkidle')
                request_snapshot(page, 'give me my next week snapshot')
                frame=page.locator('.snapshot-frame').last
                frame.content_frame.locator('.task').first.wait_for()
                page.wait_for_function("""() => [...document.querySelectorAll('.snapshot-frame')].every(f =>
                    Math.abs(f.getBoundingClientRect().height-f.contentDocument.querySelector('.shell').getBoundingClientRect().height)<2)""")
                assert frame.content_frame.locator('body').evaluate('(body)=>body.scrollWidth<=innerWidth'), 'Mobile snapshot must fit its frame'
                assert page.locator('body').evaluate('(body)=>body.scrollWidth<=innerWidth'), 'Chat must fit a phone'
                composer=page.locator('#composer').bounding_box()
                assert composer['y']+composer['height']<=845, 'The mobile message composer must stay visible'
                browser.close()
            print("Created:", ", ".join(p.name for p in sorted(OUT.glob("*.png"))))
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
