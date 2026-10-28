from pathlib import Path
import re
from datetime import datetime
from fastapi import FastAPI,HTTPException
from fastapi.responses import FileResponse,Response,HTMLResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel,Field
from typing import Literal
from . import __version__
from . import store as db
from . import ai
from . import commands
from . import storage
from .rendering import render
from .ai import reflect

app=FastAPI(title="tether-chat")
app.add_middleware(TrustedHostMiddleware,allowed_hosts=["127.0.0.1","localhost","[::1]"])
db.init()
from threading import Lock
_workspace_init_lock=Lock()
_initialized_workspaces={str(db.path().absolute())}

@app.middleware('http')
async def fresh_desktop_assets(request,call_next):
    from . import workspaces
    from fastapi.responses import JSONResponse
    mode=request.headers.get('X-Tether-Workspace',request.query_params.get('workspace','work'))
    try:workspaces.normalize(mode)
    except ValueError as exc:return JSONResponse({'detail':str(exc)},status_code=422)
    with workspaces.use(mode):
        if request.url.path.startswith('/api/'):
            path=str(db.path().absolute())
            if path not in _initialized_workspaces or not db.path().exists():
                with _workspace_init_lock:
                    if path not in _initialized_workspaces or not db.path().exists():
                        db.init();_initialized_workspaces.add(path)
        response=await call_next(request)
    if request.url.path.endswith(('.js','.mjs','.css')):
        response.headers['Cache-Control']='no-store'
    return response

def desktop_screen(name):
    """A new desktop release must never reuse an older WebView script URL."""
    text=Path(__file__).with_name(name).read_text(encoding='utf-8')
    def versioned(match):
        query=match[3] or ''
        return match[1]+match[2]+query+('&' if query else '?')+'release='+__version__+match[4]
    text=re.sub(r'''((?:src|href)=["'])(/[^"']+\.(?:css|m?js))(\?[^"']*)?(["'])''',versioned,text)
    return HTMLResponse(text,headers={'Cache-Control':'no-store'})
class Ask(BaseModel):
    question:str=Field(min_length=1,max_length=1000)
class Thread(BaseModel):
    title:str=Field(min_length=1,max_length=300)
    summary:str=""
    categories:list[str]|None=Field(default=None,max_length=20)
class Change(BaseModel):
    title:str|None=None
    summary:str|None=None
    category:str|None=None
    categories:list[str]|None=Field(default=None,max_length=20)
    state:Literal["open","waiting","paused","settled"]|None=None
    revisit_at:datetime|None=None
    due_at:datetime|None=None
    recurrence:Literal["daily","weekly","monthly","quarterly","yearly"]|None=None
    next_occurrence:datetime|None=None
    due_action:Literal["activity_report"]|None=None
    action_config:dict|None=None
    action_prompt:str|None=None
    archived_at:str|None=None
class Entry(BaseModel):
    kind:Literal["thought","question","action","decision","update"]="thought"
    body:str=Field(min_length=1)
class ActionChange(BaseModel):
    done:bool|None=None
    due_at:datetime|None=None
    revisit_at:datetime|None=None
class Done(BaseModel):
    done:bool
class Relation(BaseModel):
    other_id:str
def found(x):
    if x is None:raise HTTPException(404,"Not found")
    return x
@app.get("/icon/{size}.png")
def icon_png(size:int):
    if size not in (16,32,48,64,128,192,256,512):
        raise HTTPException(404,"Icon size unavailable")
    from .windows_icon import raster
    return Response(raster(size),media_type="image/png",headers={"Cache-Control":"public, max-age=3600"})

@app.get("/favicon.svg")
def favicon():return FileResponse(Path(__file__).with_name("favicon.svg"),media_type="image/svg+xml")
@app.get("/theme.css")
def theme_css():return FileResponse(Path(__file__).with_name("theme.css"),media_type="text/css")
@app.get("/theme.js")
def theme_js():return FileResponse(Path(__file__).with_name("theme.js"),media_type="application/javascript")
@app.get("/updates.js")
def updates_js():return FileResponse(Path(__file__).with_name("updates.js"),media_type="application/javascript")
@app.get("/notes.js")
def notes_js():return FileResponse(Path(__file__).with_name("notes.js"),media_type="application/javascript")
@app.get("/notes.css")
def notes_css():return FileResponse(Path(__file__).with_name("notes.css"),media_type="text/css")
@app.get("/api/health")
def health():return {"app":"tether","brand":"tether-chat","version":__version__,"status":"ok","streaming_chat":True,"board_categories":True,"tool_runner":"unbounded-v2"}
@app.get("/manifest.webmanifest")
def manifest():return FileResponse(Path(__file__).with_name("manifest.webmanifest"),media_type="application/manifest+json")
@app.get("/")
def home():return desktop_screen('index.html')
@app.get("/snapshots")
def snapshots_page():return desktop_screen('snapshot.html')
@app.get("/api/snapshot")
def snapshot_api(start:str,end:str,category:str=""):
    from .snapshots import snapshot
    try:return snapshot(start,end,category)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None

