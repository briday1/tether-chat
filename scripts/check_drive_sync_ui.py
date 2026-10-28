"""Two-household-device UI test using synthetic Google/Picker responses only."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import importlib.util,json,os,tempfile,threading
ROOT=Path(__file__).resolve().parents[1]
MOCK="""(()=>{window.gapi={load:(name,options)=>options.callback()};
class View{setMode(){return this}setParent(){return this}setIncludeFolders(){this.folder=true;return this}setSelectFolderEnabled(){return this}setMimeTypes(){return this}}
class Builder{addView(v){this.view=v;return this}setOAuthToken(){return this}setDeveloperKey(){return this}setAppId(){return this}setOrigin(){return this}enableFeature(){return this}setCallback(fn){this.callback=fn;return this}build(){return this}dispose(){}setVisible(){this.callback({action:'picked',docs:[{id:'sheet_123456',name:'Tether · Our Home'}]})}}
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
    def open_device(token):
     context=browser.new_context();page=context.new_page();page.add_init_script(MOCK.replace('TOKEN',token));page.route('https://sheets.googleapis.com/**',google);page.route('https://www.googleapis.com/**',lambda r:r.abort());page.route('https://accounts.google.com/**',lambda r:r.abort());page.route('https://apis.google.com/**',lambda r:r.abort());page.on('pageerror',lambda error:errors.append(str(error)))
     page.goto(f'http://127.0.0.1:{server.server_port}/tether-chat/?workspace=home&view=sharing');page.wait_for_function('!!window.tetherFetch')
     screen=page.frame_locator('#app-frame');expect(screen.locator('#settings')).to_be_visible();expect(screen.get_by_role('link',name='Share Home',exact=True)).to_have_count(0);expect(screen.locator('#sharingSettings')).to_have_attribute('open','');screen.get_by_text('App setup',exact=True).click();screen.locator('#clientId').fill('test-client.apps.googleusercontent.com');screen.locator('#projectNumber').fill('123456789');screen.locator('#pickerKey').fill('fake-restricted-browser-key');screen.locator('#connect').click();expect(screen.locator('#syncStatus')).to_contain_text('Google connected');return page,screen
    def api(page,path,method='GET',data=None):return page.evaluate("async args=>{const runtime=await window.tetherReady;const response=await runtime.fetch('/tether-chat/api'+args.path,{method:args.method,body:args.data===null?undefined:JSON.stringify(args.data)});return response.json()}",{'path':path,'method':method,'data':data})
    def sync(page):page.evaluate('async()=>await window.tetherHomeSync.sync({force:true})')
    owner,screen=open_device('fake-owner-token');milk=api(owner,'/threads','POST',{'title':'Buy milk','categories':['Groceries']});screen.locator('#consent').check();screen.locator('#createHousehold').click();expect(screen.locator('#syncStatus')).to_contain_text('Synced');expect(screen.locator('#connectionStatus')).to_contain_text('does not confirm');expect(screen.locator('#shareHousehold')).to_have_attribute('href','https://docs.google.com/spreadsheets/d/sheet_123456/edit')
    partner,peer=open_device('fake-partner-token');appointment=api(partner,'/threads','POST',{'title':'Dentist appointment'});peer.locator('#consent').check();peer.locator('#joinHousehold').click();expect(peer.locator('#syncStatus')).to_contain_text('Synced');sync(owner);assert len(api(owner,'/threads'))==2;assert len(api(partner,'/threads'))==2;expect(screen.locator('#householdStatus')).to_contain_text('Our Home')
    api(owner,'/threads/'+milk['id'],'PATCH',{'title':'Oat milk'});api(partner,'/threads/'+milk['id'],'PATCH',{'title':'Whole milk'});sync(owner);sync(partner);sync(owner);expect(screen.locator('#conflicts')).to_contain_text('Whole milk');screen.locator('#conflicts').get_by_role('button',name='Whole milk',exact=True).click();expect(screen.locator('#conflicts .conflict')).to_have_count(0);sync(partner);assert api(owner,'/threads/'+milk['id'])['title']==api(partner,'/threads/'+milk['id'])['title']=='Whole milk'
    assert set(writes)=={'Bearer fake-owner-token','Bearer fake-partner-token'}
    screen.locator('#closeSettings').click();expect(screen.locator('#settings')).not_to_be_visible();screen.locator('#navsettings').click();expect(screen.locator('#householdStatus')).to_contain_text('Our Home');screen.locator('#closeSettings').click();screen.get_by_role('link',name='Tasks',exact=True).click();expect(screen.get_by_role('combobox',name='Work or Home')).to_have_count(0);screen.locator('#navsettings').click();screen.locator('#sharingSettings>summary').click();expect(screen.locator('#householdStatus')).to_contain_text('Our Home')
    owner.reload();screen=owner.frame_locator('#app-frame');screen.locator('#navsettings').click();screen.locator('#sharingSettings>summary').click();expect(screen.locator('#householdStatus')).to_contain_text('Our Home');screen.locator('#connect').click();expect(screen.locator('#syncStatus')).to_contain_text('Synced');owner.on('dialog',lambda d:d.accept());screen.locator('#disconnect').click();expect(screen.locator('#syncStatus')).to_contain_text('Disconnected');assert len(api(owner,'/threads'))==2;owner.goto(f'http://127.0.0.1:{server.server_port}/tether-chat/drive-sharing.html');screen=owner.frame_locator('#app-frame');expect(screen.locator('#settings')).to_be_visible();expect(screen.locator('#sharingSettings')).to_have_attribute('open','');expect(screen.get_by_role('link',name='Share Home',exact=True)).to_have_count(0);owner.set_viewport_size({'width':390,'height':844});expect(screen.locator('#closeSettings')).to_be_visible();screen.locator('#closeSettings').click();expect(screen.locator('#settings')).not_to_be_visible();assert not errors,errors
    browser.close();print('Sheets mock UI passed: Create/Join, consent, bilateral sync, append-only Sheet, conflicts, navigation/reload and disconnect. Real Google remains unverified.')
  finally:server.shutdown()
if __name__=='__main__':main()
