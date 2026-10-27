"""Deterministic slash commands; no AI API call necessary."""
from . import notes, store

COMMANDS=[
    {"name":"/help","description":"Show available commands"},
    {"name":"/brief","description":"Today's overview: due, active, waiting"},
    {"name":"/due","description":"Things ready to revisit"},
    {"name":"/waiting","description":"Things blocked or waiting"},
    {"name":"/recent","description":"Recently updated things"},
]
def execute(message):
    command=message.strip().split(maxsplit=1)[0].lower()
    if command=="/help":return {"answer":"# tether-chat commands\n"+ "\n".join("- **"+c["name"]+"** — "+c["description"] for c in COMMANDS)}
    if command=="/brief":return {"answer":store.daily_brief()}
    if command in ("/due","/waiting","/recent"):
        rows=store.overview()["due" if command=="/due" else "waiting"] if command!="/recent" else [t for t in store.list_threads() if not t.get('archived_at')]
        title={'/due':'Bring to attention','/waiting':'Waiting on','/recent':'Recently updated'}[command]
        return {"answer":notes.task_note(title,rows,store.get,limit=15 if command=='/recent' else 25)}
    return None
