"""Persist database location and stage safe migrations for next tether-chat restart."""
import json, os, sqlite3
from pathlib import Path

def config_path():
    return Path.home()/".tend"/"storage.json"

def load():
    try:return json.loads(config_path().read_text(encoding="utf-8"))
    except (FileNotFoundError,ValueError):return {}

def active_path():
    return Path(load().get("active",str(Path.home()/".tend"/"tend.sqlite3"))).expanduser().resolve()

def info():
    c=load()
    return {"current":str(active_path()),"pending":c.get("pending"),"pending_mode":c.get("pending_mode","move"),"environment_override":bool(os.environ.get("TEND_DB"))}

def _write(config):
    f=config_path();f.parent.mkdir(parents=True,exist_ok=True)
    import tempfile
    fd,temp=tempfile.mkstemp(prefix=".storage-",dir=f.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:json.dump(config,stream)
        os.replace(temp,f)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def stage(target,mode="move"):
    from .workspaces import current
    if current()!='work':raise ValueError("Manage database locations from Work; Home remains in its own local file")
    if mode not in ("move","existing"):raise ValueError("Choose Move current or Use existing")
    if os.environ.get("TEND_DB"):raise ValueError("Remove TEND_DB environment override before relocating the database")
    path=Path(target).expanduser().resolve()
    if mode=="move" and path.is_dir():path=path/active_path().name
    if path.suffix.lower() not in (".sqlite3",".sqlite",".db"):raise ValueError("Use a .sqlite3, .sqlite, or .db filename")
    if path==active_path():raise ValueError("Choose a different destination")
    if mode=="move" and path.exists():raise ValueError("Destination exists; choose an unused file")
    if mode=="existing":validate_existing(path)
    if not path.parent.is_dir():raise ValueError("Destination folder must already exist")
    if mode=="move" and not os.access(path.parent,os.W_OK):raise ValueError("Destination folder is not writable")
    config=load();config["pending"]=str(path);config["pending_mode"]=mode;_write(config)
    return info()

def activate_pending():
    """Called only by the single-command launcher before any server is started."""
    config=load();target=config.get("pending")
    if not target:return
    destination=Path(target)
    source=active_path()
    # Keep Home attached to its original file when changing the Work location.
    home=source.with_name(source.stem+'.home'+source.suffix)
    if home.exists():config.setdefault('home',str(home))
    if config.get("pending_mode")=="existing":
        validate_existing(destination)
        config["active"]=str(destination)
        config.pop("pending",None);config.pop("pending_mode",None)
        _write(config)
        return
    if destination.exists():raise RuntimeError("Pending database destination already exists; migration cancelled")
    destination.parent.mkdir(parents=True,exist_ok=True)
    try:
        with sqlite3.connect(source) as src,sqlite3.connect(destination) as dst:
            src.backup(dst)
            ok=dst.execute("PRAGMA integrity_check").fetchone()[0]
            if ok!="ok":raise RuntimeError("Database verification failed")
        config["active"]=str(destination);config.pop("pending",None);config.pop("pending_mode",None);_write(config)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    # Source is retained as a backup, never deleted.

def validate_existing(path):
    if not path.is_file():raise ValueError("Existing database file not found")
    try:
        # Open read-only: never create, initialize or alter a candidate database.
        with sqlite3.connect(path.as_uri()+"?mode=ro",uri=True) as c:
            if c.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise ValueError("Database integrity check failed")
            tables={row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"threads","entries","relations","conversation"}.issubset(tables):
                raise ValueError("File is not a recognized tether-chat database")
    except sqlite3.DatabaseError:
        raise ValueError("File is not a readable tether-chat SQLite database") from None

def choose_folder():
    """Open a native OS folder picker on the same machine running tether-chat."""
    import subprocess,sys
    script=(
        "import tkinter as tk\n"
        "from tkinter import filedialog\n"
        "root=tk.Tk()\n"
        "root.withdraw()\n"
        "root.attributes('-topmost', True)\n"
        "try:\n"
        "    print(filedialog.askdirectory(parent=root,title='Select tether-chat database folder',mustexist=True) or '')\n"
        "finally:\n"
        "    root.destroy()\n"
    )
    try:
        result=subprocess.run([sys.executable,"-c",script],text=True,capture_output=True,timeout=180,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise ValueError("Could not open native folder picker") from None
    if result.returncode:
        raise ValueError("Native folder picker unavailable on this computer")
    folder=result.stdout.strip().splitlines()
    return {"folder":folder[-1] if folder else None}
