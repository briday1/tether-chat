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
    assert "dateButton.onclick=()=>selectDate(iso)" in page
    assert "onfocus=" not in page
    assert "pointerenter" not in page
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
    assert "more.onclick=()=>selectDate(iso)" in page
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


def test_display_clean_layout_starts_on_today_not_saved_anchor():
    page = (ROOT / 'tether/display.html').read_text()
    script = (ROOT / 'tether/display.js').read_text()
    for removed in ['display-quick', 'display-footer', 'display-date', 'display-density']:
        assert f'id="{removed}"' not in page
    assert 'saved.anchor' not in script
    assert 'saved.followingToday' not in script
    assert 'id="display-clock-date"' in page
    assert 'id="display-clock-time"' in page
    assert "+' - '+" not in script
    assert "replace(/\\s/g,'')" not in script
    assert script.index('refresh(true); // First frame') < script.index("fetch('/api/preferences')")


def test_display_back_forward_cache_keeps_refresh_and_resets_today():
    script = (ROOT / 'tether/display.js').read_text()
    snapshot = (ROOT / 'tether/snapshot.html').read_text()
    assert "if(!event.persisted){clearInterval(timer)" in script
    assert "if(event.persisted){followingToday=true;refresh(true)" in script
    assert "if(!event.persisted){clearInterval(refreshTimer)" in snapshot
    assert "window.addEventListener('pageshow'" in snapshot


def test_display_settings_uses_same_svg_as_other_views():
    import re
    pages = [(ROOT / 'tether' / name).read_text(encoding='utf-8') for name in ['display.html', 'index.html', 'board.html']]
    icons = [re.search(r'id="(?:display-settings|navsettings)"[^>]*>(<svg.*?</svg>)', page).group(1) for page in pages]
    assert len(set(icons)) == 1

def test_task_detail_reload_and_pending_panel_requests_are_guarded():
    snapshot = (ROOT / 'tether/snapshot.html').read_text(encoding='utf-8')
    assert "delete state.tetherSnapshotDetail;history.replaceState" in snapshot
    assert "if(request!==selectionRevision||detail.open)return" in snapshot
    assert "queueMicrotask(()=>{if(!detail.open&&!detailClosing)load()})" in snapshot

def test_task_details_escape_is_handled_in_embedded_document():
    snapshot = (ROOT / 'tether/snapshot.html').read_text(encoding='utf-8')
    assert "if(event.key==='Escape'&&detail.open)" in snapshot
    assert "event.stopPropagation();closeDetail()" in snapshot

def test_dashboard_task_history_is_owned_by_display_not_nested_snapshot():
    snapshot = (ROOT / 'tether/snapshot.html').read_text(encoding='utf-8')
    assert "const parentOwnsDetail=parent!==window&&params.get('layout')==='display'" in snapshot
    assert "if(parentOwnsDetail&&push){parent.postMessage" in snapshot
    assert "type:'tether:snapshot-detail-request',action:'open',task:t" in snapshot
    assert "type:'tether:snapshot-detail-request',action:'close'" in snapshot
    assert "if(parentOwnsDetail)return;if(history.state?.tetherSnapshotDetail)" in snapshot
    assert "if(event.data?.type==='tether:snapshot-detail-close'){dismissDetail();detailClosing=false}" in snapshot


def test_calendar_return_is_automatic_without_helper_copy():
    page = (ROOT / 'tether/snapshot.html').read_text(encoding='utf-8')
    assert 'date-panel-hint' not in page
    assert 'Returns to Today after 15 seconds' not in page
    assert 'function scheduleReturn()' in page and '15000' in page


def test_main_settings_gear_matches_borderless_display():
    for name in ['index.html', 'board.html']:
        page = (ROOT / 'tether' / name).read_text(encoding='utf-8')
        assert 'border:0;border-radius:0;background:none;cursor:pointer}.settings-gear' in page
        assert '.settings-gear:focus-visible{outline:2px solid var(--accent)' in page
        assert 'class="settings-gear" aria-label="Settings" title="Settings"' in page


def test_dashboard_cell_packing_is_scoped_and_observable():
    page=(ROOT/'tether/snapshot.html').read_text()
    assert "if(dashboard&&month){cell.displayRecords=records" in page
    assert "records.slice(0,3)" in page  # Chat month keeps abstract markers.
    assert "requestAnimationFrame(()=>{packingFrame=0;packDisplayCells()})" in page
    assert "if(cell.packingKey===key)continue" in page
    assert "cell.dataset.totalCount=records.length" in page
    assert "cell.dataset.visibleCount=plan.visible" in page
    assert "cell.dataset.hiddenCount=plan.more" in page
    assert "display-item-title" in page and "display-item-context" in page
