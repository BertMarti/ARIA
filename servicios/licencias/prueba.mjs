import assert from "node:assert/strict";
import { test } from "node:test";
import { generateKeyPair, sign, verify } from "node:crypto";
import { promisify } from "node:util";
import worker from "./worker.js";

const generar = promisify(generateKeyPair);
const texto = (obj) => JSON.stringify(obj);

async function contexto({ tienda = "10", respuestaTienda = tienda, producto = "20", estado = "active", valida = true } = {}) {
  const { privateKey, publicKey } = await generar("ed25519", {});
  const der = privateKey.export({ type: "pkcs8", format: "der" }).toString("base64");
  const kv = new Map();
  const env = { LS_STORE_ID: tienda, LS_PRODUCT_ID: producto, CLAVE_PRIVADA_PKCS8_B64: der,
    LICENCIAS: { get: async k => kv.get(k) ?? null, put: async (k, v) => kv.set(k, v) } };
  const anterior = globalThis.fetch;
  const llamadas = [];
  // Forma real de la License API de Lemon Squeezy: campos en el primer nivel.
  globalThis.fetch = async (url, opciones) => {
    const body = new URLSearchParams(opciones.body);
    llamadas.push({ url: String(url), body: Object.fromEntries(body) });
    const comun = { error: null, license_key: { id: 1, status: estado, key: body.get("license_key") },
      meta: { store_id: Number(respuestaTienda), product_id: Number(producto) } };
    if (String(url).endsWith("/activate"))
      return new Response(texto({ ...comun, activated: valida, instance: { id: "instancia-1", name: body.get("instance_name") } }), { status: 200 });
    return new Response(texto({ ...comun, valid: valida, instance: { id: body.get("instance_id") } }), { status: 200 });
  };
  return { env, publicKey, llamadas, restaurar: () => { globalThis.fetch = anterior; } };
}

function peticion(ruta, cuerpo) {
  return new Request(`https://licencias.example.com${ruta}`, {
    method: "POST", headers: { "content-type": "application/json", "CF-Connecting-IP": "203.0.113.10" },
    body: texto(cuerpo),
  });
}

test("activa y devuelve una licencia verificable", async () => {
  const c = await contexto();
  try {
    const r = await worker.fetch(peticion("/v1/activar", { clave: "clave-demo-1", instalacion: "instalacion-demo-1" }), c.env);
    assert.equal(r.status, 200);
    const licencia = (await r.json()).licencia;
    const [p, f] = licencia.split(".");
    assert.equal(verify(null, Buffer.from(p, "base64url"), c.publicKey, Buffer.from(f, "base64url")), true);
  } finally { c.restaurar(); }
});

test("rechaza una tienda distinta, una caducada y una entrada mala", async () => {
  const otra = await contexto({ respuestaTienda: "99" });
  try {
    const r = await worker.fetch(peticion("/v1/activar", { clave: "clave-demo-1", instalacion: "instalacion-demo-1" }), otra.env);
    assert.equal(r.status, 403);
  } finally { otra.restaurar(); }
  const caducada = await contexto({ estado: "expired" });
  try {
    assert.equal((await worker.fetch(peticion("/v1/activar", { clave: "clave-demo-1", instalacion: "instalacion-demo-1" }), caducada.env)).status, 403);
  } finally { caducada.restaurar(); }
  const mala = await contexto();
  try {
    assert.equal((await worker.fetch(peticion("/v1/activar", { clave: "x", instalacion: "corta" }), mala.env)).status, 400);
  } finally { mala.restaurar(); }
});

test("renovar valida la misma instancia que se activó", async () => {
  const c = await contexto();
  try {
    const cuerpo = { clave: "clave-demo-1", instalacion: "instalacion-demo-1" };
    assert.equal((await worker.fetch(peticion("/v1/activar", cuerpo), c.env)).status, 200);
    assert.equal((await worker.fetch(peticion("/v1/renovar", cuerpo), c.env)).status, 200);
    assert.ok(c.llamadas[0].url.endsWith("/activate"));
    assert.ok(c.llamadas[1].url.endsWith("/validate"));
    assert.equal(c.llamadas[1].body.instance_id, "instancia-1");
  } finally { c.restaurar(); }
});

test("una clave desactivada no renueva", async () => {
  const c = await contexto({ estado: "disabled" });
  try {
    assert.equal((await worker.fetch(peticion("/v1/renovar", { clave: "clave-demo-1", instalacion: "instalacion-demo-1" }), c.env)).status, 403);
  } finally { c.restaurar(); }
});
