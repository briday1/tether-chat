"""Choose local service ports and remember a successful desktop launch."""
import json
import os
from pathlib import Path
import socket
import tempfile
from http.client import HTTPException
from urllib.request import build_opener,ProxyHandler

# A local health probe must never travel through a system/VPN HTTP proxy.
urlopen=build_opener(ProxyHandler({})).open
from . import __version__


def _state_path():return Path.home()/'.tend'/'launch-ports.json'


def _valid(value):return isinstance(value,int) and not isinstance(value,bool) and 1<=value<=65535


def _saved():
    try:
        value=json.loads(_state_path().read_text(encoding='utf-8'))
        if isinstance(value,dict) and all(_valid(value.get(key)) for key in ('web','mcp')) and value['web']!=value['mcp']:return value
    except (OSError,ValueError):pass
    return {'web':8765,'mcp':8766}


def web_port():return int(os.environ.get('TEND_WEB_PORT') or _saved()['web'])


def mcp_port():return int(os.environ.get('TEND_MCP_PORT') or _saved()['mcp'])


def compatible(port):
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/health',timeout=.75) as response:
            data=json.load(response)
            return (response.status==200 and isinstance(data,dict) and data.get('app')=='tend'
                    and data.get('brand')=='tether-chat' and data.get('version')==__version__
                    and data.get('streaming_chat') is True and data.get('tool_runner')=='unbounded-v2')
    except (OSError,ValueError,HTTPException):return False


def listening(port):
    with socket.socket() as probe:
        probe.settimeout(.5)
        return probe.connect_ex(('127.0.0.1',port))==0


def _available(port):
    try:
        with socket.socket() as probe:probe.bind(('127.0.0.1',port))
        return True
    except OSError:return False


def _choose(preferred,excluded):
    for candidate in range(preferred,min(preferred+128,65536)):
        if candidate not in excluded and _available(candidate):return candidate
    # Let the OS choose if the preferred neighborhood is full.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));candidate=probe.getsockname()[1]
    if candidate in excluded:return _choose(10240,excluded)
    return candidate


def configure(log=print):
    """Return True when reusing a compatible server; otherwise choose free ports."""
    web,mcp=web_port(),mcp_port()
    if not _valid(web) or not _valid(mcp):raise ValueError('Service ports must be between 1 and 65535')
    if web==mcp:raise ValueError('Web and MCP ports must differ')
    if compatible(web) and listening(mcp):
        os.environ['TEND_WEB_PORT']=str(web);os.environ['TEND_MCP_PORT']=str(mcp)
        return True
    chosen_web=_choose(web,{mcp});chosen_mcp=_choose(mcp,{chosen_web})
    os.environ['TEND_WEB_PORT']=str(chosen_web);os.environ['TEND_MCP_PORT']=str(chosen_mcp)
    if (chosen_web,chosen_mcp)!=(web,mcp):
        log(f'Previous service ports were busy; using web {chosen_web} and MCP {chosen_mcp}. Existing processes were left running.')
    return False


def remember():
    """Only save after services are ready; replace atomically across launches."""
    path=_state_path();path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as output:
            temporary=Path(output.name);json.dump({'web':web_port(),'mcp':mcp_port()},output);output.write('\n')
        os.replace(temporary,path)
    finally:
        if temporary:temporary.unlink(missing_ok=True)
