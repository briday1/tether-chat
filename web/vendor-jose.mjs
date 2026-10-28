/*
Vendored jose 6.2.13 (https://github.com/panva/jose).
Bundled using esbuild 0.25.12; exports CompactEncrypt, compactDecrypt, decodeProtectedHeader.
Source: npm jose@6.2.13, zero runtime dependencies.
NPM integrity: sha512-7TIg10ZE1x82YediN+lcrPNvGMKge9yFHQD+Qho/b8y2adfugU3AsvvHfxV0fzyFllT6l9xCjf4RWY9g/Z9PJQ==
Rebuild: esbuild entry.mjs --bundle --format=esm --platform=browser --target=es2022

The MIT License (MIT)

Copyright (c) 2018 Filip Skokan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

*/
// node_modules/jose/dist/webapi/lib/buffer_utils.js
var encoder = new TextEncoder();
var decoder = new TextDecoder();
var strictDecoder = new TextDecoder("utf-8", { fatal: true });
var UINT32_RANGE = 2 ** 32;
function concat(...buffers) {
  const size = buffers.reduce((acc, { length }) => acc + length, 0), buf = new Uint8Array(size);
  let i = 0;
  for (const buffer of buffers)
    buf.set(buffer, i), i += buffer.length;
  return buf;
}
function writeUInt32BE(buf, value, offset) {
  if (value < 0 || value >= UINT32_RANGE)
    throw new RangeError(`value must be >= 0 and <= ${UINT32_RANGE - 1}. Received ${value}`);
  buf.set([value >>> 24, value >>> 16, value >>> 8, value & 255], offset);
}
function uint64be(value) {
  const high = Math.floor(value / UINT32_RANGE), low = value % UINT32_RANGE, buf = new Uint8Array(8);
  return writeUInt32BE(buf, high, 0), writeUInt32BE(buf, low, 4), buf;
}
function uint32be(value) {
  const buf = new Uint8Array(4);
  return writeUInt32BE(buf, value), buf;
}
var NON_ASCII = /[^\x00-\x7f]/;
function encode(string) {
  if (typeof string == "string" && string.length >= 128) {
    if (NON_ASCII.test(string))
      throw new TypeError("non-ASCII string encountered in encode()");
    return encoder.encode(string);
  }
  const bytes = new Uint8Array(string.length);
  for (let i = 0; i < string.length; i++) {
    const code = string.charCodeAt(i);
    if (code > 127)
      throw new TypeError("non-ASCII string encountered in encode()");
    bytes[i] = code;
  }
  return bytes;
}
function encodeBase64(input, url = false) {
  if (Uint8Array.prototype.toBase64)
    return input.toBase64({ alphabet: url ? "base64url" : "base64", omitPadding: url });
  const CHUNK_SIZE = 32768, arr = [];
  for (let i = 0; i < input.length; i += CHUNK_SIZE)
    arr.push(String.fromCharCode.apply(null, input.subarray(i, i + CHUNK_SIZE)));
  const encoded = btoa(arr.join(""));
  return url ? encoded.replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_") : encoded;
}
function decodeBase64(encoded, url = false) {
  if (Uint8Array.fromBase64)
    return Uint8Array.fromBase64(encoded, { alphabet: url ? "base64url" : "base64" });
  if (url) {
    if (encoded.includes("+") || encoded.includes("/"))
      throw new TypeError("Invalid base64url");
    encoded = encoded.replace(/-/g, "+").replace(/_/g, "/");
  }
  const binary = atob(encoded), bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++)
    bytes[i] = binary.charCodeAt(i);
  return bytes;
}
async function digest(algorithm, data) {
  const subtleDigest = `SHA-${algorithm.slice(-3)}`;
  return new Uint8Array(await crypto.subtle.digest(subtleDigest, data));
}

// node_modules/jose/dist/webapi/util/errors.js
var JOSEError = class extends Error {
  static code = "ERR_JOSE_GENERIC";
  code = "ERR_JOSE_GENERIC";
  constructor(message2, options) {
    super(message2, options), this.name = this.constructor.name, Error.captureStackTrace?.(this, this.constructor);
  }
};
var JOSEAlgNotAllowed = class extends JOSEError {
  static code = "ERR_JOSE_ALG_NOT_ALLOWED";
  code = "ERR_JOSE_ALG_NOT_ALLOWED";
};
var JOSENotSupported = class extends JOSEError {
  static code = "ERR_JOSE_NOT_SUPPORTED";
  code = "ERR_JOSE_NOT_SUPPORTED";
};
var JWEDecryptionFailed = class extends JOSEError {
  static code = "ERR_JWE_DECRYPTION_FAILED";
  code = "ERR_JWE_DECRYPTION_FAILED";
  constructor(message2 = "decryption operation failed", options) {
    super(message2, options);
  }
};
var JWEInvalid = class extends JOSEError {
  static code = "ERR_JWE_INVALID";
  code = "ERR_JWE_INVALID";
};

// node_modules/jose/dist/webapi/util/base64url.js
var invalid = "The input to be decoded is not correctly encoded.";
function decode(input) {
  try {
    return decodeBase64(typeof input == "string" ? input : decoder.decode(input), true);
  } catch (cause) {
    throw new TypeError(invalid, { cause });
  }
}
function encode2(input) {
  return encodeBase64(typeof input == "string" ? encoder.encode(input) : input, true);
}

