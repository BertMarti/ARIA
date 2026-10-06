"use strict";
const $ = (id) => document.getElementById(id);
const historial = []; // {role, content}; solo en memoria del navegador

// --- Utilidades seguras (nunca innerHTML con texto del modelo) ---
function el(tag, props, ...hijos) {
  const e = document.createElement(tag);
  if (props) for (const [k, v] of Object.entries(props)) { if (k === "class") e.className = v; else e[k] = v; }
  for (const h of hijos) e.append(h);
  return e;
}

// Markdown minimo: bloques ```, `codigo`, **negrita** y enlaces https:// automaticos.
function renderInline(txt, padre) {
  const re = /(`[^`\n]+`|\*\*[^*\n]+\*\*|https?:\/\/[^\s<>)"']+)/g;
  let ultimo = 0, m;
  while ((m = re.exec(txt))) {
    if (m.index > ultimo) padre.append(txt.slice(ultimo, m.index));
    const t = m[0];
    if (t[0] === "`") padre.append(el("code", null, t.slice(1, -1)));
    else if (t.startsWith("**")) padre.append(el("strong", null, t.slice(2, -2)));
    else {
      let url = t, cola = "";
      while (/[.,;:!?]$/.test(url)) { cola = url.slice(-1) + cola; url = url.slice(0, -1); }
      let valida = false;
      try { valida = ["https:", "http:"].includes(new URL(url).protocol); } catch (_) {}
      if (valida) { const a = el("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, url); padre.append(a, cola); }
      else padre.append(t);
    }
    ultimo = m.index + t.length;
  }
  if (ultimo < txt.length) padre.append(txt.slice(ultimo));
}
function renderMd(txt, cont) {
  cont.replaceChildren();
  txt.split(/```/).forEach((parte, i) => {
    if (i % 2) cont.append(el("pre", null, el("code", null, parte.replace(/^[^\n]*\n/, ""))));
    else if (parte) { const p = el("p"); renderInline(parte, p); cont.append(p); }
  });
}

// --- Chat ---
const caja = $("mensajes");
function addMsg(clase, texto) {
  const d = el("div", { class: "msg " + clase });
  if (texto) renderMd(texto, d);
  caja.append(d); caja.scrollTop = caja.scrollHeight;
  return d;
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
      if (l) { try { yield JSON.parse(l); } catch (_) {} }
    }
  }
}
async function enviar(texto) {
  historial.push({ role: "user", content: texto });
  addMsg("user", texto);
  let burbuja = null, acumulado = "";
  $("enviar").disabled = true;
  try {
    const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: historial }) });
    if (r.status === 401) { location.href = "/login"; return; }
    if (!r.ok) throw new Error("HTTP " + r.status);
    for await (const ev of lineasNdjson(r)) {
      if (ev.type === "token") {
        if (!burbuja) burbuja = addMsg("bot", "");
        acumulado += ev.text; renderMd(acumulado, burbuja); caja.scrollTop = caja.scrollHeight;
      } else if (ev.type === "herramienta") {
        addMsg("tool", "🔧 " + ev.name + (Object.keys(ev.args || {}).length ? " " + JSON.stringify(ev.args) : ""));
        burbuja = null; // el texto posterior va en una burbuja nueva
        if (acumulado) { historial.push({ role: "assistant", content: acumulado }); acumulado = ""; }
      } else if (ev.type === "resultado") {
        addMsg("tool", "↳ " + ev.text);
      } else if (ev.type === "aviso") addMsg("aviso", ev.text);
      else if (ev.type === "error") addMsg("aviso", ev.text);
    }
    if (acumulado) historial.push({ role: "assistant", content: acumulado });
  } catch (e) {
    addMsg("aviso", "Error de conexión con ARIA.");
  } finally { $("enviar").disabled = false; $("texto").focus(); }
}
$("form").addEventListener("submit", (e) => {
  e.preventDefault();
  const t = $("texto").value.trim();
  if (!t || $("enviar").disabled) return;
  $("texto").value = ""; enviar(t);
});
$("texto").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("form").requestSubmit(); } });
$("nuevo").addEventListener("click", () => { historial.length = 0; caja.replaceChildren(); });

// --- Modelos ---
let modeloOk = false;
async function cargarModelo() {
  try {
    const m = await (await fetch("/api/models")).json();
    $("modelo-activo").textContent = m.activo;
    const info = $("modelo-info");
    info.replaceChildren();
    info.append(el("div", null, "Activo: ", el("code", null, m.activo)));
    if (!m.ollama) info.append(el("div", { class: "error" }, "Ollama no responde."));
    else info.append(el("div", { class: "muted" }, "Instalados: " + (m.instalados.join(", ") || "ninguno")));
    modeloOk = m.activo_instalado;
    $("btn-pull").hidden = !(m.ollama && !m.activo_instalado);
    if (m.ollama && !m.activo_instalado) info.append(el("div", { class: "aviso-txt" }, "El modelo activo no está descargado."));
  } catch (_) { $("modelo-info").textContent = "No se pudo consultar."; }
}
$("btn-pull").addEventListener("click", async () => {
  const b = $("btn-pull"), bar = $("pull-bar"), est = $("pull-estado");
  b.disabled = true; bar.hidden = false; bar.value = 0; est.textContent = "Iniciando descarga…";
  try {
    const r = await fetch("/api/models/pull", { method: "POST" });
    for await (const ev of lineasNdjson(r)) {
      if (ev.type === "progreso") {
        est.textContent = ev.estado;
        if (ev.total) bar.value = Math.round((ev.completado || 0) * 100 / ev.total);
      } else if (ev.type === "error") est.textContent = ev.text;
      else if (ev.type === "fin") est.textContent = "Modelo descargado.";
    }
  } catch (_) { est.textContent = "Error durante la descarga."; }
  b.disabled = false; bar.hidden = true; cargarModelo();
});

// --- Servicios ---
function pintarServicio(id, s, detalles) {
  const c = $(id).querySelector(".cuerpo");
  c.replaceChildren();
  const clase = s.estado === "ok" ? "ok" : s.estado === "parcial" ? "parcial" : "mal";
  const txt = s.estado === "ok" ? "Activo" : s.estado === "parcial" ? "Parcial" : "No instalado o sin respuesta";
  c.append(el("div", { class: "fila" }, el("span", { class: "dot " + clase }), txt));
  for (const d of detalles) c.append(el("div", { class: "muted" }, d));
  if (s.estado !== "no_instalado") {
    const url = `https://${location.hostname}:${s.puerto_web}${s.ruta_web}`;
    c.append(el("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, "Abrir panel"));
  }
}
async function cargarServicios() {
  try {
    const s = await (await fetch("/api/services")).json();
    pintarServicio("card-shield", s.shield_dns, ["DNS: " + (s.shield_dns.dns_ok ? "responde" : "sin respuesta"), "Web: " + (s.shield_dns.web_ok ? "responde" : "sin respuesta")]);
    pintarServicio("card-heimdall", s.heimdall, ["Puerto " + s.heimdall.puerto_web + ": " + (s.heimdall.web_ok ? "abierto" : "cerrado")]);
  } catch (_) {}
}

// --- Spotify ---
async function cargarSpotify() {
  const c = $("spotify-cuerpo"), ctrl = $("spotify-ctrl");
  try {
    const s = await (await fetch("/api/spotify/status")).json();
    c.replaceChildren(); ctrl.hidden = true;
    if (!s.configurado) {
      c.append(el("div", { class: "muted" }, "No configurado. Crea una app en developer.spotify.com/dashboard, añade la Redirect URI " + s.redirect_uri + " y rellena SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET en .env (después: docker compose up -d). Requiere Spotify Premium."));
    } else if (!s.conectado) {
      c.append(el("a", { href: "/spotify/login" }, "Conectar Spotify"));
    } else {
      ctrl.hidden = false;
      if (s.error) c.append(el("div", { class: "error" }, s.error));
      else if (s.ahora && s.ahora.titulo) c.append(el("div", null, (s.ahora.reproduciendo ? "▶ " : "⏸ ") + s.ahora.titulo), el("div", { class: "muted" }, s.ahora.artistas || ""));
      else c.append(el("div", { class: "muted" }, "Nada en reproducción."));
    }
  } catch (_) { c.textContent = "No se pudo consultar."; }
}
document.querySelectorAll("[data-sp]").forEach((b) => b.addEventListener("click", async () => {
  b.disabled = true;
  try {
    const r = await fetch("/api/spotify/" + b.dataset.sp, { method: "POST" });
    const j = await r.json();
    if (!r.ok) addMsg("aviso", j.error || "Error de Spotify.");
  } catch (_) {}
  b.disabled = false; setTimeout(cargarSpotify, 800);
}));

cargarModelo(); cargarServicios(); cargarSpotify();
setInterval(cargarServicios, 20000);
setInterval(cargarSpotify, 15000);
if (new URLSearchParams(location.search).get("spotify")) history.replaceState(null, "", "/");
