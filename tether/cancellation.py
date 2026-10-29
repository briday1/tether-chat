"""Cooperative cancellation scoped to one durable chat job, not its UI."""
import asyncio
from contextvars import ContextVar
from contextlib import contextmanager
import threading

class Interrupted(Exception):
    """Explicitly stopped, never a provider failure or retry instruction."""

_current = ContextVar('chat_cancellation', default=None)

class Token:
    def __init__(self, checkpoint=None):
        self.event = threading.Event()
        self.gate = threading.RLock()
        self.hooks = set()
        self.checkpoint = checkpoint

    def check(self):
        if self.event.is_set():
            raise Interrupted('Stopped. Completed changes were kept.')

    def cancel(self):
        # Signal before waiting for an already-started tool to finish. No later
        # tool can enter the gate; cancellation never pretends to undo that tool.
        self.event.set()
        with self.gate:
            for hook in tuple(self.hooks):
                hook()

    @contextmanager
    def use(self):
        context = _current.set(self)
        try:
            self.check()
            yield
        finally:
            _current.reset(context)

    def perform(self, operation, metadata):
        with self.gate:
            self.check()
            try:
                result = operation()
            except Exception:
                if self.checkpoint:
                    self.checkpoint({**metadata, 'outcome': 'unknown', 'result': {'error': 'Operation failed; some changes may have been saved. Inspect current data before attempting again.'}})
                raise
            if self.checkpoint:
                self.checkpoint({**metadata, 'result': result})
            return result


def check():
    token = _current.get()
    if token: token.check()


def perform(operation, metadata):
    token = _current.get()
    return token.perform(operation, metadata) if token else operation()


def sleep(seconds):
    import time
    token = _current.get()
    if token:
        if token.event.wait(seconds): token.check()
    else: time.sleep(seconds)


def run(coroutine):
    """Run cancellable async network I/O from the serialized worker thread."""
    token = _current.get()
    async def wrapped():
        task = asyncio.current_task()
        loop = asyncio.get_running_loop()
        hook = lambda: loop.call_soon_threadsafe(task.cancel)
        if token:
            with token.gate:
                token.hooks.add(hook)
                if token.event.is_set(): task.cancel()
        try:
            return await coroutine
        except asyncio.CancelledError:
            raise Interrupted('Stopped. Completed changes were kept.') from None
        finally:
            if token:
                with token.gate: token.hooks.discard(hook)
    return asyncio.run(wrapped())
