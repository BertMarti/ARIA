"use strict";
// Modo HUD: escena a pantalla completa con fondo animado, orbe, tarjetas que reaccionan al ratón y opciones.
// Todo el texto entra con nodos del DOM; los efectos se apagan con «reducir movimiento» o desde Opciones.
const Hud = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const TEMAS = { cian: [56, 214, 255], violeta: [167, 139, 250], ambar: [251, 191, 36], verde: [52, 211, 153], rosa: [244, 114, 182] };
  const NOMBRES_TEMA = { cian: "Cian", violeta: "Violeta", ambar: "Ámbar", verde: "Verde", rosa: "Rosa" };
  const TARJETAS = { tiempo: "Clima", agenda: "Agenda de hoy", pendiente: "Pendiente", finanzas: "Finanzas", casa: "Estado de la casa", red: "Red y seguridad", inversiones: "Mercados" };
  const DEFECTO = { tarjetas: Object.fromEntries(Object.keys(TARJETAS).map((k) => [k, true])), tema: "cian", raton: true, fondo: true, cursor: true, segundos: false, voz: true };
  const ESTADOS = { reposo: "En espera", escuchando: "Te escucho", pensando: "Procesando…", hablando: "Hablando" };
  const reducido = matchMedia("(prefers-reduced-motion: reduce)");
  const tactil = matchMedia("(hover: none)");

  let activo = false, raf = 0, rafFondo = 0, refresco = 0, refrescoDirecto = 0;
  let estado = "reposo", nivel = 0, suave = 0, color = [56, 214, 255], t0 = performance.now(), ultimoEstatico = 0;
  let puntero = { x: .5, y: .5, dentro: false }, opts = cargarOpciones(), resumen = null, apUltimo = null, sisUltimo = {};
  const cpuHist = [], particulas = [], estrellas = [];
  const $w = (id) => $(id);
  const mayus = (x) => x.charAt(0).toUpperCase() + x.slice(1);
  const hora = (iso) => String(iso || "").slice(11, 16);
  const eur = (n, dec = 2) => Number(n).toLocaleString("es-ES", { style: "currency", currency: "EUR", minimumFractionDigits: dec, maximumFractionDigits: dec, useGrouping: "always" });
  const pct = (p) => (p > 0 ? "+" : "") + Number(p).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " %";
  const movimiento = () => opts.raton && !reducido.matches && !tactil.matches;

  function cargarOpciones() {
    try {
      const o = JSON.parse(Prefs.get("hud_opciones", "null"));
      if (o) return { ...DEFECTO, ...o, tarjetas: { ...DEFECTO.tarjetas, ...(o.tarjetas || {}) } };
    } catch (_) { /* valores por defecto */ }
    return structuredClone(DEFECTO);
  }
  function guardarOpciones() { Prefs.set("hud_opciones", JSON.stringify(opts)); aplicarOpciones(); }

  // --- Piezas visuales ---
  function svg(tag, attrs, ...hijos) { const n = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v); n.append(...hijos); return n; }
  function anillo(valor, etiqueta, unidad, alerta) {
    const r = 26, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, Number(valor) || 0));
    return el("div", { class: "hud-anillo" + (alerta ? " alerta" : "") },
      svg("svg", { viewBox: "0 0 64 64", "aria-hidden": "true" },
        svg("circle", { cx: 32, cy: 32, r, class: "pista" }),
        svg("circle", { cx: 32, cy: 32, r, class: "valor", "stroke-dasharray": `${(c * v / 100).toFixed(1)} ${c.toFixed(1)}`, transform: "rotate(-90 32 32)" })),
      el("strong", null, valor == null ? "—" : String(Math.round(valor)) + unidad), el("span", null, etiqueta));
  }
  function linea(serie, alto = 34) {
    const w = 160, xs = serie.filter((x) => x != null);
    if (xs.length < 2) return null;
    const min = Math.min(...xs), max = Math.max(...xs), rango = max - min || 1;
    const pts = xs.map((v, i) => `${(i / (xs.length - 1) * w).toFixed(1)},${(alto - 2 - (v - min) / rango * (alto - 4)).toFixed(1)}`).join(" ");
    return svg("svg", { class: "hud-linea", viewBox: `0 0 ${w} ${alto}`, preserveAspectRatio: "none", "aria-hidden": "true" },
      svg("polygon", { points: `0,${alto} ${pts} ${w},${alto}`, class: "area" }), svg("polyline", { points: pts, class: "trazo" }));
  }
  function barra(v, alerta) { const b = el("div", { class: "hud-barra" + (alerta ? " alerta" : "") }), f = el("span"); f.style.width = Math.max(0, Math.min(100, Number(v) || 0)) + "%"; b.append(f); return b; }
  function dato(etq, valor, clase) { return el("div", { class: "hud-dato " + (clase || "") }, el("span", null, etq), el("strong", null, valor)); }
  function grande(texto, sub) { return el("div", { class: "hud-grande" }, el("strong", null, texto), sub ? el("span", null, sub) : null); }
  function chipCambio(c) { return c == null ? el("span", { class: "hud-chip" }, "—") : el("span", { class: "hud-chip " + (c >= 0 ? "sube" : "baja") }, (c >= 0 ? "▲ " : "▼ ") + pct(c)); }

  function pintar(w, led, ...hijos) {
    const t = document.querySelector(`#v-hud .hud-card[data-w="${w}"]`); if (!t) return;
    hijos = hijos.filter(Boolean);
    const visible = opts.tarjetas[w] !== false && hijos.length > 0 && (!t.classList.contains("hud-admin") || Sesion.esAdmin);
    t.hidden = !visible;
    if (!visible) return;
    t.querySelector(".hud-cuerpo").replaceChildren(...hijos);
    t.dataset.led = led || "ok";
  }

  // --- Datos ---
  async function datos() {
    const pet = [api("/api/resumen-diario"), api("/api/avisos"), api("/api/recordatorios")];
    if (Sesion.esAdmin) pet.push(api("/api/vpn/clients"), api("/api/shield"));
    const [b, a, r, v, sh] = await Promise.allSettled(pet);
    const d = resumen = b.value?.ok ? b.value.data : null;
    const t = d?.tiempo;
    pintar("tiempo", t?.aviso_manana ? "aviso" : "ok", ...(t ? [
      grande(`${t.actual ?? t.max}°`, mayus(t.cielo) + " · " + t.ciudad),
      el("div", { class: "hud-fila3" }, dato("Mín", t.min + "°"), dato("Máx", t.max + "°"), dato("Lluvia", (t.lluvia ?? "—") + " %")),
      barra(t.lluvia), t.aviso_manana ? el("p", { class: "hud-nota aviso" }, t.aviso_manana) : null] : []));
    const ag = d?.agenda || {}, items = [];
    for (const e of (ag.eventos || []).slice(0, 4)) items.push(el("li", null, el("span", { class: "hud-h" }, e.todo_el_dia ? "Día" : hora(e.inicio)), el("span", null, e.titulo)));
    for (const c of (ag.cumpleanos || []).slice(0, 2)) items.push(el("li", { class: "cumple" }, el("span", { class: "hud-h" }, "Cumple"), el("span", null, c.nombre + (c.edad ? ` (${c.edad})` : ""))));
    pintar("agenda", "ok", items.length ? el("ul", { class: "hud-lista-ag" }, ...items) : el("p", { class: "hud-nota" }, "Día despejado."));
    const noLeidos = a.value?.ok ? a.value.data.no_leidos || 0 : null, rs = r.value?.ok ? r.value.data.recordatorios || [] : [];
    pintar("pendiente", noLeidos ? "aviso" : "ok",
      el("div", { class: "hud-fila2" }, dato("Avisos", noLeidos == null ? "—" : String(noLeidos), noLeidos ? "aviso" : ""), dato("Recordatorios", String(rs.length))),
      el("p", { class: "hud-nota" }, rs[0] ? "Próximo: " + rs[0].texto + " · " + rs[0].descripcion : "Nada pendiente."));
    const f = d?.finanzas;
    if (f) {
      const dif = f.mes_anterior_mismo_dia ? Math.round((f.gastos - f.mes_anterior_mismo_dia) * 100 / f.mes_anterior_mismo_dia) : null;
      const top = (f.presupuestos || []).slice().sort((x, y) => y.porcentaje - x.porcentaje)[0];
      pintar("finanzas", top?.superado ? "aviso" : "ok", grande(eur(f.gastos / 100), "gastado en " + f.mes_texto),
        dif == null ? null : el("p", { class: "hud-nota" }, el("span", { class: "hud-chip " + (dif > 0 ? "baja" : "sube") }, (dif > 0 ? "▲ " : "▼ ") + Math.abs(dif) + " %"), " frente al mes pasado"),
        top ? el("div", { class: "hud-medidor" }, dato(top.categoria, Math.round(top.porcentaje) + " %"), barra(top.porcentaje, top.superado)) : null);
    } else pintar("finanzas", "ok");
    const inv = d?.inversiones?.valores || [];
    pintar("inversiones", "ok", inv.length ? el("ul", { class: "hud-lista-inv" }, ...inv.slice(0, 5).map((x) =>
      el("li", null, el("span", { class: "n" }, x.nombre || x.simbolo), el("strong", null, eur(x.precio, x.precio >= 1000 ? 0 : 2)), chipCambio(x.variacion_dia)))) : null);
    if (!Sesion.esAdmin) return;
    apUltimo = d?.aplicaciones || apUltimo;
    pintarCasa();
    const rd = d?.red, vpn = v?.value?.ok && v.value.data.conectado ? v.value.data.clientes : null, s = sh?.value?.ok && sh.value.data.conectado ? sh.value.data : null;
    pintar("red", rd?.n_desconocidos ? "aviso" : "ok",
      el("div", { class: "hud-fila2" }, dato("Dispositivos", rd ? String(rd.total) : "—"), dato("Sin identificar", rd ? String(rd.n_desconocidos) : "—", rd?.n_desconocidos ? "aviso" : "")),
      el("div", { class: "hud-fila2" }, dato("VPN", vpn ? `${vpn.filter((x) => x.conectado).length}/${vpn.length}` : "—"), dato("Anuncios bloqueados", s ? fmtNum(s.bloqueadas ?? 0) : "—")),
      s && s.porcentaje != null ? el("div", { class: "hud-medidor" }, dato("Bloqueo", String(s.porcentaje).replace(".", ",") + " %"), barra(s.porcentaje)) : null);
  }
  function pintarCasa() {
    const ap = apUltimo, sis = sisUltimo, ram = ap?.raspberry?.ram, temp = sis.temperatura ?? ap?.raspberry?.temperatura;
    pintar("casa", ap && !ap.ok ? "aviso" : "ok",
      el("p", { class: "hud-veredicto " + (ap && !ap.ok ? "aviso" : "ok") }, ap ? (ap.ok ? "Todo en orden" : ap.problemas.length + (ap.problemas.length === 1 ? " cosa que revisar" : " cosas que revisar")) : "Comprobando…"),
      el("div", { class: "hud-anillos" }, anillo(sis.cpu, "CPU", "%", sis.cpu > 85), anillo(ram, "RAM", "%", ram > 85), anillo(temp, "Temp.", "°", temp >= 75)),
      cpuHist.length > 1 ? el("div", { class: "hud-medidor" }, el("span", { class: "hud-mini" }, "CPU · último minuto"), linea(cpuHist)) : null,
      ap && !ap.ok ? el("ul", { class: "hud-problemas" }, ...ap.problemas.slice(0, 3).map((p) => el("li", null, mayus(p)))) : null);
  }
  async function directo() {
    if (!activo || !Sesion.esAdmin || opts.tarjetas.casa === false || document.hidden) return;
    const r = await api("/api/sistema/directo");
    if (!r.ok || !r.data?.sistema) return;
    sisUltimo = r.data.sistema;
    cpuHist.push(sisUltimo.cpu); if (cpuHist.length > 12) cpuHist.shift();
    pintarCasa();
  }

  // --- Acciones rápidas ---
  function textoResumen() {
    const d = resumen; if (!d) return "";
    const partes = [d.saludo + "."];
    if (d.tiempo) partes.push(`En ${d.tiempo.ciudad}, ${d.tiempo.cielo}, con ${d.tiempo.actual ?? d.tiempo.max} grados y una máxima de ${d.tiempo.max}.`);
    if (d.aplicaciones) partes.push(d.aplicaciones.ok ? "Todo en casa está en orden." : "Hay que revisar: " + d.aplicaciones.problemas.join(", ") + ".");
    const ev = d.agenda?.eventos || [];
    partes.push(ev.length ? `Hoy tienes ${ev.length === 1 ? "un evento" : ev.length + " eventos"}: ` + ev.map((e) => (e.todo_el_dia ? "" : "a las " + hora(e.inicio) + ", ") + e.titulo).join("; ") + "." : "No tienes eventos hoy.");
    return partes.join(" ");
  }
  function rapidas() {
    const b = (txt, fn, solo) => { if (solo && !Sesion.esAdmin) return null; const x = el("button", { type: "button", class: "hud-rapida" }, txt); x.addEventListener("click", fn); return x; };
    $w("hud-rapidas").replaceChildren(...[
      b("Leer resumen", () => { const t = textoResumen(); if (t) { $w("hud-subtitulo").textContent = t; Voz.hablar(t); } }),
      b("Silenciar", () => Voz.parar()),
      b("Agenda", () => { location.hash = "agenda"; }),
      b("Pausar anuncios 30 min", async () => {
        if (!(await confirmar("Pausar anuncios", "El bloqueador de anuncios se pausará 30 minutos.", "Pausar"))) return;
        const r = await api("/api/shield/pause", { method: "POST", json: { minutos: 30 } });
        toast(r.ok ? "Bloqueador en pausa 30 min." : (r.data.error || "No se pudo pausar."), r.ok ? "" : "mal");
      }, true),
    ].filter(Boolean));
  }

  function relojLocal() {
    const ahora = new Date(), h = $w("hud-hora");
    h.textContent = ahora.toLocaleTimeString("es-ES", opts.segundos ? { hour: "2-digit", minute: "2-digit", second: "2-digit" } : { hour: "2-digit", minute: "2-digit" });
    h.dateTime = ahora.toISOString();
    $w("hud-fecha").textContent = mayus(ahora.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" }));
  }

  // --- Ratón: parallax de la escena, foco y giro 3D de las tarjetas, cursor luminoso ---
  function alMover(e) {
    const sec = $w("v-hud"), box = sec.getBoundingClientRect();
    puntero = { x: (e.clientX - box.left) / box.width, y: (e.clientY - box.top) / box.height, dentro: true, cx: e.clientX, cy: e.clientY };
    if (!movimiento()) return;
    sec.style.setProperty("--px", (puntero.x - .5).toFixed(3)); sec.style.setProperty("--py", (puntero.y - .5).toFixed(3));
    if (opts.cursor) $w("hud-cursor").style.transform = `translate(${e.clientX}px, ${e.clientY}px)`;
    const t = e.target.closest?.(".hud-card");
    for (const c of sec.querySelectorAll(".hud-card.foco")) if (c !== t) soltar(c);
    if (t) {
      const r = t.getBoundingClientRect(), mx = (e.clientX - r.left) / r.width, my = (e.clientY - r.top) / r.height;
      t.classList.add("foco");
      t.style.setProperty("--mx", (mx * 100).toFixed(1) + "%"); t.style.setProperty("--my", (my * 100).toFixed(1) + "%");
      t.style.setProperty("--rx", ((.5 - my) * 10).toFixed(2) + "deg"); t.style.setProperty("--ry", ((mx - .5) * 12).toFixed(2) + "deg");
    }
  }
  function soltar(c) { c.classList.remove("foco"); c.style.setProperty("--rx", "0deg"); c.style.setProperty("--ry", "0deg"); }
  function alSalir() { puntero.dentro = false; const sec = $w("v-hud"); sec.style.setProperty("--px", "0"); sec.style.setProperty("--py", "0"); sec.querySelectorAll(".hud-card.foco").forEach(soltar); }

  // --- Fondo: estrellas con parallax y rejilla en perspectiva que avanza ---
  function rgba(c, o) { return `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${o})`; }
  function dibujarFondo(ahora) {
    if (!activo || document.hidden) { rafFondo = 0; return; }
    const c = $w("hud-fondo"), dpr = Math.min(1.5, devicePixelRatio || 1), w = c.clientWidth, h = c.clientHeight;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
    const ctx = c.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    const quieto = reducido.matches || !opts.fondo, t = quieto ? 0 : (ahora - t0) / 1000, tema = TEMAS[opts.tema] || TEMAS.cian;
    const px = movimiento() ? puntero.x - .5 : 0, py = movimiento() ? puntero.y - .5 : 0;
    for (const s of estrellas) {
      const o = .2 + .5 * s.z * (.6 + .4 * Math.sin(t * 1.3 + s.f));
      ctx.fillStyle = `rgba(220,235,255,${o.toFixed(2)})`;
      ctx.fillRect(((s.x * w - px * 40 * s.z) % w + w) % w, s.y * h - py * 24 * s.z, s.z * 1.6, s.z * 1.6);
    }
    const horizonte = h * (.68 - py * .04), vx = w / 2 - px * 120;
    ctx.lineWidth = 1;
    for (let i = -16; i <= 16; i++) {
      ctx.strokeStyle = rgba(tema, (.06 + (16 - Math.abs(i)) / 180).toFixed(3));
      ctx.beginPath(); ctx.moveTo(vx + i * 6, horizonte); ctx.lineTo(w / 2 + i * w / 10, h); ctx.stroke();
    }
    const fase = (t * .3) % 1;
    for (let k = 0; k < 12; k++) {
      const z = (k + fase) / 12, y = horizonte + (h - horizonte) * z * z;
      ctx.strokeStyle = rgba(tema, (.04 + .24 * z).toFixed(3));
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }
    const g = ctx.createLinearGradient(0, horizonte - 70, 0, horizonte + 30);
    g.addColorStop(0, rgba(tema, 0)); g.addColorStop(.7, rgba(tema, .14)); g.addColorStop(1, rgba(tema, 0));
    ctx.fillStyle = g; ctx.fillRect(0, horizonte - 70, w, 100);
    if (quieto && !movimiento()) { rafFondo = 0; return; }
    rafFondo = requestAnimationFrame(dibujarFondo);
  }

  // --- Orbe: núcleo que «mira» al ratón, anillos, mira, onda de voz y partículas que se apartan del cursor ---
  function dibujar(ahora) {
    if (!activo || document.hidden) { raf = 0; return; }
    const quieto = reducido.matches;
    if (quieto && ahora - ultimoEstatico < 400) { raf = requestAnimationFrame(dibujar); return; }
    ultimoEstatico = ahora;
    const c = $w("hud-orbe"), box = c.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
    if (!box.width) { raf = requestAnimationFrame(dibujar); return; }
    if (c.width !== Math.round(box.width * dpr) || c.height !== Math.round(box.height * dpr)) { c.width = Math.round(box.width * dpr); c.height = Math.round(box.height * dpr); }
    const ctx = c.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const w = box.width, h = box.height, x = w / 2, y = h / 2, R = Math.min(w, h) * .3, halo = Math.min(w, h) / 2;
    const t = quieto ? 0 : (ahora - t0) / 1000, tema = TEMAS[opts.tema] || TEMAS.cian;
    const objetivo = { reposo: tema, escuchando: [52, 211, 153], pensando: [167, 139, 250], hablando: tema.map((v) => Math.min(255, v + 30)) }[estado] || tema;
    color = color.map((v, i) => v + (objetivo[i] - v) * .08);
    const voz = estado === "escuchando" || estado === "hablando";
    suave += ((voz ? nivel : 0) - suave) * .25;
    const r = R * (1 + (quieto ? 0 : Math.sin(t * 1.1) * .03) + suave * .18), vel = estado === "pensando" ? 2.6 : voz ? 1.4 : .6;
    let ox = 0, oy = 0, mxl = -1e9, myl = -1e9;
    if (movimiento() && puntero.dentro && puntero.cx != null) {
      mxl = puntero.cx - box.left; myl = puntero.cy - box.top;
      const dx = mxl - x, dy = myl - y, d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / (R * 4));
      ox = dx / d * r * .28 * k; oy = dy / d * r * .28 * k;
    }
    ctx.clearRect(0, 0, w, h);
    let g = ctx.createRadialGradient(x, y, r * .2, x, y, halo);
    g.addColorStop(0, rgba(color, .35 + suave * .3)); g.addColorStop(.5, rgba(color, .08)); g.addColorStop(1, rgba(color, 0));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, halo, 0, Math.PI * 2); ctx.fill();
    g = ctx.createRadialGradient(x - r * .25 + ox, y - r * .3 + oy, r * .05, x, y, r);
    g.addColorStop(0, "rgba(255,255,255,.92)"); g.addColorStop(.25, rgba(color, .85)); g.addColorStop(.75, rgba(color.map((v) => v * .35), .9)); g.addColorStop(1, rgba(color.map((v) => v * .15), .2));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r * .78, 0, Math.PI * 2); ctx.fill();
    ctx.save(); ctx.beginPath(); ctx.arc(x, y, r * .78, 0, Math.PI * 2); ctx.clip();
    ctx.globalCompositeOperation = "lighter"; ctx.lineWidth = 1.2;
    for (let i = 0; i < 6; i++) {
      ctx.strokeStyle = rgba(i % 2 ? [255, 255, 255] : color, .16);
      ctx.beginPath(); ctx.ellipse(x + ox * .3, y + oy * .3, r * (.75 - i * .06), r * (.22 + i * .05), t * vel * (.3 + i * .08) + i * 1.05, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.restore();
    ctx.globalCompositeOperation = "lighter";
    [[1.0, 1, [r * .5, r * .18], 1.6, .8], [1.18, -1.3, [r * .08, r * .12], 1, .55], [1.36, .7, [r * 1.2, r * .4], 1, .35]].forEach(([k, s, dash, lw, o]) => {
      ctx.save(); ctx.translate(x, y); ctx.rotate(t * vel * .35 * s); ctx.setLineDash(dash);
      ctx.strokeStyle = rgba(color, o); ctx.lineWidth = lw; ctx.beginPath(); ctx.arc(0, 0, r * k, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
    });
    ctx.strokeStyle = rgba(color, .6); ctx.lineWidth = 1.4;   // marcas de mira
    for (let i = 0; i < 4; i++) { const a = i * Math.PI / 2 + t * .1; ctx.beginPath(); ctx.moveTo(x + Math.cos(a) * r * 1.5, y + Math.sin(a) * r * 1.5); ctx.lineTo(x + Math.cos(a) * r * 1.62, y + Math.sin(a) * r * 1.62); ctx.stroke(); }
    if (suave > .02) {
      ctx.strokeStyle = rgba(color, .9); ctx.lineWidth = 2; ctx.beginPath();
      for (let i = 0; i <= 120; i++) {
        const a = i / 120 * Math.PI * 2, rr = r * .86 + Math.sin(a * 6 + t * 7) * suave * r * .12 + Math.sin(a * 11 - t * 5) * suave * r * .06;
        i ? ctx.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr) : ctx.moveTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
      }
      ctx.closePath(); ctx.stroke();
    }
    for (const p of particulas) {
      if (!quieto) p.a += p.v * vel * .006;
      const rr = Math.min(r * p.r * (1 + suave * .25), halo * .97);
      let qx = x + Math.cos(p.a) * rr, qy = y + Math.sin(p.a) * rr * .92;
      const dx = qx - mxl, dy = qy - myl, d = Math.hypot(dx, dy);
      p.empuje = d < 80 ? Math.min(1, p.empuje + .2) : p.empuje * .92;
      if (p.empuje > .01 && d > 0) { qx += dx / d * 24 * p.empuje; qy += dy / d * 24 * p.empuje; }
      ctx.fillStyle = rgba(p.c ? [167, 139, 250] : color, p.o);
      ctx.beginPath(); ctx.arc(qx, qy, p.s, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
    raf = requestAnimationFrame(dibujar);
  }
  function preparar() {
    particulas.length = 0; estrellas.length = 0;
    const n = Math.max(28, Math.min(110, Math.floor(innerWidth * innerHeight / 15000)));
    for (let i = 0; i < n; i++) particulas.push({ a: Math.random() * Math.PI * 2, r: 1.05 + Math.random() * .75, s: .6 + Math.random() * 1.8, o: .25 + Math.random() * .6, v: (.4 + Math.random()) * (Math.random() < .5 ? -1 : 1), c: Math.random() < .35, empuje: 0 });
    const m = Math.min(160, Math.floor(innerWidth * innerHeight / 9000));
    for (let i = 0; i < m; i++) estrellas.push({ x: Math.random(), y: Math.random() * .64, z: .2 + Math.random() * .8, f: Math.random() * Math.PI * 2 });
  }

  // --- Opciones ---
  function aplicarOpciones() {
    const sec = $w("v-hud");
    sec.style.setProperty("--hud-c", (TEMAS[opts.tema] || TEMAS.cian).join(","));
    sec.classList.toggle("sin-raton", !movimiento());
    sec.classList.toggle("sin-fondo", !opts.fondo);
    sec.classList.toggle("con-cursor", movimiento() && opts.cursor);
    if (!movimiento()) alSalir();
    relojLocal();
    if (activo) { datos(); if (!rafFondo) rafFondo = requestAnimationFrame(dibujarFondo); }
  }
  const INTERRUPTORES = [["hud-op-raton", "raton"], ["hud-op-fondo", "fondo"], ["hud-op-cursor", "cursor"], ["hud-op-segundos", "segundos"], ["hud-op-voz", "voz"]];
  function pintarOpciones() {
    $w("hud-op-tarjetas").replaceChildren(...Object.entries(TARJETAS).filter(([k]) => Sesion.esAdmin || !["casa", "red"].includes(k)).map(([k, nombre]) => {
      const i = el("input", { type: "checkbox", checked: opts.tarjetas[k] !== false });
      i.addEventListener("change", () => { opts.tarjetas[k] = i.checked; guardarOpciones(); });
      return el("label", { class: "interruptor" }, i, el("span", null, nombre));
    }));
    $w("hud-op-temas").replaceChildren(...Object.keys(TEMAS).map((k) => {
      const b = el("button", { type: "button", class: "hud-tema" + (opts.tema === k ? " activo" : ""), title: NOMBRES_TEMA[k] });
      b.setAttribute("aria-label", "Color " + NOMBRES_TEMA[k]); b.setAttribute("aria-pressed", String(opts.tema === k));
      b.style.setProperty("--t", TEMAS[k].join(","));
      b.addEventListener("click", () => { opts.tema = k; guardarOpciones(); pintarOpciones(); });
      return b;
    }));
    for (const [id, k] of INTERRUPTORES) $w(id).checked = !!opts[k];
  }
  function panel(abrir) {
    const p = $w("hud-panel"), si = abrir ?? p.hidden;
    p.hidden = !si; $w("hud-opciones").setAttribute("aria-expanded", String(si));
    if (si) { pintarOpciones(); p.querySelector("input, button")?.focus(); }
  }

  function cambiar(e) {
    estado = e.detail?.estado || "reposo"; nivel = Math.max(0, Math.min(1, Number(e.detail?.nivel) || 0));
    $w("v-hud").dataset.estado = estado; $w("hud-estado").textContent = ESTADOS[estado] || "";
  }
  function activar(si) {
    activo = si;
    clearInterval(refresco); clearInterval(refrescoDirecto);
    if (!si) { cancelAnimationFrame(raf); cancelAnimationFrame(rafFondo); raf = rafFondo = 0; panel(false); return; }
    preparar(); aplicarOpciones(); rapidas(); directo();
    refresco = setInterval(() => { if (!document.hidden) datos(); }, 60000);
    refrescoDirecto = setInterval(directo, 5000);
    if (!raf) raf = requestAnimationFrame(dibujar);
    if (!rafFondo) rafFondo = requestAnimationFrame(dibujarFondo);
  }
  function iniciar() {
    addEventListener("aria:estado", cambiar);
    addEventListener("resize", () => { if (activo) preparar(); });
    addEventListener("aria:hud-texto", (e) => { if (activo) $w("hud-subtitulo").textContent = String(e.detail?.texto || "").slice(-420); });
    addEventListener("visibilitychange", () => { if (activo && !document.hidden) { if (!raf) raf = requestAnimationFrame(dibujar); if (!rafFondo) rafFondo = requestAnimationFrame(dibujarFondo); } });
    reducido.addEventListener?.("change", aplicarOpciones);
    setInterval(() => { if (activo) relojLocal(); }, 1000);
    const sec = $w("v-hud");
    sec.addEventListener("pointermove", alMover); sec.addEventListener("pointerleave", alSalir);
    $w("hud-salir").addEventListener("click", () => { location.hash = "inicio"; });
    $w("hud-pantalla").addEventListener("click", async () => { try { if (!document.fullscreenElement) await document.documentElement.requestFullscreen(); else await document.exitFullscreen(); } catch (_) { toast("La pantalla completa no está disponible.", "mal"); } });
    $w("hud-opciones").addEventListener("click", () => panel());
    $w("hud-panel-cerrar").addEventListener("click", () => { panel(false); $w("hud-opciones").focus(); });
    sec.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$w("hud-panel").hidden) { panel(false); $w("hud-opciones").focus(); } });
    for (const [id, k] of INTERRUPTORES) $w(id).addEventListener("change", () => { opts[k] = $w(id).checked; guardarOpciones(); });
    $w("hud-op-reset").addEventListener("click", () => { opts = structuredClone(DEFECTO); guardarOpciones(); pintarOpciones(); });
    Voz.botonMic($w("hud-mic"), (t) => { $w("hud-texto").value = t; $w("hud-form").requestSubmit(); });
    $w("hud-manos").addEventListener("click", () => ManosLibres.activa() ? ManosLibres.parar() : ManosLibres.iniciar());
    ManosLibres.alCambiar((on) => { $w("hud-manos").setAttribute("aria-pressed", on); });
    $w("hud-form").addEventListener("submit", async (e) => {
      e.preventDefault(); const t = $w("hud-texto").value.trim(); if (!t) return;
      $w("hud-texto").value = ""; const r = await Chat.enviarDesdeVoz(t); location.hash = "hud";
      if (r) { $w("hud-subtitulo").textContent = r.slice(0, 420); if (opts.voz) Voz.hablar(r); }
    });
  }
  return { iniciar, activar };
})();
