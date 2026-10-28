"""Structural guards for the shared, no-provider Display screen and calendar."""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]


def test_display_uses_shared_calendar_and_workspace():
    page=(ROOT/'tend/display.html').read_text()
    script=(ROOT/'tend/display.js').read_text()
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
    page=(ROOT/'tend/snapshot.html').read_text()
    assert '.day{height:136px' in page
    assert '.day-items{min-height:0;overflow:auto' in page
    assert "button.addEventListener('focus'" in page
    assert 'dialog.showModal()' in page
    assert "event.source===parent && event.origin===location.origin" in page
    assert "if(signature===lastSignature)return" in page


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
