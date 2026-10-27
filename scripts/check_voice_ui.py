"""Desktop voice UI checks with synthetic audio; no microphone or paid provider is used."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def serve():
    from tend import ai,voice
    from tend.app import app
    import uvicorn
    ai.public_config=lambda:{'base_url':'https://provider.example/v1','model':'test','has_key':True}
    voice.transcribe=lambda *args,**kwargs:{'text':'Recorded voice draft.'}
    uvicorn.run(app,host='127.0.0.1',port=18769,log_level='warning')


def main():
    from playwright.sync_api import sync_playwright
    from voice_ui_checks import MOCKS,check_dictation,check_recording
    with tempfile.TemporaryDirectory(prefix='tether-voice-ui-') as temp:
        environment=os.environ.copy();environment['TEND_DB']=str(Path(temp)/'voice.sqlite3')
        server=subprocess.Popen([sys.executable,__file__,'--serve'],cwd=ROOT,env=environment,stdout=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    with urlopen('http://127.0.0.1:18769/api/health',timeout=1):break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('Voice test server did not start')
            with sync_playwright() as pw:
                browser=pw.chromium.launch();page=browser.new_page();errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)));page.add_init_script(MOCKS)
                page.goto('http://127.0.0.1:18769/')
                check_dictation(page,page);check_recording(page,page)
                assert not errors,errors
                browser.close();print('Desktop voice input: dictation, recording, permission errors, cancellation, draft preservation, and review before sending passed.')
        finally:server.terminate();server.wait(timeout=15)


if __name__=='__main__':
    if '--serve' in sys.argv:serve()
    else:main()
