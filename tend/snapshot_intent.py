"""Resolve natural-language snapshot requests without involving the AI provider."""
import re
from datetime import date, timedelta
from calendar import monthrange
from urllib.parse import urlencode
from .snapshots import snapshot

def _month_offset(today, offset):
    index=today.year*12+today.month-1+offset
    year,month=divmod(index,12)
    return date(year,month+1,1),date(year,month+1,monthrange(year,month+1)[1])

def resolve(message, today=None):
    text=message.strip().lower()
    text=re.sub(r"^/snapshot\s+(week|month)\s*$",r"/snapshot this \1",text)
    text=re.sub(r"^/snapshot\s+day\s*$","/snapshot today",text)
    if not (re.search(r"(?<!\w)(snapshot|snapshots)(?!\w)",text) or
            re.search(r"\b(calendar (?:report|view|summary)|visual (?:task |activity )?(?:report|summary))\b",text)):
        return None
    today=today or date.today()
    explicit=re.search(r"(\d{4}-\d{2}-\d{2})\s+(?:to|through|until|–|—)\s+(\d{4}-\d{2}-\d{2})",text)
    if explicit:
        start,end=map(date.fromisoformat,explicit.groups())
    elif re.search(r"\b(yesterday|tomorrow|today)\b",text):
        shift=-1 if "yesterday" in text else 1 if "tomorrow" in text else 0
        start=end=today+timedelta(days=shift)
    elif re.search(r"\b(last|previous|this|current|next)\s+(week|month)\b",text):
        match=re.search(r"\b(last|previous|this|current|next)\s+(week|month)\b",text)
        offset={"last":-1,"previous":-1,"this":0,"current":0,"next":1}[match[1]]
        if match[2]=="week":
            start=today-timedelta(days=today.weekday())+timedelta(weeks=offset)
            end=start+timedelta(days=6)
        else:start,end=_month_offset(today,offset)
    elif m:=re.search(r"\b(next|past|last)\s+(\d{1,3})\s+(days?|weeks?)\b",text):
        count=int(m[2])*(7 if m[3].startswith("week") else 1)
        if count>366:raise ValueError("Snapshots support at most 366 days")
        if m[1] in ("past","last"):end=today;start=today-timedelta(days=count-1)
        else:start=today;end=today+timedelta(days=count-1)
    elif m:=re.search(r"\b(\d{4}-\d{2}-\d{2})\b",text):
        start=end=date.fromisoformat(m[1])
    else:
        start=today-timedelta(days=today.weekday())
        end=start+timedelta(days=6)
    if end<start or (end-start).days>365:raise ValueError("Snapshot date range must be 1–366 days")
    return start.isoformat(),end.isoformat()

def respond(message,today=None):
    dates=resolve(message,today)
    if dates is None:return None
    start,end=dates
    snapshot(start,end)  # Validate and keep errors deterministic, without a provider request.
    p=urlencode({"start":start,"end":end})
    link="/snapshots?"+p
    return {"answer":f"[Calendar · {start} — {end}]({link})",
            "snapshot":{"start":start,"end":end,"url":link}}
