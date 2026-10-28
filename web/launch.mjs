/* Check once before opening a session. Nothing here runs on focus or a timer. */
export function configVersion(source){
  const match=source.match(/^\s*window\.TETHER_CONFIG\s*=\s*(\{[\s\S]*\})\s*;?\s*$/);
  if(!match)throw Error('Invalid app configuration');
  return JSON.parse(match[1]).version;
}
export async function prepareLaunch(config){
  if(navigator.onLine===false||!('serviceWorker' in navigator))return true;
  try{
    const registration=await navigator.serviceWorker.register(config.base+'sw.js',{scope:config.base,updateViaCache:'none'});
    await registration.update();
    const deadline=Date.now()+15000;
    while(registration.installing&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,50));
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),5000);
    let latest;
    try{
      const response=await fetch(config.base+'app-config.js?launch='+Date.now(),{cache:'no-store',signal:controller.signal});
      if(response.ok)latest=configVersion(await response.text());
    }finally{clearTimeout(timeout)}
    if(registration.waiting||latest&&latest!==config.version){
      location.replace(config.base+'update.html?launch=1');return false;
    }
  }catch(_){ /* An offline or failed update leaves the installed release usable. */ }
  return true;
}