@app.get("/api/snapshot.png")
def snapshot_png(start:str,end:str,category:str="",theme:str="sage",scale:int=2):
    from .snapshot_export import png
    try:
        return Response(png(start,end,category,theme,scale),media_type="image/png",
                        headers={"Content-Disposition":"attachment; filename=tether-snapshot.png",
                                 "Cache-Control":"no-store"})
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from None

@app.get('/workspace.js')
def workspace_script():return FileResponse(Path(__file__).with_name('workspace.js'),media_type='application/javascript')
@app.get('/display.js')
def display_script():return FileResponse(Path(__file__).with_name('display.js'),media_type='application/javascript')
@app.get('/display.css')
def display_style():return FileResponse(Path(__file__).with_name('display.css'),media_type='text/css')
@app.get('/display')
def display_page():return desktop_screen('display.html')

@app.get("/board")
def board_page():return desktop_screen('board.html')
@app.get("/api/snapshot.svg")
def snapshot_svg(start:str,end:str,category:str="",theme:str="sage"):
    from .snapshot_export import svg
    try:return Response(svg(start,end,category,theme),media_type="image/svg+xml",
                        headers={"Content-Disposition":"attachment; filename=tether-snapshot.svg","Cache-Control":"no-store"})
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
@app.get("/api/board")
def board():return db.board()
@app.get("/api/mentions")
def mentions():
    """Real, current link targets for interactive task/category/action references in chat."""
    tasks=[t for t in db.list_threads() if not t.get("archived_at")]
    actions=db.query("""SELECT e.id,e.thread_id,e.body,e.done,e.due_at,e.revisit_at
        FROM entries e JOIN threads t ON t.id=e.thread_id
        WHERE e.kind='action' AND t.archived_at IS NULL""")
    return {"categories":sorted({name for t in tasks for name in db.category_names(t)}),
            "tasks":[{"id":t["id"],"title":t["title"],"categories":t["categories"]} for t in tasks],
            "actions":actions}

@app.get("/api/threads")
def threads(q:str=""):return db.list_threads(q)
@app.get("/api/overview")
def overview():return db.overview()
@app.post("/api/threads",status_code=201)
def create(data:Thread):
    try:return db.create(data.title,data.summary,data.categories)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
@app.get("/api/threads/{id}")
def get(id:str):return found(db.get(id))
@app.patch("/api/threads/{id}")
def change(id:str,data:Change):
    fields=data.model_dump(exclude_unset=True)
    for field in ("revisit_at","due_at","next_occurrence"):
        if fields.get(field):fields[field]=fields[field].isoformat()
    try:return found(db.update(id,fields))
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
@app.get("/api/threads/{id}/due-action")
def thread_due_action(id:str):
    """Preview the configured task action; never invokes paid AI."""
    return db.report_for_task(id)

@app.get("/api/archived")
def archived(q:str=""):return db.archived_threads(q)

@app.post("/api/threads/{id}/archive")
def archive(id:str):return db.archive_thread(id,True)

@app.post("/api/threads/{id}/restore")
def restore(id:str):return db.archive_thread(id,False)

@app.delete("/api/threads/{id}")
def delete(id:str):return {"deleted":db.delete(id)}
@app.post("/api/threads/{id}/entries",status_code=201)
def add(id:str,data:Entry):return found(db.add(id,data.kind,data.body))
@app.patch("/api/actions/{id}")
def change_action(id:str,data:ActionChange):
    fields=data.model_dump(exclude_unset=True)
    for field in ("due_at","revisit_at"):
        if fields.get(field):fields[field]=fields[field].isoformat()
    try:return found(db.update_action(id,fields))
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
@app.patch("/api/entries/{id}")
def done(id:str,data:Done):return found(db.toggle(id,data.done))
@app.post("/api/threads/{id}/links")
def link(id:str,data:Relation):
    if not db.link(id,data.other_id):raise HTTPException(404,"Thread not found")
    return db.get(id)

@app.post("/api/reflect")
def reflection(data:Ask):
    try:return reflect(data.question)
    except ValueError as exc:raise HTTPException(502,str(exc)) from exc

class Message(BaseModel):
    text:str=Field(min_length=1,max_length=50000)
class Provider(BaseModel):
    base_url:str
    model:str
    api_key:str|None=None
    clear_key:bool=False

@app.get("/api/settings")
def settings():return ai.public_config()

@app.get('/api/preferences')
def preferences():return db.preferences()

@app.post('/api/preferences')
def save_preferences(data:dict):
    try:return db.set_preferences(data)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None

