import pytest
from fastapi.testclient import TestClient
from tend import store
from tend.app import app

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv("TEND_DB",str(tmp_path/"test.sqlite3"))
    store.init()
    return TestClient(app,base_url="http://127.0.0.1")

def test_capture_search_revisit_and_delete(client):
    t=client.post("/api/threads",json={"title":"Think about this"}).json()
    id=t["id"]
    assert client.get("/api/threads?q=Think").json()[0]["id"]==id
    note=client.post(f"/api/threads/{id}/entries",json={"kind":"action","body":"Try something"}).json()
    assert client.patch("/api/entries/"+note["id"],json={"done":True}).json()["done"]==1
    assert len(client.get("/api/threads?q=Try").json())==1
    assert client.patch("/api/threads/"+id,json={"revisit_at":"2020-01-01T00:00:00Z","state":"waiting"}).status_code==200
    assert client.get("/api/overview").json()["due"][0]["id"]==id
    assert client.delete("/api/threads/"+id).json()["deleted"] is True

def test_related_and_home(client):
    a=client.post("/api/threads",json={"title":"A"}).json()["id"]
    b=client.post("/api/threads",json={"title":"B"}).json()["id"]
    assert client.post("/api/threads/"+a+"/links",json={"other_id":b}).status_code==200
    assert client.get("/api/threads/"+b).json()["related"][0]["id"]==a
    assert client.get("/").status_code==200

def test_board_category_and_manual_edit(client):
    thought=client.post("/api/threads",json={"title":"Experiment with a new interface"}).json()
    id=thought["id"]
    response=client.patch(f"/api/threads/{id}",json={"category":"Product ideas","summary":"Try different views","state":"waiting"})
    assert response.status_code==200
    assert response.json()["category"]=="Product ideas"
    board=client.get("/api/board")
    assert board.status_code==200
    assert any(x["name"]=="Product ideas" and x["threads"][0]["id"]==id for x in board.json())
    assert client.get("/board").status_code==200

def test_markdown_is_sanitized_and_formatted():
    from tend.rendering import render
    html = render("**Bold** and *italic*\n\n- one\n- two\n\n<script>alert(1)</script>")
    assert "<strong>Bold</strong>" in html
    assert "<em>italic</em>" in html
    assert "<li>" in html
    assert "<script>" not in html
    assert "alert(1)" in html

def test_rendered_history(client):
    from tend import store
    store.remember("assistant","A **formatted** response")
    result = client.get("/api/conversation/rendered")
    assert result.status_code == 200
    assert "<strong>formatted</strong>" in result.json()[-1]["html"]

def test_theme_assets(client):
    from tend import __version__
    css=client.get("/theme.css")
    js=client.get("/theme.js")
    assert css.status_code==200 and "--accent" in css.text
    assert js.status_code==200 and "data-theme-picker" in js.text
    assert f'href="/theme.css?release={__version__}"' in client.get("/").text
    assert f'href="/theme.css?release={__version__}"' in client.get("/board").text

@pytest.mark.parametrize('path',['/','/board','/snapshots'])
def test_desktop_upgrade_uses_fresh_asset_urls(client,path):
    import re
    from tend import __version__
    page=client.get(path)
    assert page.headers['cache-control']=='no-store'
    assets=re.findall(r'(?:src|href)="(/[^" ]+\.(?:css|m?js)\?[^" ]+)"',page.text)
    assert assets
    for url in assets:
        assert 'release='+__version__ in url
        response=client.get(url)
        assert response.status_code==200 and response.headers['cache-control']=='no-store'

def test_local_brief_and_command_reference(client):
    from tend import commands,store
    store.create("Important ongoing decision")
    assert "Important ongoing decision" in store.daily_brief()
    assert "**/brief**" in commands.execute("/help")["answer"]
    assert client.post("/api/chat",json={"text":"/brief"}).status_code==200
    assert any(c["name"]=="/brief" for c in client.get("/api/commands").json())

