"use strict";
// Página pública /acceso: pedir acceso y ver el estado de la propia solicitud (su token se guarda en este navegador).
(() => {
  const $ = (s) => document.querySelector(s);
  const CLAVE = "aria_solicitud_acceso";
  const reducido = matchMedia("(prefers-reduced-motion: reduce)");
  let turnstile = "";

  const lienzo = $(".acc-ping");
  if (lienzo && typeof Ping !== "undefined") new Ping(lienzo, { global: true, sigueMs: 5000, escala: .9, zona: { x: .6, y: .5, ax: .25, ay: .2 } });

  const leer = () => { try { return localStorage.getItem(CLAVE) || ""; } catch (_) { return ""; } };
  const guardar = (t) => { try { localStorage.setItem(CLAVE, t); } catch (_) { /* sin almacenamiento */ } };

  const TEXTOS = {
    pendiente: "Pendiente: el administrador aún no la ha revisado. Vuelve más tarde.",
    aprobada: "¡Aprobada! Pulsa «Ya tengo acceso» y entra con tu email.",
    rechazada: "No se ha aprobado esta vez.",
  };
  async function comprobar() {
    const token = leer(); if (!token) return;
    const caja = $("#acc-estado"), p = $("#acc-estado-texto");
    caja.hidden = false; p.textContent = "Comprobando…"; p.className = "acc-estado";
    try {
      const r = await fetch("/acceso/estado/" + encodeURIComponent(token));
      if (!r.ok) { p.textContent = "No encuentro tu solicitud. Puedes enviar otra."; return; }
      const d = await r.json();
      p.textContent = (d.nombre ? d.nombre + ": " : "") + (TEXTOS[d.estado] || d.estado);
      p.className = "acc-estado " + d.estado;
    } catch (_) { p.textContent = "No se pudo comprobar ahora."; }
  }
  $("#acc-comprobar").addEventListener("click", comprobar);

  async function prepararTurnstile() {
    try {
      const r = await fetch("/acceso/config"); const d = await r.json();
      if (!d.turnstile) return;
      const s = document.createElement("script");
      s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"; s.async = true;
      s.onload = () => window.turnstile.render("#acc-turnstile", { sitekey: d.turnstile, theme: "dark", callback: (t) => { turnstile = t; } });
      document.head.append(s);
    } catch (_) { /* sin Turnstile */ }
  }

  $("#acc-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("#acc-error"), boton = $("#acc-enviar");
    err.hidden = true;
    const datos = { nombre: $("#acc-nombre").value.trim(), email: $("#acc-email").value.trim(), motivo: $("#acc-motivo").value.trim(),
      web: $("#acc-web").value, turnstile };
    if (!datos.nombre || !datos.email || !datos.motivo) { err.textContent = "Rellena los tres campos."; err.hidden = false; return; }
    boton.disabled = true; boton.textContent = "Enviando…";
    try {
      const r = await fetch("/acceso/solicitar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || "No se pudo enviar.");
      if (d.token) guardar(d.token);
      else if (!leer()) { $("#acc-estado").hidden = false; $("#acc-estado-texto").textContent = "Ya había una solicitud con ese email. Su estado solo se ve desde el navegador en el que se envió."; boton.textContent = "Solicitud enviada"; return; }
      $("#acc-form").reset();
      boton.textContent = "Solicitud enviada";
      await comprobar();
      $("#acc-estado").scrollIntoView({ behavior: reducido.matches ? "auto" : "smooth", block: "center" });
    } catch (x) {
      err.textContent = x.message; err.hidden = false; boton.disabled = false; boton.textContent = "Enviar solicitud";
      if (window.turnstile) window.turnstile.reset("#acc-turnstile");
    }
  });

  prepararTurnstile();
  comprobar();
})();
