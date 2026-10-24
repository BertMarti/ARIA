// Protocolo RUNA v1 (solo cifrar), el mismo que la web de RUNA y que protocolo.py. Solo usa Web Crypto.
// Se ejecuta en el navegador: la llave (K) se genera aquí y viaja únicamente en el fragmento «#» del enlace.
const enc = new TextEncoder();
export const BLOQUES = [1, 4, 16, 64, 256, 1024].map((k) => k * 1024);
export const MAX_TEXTO = 100000;

export function b64url(bytes) {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export const hex = (bytes) => Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");

function unir(...partes) {
  const out = new Uint8Array(partes.reduce((n, p) => n + p.length, 0));
  let i = 0;
  for (const p of partes) { out.set(p, i); i += p.length; }
  return out;
}

async function hkdf(ikm, salt, info, bits) {
  const base = await crypto.subtle.importKey("raw", ikm, "HKDF", false, ["deriveBits"]);
  return new Uint8Array(await crypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt, info: enc.encode(info) }, base, bits));
}

/** salt, clave de cifrado, token (prueba de contraseña) y prueba de enlace, como protocolo._derivar. */
export async function derivar(clave, contrasena) {
  const salt = await hkdf(clave, new Uint8Array(), "runa/v1/salt", 128);
  let ikm = clave;
  if (contrasena) {
    const pw = await crypto.subtle.importKey("raw", enc.encode(contrasena.normalize("NFC")), "PBKDF2", false, ["deriveBits"]);
    const p = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt, iterations: 600000 }, pw, 256);
    ikm = unir(clave, new Uint8Array(p));
  }
  return {
    salt,
    enc: await hkdf(ikm, salt, "runa/v1/enc", 256),
    token: await hkdf(ikm, salt, "runa/v1/auth", 256),
    link: await hkdf(clave, salt, "runa/v1/link", 256),
  };
}

/** `u32 BE longitud | {"text": …} | ceros` hasta el bloque siguiente (oculta la longitud real). */
export function empaquetar(texto) {
  const cab = enc.encode(JSON.stringify({ text: texto }));
  const largo = new Uint8Array(4);
  new DataView(largo.buffer).setUint32(0, cab.length, false);
  const cuerpo = unir(largo, cab);
  const bloque = BLOQUES.find((b) => b >= cuerpo.length);
  if (!bloque) throw new Error("El secreto es demasiado grande");
  const out = new Uint8Array(bloque);
  out.set(cuerpo);
  return out;
}

/**
 * Cifra el texto. Devuelve lo que se sube (cifrado y dos SHA-256) y el fragmento del enlace, que nunca se sube.
 * `_clave` e `_iv` solo existen para las pruebas con vectores conocidos.
 */
export async function sellar(texto, contrasena = "", _clave, _iv) {
  if (texto.length > MAX_TEXTO) throw new Error("El texto supera el máximo");
  const clave = _clave ?? crypto.getRandomValues(new Uint8Array(32));
  const iv = _iv ?? crypto.getRandomValues(new Uint8Array(12));
  const d = await derivar(clave, contrasena);
  const k = await crypto.subtle.importKey("raw", d.enc, "AES-GCM", false, ["encrypt"]);
  const aad = enc.encode(`runa/v1|${contrasena ? "p" : "-"}`);
  const cifrado = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: aad }, k, empaquetar(texto)));
  const sha = async (b) => hex(new Uint8Array(await crypto.subtle.digest("SHA-256", b)));
  return {
    ciphertext: b64url(unir(iv, cifrado)),
    verifier: await sha(d.token),
    linkVerifier: await sha(d.link),
    fragmento: `v1.${b64url(clave)}${contrasena ? ".p" : ""}`,
  };
}