@app.get('/preferences.js')
def preferences_script():return FileResponse(Path(__file__).with_name('preferences.js'),media_type='application/javascript')

@app.post("/api/settings")
def settings_save(data:Provider):
    try:return ai.save(data.base_url,data.model,data.api_key,data.clear_key)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None

class ModelConnection(BaseModel):
    base_url:str|None=None
    api_key:str|None=None

@app.post('/api/settings/models')
def settings_models(data:ModelConnection):
    try:return ai.models(data.base_url,data.api_key)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None

@app.get('/provider-models.js')
def provider_models_script():return FileResponse(Path(__file__).with_name('provider-models.js'),media_type='application/javascript')

@app.get("/api/conversation")
def history():return db.conversation()

@app.post("/api/chat")
def chat(data:Message):
    message=data.text.strip()
    if not message:raise HTTPException(422,"Message required")
    try:
        from .snapshot_intent import respond as snapshot_respond
        result=snapshot_respond(message) or (commands.execute(message) if message.startswith("/") else ai.chat(message))
    except ValueError as exc:raise HTTPException(502,str(exc)) from exc
    db.remember("user",message)
    db.remember("assistant",result["answer"])
    return {"answer":result["answer"],"answer_html":render(result["answer"]),"actions":result.get("actions",[]),"history":db.conversation()}

@app.get("/api/backup")
def backup():
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    from tempfile import NamedTemporaryFile
    import sqlite3
    import os
    file=NamedTemporaryFile(prefix="tether-chat-backup-",suffix=".sqlite3",delete=False)
    file.close()
    try:
        with sqlite3.connect(db.path()) as src, sqlite3.connect(file.name) as dest:src.backup(dest)
    except Exception:
        os.unlink(file.name)
        raise
    return FileResponse(file.name,filename="tether-chat-"+__import__("tether.workspaces",fromlist=["current"]).current()+"-backup.sqlite3",media_type="application/octet-stream",
                        background=BackgroundTask(os.unlink,file.name))

@app.get("/api/portable")
def portable_backup():
    from .portable import export_data
    import json
    return Response(json.dumps(export_data(),ensure_ascii=False),media_type="application/json",
                    headers={"Content-Disposition":"attachment; filename=tether-portable-backup.json",
                             "Cache-Control":"no-store"})

class LocationSearch(BaseModel):
    query:str=Field(min_length=1,max_length=500)
class LocationChoice(BaseModel):
    result_id:str=Field(min_length=1,max_length=200)
@app.post('/api/locations/{id}/search')
def location_search(id:str,data:LocationSearch):
    from .locations import search
    try:return search(id,data.query)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
@app.post('/api/locations/{id}/save')
def location_save(id:str,data:LocationChoice):
    from .locations import save
    try:return save(id,data.result_id)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
@app.get('/locations.js')
def location_script():return FileResponse(Path(__file__).with_name('locations.js'),media_type='application/javascript')

@app.get("/api/conversation/rendered")
def rendered_history():
    return [{"id":row["id"],"role":row["role"],"body":row["body"],"html":render(row["body"]) if row["role"]=="assistant" else None,"created_at":row["created_at"]} for row in db.conversation()]

@app.get("/api/commands")
def command_reference():return commands.COMMANDS
@app.get("/api/brief")
def brief():return {"text":db.daily_brief(),"html":render(db.daily_brief())}

@app.get("/api/attention")
def attention(force:bool=False):
    from .attention import items
    return items(force)

class ActivityInput(BaseModel):
    body:str=Field(min_length=1,max_length=10000)
    kind:Literal["progress","feedback","decision","blocker","milestone","other"]="progress"
    occurred_at:datetime|None=None

class StorageLocation(BaseModel):
    path:str=Field(min_length=1,max_length=2048)
    mode:Literal["move","existing"]="move"

@app.post("/api/threads/{id}/activity",status_code=201)
def add_activity(id:str,data:ActivityInput):
    try:
        result=db.record_activity(id,data.body,data.kind,data.occurred_at.isoformat() if data.occurred_at else None)
        return found(result)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None

@app.get("/api/activity/report")
def report(period:Literal["week","month","quarter","year"]="week",anchor:datetime|None=None):
    try:return db.activity_report(period,anchor.isoformat() if anchor else None)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None

@app.get("/api/storage")
def storage_info():return storage.info()

@app.post("/api/storage")
def stage_storage(data:StorageLocation):
    try:return storage.stage(data.path,data.mode)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None

@app.post("/api/storage/choose-folder")
def select_storage_folder():
    try:return storage.choose_folder()
    except ValueError as exc:raise HTTPException(503,str(exc)) from None

class Occurrence(BaseModel):
    description:str="Completed recurring occurrence"
@app.post("/api/threads/{id}/complete-occurrence")
def complete_recurring(id:str,data:Occurrence):
    try:return db.complete_occurrence(id,data.description)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
