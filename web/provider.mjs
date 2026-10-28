/* Provider errors are data. Never echo credentials supplied in an error body. */
const baseModel=id=>(id.startsWith('ft:')?id.split(':')[1]:id).replace(/-\d{4}-\d\d-\d\d$/,'');
export function modelOptions(base,id,catalog={}){return new URL(base).hostname==='api.openai.com'?catalog.openai?.[baseModel(id)]||{}:{}}
export function compatibleModels(items,base,catalog={}){
  return [...new Set(items.filter(item=>{
    const id=item?.id;if(typeof id!=='string'||!id.trim()||id.length>200)return false;
    const caps=item.capabilities||{},flags=[item.supports_tool_calling,item.supports_function_calling,caps.tools,caps.tool_calling,caps.function_calling];
    if(flags.some(value=>value===false)||typeof item.shutdown_date==='string'&&item.shutdown_date<=new Date().toISOString().slice(0,10))return false;
    if(/embed|whisper|tts|audio|realtime|transcrib|moderation|dall-e|image|video|sora/i.test(id))return false;
    const declared=Array.isArray(item.supported_parameters)?item.supported_parameters.some(p=>['tools','function_calling'].includes(p)):null;
    if(declared===false)return false;
    return new URL(base).hostname==='api.openai.com'?Object.hasOwn(catalog.openai||{},baseModel(id)):flags.some(value=>value===true)||declared===true;
  }).map(item=>item.id))].sort();
}
export function retryDelay(header,attempt=0,now=Date.now()) {
  if(header!==null && String(header).trim()){
    const seconds=Number(header),date=Date.parse(header);
    if(Number.isFinite(seconds))return Math.max(0,seconds);
    if(Number.isFinite(date))return Math.max(0,(date-now)/1000);
  }
  return 2**attempt+Math.random()*.3;
}
export async function providerFailure(response,key,base) {
  let data;try{data=await response.json()}catch(_){}
  const error=data?.error,code=typeof error?.code==='string'?error.code:'',type=error?.type||'';
  const safeCode=/^[a-zA-Z0-9_.-]{1,80}$/.test(code) && !(key && code.includes(key)) && !code.startsWith('sk-')?code:'';
  const raw=typeof error?.message==='string'?error.message:'';
  const billing={
    credit_balance_exhausted:'Your API credit balance is empty. Add credits in your provider billing settings.',
    organization_spend_limit_exceeded:'Your organization API spending limit was reached. Check its billing limits.',
    project_spend_limit_exceeded:'Your project API spending limit was reached. Check the project limits.',
    organization_usage_limit_exceeded:'Your organization API usage limit was reached. Check your provider usage limits.',
  };
  const quota=!!billing[code] || ['insufficient_quota','billing_hard_limit_reached','billing_not_active','usage_limit_reached'].includes(code)
    || type==='insufficient_quota' || /exceeded your current quota|insufficient (?:credit|quota)|credit balance|billing hard limit/i.test(raw);
  let message=billing[code];
  if(!message && quota)message='Your API billing or usage quota was reached. Check API credits and project limits; creating a key does not add credit.';
  if(message && new URL(base).hostname==='api.openai.com')message+=' ChatGPT subscriptions do not include API credit.';
  if(!message)message={401:'The provider rejected this API key. Check the key and provider URL.',
    403:'The provider denied access. Check key permissions and model access.',404:'The API endpoint or model was not found. Check the provider base URL and model.',
    429:'The provider temporarily rate limited this connection. Wait before trying again.'}[response.status];
  if(!message){
    const detail=raw.split(key||'\0').join('[redacted]').replace(/\bsk-[a-zA-Z0-9_-]+/g,'[redacted]').replace(/[\x00-\x1f]/g,' ').slice(0,240);
    message='The AI provider rejected the request.'+(detail?' '+detail:' Check the provider URL and selected model.');
  }
  return {message:message+` (HTTP ${response.status}${safeCode?', '+safeCode:''})`,retryable:!quota && [429,500,502,503,504].includes(response.status)};
}