// node_modules/jose/dist/webapi/lib/validate.js
function assertUint8Array(input, label) {
  if (!(input instanceof Uint8Array))
    throw new TypeError(`${label} must be an instance of Uint8Array`);
}
function isObject(input) {
  if (typeof input != "object" || input === null || Object.prototype.toString.call(input) !== "[object Object]")
    return false;
  const prototype = Object.getPrototypeOf(input);
  return prototype === null || Object.getPrototypeOf(prototype) === null;
}
function isDisjoint(...headers) {
  const parameters = /* @__PURE__ */ new Set();
  for (const header of headers)
    if (header)
      for (const parameter of Object.keys(header)) {
        if (parameters.has(parameter))
          return false;
        parameters.add(parameter);
      }
  return true;
}
function assertNotSet(value, name) {
  if (value !== void 0)
    throw new TypeError(`${name} can only be called once`);
}
function decodeBase64url(value, label, ErrorClass) {
  try {
    return decode(value);
  } catch (cause) {
    throw new ErrorClass(`Failed to base64url decode the ${label}`, { cause });
  }
}
function encodeAsciiMember(value, label, ErrorClass) {
  try {
    return encode(value);
  } catch (cause) {
    throw new ErrorClass(`The ${label} is not a valid base64url string`, { cause });
  }
}
function parseJoseHeader(encodedProtectedHeader, ErrorClass, message2) {
  let parsed;
  try {
    parsed = JSON.parse(strictDecoder.decode(decode(encodedProtectedHeader)));
  } catch (cause) {
    throw new ErrorClass(message2, { cause });
  }
  if (!isObject(parsed))
    throw new ErrorClass(message2);
  return parsed;
}
var JWE_RECOGNIZED = { __proto__: null };
function validateAlgorithms(option, algorithms) {
  if (algorithms !== void 0 && (!Array.isArray(algorithms) || algorithms.some((s) => typeof s != "string")))
    throw new TypeError(`"${option}" option must be an array of strings`);
  return algorithms === void 0 ? void 0 : new Set(algorithms);
}
function validateCritDuplicates(Err, protectedHeader) {
  const { crit } = protectedHeader ?? {};
  if (Array.isArray(crit) && new Set(crit).size !== crit.length)
    throw new Err('"crit" (Critical) Header Parameter MUST NOT contain duplicate values');
}
function validateCrit(Err, recognizedDefault, recognizedOption, protectedHeader, joseHeader) {
  if (joseHeader.crit !== void 0 && protectedHeader?.crit === void 0)
    throw new Err('"crit" (Critical) Header Parameter MUST be integrity protected');
  if (!protectedHeader || protectedHeader.crit === void 0)
    return [];
  if (!Array.isArray(protectedHeader.crit) || protectedHeader.crit.length === 0 || protectedHeader.crit.some((input) => typeof input != "string" || input.length === 0))
    throw new Err('"crit" (Critical) Header Parameter MUST be an array of non-empty strings when present');
  const recognized = recognizedOption === void 0 ? recognizedDefault : { __proto__: null, ...recognizedOption, ...recognizedDefault };
  for (const parameter of protectedHeader.crit) {
    if (!(parameter in recognized))
      throw new JOSENotSupported(`Extension Header Parameter "${parameter}" is not recognized`);
    if (!Object.hasOwn(joseHeader, parameter) || joseHeader[parameter] === void 0)
      throw new Err(`Extension Header Parameter "${parameter}" is missing`);
    if (recognized[parameter] && (!Object.hasOwn(protectedHeader, parameter) || protectedHeader[parameter] === void 0))
      throw new Err(`Extension Header Parameter "${parameter}" MUST be integrity protected`);
  }
  return protectedHeader.crit;
}
function serializeJoseHeader(Err, header) {
  let serialized, parsed;
  try {
    serialized = JSON.stringify(header), parsed = JSON.parse(serialized);
  } catch (cause) {
    throw new Err("JOSE Header is not valid JSON", { cause });
  }
  if (!isObject(parsed))
    throw new Err("JOSE Header is not a JSON object");
  return [parsed, serialized];
}

// node_modules/jose/dist/webapi/lib/key.js
var tag = (key) => key[Symbol.toStringTag];
var jwkMatchesOp = (entry, key, usage) => {
  const { alg } = entry;
  if (key.use !== void 0) {
    const expected = usage === "sign" || usage === "verify" ? "sig" : "enc";
    if (key.use !== expected)
      throw new TypeError(`Invalid key for this operation, its "use" must be "${expected}" when present`);
  }
  if (key.alg !== void 0 && key.alg !== alg)
    throw new TypeError(`Invalid key for this operation, its "alg" must be "${alg}" when present`);
  if (Array.isArray(key.key_ops)) {
    const expectedKeyOp = usage === "encrypt" || usage === "decrypt" ? entry.ops?.[usage === "encrypt" ? 0 : 1] : usage;
    if (expectedKeyOp && !key.key_ops.includes(expectedKeyOp))
      throw new TypeError(`Invalid key for this operation, its "key_ops" must include "${expectedKeyOp}" when present`);
  }
};
async function prepareKey(entry, key, usage) {
  const { alg, secret } = entry, requiresPrivateKey = usage === "decrypt" || usage === "sign";
  if (secret && key instanceof Uint8Array)
    return key;
  let normalized, keyObject;
  if (isObject(key)) {
    if (normalized = normalizeJwk(key), typeof normalized.kty != "string")
      throw invalidKeyType(alg, key, secret);
    if (!(secret ? normalized.kty === "oct" && typeof normalized.k == "string" : normalized.kty !== "oct" && (requiresPrivateKey ? normalized.kty === "AKP" && typeof normalized.priv == "string" || typeof normalized.d == "string" : normalized.d === void 0 && normalized.priv === void 0)))
      throw new TypeError(secret ? 'JSON Web Key for symmetric algorithms must have JWK "kty" (Key Type) equal to "oct" and the JWK "k" (Key Value) present' : `JSON Web Key for this operation must be a ${requiresPrivateKey ? "private" : "public"} JWK`);
    if (jwkMatchesOp(entry, normalized, usage), normalized.kty === "oct")
      return decode(normalized.k);
    if (!Object.isFrozen(key)) {
      const { key_ops } = key;
      Array.isArray(key_ops) && Object.freeze(key_ops), Object.freeze(key);
    }
  } else {
    if (!isKeyLike(key))
      throw invalidKeyType(alg, key, secret);
    const expectedType = secret ? "secret" : requiresPrivateKey ? "private" : "public";
    if (key.type !== expectedType && (secret || ["secret", "public", "private"].includes(key.type)))
      throw new TypeError(`${tag(key)} instances must be of type "${expectedType}" for the ${alg} algorithm`);
    if (isCryptoKey(key))
      return key;
    if (keyObject = key, keyObject.type === "secret")
      return keyObject.export();
  }
  cache ||= /* @__PURE__ */ new WeakMap();
  const cacheKey = key;
  let cached = cache.get(cacheKey);
  if (cached?.[alg])
    return cached[alg];
  if (cached || cache.set(cacheKey, cached = {}), keyObject && typeof keyObject.toCryptoKey == "function") {
    const isPublic = keyObject.type === "public", crv = nist[keyObject.asymmetricKeyDetails?.namedCurve], params = entry.resolve?.({ crv, asymmetricKeyType: keyObject.asymmetricKeyType }) ?? entry.subtle;
    return cached[alg] = keyObject.toCryptoKey(params, isPublic, entry.usages[isPublic ? 0 : 1]);
  }
  return normalized ??= keyObject.export({ format: "jwk" }), normalized.alg = alg, cached[alg] = await jwkToKey(entry, normalized);
}
var cache;
var nist = {
  __proto__: null,
  prime256v1: "P-256",
  secp384r1: "P-384",
  secp521r1: "P-521"
};
function assertCryptoKey(key) {
  if (!isCryptoKey(key))
    throw new Error("CryptoKey instance expected");
}
var isCryptoKey = (key) => {
  if (key?.[Symbol.toStringTag] === "CryptoKey")
    return true;
  try {
    return key instanceof CryptoKey;
  } catch {
    return false;
  }
};
var isKeyObject = (key) => key?.[Symbol.toStringTag] === "KeyObject";
var isKeyLike = (key) => isCryptoKey(key) || isKeyObject(key);
function message(msg, actual, ...types) {
  if (types.length > 2) {
    const last = types.pop();
    msg += `one of type ${types.join(", ")}, or ${last}.`;
  } else types.length === 2 ? msg += `one of type ${types[0]} or ${types[1]}.` : msg += `of type ${types[0]}.`;
  return actual == null ? msg += ` Received ${actual}` : typeof actual == "function" && actual.name ? msg += ` Received function ${actual.name}` : typeof actual == "object" && actual != null && actual.constructor?.name && (msg += ` Received an instance of ${actual.constructor.name}`), msg;
}
var invalidKeyInput = (actual, ...types) => message("Key must be ", actual, ...types);
function invalidKeyType(alg, actual, secret) {
  const types = ["CryptoKey", "KeyObject", "JSON Web Key"];
  return secret && types.push("Uint8Array"), new TypeError(message(`Key for the ${alg} algorithm must be `, actual, ...types));
}
var unusable = (name, prop = "algorithm.name") => new TypeError(`CryptoKey does not support this operation, its ${prop} must be ${name}`);
function checkUsage(key, usage) {
  if (usage && !key.usages.includes(usage))
    throw new TypeError(`CryptoKey does not support this operation, its usages must include ${usage}.`);
}
function checkModulusLength(alg, key) {
  const { modulusLength } = key.algorithm;
  if (typeof modulusLength != "number" || modulusLength < 2048)
    throw new TypeError(`${alg} requires key modulusLength to be 2048 bits or larger`);
}
function checkCryptoKey(key, expected, usage) {
  const algorithm = key.algorithm;
  if (algorithm.name !== expected.name)
    throw unusable(expected.name);
  if (expected.hash && algorithm.hash?.name !== expected.hash)
    throw unusable(expected.hash, "algorithm.hash");
  if (expected.namedCurve && algorithm.namedCurve !== expected.namedCurve)
    throw unusable(expected.namedCurve, "algorithm.namedCurve");
  if (expected.length !== void 0 && algorithm.length !== expected.length)
    throw unusable(expected.length, "algorithm.length");
  checkUsage(key, usage);
}
function snapshotJwk(jwk) {
  return { __proto__: null, ...jwk };
}
function normalizeJwk(jwk) {
  const normalized = snapshotJwk(jwk);
  if (normalized.ext !== void 0 && typeof normalized.ext != "boolean")
    throw new TypeError('"ext" (Extractable) Parameter must be a boolean');
  if (normalized.key_ops !== void 0) {
    const value = normalized.key_ops, keyOps = Array.isArray(value) ? [...value] : void 0;
    if (!keyOps || keyOps.some((operation) => typeof operation != "string") || new Set(keyOps).size !== keyOps.length)
      throw new TypeError('"key_ops" (Key Operations) Parameter must be an array of unique strings');
    normalized.key_ops = keyOps;
  }
  return normalized;
}
async function jwkToKey(entry, jwk, extractable) {
  if (!entry.kty.includes(jwk.kty))
    throw new JOSENotSupported('Invalid or unsupported JWK "alg" (Algorithm) Parameter value');
  const algorithm = entry.resolve?.({ kty: jwk.kty, crv: jwk.crv }) ?? entry.subtle, isPrivate = !!(jwk.d || jwk.priv), keyData = { ...jwk, ext: extractable ?? jwk.ext };
  return keyData.kty !== "AKP" && delete keyData.alg, delete keyData.use, crypto.subtle.importKey("jwk", keyData, algorithm, keyData.ext ?? !isPrivate, jwk.key_ops ?? entry.usages[isPrivate ? 1 : 0]);
}
async function rawKey(key, expected, usage, extractable = false) {
  return key instanceof Uint8Array && (key = await crypto.subtle.importKey("raw", key, expected, extractable, [usage])), checkCryptoKey(key, expected, usage), key;
}

