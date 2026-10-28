/* Model discovery reads the typed connection, without saving or testing a paid call. */
(() => {
  const $=selector=>document.querySelector(selector);
  let revision=0,timer=null,configured=null,manualModel=false,lastConnection='';
  function invalidate(){revision++;clearTimeout(timer);lastConnection='';$('#modelOptions')?.replaceChildren()}
  function signature(){return JSON.stringify([$('#base').value.trim(),$('#key').value.trim()])}
  function canLoad(){return $('#key').value.trim() || configured?.has_key && $('#base').value.trim().replace(/\/+$/,'')===configured.base_url.replace(/\/+$/,'')}
  async function discover(force=false){
    if(!$('#provider') || !canLoad())return;
    const connection=signature();if(!force && connection===lastConnection)return;
    const current=++revision,selected=$('#model').value;
    $('#modelStatus').textContent='Loading available models…';
    try{
      const response=await fetch('/api/settings/models',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({base_url:$('#base').value.trim(),api_key:$('#key').value.trim()||null})});
      const result=await response.json();
      if(current!==revision || connection!==signature())return;
      if(!response.ok)throw Error(result.detail||'Could not load models. Enter a model ID manually.');
      const ids=result.models||[],options=ids.map(id=>{const option=document.createElement('option');option.value=id;return option});
      $('#modelOptions').replaceChildren(...options);lastConnection=connection;
      // Keep a deliberate manual choice. Prefer a small chat model for a new connection.
      if(!manualModel && selected===$('#model').value && !ids.includes(selected)){
        const candidates=ids.filter(id=>!/(embed|whisper|tts|audio|realtime|transcrib|moderation|dall-e|image|video|sora|babbage|davinci|search|codex|computer-use|(?:^|-)pro(?:-|$))/i.test(id));
        const preferred=candidates.find(id=>/(mini|flash|haiku|luna|lite)/i.test(id) && !/\d{4}-\d{2}-\d{2}/.test(id))||candidates[0];
        if(preferred)$('#model').value=preferred;
      }
      $('#modelStatus').textContent=ids.length?`${ids.length} tool-calling models found. Choose a compatible model.`:
        'No verified tool-calling models were reported. Enter an ID only if you know it supports chat tools.';
    }catch(error){if(current===revision && connection===signature())$('#modelStatus').textContent=error.message}
  }
  window.tetherProviderConfigured=c=>{
    configured=c;invalidate();manualModel=!!(c.has_key||c.has_saved_key);
    if(c.has_key)discover();
    else if($('#modelStatus'))$('#modelStatus').textContent=c.locked?'Unlock your saved key to load available models.':'Models load automatically after you enter a provider URL and key.';
  };
  window.tetherDiscoverModels=()=>discover();
  document.addEventListener('DOMContentLoaded',()=>{
    if(!$('#provider'))return;
    $('#model').addEventListener('input',()=>{manualModel=true});
    for(const selector of ['#base','#key'])$(selector).addEventListener('input',()=>{
      invalidate();$('#modelStatus').textContent='Models load automatically from this URL and key.';
      timer=setTimeout(()=>discover(),700);
    });
    $('#refreshModels').onclick=()=>{
      if(!canLoad()){$('#modelStatus').textContent=configured?.locked?'Unlock your saved key to load models.':'Enter your API key for this provider URL to load models.';return}
      discover(true);
    };
  });
})();
