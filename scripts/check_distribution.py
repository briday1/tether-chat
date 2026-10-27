"""Check a built wheel outside the source directory, including uv's tool shims."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
wheel=next((ROOT/'dist').glob('tether_chat-*.whl'))
check='''from importlib.metadata import distribution
from importlib.resources import files
from tend.snapshot_export import png,svg
from tend.native import WINDOW_TITLE
from tend import __version__
d=distribution("tether-chat")
names={e.name for e in d.entry_points if e.group in ("console_scripts","gui_scripts")}
assert names=={"tether-chat","tether-chat-desktop"},names
assert d.version==__version__
assert WINDOW_TITLE=="tether."
assert files("tend").joinpath("chat.js").is_file()
assert files("tend").joinpath("notes.js").is_file()
assert files("tend").joinpath("notes.css").is_file()
assert files("tend").joinpath("action-notes.js").is_file()
assert files("tend").joinpath("voice.js").is_file()
assert files("tend").joinpath("updates.js").is_file()
for name in ("index.html","board.html"):
    page=files("tend").joinpath(name).read_text(encoding="utf-8")
    assert '<span class="brand-word">tether<span>.</span></span>' in page
print("Installed wheel:",d.version,"; commands:",sorted(names))
'''
with tempfile.TemporaryDirectory(prefix='tether-chat-wheel-') as temporary:
    root=Path(temporary);envdir=root/'core'
    subprocess.run([sys.executable,'-m','venv',str(envdir)],check=True)
    python=envdir/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check',str(wheel)],check=True,cwd=root)
    subprocess.run([str(python),'-c',check],check=True,cwd=root)
    subprocess.run([str(python),'-m','tend.cli','--help'],check=True,cwd=root)
    uv=shutil.which('uv')
    if uv:
        tools=root/'tools';bin_dir=root/'bin';env=os.environ.copy()
        env.update(UV_TOOL_DIR=str(tools),UV_TOOL_BIN_DIR=str(bin_dir),UV_NO_PROGRESS='1')
        subprocess.run([uv,'tool','install','--python',sys.executable,f'tether-chat[desktop] @ {wheel.as_uri()}'],check=True,cwd=root,env=env)
        names={p.name.removesuffix('.exe') for p in bin_dir.iterdir() if p.is_file()}
        assert names=={'tether-chat','tether-chat-desktop'},names
        print('uv exposed exactly:',', '.join(sorted(names)))
    else:raise SystemExit('uv is required for the isolated desktop installation check')