// node_modules/jose/dist/webapi/lib/content_encryption.js
var generateCek = (enc) => crypto.getRandomValues(new Uint8Array(enc.cekBits >> 3));
function checkCekLength(cek, expected) {
  const actual = cek.byteLength << 3;
  if (actual !== expected)
    throw new JWEInvalid(`Invalid Content Encryption Key length. Expected ${expected} bits, got ${actual} bits`);
}
var generateIv = (enc) => crypto.getRandomValues(new Uint8Array(enc.ivBits >> 3));
function checkIvLength(enc, iv) {
  if (iv.length << 3 !== enc.ivBits)
    throw new JWEInvalid("Invalid Initialization Vector length");
}
async function cbcKeySetup(enc, cek, usage) {
  if (!(cek instanceof Uint8Array))
    throw new TypeError(invalidKeyInput(cek, "Uint8Array"));
  const keyLengthBits = enc.cekBits >> 1, encKey = await crypto.subtle.importKey("raw", cek.subarray(keyLengthBits >> 3), "AES-CBC", false, [usage]), macKey = await crypto.subtle.importKey("raw", cek.subarray(0, keyLengthBits >> 3), {
    hash: `SHA-${keyLengthBits << 1}`,
    name: "HMAC"
  }, false, ["sign"]);
  return [encKey, macKey, keyLengthBits];
}
async function cbcHmacTag(macKey, macData, keyLengthBits) {
  return new Uint8Array((await crypto.subtle.sign("HMAC", macKey, macData)).slice(0, keyLengthBits >> 3));
}
async function cbcEncrypt(enc, plaintext, cek, iv, aad) {
  const [encKey, macKey, keyLengthBits] = await cbcKeySetup(enc, cek, "encrypt"), ciphertext = new Uint8Array(await crypto.subtle.encrypt({
    iv,
    name: "AES-CBC"
  }, encKey, plaintext)), al = uint64be(aad.length * 8), macData = concat(aad, iv, ciphertext, al), tag2 = await cbcHmacTag(macKey, macData, keyLengthBits);
  return { ciphertext, tag: tag2, iv };
}
async function timingSafeEqual(a, b) {
  const algorithm = { name: "HMAC", hash: "SHA-256" }, key = await crypto.subtle.generateKey(algorithm, false, ["sign", "verify"]), aHmac = await crypto.subtle.sign(algorithm, key, a);
  return crypto.subtle.verify(algorithm, key, aHmac, b);
}
async function cbcDecrypt(enc, cek, ciphertext, iv, tag2, aad) {
  const [encKey, macKey, keyLengthBits] = await cbcKeySetup(enc, cek, "decrypt"), al = uint64be(aad.length * 8), macData = concat(aad, iv, ciphertext, al), expectedTag = await cbcHmacTag(macKey, macData, keyLengthBits);
  try {
    if (await timingSafeEqual(tag2, expectedTag))
      return new Uint8Array(await crypto.subtle.decrypt({ iv, name: "AES-CBC" }, encKey, ciphertext));
  } catch {
  }
  throw new JWEDecryptionFailed();
}
async function encrypt(enc, plaintext, cek, iv, aad) {
  if (!isCryptoKey(cek) && !(cek instanceof Uint8Array))
    throw new TypeError(invalidKeyInput(cek, "CryptoKey", "KeyObject", "Uint8Array", "JSON Web Key"));
  if (iv ? checkIvLength(enc, iv) : iv = generateIv(enc), cek instanceof Uint8Array && checkCekLength(cek, enc.cekBits), enc.cbc)
    return cbcEncrypt(enc, plaintext, cek, iv, aad);
  const encKey = await rawKey(cek, enc.subtle, "encrypt"), encrypted = new Uint8Array(await crypto.subtle.encrypt({
    additionalData: aad,
    iv,
    name: "AES-GCM",
    tagLength: 128
  }, encKey, plaintext));
  return { ciphertext: encrypted.subarray(0, -16), tag: encrypted.subarray(-16), iv };
}
async function decrypt(enc, cek, ciphertext, iv, tag2, aad) {
  if (!isCryptoKey(cek) && !(cek instanceof Uint8Array))
    throw new TypeError(invalidKeyInput(cek, "CryptoKey", "KeyObject", "Uint8Array", "JSON Web Key"));
  if (!iv)
    throw new JWEInvalid("JWE Initialization Vector missing");
  if (!tag2)
    throw new JWEInvalid("JWE Authentication Tag missing");
  if (!enc.cbc && tag2.length !== 16)
    throw new JWEInvalid("Invalid Authentication Tag length");
  if (checkIvLength(enc, iv), cek instanceof Uint8Array && checkCekLength(cek, enc.cekBits), enc.cbc)
    return cbcDecrypt(enc, cek, ciphertext, iv, tag2, aad);
  const encKey = await rawKey(cek, enc.subtle, "decrypt");
  try {
    return new Uint8Array(await crypto.subtle.decrypt({
      additionalData: aad,
      iv,
      name: "AES-GCM",
      tagLength: 128
    }, encKey, concat(ciphertext, tag2)));
  } catch {
    throw new JWEDecryptionFailed();
  }
}

