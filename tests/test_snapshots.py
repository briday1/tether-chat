"""Snapshot data and PNG export behavior; runs against isolated SQLite."""
import io
from datetime import date, timedelta
from PIL import Image
from tether import store
from tether.snapshots import snapshot
from tether.snapshot_export import png

def test_snapshot_actual_records(tmp_path,monkeypatch):
    monkeypatch.setenv("TETHER_DB",str(tmp_path/"test.sqlite3"))
    store.init()
    t=store.create("Finish interactive snapshots")
    store.update(t["id"],{"category":"Product","due_at":"2026-10-24T12:00:00Z"})
    store.record_activity(t["id"],"Started visualization","progress","2026-10-23T10:00:00Z")
    report=snapshot("2026-10-22","2026-10-25")
    assert report["insights"]["scheduled_due"]==1
    assert report["insights"]["activity_events"]==1
    assert report["insights"]["active_days"]==1
    assert report["days"][2]["tasks"][0]["href"]=="/board#task/"+t["id"]
    assert report["days"][1]["activity"][0]["body"]=="Started visualization"
    assert "historical" in report["notice"].lower()
    result=png("2026-10-22","2026-10-25",theme="ocean",scale=2)
    image=Image.open(io.BytesIO(result))
    assert image.format=="PNG"
    # The explicit range crosses Sunday, so the calendar includes two rows.
    assert image.width==2200 and 450<image.height<600
    assert png("2026-10-22","2026-10-25",theme="ocean",scale=2)==result

def test_range_validation(tmp_path,monkeypatch):
    import pytest
    monkeypatch.setenv("TETHER_DB",str(tmp_path/"test.sqlite3"))
    store.init()
    with pytest.raises(ValueError):
        snapshot("2026-11-01","2026-10-01")
    with pytest.raises(ValueError):
        snapshot("2026-01-01","2028-01-01")
    with pytest.raises(ValueError):
        png("2026-10-01","2026-10-02",theme="invalid")

def test_content_sizing_partial_ranges_and_complete_exports(tmp_path,monkeypatch):
    import xml.etree.ElementTree as ET
    from tether.snapshot_export import svg
    monkeypatch.setenv('TETHER_DB',str(tmp_path/'test.sqlite3'));store.init()
    # A weekend crossing Sunday spans two complete Sunday–Saturday rows.
    week=Image.open(io.BytesIO(png('2026-10-26','2026-11-01',scale=1)))
    weekend=Image.open(io.BytesIO(png('2026-10-31','2026-11-01',scale=1)))
    month=Image.open(io.BytesIO(png('2026-10-01','2026-10-31',scale=1)))
    assert weekend.height==week.height<300
    assert month.height>week.height*2
    for n in range(6):
        task=store.create('Review & approve <draft> '+str(n),categories=['Projects','Product'])
        store.update(task['id'],{'due_at':'2026-10-27T12:00:00Z'})
    full=Image.open(io.BytesIO(png('2026-10-26','2026-11-01',scale=1)))
    assert full.height>week.height
    xml=ET.fromstring(svg('2026-10-26','2026-11-01'))
    labels=[e.text for e in xml.iter() if e.tag.endswith('text')]
    for n in range(6):assert 'Review & approve <draft> '+str(n) in ' '.join(labels)
    assert labels.count('Projects')==labels.count('Product')==6
    # Archived tasks keep their history but stop appearing as current obligations.
    store.archive_thread(task['id'])
    assert snapshot('2026-10-26','2026-11-01')['insights']['scheduled_due']==5

def test_snapshot_context_is_real_and_task_scoped(tmp_path, monkeypatch):
    import json
    monkeypatch.setenv('TETHER_DB', str(tmp_path/'context.sqlite3'))
    store.init()
    t = store.create('Dentist <check>', 'Bring insurance & questions')
    other = store.create('Other task')
    store.update(t['id'], {'due_at':'2026-10-30T18:30:00Z', 'revisit_at':'2026-10-30T16:00:00Z'})
    store.add(t['id'], 'thought', 'Literal <script> note')
    action = store.add(t['id'], 'action', 'Bring form')
    store.update_action(action['id'], {'due_at':'2026-10-30T18:00:00Z'})
    store.add_action_note(action['id'], 'Action-specific note')
    with store.conn() as c:
        c.execute('CREATE TABLE location_requests(id TEXT PRIMARY KEY,value TEXT NOT NULL)')
        for index, row in enumerate([
            {'task_id':t['id'], 'status':'saved', 'selected':{'address':'123 Main Street'}},
            {'task_id':other['id'], 'status':'saved', 'selected':{'address':'Private other place'}},
            {'task_id':t['id'], 'status':'ready', 'selected':{'address':'Unconfirmed place'}},
        ]):
            c.execute('INSERT INTO location_requests VALUES(?,?)', (str(index), json.dumps(row)))
    records = snapshot('2026-10-30', '2026-10-30')['days'][0]['tasks']
    task = next(r for r in records if not r['action_id'])
    item = next(r for r in records if r['action_id'])
    assert task['summary'] == 'Bring insurance & questions'
    assert task['location'] == item['location'] == '123 Main Street'
    assert task['note_preview'] == 'Literal <script> note'
    assert item['note_preview'] == 'Action-specific note'
    assert task['due_at'] == '2026-10-30T18:30:00Z'
    assert task['revisit_at'] == '2026-10-30T16:00:00Z'
    assert item['revisit_at'] is None

def test_snapshot_summary_is_a_preview_but_task_details_are_complete(tmp_path, monkeypatch):
    monkeypatch.setenv('TETHER_DB', str(tmp_path/'preview.sqlite3'))
    store.init()
    text = 'Full task context. ' * 100
    task = store.create('Long details', text)
    store.update(task['id'], {'due_at':'2026-10-30T18:00:00Z'})
    record = snapshot('2026-10-30', '2026-10-30')['days'][0]['tasks'][0]
    assert record['summary'] == text[:300]
    assert store.get(task['id'])['summary'] == text


def test_exports_ignore_reminder_week_preference(tmp_path, monkeypatch):
    from tether.snapshot_export import _layout, svg
    import xml.etree.ElementTree as ET
    monkeypatch.setenv('TETHER_DB', str(tmp_path/'week.sqlite3'));store.init()
    for preference in range(7):
        store.set_preferences({'week_start':preference})
        _,cols,rows,*_=_layout('2026-10-01','2026-10-31',None,'light')
        assert cols==7 and len(rows)==5
        assert rows[0][0]['date']==date(2026,9,27)
        assert rows[-1][-1]['date']==date(2026,10,31)
        labels=[e.text for e in ET.fromstring(svg('2026-11-01','2026-11-07')).iter() if e.tag.endswith('text')]
        assert labels[1:8]==['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
        _,cols,rows,*_=_layout('2026-10-31','2026-11-01',None,'light')
        assert cols==7 and len(rows)==2
        _,cols,rows,*_=_layout('2026-11-01','2026-11-01',None,'light')
        assert cols==1 and len(rows)==1 and rows[0][0]['date']==date(2026,11,1)
