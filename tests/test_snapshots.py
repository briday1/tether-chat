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
    assert image.width==2200 and 250<image.height<500
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
    # A weekend-only empty range still has a complete Monday–Friday row.
    week=Image.open(io.BytesIO(png('2026-10-26','2026-11-01',scale=1)))
    weekend=Image.open(io.BytesIO(png('2026-10-31','2026-11-01',scale=1)))
    month=Image.open(io.BytesIO(png('2026-10-01','2026-10-31',scale=1)))
    assert weekend.height==week.height<200
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
