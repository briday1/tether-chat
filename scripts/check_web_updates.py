"""Automatic mobile releases preserve offline data, drafts, active work and editors."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('web_build',ROOT/'scripts/build_web.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
DB="""async action=>{
 const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('tether-chat-web:/tether-chat/');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)});
 return new Promise((resolve,reject)=>{
  const tx=db.transaction('state',action==='read'?'readonly':'readwrite'),store=tx.objectStore('state'),read=store.get('data');let state;
  read.onsuccess=()=>{state=read.result;
   if(action==='busy'){state.jobs.push({id:'update-busy-fixture',status:'running',updated_at:new Date().toISOString()});store.put(state,'data')}
   if(action==='idle'){state.jobs=state.jobs.filter(j=>j.id!=='update-busy-fixture');store.put(state,'data')}
  };
  tx.oncomplete=()=>{db.close();resolve(state)};tx.onerror=()=>{db.close();reject(tx.error)};
 });
}"""


class FreshHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if 'If-Modified-Since' in self.headers:del self.headers['If-Modified-Since']
        super().do_GET()
    def end_headers(self):
        self.send_header('Cache-Control','no-store');super().end_headers()
    def log_message(self,*args):pass


def main():
    from playwright.sync_api import sync_playwright,expect
    with tempfile.TemporaryDirectory(prefix='tether-web-update-') as temporary:
        print('Update check: build fixture',flush=True)
        folder=Path(temporary);release=builder.build(folder/'release','/tether-chat/')
        config=json.loads((release/'app-config.js').read_text().removeprefix('window.TETHER_CONFIG=').rstrip(';\n'))
        version=config['version'];served=folder/'site'/'tether-chat';shutil.copytree(release,served)
        legacy={**config,'version':'2026.18'}
        (served/'app-config.js').write_text('window.TETHER_CONFIG='+json.dumps(legacy)+';\n')
        (served/'shell.mjs').write_bytes((ROOT/'tests/fixtures/legacy-web-shell.mjs').read_bytes())
        # This snapshots the old worker without an activation message handler.
        assets=[config['base']+str(file.relative_to(served)) for file in served.rglob('*') if file.is_file() and file.name not in {'sw.js','update.html'} and not file.name.startswith('.')]
        worker=(ROOT/'tests/fixtures/legacy-web-sw.js.in').read_text()
        for key,value in {'__CACHE__':'tether-web:/tether-chat/:2026.18:fixture','__PREFIX__':'tether-web:/tether-chat/:','__ASSETS__':assets,'__BASE__':'/tether-chat/'}.items():worker=worker.replace(key,json.dumps(value))
        (served/'sw.js').write_text(worker)
        # The actual old release has no update page on its server or in its cache.
        (served/'update.html').unlink()
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(FreshHandler,directory=str(folder/'site')))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}/tether-chat/'
        (folder/'site'/'unrelated.html').write_text('<title>Another app</title><p>Keep this page.</p>')
        try:
            with sync_playwright() as pw:
                executable=os.environ.get('TETHER_TEST_CHROMIUM')
                browser=pw.chromium.launch(**({'executable_path':executable} if executable else {}))
                context=browser.new_context(viewport={'width':390,'height':844})
                context.route('https://**/*',lambda route:route.fulfill(status=418,body='No remote AI calls during update checks'))
                print('Update check: open legacy release',flush=True)
                page=context.new_page();page.goto(base)
                page.wait_for_function('navigator.serviceWorker.controller!==null')
                page.evaluate("""async()=>{const r=await tetherReady;
                  const api=async(path,body)=>(await r.fetch('/tether-chat/api'+path,{method:'POST',body:JSON.stringify(body)})).json();
                  const task=await api('/threads',{title:'Keep this task',summary:'Saved before the update'});
                  await api('/threads/'+task.id+'/entries',{kind:'thought',body:'Keep this note too'});
                  await api('/settings',{base_url:'https://provider.example/v1',model:'synthetic-model',api_key:'synthetic-saved-key',remember:true,passphrase:'synthetic-passphrase'});
                }""")
                frame=page.frame_locator('#app-frame');frame.get_by_label('Message tether').fill('Keep this unsent phone draft.')
                before=page.evaluate(DB,'read')
                unrelated=context.new_page();unrelated.goto(base.replace('/tether-chat/','/unrelated.html'));unrelated.evaluate("window.keepThisTab='untouched'")
                other=context.new_page();other.goto(base)
                expect(other.frame_locator('#app-frame').locator('#browserVersion')).to_contain_text('2026.18')
                print('Update check: deploy current release',flush=True)
                shutil.copytree(release,served,dirs_exist_ok=True)
                page.evaluate(DB,'busy')
                # New workers activate without any Settings action, but do not
                # navigate open documents or interrupt their active work.
                page.evaluate("async()=>{const r=await navigator.serviceWorker.getRegistration();await r.update()}")
                update=context.new_page();update.goto(base+'update.html')
                expect(update.locator('#status')).to_contain_text('Waiting for your current chat request')
                assert update.url.endswith('/update.html')
                assert update.evaluate('document.documentElement.scrollWidth<=innerWidth')
                update.screenshot(path=str(folder/'update-waiting.jpg'),type='jpeg',quality=90)
                # The second tab stays open throughout recovery; no all-tabs-closed workaround.
                other.evaluate(DB,'idle')
                print('Update check: finish legacy recovery',flush=True)
                update.wait_for_url(base,timeout=90000)
                # Legacy shells start current code on normal navigation; no forced
                # navigation of other tabs with potentially unsaved editors.
                other.reload();page.reload()
                expect(other.frame_locator('#app-frame').locator('#browserVersion')).to_contain_text(version)
                expect(page.frame_locator('#app-frame').locator('#browserVersion')).to_contain_text(version)
                assert unrelated.evaluate('window.keepThisTab')=='untouched'
                assert page.evaluate("async()=>{const r=await tetherReady;return (await (await r.fetch('/tether-chat/api/settings')).json()).has_key}")
                updated=update.frame_locator('#app-frame')
                expect(updated.locator('#browserVersion')).to_contain_text(version)
                expect(updated.get_by_label('Message tether')).to_have_value('Keep this unsent phone draft.')
                after=update.evaluate(DB,'read')
                for field in ('tasks','entries','messages','settings'):assert after[field]==before[field],field+' changed during update'
                assert after['settings']['encrypted_key']['ciphertext']
                unlocked=update.evaluate("async()=>{const r=await tetherReady;return (await r.fetch('/tether-chat/api/settings/unlock',{method:'POST',body:JSON.stringify({passphrase:'synthetic-passphrase'})})).json()}")
                assert unlocked['has_key']
                expect(updated.get_by_role('button',name='Update app',exact=True)).to_have_count(0)
                # Even a stale cached config cannot override an online release.
                update.evaluate('''async()=>{
                  for(const key of await caches.keys())if(key.startsWith('tether-web:/tether-chat/:')){
                    const cache=await caches.open(key),path='/tether-chat/app-config.js';
                    const text=await (await cache.match(path)).text();
                    const config=JSON.parse(text.slice('window.TETHER_CONFIG='.length).trim().replace(/;$/,''));
                    config.version='2026.18';await cache.put(path,new Response('window.TETHER_CONFIG='+JSON.stringify(config)+';'));
                  }
                }''')
                print('Update check: ignore stale cache',flush=True)
                update.reload()
                expect(updated.locator('#browserVersion')).to_contain_text(version)
                print('Update check: defer active work',flush=True)
                future=version.split('.')[0]+'.'+str(int(version.split('.')[1])+1)
                update.evaluate(DB,'busy')
                updated.get_by_label('Message tether').fill('Keep this automatic-update draft.')
                for name in ('app-config.js','sw.js'):
                    path=served/name;path.write_text(path.read_text().replace(version,future))
                update.evaluate("window.dispatchEvent(new Event('focus'))")
                update.wait_for_timeout(1000)
                expect(updated.locator('#browserVersion')).to_contain_text(version)
                assert update.url==base
                update.evaluate(DB,'idle')
                updated.get_by_role('button',name='Settings',exact=True).click()
                update.evaluate("window.dispatchEvent(new Event('focus'))")
                update.wait_for_timeout(1000)
                expect(updated.locator('#browserVersion')).to_contain_text(version)
                updated.get_by_role('button',name='Close settings',exact=True).click()
                update.evaluate("window.dispatchEvent(new Event('focus'))")
                print('Update check: await automatic refresh',flush=True)
                expect(updated.locator('#browserVersion')).to_contain_text(future,timeout=90000)
                expect(updated.get_by_label('Message tether')).to_have_value('Keep this automatic-update draft.')
                after=update.evaluate(DB,'read')
                for field in ('tasks','entries','settings'):assert after[field]==before[field]
                assert unrelated.evaluate('window.keepThisTab')=='untouched'
                # The complete installed bundle remains usable without the network.
                print('Update check: offline reload',flush=True)
                context.set_offline(True);update.reload()
                expect(updated.locator('#browserVersion')).to_contain_text(future)
                expect(updated.get_by_label('Message tether')).to_have_value('Keep this automatic-update draft.')
                assert update.evaluate('document.documentElement.scrollWidth<=innerWidth')
                if os.environ.get('TETHER_UPDATE_SCREENSHOT'):update.screenshot(path=os.environ['TETHER_UPDATE_SCREENSHOT'])
                browser.close()
                print('PASS: online releases override stale caches; automatic updates wait for chat and editors; drafts, credentials, data, offline use and unrelated tabs survive.')
        finally:server.shutdown();server.server_close()


if __name__=='__main__':main()
