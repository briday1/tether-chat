"""Python-only desktop entry: native Windows window, persistent tray on desktops."""
import ctypes
import io
import os
import sys
import time
from pathlib import Path

from . import __version__
from .branding import APP_NAME

WINDOW_TITLE=APP_NAME+' '+__version__
_ICON_HANDLES={}
_ICON_RESOURCES=[]


def _user32():
    """Declare pointer-sized signatures before touching a 64-bit HWND/HICON."""
    api=ctypes.windll.user32
    api.FindWindowW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p]
    api.FindWindowW.restype=ctypes.c_void_p
    api.ShowWindow.argtypes=[ctypes.c_void_p,ctypes.c_int]
    api.SetForegroundWindow.argtypes=[ctypes.c_void_p]
    api.LoadImageW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_int,ctypes.c_int,ctypes.c_uint]
    api.LoadImageW.restype=ctypes.c_void_p
    api.SendMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
    api.SendMessageW.restype=ctypes.c_ssize_t
    api.DestroyIcon.argtypes=[ctypes.c_void_p]
    if hasattr(api,'GetDpiForWindow'):
        api.GetDpiForWindow.argtypes=[ctypes.c_void_p];api.GetDpiForWindow.restype=ctypes.c_uint
    if hasattr(api,'GetSystemMetricsForDpi'):
        api.GetSystemMetricsForDpi.argtypes=[ctypes.c_int,ctypes.c_uint]
        api.GetSystemMetricsForDpi.restype=ctypes.c_int
    return api


def _existing_window():
    api=_user32();hwnd=api.FindWindowW(None,WINDOW_TITLE)
    if hwnd:api.ShowWindow(hwnd,9);api.SetForegroundWindow(hwnd)
    return bool(hwnd)


def _apply_windows_window_icon(window,icon_file):
    """Use this window's actual handle and current DPI, never a title search."""
    api=_user32()
    hwnd=int(window.native.Handle.ToInt64())
    dpi=api.GetDpiForWindow(hwnd) if hasattr(api,'GetDpiForWindow') else 96
    dpi=dpi or 96
    for kind,xmetric,ymetric,default in ((0,49,50,16),(1,11,12,32)):
        width=api.GetSystemMetricsForDpi(xmetric,dpi) if hasattr(api,'GetSystemMetricsForDpi') else round(default*dpi/96)
        height=api.GetSystemMetricsForDpi(ymetric,dpi) if hasattr(api,'GetSystemMetricsForDpi') else width
        width=width or default;height=height or width
        key=(hwnd,kind)
        previous=_ICON_HANDLES.get(key)
        if previous and previous[:2]==(width,height):continue
        handle=api.LoadImageW(None,str(icon_file),1,width,height,0x10)
        if not handle:raise OSError('Windows could not load the tether-chat icon')
        api.SendMessageW(hwnd,0x0080,kind,handle)
        _ICON_HANDLES[key]=(width,height,handle)
        # Only release handles created by us, never icons owned by WinForms.
        if previous:api.DestroyIcon(previous[2])


def _stop_owned(server):
    if server is not None and server.poll() is None:
        from .shutdown import stop_child
        from .desktop import log
        stop_child(server,log=log)


def _run():
    from . import desktop
    if sys.platform!='win32':
        server=None
        try:
            server=desktop.start_and_open(open_window=True)
            desktop.run_tray(server)
        finally:_stop_owned(server)
        return
    import webview
    import pystray
    webview.settings['ALLOW_DOWNLOADS']=True
    from PIL import Image
    from .windows_icon import raster,create_icon

    from .branding import set_process_identity
    set_process_identity()
    kernel=ctypes.windll.kernel32
    kernel.CreateMutexW.restype=ctypes.c_void_p
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    mutex=kernel.CreateMutexW(None,False,'Local\\tether-chatNativeDesktop-'+__version__)
    if not mutex:raise RuntimeError('Could not create the tether-chat desktop lock')
    if kernel.GetLastError()==183:
        try:
            for _ in range(40):
                if _existing_window():break
                time.sleep(.25)
        finally:kernel.CloseHandle(mutex)
        return

    supervisor=None;tray=None;exiting=False
    try:
        # Keep the uv/pipx environment interpreter, not its resolved base symlink.
        py=Path(sys.executable)
        if getattr(sys,'frozen',False):
            root=py.absolute().parent.parent
            py=root/'.venv'/'Scripts'/'python.exe'
            if not py.is_file():raise RuntimeError('Reinstall the optional native build or use tether-chat-desktop from a Python installation.')
        os.environ['TEND_SERVICE_PYTHON']=str(py)
        icon_file=create_icon(Path.home()/'.tend'/'icons'/'tether-chat-horizon-v3.ico')
        supervisor=desktop.start_and_open(open_window=False)
        window=webview.create_window(WINDOW_TITLE,f'http://127.0.0.1:{desktop.port()}/',
            width=1180,height=780,min_size=(620,450),background_color='#f5f5f5',text_select=True)

        def apply_icons(*_):
            try:_apply_windows_window_icon(window,icon_file)
            except Exception as exc:desktop.log('Window icon: '+repr(exc))

        def before_show(*_):
            # Set the full ICO on WinForms first so its own initialization does not
            # replace our caption icon with python.exe's icon after WM_SETICON.
            try:
                from System.Drawing import Icon
                native_icon=Icon(str(icon_file))
                _ICON_RESOURCES.append(native_icon)
                window.native.Icon=native_icon
                window.native.ShowIcon=True
                if hasattr(window.native,'DpiChanged'):
                    window.native.DpiChanged+=apply_icons
            except Exception as exc:desktop.log('Native icon initialization: '+repr(exc))
            apply_icons()

        def on_close():
            if not exiting:window.hide();return False
        window.events.before_show+=before_show
        window.events.shown+=apply_icons
        window.events.closing+=on_close

        def reopen(icon,item):
            window.show();window.restore();apply_icons()

        def exit_app(icon,item):
            nonlocal exiting
            exiting=True;icon.stop();window.destroy()

        tray=pystray.Icon('tether-chat',Image.open(io.BytesIO(raster(256))).convert('RGBA'),APP_NAME,
            pystray.Menu(pystray.MenuItem('Open tether-chat',reopen,default=True),pystray.MenuItem('Exit tether-chat',exit_app)))
        tray.run_detached()
        webview.start(gui='edgechromium',debug=False,private_mode=False,storage_path=str(Path.home()/'.tend'/'webview'))
    finally:
        if tray:
            try:tray.stop()
            except Exception:pass
        _stop_owned(supervisor)
        api=_user32()
        for _,_,handle in _ICON_HANDLES.values():api.DestroyIcon(handle)
        _ICON_HANDLES.clear()
        for resource in _ICON_RESOURCES:
            try:resource.Dispose()
            except Exception:pass
        _ICON_RESOURCES.clear()
        kernel.CloseHandle(mutex)


def main():
    import argparse
    parser=argparse.ArgumentParser(prog='tether-chat-desktop',description='Launch tether-chat with a persistent system tray.')
    parser.parse_args()
    try:_run()
    except KeyboardInterrupt:pass
    except Exception as exc:
        from .desktop import log,show_error
        message=str(exc)
        if isinstance(exc,ImportError):message+='\nInstall the desktop extra: uv tool install "tether-chat[desktop]"'
        log('Desktop launcher: '+repr(exc));show_error(message+'\n\nSee ~/.tend/desktop-launch.log')
        if sys.stderr:print(message,file=sys.stderr)
        raise SystemExit(1) from exc


if __name__=='__main__':main()
