"""Windows desktop entry point: start tether-chat only when needed, then open an app window."""
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

def log(message):
    path=Path.home()/".tend"/"desktop-launch.log"
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as f:f.write(message+"\n")

def port():
    from .ports import web_port
    return web_port()

def healthy():
    from .ports import compatible
    return compatible(port())

def open_app():
    url=f"http://127.0.0.1:{port()}/"
    paths=[]
    for root in (os.environ.get("PROGRAMFILES(X86)",""),os.environ.get("PROGRAMFILES",""),os.environ.get("LOCALAPPDATA","")):
        if root:
            paths.extend([str(Path(root)/"Microsoft"/"Edge"/"Application"/"msedge.exe"),
                          str(Path(root)/"Google"/"Chrome"/"Application"/"chrome.exe")])
    for executable in paths:
        if Path(executable).is_file():
            subprocess.Popen([executable,"--app="+url],close_fds=True)
            return
    webbrowser.open(url)

def show_error(message):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,str(message),"tether. launcher",0x10)
    except Exception:
        pass

def main():
    import ctypes
    create_mutex=ctypes.windll.kernel32.CreateMutexW
    create_mutex.restype=ctypes.c_void_p
    create_mutex.argtypes=(ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p)
    mutex=create_mutex(None,False,"Local\\tether-chatDesktopTray")
    if not mutex:raise RuntimeError("Could not initialize desktop launcher")
    if ctypes.windll.kernel32.GetLastError()==183:
        # A tray instance already exists; just reopen its application window.
        for _ in range(40):
            if healthy():break
            time.sleep(.25)
        if healthy():open_app()
        else:show_error("tether-chat is still starting or unavailable. Check the tray and server.log.")
        ctypes.windll.kernel32.CloseHandle(mutex)
        return
    server=None
    try:
        server=start_and_open()
        run_tray(server)
    finally:
        ctypes.windll.kernel32.CloseHandle(mutex)

def start_and_open(open_window=True):
    from . import ports
    reuse=ports.configure(log=log)
    if not reuse:
        # Run the console Python interpreter with its console creation suppressed.
        # The supervisor prints progress; pythonw has no stdout and can crash on print().
        py=os.environ.get("TEND_SERVICE_PYTHON",sys.executable)
        if py.lower().endswith("pythonw.exe"):
            py=py[:-len("pythonw.exe")]+"python.exe"
        flags=getattr(subprocess,"CREATE_NO_WINDOW",0)|getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)
        env=os.environ.copy()
        env["TEND_NO_BROWSER"]="1"
        logs=Path.home()/".tend"/"server.log"
        logs.parent.mkdir(parents=True,exist_ok=True)
        with logs.open("ab") as output:
            child=subprocess.Popen([py,"-m","tend.cli"],env=env,creationflags=flags,
                             stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
                             close_fds=True)
        for _ in range(120):
            if healthy():break
            if child.poll() is not None:
                raise RuntimeError("tether-chat server process exited. Check ~/.tend/server.log")
            time.sleep(.25)
        else:
            log("tether-chat server failed to become ready; see server.log")
            raise RuntimeError("tether-chat did not start; see ~/.tend/server.log")
    ports.remember()
    if open_window:open_app()
    return child if 'child' in locals() else None

def run_tray(server):
    """Remain in the system tray after the app window closes."""
    import io
    import pystray
    from PIL import Image
    from .windows_icon import raster
    tray_icon=Image.open(io.BytesIO(raster(256))).convert("RGBA")
    def reopen(icon,item):
        if not healthy():
            show_error("tether-chat's web server is unavailable. Exit tether and start it again from the desktop shortcut.")
        else:
            open_app()
    def quit_tend(icon,item):
        icon.stop()
        if server is None or server.poll() is not None:
            return
        try:
            import psutil
            parent=psutil.Process(server.pid)
            children=parent.children(recursive=True)
            try:parent.terminate()
            except psutil.Error:pass
            for proc in children:
                try:proc.terminate()
                except psutil.Error:pass
            psutil.wait_procs(children,timeout=3)
            for proc in children:
                try:
                    if proc.is_running():proc.kill()
                except psutil.Error:pass
        except Exception as exc:
            log("Unable to stop services cleanly: "+repr(exc))
    menu=pystray.Menu(
        pystray.MenuItem("Open tether",reopen,default=True),
        pystray.MenuItem("Exit tether" if server else "Exit tether tray",quit_tend),
    )
    icon=pystray.Icon("tend",tray_icon,"tether.",menu)
    icon.run()

if __name__=="__main__":
    try:main()
    except Exception as exc:
        log(type(exc).__name__+": "+str(exc))
        show_error(str(exc)+"\n\nSee %USERPROFILE%\\.tend\\desktop-launch.log")
        raise