// node_modules/jose/dist/webapi/lib/key_descriptor.js
function table(entries) {
  const out = { __proto__: null };
  for (const alg in entries)
    out[alg] = { ...entries[alg], alg };
  return out;
}

// node_modules/jose/dist/webapi/lib/jwe_algorithms.js
var wrap = [
  ["encrypt", "wrapKey"],
  ["decrypt", "unwrapKey"]
];
var derive = [[], ["deriveBits"]];
var none = [[], []];
function rsaes(bits) {
  return {
    kty: ["RSA"],
    mode: "key-encryption",
    subtle: { name: "RSA-OAEP", hash: `SHA-${bits}` },
    usages: wrap,
    ops: ["wrapKey", "unwrapKey"]
  };
}
function ecdh(mode) {
  return {
    kty: ["EC", "OKP"],
    mode,
    subtle: { name: "ECDH" },
    resolve: ({ kty, crv, asymmetricKeyType }) => {
      if (crv === "X25519" || asymmetricKeyType === "x25519")
        return { name: "X25519" };
      if (kty === "OKP")
        throw new JOSENotSupported('Invalid or unsupported JWK "alg" (Algorithm) Parameter value');
      return { name: "ECDH", namedCurve: crv };
    },
    usages: derive,
    ops: [void 0, "deriveBits"]
  };
}
function aeskw(bits, gcm = false) {
  return {
    kty: ["oct"],
    mode: "key-wrapping",
    secret: true,
    subtle: { name: gcm ? "AES-GCM" : "AES-KW", length: bits },
    usages: none,
    ops: gcm ? ["encrypt", "decrypt"] : ["wrapKey", "unwrapKey"]
  };
}
function pbes2() {
  return {
    kty: ["oct"],
    mode: "key-wrapping",
    secret: true,
    subtle: { name: "PBKDF2" },
    usages: none,
    ops: ["deriveBits", "deriveBits"]
  };
}
var JWE = table({
  dir: {
    kty: ["oct"],
    mode: "direct-encryption",
    secret: true,
    subtle: { name: "AES-GCM" },
    usages: none,
    ops: ["encrypt", "decrypt"]
  },
  "RSA-OAEP": rsaes(1),
  "RSA-OAEP-256": rsaes(256),
  "RSA-OAEP-384": rsaes(384),
  "RSA-OAEP-512": rsaes(512),
  "ECDH-ES": ecdh("direct-key-agreement"),
  "ECDH-ES+A128KW": ecdh("key-agreement-with-key-wrapping"),
  "ECDH-ES+A192KW": ecdh("key-agreement-with-key-wrapping"),
  "ECDH-ES+A256KW": ecdh("key-agreement-with-key-wrapping"),
  A128KW: aeskw(128),
  A192KW: aeskw(192),
  A256KW: aeskw(256),
  A128GCMKW: aeskw(128, true),
  A192GCMKW: aeskw(192, true),
  A256GCMKW: aeskw(256, true),
  "PBES2-HS256+A128KW": pbes2(),
  "PBES2-HS384+A192KW": pbes2(),
  "PBES2-HS512+A256KW": pbes2()
});
var contentOps = ["encrypt", "decrypt"];
function contentEncryption(bits, cbc = false) {
  return {
    kty: ["oct"],
    secret: true,
    subtle: { name: cbc ? "AES-CBC" : "AES-GCM", length: bits },
    usages: none,
    ops: contentOps,
    cekBits: bits,
    ivBits: cbc ? 128 : 96,
    cbc
  };
}
var ENC = table({
  A128GCM: contentEncryption(128),
  A192GCM: contentEncryption(192),
  A256GCM: contentEncryption(256),
  "A128CBC-HS256": contentEncryption(256, true),
  "A192CBC-HS384": contentEncryption(384, true),
  "A256CBC-HS512": contentEncryption(512, true)
});
function unsupported(parameter, name) {
  throw new JOSENotSupported(`Invalid or unsupported "${parameter}" (JWE ${name}) header value`);
}
function jweAlgorithm(alg) {
  return (typeof alg == "string" ? JWE[alg] : void 0) ?? unsupported("alg", "Algorithm");
}
function isJWECEKTransport(algorithm) {
  return algorithm.mode === "key-wrapping" || algorithm.mode === "key-encryption" || algorithm.mode === "key-agreement-with-key-wrapping";
}
function jweEncryption(enc) {
  return (typeof enc == "string" ? ENC[enc] : void 0) ?? unsupported("enc", "Encryption Algorithm");
}

