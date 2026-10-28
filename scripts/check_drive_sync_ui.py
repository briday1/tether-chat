"""Synthetic Drive/Picker UI coverage. Never contacts Google or uses real credentials."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import importlib.util,json,os,tempfile,threading
ROOT=Path(__file__).resolve().parents[1]
MOCK="""(()=>{window.gapi={load:(name,options)=>options.callback()};
class View{setMode(){return this}setIncludeFolders(){this.folder=true;return this}setSelectFolderEnabled(){return this}setMimeTypes(){return this}}
class Builder{addView(v){this.view=v;return this}setOAuthToken(){return this}setDeveloperKey(){return this}setAppId(){return this}setOrigin(){return this}enableFeature(){return this}setCallback(fn){this.callback=fn;return this}build(){return this}dispose(){}setVisible(){this.callback({action:'picked',docs:this.view.folder?[{id:'folder_123456',name:'Our Home'}]:[{id:'peer_12345678',name:'Partner device'}]})}}
window.google={accounts:{oauth2:{hasGrantedAllScopes:()=>true,initTokenClient:o=>({requestAccessToken:()=>o.callback({access_token:'fake-google-token',expires_in:3600})})}},picker:{DocsView:View,ViewId:{DOCS:'docs'},DocsViewMode:{LIST:'list'},Feature:{MULTISELECT_ENABLED:'multi'},Action:{PICKED:'picked',CANCEL:'cancel'},PickerBuilder:Builder}};
})()"""
def main():
 from playwright.sync_api import sync_playwright,expect
 spec=importlib.util.spec_from_file_location('build_web',ROOT/'scripts/build_web.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
 with tempfile.TemporaryDirectory(prefix='tether-drive-ui-') as temp:
  builder.build(Path(temp)/'tether-chat','/tether-chat/')
  server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=temp));threading.Thread(target=server.serve_forever,daemon=True).start()
  journals={'peer_12345678':{'format':'tether-home-journal','version':1,'workspace':'folder_123456','writer':'partner_123456','operations':[]}};versions={'peer_12345678':1};writes=[]
  def google(route):
   request=route.request;url=request.url
   headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Authorization,Content-Type,If-Match','Access-Control-Allow-Methods':'GET,POST,PATCH,OPTIONS','Access-Control-Expose-Headers':'ETag'}
   if request.method=='OPTIONS':route.fulfill(status=204,headers=headers);return
   if '/upload/' in url and request.method=='POST':
    body=request.post_data;parts=body.split('\r\n\r\n');data=json.loads(parts[2].split('\r\n--')[0]);identity='own_123456789';journals[identity]=data;versions[identity]=1
    route.fulfill(json={'id':identity,'name':'This device'},headers=headers);return
   identity=url.split('/files/')[-1].split('?')[0]
   if identity=='folder_123456':route.fulfill(json={'id':identity,'name':'Our Home','mimeType':'application/vnd.google-apps.folder','capabilities':{'canAddChildren':True}},headers=headers);return
   if identity not in journals:route.fulfill(status=404,json={},headers=headers);return
   etag='"v'+str(versions[identity])+'"'
   if request.method=='PATCH':
    if request.headers.get('if-match')!=etag:route.fulfill(status=412,json={},headers=headers);return
    writes.append(identity);journals[identity]=json.loads(request.post_data);versions[identity]+=1;route.fulfill(json={'id':identity},headers=headers);return
   route.fulfill(json=journals[identity],headers={**headers,'ETag':etag})
  try:
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=os.environ.get('TETHER_TEST_CHROMIUM'),args=['--no-sandbox']);page=browser.new_page();page.add_init_script(MOCK)
    page.route('https://www.googleapis.com/**',google);page.route('https://accounts.google.com/**',lambda r:r.abort());page.route('https://apis.google.com/**',lambda r:r.abort())
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(f'http://127.0.0.1:{server.server_port}/tether-chat/?workspace=home&view=sharing');page.wait_for_function('!!window.tetherFetch')
    page.evaluate("async()=>{const r=await window.tetherReady;await r.fetch('/tether-chat/api/threads',{method:'POST',body:JSON.stringify({title:'Buy milk',categories:['Groceries']})})}")
    screen=page.frame_locator('#app-frame');screen.get_by_text('App setup',exact=True).click();screen.locator('#clientId').fill('test-client.apps.googleusercontent.com');screen.locator('#projectNumber').fill('123456789');screen.locator('#pickerKey').fill('fake-restricted-browser-key');screen.locator('#connect').click();expect(screen.locator('#syncStatus')).to_contain_text('Google connected')
    screen.locator('#pickFolder').click();expect(screen.locator('#folderStatus')).to_contain_text('Our Home');screen.locator('#consent').check();screen.locator('#createJournal').click();expect(screen.locator('#syncStatus')).to_contain_text('Synced');screen.locator('#pickPeers').click();expect(screen.locator('#peerFiles')).to_contain_text('Partner device');expect(screen.locator('#syncStatus')).to_contain_text('Synced')
    assert journals['own_123456789']['operations'];assert not journals['peer_12345678']['operations'];assert set(writes)=={'own_123456789'}
    screen.get_by_role('link',name='Tasks',exact=True).click();expect(screen.get_by_role('combobox',name='Work or Home')).to_have_value('home');screen.get_by_role('link',name='Share Home',exact=True).click();expect(screen.locator('#peerFiles')).to_contain_text('Partner device')
    page.reload();screen=page.frame_locator('#app-frame');expect(screen.locator('#peerFiles')).to_contain_text('Partner device');screen.locator('#connect').click();expect(screen.locator('#syncStatus')).to_contain_text('Synced')
    page.on('dialog',lambda dialog:dialog.accept());screen.locator('#disconnect').click();expect(screen.locator('#syncStatus')).to_contain_text('Disconnected');assert not errors,errors
    browser.close();print('Drive UI mock checks passed: consent, Picker, Home sync, peer read-only, navigation/reload and disconnect. Real Google still unverified.')
  finally:server.shutdown()
if __name__=='__main__':main()
