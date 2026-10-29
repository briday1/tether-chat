"""Deterministic tether-chat calendar snapshot aggregation (no AI calls)."""
from collections import Counter, defaultdict
import json
from datetime import date, timedelta,datetime
from . import store as db
from .recurrence import occurrences

def snapshot(start: str, end: str, category: str = "") -> dict:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < first or (last-first).days > 365:
        raise ValueError("Date range must be ordered and at most 366 days")
    threads = db.with_categories(db.query("SELECT id,title,summary,category,state,due_at,revisit_at,next_occurrence,recurrence,recurrence_end,recurrence_anchor,recurrence_timezone,created_at,archived_at FROM threads WHERE archived_at IS NULL"))
    events = db.with_categories(db.query("SELECT a.thread_id,a.kind,a.body,a.occurred_at,t.title,t.category FROM activity a JOIN threads t ON t.id=a.thread_id WHERE substr(a.occurred_at,1,10)>=? AND substr(a.occurred_at,1,10)<=? ORDER BY a.occurred_at,a.id", (start,end)),"thread_id")
    if category:
        threads = [t for t in threads if category in t["categories"]]
        events = [e for e in events if category in e["categories"]]
    # Only user-confirmed saved places are displayed; no lookup is performed.
    locations = {}
    if db.query("SELECT name FROM sqlite_master WHERE type='table' AND name='location_requests'"):
        for row in db.query("SELECT value FROM location_requests ORDER BY rowid"):
            saved = json.loads(row['value'])
            if saved.get('status') == 'saved' and saved.get('selected', {}).get('address'):
                locations[saved['task_id']] = saved['selected']['address']
    notes = {}
    for row in db.query("SELECT thread_id,body FROM entries WHERE kind!='action' ORDER BY created_at,id"):
        notes[row['thread_id']] = row['body']
    action_notes = {}
    for row in db.query("SELECT action_id,body FROM action_notes ORDER BY created_at,id"):
        action_notes[row['action_id']] = row['body']
    byday = defaultdict(lambda: {"tasks":[], "activity":[]})
    def calendar_day(value):
        if not value:return None
        if len(value)==10:return value
        try:return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone().date().isoformat()
        except (ValueError,TypeError):return None
    def add(t,action=None):
        record=action or t;dates={}
        for field,kind in [('due_at','deadline'),('revisit_at','reminder')]:
            day=calendar_day(record.get(field))
            if day and start<=day<=end:dates.setdefault(day,[]).append(kind)
        projected = {}
        if not action and not t.get('recurrence'):
            day = calendar_day(t.get('next_occurrence'))
            if day and start <= day <= end:dates.setdefault(day, []).append('reminder')
        if not action:
            for occurrence in occurrences(t, start, end):
                day = calendar_day(occurrence)
                dates.setdefault(day, []).append('recurrence')
                projected[day] = occurrence
        for day,kinds in dates.items():
            kinds=list(dict.fromkeys(kinds));done=bool(action and action.get('done'))
            byday[day]['tasks'].append({'id':t['id'],'task_id':t['id'],'action_id':action['id'] if action else None,
              'title':action['body'] if action else t['title'],'task_title':t['title'],'category':t['category'],'categories':t['categories'],
              'state':'settled' if done else t['state'],'date':day,'schedule_kinds':kinds,
              'summary':t.get('summary','')[:300],'location':locations.get(t['id'],''),
              'note_preview':(action_notes.get(action['id'],'') if action else notes.get(t['id'],''))[:240],
              'due_at':record.get('due_at'),'revisit_at':record.get('revisit_at'),
              'next_occurrence':projected.get(day) or (t.get('next_occurrence') if not action and not t.get('recurrence') else None), 'occurrence_at':projected.get(day),
              'recurrence':None if action else t.get('recurrence'), 'recurrence_end':None if action else t.get('recurrence_end'),
              'is_projection':bool(projected.get(day) and projected[day] != t.get('next_occurrence')),
              'schedule_label':' · '.join(label for label in ['Due' if 'deadline' in kinds else '', 'Reminder' if 'reminder' in kinds else '', 'Repeats' if 'recurrence' in kinds else '', 'Done' if done else ''] if label),
              'href':'/board#action/'+t['id']+'/'+action['id'] if action else '/board#task/'+t['id']})
    for t in threads:add(t)
    parents={t['id']:t for t in threads}
    for action in db.query("SELECT id,thread_id,body,done,due_at,revisit_at FROM entries WHERE kind='action'"):
        if action['thread_id'] in parents:add(parents[action['thread_id']],action)
    for e in events:
        day=e["occurred_at"][:10]
        byday[day]["activity"].append({"thread_id":e["thread_id"],"title":e["title"],"category":e["category"],"categories":e["categories"],"kind":e["kind"],"body":e["body"],"occurred_at":e["occurred_at"]})
    days=[]
    cursor=first
    while cursor<=last:
        iso=cursor.isoformat()
        items=byday[iso]
        items["tasks"].sort(key=lambda t:(t["category"].casefold(),t["title"].casefold(),t["id"]))
        days.append({"date":iso,**items})
        cursor+=timedelta(days=1)
    due=[t for d in days for t in d["tasks"]]
    categories=Counter(c for t in due for c in t["categories"])
    kinds=Counter(e["kind"] for e in events)
    return {"start":start,"end":end,"category":category or None,"week_start":db.preferences()['week_start'],"days":days,
            "insights":{"scheduled_due":len(due),"activity_events":len(events),
                        "active_days":sum(bool(d["activity"]) for d in days),
                        "categories":dict(sorted(categories.items())),
                        "activity_types":dict(sorted(kinds.items()))},
            "notice":"Task and action reminders and deadlines use local calendar dates. Activity uses recorded UTC dates. No historical state changes are inferred."}