// node_modules/jose/dist/webapi/lib/key_management.js
function checkEcdhCryptoKey(key, usage) {
  if (key.algorithm.name !== "ECDH" && key.algorithm.name !== "X25519")
    throw new TypeError("CryptoKey does not support this operation, its algorithm.name must be ECDH or X25519");
  checkUsage(key, usage);
}
async function aeskwWrap(alg, key, cek) {
  const cryptoKey = await rawKey(key, jweAlgorithm(alg).subtle, "wrapKey", true), cryptoKeyCek = await crypto.subtle.importKey("raw", cek, { hash: "SHA-256", name: "HMAC" }, true, ["sign"]);
  return new Uint8Array(await crypto.subtle.wrapKey("raw", cryptoKeyCek, cryptoKey, "AES-KW"));
}
async function aeskwUnwrap(alg, key, encryptedKey) {
  const cryptoKey = await rawKey(key, jweAlgorithm(alg).subtle, "unwrapKey", true), cryptoKeyCek = await crypto.subtle.unwrapKey("raw", encryptedKey, cryptoKey, "AES-KW", { hash: "SHA-256", name: "HMAC" }, true, ["sign"]);
  return new Uint8Array(await crypto.subtle.exportKey("raw", cryptoKeyCek));
}
function checkRsaKey(alg, key, usage) {
  checkCryptoKey(key, jweAlgorithm(alg).subtle, usage), checkModulusLength(alg, key);
}
async function deriveKey(p2s, alg, p2c, key) {
  if (!(p2s instanceof Uint8Array) || p2s.length < 8)
    throw new JWEInvalid("PBES2 Salt Input must be 8 or more octets");
  if (!Number.isSafeInteger(p2c) || Math.sign(p2c) !== 1)
    throw new JWEInvalid("PBES2 Count Input must be a positive integer");
  const salt = concat(encode(alg), Uint8Array.of(0), p2s), keyLengthBits = parseInt(alg.slice(13, 16), 10), subtleAlg = {
    hash: `SHA-${alg.slice(8, 11)}`,
    iterations: p2c,
    name: "PBKDF2",
    salt
  }, cryptoKey = await rawKey(key, jweAlgorithm(alg).subtle, "deriveBits");
  return new Uint8Array(await crypto.subtle.deriveBits(subtleAlg, cryptoKey, keyLengthBits));
}
function lengthAndInput(input) {
  return concat(uint32be(input.length), input);
}
async function concatKdf(Z, keyDataLength, OtherInfo) {
  const dkLen = keyDataLength >> 3, hashLen = 32, reps = Math.ceil(dkLen / hashLen), dk = new Uint8Array(reps * hashLen);
  for (let i = 1; i <= reps; i++) {
    const hashResult = await digest("sha256", concat(uint32be(i), Z, OtherInfo));
    dk.set(hashResult, (i - 1) * hashLen);
  }
  return dk.slice(0, dkLen);
}
async function ecdhesDeriveKey(publicKey, privateKey, algorithmId, keyDataLength, apu = new Uint8Array(), apv = new Uint8Array()) {
  checkEcdhCryptoKey(publicKey), checkEcdhCryptoKey(privateKey, "deriveBits");
  const otherInfo = concat(lengthAndInput(encode(algorithmId)), lengthAndInput(apu), lengthAndInput(apv), uint32be(keyDataLength)), Z = new Uint8Array(await crypto.subtle.deriveBits({
    name: publicKey.algorithm.name,
    public: publicKey
  }, privateKey, publicKey.algorithm.name === "X25519" ? 256 : Math.ceil(parseInt(publicKey.algorithm.namedCurve.slice(-3), 10) / 8) << 3));
  return concatKdf(Z, keyDataLength, otherInfo);
}
function assertEcdhKey(key) {
  assertCryptoKey(key);
  const curve = key.algorithm.namedCurve;
  if (curve !== "P-256" && curve !== "P-384" && curve !== "P-521" && key.algorithm.name !== "X25519")
    throw new JOSENotSupported("ECDH with the provided key is not allowed or not supported by your javascript runtime");
}
function partyInfo(joseHeader, name) {
  const value = joseHeader[name];
  if (value !== void 0) {
    if (typeof value != "string")
      throw new JWEInvalid(`JOSE Header "${name}" (Agreement Party${name === "apu" ? "U" : "V"}Info) invalid`);
    return decodeBase64url(value, name, JWEInvalid);
  }
}
function checkPartyInfo(apu, apv) {
  if (!(apu === void 0 || apv === void 0 || apu.byteLength !== apv.byteLength)) {
    for (let i = 0; i < apu.byteLength; i++)
      if (apu[i] !== apv[i])
        return;
    throw new JWEInvalid('JOSE Header "apu" and "apv" values must be distinct');
  }
}
function assertEncryptedKey(encryptedKey) {
  if (encryptedKey === void 0)
    throw new JWEInvalid("JWE Encrypted Key missing");
}
function assertNoEncryptedKey(encryptedKey) {
  if (encryptedKey !== void 0)
    throw new JWEInvalid("Encountered unexpected JWE Encrypted Key");
}
function validateMaxPBES2Count(value) {
  if (value !== void 0 && value !== 1 / 0 && (!Number.isSafeInteger(value) || value < 1))
    throw new TypeError("maxPBES2Count must be a positive safe integer or Infinity");
}
async function decryptKeyManagement(entry, enc, key, encryptedKey, joseHeader, maxPBES2Count) {
  const { alg } = entry, mode = entry.mode;
  if (mode === "direct-encryption")
    return assertNoEncryptedKey(encryptedKey), key;
  const direct = mode === "direct-key-agreement";
  switch (direct ? assertNoEncryptedKey(encryptedKey) : assertEncryptedKey(encryptedKey), entry.subtle.name) {
    case "ECDH": {
      const { epk } = joseHeader;
      if (!isObject(epk) || ["d", "k", "p", "q", "dp", "dq", "qi", "oth", "priv"].some((parameter) => Object.hasOwn(epk, parameter)))
        throw new JWEInvalid('JOSE Header "epk" (Ephemeral Public Key) missing or invalid');
      assertEcdhKey(key);
      const ephemeralPublicKey = await jwkToKey(entry, epk), partyUInfo = partyInfo(joseHeader, "apu"), partyVInfo = partyInfo(joseHeader, "apv");
      checkPartyInfo(partyUInfo, partyVInfo);
      const derivedKey = await ecdhesDeriveKey(ephemeralPublicKey, key, direct ? enc.alg : alg, direct ? enc.cekBits : parseInt(alg.slice(-5, -2), 10), partyUInfo, partyVInfo);
      if (direct)
        return derivedKey;
      key = derivedKey;
      break;
    }
    case "RSA-OAEP":
      return assertCryptoKey(key), checkRsaKey(alg, key, "decrypt"), new Uint8Array(await crypto.subtle.decrypt("RSA-OAEP", key, encryptedKey));
    case "PBKDF2": {
      if (typeof joseHeader.p2c != "number")
        throw new JWEInvalid('JOSE Header "p2c" (PBES2 Count) missing or invalid');
      validateMaxPBES2Count(maxPBES2Count);
      const p2cLimit = maxPBES2Count ?? 1e4;
      if (joseHeader.p2c > p2cLimit)
        throw new JWEInvalid('JOSE Header "p2c" (PBES2 Count) out is of acceptable bounds');
      if (typeof joseHeader.p2s != "string")
        throw new JWEInvalid('JOSE Header "p2s" (PBES2 Salt) missing or invalid');
      const p2s = decodeBase64url(joseHeader.p2s, "p2s", JWEInvalid);
      key = await deriveKey(p2s, alg, joseHeader.p2c, key);
      break;
    }
    case "AES-GCM": {
      if (typeof joseHeader.iv != "string")
        throw new JWEInvalid('JOSE Header "iv" (Initialization Vector) missing or invalid');
      if (typeof joseHeader.tag != "string")
        throw new JWEInvalid('JOSE Header "tag" (Authentication Tag) missing or invalid');
      const iv = decodeBase64url(joseHeader.iv, "iv", JWEInvalid), tag2 = decodeBase64url(joseHeader.tag, "tag", JWEInvalid);
      if (iv.byteLength !== 12)
        throw new JWEInvalid("Invalid Initialization Vector length");
      if (tag2.byteLength !== 16)
        throw new JWEInvalid("Invalid Authentication Tag length");
      return decrypt(jweEncryption(alg.slice(0, -2)), key, encryptedKey, iv, tag2, new Uint8Array());
    }
  }
  return aeskwUnwrap(alg.slice(-6), key, encryptedKey);
}
async function encryptKeyManagement(entry, enc, inputKey, joseHeader, providedCek, providedParameters = {}) {
  const { alg, mode } = entry, transport = isJWECEKTransport(entry);
  if (providedCek !== void 0 && !transport)
    throw new TypeError(`setContentEncryptionKey cannot be called with JWE "alg" (Algorithm) Header ${alg}`);
  let key = await prepareKey(mode === "direct-encryption" ? enc : entry, inputKey, "encrypt");
  if (mode === "direct-encryption")
    return [key, void 0, void 0];
  const cek = transport ? providedCek ?? generateCek(enc) : void 0;
  cek && checkCekLength(cek, enc.cekBits);
  let encryptedKey, parameters;
  switch (entry.subtle.name) {
    case "ECDH": {
      assertEcdhKey(key);
      const { apu: providedApu, apv: providedApv } = providedParameters;
      providedApu !== void 0 && assertUint8Array(providedApu, '"apu"'), providedApv !== void 0 && assertUint8Array(providedApv, '"apv"');
      const apu = providedApu ?? partyInfo(joseHeader, "apu"), apv = providedApv ?? partyInfo(joseHeader, "apv");
      checkPartyInfo(apu, apv);
      let ephemeralPrivateKey;
      providedParameters.epk !== void 0 ? ephemeralPrivateKey = await prepareKey(entry, providedParameters.epk, "decrypt") : ephemeralPrivateKey = (await crypto.subtle.generateKey(key.algorithm, true, ["deriveBits"])).privateKey;
      const subtle = crypto.subtle;
      let exportableEpk = ephemeralPrivateKey;
      if (!exportableEpk.extractable) {
        if (typeof subtle.getPublicKey != "function")
          throw new TypeError('CryptoKey for "epk" must be extractable');
        exportableEpk = await subtle.getPublicKey(ephemeralPrivateKey, []);
      }
      const { x, y, crv, kty } = await subtle.exportKey("jwk", exportableEpk), direct = mode === "direct-key-agreement", derivedKey = await ecdhesDeriveKey(key, ephemeralPrivateKey, direct ? enc.alg : alg, direct ? enc.cekBits : parseInt(alg.slice(-5, -2), 10), apu, apv), epk = { x, crv, kty };
      if (kty === "EC" && (epk.y = y), parameters = { epk }, providedApu !== void 0 && (parameters.apu = encode2(providedApu)), providedApv !== void 0 && (parameters.apv = encode2(providedApv)), direct)
        return [derivedKey, void 0, parameters];
      key = derivedKey;
      break;
    }
    case "RSA-OAEP": {
      assertCryptoKey(key), checkRsaKey(alg, key, "encrypt"), encryptedKey = new Uint8Array(await crypto.subtle.encrypt("RSA-OAEP", key, cek));
      break;
    }
    case "PBKDF2": {
      const { p2c = 2048, p2s = crypto.getRandomValues(new Uint8Array(16)) } = providedParameters;
      key = await deriveKey(p2s, alg, p2c, key), parameters = { p2c, p2s: encode2(p2s) };
      break;
    }
    case "AES-GCM": {
      const iv = providedParameters.iv === void 0 ? crypto.getRandomValues(new Uint8Array(12)) : providedParameters.iv;
      if (!(iv instanceof Uint8Array))
        throw new TypeError('"iv" must be an instance of Uint8Array');
      const wrapped = await encrypt(jweEncryption(alg.slice(0, -2)), cek, key, iv, new Uint8Array());
      encryptedKey = wrapped.ciphertext, parameters = { iv: encode2(wrapped.iv), tag: encode2(wrapped.tag) };
    }
  }
  if (encryptedKey ??= await aeskwWrap(alg.slice(-6), key, cek), !(encryptedKey instanceof Uint8Array) || !encryptedKey.byteLength)
    throw new TypeError("JWE key management algorithm did not produce an Encrypted Key");
  return [cek, encryptedKey, parameters];
}

