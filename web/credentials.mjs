/* Only an encrypted key may be saved persistently. Plaintext stays in this session. */
import {Problem} from './store.mjs';
const bytes = value => Uint8Array.from(atob(value), c => c.charCodeAt(0));
const base64 = value => btoa(String.fromCharCode(...value));
async function derive(passphrase, salt) {
  if (typeof passphrase !== 'string' || passphrase.length < 8) throw new Problem('Use an unlock passphrase of at least 8 characters');
  const material = await crypto.subtle.importKey('raw',new TextEncoder().encode(passphrase),'PBKDF2',false,['deriveKey']);
  return crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:310000,hash:'SHA-256'},material,
    {name:'AES-GCM',length:256},false,['encrypt','decrypt']);
}
export async function encryptKey(value, passphrase) {
  const salt = crypto.getRandomValues(new Uint8Array(16)), iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await derive(passphrase,salt);
  const encrypted = await crypto.subtle.encrypt({name:'AES-GCM',iv},key,new TextEncoder().encode(value));
  return {salt:base64(salt),iv:base64(iv),ciphertext:base64(new Uint8Array(encrypted))};
}
export async function decryptKey(encrypted, passphrase) {
  try {
    const key=await derive(passphrase,bytes(encrypted.salt));
    return new TextDecoder().decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:bytes(encrypted.iv)},key,bytes(encrypted.ciphertext)));
  } catch (error) {
    if (error instanceof Problem) throw error;
    throw new Problem('Could not unlock the saved key. Check your passphrase.');
  }
}
