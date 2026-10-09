"use strict";
// Presencia a pantalla completa: canvas ligero y widgets que fallan de forma silenciosa.
const Hud = (() => {
  let activo = false, raf = 0, reloj = 0, refresco = 0, estado = "reposo", nivel = 0;
  const particulas = [];
  const $w = (id) => $(id);
  const texto = (id, value) => { const e = $w(id); e.querySelector(".hud-valor").textContent = value; e.hidden = !value; };

  const COLORES = { reposo: [56, 214, 255], escuchando: [52, 211, 153], pensando: [124, 140, 255], hablando: [92, 225, 255] };
  const reducido = matchMedia("(prefers-reduced-motion: reduce)");
  let suave = 0, color = [56, 214, 255], t0 = performance.now(), ultimoEstatico = 0;
  const mayus = (x) => x.charAt(0).toUpperCase() + x.slice(1);

  function relojLocal() {
    const ahora = new Date(), hora = $w("hud-hora");
    hora.textContent = ahora.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
    hora.dateTime = ahora.toISOString();
    $w("hud-fecha").textContent = mayus(ahora.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" }));
  }
  function ocultar(id) { $w(id).hidden = true; }
  function lista(id, filas) {
    const ul = $w(id).querySelector(".hud-lista"); ul.replaceChildren(...filas); $w(id).hidden = !filas.length;
  }
  async function datos() {
    const peticiones = [api("/api/resumen-diario"), api("/api/avisos"), api("/api/recordatorios")];
    if (Sesion.esAdmin) peticiones.push(api("/api/vpn/clients"), api("/api/shield"));
    const [b, a, r, v, sh] = await Promise.allSettled(peticiones);
    const d = b?.value?.ok ? b.value.data : null;
    if (d?.tiempo) { const t = d.tiempo; texto("hud-tiempo", `${t.actual ?? t.max} °C · ${t.cielo} · ${t.min}–${t.max} °C`); } else ocultar("hud-tiempo");
    if (a?.value?.ok) { const n = a.value.data.no_leidos || 0; texto("hud-avisos", n ? `${n} sin leer` : "Todo leído"); } else ocultar("hud-avisos");
    if (r?.value?.ok) { const rs = r.value.data.recordatorios || []; texto("hud-recordatorio", rs.length ? `${rs[0].texto} · ${rs[0].descripcion}` : "Ninguno pendiente"); } else ocultar("hud-recordatorio");
    const inv = d?.inversiones?.valores || [];
    lista("hud-inversiones", inv.slice(0, 4).map((x) => el("li", null, el("span", null, x.nombre || x.simbolo),
      x.variacion_dia == null ? el("span", null, "—") : el("span", { class: x.variacion_dia >= 0 ? "sube" : "baja" }, (x.variacion_dia >= 0 ? "▲ " : "▼ ") + Math.abs(x.variacion_dia).toLocaleString("es-ES", { maximumFractionDigits: 2 }) + " %"))));
    if (!Sesion.esAdmin) return;
    for (const id of ["hud-sistema", "hud-vpn", "hud-shield"]) $w(id).hidden = false;
    const ap = d?.aplicaciones;
    if (ap) { texto("hud-sistema", (ap.ok ? "✓ Todo en orden" : "⚠ " + ap.problemas.length + (ap.problemas.length === 1 ? " cosa que revisar" : " cosas que revisar")) + (ap.raspberry?.temperatura != null ? ` · ${String(ap.raspberry.temperatura).replace(".", ",")} °C` : "")); $w("hud-sistema").classList.toggle("mal", !ap.ok); } else ocultar("hud-sistema");
    if (v?.value?.ok && v.value.data.conectado) texto("hud-vpn", `${v.value.data.clientes.filter((x) => x.conectado).length} de ${v.value.data.clientes.length}`); else ocultar("hud-vpn");
    if (sh?.value?.ok && sh.value.data.conectado) texto("hud-shield", fmtNum(sh.value.data.bloqueadas ?? 0)); else ocultar("hud-shield");
  }

  // --- Orbe: halo, núcleo con remolino, tres anillos discontinuos, onda de voz y partículas en órbita ---
  function rgba(c, o) { return `rgba(${c[0]},${c[1]},${c[2]},${o})`; }
  function dibujar(ahora) {
    if (!activo || document.hidden) { raf = 0; return; }
    const quieto = reducido.matches;
    if (quieto && ahora - ultimoEstatico < 400) { raf = requestAnimationFrame(dibujar); return; }
    ultimoEstatico = ahora;
    const c = $w("hud-orbe"), box = c.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
    if (c.width !== Math.round(box.width * dpr) || c.height !== Math.round(box.height * dpr)) { c.width = Math.round(box.width * dpr); c.height = Math.round(box.height * dpr); }
    const ctx = c.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const w = box.width, h = box.height, x = w / 2, y = h / 2, R = Math.min(w, h) * .3;
    const t = quieto ? 0 : (ahora - t0) / 1000;
    const objetivo = COLORES[estado] || COLORES.reposo;
    color = color.map((v, i) => v + (objetivo[i] - v) * .08);
    const activoVoz = estado === "escuchando" || estado === "hablando";
    suave += ((activoVoz ? nivel : 0) - suave) * .25;
    const respira = quieto ? 0 : Math.sin(t * 1.1) * .03, r = R * (1 + respira + suave * .18);
    const vel = estado === "pensando" ? 2.6 : activoVoz ? 1.4 : .6;
    ctx.clearRect(0, 0, w, h);
    // Halo
    const halo = Math.min(w, h) / 2;   // el halo se apaga antes del borde del lienzo: sin esquinas visibles
    let g = ctx.createRadialGradient(x, y, r * .2, x, y, halo);
    g.addColorStop(0, rgba(color, .35 + suave * .3)); g.addColorStop(.5, rgba(color, .08)); g.addColorStop(1, rgba(color, 0));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, halo, 0, Math.PI * 2); ctx.fill();
    // Núcleo
    g = ctx.createRadialGradient(x - r * .25, y - r * .3, r * .05, x, y, r);
    g.addColorStop(0, "rgba(255,255,255,.9)"); g.addColorStop(.25, rgba(color, .85)); g.addColorStop(.75, rgba(color.map((v) => v * .35), .9)); g.addColorStop(1, rgba(color.map((v) => v * .15), .2));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r * .78, 0, Math.PI * 2); ctx.fill();
    // Remolino dentro del núcleo
    ctx.save(); ctx.beginPath(); ctx.arc(x, y, r * .78, 0, Math.PI * 2); ctx.clip();
    ctx.globalCompositeOperation = "lighter"; ctx.lineWidth = 1.2;
    for (let i = 0; i < 6; i++) {
      ctx.strokeStyle = rgba(i % 2 ? [255, 255, 255] : color, .16);
      ctx.beginPath(); ctx.ellipse(x, y, r * (.75 - i * .06), r * (.22 + i * .05), t * vel * (.3 + i * .08) + i * 1.05, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.restore();
    // Anillos discontinuos que giran en sentidos opuestos
    ctx.globalCompositeOperation = "lighter";
    [[1.0, 1, [r * .5, r * .18], 1.6, .8], [1.18, -1.3, [r * .08, r * .12], 1, .55], [1.36, .7, [r * 1.2, r * .4], 1, .35]].forEach(([k, s, dash, lw, o]) => {
      ctx.save(); ctx.translate(x, y); ctx.rotate(t * vel * .35 * s); ctx.setLineDash(dash);
      ctx.strokeStyle = rgba(color, o); ctx.lineWidth = lw; ctx.beginPath(); ctx.arc(0, 0, r * k, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
    });
    // Onda de voz alrededor del núcleo
    if (suave > .02) {
      ctx.strokeStyle = rgba(color, .9); ctx.lineWidth = 2; ctx.beginPath();
      for (let i = 0; i <= 120; i++) {
        const a = i / 120 * Math.PI * 2, rr = r * .86 + Math.sin(a * 6 + t * 7) * suave * r * .12 + Math.sin(a * 11 - t * 5) * suave * r * .06;
        i ? ctx.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr) : ctx.moveTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
      }
      ctx.closePath(); ctx.stroke();
    }
    // Partículas en órbita
    for (const p of particulas) {
      if (!quieto) p.a += p.v * vel * .006;
      const rr = Math.min(r * p.r * (1 + suave * .25), halo * .97);
      ctx.fillStyle = rgba(p.c ? [124, 140, 255] : color, p.o);
      ctx.beginPath(); ctx.arc(x + Math.cos(p.a) * rr, y + Math.sin(p.a) * rr * .92, p.s, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
    raf = requestAnimationFrame(dibujar);
  }
  function preparar() {
    particulas.length = 0;
    const n = Math.max(28, Math.min(110, Math.floor(innerWidth * innerHeight / 15000)));
    for (let i = 0; i < n; i++) particulas.push({ a: Math.random() * Math.PI * 2, r: 1.05 + Math.random() * .75, s: .6 + Math.random() * 1.8, o: .25 + Math.random() * .6, v: (.4 + Math.random()) * (Math.random() < .5 ? -1 : 1), c: Math.random() < .35 });
  }
  function cambiar(e) { estado = e.detail?.estado || "reposo"; nivel = Math.max(0, Math.min(1, Number(e.detail?.nivel) || 0)); $w("hud-orbe").dataset.estado = estado; $w("hud-estado").textContent = { reposo: "En espera", escuchando: "Te escucho", pensando: "Pensando…", hablando: "Hablando" }[estado] || ""; }
  function activar(si) { activo = si; if (!si) { cancelAnimationFrame(raf); raf = 0; clearInterval(refresco); return; } preparar(); relojLocal(); datos(); clearInterval(refresco); refresco = setInterval(() => { if (!document.hidden) datos(); }, 60000); if (!raf) raf = requestAnimationFrame(dibujar); }
  function iniciar() {
    addEventListener("aria:estado", cambiar); addEventListener("resize", preparar);
    addEventListener("aria:hud-texto", (e) => { if (activo) $w("hud-subtitulo").textContent = String(e.detail?.texto || "").slice(-420); });
    addEventListener("visibilitychange", () => { if (activo && !document.hidden && !raf) raf = requestAnimationFrame(dibujar); });
    setInterval(() => { if (activo) relojLocal(); }, 1000);
    $w("hud-salir").addEventListener("click", () => { location.hash = "inicio"; });
    $w("hud-pantalla").addEventListener("click", async () => { try { if (!document.fullscreenElement) await document.documentElement.requestFullscreen(); else await document.exitFullscreen(); } catch (_) { toast("La pantalla completa no está disponible.", "mal"); } });
    Voz.botonMic($w("hud-mic"), (t) => { $w("hud-texto").value = t; $w("hud-form").requestSubmit(); });
    $w("hud-manos").addEventListener("click", () => ManosLibres.activa() ? ManosLibres.parar() : ManosLibres.iniciar());
    ManosLibres.alCambiar((on) => { $w("hud-manos").setAttribute("aria-pressed", on); });
    $w("hud-form").addEventListener("submit", async (e) => { e.preventDefault(); const t = $w("hud-texto").value.trim(); if (!t) return; $w("hud-texto").value = ""; const r = await Chat.enviarDesdeVoz(t); location.hash = "hud"; if (r) { $w("hud-subtitulo").textContent = r.slice(0, 420); Voz.hablar(r); } });
  }
  return { iniciar, activar };
})();
