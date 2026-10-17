const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };

function respuesta(cuerpo, estado = 200) {
  return new Response(JSON.stringify(cuerpo), { status: estado, headers: JSON_HEADERS });
}

function b64url(bytes) {
  let texto = "";
  for (const byte of new Uint8Array(bytes)) texto += String.fromCharCode(byte);
  return btoa(texto).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64bytes(texto) {
  const normal = texto.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - texto.length % 4) % 4);
  const binario = atob(normal);
  return Uint8Array.from(binario, c => c.charCodeAt(0));
}

async function sha256(texto) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(texto)));
}

function entradaValida(datos) {
  return datos && typeof datos.clave === "string" && /^[A-Za-z0-9-]{8,64}$/.test(datos.clave)
    && typeof datos.instalacion === "string" && /^[A-Za-z0-9_-]{16,40}$/.test(datos.instalacion);
}

async function limitar(request, env) {
  const ip = request.headers.get("CF-Connecting-IP") || "desconocida";
  const ahora = Math.floor(Date.now() / 3600000);
  const clave = `limite:${await digestHex(ip)}:${ahora}`;
  const actual = Number(await env.LICENCIAS.get(clave) || 0);
  if (actual >= 10) return false;
  await env.LICENCIAS.put(clave, String(actual + 1), { expirationTtl: 3700 });
  return true;
}

async function digestHex(texto) {
  return [...await sha256(texto)].map(x => x.toString(16).padStart(2, "0")).join("");
}

async function lemon(env, endpoint, fields) {
  const body = new URLSearchParams(fields);
  const respuestaLS = await fetch(`https://api.lemonsqueezy.com/v1/licenses/${endpoint}`, {
    method: "POST",
    headers: { accept: "application/json", "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  let datos;
  try { datos = await respuestaLS.json(); } catch { return null; }
  return respuestaLS.ok ? datos : null;
}

// Respuesta de la License API de Lemon Squeezy (campos en el primer nivel, no en data.attributes):
// activate → {activated, license_key:{status,…}, instance:{id,…}, meta:{store_id, product_id,…}}
// validate → {valid, license_key:{status,…}, instance, meta}
function datosLicencia(datos, env) {
  const meta = datos?.meta || {};
  const licencia = datos?.license_key || {};
  const tienda = String(meta.store_id ?? "");
  const producto = String(meta.product_id ?? "");
  const correcta = datos?.valid === true || datos?.activated === true;
  // Sin esta comprobación, una clave de cualquier otra tienda de Lemon Squeezy valdría para ARIA.
  if (tienda !== String(env.LS_STORE_ID) || producto !== String(env.LS_PRODUCT_ID)
      || licencia.status !== "active" || !correcta) return null;
  return datos;
}

async function firmar(clave, instalacion, env) {
  const privado = await crypto.subtle.importKey("pkcs8", b64bytes(env.CLAVE_PRIVADA_PKCS8_B64),
    { name: "Ed25519" }, false, ["sign"]);
  const huella = await digestHex(clave);
  const hoy = new Date();
  const caduca = new Date(hoy.getTime() + 14 * 86400000);
  const iso = fecha => isoFecha(fecha);
  const payload = JSON.stringify({ v: 1, id: `ls-${huella.slice(0, 12)}`, plan: "premium",
    emitida: iso(hoy), caduca: iso(caduca), instalacion });
  const crudo = new TextEncoder().encode(payload);
  const firma = await crypto.subtle.sign({ name: "Ed25519" }, privado, crudo);
  return `${b64url(crudo)}.${b64url(firma)}`;
}

function isoFecha(fecha) {
  return fecha.toISOString().slice(0, 10);
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return respuesta({ error: "Método no permitido." }, 405);
    const url = new URL(request.url);
    if (url.pathname !== "/v1/activar" && url.pathname !== "/v1/renovar")
      return respuesta({ error: "Ruta no encontrada." }, 404);
    if (!(await limitar(request, env))) return respuesta({ error: "Demasiadas solicitudes." }, 429);
    if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json"))
      return respuesta({ error: "La petición no es válida." }, 400);
    const cuerpo = await request.arrayBuffer();
    if (cuerpo.byteLength > 1024) return respuesta({ error: "La petición es demasiado grande." }, 400);
    let datos;
    try { datos = JSON.parse(new TextDecoder().decode(cuerpo)); } catch { return respuesta({ error: "El JSON no es válido." }, 400); }
    if (!entradaValida(datos)) return respuesta({ error: "La clave o la instalación no son válidas." }, 400);
    const hash = await digestHex(datos.clave);
    const claveKV = `instancia:${hash}:${datos.instalacion}`;
    let instancia = await env.LICENCIAS.get(claveKV);
    // Sin instancia guardada (primera vez, o KV perdido) se activa; con ella, se valida esa instancia concreta.
    const endpoint = instancia ? "validate" : "activate";
    const campos = { license_key: datos.clave };
    if (endpoint === "activate") campos.instance_name = `aria-${datos.instalacion}`;
    else campos.instance_id = instancia;
    const ls = await lemon(env, endpoint, campos);
    const atributos = ls && datosLicencia(ls, env);
    if (!atributos) return respuesta({ error: "La clave no está activa o no corresponde a este producto." }, 403);
    if (endpoint === "activate") {
      instancia = atributos.instance?.id;
      if (!instancia) return respuesta({ error: "La activación no ha devuelto una instancia válida." }, 403);
      await env.LICENCIAS.put(claveKV, String(instancia));
    }
    return respuesta({ licencia: await firmar(datos.clave, datos.instalacion, env) });
  },
};

