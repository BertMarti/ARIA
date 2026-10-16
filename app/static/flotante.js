"use strict";
// Ventana flotante con Document Picture-in-Picture (Chrome y Edge de escritorio).
const Flotante = (() => {
  const ESTADOS = { reposo: "En espera", escuchando: "Te escucho", pensando: "Procesando…", hablando: "Hablando" };
  const disponible = () => "documentPictureInPicture" in window;
  let pip = null, abort = null, estado = "reposo", nivel = 0, texto = "", raf = 0;

  function nodo(doc, tipo, clase, contenido) {
    const n = doc.createElement(tipo);
    if (clase) n.className = clase;
    if (contenido != null) n.textContent = contenido;
    return n;
  }

  function color() { return estado === "escuchando" ? [52, 211, 153] : estado === "pensando" ? [167, 139, 250] : [56, 214, 255]; }
  function dibujar() {
    if (!pip) { raf = 0; return; }
    // El reloj de animación es el de la ventana flotante: el de la pestaña de ARIA se para cuando está oculta
    const c = pip.document.querySelector(".flot-orbe"), box = c.getBoundingClientRect();
    if (!box.width) { raf = pip.requestAnimationFrame(dibujar); return; }
    const dpr = Math.min(2, pip.devicePixelRatio || 1);
    if (c.width !== Math.round(box.width * dpr) || c.height !== Math.round(box.height * dpr)) { c.width = Math.round(box.width * dpr); c.height = Math.round(box.height * dpr); }
    const ctx = c.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, box.width, box.height);
    const w = box.width, h = box.height, x = w / 2, y = h / 2, t = performance.now() / 1000, c0 = color();
    const r = Math.min(w, h) * .25 * (1 + nivel * .16), halo = Math.min(w, h) * .48;
    const rgba = (a, o) => `rgba(${a.join(",")},${o})`;
    let g = ctx.createRadialGradient(x, y, r * .1, x, y, halo);
    g.addColorStop(0, rgba(c0, .35 + nivel * .25)); g.addColorStop(1, rgba(c0, 0)); ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, halo, 0, Math.PI * 2); ctx.fill();
    g = ctx.createRadialGradient(x - r * .25, y - r * .3, r * .05, x, y, r);
    g.addColorStop(0, "rgba(255,255,255,.95)"); g.addColorStop(.3, rgba(c0, .9)); g.addColorStop(1, rgba(c0, .15)); ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    ctx.save(); ctx.translate(x, y); ctx.globalCompositeOperation = "lighter"; ctx.lineWidth = 1.2;
    for (let i = 0; i < 4; i++) { ctx.strokeStyle = rgba(i % 2 ? [255, 255, 255] : c0, .2); ctx.beginPath(); ctx.ellipse(0, 0, r * (.76 - i * .08), r * (.25 + i * .06), t * (estado === "pensando" ? 1.8 : .7) + i, 0, Math.PI * 2); ctx.stroke(); }
    ctx.strokeStyle = rgba(c0, .75); ctx.lineWidth = 1.4;
    for (let i = 0; i < 4; i++) { const a = i * Math.PI / 2 + t * .08; ctx.beginPath(); ctx.moveTo(Math.cos(a) * r * 1.35, Math.sin(a) * r * 1.35); ctx.lineTo(Math.cos(a) * r * 1.52, Math.sin(a) * r * 1.52); ctx.stroke(); }
    ctx.restore();
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { raf = 0; return; }
    raf = pip.requestAnimationFrame(dibujar);
  }

  function reflejar() {
    if (!pip) return;
    const d = pip.document;
    d.querySelector(".flot-estado").textContent = ESTADOS[estado] || ESTADOS.reposo;
    const sub = d.querySelector(".flot-subtitulo"); sub.textContent = texto || ESTADOS[estado] || "";
    d.querySelector(".flot-hud").dataset.estado = estado;
    if (!raf) raf = pip.requestAnimationFrame(dibujar);
  }

  function limpiar() {
    if (raf) pip?.cancelAnimationFrame(raf);
    raf = 0; abort?.abort(); abort = null; pip = null;
  }
  function enviar(t) { t = String(t || "").trim(); if (t && window.Chat) Chat.enviarDesdeVoz(t, true); }

  async function abrir() {
    if (!disponible()) return false;
    if (pip && !pip.closed) { pip.focus(); return true; }
    try { pip = await document.documentPictureInPicture.requestWindow({ width: 320, height: 360 }); }
    catch (_) { return false; }
    const d = pip.document, body = d.body;
    for (const sheet of document.styleSheets) {
      const link = sheet.ownerNode;
      if (link?.tagName !== "LINK" || link.rel !== "stylesheet") continue;
      const copia = d.createElement("link"); copia.rel = "stylesheet"; copia.href = link.href; d.head.append(copia);
    }
    const hud = nodo(d, "main", "flot-hud");
    const titulo = nodo(d, "h1", "flot-titulo", "ARIA");
    const canvas = nodo(d, "canvas", "flot-orbe"); canvas.setAttribute("aria-label", "Estado visual de ARIA");
    const sub = nodo(d, "p", "flot-subtitulo"); sub.setAttribute("aria-live", "polite");
    const est = nodo(d, "p", "flot-estado", ESTADOS.reposo);
    const form = nodo(d, "form", "flot-form"), input = nodo(d, "input", "flot-texto"); input.type = "text"; input.maxLength = 2000; input.placeholder = "Habla con ARIA…"; input.setAttribute("aria-label", "Pregunta para ARIA");
    const mic = nodo(d, "button", "flot-mic", "Micrófono"); mic.type = "button"; mic.setAttribute("aria-label", "Mantén pulsado para hablar");
    const send = nodo(d, "button", "flot-enviar", "Enviar"); send.type = "submit";
    const cerrar = nodo(d, "button", "flot-cerrar", "Cerrar"); cerrar.type = "button"; cerrar.setAttribute("aria-label", "Cerrar ventana flotante");
    form.append(input, mic, send); hud.append(titulo, canvas, est, sub, form, cerrar); body.append(hud);
    abort = new AbortController();
    const signal = { signal: abort.signal };
    addEventListener("aria:estado", (e) => { estado = e.detail?.estado || "reposo"; nivel = Math.max(0, Math.min(1, Number(e.detail?.nivel) || 0)); reflejar(); }, signal);
    addEventListener("aria:hud-texto", (e) => { texto = String(e.detail?.texto || "").slice(-420); reflejar(); }, signal);
    form.addEventListener("submit", (e) => { e.preventDefault(); const t = input.value.trim(); input.value = ""; enviar(t); });
    cerrar.addEventListener("click", () => pip.close());
    try { Voz.botonMic(mic, enviar); } catch (_) { mic.addEventListener("click", () => ManosLibres.iniciar()); }
    pip.addEventListener("pagehide", limpiar, { once: true });
    reflejar();
    return true;
  }
  function cerrar() { if (pip && !pip.closed) pip.close(); else limpiar(); }

  const boton = document.querySelector('[data-flotante="abrir"]');
  if (boton) { boton.hidden = !disponible(); boton.addEventListener("click", abrir); }
  return { disponible, abrir, cerrar };
})();
