"""Exercise desktop settings controls with an isolated synthetic credential service."""
import json
from pathlib import Path

def check_nav_settings_gear(ui):
    gear = ui.locator('#navsettings')
    assert gear.get_attribute('aria-label') == 'Settings'
    assert gear.evaluate("n=>{const s=getComputedStyle(n);return s.borderTopWidth==='0px'&&s.borderRightWidth==='0px'&&s.backgroundColor==='rgba(0, 0, 0, 0)'}")
    assert gear.locator('svg').get_attribute('width') == '21'
    product = gear.evaluate("()=>window.tetherWorkspace||'work'")
    view = ui.locator('.topnav a.active').inner_text().strip().lower()
    Path('artifacts').mkdir(exist_ok=True)
    ui.locator('.topnav').screenshot(path=f'artifacts/display-{product}-{view}-settings-gear.png')


def check_settings_appearance(ui):
    check_nav_settings_gear(ui)
    controls=ui.locator('#settings button:not(#closeSettings)').evaluate_all('''buttons=>buttons.filter(b=>b.getClientRects().length).map(b=>{
      const s=getComputedStyle(b);return {text:b.textContent,height:b.getBoundingClientRect().height,font:s.fontSize,radius:s.borderRadius,border:s.borderTopWidth,padding:s.padding};
    })''')
    assert len(controls)>=(2 if ui.locator("#householdSettings").count() else 3),controls
    for control in controls:
        assert control['height']>=40 and control['font']=='13px' and control['radius']=='8px' and control['border']=='1px',control
    assert len({control['padding'] for control in controls})==1,controls


def check_provider_settings(page):
    from playwright.sync_api import expect
    saved={'base_url':'https://api.openai.com/v1','model':'gpt-4.1-mini','has_key':False}
    saves=[];tests=[];discovered=[]
    def settings(route):
        path=route.request.url.split('/api/settings',1)[1]
        body=route.request.post_data_json if route.request.method=='POST' else {}
        if path=='/models':
            discovered.append(body)
            result={'models':['fixture-mini','fixture-model']}
        elif path=='/test':
            assert saved['has_key'] and saves[-1]['api_key']=='desktop-synthetic-key'
            tests.append(dict(saved));result={'ok':True,'message':'Connection successful'}
        elif route.request.method=='POST':
            saves.append(body);saved.update(base_url=body['base_url'],model=body['model'],has_key=saved['has_key'] or bool(body['api_key']));result=saved
        else:result=saved
        route.fulfill(status=200,content_type='application/json',body=json.dumps(result))
    page.route('**/api/settings**',settings)
    try:
        page.get_by_role('button',name='Settings',exact=True).click()
        check_settings_appearance(page)
        expect(page.locator('#connectionMode')).to_contain_text('Desktop connection')
        page.get_by_label('Provider API base URL').fill('https://provider.example/v1')
        page.get_by_label('API key',exact=True).fill('desktop-synthetic-key')
        expect(page.locator('#modelStatus')).to_contain_text('2 tool-calling models available')
        expect(page.get_by_label('Model',exact=True)).to_have_value('fixture-mini')
        assert saves==[] and tests==[] and discovered[-1]['api_key']=='desktop-synthetic-key'
        page.get_by_role('button',name='Test connection',exact=True).click()
        expect(page.locator('#providerStatus')).to_have_text('Connection successful')
        assert len(saves)==len(tests)==1 and tests[0]['model']=='fixture-mini'
        expect(page.get_by_label('API key',exact=True)).to_have_value('')
        page.get_by_label('Model',exact=True).select_option('fixture-model')
        page.get_by_role('button',name='Refresh models',exact=True).click()
        expect(page.get_by_label('Model',exact=True)).to_have_value('fixture-model')
        page.locator('#provider').evaluate('(form)=>{form.requestSubmit();form.requestSubmit()}')
        page.get_by_role('button',name='Close settings',exact=True).click()
        assert page.evaluate('window.tetherBeforeChat()') is True
        assert len(saves)==2 and saves[-1]['model']=='fixture-model' and saves[-1]['api_key'] is None
        page.get_by_role('button',name='Settings',exact=True).click()
        expect(page.locator('#keyStatus')).to_contain_text('API key configured and ready')
        expect(page.get_by_label('Model',exact=True)).to_have_value('fixture-model')
        page.get_by_role('button',name='Close settings',exact=True).click()
    finally:page.unroute('**/api/settings**',settings)
