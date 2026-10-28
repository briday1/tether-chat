/* Household AI credentials use RFC 7516 JWE, never custom encryption or links.
 * PBES2 SHA-512 count follows OWASP Password Storage's 220,000 recommendation.
 * The v1 format fixes algorithms/counts; inspect BEFORE any expensive KDF work.
 * Encryption authenticates a bundle, not its author: every passphrase holder
 * can create one. The caller MUST separately confirm/pin the provider endpoint
 * and key revision locally before using a decrypted key for any request.
 */
import {CompactEncrypt, compactDecrypt, decodeProtectedHeader} from './vendor-jose.mjs';

export const HOUSEHOLD_AI_VERSION=1;
export const HOUSEHOLD_AI_ITERATIONS=220000;
export const HOUSEHOLD_AI_MAX_JWE=24000;
const ALG='PBES2-HS512+A256KW',ENC='A256GCM',TYPE='tether-household-ai+jwe';
const encoder=new TextEncoder(),decoder=new TextDecoder('utf-8',{fatal:true});
const idPattern=/^[A-Za-z0-9_-]{8,200}$/;
const HEADER_KEYS=['alg','enc','typ','v','household','revision','p2c','p2s'];
const invalid=()=>new Error('Unsupported or invalid encrypted household AI settings.');
function plain(value){if(value===null||typeof value!=='object'||Object.prototype.toString.call(value)!=='[object Object]')return false;const proto=Object.getPrototypeOf(value);return proto===null||Object.getPrototypeOf(proto)===null}
function context(value){
  if(!plain(value)||!idPattern.test(value.householdId||'')||!idPattern.test(value.revisionId||''))throw invalid();
  return {householdId:value.householdId,revisionId:value.revisionId};
}
function password(value){
  if(typeof value!=='string'||[...value].length<16||value.length>1024||encoder.encode(value).length>4096)
    throw new Error('Use a household passphrase of 16 to 1024 characters, preferably several random words.');
  return encoder.encode(value);
}
export function normalizeHouseholdProvider(value){
  if(typeof value!=='string'||value.length>2048||/[\s\\\x00-\x1f\x7f]/u.test(value))
    throw new Error('Use a public HTTPS provider URL without credentials, spaces, query, or fragment.');
  let url;try{url=new URL(value)}catch(_){throw new Error('Use a valid public HTTPS provider URL.');}
  const host=url.hostname.toLowerCase();
  // A browser cannot verify a DNS answer. Reject explicit local/IP targets,
  // require a DNS name, and still require local endpoint confirmation upstream.
  const labels=host.split('.');
  if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash||host.length>253||labels.length<2
    ||labels.some(label=>!(/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/).test(label))
    ||/^\d+$/.test(labels.at(-1))||/(?:^|\.)(localhost|local|internal|intranet|lan|home|arpa|onion)$/.test(host))
    throw new Error('Use a public HTTPS provider URL without credentials, query, fragment, or local/IP host.');
  const normalized=url.href.replace(/\/+$/,'');
  if(normalized.length>2048)throw new Error('Use a provider URL no longer than 2048 characters.');
  return normalized;
}
export function validateHouseholdAIConfig(config){
  if(!plain(config)||Object.keys(config).sort().join(',')!=='api_key,base_url,model')throw new Error('Invalid household AI provider settings.');
  const base_url=normalizeHouseholdProvider(config.base_url);
  if(typeof config.model!=='string'||!config.model.trim()||config.model.length>200||/[\x00-\x1f\x7f]/.test(config.model))throw new Error('Choose a valid household AI model.');
  if(typeof config.api_key!=='string'||!config.api_key||config.api_key.length>10000||encoder.encode(config.api_key).length>10000||/[\s\x00-\x1f\x7f]/u.test(config.api_key))throw new Error('Enter a valid dedicated household API key.');
  return {base_url,model:config.model.trim(),api_key:config.api_key};
}
function decodeBase64(value){
  if(typeof value!=='string'||!/^[A-Za-z0-9_-]*$/.test(value)||value.length%4===1)throw invalid();
  try{return Uint8Array.from(atob(value.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-value.length%4)%4)),c=>c.charCodeAt(0))}catch(_){throw invalid();}
}
export function inspectHouseholdBundle(jwe,expected){
  const binding=context(expected);
  if(typeof jwe!=='string'||jwe.length>HOUSEHOLD_AI_MAX_JWE)throw invalid();
  const parts=jwe.split('.');
  if(parts.length!==5||parts[0].length>2048||parts.some(part=>!part||!/^[A-Za-z0-9_-]+$/.test(part)))throw invalid();
  let header;try{header=decodeProtectedHeader(jwe)}catch(_){throw invalid();}
  if(!plain(header)||Object.keys(header).length!==HEADER_KEYS.length||HEADER_KEYS.some(key=>!Object.hasOwn(header,key))
    ||header.alg!==ALG||header.enc!==ENC||header.typ!==TYPE||header.v!==HOUSEHOLD_AI_VERSION
    ||header.household!==binding.householdId||header.revision!==binding.revisionId
    ||header.p2c!==HOUSEHOLD_AI_ITERATIONS||decodeBase64(header.p2s).length!==16
    ||decodeBase64(parts[1]).length!==40||decodeBase64(parts[2]).length!==12||decodeBase64(parts[4]).length!==16
    ||decodeBase64(parts[3]).length>16384)throw invalid();
  return {version:header.v,householdId:header.household,revisionId:header.revision};
}
export async function sealHouseholdBundle(config,passphrase,binding){
  const {householdId,revisionId}=context(binding),safe=validateHouseholdAIConfig(config),secret=password(passphrase);
  const plaintext=encoder.encode(JSON.stringify({v:HOUSEHOLD_AI_VERSION,householdId,revisionId,...safe}));
  try{
    const jwe=await new CompactEncrypt(plaintext)
      .setProtectedHeader({alg:ALG,enc:ENC,typ:TYPE,v:HOUSEHOLD_AI_VERSION,household:householdId,revision:revisionId})
      .setKeyManagementParameters({p2c:HOUSEHOLD_AI_ITERATIONS,p2s:crypto.getRandomValues(new Uint8Array(16))})
      .encrypt(secret);
    inspectHouseholdBundle(jwe,{householdId,revisionId});return jwe;
  }finally{secret.fill(0);plaintext.fill(0);}
}
export async function openHouseholdBundle(jwe,passphrase,binding){
  inspectHouseholdBundle(jwe,binding);const secret=password(passphrase);let plaintext;
  try{
    const result=await compactDecrypt(jwe,secret,{keyManagementAlgorithms:[ALG],contentEncryptionAlgorithms:[ENC],maxPBES2Count:HOUSEHOLD_AI_ITERATIONS});plaintext=result.plaintext;
    if(plaintext.length>16384)throw invalid();
    const data=JSON.parse(decoder.decode(plaintext));
    if(!plain(data)||Object.keys(data).sort().join(',')!=='api_key,base_url,householdId,model,revisionId,v'
      ||data.v!==HOUSEHOLD_AI_VERSION||data.householdId!==binding.householdId||data.revisionId!==binding.revisionId)throw invalid();
    return validateHouseholdAIConfig({base_url:data.base_url,model:data.model,api_key:data.api_key});
  }catch(_){throw new Error('Could not unlock household AI settings. Check the passphrase or ask for the current household setup.');}
  finally{secret.fill(0);plaintext?.fill(0);}
}
// Runtime-facing name; keep normalization identical at decryption and use time.
export const normalizeEndpoint=normalizeHouseholdProvider;