// node_modules/jose/dist/webapi/lib/deflate.js
function validateZip(joseHeader, protectedHeader) {
  if (joseHeader.zip !== void 0 && joseHeader.zip !== "DEF")
    throw new JOSENotSupported('Unsupported JWE "zip" (Compression Algorithm) Header Parameter value.');
  if (joseHeader.zip !== void 0 && !protectedHeader?.zip)
    throw new JWEInvalid('JWE "zip" (Compression Algorithm) Header Parameter MUST be in a protected header.');
}
function supported(name) {
  if (typeof globalThis[name] > "u")
    throw new JOSENotSupported(`JWE "zip" (Compression Algorithm) Header Parameter requires the ${name} API.`);
}
async function transform(stream, input, maxLength = 1 / 0) {
  const writer = stream.writable.getWriter();
  writer.write(input).catch(() => {
  }), writer.close().catch(() => {
  });
  const chunks = [];
  let length = 0;
  const reader = stream.readable.getReader();
  for (; ; ) {
    const { value, done } = await reader.read();
    if (done)
      break;
    if (chunks.push(value), length += value.byteLength, maxLength !== 1 / 0 && length > maxLength)
      throw new JWEInvalid("Decompressed plaintext exceeded the configured limit");
  }
  return concat(...chunks);
}
async function compress(input) {
  return supported("CompressionStream"), transform(new CompressionStream("deflate-raw"), input);
}
async function decompress(input, maxLength) {
  return supported("DecompressionStream"), transform(new DecompressionStream("deflate-raw"), input, maxLength);
}

