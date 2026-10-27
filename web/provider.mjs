/* Provider errors are data. Never echo credentials supplied in an error body. */
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
