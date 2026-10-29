"""Synthetic transport cancellation; no provider credentials or network."""
import asyncio
import threading
import httpx
import pytest
from tether import ai, cancellation

@pytest.mark.parametrize('phase',['connect','read'])
def test_cancel_pending_provider_io_and_no_fixed_timeout(monkeypatch,phase):
    entered=threading.Event();closed=threading.Event();result=[];options=[]
    original=httpx.AsyncClient
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            entered.set()
            await asyncio.Event().wait()
            yield b'never'
        async def aclose(self): closed.set()
    async def handler(request):
        if phase=='connect':
            entered.set()
            try: await asyncio.Event().wait()
            finally: closed.set()
        return httpx.Response(200,stream=Stream())
    def client(**kwargs):
        options.append(kwargs)
        return original(**kwargs,transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx,'AsyncClient',client)
    token=cancellation.Token()
    def worker():
        try:
            with token.use():ai.provider_request('https://synthetic.invalid/v1',{},'synthetic')
        except cancellation.Interrupted: result.append('interrupted')
    thread=threading.Thread(target=worker);thread.start()
    assert entered.wait(2)
    token.cancel();thread.join(2)
    assert not thread.is_alive() and closed.is_set() and result==['interrupted']
    assert options[0]['timeout'] is None and options[0]['follow_redirects'] is False


def test_cancel_backoff_does_not_retry():
    token=cancellation.Token();token.cancel()
    with pytest.raises(cancellation.Interrupted):
        with token.use(): cancellation.sleep(60)


def test_provider_can_run_longer_than_old_22_second_limit(monkeypatch):
    original=httpx.AsyncClient
    async def handler(request):
        await asyncio.sleep(22.1)
        return httpx.Response(200,json={'choices':[{'message':{'content':'Still works'}}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs: original(**kwargs,transport=httpx.MockTransport(handler)))
    assert ai.provider_request('https://synthetic.invalid/v1',{},'synthetic').json()['choices']


def test_tool_stop_waits_for_started_result_and_blocks_next_tool():
    outcomes=[];entered=threading.Event();release=threading.Event();stopped=threading.Event()
    token=cancellation.Token(outcomes.append)
    def operation():
        entered.set(); assert release.wait(2)
        return {'id':'saved'}
    def worker():
        with token.use(): cancellation.perform(operation,{'name':'capture'})
    thread=threading.Thread(target=worker);thread.start();assert entered.wait(1)
    stopper=threading.Thread(target=lambda:(token.cancel(),stopped.set()));stopper.start()
    assert not stopped.wait(.02)
    release.set();thread.join(1);stopper.join(1)
    assert stopped.is_set() and outcomes[0]['result']=={'id':'saved'}
    with pytest.raises(cancellation.Interrupted): token.perform(lambda:pytest.fail('must not run'),{})


def test_unknown_tool_outcome_is_checkpointed_without_retry():
    outcomes=[];token=cancellation.Token(outcomes.append)
    def uncertain(): raise ValueError('failed after write')
    with pytest.raises(ValueError): token.perform(uncertain,{'name':'capture'})
    assert outcomes[0]['outcome']=='unknown'
