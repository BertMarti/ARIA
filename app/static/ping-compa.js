"use strict";
// Ping compañero: una única animación de Ping, activada solo durante cada aparición.
const PingCompa = (() => {
  const MODO = "ping_modo", REDUCIDO = matchMedia("(prefers-reduced-motion: reduce)");
  let canvas, ping, burbuja, salida, paseo, vuelta, iniciado = false, audioPermitido = false;
  const modo = () => { try { return localStorage.getItem("aria_" + MODO) || "pasea"; } catch (_) { return "pasea"; } };
  const voz = () => { try { return localStorage.getItem("aria_ping_voz") === "1"; } catch (_) { return false; } };
  const vistaBloqueada = () => ["cerebro", "mapa"].includes(location.hash.replace("#", "")) || document.querySelector("dialog[open]");
  const esperar = (min, max) => Math.round((min + Math.random() * (max - min)) * 60000);
  const borde = () => {
    const w = innerWidth, h = innerHeight, m = 72, lado = Math.floor(Math.random() * 4);
    if (lado === 0) return { x: m + Math.random() * Math.min(180, w * .22), y: m + Math.random() * 120 };
    if (lado === 1) return { x: w - m - Math.random() * Math.min(180, w * .22), y: m + Math.random() * 120 };
    if (lado === 2) return { x: m, y: h * (.25 + Math.random() * .45) };
    return { x: w - m, y: h * (.25 + Math.random() * .45) };
  };
  function guardarAnunciados(id) {
    try {
      const k = "aria_ping_anunciados", a = JSON.parse(localStorage.getItem(k) || "[]").filter((x) => x !== id);
      a.push(id); localStorage.setItem(k, JSON.stringify(a.slice(-50)));
    } catch (_) { /* almacenamiento no disponible */ }
  }
  function yaAnunciado(id) {
    try { return JSON.parse(localStorage.getItem("aria_ping_anunciados") || "[]").includes(id); } catch (_) { return false; }
  }
  function sonido() {
    if (!voz() || !audioPermitido) return;
    const a = new Audio("/static/escaparate/audio/ping-eh-mira.mp3"); a.volume = .6;
    a.play().catch(() => {});
  }
  function seguro() { return !document.hidden && !vistaBloqueada() && modo() !== "nunca"; }
  function mostrar() {
    if (!canvas || !seguro()) return false;
    canvas.hidden = false; canvas.classList.add("ping-visible"); ping.iniciar(); return true;
  }
  function ocultar() {
    clearTimeout(salida); clearInterval(vuelta); if (!canvas) return;
    if (burbuja) { burbuja.remove(); burbuja = null; }
    if (canvas.hidden) return;
    // Se va volando por el borde más cercano y luego se apaga el lienzo (sin rAF mientras no está).
    const izquierda = ping.p.x < innerWidth / 2;
    ping.destino = { x: izquierda ? -60 : innerWidth + 60, y: ping.p.y };
    salida = setTimeout(() => {
      canvas.classList.remove("ping-visible");
      salida = setTimeout(() => { ping.parar(); canvas.hidden = true; }, 850);
    }, REDUCIDO.matches ? 0 : 1100);
  }
  function volar() {
    if (!mostrar()) return;
    const r = canvas.getBoundingClientRect(), entra = borde();
    ping.p.x = Math.random() < .5 ? -35 : r.width + 35; ping.p.y = entra.y;
    ping.destino = entra; ping.tono("ok");
    vuelta = setInterval(() => { if (!burbuja) ping.destino = borde(); }, 4500);   // da vueltas de esquina en esquina
    salida = setTimeout(ocultar, 15000 + Math.random() * 15000);
  }
  function programar() {
    clearTimeout(paseo);
    if (modo() === "pasea" && !REDUCIDO.matches && !document.hidden) paseo = setTimeout(() => { volar(); programar(); }, esperar(4, 9));
  }
  function juntoCampana() {
    const c = $("campana"); if (!c) return;
    const r = c.getBoundingClientRect(); ping.destino = { x: Math.max(70, r.left - 28), y: r.top + r.height / 2 };
    if (!burbuja) {
      burbuja = el("div", { class: "ping-compa-bocadillo", role: "status" });
      document.body.append(burbuja);
    }
    const b = burbuja, x = Math.min(innerWidth - b.offsetWidth - 12, Math.max(12, r.left - b.offsetWidth - 10));
    b.style.left = x + "px"; b.style.top = Math.max(12, r.bottom + 10) + "px";
  }
  function textoAviso(lista) {
    if (lista.length > 1) return "¡Eh, mira! Tienes " + lista.length + " avisos nuevos";
    return "¡Eh, mira! " + String(lista[0].texto || lista[0].titulo || "Tienes un aviso nuevo").slice(0, 90);
  }
  function anunciar(lista) {
    if (!lista.length || modo() === "nunca" || document.hidden || vistaBloqueada()) return;
    const nuevos = lista.filter((a) => a.id != null && !yaAnunciado(String(a.id)));
    if (!nuevos.length || !mostrar()) return;
    nuevos.forEach((a) => guardarAnunciados(String(a.id)));
    const grave = nuevos.some((a) => a.severidad === "grave" || a.prioridad === "alta" || a.prioridad === "high");
    clearInterval(vuelta); ping.tono(grave ? "aviso" : "ok"); juntoCampana();
    burbuja.classList.toggle("alerta", grave); burbuja.replaceChildren(
      el("p", { class: "ping-compa-texto" }, textoAviso(nuevos)),
      el("div", { class: "ping-compa-acciones" },
        el("button", { type: "button", class: "primario pequeno" }, "Ver"),
        el("button", { type: "button", class: "fantasma pequeno" }, "Luego")));
    burbuja.querySelector("button").addEventListener("click", () => { $("campana")?.click(); ocultar(); });
    burbuja.querySelectorAll("button")[1].addEventListener("click", ocultar);
    $("campana")?.classList.add("ping-compa-campana"); setTimeout(() => $("campana")?.classList.remove("ping-compa-campana"), 3200);
    sonido(); clearTimeout(salida); salida = setTimeout(ocultar, 20000);
  }
  function propuestas(e) {
    if (modo() === "nunca" || document.hidden || vistaBloqueada()) return;
    const p = (e.detail || []).filter((x) => x.id != null && !yaAnunciado("propuesta:" + x.id));
    if (!p.length || !mostrar()) return;
    p.forEach((x) => guardarAnunciados("propuesta:" + x.id)); clearInterval(vuelta); ping.tono("pensando"); juntoCampana();
    burbuja.replaceChildren(el("p", { class: "ping-compa-texto" }, "¡Eh, mira! Tienes una propuesta nueva."), el("div", { class: "ping-compa-acciones" }, el("button", { type: "button", class: "fantasma pequeno" }, "Luego")));
    burbuja.querySelector("button").addEventListener("click", ocultar); sonido(); clearTimeout(salida); salida = setTimeout(ocultar, 20000);
  }
  function iniciar() {
    if (iniciado) return; iniciado = true;
    canvas = el("canvas", { class: "ping-compa-lienzo", hidden: true, ariaHidden: "true" }); document.body.append(canvas);
    ping = new Ping(canvas, { escala: .72, zona: { x: .5, y: .5, ax: .1, ay: .1 }, tono: "ok" }); ping.parar(); canvas.hidden = true;
    addEventListener("pointerdown", () => { audioPermitido = true; }, { once: true, passive: true });
    addEventListener("keydown", () => { audioPermitido = true; }, { once: true, passive: true });
    addEventListener("resize", () => { if (burbuja) juntoCampana(); });
    new MutationObserver(() => { if (document.querySelector("dialog[open]")) ocultar(); }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ["open"] });
    addEventListener("aria:avisos", (e) => anunciar(e.detail || [])); addEventListener("aria:propuestas", propuestas);
    addEventListener("aria:ping-ajustes", () => { ocultar(); programar(); });
    addEventListener("hashchange", () => { if (vistaBloqueada()) ocultar(); programar(); });
    document.addEventListener("visibilitychange", () => { if (document.hidden) { ocultar(); clearTimeout(paseo); } else programar(); });
    programar();
  }
  return { iniciar };
})();
