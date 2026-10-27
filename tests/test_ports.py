"""A busy web or MCP port must not prevent launch or stop an unrelated process."""
import json
import os
import socket
import pytest
from tend import ports


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.delenv('TEND_WEB_PORT',raising=False);monkeypatch.delenv('TEND_MCP_PORT',raising=False)
    monkeypatch.setattr(ports,'_state_path',lambda:tmp_path/'launch-ports.json')
    return tmp_path


def listening():
    server=socket.socket();server.bind(('127.0.0.1',0));server.listen();return server


def test_occupied_web_and_mcp_select_free_ports_and_remember_for_next_launch(isolated,monkeypatch):
    with listening() as web,listening() as mcp:
        old_web,old_mcp=web.getsockname()[1],mcp.getsockname()[1]
        monkeypatch.setenv('TEND_WEB_PORT',str(old_web));monkeypatch.setenv('TEND_MCP_PORT',str(old_mcp))
        monkeypatch.setattr(ports,'compatible',lambda port:False)
        messages=[];assert ports.configure(messages.append) is False
        assert ports.web_port() not in (old_web,old_mcp)
        assert ports.mcp_port() not in (old_web,old_mcp,ports.web_port())
        for value in (ports.web_port(),ports.mcp_port()):
            with socket.socket() as available:available.bind(('127.0.0.1',value))
        # The original listeners were not killed or closed.
        assert web.getsockname()[1]==old_web and mcp.getsockname()[1]==old_mcp
        assert messages
        chosen=ports.web_port(),ports.mcp_port();ports.remember()
    monkeypatch.delenv('TEND_WEB_PORT');monkeypatch.delenv('TEND_MCP_PORT')
    assert (ports.web_port(),ports.mcp_port())==chosen


def test_compatible_server_is_reused_without_requiring_its_ports_to_be_free(isolated,monkeypatch):
    monkeypatch.setattr(ports,'compatible',lambda port:port==8765)
    monkeypatch.setattr(ports,'_choose',lambda *args:pytest.fail('Must reuse the running instance'))
    assert ports.configure() is True
    assert ports.web_port()==8765


def test_busy_mcp_alone_is_resolved_and_explicit_free_ports_are_retained(isolated,monkeypatch):
    with listening() as mcp:
        monkeypatch.setattr(ports,'compatible',lambda port:False)
        monkeypatch.setenv('TEND_MCP_PORT',str(mcp.getsockname()[1]))
        assert ports.configure(lambda message:None) is False
        assert ports.mcp_port()!=mcp.getsockname()[1]
        previous=ports.web_port(),ports.mcp_port()
        assert ports.configure() is False
        assert (ports.web_port(),ports.mcp_port())==previous


def test_corrupt_saved_ports_fall_back_and_explicit_environment_takes_precedence(isolated,monkeypatch):
    path=ports._state_path()
    for value in ['not json',json.dumps({'web':-1,'mcp':8766}),json.dumps({'web':True,'mcp':8766}),json.dumps({'web':8000,'mcp':8000})]:
        path.write_text(value);assert ports.web_port()==8765
    path.write_text(json.dumps({'web':9000,'mcp':9001}))
    monkeypatch.setenv('TEND_WEB_PORT','9876');assert ports.web_port()==9876


def test_equal_service_ports_are_rejected_before_starting(isolated,monkeypatch):
    monkeypatch.setenv('TEND_WEB_PORT','9000');monkeypatch.setenv('TEND_MCP_PORT','9000')
    with pytest.raises(ValueError,match='differ'):ports.configure()


def test_real_launcher_starts_with_both_requested_ports_occupied_and_next_launch_reuses_it(tmp_path):
    """Exercise the real supervisor and services, including the Windows process tree."""
    import subprocess
    import sys
    import time
    from urllib.request import urlopen
    from tend.shutdown import stop_process_tree
    state=tmp_path/'launch-ports.json';output=tmp_path/'launch.log'
    program="from pathlib import Path;from tend import ports,cli;ports._state_path=lambda:Path("+repr(str(state))+");cli.main()"
    with listening() as web,listening() as mcp:
        environment=os.environ.copy()
        environment.update(TEND_DB=str(tmp_path/'tasks.sqlite3'),TEND_WEB_PORT=str(web.getsockname()[1]),
                           TEND_MCP_PORT=str(mcp.getsockname()[1]),TEND_NO_BROWSER='1')
        with output.open('wb') as log:
            child=subprocess.Popen([sys.executable,'-c',program],env=environment,stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+30
            while not state.is_file():
                if child.poll() is not None:pytest.fail(output.read_text())
                if time.monotonic()>deadline:pytest.fail('Launch did not recover: '+output.read_text())
                time.sleep(.1)
            actual=json.loads(state.read_text())
            with urlopen(f"http://127.0.0.1:{actual['web']}/api/health",timeout=3) as response:
                assert json.load(response)['version']==ports.__version__
            with socket.socket() as probe:assert probe.connect_ex(('127.0.0.1',actual['mcp']))==0
            again=environment.copy();again.pop('TEND_WEB_PORT');again.pop('TEND_MCP_PORT')
            reused=subprocess.run([sys.executable,'-c',program],env=again,capture_output=True,text=True,timeout=10)
            assert reused.returncode==0 and 'reused existing' in reused.stdout,reused.stderr
            assert 'Previous service ports were busy' in output.read_text()
        finally:
            stop_process_tree(child.pid,log=lambda message:None);child.wait(timeout=10)