// node_modules/jose/dist/webapi/lib/jwe_decrypt.js
function shareJWE(jwe) {
  const { protected: encodedProtected, ciphertext, iv, tag: tag2, aad } = jwe;
  let protectedHeader;
  return encodedProtected !== void 0 && (protectedHeader = parseJoseHeader(encodedProtected, JWEInvalid, "JWE Protected Header is invalid")), [
    protectedHeader,
    decodeBase64url(ciphertext, "ciphertext", JWEInvalid),
    iv !== void 0 ? decodeBase64url(iv, "iv", JWEInvalid) : void 0,
    tag2 !== void 0 ? decodeBase64url(tag2, "tag", JWEInvalid) : void 0,
    encodeAsciiMember((encodedProtected ?? "") + (aad !== void 0 ? `.${aad}` : ""), "aad", JWEInvalid)
  ];
}
function prepareDecrypt(options) {
  return [
    options && validateAlgorithms("keyManagementAlgorithms", options.keyManagementAlgorithms),
    options && validateAlgorithms("contentEncryptionAlgorithms", options.contentEncryptionAlgorithms),
    options?.crit,
    options?.maxPBES2Count,
    options?.maxDecompressedLength
  ];
}
async function decryptJWE(jwe, shared, key, token = shareJWE(jwe)) {
  const [protectedHeader, ciphertext, iv, tag2, additionalAuthenticatedData] = token, { header, unprotected, aad } = jwe;
  let joseHeader;
  if (header !== void 0 || unprotected !== void 0) {
    if (!isDisjoint(protectedHeader, header, unprotected))
      throw new JWEInvalid("JWE Protected, JWE Unprotected Header, and JWE Per-Recipient Unprotected Header Parameter names must be disjoint");
    joseHeader = { ...protectedHeader, ...header, ...unprotected };
  } else
    joseHeader = protectedHeader ?? {};
  const [keyManagementAlgorithms, contentEncryptionAlgorithms, crit, maxPBES2Count, maxDecompressedLength] = shared, { encrypted_key: encodedKey } = jwe;
  validateCrit(JWEInvalid, JWE_RECOGNIZED, crit, protectedHeader, joseHeader), validateZip(joseHeader, protectedHeader);
  const { alg, enc } = joseHeader;
  if (typeof alg != "string" || !alg)
    throw new JWEInvalid("missing JWE Algorithm (alg) in JWE Header");
  const selected = JWE[alg];
  if (encodedKey === "" && (!selected || !isJWECEKTransport(selected)))
    throw new JWEInvalid("JWE Encrypted Key incorrect type");
  const integrated = selected?.mode === "integrated-encryption";
  if (!integrated && (typeof enc != "string" || !enc))
    throw new JWEInvalid("missing JWE Encryption Algorithm (enc) in JWE Header");
  if (keyManagementAlgorithms && !keyManagementAlgorithms.has(alg) || !keyManagementAlgorithms && alg.startsWith("PBES2"))
    throw new JOSEAlgNotAllowed('"alg" (Algorithm) Header Parameter value not allowed');
  let encEntry;
  if (integrated) {
    if (enc !== void 0)
      throw new JWEInvalid('JWE "enc" (Encryption Algorithm) Header Parameter must not be present for integrated encryption');
    if (iv?.byteLength)
      throw new JWEInvalid("JWE Initialization Vector must be empty for integrated encryption");
    if (tag2?.byteLength)
      throw new JWEInvalid("JWE Authentication Tag must be empty for integrated encryption");
  } else {
    if (contentEncryptionAlgorithms && !contentEncryptionAlgorithms.has(enc))
      throw new JOSEAlgNotAllowed('"enc" (Encryption Algorithm) Header Parameter value not allowed');
    encEntry = jweEncryption(enc);
  }
  let encryptedKey;
  if (encodedKey !== void 0)
    try {
      encryptedKey = decodeBase64url(encodedKey, "encrypted_key", JWEInvalid);
    } catch (error) {
      if (!selected || !isJWECEKTransport(selected))
        throw error;
      encryptedKey = new Uint8Array();
    }
  let resolvedKey = false;
  typeof key == "function" && (key = await key(protectedHeader, jwe), resolvedKey = true);
  const algEntry = selected ?? jweAlgorithm(alg);
  isJWECEKTransport(algEntry) && encryptedKey === void 0 && (encryptedKey = new Uint8Array());
  const k = await prepareKey(algEntry.mode === "direct-encryption" ? encEntry : algEntry, key, "decrypt");
  let plaintext;
  if (algEntry.mode === "integrated-encryption")
    plaintext = await algEntry.decrypt(k, encryptedKey, ciphertext, additionalAuthenticatedData, protectedHeader, joseHeader);
  else {
    const encryption = encEntry;
    let cek;
    try {
      cek = await decryptKeyManagement(algEntry, encryption, k, encryptedKey, joseHeader, maxPBES2Count), isJWECEKTransport(algEntry) && cek instanceof Uint8Array && cek.byteLength << 3 !== encryption.cekBits && (cek = generateCek(encryption));
    } catch (err) {
      if (err instanceof TypeError || err instanceof JWEInvalid || err instanceof JOSENotSupported)
        throw err;
      cek = generateCek(encryption);
    }
    plaintext = await decrypt(encryption, cek, ciphertext, iv, tag2, additionalAuthenticatedData);
  }
  if (joseHeader.zip === "DEF") {
    const decompressionLimit = maxDecompressedLength ?? 25e4;
    if (decompressionLimit === 0)
      throw new JOSENotSupported('JWE "zip" (Compression Algorithm) Header Parameter is not supported.');
    if (decompressionLimit !== 1 / 0 && (!Number.isSafeInteger(decompressionLimit) || decompressionLimit < 1))
      throw new TypeError("maxDecompressedLength must be 0, a positive safe integer, or Infinity");
    plaintext = await decompress(plaintext, decompressionLimit).catch((cause) => {
      throw cause instanceof JWEInvalid ? cause : new JWEInvalid("Failed to decompress plaintext", { cause });
    });
  }
  return {
    plaintext,
    ...protectedHeader && { protectedHeader },
    ...aad !== void 0 && {
      additionalAuthenticatedData: decodeBase64url(aad, "aad", JWEInvalid)
    },
    ...unprotected && { sharedUnprotectedHeader: unprotected },
    ...header && { unprotectedHeader: header },
    ...resolvedKey && { key: k }
  };
}
async function decryptCompact(jwe, shared, key) {
  if (jwe instanceof Uint8Array && (jwe = decoder.decode(jwe)), typeof jwe != "string")
    throw new JWEInvalid("Compact JWE must be a string or Uint8Array");
  const { 0: protectedHeader, 1: encryptedKey, 2: iv, 3: ciphertext, 4: tag2, length } = jwe.split(".");
  if (length !== 5)
    throw new JWEInvalid("Invalid Compact JWE");
  return decryptJWE({
    ciphertext,
    iv: iv || void 0,
    protected: protectedHeader,
    tag: tag2 || void 0,
    encrypted_key: encryptedKey || void 0
  }, shared, key);
}

// node_modules/jose/dist/webapi/jwe/compact/decrypt.js
async function compactDecrypt(jwe, key, options) {
  return decryptCompact(jwe, prepareDecrypt(options), key);
}

