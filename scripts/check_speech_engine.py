"""Real Vosk/WASM recognition and offline reload, using Vosk's public test recording.

No user microphone, API key, provider, or user task database is used. Run on CI
with Playwright Chromium installed; audio comes from Chrome's fake-device flag.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import hashlib
import os
import re
import sys
import tempfile
import threading
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_web import build

LIBRARY='https://cdn.jsdelivr.net/npm/vosk-browser@0.0.8/dist/vosk.js'
MODEL='https://ccoreilly.github.io/vosk-browser/models/vosk-model-small-en-us-0.15.tar.gz'
AUDIO='https://raw.githubusercontent.com/alphacep/vosk-api/master/python/example/test.wav'


def download(directory,name,url,digest,algorithm='sha256'):
    path=directory/name
    def valid():return path.is_file() and hashlib.new(algorithm,path.read_bytes()).hexdigest()==digest
    if not valid():
        with urlopen(url,timeout=60) as response:data=response.read()
        assert hashlib.new(algorithm,data).hexdigest()==digest,'Speech fixture checksum mismatch: '+name
        path.write_bytes(data)
    return path


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass


def main():
    from playwright.sync_api import sync_playwright,expect
    cache=Path(os.environ.get('TETHER_SPEECH_TEST_CACHE',Path.home()/'.cache/tether-speech-check'));cache.mkdir(parents=True,exist_ok=True)
    library=download(cache,'vosk-0.0.8.js',LIBRARY,'9eac98f1c9477fddee0581648240024a1313baf137539ef25d225a7f45acf9783372851ee8e07fd4188e7c7a8a3967a0','sha384')
    model=download(cache,'en-us-0.15.tar.gz',MODEL,'f0b24bb92a48ca575b6a96500d6b543f0f079c573dfe85bbe16001fc0404e1d8')
    audio=download(cache,'numbers.wav',AUDIO,'dcfea5712c43a43ba7ae8083afb39d36993e5a69c46e88b68aaa72b65cb615bb')
    with tempfile.TemporaryDirectory(prefix='tether-real-speech-') as temporary:
        root=Path(temporary);build(root/'speech-check','/speech-check/')
        server=ThreadingHTTPServer(('127.0.0.1',18771),partial(Quiet,directory=str(root)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(args=['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',
                                                  '--use-file-for-fake-audio-capture='+str(audio.resolve())])
                context=browser.new_context(permissions=['microphone']);requests=[];errors=[]
                context.on('request',lambda request:requests.append((request.method,request.url)))
                context.route(LIBRARY,lambda route:route.fulfill(path=str(library),content_type='application/javascript',headers={'Access-Control-Allow-Origin':'*'}))
                context.route(MODEL,lambda route:route.fulfill(path=str(model),content_type='application/gzip',headers={'Access-Control-Allow-Origin':'*'}))
                page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto('http://127.0.0.1:18771/speech-check/')
                frame=page.frame_locator('#app-frame');field=frame.get_by_label('Message tether')
                field.fill('Keep typed draft.');frame.locator('#voiceInput').click()
                expect(frame.locator('#voiceStatus')).to_contain_text('Listening',timeout=120000)
                expect(field).to_have_value(re.compile(r'^Keep typed draft\. .*\b(one|zero)\b'),timeout=45000)
                # It is still listening while real recognized words are already in the draft.
                expect(frame.locator('#voiceInput')).to_have_class('voice-button listening')
                frame.locator('#voiceInput').click()
                expect(frame.locator('#voiceInput')).to_have_attribute('aria-pressed','false',timeout=10000)
                assert field.input_value().startswith('Keep typed draft. ')
                assert frame.locator('.bubble.user').count()==0
                page.evaluate('async()=>{await navigator.serviceWorker.ready}')
                context.unroute(LIBRARY);context.unroute(MODEL)
                before=len([url for method,url in requests if url.startswith('https:')])
                context.set_offline(True);page.reload()
                frame=page.frame_locator('#app-frame');field=frame.get_by_label('Message tether');field.fill('Offline draft.')
                frame.locator('#voiceInput').click()
                expect(frame.locator('#voiceStatus')).to_contain_text('Listening',timeout=120000)
                expect(field).to_have_value(re.compile(r'^Offline draft\. .*\b(one|zero)\b'),timeout=45000)
                frame.locator('#voiceInput').click()
                expect(frame.locator('#voiceInput')).to_have_attribute('aria-pressed','false',timeout=10000)
                assert len([url for method,url in requests if url.startswith('https:')])==before,'Offline speech tried a network download'
                assert not [url for method,url in requests if method=='POST'],'Voice sent an API request'
                assert frame.locator('.bubble.user').count()==0
                assert not errors,errors
                browser.close()
                print('Real on-device speech: live words, microphone toggle, draft preservation, no API calls, and offline reload passed.')
        finally:server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':main()
