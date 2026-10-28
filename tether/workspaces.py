"""Installed tether-chat is Work-only; household data lives in tether-home."""
from contextlib import contextmanager

def current():
    return 'work'

def normalize(value):
    if value != 'work':
        raise ValueError('tether-chat supports Work only. Open tether-home for household tasks.')
    return 'work'

@contextmanager
def use(value):
    normalize(value)
    yield

def database_path(base):
    # Existing Work database path is unchanged. Legacy Home files are left intact
    # but are never opened or uploaded by the installed application.
    return base

def guidance():
    return 'You are using tether-chat for Work tasks. Only this Work database is available. Household tasks belong in the separate tether-home browser app.'
