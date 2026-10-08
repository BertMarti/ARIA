"use strict";
// Utilidades compartidas. Regla de oro: el texto del modelo o de las APIs
// nunca se inserta con innerHTML; siempre nodos del DOM / textContent.
const $ = (id) => document.getElementById(id);

function el(tag, props, ...hijos) {
  const e = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") e.className = v;
      else if (k === "dataset") Object.assign(e.dataset, v);
      else e[k] = v;
    }
  }
  for (const h of hijos) if (h !== null && h !== undefined && h !== false) e.append(h);
  return e;
}

function fmtBytes(n) {
  n = Number(n) || 0;
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i === 0 ? n : n.toFixed(n >= 100 ? 0 : 1)).toString().replace(".", ",") + " " + u[i];
}
// Si se entra por el dominio público (aria.<dominio>), los paneles van por shield./heimdall.<dominio>;
// en casa (IP, .local o .lan) se usa la dirección local que da el servidor.
function enlacePanel(tipo, urlLocal) {
  const h = location.hostname;
  if (h.startsWith("aria.") && !/\.(local|lan)$/.test(h)) {
    const dom = h.slice(5);
    return tipo === "shield" ? "https://shield." + dom + "/admin/" : "https://heimdall." + dom + "/";
  }
  return urlLocal;
}
// Texto que no cabe: se recorta con «…» y, al pasar el ratón (o enfocar), se desliza de derecha a izquierda.
function marquesina(contenedor, texto) {
  const s = el("span", { class: "marq-txt" }, texto);
  contenedor.classList.add("marq");
  contenedor.title = texto;
  contenedor.append(s);
  const ir = () => {
    const d = s.scrollWidth - contenedor.clientWidth;
    if (d <= 2) return;
    contenedor.classList.add("marq-on");
    s.style.setProperty("--marq-d", -d - 8 + "px");
    s.style.setProperty("--marq-t", Math.max(1.2, (d + 8) / 45) + "s");
  };
  const volver = () => { contenedor.classList.remove("marq-on"); };
  contenedor.addEventListener("mouseenter", ir);
  contenedor.addEventListener("focus", ir);
  contenedor.addEventListener("mouseleave", volver);
  contenedor.addEventListener("blur", volver);
  return contenedor;
}
function fmtNum(n) { return (Number(n) || 0).toLocaleString("es-ES"); }

// Llamada a la API con JSON. Devuelve { ok, status, data }. 401 -> pantalla de acceso.
async function api(ruta, opciones = {}) {
  const o = { method: "GET", ...opciones };
  if (o.json !== undefined) {
    o.headers = { "Content-Type": "application/json", ...(o.headers || {}) };
    o.body = JSON.stringify(o.json);
    delete o.json;
  }
  let r;
  try { r = await fetch(ruta, o); } catch (e) { if (e.name === "AbortError") throw e; return { ok: false, status: 0, data: { error: "Sin conexión con ARIA." } }; }
  if (r.status === 401) { location.href = "/login"; return { ok: false, status: 401, data: {} }; }
  let data = {};
  try { data = await r.json(); } catch (_) { /* sin cuerpo JSON */ }
  return { ok: r.ok, status: r.status, data };
}

async function* lineasNdjson(resp) {
  const lector = resp.body.getReader(), dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await lector.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const l = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (l) { try { yield JSON.parse(l); } catch (_) { /* línea incompleta */ } }
    }
  }
}

function toast(texto, tipo) {
  const t = el("div", { class: "toast " + (tipo || "") }, texto);
  $("toasts").append(t);
  setTimeout(() => t.remove(), 4500);
}

// Diálogo de confirmación propio (devuelve una promesa con true/false).
function confirmar(titulo, texto, etiqueta) {
  const d = $("dlg-confirmar");
  $("confirmar-titulo").textContent = titulo;
  $("confirmar-texto").textContent = texto || "";
  $("confirmar-si").textContent = etiqueta || "Confirmar";
  return new Promise((resolver) => {
    const fin = (v) => { d.close(); $("confirmar-si").onclick = $("confirmar-no").onclick = d.onclose = null; resolver(v); };
    $("confirmar-si").onclick = () => fin(true);
    $("confirmar-no").onclick = () => fin(false);
    d.onclose = () => resolver(false);
    d.showModal();
  });
}

function barra(valor, aviso, malo) {
  const v = Math.max(0, Math.min(100, Number(valor) || 0));
  const valorEl = el("div", { class: "barra-valor" + (v >= malo ? " mal" : v >= aviso ? " aviso" : "") });
  valorEl.style.width = v + "%"; // CSSOM: permitido por la CSP (no es un atributo style)
  return el("div", { class: "barra", role: "progressbar", ariaValueNow: String(Math.round(v)) }, valorEl);
}

function enlaceExterno(url, texto) {
  return el("a", { href: url, target: "_blank", rel: "noopener noreferrer", class: "enlace-panel" }, texto);
}

// Sesión actual (usuario, rol). Los botones se ocultan por rol, pero quien manda es el servidor (403).
const Sesion = { rol: "usuario", nombre: "", email: "", tienePassword: true, esAdmin: false, funciones: {} };
async function cargarSesion() {
  const { ok, data } = await api("/api/info");
  if (!ok) return;
  Sesion.rol = data.rol || "usuario"; Sesion.nombre = data.usuario || ""; Sesion.email = data.email || "";
  Sesion.tienePassword = data.tiene_password !== false; Sesion.esAdmin = Sesion.rol === "admin";
  Sesion.funciones = data.funciones || {};
  document.body.classList.toggle("rol-usuario", !Sesion.esAdmin);
  document.body.classList.toggle("sin-spotify", !Sesion.funciones.spotify);
}

// Ajuste por dispositivo (localStorage puede no estar disponible).
const Prefs = {
  get(k, def) { try { const v = localStorage.getItem("aria_" + k); return v === null ? def : v; } catch (_) { return def; } },
  set(k, v) { try { localStorage.setItem("aria_" + k, v); } catch (_) { /* ignorar */ } },
};
