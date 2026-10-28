"""Start tether-chat's local browser and HTTP MCP servers with one command."""
import os
from . import environment
import subprocess
import sys
import time
import webbrowser
from urllib.request import urlopen
from urllib.error import URLError
from . import store
from . import storage
from pathlib import Path

def main():
    import argparse
    parser=argparse.ArgumentParser(prog="tether-chat",description="tether-chat local task assistant")
    sub=parser.add_subparsers(dest="command")
    serve=sub.add_parser("serve",help="Start browser and MCP services")
    for target in (parser,serve):
        target.add_argument("--host",default="127.0.0.1")
        target.add_argument("--port",type=int)
        target.add_argument("--mcp-port",type=int)
        target.add_argument("--no-browser",action="store_true")
    desktop=sub.add_parser("desktop",help="Install desktop launcher")
    desktop.add_argument("action",choices=["install"])
    desktop.add_argument("--destination",help="Shortcut directory (defaults to Desktop)")
    export=sub.add_parser("export",help="Export a portable JSON backup for the browser edition")
    export.add_argument("--output",required=True,help="New JSON file to create (existing files are never overwritten)")
    args=parser.parse_args()
    if args.command=="export":
        import json
        from .portable import export_data
        destination=Path(args.output).expanduser()
        data=export_data()
        with destination.open('x',encoding='utf-8') as output:
            json.dump(data,output,ensure_ascii=False,indent=2)
            output.write('\n')
        print("Portable tether backup:",destination)
        return
    if args.command=="desktop":
        from .desktop_install import install
        print("tether-chat shortcut:",install(args.destination))
        return
    if args.host not in ("127.0.0.1","localhost","::1"):
        parser.error("tether-chat is local-only; bind to 127.0.0.1 or localhost.")
    if args.port is not None and not 1<=args.port<=65535:parser.error("Invalid --port")
    if args.mcp_port is not None and not 1<=args.mcp_port<=65535:parser.error("Invalid --mcp-port")
    if args.port is not None:os.environ["TETHER_WEB_PORT"]=str(args.port)
    if args.mcp_port is not None:os.environ["TETHER_MCP_PORT"]=str(args.mcp_port)
    if args.no_browser:os.environ["TETHER_NO_BROWSER"]="1"
    # Recover automatically from a stale server or another program using either port.
    from . import ports
    if ports.configure():
        if environment.get("TETHER_NO_BROWSER")!="1":
            webbrowser.open(f"http://127.0.0.1:{ports.web_port()}/")
        print("tether-chat is already running; reused existing web server.",flush=True)
        return
    store.init()
    storage.activate_pending()
    store.init()
    env=environment.snapshot()
    web_host="127.0.0.1"
    web_port=int(env.get("TETHER_WEB_PORT","8765"))
    mcp_port=int(env.get("TETHER_MCP_PORT","8766"))
    if web_port==mcp_port: raise SystemExit("Web and MCP ports must differ")
    commands=[
        [sys.executable,"-m","uvicorn","tether.app:app","--host",web_host,"--port",str(web_port)],
        [sys.executable,"-m","tether.mcp_server","--http"],
        [sys.executable,"-m","tether.notifications"]
    ]
    children=[]
    restart_history={}
    service_names=("web","mcp","notifications")
    # On Windows, child python.exe processes otherwise create their own console.
    flags=getattr(subprocess,"CREATE_NO_WINDOW",0) if os.name=="nt" else 0
    log_path=Path.home()/".tend"/"services.log"
    log_path.parent.mkdir(parents=True,exist_ok=True)
    log_offset=log_path.stat().st_size if log_path.exists() else 0
    try:
        for command in commands:
            with log_path.open("ab") as output:
                children.append(subprocess.Popen(command,env=env,creationflags=flags,
                    stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
                    close_fds=True,cwd=str(Path(__file__).resolve().parent.parent)))
        url=f"http://{web_host}:{web_port}"
        # Wait for a valid response instead of opening an unavailable page.
        deadline=time.monotonic()+20
        ready=False
        while time.monotonic()<deadline:
            for index,child in enumerate(children):
                if child.poll() is not None:
                    details=log_path.read_bytes()[log_offset:][-2500:].decode('utf-8',errors='replace').strip()
                    raise RuntimeError(f"tether-chat {service_names[index]} service exited (code {child.returncode}).\n{details or 'No service output was recorded.'}")
            try:
                ready=ports.compatible(web_port) and ports.listening(mcp_port)
                if ready:break
            except (URLError,OSError,TimeoutError):pass
            if not ready:time.sleep(.2)
        if not ready:raise RuntimeError("tether-chat did not become ready on "+url)
        ports.remember()
        print(f"tether-chat browser: {url}",flush=True)
        print(f"tether-chat MCP: http://127.0.0.1:{mcp_port}/mcp",flush=True)
        print(f"Local database: {store.path()}",flush=True)
        print("Press Ctrl+C to stop tether-chat when running in a terminal.",flush=True)
        if env.get("TETHER_NO_BROWSER")!="1":
            webbrowser.open(url)
        while True:
            for index,child in enumerate(children):
                exit_code=child.poll()
                if exit_code is None:
                    continue
                name=service_names[index]
                now=time.monotonic()
                times=[t for t in restart_history.get(name,[]) if now-t<120]
                if len(times)>=3:
                    raise RuntimeError(f"tether-chat {name} service repeatedly exited (last code {exit_code}); see {log_path}")
                times.append(now)
                restart_history[name]=times
                print(f"tether-chat {name} service exited (code {exit_code}); restarting ({len(times)}/3 within 2 minutes)",flush=True)
                with log_path.open("ab") as output:
                    children[index]=subprocess.Popen(commands[index],env=env,creationflags=flags,
                        stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
                        close_fds=True,cwd=str(Path(__file__).resolve().parent.parent))
            if storage.load().get("pending"):
                print("Switching tether-chat database; restarting local services...",flush=True)
                for child in children:
                    if child.poll() is None:child.terminate()
                for child in children:
                    try:child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                children.clear()
                try:
                    storage.activate_pending()
                except Exception as exc:
                    print("Database switch failed; retaining existing database:",str(exc),flush=True)
                    # Clear the pending switch to avoid repeatedly interrupting running services.
                    c=storage.load();c.pop("pending",None);c.pop("pending_mode",None);storage._write(c)
                store.init()
                for command in commands:
                    with log_path.open("ab") as output:
                        children.append(subprocess.Popen(command,env=env,creationflags=flags,
                            stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
                            close_fds=True,cwd=str(Path(__file__).resolve().parent.parent)))
                deadline=time.monotonic()+20
                while time.monotonic()<deadline:
                    if any(child.poll() is not None for child in children):
                        raise RuntimeError("tether-chat restart failed")
                    try:
                        with urlopen(url,timeout=.8) as response:
                            if response.status==200:break
                    except (URLError,OSError,TimeoutError):
                        time.sleep(.2)
                else:raise RuntimeError("tether-chat web server did not restart")
                print("tether-chat database active:",store.path(),flush=True)
            time.sleep(.4)
    except KeyboardInterrupt:
        pass
    finally:
        # Stop each service's descendants before the direct process. On Windows
        # venv Python may spawn a second base-interpreter process per service.
        from .shutdown import stop_child
        for child in children:
            try:
                stop_child(child,log=lambda message:print(message,flush=True))
            except Exception as exc:
                print("tether-chat shutdown warning:",str(exc),flush=True)

if __name__=="__main__":main()
