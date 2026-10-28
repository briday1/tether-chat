"""Structural guards for the shared, no-provider Display screen and calendar."""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]


def test_display_uses_shared_calendar_and_workspace():
    page=(ROOT/'tether/display.html').read_text()
    script=(ROOT/'tether/display.js').read_text()
    assert 'src="/workspace.js"' in page
    assert 'data-display-nav' in page
    assert 'id="display-calendar"' in page
    assert "'/snapshots?'" in script
    assert "workspace:mode()" in script
    assert "window.tetherWorkspaceURL(href)" in script
    assert '60000' in script
    assert 'chat/completions' not in script and "'/api/chat'" not in script
    assert 'followingToday' in script and 'localStorage.setItem(storageKey()' in script


def test_calendar_has_fixed_cells_and_accessible_detail_paths():
    page=(ROOT/'tether/snapshot.html').read_text()
    assert 'height:108px;overflow:hidden' in page
    assert '.day-items{min-height:0;overflow:hidden' in page
    assert "dateButton.onclick=dateButton.onfocus" in page
    assert 'dialog.showModal()' not in page
    assert 'id="date-panel"' in page and '15000' in page
    assert "records.slice(0,3)" in page
    assert "$('#date-panel-items').addEventListener('scroll'" in page
    assert 'id="png"' not in page and 'id="svg"' not in page
    assert "event.source!==parent||event.origin!==location.origin" in page.replace(" ", "")
    assert "if(signature===lastSignature){renderPanel();return}" in page


def test_browser_build_has_display_assets(tmp_path):
    spec=importlib.util.spec_from_file_location('build_web',ROOT/'scripts/build_web.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    output=builder.build(tmp_path/'browser','/tether-chat/')
    for name in ['display.html','display.js','display.css']:
        assert (output/name).is_file()
    page=(output/'display.html').read_text()
    assert '/tether-chat/bridge.js' in page
    assert '/tether-chat/display.js' in page
    script=(output/'display.js').read_text()
    assert "'/tether-chat/snapshots.html?'" in script
    assert "'/tether-chat/board.html#'" in script


def test_display_dashboard_fits_without_changing_chat_snapshots():
    css=(ROOT/'tether/display.css').read_text()
    script=(ROOT/'tether/display.js').read_text()
    page=(ROOT/'tether/snapshot.html').read_text()
    assert '100dvh' in css and 'minmax(0,1fr)' in css
    assert "layout:'display'" in script
    assert "(compact||weekends)?7:5" in page
    assert 'grid-template-rows:repeat(var(--rows,1),minmax(0,1fr))' in page
    assert "more.onclick=more.onfocus=()=>selectDate(iso)" in page
    assert "id=\"view-week\"" not in (ROOT/'tether/display.html').read_text()
    assert "frame.style.height=" not in script
    assert 'Reconnect Google in Settings' in script
    assert 'Household updates delayed' in script
    assert "service.state()" in script and "service.start(" not in script
    assert 'display-sidebar' in css and 'display-backdrop' in css


def test_display_header_navigation_and_local_date_clock():
    page = (ROOT / 'tether/display.html').read_text()
    script = (ROOT / 'tether/display.js').read_text()
    snapshot = (ROOT / 'tether/snapshot.html').read_text()
    for control in ['display-previous', 'display-next', 'display-today']:
        assert f'id="{control}"' in page
    assert 'aria-label="Previous month"' in page
    assert 'aria-label="Next month"' in page
    assert "weekday:'long',month:'long',day:'numeric'" in script
    assert "hour12:true" in script
    assert "tether:snapshot-today" in script and "tether:snapshot-today" in snapshot
    assert "setAttribute('aria-current','date')" in snapshot
