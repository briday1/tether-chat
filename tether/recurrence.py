"""Bounded, read-only recurrence arithmetic shared by calendar and completion.

An anchor preserves month-end intent. Named zones preserve wall time through DST;
legacy offsets remain fixed. Missing DST times roll forward, overlaps choose fold 0.
"""
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re

FREQUENCIES = ('daily', 'weekly', 'monthly', 'quarterly', 'yearly')


def parse(value, zone=None):
    if not isinstance(value, str):
        raise ValueError('Invalid recurrence date')
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return datetime.combine(date.fromisoformat(value), time(), timezone.utc), True
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})', value):
        raise ValueError('Recurrence must include timezone or be a calendar date')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('Invalid recurrence date') from None
    if result.tzinfo is None:
        raise ValueError('Recurrence must include timezone or be a calendar date')
    if zone:
        result = result.astimezone(ZoneInfo(zone))
    return result, False


def validate_zone(zone):
    if zone is not None:
        if not isinstance(zone, str) or not zone or len(zone) > 100:
            raise ValueError('Invalid recurrence timezone')
        try:
            ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Invalid recurrence timezone') from None


def validate_end(value):
    if value is not None:
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError('Repeat end must be a YYYY-MM-DD date')
        date.fromisoformat(value)


def at(anchor, frequency, index, zone=None):
    """Return one occurrence directly; index is relative to the original anchor."""
    dt, date_only = parse(anchor, zone)
    if index == 0:
        return dt.date().isoformat() if date_only else dt.isoformat()
    if frequency in ('daily', 'weekly'):
        candidate = dt + timedelta(days=index * (7 if frequency == 'weekly' else 1))
    else:
        step = {'monthly': 1, 'quarterly': 3, 'yearly': 12}.get(frequency)
        if step is None:
            raise ValueError('Invalid recurrence')
        ordinal = dt.year * 12 + dt.month - 1 + index * step
        year, month = divmod(ordinal, 12)
        candidate = dt.replace(year=year, month=month + 1,
                               day=min(dt.day, monthrange(year, month + 1)[1]), fold=0)
    if zone and not date_only:
        # Resolve spring-forward nonexistent wall times to the corresponding later time.
        candidate = candidate.astimezone(timezone.utc).astimezone(ZoneInfo(zone))
    return candidate.date().isoformat() if date_only else candidate.isoformat()


def index_near(anchor, frequency, target, zone=None):
    dt, _ = parse(anchor, zone)
    target = target.astimezone(dt.tzinfo)
    if frequency in ('daily', 'weekly'):
        return max(0, (target.date() - dt.date()).days // (7 if frequency == 'weekly' else 1) - 2)
    months = (target.year - dt.year) * 12 + target.month - dt.month
    return max(0, months // {'monthly': 1, 'quarterly': 3, 'yearly': 12}[frequency] - 2)


def ended(value, end, zone=None):
    return bool(end and parse(value, zone)[0].date().isoformat() > end)


def occurrences(task, first, last):
    """Yield occurrences in the viewer-local inclusive date range, without writes."""
    current, frequency = task.get('next_occurrence'), task.get('recurrence')
    if not current or frequency not in FREQUENCIES or task.get('state') == 'settled' or task.get('archived_at'):
        return
    zone = task.get('recurrence_timezone')
    anchor = task.get('recurrence_anchor') or current
    current_dt, date_only = parse(current, zone)
    lower = datetime.combine(date.fromisoformat(first), time()).astimezone()
    # A +/- 2 index cushion accommodates viewer vs schedule timezone date boundaries.
    index = index_near(anchor, frequency, lower, zone)
    while True:
        try:
            value = at(anchor, frequency, index, zone)
        except (OverflowError, ValueError):
            return
        candidate, _ = parse(value, zone)
        day = candidate.date().isoformat() if date_only else candidate.astimezone().date().isoformat()
        if day > last or ended(value, task.get('recurrence_end'), zone):
            return
        if candidate.astimezone(timezone.utc) >= current_dt.astimezone(timezone.utc) and day >= first:
            yield value
        index += 1


def next_after(task, now):
    current = task['next_occurrence']
    zone, frequency = task.get('recurrence_timezone'), task['recurrence']
    anchor = task.get('recurrence_anchor') or current
    current_dt, date_only = parse(current, zone)
    instant = datetime.fromisoformat(now.replace('Z', '+00:00'))
    if date_only:
        instant = instant.astimezone().replace(tzinfo=timezone.utc)
    cutoff = max(current_dt.astimezone(timezone.utc), instant.astimezone(timezone.utc))
    index = index_near(anchor, frequency, cutoff, zone)
    while True:
        try:
            value = at(anchor, frequency, index, zone)
        except (OverflowError, ValueError):
            return None
        if ended(value, task.get('recurrence_end'), zone):
            return None
        if parse(value, zone)[0].astimezone(timezone.utc) > cutoff:
            return value
        index += 1


def equivalent(left, right):
    if left == right:return True
    if not left or not right:return False
    try:
        a, ad = parse(left)
        b, bd = parse(right)
        return ad == bd and a == b
    except ValueError:
        return False


def is_due(value, now):
    try:
        dt, date_only = parse(value)
        instant = datetime.fromisoformat(now.replace('Z', '+00:00'))
        return dt.date() <= instant.astimezone().date() if date_only else dt <= instant
    except (ValueError, TypeError):
        return False


def local_day(value):
    """Keep calendar dates literal, otherwise use the viewer-local calendar day."""
    dt,date_only=parse(value)
    return (dt.date() if date_only else dt.astimezone().date()).isoformat()


def deadline_due(value, now):
    """Deadlines are day-granular in the viewer's calendar; reminders are instants."""
    try:
        return local_day(value) <= datetime.fromisoformat(now.replace('Z', '+00:00')).astimezone().date().isoformat()
    except (ValueError, TypeError):
        return False
