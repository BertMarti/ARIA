"use strict";
// Red 3D de ARIA: un HUD ligero, sin dependencias ni estilos inline.
const Cerebro = (() => {
  const COLORES = { "núcleo": [234, 250, 255], cerebros: [124, 140, 255], agentes: [56, 214, 255], herramientas: [52, 211, 153], módulos: [251, 191, 36], servicios: [96, 165, 250], canales: [244, 114, 182], datos: [203, 213, 225], túnel: [251, 146, 60], copias: [251, 146, 60] };
  const ESTADOS = { ok: [52, 211, 153], aviso: [251, 191, 36], mal: [239, 68, 68], apagado: [100, 116, 139] };
  const GRUPOS = { núcleo: "Núcleo", cerebros: "Cerebros", agentes: "Agentes", herramientas: "Herramientas", módulos: "Módulos", servicios: "Servicios", canales: "Canales", datos: "Datos", túnel: "Túnel", copias: "Copias" };
  const reducido = matchMedia("(prefers-reduced-motion: reduce)");
  let activo = false, raf = 0, reloj = 0, datos = { nodos: [], enlaces: [] }, seleccion = null, sobre = null, actividad = [], ultimoAct = 0, ultimo = 0;
  let giro = { x: -.35, y: .08 }, zoom = .7, arrastre = null, desplegando = false, calidad = 1, coste = 0;
  let fondo, radar, particulas = [], focus = { x: 0, y: 0, zoom: .7 };
  const $ = (id) => document.getElementById(id);
  const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
  const radio = 260;
  const angulo = (i, total) => i / Math.max(1, total) * Math.PI * 2 - Math.PI / 2;

  function colocar() {
    const porGrupo = {};
    for (const n of datos.nodos) (porGrupo[n.grupo] ||= []).push(n);
    const zonas = {
      cerebros: (i, t) => { const a = angulo(i, t); return [Math.cos(a) * radio, -radio * .62, Math.sin(a) * radio]; },
      servicios: (i, t) => { const a = angulo(i, t); return [Math.cos(a) * radio, radio * .62, Math.sin(a) * radio]; },
      agentes: (i, t) => { const a = angulo(i, t); return [Math.cos(a) * radio * .55, 0, Math.sin(a) * radio * .55]; },
      herramientas: (i, t) => { const a = angulo(i, t); return [Math.cos(a) * radio, 0, Math.sin(a) * radio]; },
      módulos: (i, t) => [radio * .92, (i - (t - 1) / 2) * 32, i % 2 ? 45 : -45],
      canales: (i, t) => [-radio * .92, (i - (t - 1) / 2) * 32, i % 2 ? 45 : -45],
      datos: (i, t) => [(i - (t - 1) / 2) * 58, (i % 2) * 30 - 15, -radio * .88],
      túnel: (i, t) => [radio * .48 + i * 42, -radio * .82 + (i - (t - 1) / 2) * 30, 25],
      copias: (i, t) => [-radio * .48 - i * 42, -radio * .82 + (i - (t - 1) / 2) * 30, 25]
    };
    for (const [g, lista] of Object.entries(porGrupo)) lista.forEach((n, i) => {
      const p = g === "núcleo" ? [0, 0, 0] : (zonas[g] || zonas.datos)(i, lista.length);
      n.x = p[0]; n.y = p[1]; n.z = p[2]; n._radio = g === "núcleo" ? 34 : (g === "agentes" || g === "cerebros" ? 9 : 6);
    });
  }
  function proyectar(n, w, h) {
    const cy = Math.cos(giro.y), sy = Math.sin(giro.y), cx = Math.cos(giro.x), sx = Math.sin(giro.x);
    const x1 = n.x * cy - n.z * sy, z1 = n.x * sy + n.z * cy, y1 = n.y * cx - z1 * sx, z = n.y * sx + z1 * cx;
    const p = 600 / (600 + z) * zoom;
    return { x: w / 2 + x1 * p, y: h / 2 + y1 * p, z, r: Math.max(2.5, (n._radio || 6) * p), p };
  }
  function reciente(e) { return actividad.some((a) => a.herramienta && (e.origen.includes(a.herramienta) || e.destino.includes(a.herramienta))); }
  function conectado(id) { return datos.enlaces.some((e) => (e.origen === id || e.destino === id) && (seleccion?.id === id || sobre?.id === id || seleccion?.id === e.origen || seleccion?.id === e.destino || sobre?.id === e.origen || sobre?.id === e.destino)); }
  function crearFondo(w, h) {
    if (!fondo) fondo = document.createElement("canvas");
    const dpr = Math.min(1.25, devicePixelRatio || 1); fondo.width = w * dpr; fondo.height = h * dpr;
    const x = fondo.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, w, h);
    const niebla = x.createRadialGradient(w * .5, h * .42, 5, w * .5, h * .42, Math.max(w, h) * .72);
    niebla.addColorStop(0, "rgba(41,75,126,.25)"); niebla.addColorStop(.5, "rgba(45,24,91,.08)"); niebla.addColorStop(1, "rgba(2,5,13,0)"); x.fillStyle = niebla; x.fillRect(0, 0, w, h);
    const n = Math.min(180, Math.floor(w * h / 9000));
    for (let i = 0; i < n; i++) { const z = .15 + ((i * 37) % 100) / 120, sx = (i * 97.13 % 100) / 100 * w, sy = (i * 53.7 % 62) / 100 * h; x.fillStyle = `rgba(205,230,255,${(.13 + z * .52).toFixed(2)})`; x.fillRect(sx, sy, z * 1.7, z * 1.7); }
    const hy = h * .66, vx = w / 2;
    x.lineWidth = 1; for (let i = -15; i <= 15; i++) { x.strokeStyle = `rgba(56,214,255,${(.025 + (15 - Math.abs(i)) / 800).toFixed(3)})`; x.beginPath(); x.moveTo(vx + i * 7, hy); x.lineTo(vx + i * w / 9, h); x.stroke(); }
    for (let i = 0; i < 13; i++) { const z = i / 13, y = hy + (h - hy) * z * z; x.strokeStyle = `rgba(167,139,250,${(.035 + z * .13).toFixed(3)})`; x.beginPath(); x.moveTo(0, y); x.lineTo(w, y); x.stroke(); }
  }
  function flujo(x, a, b, na, nb, e, t, brillante, limite) {
    const ca = COLORES[na.grupo] || COLORES.datos, cb = COLORES[nb.grupo] || COLORES.datos;
    const g = x.createLinearGradient(a.x, a.y, b.x, b.y); g.addColorStop(0, rgba(ca, brillante ? .78 : .26)); g.addColorStop(.5, rgba([190,225,255], brillante ? .55 : .12)); g.addColorStop(1, rgba(cb, brillante ? .78 : .26));
    x.strokeStyle = g; x.lineWidth = brillante ? 1.45 : .65; x.beginPath(); x.moveTo(a.x, a.y); x.lineTo(b.x, b.y); x.stroke();
    if (reducido.matches) return;
    const cantidad = Math.min(brillante ? 4 : calidad > .5 ? 2 : 1, limite), fase = (t * (brillante ? .00055 : .0003)) % 1;
    x.globalCompositeOperation = "lighter";
    for (let i = 0; i < cantidad; i++) { const q = (fase + i / cantidad) % 1, px = a.x + (b.x - a.x) * q, py = a.y + (b.y - a.y) * q, r = brillante ? 2.6 : 1.25; const glow = x.createRadialGradient(px, py, 0, px, py, r * 4); glow.addColorStop(0, "rgba(255,255,255,.95)"); glow.addColorStop(1, "rgba(90,220,255,0)"); x.fillStyle = glow; x.beginPath(); x.arc(px, py, r * 4, 0, Math.PI * 2); x.fill(); x.fillStyle = rgba([220,250,255], .9); x.beginPath(); x.arc(px, py, r, 0, Math.PI * 2); x.fill(); }
    x.globalCompositeOperation = "source-over";
  }
  function dibujarNucleo(x, p, t) {
    const c = [56, 214, 255], r = p.r * (1 + Math.sin(t * .002) * .035); x.globalCompositeOperation = "lighter";
    const onda = (t % 4000) / 4000; x.strokeStyle = rgba(c, (1 - onda) * .24); x.lineWidth = 1.4; x.beginPath(); x.arc(p.x, p.y, r * (1.3 + onda * 5.2), 0, Math.PI * 2); x.stroke();
    const halo = x.createRadialGradient(p.x, p.y, r * .2, p.x, p.y, r * 7); halo.addColorStop(0, rgba(c, .48)); halo.addColorStop(.34, rgba([167,139,250], .2)); halo.addColorStop(1, rgba(c, 0)); x.fillStyle = halo; x.beginPath(); x.arc(p.x, p.y, r * 7, 0, Math.PI * 2); x.fill();
    const orb = x.createRadialGradient(p.x - r * .35, p.y - r * .4, r * .05, p.x, p.y, r); orb.addColorStop(0, "rgba(255,255,255,.98)"); orb.addColorStop(.24, rgba(c, .9)); orb.addColorStop(.72, rgba([92,56,190], .8)); orb.addColorStop(1, rgba([8,16,48], .25)); x.fillStyle = orb; x.beginPath(); x.arc(p.x, p.y, r, 0, Math.PI * 2); x.fill();
    x.save(); x.beginPath(); x.arc(p.x, p.y, r * .92, 0, Math.PI * 2); x.clip(); x.lineWidth = 1.2;
    for (let i = 0; i < 5; i++) { x.strokeStyle = rgba(i % 2 ? [167,139,250] : c, .32); x.beginPath(); x.ellipse(p.x, p.y, r * (.7 - i * .07), r * (.18 + i * .06), t * .0005 * (i + 1) + i, 0, Math.PI * 2); x.stroke(); } x.restore();
    for (const [k, v, dash] of [[1.35, .82, [r * .38, r * .18]], [1.72, .62, [r * .1, r * .32]], [2.1, .42, [r * .5, r * .08]]]) { x.save(); x.translate(p.x, p.y); x.rotate(t * .00035 * v); x.setLineDash(dash); x.strokeStyle = rgba(v > .6 ? c : [167,139,250], v); x.lineWidth = 1.5; x.beginPath(); x.ellipse(0, 0, r * k, r * (k * .34), v * .7, 0, Math.PI * 2); x.stroke(); x.restore(); } x.globalCompositeOperation = "source-over"; x.fillStyle = "rgba(235,250,255,.95)"; x.font = "bold 12px ui-monospace, monospace"; x.textAlign = "center"; x.textBaseline = "top"; x.shadowColor = "rgba(56,214,255,.9)"; x.shadowBlur = 12; x.fillText("ARIA", p.x, p.y + r * 2.45); x.shadowBlur = 0;
  }
  function dibujarNodo(x, n, p, t, i, quieto) {
    const col = COLORES[n.grupo] || COLORES.datos, estado = ESTADOS[n.estado] || ESTADOS.apagado, foco = sobre?.id === n.id || seleccion?.id === n.id, activoNodo = actividad.some((a) => a.herramienta && n.id.includes(a.herramienta));
    const escala = foco ? 1.18 : 1, r = p.r * escala, brillo = Math.max(.35, .86 - p.z / 950); x.globalCompositeOperation = "lighter";
    const halo = x.createRadialGradient(p.x - r * .35, p.y - r * .4, 0, p.x, p.y, r * 3.2); halo.addColorStop(0, rgba(col, .42)); halo.addColorStop(1, rgba(col, 0)); x.fillStyle = halo; x.beginPath(); x.arc(p.x, p.y, r * 3.2, 0, Math.PI * 2); x.fill();
    const cristal = x.createRadialGradient(p.x - r * .38, p.y - r * .45, r * .05, p.x, p.y, r); cristal.addColorStop(0, rgba(col, .95)); cristal.addColorStop(.3, rgba(col, .82)); cristal.addColorStop(1, rgba(col, .25)); x.fillStyle = cristal; x.beginPath(); x.arc(p.x, p.y, r, 0, Math.PI * 2); x.fill();
    x.globalCompositeOperation = "source-over"; x.strokeStyle = rgba(estado, .95 * brillo); x.lineWidth = 1.4; x.beginPath(); x.arc(p.x, p.y, r + 3, (t * .00025 + i) % 6.28, (t * .00025 + i) % 6.28 + Math.PI * 1.55); x.stroke();
    if (n.estado === "mal" && !quieto) { x.globalCompositeOperation = "lighter"; for (let q = 0; q < 2; q++) { const rr = r * (2 + ((t * .00035 + q * .5) % 1.1)); x.strokeStyle = rgba(estado, .28); x.beginPath(); x.arc(p.x, p.y, rr, 0, Math.PI * 2); x.stroke(); } x.globalCompositeOperation = "source-over"; }
  }
  const ROTULOS = new Set(["cerebros", "agentes", "servicios", "canales", "túnel", "copias"]);
  function rotulo(x, n, p) {
    if (!ROTULOS.has(n.grupo) && sobre?.id !== n.id && seleccion?.id !== n.id) return;
    const opacidad = Math.max(.2, Math.min(1, .9 - p.z / 850)), col = COLORES[n.grupo] || COLORES.datos;
    x.globalCompositeOperation = "source-over"; x.fillStyle = rgba(col, opacidad); x.font = "10px ui-monospace, monospace"; x.textAlign = "center"; x.textBaseline = "bottom"; x.fillText(String(n.nombre || n.id).toUpperCase(), p.x, p.y - p.r - 7);
  }
  function pulsoEnlaces(x, a, b, fase) {
    if (reducido.matches || fase > 1) return;
    const px = a.x + (b.x - a.x) * fase, py = a.y + (b.y - a.y) * fase, op = (1 - fase) * .34;
    x.globalCompositeOperation = "lighter"; const g = x.createRadialGradient(px, py, 0, px, py, 15); g.addColorStop(0, `rgba(220,250,255,${op})`); g.addColorStop(1, "rgba(56,214,255,0)"); x.fillStyle = g; x.beginPath(); x.arc(px, py, 15, 0, Math.PI * 2); x.fill(); x.globalCompositeOperation = "source-over";
  }
  function visor(x, n, p, w, h) {
    if (!n || !sobre || sobre.id !== n.id) return;
    const text = String(n.nombre || n.id);
    x.font = "11px ui-monospace, monospace";
    const width = Math.min(190, x.measureText(text).width + 34);
    const left = Math.max(8, Math.min(w - width - 8, p.x - width / 2));
    const top = Math.max(30, Math.min(h - 31, p.y - p.r - 44));
    x.fillStyle = "rgba(4,13,28,.9)";
    x.fillRect(left, top, width, 23);
    x.strokeStyle = rgba(COLORES[n.grupo] || COLORES.datos, .75);
    x.lineWidth = 1;
    x.beginPath();
    x.moveTo(left, top + 6);
    x.lineTo(left, top);
    x.lineTo(left + 6, top);
    x.moveTo(left + width - 6, top);
    x.lineTo(left + width, top);
    x.lineTo(left + width, top + 6);
    x.stroke();
    x.fillStyle = "rgba(230,245,255,.95)";
    x.textAlign = "center";
    x.fillText(text, left + width / 2, top + 15);
  }
  function radarDibujar(w, h) { if (!radar) return; const x = radar.getContext("2d"), s = 96; x.clearRect(0, 0, s, s); x.strokeStyle = "rgba(56,214,255,.35)"; x.beginPath(); x.arc(48, 48, 37, 0, 7); x.stroke(); x.beginPath(); x.moveTo(48, 10); x.lineTo(48, 86); x.moveTo(10, 48); x.lineTo(86, 48); x.stroke(); for (const n of datos.nodos) { const px = 48 + n.x / radio * 33, py = 48 + n.z / radio * 33; x.fillStyle = rgba(COLORES[n.grupo] || COLORES.datos, n.grupo === "núcleo" ? 1 : .7); x.fillRect(px - 1.5, py - 1.5, 3, 3); } x.strokeStyle = "rgba(255,255,255,.9)"; x.beginPath(); x.moveTo(48, 48); x.lineTo(48 + Math.sin(giro.y) * 27, 48 - Math.cos(giro.y) * 27); x.stroke(); }
  function dibujar(t) {
    raf = 0; if (!activo || document.hidden) return; const c = $("cerebro-canvas"), box = c.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1); if (!box.width) return; const w = box.width, h = box.height; if (!fondo || c.width !== w * dpr || c.height !== h * dpr) { c.width = w * dpr; c.height = h * dpr; crearFondo(w, h); } const x = c.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0); const quieto = reducido.matches; if (!quieto && !arrastre && !seleccion) giro.y += .0008 * calidad;
    zoom += (focus.zoom - zoom) * (quieto ? 1 : .035); if (seleccion) { const q = proyectar(seleccion, w, h); /* q.x=100, centro=400 => desplazamiento +300. */ const paso = quieto ? 1 : .09; focus.x += (w / 2 - q.x - focus.x) * paso; focus.y += (h / 2 - q.y - focus.y) * paso; } else { focus.x *= quieto ? 0 : .96; focus.y *= quieto ? 0 : .96; } x.clearRect(0, 0, w, h); x.drawImage(fondo, 0, 0, w, h); const ps = new Map(datos.nodos.map((n) => { const e = desplegando && !quieto ? Math.min(1, Math.max(0, (t - (n._inicio || 0)) / 1500)) : 1; const p = proyectar(e < 1 ? { ...n, x: n.x * e, y: n.y * e, z: n.z * e } : n, w, h); p.x += focus.x; p.y += focus.y; return [n.id, p]; }));
     let partículas = 300, pulso = quieto ? 2 : (t % 4000) / 520; for (const e of datos.enlaces) { const a = ps.get(e.origen), b = ps.get(e.destino), na = datos.nodos.find((n) => n.id === e.origen), nb = datos.nodos.find((n) => n.id === e.destino); if (a && b && na && nb) { const brillante = !!(seleccion && (e.origen === seleccion.id || e.destino === seleccion.id) || sobre && (e.origen === sobre.id || e.destino === sobre.id) || reciente(e)); flujo(x, a, b, na, nb, e, t, brillante, partículas); if (na.grupo === "núcleo" || nb.grupo === "núcleo") pulsoEnlaces(x, na.grupo === "núcleo" ? a : b, na.grupo === "núcleo" ? b : a, pulso); partículas -= brillante ? 4 : calidad > .5 ? 2 : 1; if (partículas <= 0) break; } }
     const nucleo = datos.nodos.find((n) => n.grupo === "núcleo"); for (const n of datos.nodos.slice().sort((a, b) => ps.get(a.id).z - ps.get(b.id).z)) { const p = ps.get(n.id); if (n.grupo !== "núcleo") dibujarNodo(x, n, p, quieto ? 0 : t, datos.nodos.indexOf(n), quieto); } if (nucleo) dibujarNucleo(x, ps.get(nucleo.id), quieto ? 0 : t);
     for (const n of datos.nodos) { const p = ps.get(n.id); if (n.grupo !== "núcleo") rotulo(x, n, p); if (n.grupo !== "núcleo" && (sobre?.id === n.id || seleccion?.id === n.id)) visor(x, n, p, w, h); } radarDibujar(w, h); if (desplegando && datos.nodos.every((n) => t - (n._inicio || t) >= 1500)) desplegando = false;
    coste = performance.now() - t; if (coste > 25) calidad = Math.max(.35, calidad * .9); else if (coste < 16) calidad = Math.min(1, calidad + .01); if (!quieto) raf = requestAnimationFrame(dibujar);
  }
   function pintarPanel(n) { const p = $("cerebro-panel"); p.replaceChildren(); if (!n) { p.append(el("p", { class: "muted" }, "Selecciona un nodo para ver sus datos.")); return; } const conexiones = datos.enlaces.filter((e) => e.origen === n.id || e.destino === n.id).map((e) => e.origen === n.id ? e.destino : e.origen).map((id) => datos.nodos.find((item) => item.id === id)).filter(Boolean); const estado = el("span", { class: `cerebro-estado cerebro-estado-${n.estado}` }, n.estado); p.append(el("h2", null, n.nombre), el("p", { class: "cerebro-meta" }, n.grupo, " · ", estado)); p.append(el("h3", null, "Qué hace"), el("p", null, n.que_hace || "Forma parte de la arquitectura de ARIA.")); p.append(el("h3", null, "Ahora mismo"), el("p", { class: n.estado === "mal" ? "error" : "muted" }, n.detalle || "Sin detalle")); const dl = el("dl", { class: "cerebro-datos" }); for (const [k, v] of Object.entries(n.datos || {})) dl.append(el("dt", null, k), el("dd", null, String(v ?? "—"))); p.append(dl, el("h3", null, "Cómo mejorarlo"), el("ul", { class: "cerebro-mejoras" }, ...(n.mejoras || []).map((texto) => el("li", null, texto))), el("h3", null, "Conexiones")); const lista = el("ul", { class: "cerebro-conexiones" }); for (const otro of conexiones) { const boton = el("button", { type: "button", class: "cerebro-conexion" }, otro.nombre); boton.addEventListener("click", () => { seleccion = otro; focus.zoom = 1.12; pintarPanel(otro); if (!raf) raf = requestAnimationFrame(dibujar); }); lista.append(el("li", null, boton)); } p.append(lista); }
   function nodoEn(e) { const c = $("cerebro-canvas"), r = c.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1), x = ((e.clientX - r.left) * c.width / r.width) / dpr, y = ((e.clientY - r.top) * c.height / r.height) / dpr; let mejor = null, distancia = 24; for (const n of datos.nodos) { const p = proyectar(n, r.width, r.height); p.x += focus.x; p.y += focus.y; const d = Math.hypot(x - p.x, y - p.y); if (d < Math.max(distancia, p.r + 7)) { mejor = n; distancia = d; } } return mejor; }
  function pintarLeyenda() { $("cerebro-leyenda").replaceChildren(...Object.entries(GRUPOS).map(([k, v]) => el("span", { class: "cerebro-leyenda-item grupo-" + k.replace("/", "-"), "data-grupo": k }, v)), el("span", { class: "cerebro-anillo" }, "Anillo: estado")); }
  async function cargar() { const r = await api("/api/cerebro"); if (r.ok) { const primera = !datos.nodos.length; datos = r.data; colocar(); if (primera && !reducido.matches) { const ahora = performance.now(); datos.nodos.forEach((n, i) => { n._inicio = ahora + i * 18; }); desplegando = true; } pintarLeyenda(); ultimo = Date.now(); } if (!raf) raf = requestAnimationFrame(dibujar); }
  async function cargarActividad() { if (!activo || document.hidden) return; const r = await api(`/api/cerebro/actividad?desde=${encodeURIComponent(ultimoAct)}`); if (r.ok) { actividad = [...actividad, ...(r.data.actividad || [])].slice(-100); ultimoAct = Date.now() / 1000; $("cerebro-acciones").textContent = `${actividad.filter((a) => a.ts > Date.now() / 1000 - 60).length} acciones/min`; if (!reducido.matches && !raf) raf = requestAnimationFrame(dibujar); } }
    function iniciar() { const c = $("cerebro-canvas"), escena = c.closest(".cerebro-escena"); radar = document.createElement("canvas"); radar.className = "cerebro-radar"; radar.width = 96; radar.height = 96; radar.setAttribute("aria-label", "Orientación de la cámara"); escena.append(radar); c.addEventListener("pointerdown", (e) => { arrastre = { x: e.clientX, y: e.clientY, inicioX: e.clientX, inicioY: e.clientY, movido: false }; c.setPointerCapture(e.pointerId); }); c.addEventListener("pointermove", (e) => { sobre = nodoEn(e); if (arrastre) { const dx = e.clientX - arrastre.x, dy = e.clientY - arrastre.y; arrastre.movido ||= Math.hypot(e.clientX - arrastre.inicioX, e.clientY - arrastre.inicioY) >= 8; giro.x += dy * .008; giro.y += dx * .008; arrastre.x = e.clientX; arrastre.y = e.clientY; } if (!raf) raf = requestAnimationFrame(dibujar); }); c.addEventListener("pointerup", (e) => { if (arrastre && !arrastre.movido) { const n = nodoEn(e); seleccion = n || null; focus.zoom = n ? 1.12 : .7; pintarPanel(n); } arrastre = null; if (!raf) raf = requestAnimationFrame(dibujar); }); c.addEventListener("wheel", (e) => { e.preventDefault(); focus.zoom = Math.max(.55, Math.min(2.2, focus.zoom * (e.deltaY < 0 ? 1.08 : .92))); }, { passive: false }); c.addEventListener("dblclick", () => { giro = { x: -.35, y: .08 }; focus = { x: 0, y: 0, zoom: .7 }; seleccion = null; pintarPanel(null); if (!raf) raf = requestAnimationFrame(dibujar); }); c.addEventListener("keydown", (e) => { if (e.key === "Escape") { giro = { x: -.35, y: .08 }; focus = { x: 0, y: 0, zoom: .7 }; seleccion = null; pintarPanel(null); } if (e.key === "ArrowLeft") giro.y -= .08; if (e.key === "ArrowRight") giro.y += .08; if (e.key === "ArrowUp") giro.x -= .08; if (e.key === "ArrowDown") giro.x += .08; if (e.key === "+" || e.key === "=") focus.zoom = Math.min(2.2, focus.zoom * 1.1); if (e.key === "-") focus.zoom = Math.max(.55, focus.zoom * .9); if (!raf) raf = requestAnimationFrame(dibujar); }); addEventListener("resize", () => { if (activo && !raf) raf = requestAnimationFrame(dibujar); }); addEventListener("visibilitychange", () => { if (activo && !document.hidden && !raf) raf = requestAnimationFrame(dibujar); }); pintarLeyenda(); }
  function activar(si) { activo = si; clearInterval(reloj); if (!si) { cancelAnimationFrame(raf); raf = 0; return; } cargar(); cargarActividad(); reloj = setInterval(() => { if (!document.hidden) { cargar(); cargarActividad(); } }, 5000); }
  return { iniciar, activar };
})();
