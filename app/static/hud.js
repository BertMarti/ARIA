"use strict";
// Presencia a pantalla completa: canvas ligero y widgets que fallan de forma silenciosa.
const Hud = (() => {
  let activo = false, raf = 0, reloj = 0, refresco = 0, estado = "reposo", nivel = 0;
  const particulas = [];
  const $w = (id) => $(id);
  const texto = (id, value) => { const e = $w(id); e.querySelector(".hud-valor").textContent = value; e.hidden = !value; };

  function relojLocal() {
    const ahora = new Date(), hora = $w("hud-hora");
    hora.textContent = ahora.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
    hora.dateTime = ahora.toISOString();
    $w("hud-fecha").textContent = ahora.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });
  }
  function ocultar(id) { $w(id).hidden = true; }
  async function datos() {
    const peticiones = [api("/api/briefing"), api("/api/avisos"), api("/api/recordatorios")];
    if (Sesion.esAdmin) peticiones.push(api("/api/system"), api("/api/vpn/clients"), api("/api/shield"));
    const [b, a, r, s, v, sh] = await Promise.allSettled(peticiones);
    if (b?.value?.ok && b.value.data.tiempo) { const t = b.value.data.tiempo; texto("hud-tiempo", `${t.ciudad}: ${t.cielo}, ${t.actual ?? ""} °C · ${t.min}-${t.max} °C`); } else ocultar("hud-tiempo");
    if (a?.value?.ok) texto("hud-avisos", `${a.value.data.no_leidos || 0} sin leer`); else ocultar("hud-avisos");
    if (r?.value?.ok) { const rs = r.value.data.recordatorios || []; texto("hud-recordatorio", rs.length ? `${rs[0].texto} · ${rs[0].descripcion}` : "Ninguno pendiente"); } else ocultar("hud-recordatorio");
    if (!Sesion.esAdmin) return;
    for (const id of ["hud-sistema", "hud-vpn", "hud-shield"]) $w(id).hidden = false;
    if (s?.value?.ok) texto("hud-sistema", [s.value.data.temperatura != null ? `${s.value.data.temperatura} °C` : "", s.value.data.memoria ? `RAM ${Math.round(s.value.data.memoria.porcentaje)} %` : ""].filter(Boolean).join(" · ")); else ocultar("hud-sistema");
    if (v?.value?.ok && v.value.data.conectado) texto("hud-vpn", `${v.value.data.clientes.filter((x) => x.conectado).length} conectados`); else ocultar("hud-vpn");
    if (sh?.value?.ok && sh.value.data.conectado) texto("hud-shield", String(sh.value.data.bloqueadas ?? 0)); else ocultar("hud-shield");
  }
  function dibujar() {
    if (!activo || document.hidden) { raf = 0; return; }
    const c = $w("hud-orbe"), box = c.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
    if (c.width !== box.width * dpr || c.height !== box.height * dpr) { c.width = box.width * dpr; c.height = box.height * dpr; }
    const x = c.width / 2, y = c.height / 2, radio = Math.min(x, y) * .52, ctx = c.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const w = box.width, h = box.height, pulso = estado === "escuchando" || estado === "hablando" ? nivel * 45 : Math.sin(Date.now() / 1800) * 7;
    ctx.clearRect(0, 0, w, h); ctx.globalCompositeOperation = "lighter";
    const grad = ctx.createRadialGradient(x, y, radio * .15, x, y, radio * 1.5); grad.addColorStop(0, "rgba(56,214,255,.55)"); grad.addColorStop(1, "rgba(56,214,255,0)"); ctx.fillStyle = grad; ctx.beginPath(); ctx.arc(x, y, radio * 1.65 + pulso, 0, Math.PI * 2); ctx.fill();
    for (let i = 0; i < particulas.length; i++) { const p = particulas[i], ang = p.a + (estado === "pensando" ? Date.now() / 2200 : 0), rr = radio * p.r + pulso * p.r; ctx.fillStyle = `rgba(124,140,255,${p.o})`; ctx.beginPath(); ctx.arc(x + Math.cos(ang) * rr, y + Math.sin(ang) * rr, p.s, 0, Math.PI * 2); ctx.fill(); }
    ctx.globalCompositeOperation = "source-over"; ctx.strokeStyle = "rgba(56,214,255,.85)"; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(x, y, radio + pulso, 0, Math.PI * 2); ctx.stroke();
    raf = requestAnimationFrame(dibujar);
  }
  function preparar() { particulas.length = 0; const n = Math.max(24, Math.min(90, Math.floor(innerWidth * innerHeight / 18000))); for (let i = 0; i < n; i++) particulas.push({ a: Math.random() * Math.PI * 2, r: .75 + Math.random() * .75, s: 1 + Math.random() * 2, o: .35 + Math.random() * .6 }); }
  function cambiar(e) { estado = e.detail?.estado || "reposo"; nivel = Math.max(0, Math.min(1, Number(e.detail?.nivel) || 0)); $w("hud-orbe").dataset.estado = estado; }
  function activar(si) { activo = si; if (!si) { cancelAnimationFrame(raf); raf = 0; clearInterval(refresco); return; } preparar(); relojLocal(); datos(); clearInterval(refresco); refresco = setInterval(() => { if (!document.hidden) datos(); }, 45000); if (!raf) raf = requestAnimationFrame(dibujar); }
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
