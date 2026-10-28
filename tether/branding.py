"""One identity and artwork for the desktop window, tray and notifications."""
from pathlib import Path
import sys

APP_ID = 'tether-chat.Desktop'
APP_NAME = 'tether-chat'


def icon_path():
    from .windows_icon import create_icon, raster
    folder = Path.home()/'.tend'/'icons'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/('tether-chat-horizon-v3.ico' if sys.platform == 'win32' else 'tether-chat-horizon-v3.png')
    if not path.exists():
        if sys.platform == 'win32':
            create_icon(path)
        else:
            path.write_bytes(raster(256))
    return path


def set_process_identity():
    if sys.platform == 'win32':
        import ctypes
        function = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        function.argtypes = [ctypes.c_wchar_p]
        function.restype = ctypes.c_long
        result = function(APP_ID)
        if result < 0:
            raise OSError('Windows could not set the tether-chat application identity')
