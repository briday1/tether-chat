"""Exercise desktop settings controls with an isolated synthetic credential service."""
import json


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
        page.get_by_label('Provider API base URL').fill('https://provider.example/v1')
        page.get_by_label('API key',exact=True).fill('desktop-synthetic-key')
        expect(page.locator('#modelStatus')).to_contain_text('2 models found')
        expect(page.get_by_label('Model',exact=True)).to_have_value('fixture-mini')
        assert saves==[] and tests==[] and discovered[-1]['api_key']=='desktop-synthetic-key'
        page.get_by_role('button',name='Test connection',exact=True).click()
        expect(page.locator('#providerStatus')).to_have_text('Connection successful')
        assert len(saves)==len(tests)==1 and tests[0]['model']=='fixture-mini'
        expect(page.get_by_label('API key',exact=True)).to_have_value('')
        page.get_by_label('Model',exact=True).fill('manual-model')
        page.locator('#provider').evaluate('(form)=>{form.requestSubmit();form.requestSubmit()}')
        page.get_by_role('button',name='Close settings',exact=True).click()
        assert page.evaluate('window.tetherBeforeChat()') is True
        assert len(saves)==2 and saves[-1]['model']=='manual-model' and saves[-1]['api_key'] is None
        page.get_by_role('button',name='Settings',exact=True).click()
        expect(page.locator('#keyStatus')).to_contain_text('API key configured and ready')
        expect(page.get_by_label('Model',exact=True)).to_have_value('manual-model')
        page.get_by_role('button',name='Close settings',exact=True).click()
    finally:page.unroute('**/api/settings**',settings)
