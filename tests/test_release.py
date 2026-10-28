"""Regressions for package metadata, branding, action scope and desktop icons."""
from io import BytesIO
from pathlib import Path
import sys
import tomllib
import pytest
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]


def test_exact_public_commands_and_core_pillow():
    project=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']
    assert project['name']=='tether-chat'
    assert set(project['scripts'])=={'tether-chat'}
    assert set(project['gui-scripts'])=={'tether-chat-desktop'}
    assert any(s.lower().startswith('pillow') and ';' not in s for s in project['dependencies'])
    assert not any(s.lower().startswith(('pystray','pywebview')) for s in project['dependencies'])
    from tether import __version__
    assert project['version']==__version__


def test_header_brand_and_shared_drawer_styles():
    for name in ('index.html','board.html'):
        page=(ROOT/'tether'/name).read_text(encoding='utf-8')
        assert '<span class="brand-word">tether<span>.</span></span>' in page
        assert '<span class="brand-word">tend' not in page
    css=(ROOT/'tether/theme.css').read_text(encoding='utf-8')
    assert '.reference-drawer,.action-drawer{position:fixed;' in css
    assert '#board:has(.actions-section){grid-template-columns:' in css
    assert '.bubble.assistant a{color:var(--accent)!important}' in css
    from tether import __version__
    from tether.native import WINDOW_TITLE
    assert WINDOW_TITLE=='tether-chat '+__version__


def test_icons_have_all_dpi_sizes_and_unclipped_alpha(tmp_path):
    from tether.windows_icon import create_icon,raster,ICON_SIZES
    ico=Image.open(create_icon(tmp_path/'mark.ico'))
    assert ico.ico.sizes()=={(size,size) for size in ICON_SIZES}
    for size in ICON_SIZES:
        image=Image.open(BytesIO(raster(size)))
        assert image.size==(size,size)
        left,top,right,bottom=image.getchannel('A').getbbox()
        assert 0<left<right<size and 0<top<bottom<size
        assert image.getpixel((size//2,size//2))[3]>240
    with pytest.raises(ValueError):raster(0)


def test_action_dates_and_completion_do_not_modify_parent_or_siblings(tmp_path,monkeypatch):
    from tether import store
    monkeypatch.setenv('TETHER_DB',str(tmp_path/'db.sqlite3'));store.init()
    task=store.create('Briefing',categories=['Projects'])
    first=store.add(task['id'],'action','Contact review team')
    second=store.add(task['id'],'action','Check the attachment')
    stamp='2030-10-27T09:00:00+00:00'
    store.update_action(first['id'],{'due_at':stamp,'revisit_at':stamp,'done':True})
    current=store.get(task['id'])
    assert current['due_at'] is None and current['revisit_at'] is None
    sibling=next(e for e in current['entries'] if e['id']==second['id'])
    assert sibling['due_at'] is None and sibling['revisit_at'] is None and not sibling['done']


@pytest.mark.skipif(sys.platform!='win32',reason='Real HWND test requires Windows')
def test_windows_assigns_icons_to_actual_window_handle(tmp_path):
    import ctypes
    from types import SimpleNamespace
    from tether import native
    from tether.windows_icon import create_icon
    api=native._user32()
    api.CreateWindowExW.argtypes=[ctypes.c_ulong,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p]
    api.CreateWindowExW.restype=ctypes.c_void_p
    api.DestroyWindow.argtypes=[ctypes.c_void_p]
    hwnd=api.CreateWindowExW(0,'STATIC','tether-chat icon regression',0,0,0,320,200,None,None,None,None)
    assert hwnd
    window=SimpleNamespace(native=SimpleNamespace(Handle=SimpleNamespace(ToInt64=lambda:hwnd)))
    try:
        native._apply_windows_window_icon(window,create_icon(tmp_path/'test.ico'))
        for kind in (0,1):
            handle=api.SendMessageW(hwnd,0x007F,kind,0)
            assert handle and handle==native._ICON_HANDLES[(hwnd,kind)][2]
        count=len(native._ICON_HANDLES)
        native._apply_windows_window_icon(window,tmp_path/'test.ico')
        assert len(native._ICON_HANDLES)==count
    finally:
        api.DestroyWindow(hwnd)
        for key,(_,_,handle) in list(native._ICON_HANDLES.items()):
            if key[0]==hwnd:api.DestroyIcon(handle);del native._ICON_HANDLES[key]
