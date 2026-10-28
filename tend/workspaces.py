"""Local Work/Home datasets. A workspace is organization, not an access boundary."""
from contextvars import ContextVar
from contextlib import contextmanager

_workspace = ContextVar('tether_workspace', default='work')

def current():
    return _workspace.get()

def normalize(value):
    if value not in ('work', 'home'):
        raise ValueError('Choose Work or Home')
    return value

@contextmanager
def use(value):
    token = _workspace.set(normalize(value))
    try:
        yield
    finally:
        _workspace.reset(token)

def database_path(base):
    if current() == 'work':return base
    import os
    from pathlib import Path
    from .storage import load
    saved=load().get('home') if not os.environ.get('TEND_DB') else None
    return Path(saved).expanduser() if saved else base.with_name(base.stem + '.home' + base.suffix)

def guidance():
    if current() == 'home':
        return 'You are in Home mode. Focus on personal chores, appointments, classes, grocery lists, and everyday plans. Do not introduce work status reports or meetings unless the user asks. Only this Home workspace is available.'
    return 'You are in Work mode. Only this Work workspace is available. Keep personal Home tasks separate.'
