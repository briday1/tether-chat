"""Two-household-device UI test using synthetic Google/Picker responses only."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import importlib.util,json,os,tempfile,threading
from urllib.parse import urlencode,urlparse,parse_qs
ROOT=Path(__file__).resolve().parents[1]
MOCK="""(()=>{const nativeInterval=window.setInterval.bind(window);window.setInterval=(fn,ms)=>ms===30000?nativeInterval(()=>{if(window.fastSync)fn()},100):nativeInterval(fn,ms);window.gapi={load:(name,options)=>options.callback()};
Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.copiedInvite=text}}});
class View{setFileIds(ids){this.fileIds=ids;return this}setLabel(){return this}setOwnedByMe(){return this}setMode(){return this}setParent(){return this}setIncludeFolders(){this.folder=true;return this}setSelectFolderEnabled(){return this}setMimeTypes(){return this}}
class Builder{addView(v){this.view=v;return this}setOAuthToken(){return this}setDeveloperKey(){return this}setAppId(){return this}setOrigin(){return this}enableFeature(){return this}setCallback(fn){this.callback=fn;return this}build(){return this}dispose(){}setVisible(){window.lastPickerFileIds=this.view.fileIds;if(window.cancelPicker){this.callback({action:'cancel'});return}if(window.deferPicker){window.pendingPicker=this;return}this.callback({action:'picked',docs:[{id:window.pickerFileId||'sheet_123456',name:'Tether · Our Home'}]})}}
window.google={accounts:{oauth2:{hasGrantedAllScopes:()=>true,initTokenClient:o=>({requestAccessToken:()=>o.callback({access_token:'TOKEN',expires_in:3600})})}},picker:{DocsView:View,ViewId:{DOCS:'docs'},DocsViewMode:{LIST:'list'},Feature:{MULTISELECT_ENABLED:'multi'},Action:{PICKED:'picked',CANCEL:'cancel'},PickerBuilder:Builder}};
})()"""
def main():
 from playwright.sync_api import sync_playwright,expect
 spec=importlib.util.spec_from_file_location('build_web',ROOT/'scripts/build_web.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
 with tempfile.TemporaryDirectory(prefix='tether-drive-ui-') as temp:
  builder.build(Path(temp)/'tether-chat','/tether-chat/')
  server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=temp));threading.Thread(target=server.serve_forever,daemon=True).start()
  rows=[];writes=[];errors=[];created=False
  def google(route):
   nonlocal created
   request=route.request;url=request.url
   from urllib.parse import unquote
   headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Authorization,Content-Type','Access-Control-Allow-Methods':'GET,POST,OPTIONS'}
   if request.method=='OPTIONS':route.fulfill(status=204,headers=headers);return
   if request.headers.get('authorization')=='Bearer fake-denied-token':
    route.fulfill(status=403,json={'error':{'code':403,'message':'Permission denied'}},headers=headers);return
   if request.method=='POST' and '/values/' not in url:
    data=json.loads(request.post_data);assert not created;created=True
    rows.extend([[cell['userEnteredValue']['stringValue'] for cell in row['values']] for row in data['sheets'][0]['data'][0]['rowData']]);route.fulfill(json={'spreadsheetId':'sheet_123456'},headers=headers);return
   assert created and '/sheet_123456' in url
   if '/values/' not in url:
    route.fulfill(json={'spreadsheetId':'sheet_123456','properties':{'title':'Tether · Our Home'},'sheets':[{'properties':{'sheetId':0,'title':'Journal','sheetType':'GRID','gridProperties':{'rowCount':max(1000,len(rows)),'columnCount':5}}}]},headers=headers);return
   if request.method=='POST':
    assert ':append?' in url and 'valueInputOption=RAW' in url and 'insertDataOption=INSERT_ROWS' in url
    values=json.loads(request.post_data)['values'];rows.extend(values);writes.append(request.headers.get('authorization'));route.fulfill(json={'spreadsheetId':'sheet_123456','updates':{'updatedRows':len(values)}},headers=headers);return
   assert request.method=='GET'
   import re
   match=re.search(r'A(\d+):E(\d+)',unquote(url));assert match,url
   values=rows[int(match[1])-1:int(match[2])];route.fulfill(json={'majorDimension':'ROWS','values':values},headers=headers)
  try:
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=os.environ.get('TETHER_TEST_CHROMIUM'),args=['--no-sandbox'])
    def open_device(token,invite_url=None):
     context=browser.new_context();page=context.new_page();page.add_init_script(MOCK.replace('TOKEN',token));page.route('https://sheets.googleapis.com/**',google);page.route('https://www.googleapis.com/**',lambda r:r.abort());page.route('https://accounts.google.com/**',lambda r:r.abort());page.route('https://apis.google.com/**',lambda r:r.abort());page.on('pageerror',lambda error:errors.append(str(error)))
     page.goto(invite_url or f'http://127.0.0.1:{server.server_port}/tether-chat/?workspace=home&view=sharing');page.wait_for_function('!!window.tetherFetch')
     screen=page.frame_locator('#app-frame');expect(screen.locator('#settings')).to_be_visible();expect(screen.get_by_role('link',name='Share Home',exact=True)).to_have_count(0);expect(screen.locator('#sharingSettings')).to_have_attribute('open','');screen.get_by_text('App setup',exact=True).click();screen.locator('#clientId').fill('test-client.apps.googleusercontent.com');screen.locator('#projectNumber').fill('123456789');screen.locator('#pickerKey').fill('fake-restricted-browser-key');screen.locator('#connect').click();expect(screen.locator('#syncStatus')).to_contain_text('Google connected');return page,screen
    def api(page,path,method='GET',data=None):return page.evaluate("async args=>{const runtime=await window.tetherReady;const response=await runtime.fetch('/tether-chat/api'+args.path,{method:args.method,body:args.data===null?undefined:JSON.stringify(args.data)});return response.json()}",{'path':path,'method':method,'data':data})
    def sync(page):page.evaluate('async()=>await window.tetherHomeSync.sync({force:true})')
    owner,screen=open_device('fake-owner-token');milk=api(owner,'/threads','POST',{'title':'Buy milk','categories':['Groceries']});screen.locator('#consent').check();screen.locator('#createHousehold').click();expect(screen.locator('#syncStatus')).to_contain_text('Synced');expect(screen.locator('#connectionStatus')).to_contain_text('does not confirm');expect(screen.locator('#shareHousehold')).to_have_attribute('href','https://docs.google.com/spreadsheets/d/sheet_123456/edit')
    partner,peer=open_device('fake-partner-token');peer.locator('#consent').check();peer.locator('body').evaluate('()=>window.deferPicker=true');peer.locator('#joinHousehold').click();peer.locator('#closeSettings').click();peer.locator('#navsettings').click();peer.locator('body').evaluate('()=>window.deferPicker=false');appointment=api(partner,'/threads','POST',{'title':'Dentist appointment'});peer.locator('#consent').check();peer.locator('#joinHousehold').click();expect(peer.locator('#syncStatus')).to_contain_text('Synced');sync(owner);assert len(api(owner,'/threads'))==2;assert len(api(partner,'/threads'))==2;expect(screen.locator('#householdStatus')).to_contain_text('Our Home')
    api(owner,'/threads/'+milk['id'],'PATCH',{'title':'Oat milk'});api(partner,'/threads/'+milk['id'],'PATCH',{'title':'Whole milk'});sync(owner);sync(partner);sync(owner);expect(screen.locator('#conflicts')).to_contain_text('Whole milk');screen.locator('#conflicts').get_by_role('button',name='Whole milk',exact=True).click();expect(screen.locator('#conflicts .conflict')).to_have_count(0);sync(partner);assert api(owner,'/threads/'+milk['id'])['title']==api(partner,'/threads/'+milk['id'])['title']=='Whole milk'
    assert set(writes)=={'Bearer fake-owner-token','Bearer fake-partner-token'}
    screen.locator('#closeSettings').click();expect(screen.locator('#settings')).not_to_be_visible();screen.locator('#navsettings').click();expect(screen.locator('#householdStatus')).to_contain_text('Our Home');screen.locator('#closeSettings').click();screen.get_by_role('link',name='Tasks',exact=True).click();expect(screen.get_by_role('combobox',name='Work or Home')).to_have_count(0);owner.evaluate('()=>{window.tetherHomeSync.transport.notBefore=0;window.fastSync=true}');api(owner,'/threads/'+milk['id'],'PATCH',{'title':'Automatic after navigation'});peer.locator('#sync').click();expect(peer.locator('#syncStatus')).to_contain_text('Synced');
    for _ in range(20):
     if api(partner,'/threads/'+milk['id'])['title']=='Automatic after navigation':break
     owner.wait_for_timeout(200);sync(partner)
    assert api(partner,'/threads/'+milk['id'])['title']=='Automatic after navigation'
    screen.locator('#navsettings').click();screen.locator('#sharingSettings>summary').click();expect(screen.locator('#householdStatus')).to_contain_text('Our Home')
    owner.reload();screen=owner.frame_locator('#app-frame');screen.locator('#navsettings').click();screen.locator('#sharingSettings>summary').click();expect(screen.locator('#householdStatus')).to_contain_text('Our Home');screen.locator('#connect').click();expect(screen.locator('#syncStatus')).to_contain_text('Synced');owner.on('dialog',lambda d:d.accept());screen.locator('#disconnect').click();expect(screen.locator('#syncStatus')).to_contain_text('Disconnected');assert len(api(owner,'/threads'))==2;owner.goto(f'http://127.0.0.1:{server.server_port}/tether-chat/drive-sharing.html');screen=owner.frame_locator('#app-frame');expect(screen.locator('#settings')).to_be_visible();expect(screen.locator('#sharingSettings')).to_have_attribute('open','');expect(screen.get_by_role('link',name='Share Home',exact=True)).to_have_count(0);owner.set_viewport_size({'width':390,'height':844});expect(screen.locator('#closeSettings')).to_be_visible();screen.locator('#closeSettings').click();expect(screen.locator('#settings')).not_to_be_visible();assert not errors,errors
    # Invitations must identify an exact Sheet without granting access or autojoining.
    peer.locator('#copyInvite').click()
    expect(peer.locator('#syncStatus')).to_contain_text('copied')
    invite_url=peer.locator('body').evaluate('()=>window.copiedInvite')
    parsed=urlparse(invite_url);payload=json.loads(parse_qs(parsed.fragment)['tetherInvite'][0])
    assert parsed.path=='/tether-chat/' and parsed.hostname=='127.0.0.1'
    assert parse_qs(parsed.query)['settings']==['sharing']
    assert payload=={'v':1,'id':'sheet_123456','name':'Tether · Our Home'},payload
    assert 'token' not in invite_url.lower() and 'fake-' not in invite_url
    invited,inv=open_device('fake-invited-token',invite_url)
    expect(inv.locator('#householdInvitation')).to_be_visible()
    expect(inv.locator('#householdInvitation')).to_contain_text('Our Home')
    assert not api(invited,'/drive-sync/local')['metadata'].get('session')
    assert inv.locator('body').evaluate('()=>window.lastPickerFileIds===undefined')
    before=len(rows)
    inv.locator('#joinInvitation').click()
    expect(inv.locator('#syncStatus')).to_contain_text('Confirm')
    assert len(rows)==before and not api(invited,'/drive-sync/local')['metadata'].get('session')
    inv.locator('#consent').check()
    inv.locator('body').evaluate("()=>window.pickerFileId='wrong_sheet'")
    inv.locator('#joinInvitation').click()
    expect(inv.locator('#syncStatus')).to_contain_text('not the invited household')
    assert inv.locator('body').evaluate('()=>window.lastPickerFileIds')=='sheet_123456'
    assert len(rows)==before and not api(invited,'/drive-sync/local')['metadata'].get('session')
    inv.locator('body').evaluate('()=>{window.pickerFileId=null;window.cancelPicker=true}')
    inv.locator('#joinInvitation').click()
    expect(inv.locator('#syncStatus')).to_contain_text('access')
    expect(inv.locator('#householdInvitation')).to_be_visible()
    assert len(rows)==before and not api(invited,'/drive-sync/local')['metadata'].get('session')
    inv.locator('body').evaluate('()=>{window.cancelPicker=false;window.deferPicker=true}')
    inv.locator('#joinInvitation').click()
    invited.wait_for_function("document.querySelector('#app-frame').contentWindow.pendingPicker!==undefined")
    inv.locator('#closeSettings').click();inv.locator('#navsettings').click()
    expect(inv.locator('#householdInvitation')).to_be_visible()
    expect(inv.locator('#householdInvitation')).to_contain_text('Our Home')
    expect(inv.locator('#syncStatus')).to_contain_text('paused')
    assert len(rows)==before and not api(invited,'/drive-sync/local')['metadata'].get('session')
    inv.locator('body').evaluate('()=>window.deferPicker=false')
    inv.locator('#joinInvitation').click()
    expect(inv.locator('#syncStatus')).to_contain_text('Synced')
    assert api(invited,'/drive-sync/local')['metadata']['session']['spreadsheetId']=='sheet_123456'
    assert len(api(invited,'/threads'))==2
    other_url=invite_url.split('#')[0]+'#'+urlencode({'tetherInvite':json.dumps({'v':1,'id':'other_sheet','name':'Another Home'})})
    invited.goto(other_url);inv=invited.frame_locator('#app-frame')
    expect(inv.locator('#householdInvitation')).to_contain_text('Another Home')
    inv.locator('#connect').click();expect(inv.locator('#syncStatus')).to_contain_text('Synced')
    inv.locator('#consent').check();before=len(rows)
    # A connected device must never switch households through an invitation.
    expect(inv.locator('#joinInvitation')).to_be_disabled()
    expect(inv.locator('#householdInvitation')).to_contain_text('connected to another household')
    assert api(invited,'/drive-sync/local')['metadata']['session']['spreadsheetId']=='sheet_123456'
    assert len(rows)==before
    assert inv.locator('body').evaluate('()=>window.lastPickerFileIds===undefined')
    inv.locator('#dismissInvitation').click();expect(inv.locator('#householdInvitation')).not_to_be_visible()
    denied,denied_ui=open_device('fake-denied-token',invite_url)
    api(denied,'/threads','POST',{'title':'Private task must not publish'})
    denied_ui.locator('#consent').check();before=len(rows)
    denied_ui.locator('#joinInvitation').click()
    expect(denied_ui.locator('#pendingSetup')).to_be_visible()
    expect(denied_ui.locator('#syncStatus')).to_contain_text('access')
    assert len(rows)==before and not api(denied,'/drive-sync/local')['metadata'].get('session')
    assert len(api(denied,'/threads'))==1
    denied_ui.locator('#joinInvitation').click()
    expect(denied_ui.locator('#syncStatus')).to_contain_text('pending setup')
    assert len(rows)==before and not api(denied,'/drive-sync/local')['metadata'].get('session')
    denied.on('dialog',lambda d:d.accept());denied_ui.locator('#abandonSetup').click()
    expect(denied_ui.locator('#pendingSetup')).not_to_be_visible()
    expect(denied_ui.locator('#householdInvitation')).to_be_visible()
    assert len(api(denied,'/threads'))==1
    assert not errors,errors
    browser.close();print('Sheets mock UI passed: Create/Join, consent, bilateral sync, append-only Sheet, conflicts, navigation/reload, disconnect and explicit exact-Sheet invitations. Real Google remains unverified.')
  finally:server.shutdown()
if __name__=='__main__':main()
