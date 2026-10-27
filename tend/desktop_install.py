"""Create an OS-native tether-chat launcher after pip installation."""
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys

def desktop_folder():
    home=Path.home()
    if sys.platform=="win32":
        try:
            import ctypes
            from ctypes import wintypes
            # FOLDERID_Desktop = {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
            from uuid import UUID
            class GUID(ctypes.Structure):
                _fields_=[("Data1",ctypes.c_uint32),("Data2",ctypes.c_uint16),("Data3",ctypes.c_uint16),("Data4",ctypes.c_ubyte*8)]
            u=UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641")
            g=GUID(u.time_low,u.time_mid,u.time_hi_version,(ctypes.c_ubyte*8).from_buffer_copy(u.bytes[8:]))
            result=ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g),0,None,ctypes.byref(result))==0:
                target=Path(result.value)
                ctypes.windll.ole32.CoTaskMemFree(result)
                return target
        except Exception:
            pass
    if sys.platform.startswith("linux"):
        try:
            result=subprocess.run(["xdg-user-dir","DESKTOP"],capture_output=True,text=True,timeout=3)
            if result.returncode==0 and result.stdout.strip():
                return Path(result.stdout.strip()).expanduser()
        except (OSError,subprocess.TimeoutExpired):
            pass
    return home/"Desktop"

def install(destination=None):
    folder=Path(destination).expanduser().resolve() if destination else desktop_folder()
    if not folder.is_dir():
        if destination:raise ValueError("Destination must be an existing directory: "+str(folder))
        folder.mkdir(parents=True,exist_ok=True)
    python=str(Path(sys.executable).absolute())
    if sys.platform=="win32":
        windowed=Path(python).with_name("pythonw.exe")
        if windowed.is_file():python=str(windowed)
        # A real Windows shortcut, rather than a shortcut to a repo-specific exe.
        from .windows_icon import create_icon
        icon_file=Path.home()/".tend"/"tether-chat-desktop-v3.ico"
        create_icon(icon_file)
        path=folder/"tether-chat.lnk"
        escape=lambda s:s.replace("'","''")
        script=("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('"+escape(str(path))+"');"
                +"$s.TargetPath='"+escape(python)+"';"
                +"$s.Arguments='-m tend.native';"
                +"$s.WorkingDirectory='"+escape(str(Path.home()))+"';"
                +"$s.Description='Open tether-chat';$s.IconLocation='"+escape(str(icon_file))+"';$s.Save()")
        subprocess.run(["powershell","-NoProfile","-NonInteractive","-Command",script],check=True)
    elif sys.platform=="darwin":
        path=folder/"tether-chat.command"
        path.write_text("#!/bin/sh\nexec "+shlex.quote(python)+" -m tend.native\n",encoding="utf-8")
        path.chmod(0o755)
    else:
        path=folder/"tether-chat.desktop"
        exec_line='"'+python.replace("\\","\\\\").replace('"','\\"').replace("%","%%")+'" -m tend.native'
        path.write_text("[Desktop Entry]\nType=Application\nName=tether-chat\nComment=Local task assistant\nExec="+exec_line+"\nTerminal=false\nCategories=Office;Utility;\n",encoding="utf-8")
        path.chmod(0o755)
    return path
