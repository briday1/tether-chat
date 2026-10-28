// Invitations identify a Sheet; they never grant Drive access or join it automatically.
const PARAM='tetherInvite';
const INVALID='This household invitation is invalid. Ask the sender to copy a new invitation from Share Home.';
const fail=()=>{throw Error(INVALID)};
function inviteURL(value){
  let url;try{url=new URL(value)}catch(_){fail()}
  if(!['https:','http:'].includes(url.protocol)||url.username||url.password)fail();
  return url;
}
function validate(value){
  if(!value||typeof value!=='object'||Array.isArray(value))fail();
  if(typeof value.id!=='string'||!/^[A-Za-z0-9_-]{8,200}$/.test(value.id))fail();
  if(typeof value.name!=='string'||!value.name.trim()||value.name.length>200||/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/u.test(value.name))fail();
  return {id:value.id,name:value.name.trim()};
}
export function buildHouseholdInvite(baseURL,household){
  const url=inviteURL(baseURL),value=validate(household);
  url.searchParams.delete('view');url.searchParams.set('settings','sharing');
  url.hash=new URLSearchParams({[PARAM]:JSON.stringify({v:1,...value})}).toString();
  return url.href;
}
export function parseHouseholdInvite(value){
  const url=inviteURL(value),fragment=url.hash.slice(1),params=new URLSearchParams(fragment);
  if(!params.has(PARAM))return null;
  if(fragment.length>4096||params.getAll(PARAM).length!==1)fail();
  let payload;try{decodeURIComponent(fragment);payload=JSON.parse(params.get(PARAM))}catch(_){fail()}
  if(!payload||typeof payload!=='object'||Array.isArray(payload)||payload.v!==1||Object.keys(payload).sort().join(',')!=='id,name,v')fail();
  return validate(payload);
}