@app.get("/api/recurring")
def recurring():return {"due":db.recurring_due(),"all":[t for t in db.list_threads() if t.get("recurrence")]}

@app.post("/api/chat/stream")
def chat_stream(data:Message):
    """NDJSON status stream; tool names only, never tool arguments or secrets."""
    import json,queue,threading
    from fastapi.responses import StreamingResponse
    message=data.text.strip()
    if not message:raise HTTPException(422,"Message required")
    from contextvars import copy_context
    request_context=copy_context()
    def events():
        q=queue.Queue()
        def worker():
            try:
                from .snapshot_intent import respond as snapshot_respond
                result=snapshot_respond(message)
                if result is None:
                    if message.startswith("/"):
                        result=commands.execute(message)
                        if result is None:raise ValueError("Unknown command. Type /help.")
                    else:
                        result=ai.chat(message,progress=lambda value:q.put({"type":"status","message":value}))
                db.remember("user",message)
                db.remember("assistant",result["answer"])
                q.put({"type":"done","answer":result["answer"],"answer_html":render(result["answer"]),"snapshot":result.get("snapshot")})
            except Exception as exc:
                # Do not send raw provider exceptions or traceback to clients.
                q.put({"type":"error","message":str(exc) if isinstance(exc,ValueError) else "Assistant request failed. Check tether-chat server logs."})
            finally:q.put(None)
        threading.Thread(target=request_context.run,args=(worker,),daemon=True).start()
        while True:
            item=q.get()
            if item is None:break
            yield json.dumps(item,ensure_ascii=False)+"\n"
    return StreamingResponse(events(),media_type="application/x-ndjson",headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})

@app.post("/api/settings/test")
def test_ai_connection():
    try:
        response=ai.request([{"role":"user","content":"Respond with OK."}],tools=False)
        if not response.get("choices"):raise ValueError("Provider returned no response")
        return {"ok":True,"message":"Connection successful"}
    except ValueError as exc:raise HTTPException(502,str(exc)) from None


@app.get("/chat.js")
def chat_script():return FileResponse(Path(__file__).with_name("chat.js"),media_type="application/javascript")

@app.get("/action-notes.js")
def action_notes_script():return FileResponse(Path(__file__).with_name("action-notes.js"),media_type="application/javascript")

@app.get("/voice.js")
def voice_script():return FileResponse(Path(__file__).with_name("voice.js"),media_type="application/javascript")

@app.get("/speech.mjs")
def speech_script():return FileResponse(Path(__file__).with_name("speech.mjs"),media_type="application/javascript")

@app.post("/api/voice/transcribe")
def retired_voice_transcribe():
    raise HTTPException(410,"Voice input now runs on this device. Reload tether to update the microphone.")

from .chat_api import router as chat_router
app.include_router(chat_router)

@app.get('/drive-sharing')
def drive_sharing_page():return desktop_screen('drive-sharing.html')

@app.get('/drive-sync-core.mjs')
@app.get('/drive-sync-service.mjs')
@app.get('/drive-journals.mjs')
@app.get('/drive-setup.mjs')
@app.get('/drive-sharing.mjs')
async def drive_sync_asset(request:__import__('fastapi').Request):
    return FileResponse(Path(__file__).with_name(request.url.path.rsplit('/',1)[-1]),media_type='text/javascript')

@app.get('/api/drive-sync/local')
def drive_local_snapshot():
    from . import drive_sync
    try:return drive_sync.snapshot()
    except drive_sync.SyncError as exc:raise HTTPException(exc.status,str(exc))

@app.post('/api/drive-sync/local')
def drive_local_apply(body:dict,request:__import__('fastapi').Request):
    if request.headers.get('origin') != str(request.base_url).rstrip('/'):raise HTTPException(403,'Use the local Home sharing page')
    from . import drive_sync
    try:return drive_sync.apply(body.get('expected'),body.get('records'),body.get('metadata'),body.get('expected_revision'))
    except drive_sync.SyncError as exc:raise HTTPException(exc.status,str(exc))

@app.post('/api/drive-sync/open-browser')
def drive_open_browser(request:__import__('fastapi').Request):
    if request.headers.get('origin') != str(request.base_url).rstrip('/'):raise HTTPException(403,'Use the local Home sharing page')
    from .workspaces import current
    if current()!='home':raise HTTPException(403,'Drive sharing is available only in Home')
    import webbrowser
    from .ports import web_port
    webbrowser.open('http://localhost:'+str(web_port())+'/drive-sharing?workspace=home&external=1')
    return {'ok':True}

@app.get('/drive-config.json')
def drive_public_config():return FileResponse(Path(__file__).with_name('drive-config.json'),media_type='application/json',headers={'Cache-Control':'no-store'})