def test_claim_reminder_once(client):
    from tend import store
    t=store.create("Check local reminder")
    from datetime import datetime,timezone,timedelta
    moment=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
    store.update(t["id"],{"revisit_at":moment})
    found=store.claim_notifications()
    assert any(row["id"]==t["id"] for row in found)
    assert all(row["id"]!=t["id"] for row in store.claim_notifications())
    store.update(t["id"],{"revisit_at":(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()})
    assert any(row["id"]==t["id"] for row in store.claim_notifications())

def test_attention_empty_and_commands_without_api_key(client,monkeypatch):
    from tend import ai
    monkeypatch.setattr(ai,"public_config",lambda:{"has_key":False})
    assert client.get("/api/attention?force=true").json()["items"]==[]
    assert client.get("/api/brief").status_code==200

def test_due_date_separate_from_attention(client):
    t=client.post("/api/threads",json={"title":"Deadline test"}).json()
    data=client.patch(f"/api/threads/{t['id']}",json={"due_at":"2026-12-15T12:00:00Z","revisit_at":"2026-11-15T09:00:00Z"}).json()
    assert data["due_at"].startswith("2026-12-15")
    assert data["revisit_at"].startswith("2026-11-15")

def test_activity_reporting_backdated(client):
    t=client.post("/api/threads",json={"title":"Activity test"}).json()
    result=client.post(f"/api/threads/{t['id']}/activity",json={"body":"Worked on a draft","kind":"progress","occurred_at":"2026-07-08T10:00:00Z"})
    assert result.status_code==201
    report=client.get("/api/activity/report?period=quarter&anchor=2026-07-10T12:00:00Z").json()
    assert any(event["body"]=="Worked on a draft" for event in report["events"])

def test_database_folder_move_and_verified_switch(tmp_path,monkeypatch):
    from tend import storage,store
    monkeypatch.delenv("TEND_DB",raising=False)
    old=tmp_path/"old.sqlite3"
    newdir=tmp_path/"new"
    newdir.mkdir()
    monkeypatch.setattr(storage,"config_path",lambda:tmp_path/"storage.json")
    monkeypatch.setattr(storage,"active_path",lambda:old if not storage.load().get("active") else __import__("pathlib").Path(storage.load()["active"]))
    # Ensure a real populated database is migrated with the SQLite backup API.
    with __import__("sqlite3").connect(old) as c:
        c.execute("CREATE TABLE sample(value TEXT)")
        c.execute("INSERT INTO sample VALUES ('preserved')")
    pending=storage.stage(str(newdir),"move")
    assert pending["pending"]==str(newdir/"old.sqlite3")
    storage.activate_pending()
    assert storage.info()["current"]==str(newdir/"old.sqlite3")
    with __import__("sqlite3").connect(newdir/"old.sqlite3") as c:
        assert c.execute("SELECT value FROM sample").fetchone()[0]=="preserved"
    assert old.exists()

def test_desktop_health_and_webapp_manifest(client):
    response=client.get("/api/health")
    assert response.status_code==200
    assert response.json()["app"]=="tend"
    manifest=client.get("/manifest.webmanifest")
    assert manifest.status_code==200
    assert manifest.json()["display"]=="standalone"
    assert 'rel="manifest"' in client.get("/").text
    assert 'rel="manifest"' in client.get("/board").text


def test_notification_worker_has_no_ai_dependency():
    import inspect
    from tend import notifications
    source=inspect.getsource(notifications)
    assert "nudges" not in source
    assert "ai.request" not in source
    assert "claim_notifications" in source

def test_stream_reports_status_and_completion(client,monkeypatch):
    from tend import ai
    def fake_chat(message,progress=None):
        if progress:
            progress("Connecting to AI provider…")
            progress("Tool: overview — completed")
        return {"answer":"Found **two** items","actions":["overview"]}
    monkeypatch.setattr(ai,"chat",fake_chat)
    response=client.post("/api/chat/stream",json={"text":"What am I tracking?"})
    assert response.status_code==200
    import json
    events=[json.loads(line) for line in response.text.splitlines()]
    assert events[0]["type"]=="status"
    assert events[1]["message"]=="Tool: overview — completed"
    assert events[-1]["type"]=="done"
    assert "<strong>two</strong>" in events[-1]["answer_html"]

def test_linked_weekly_activity_report(client):
    from tend import store
    report_task=store.create("Weekly activity report")
    store.update(report_task["id"],{"category":"Branch Activity"})
    work=store.create("Branch planning")
    store.update(work["id"],{"category":"Branch Activity"})
    other=store.create("Unrelated project")
    store.update(other["id"],{"category":"Other"})
    store.record_activity(work["id"],"Finished branch planning","progress","2026-10-20T15:00:00+00:00")
    store.record_activity(other["id"],"Unrelated meeting","progress","2026-10-20T16:00:00+00:00")
    result=store.configure_due_action(report_task["id"],"activity_report","week","Branch Activity")
    assert result["due_action"]=="activity_report"
    preview=store.report_for_task(report_task["id"],"2026-10-23T13:00:00+00:00")
    assert preview["count"]==1
    assert preview["events"][0]["body"]=="Finished branch planning"
    assert preview["category"]=="Branch Activity"
    assert store.get(report_task["id"])["action_config"]["period"]=="week"

def test_recurring_due_is_in_overview(client):
    from tend import store
    t=store.create("Weekly activity report")
    store.update(t["id"],{"recurrence":"weekly","next_occurrence":"2020-01-01T00:00:00+00:00"})
    assert any(item["id"]==t["id"] for item in store.overview()["due"])

def test_task_action_editor_persists_prompt_and_schedule(client):
    task=client.post("/api/threads",json={"title":"Weekly activity report"}).json()
    response=client.patch("/api/threads/"+task["id"],json={
        "recurrence":"weekly","next_occurrence":"2026-10-23T17:00:00Z",
        "due_action":"activity_report",
        "action_prompt":"Summarize Branch Activity work for the week.",
        "action_config":{"period":"week","category":"Branch Activity"}})
    assert response.status_code==200, response.text
    saved=client.get("/api/threads/"+task["id"]).json()
    assert saved["action_prompt"]=="Summarize Branch Activity work for the week."
    assert saved["action_config"]=={"period":"week","category":"Branch Activity"}
    assert saved["recurrence"]=="weekly"
    assert saved["due_action"]=="activity_report"

def test_archive_restore_preserves_task(client):
    from tend import store
    task=store.create("Old work")
    ident=task["id"]
    store.add(ident,"thought","Original notes")
    archive=client.post("/api/threads/"+ident+"/archive")
    assert archive.status_code==200
    assert archive.json()["archived_at"]
    assert not any(t["id"]==ident for g in client.get("/api/board").json() for t in g["threads"])
    assert any(t["id"]==ident for t in client.get("/api/archived").json())
    assert all(t["id"]!=ident for t in client.get("/api/overview").json()["active"])
    restored=client.post("/api/threads/"+ident+"/restore")
    assert restored.status_code==200 and restored.json()["archived_at"] is None
    assert len(restored.json()["entries"])==1
    assert any(t["id"]==ident for g in client.get("/api/board").json() for t in g["threads"])
