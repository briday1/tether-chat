/* A native model picker lists only verified tool models from this connection. */
(() => {
  const $=selector=>document.querySelector(selector),choices=new Map();
  let revision=0,timer=null,configured=null,lastConnection='',pending=null,lastError='';
  const base=()=>$('#base').value.trim().replace(/\/+$/,'');
  const signature=()=>JSON.stringify([base(),$('#key').value.trim()]);
  const canLoad=()=>$('#key').value.trim() || configured?.has_key && base()===configured.base_url.replace(/\/+$/,'');
  function placeholder(text){const option=new Option(text,'',true,true);option.disabled=true;$('#model').replaceChildren(option)}
  function invalidate(){revision++;clearTimeout(timer);lastConnection='';lastError='';pending=null;placeholder('Connect to load tool-calling models')}
  async function discover(force=false){
    if(!$('#provider') || !canLoad())return;
    const connection=signature();
    if(pending?.connection===connection)return pending.promise;
    if(!force && connection===lastConnection)return;
    const current=++revision,selected=choices.get(base()) || (configured?.base_url.replace(/\/+$/,'')===base()?configured.model:'');
    $('#modelStatus').textContent='Loading available tool-calling models…';
    const promise=(async()=>{
      try{
        const response=await fetch('/api/settings/models',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({base_url:base(),api_key:$('#key').value.trim()||null})});
        const result=await response.json();
        if(current!==revision || connection!==signature())return;
        if(!response.ok)throw Error(result.detail||'Could not load models. Check this connection and refresh the list.');
        const ids=Array.isArray(result.models)?result.models:[];
        if(!ids.length){placeholder('No compatible tool-calling models found');lastError='This provider reported no verified tool-calling chat models. Check the URL/key or the provider’s model capabilities.'}
        else{
          $('#model').replaceChildren(...ids.map(id=>new Option(id,id)));
          const preferred=ids.find(id=>/(mini|flash|haiku|luna|lite)/i.test(id)&&!/\d{4}-\d{2}-\d{2}/.test(id))||ids[0];
          $('#model').value=ids.includes(selected)?selected:preferred;choices.set(base(),$('#model').value);lastError='';
        }
        lastConnection=connection;
        $('#modelStatus').textContent=ids.length?`${ids.length} tool-calling ${ids.length===1?'model':'models'} available. Select a model from the list.`:lastError;
      }catch(error){if(current===revision && connection===signature()){lastError=error.message;placeholder('Could not load models');$('#modelStatus').textContent=lastError}}
    })();
    pending={connection,promise};try{await promise}finally{if(pending?.promise===promise)pending=null}
  }
  window.tetherProviderConfigured=c=>{
    configured=c;choices.set(c.base_url.replace(/\/+$/,''),c.model);invalidate();
    if(c.has_key)discover();
    else $('#modelStatus').textContent=c.locked?'Unlock your saved key to load the model list.':'Enter your provider URL and API key to load the model list.';
  };
  window.tetherDiscoverModels=()=>discover();
  window.tetherRequireModel=async()=>{
    if(!canLoad())throw Error(configured && base()!==configured.base_url.replace(/\/+$/,'')?'Re-enter your API key for this provider URL to load models.':configured?.locked?'Unlock your saved key to choose a model.':'Enter your API key for this provider URL to load models.');
    await discover();
    if(!$('#model').value)throw Error(lastError||'Select a tool-calling model from the list.');
  };
  document.addEventListener('DOMContentLoaded',()=>{
    if(!$('#provider'))return;
    $('#provider').noValidate=true;
    $('#model').addEventListener('change',()=>choices.set(base(),$('#model').value));
    for(const selector of ['#base','#key'])$(selector).addEventListener('input',()=>{
      invalidate();$('#modelStatus').textContent='The model list loads automatically from this URL and key.';timer=setTimeout(()=>discover(),700);
    });
    $('#refreshModels').onclick=()=>{
      if(!canLoad()){$('#modelStatus').textContent=configured?.locked?'Unlock your saved key to load models.':'Enter your API key for this provider URL to load models.';return}
      discover(true);
    };
  });
})();
