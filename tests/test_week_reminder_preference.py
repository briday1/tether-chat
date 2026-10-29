from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from tether.decisions import resolve_reminder, reminder_intent, preferences


def test_beginning_of_week_reminder_defaults_and_explicit_day():
    now = datetime(2026, 10, 28, 15, tzinfo=timezone.utc)
    for day in range(7):
        saved = {'week_start': day}
        assert preferences(saved)['week_start'] == day
        value = resolve_reminder('beginning of next week', saved, now)
        assert (datetime.fromisoformat(value).weekday() + 1) % 7 == day
        assert resolve_reminder('next week on Tuesday', saved, now) == '2026-11-03T09:00:00+00:00'
        assert resolve_reminder('2026-11-05', saved, now) == '2026-11-05T09:00:00+00:00'
        explicit = reminder_intent('Remind me next week on 2026-11-05 at 3pm')
        assert resolve_reminder(explicit, saved, now) == '2026-11-05T15:00:00+00:00'
        phrase = reminder_intent('Remind me next week on Tuesday at 3pm')
        assert resolve_reminder(phrase, saved, now) == '2026-11-03T15:00:00+00:00'


def test_preferred_week_reminder_uses_local_day_and_dst():
    now = datetime(2026, 10, 31, 23, 30, tzinfo=ZoneInfo('America/New_York'))
    assert resolve_reminder('beginning of next week', {'week_start': 0}, now) == '2026-11-01T14:00:00+00:00'
    assert resolve_reminder('beginning of next week', {'week_start': 1}, now) == '2026-11-02T14:00:00+00:00'