// node_modules/jose/dist/webapi/lib/jwe_encrypt.js
function checkDisjoint(protectedHeader, unprotectedHeader, sharedUnprotectedHeader) {
  if (!isDisjoint(protectedHeader, unprotectedHeader, sharedUnprotectedHeader))
    throw new JWEInvalid("JWE Protected, JWE Shared Unprotected and JWE Per-Recipient Header Parameter names must be disjoint");
}
function checkEncryptHeaders(input, options, sharedHeadersNormalized = false) {
  if (!input[1] && !input[2] && !input[3])
    throw new JWEInvalid("either setProtectedHeader, setUnprotectedHeader, or sharedUnprotectedHeader must be called before #encrypt()");
  options !== void 0 && (input[8] = options?.crit);
  let [, protectedHeader, unprotectedHeader, sharedUnprotectedHeader, aad, cek, iv, keyManagementParameters, crit] = input;
  if (aad !== void 0 && assertUint8Array(aad, "JWE Additional Authenticated Data"), cek !== void 0 && assertUint8Array(cek, "JWE Content Encryption Key"), iv !== void 0 && assertUint8Array(iv, "JWE Initialization Vector"), !sharedHeadersNormalized && protectedHeader !== void 0 && (protectedHeader = serializeJoseHeader(JWEInvalid, protectedHeader)[0], input[1] = protectedHeader), unprotectedHeader !== void 0 && (unprotectedHeader = serializeJoseHeader(JWEInvalid, unprotectedHeader)[0], input[2] = unprotectedHeader), !sharedHeadersNormalized && sharedUnprotectedHeader !== void 0 && (sharedUnprotectedHeader = serializeJoseHeader(JWEInvalid, sharedUnprotectedHeader)[0], input[3] = sharedUnprotectedHeader), keyManagementParameters !== void 0 && !isObject(keyManagementParameters))
    throw new TypeError("JWE Key Management Parameters must be an object");
  checkDisjoint(protectedHeader, unprotectedHeader, sharedUnprotectedHeader);
  const joseHeader = {
    ...protectedHeader,
    ...unprotectedHeader,
    ...sharedUnprotectedHeader
  };
  validateCritDuplicates(JWEInvalid, protectedHeader), validateCrit(JWEInvalid, JWE_RECOGNIZED, crit, protectedHeader, joseHeader), validateZip(joseHeader, protectedHeader);
  const { alg, enc } = joseHeader;
  if (typeof alg != "string" || !alg)
    throw new JWEInvalid('JWE "alg" (Algorithm) Header Parameter missing or invalid');
  const algEntry = JWE[alg];
  if (algEntry?.mode === "integrated-encryption") {
    if (enc !== void 0)
      throw new JWEInvalid('JWE "enc" (Encryption Algorithm) Header Parameter must not be present for integrated encryption');
    if (cek !== void 0)
      throw new TypeError(`setContentEncryptionKey cannot be called with JWE "alg" (Algorithm) Header ${alg}`);
    if (iv !== void 0)
      throw new TypeError(`setInitializationVector cannot be called with JWE "alg" (Algorithm) Header ${alg}`);
    return [joseHeader, void 0, algEntry];
  }
  if (typeof enc != "string" || !enc)
    throw new JWEInvalid('JWE "enc" (Encryption Algorithm) Header Parameter missing or invalid');
  return [joseHeader, jweEncryption(enc), algEntry];
}
async function encryptJWE(input, checked, key) {
  const [joseHeader, encEntry, selected] = checked, [inputPlaintext, inputProtectedHeader, inputUnprotectedHeader, sharedUnprotectedHeader, aad, providedCek, inputIv, keyManagementParameters, , unprotectedParameters] = input;
  let protectedHeader = inputProtectedHeader, unprotectedHeader = inputUnprotectedHeader;
  const algEntry = selected ?? jweAlgorithm(joseHeader.alg);
  let encryptedKey, parameters, cek;
  algEntry.mode === "integrated-encryption" ? cek = await prepareKey(algEntry, key, "encrypt") : [cek, encryptedKey, parameters] = await encryptKeyManagement(algEntry, encEntry, key, joseHeader, providedCek, keyManagementParameters), parameters && (unprotectedParameters ? unprotectedHeader = unprotectedHeader ? { ...unprotectedHeader, ...parameters } : parameters : protectedHeader = protectedHeader ? { ...protectedHeader, ...parameters } : parameters, checkDisjoint(protectedHeader, unprotectedHeader, sharedUnprotectedHeader));
  const encodedProtectedHeader = protectedHeader ? encode2(JSON.stringify(protectedHeader)) : "", encodedAad = aad?.byteLength ? encode2(aad) : void 0, additionalAuthenticatedData = encode(encodedAad ? `${encodedProtectedHeader}.${encodedAad}` : encodedProtectedHeader);
  let plaintext = inputPlaintext;
  joseHeader.zip === "DEF" && (plaintext = await compress(plaintext).catch((cause) => {
    throw new JWEInvalid("Failed to compress plaintext", { cause });
  }));
  let ciphertext, tag2, iv;
  algEntry.mode === "integrated-encryption" ? [encryptedKey, ciphertext] = await algEntry.encrypt(cek, plaintext, additionalAuthenticatedData, protectedHeader, joseHeader, keyManagementParameters) : { ciphertext, tag: tag2, iv } = await encrypt(encEntry, plaintext, cek, inputIv, additionalAuthenticatedData);
  const jwe = {
    ciphertext: encode2(ciphertext)
  };
  return iv && (jwe.iv = encode2(iv)), tag2 && (jwe.tag = encode2(tag2)), encryptedKey?.byteLength && (jwe.encrypted_key = encode2(encryptedKey)), encodedAad && (jwe.aad = encodedAad), protectedHeader && (jwe.protected = encodedProtectedHeader), sharedUnprotectedHeader && (jwe.unprotected = sharedUnprotectedHeader), unprotectedHeader && (jwe.header = unprotectedHeader), jwe;
}
async function createJWE(input, key, options) {
  return encryptJWE(input, checkEncryptHeaders(input, options), key);
}
function compactJWE(jwe) {
  return [jwe.protected, jwe.encrypted_key, jwe.iv, jwe.ciphertext, jwe.tag].join(".");
}

// node_modules/jose/dist/webapi/jwe/compact/encrypt.js
var CompactEncrypt = class {
  #input;
  constructor(plaintext) {
    assertUint8Array(plaintext, "plaintext"), this.#input = [plaintext];
  }
  setContentEncryptionKey(cek) {
    return assertNotSet(this.#input[5], "setContentEncryptionKey"), this.#input[5] = cek, this;
  }
  setInitializationVector(iv) {
    return assertNotSet(this.#input[6], "setInitializationVector"), this.#input[6] = iv, this;
  }
  setProtectedHeader(protectedHeader) {
    return assertNotSet(this.#input[1], "setProtectedHeader"), this.#input[1] = protectedHeader, this;
  }
  setKeyManagementParameters(parameters) {
    return assertNotSet(this.#input[7], "setKeyManagementParameters"), this.#input[7] = parameters, this;
  }
  async encrypt(key, options) {
    return compactJWE(await createJWE([...this.#input], key, options));
  }
};

// node_modules/jose/dist/webapi/util/decode_protected_header.js
function decodeProtectedHeader(token) {
  let encodedProtectedHeader;
  if (typeof token == "string") {
    const parts = token.split(".");
    (parts.length === 3 || parts.length === 5) && ([encodedProtectedHeader] = parts);
  } else if (typeof token == "object" && token)
    if ("protected" in token)
      encodedProtectedHeader = token.protected;
    else
      throw new TypeError("Token does not contain a Protected Header");
  const invalid2 = "Invalid Token or Protected Header formatting";
  if (typeof encodedProtectedHeader != "string" || !encodedProtectedHeader)
    throw new TypeError(invalid2);
  return parseJoseHeader(encodedProtectedHeader, TypeError, invalid2);
}
export {
  CompactEncrypt,
  compactDecrypt,
  decodeProtectedHeader
};
