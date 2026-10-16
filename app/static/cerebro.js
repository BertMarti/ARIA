"use strict";
// Grafo 3D propio: una proyección sencilla mantiene la vista ligera en la Raspberry.
const Cerebro = (() => {
  const COLORES = { ok: [56, 214, 255], aviso: [251, 191, 36], mal: [244, 114, 182], apagado: [100, 116, 139] };
  const GRUPOS = { núcleo: "Núcleo", cerebros: "Cerebros", agentes: "Agentes", herramientas: "Herramientas", módulos: "Módulos", servicios: "Servicios", canales: "Canales", datos: "Datos", túnel: "Túnel", copias: "Copias" };
  const reducido = matchMedia("(prefers-reduced-motion: reduce)");
  let activo = false, raf = 0, reloj = 0, datos = { nodos: [], enlaces: [] }, seleccion = null, sobre = null, ultimo = 0, actividad = [], ultimoAct = 0;
  let giro = { x: -.12, y: .08 }, zoom = 1, arrastre = null;
  const $ = (id) => document.getElementById(id);
  const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
  const grupo = (n) => n.grupo === "núcleo" ? 0 : ["cerebros", "servicios", "agentes", "herramientas", "módulos", "canales", "datos", "túnel", "copias"].indexOf(n.grupo) + 1;

  function colocar() {
    const porGrupo = {};
    for (const n of datos.nodos) (porGrupo[n.grupo] ||= []).push(n);
    for (const [g, lista] of Object.entries(porGrupo)) lista.forEach((n, i) => {
      if (g === "núcleo") { n.x = n.y = n.z = 0; return; }
      const a = i / Math.max(1, lista.length) * Math.PI * 2 + grupo(n) * .37;
      const r = g === "herramientas" ? 210 : g === "agentes" ? 155 : 270;
      n.x = Math.cos(a) * r; n.z = Math.sin(a) * r; n.y = (grupo(n) - 4) * 35 + Math.sin(i * 2.1) * 38;
    });
  }
  function proyectar(n, w, h) {
    const cy = Math.cos(giro.y), sy = Math.sin(giro.y), cx = Math.cos(giro.x), sx = Math.sin(giro.x);
    const x1 = n.x * cy - n.z * sy, z1 = n.x * sy + n.z * cy, y1 = n.y * cx - z1 * sx, z = n.y * sx + z1 * cx;
    const p = 600 / (600 + z) * zoom;
    return { x: w / 2 + x1 * p, y: h / 2 + y1 * p, z, r: Math.max(3, (n.grupo === "núcleo" ? 15 : 7) * p), p };
  }
  function pulsos(origen, destino) { return actividad.filter((a) => a.agente === origen || a.herramienta === destino || (origen === "aria" && destino.startsWith("herramientas-"))); }
  function dibujar(t) {
    raf = 0; if (!activo || document.hidden) return;
    const c = $("cerebro-canvas"), box = c.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1); if (!box.width) return;
    if (c.width !== box.width * dpr || c.height !== box.height * dpr) { c.width = box.width * dpr; c.height = box.height * dpr; }
    const x = c.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0); const w = box.width, h = box.height, quieto = reducido.matches;
    if (!quieto && !arrastre) giro.x += .0008; x.clearRect(0, 0, w, h);
    const centro = { x: w / 2, y: h / 2 }, grad = x.createRadialGradient(centro.x, centro.y, 5, centro.x, centro.y, Math.max(w, h) * .7); grad.addColorStop(0, "rgba(31,64,105,.18)"); grad.addColorStop(1, "rgba(4,8,16,0)"); x.fillStyle = grad; x.fillRect(0, 0, w, h);
    x.strokeStyle = "rgba(56,214,255,.08)"; x.lineWidth = 1; for (let i = -8; i <= 8; i++) { x.beginPath(); x.moveTo(w / 2 + i * 28, h * .55); x.lineTo(w / 2 + i * 110, h); x.stroke(); x.beginPath(); x.moveTo(0, h * .55 + i * 22); x.lineTo(w, h * .55 + i * 22); x.stroke(); }
    const ps = new Map(datos.nodos.map((n) => [n.id, proyectar(n, w, h)]));
    for (const e of datos.enlaces) { const a = ps.get(e.origen), b = ps.get(e.destino); if (!a || !b) continue; const activoLink = sobre && (e.origen === sobre.id || e.destino === sobre.id); x.strokeStyle = activoLink ? "rgba(56,214,255,.7)" : "rgba(91,115,160,.24)"; x.lineWidth = activoLink ? 1.8 : 1; x.beginPath(); x.moveTo(a.x, a.y); x.lineTo(b.x, b.y); x.stroke(); }
    for (const [i, n] of datos.nodos.map((n, i) => [i, n]).sort((a, b) => ps.get(a[1].id).z - ps.get(b[1].id).z)) { const p = ps.get(n.id), col = COLORES[n.estado] || COLORES.apagado, foco = sobre?.id === n.id || seleccion?.id === n.id; const pulso = actividad.some((a) => a.herramienta && n.id.includes(a.herramienta)) && !quieto ? 1 + Math.sin(t / 100 + i) * .18 : 1; const alpha = Math.max(.25, Math.min(1, .92 - p.z / 950)); x.globalCompositeOperation = "lighter"; x.fillStyle = rgba(col, alpha * .22); x.beginPath(); x.arc(p.x, p.y, p.r * 3.5 * pulso, 0, Math.PI * 2); x.fill(); x.fillStyle = rgba(col, alpha); x.beginPath(); x.arc(p.x, p.y, p.r * (foco ? 1.25 : 1), 0, Math.PI * 2); x.fill(); x.globalCompositeOperation = "source-over"; if (foco || p.z < 50) { x.fillStyle = "rgba(230,240,255,.9)"; x.font = "11px ui-monospace, monospace"; x.textAlign = "center"; x.fillText(n.nombre, p.x, p.y - p.r - 7); } }
    if (!quieto) raf = requestAnimationFrame(dibujar);
  }
  function pintarPanel(n) { const p = $("cerebro-panel"); p.replaceChildren(); if (!n) { p.append(el("p", { class: "muted" }, "Selecciona un nodo para ver sus datos.")); return; } p.append(el("h2", null, n.nombre), el("p", { class: "cerebro-meta" }, `${n.grupo} · ${n.estado}`), el("p", { class: n.estado === "mal" ? "error" : "muted" }, n.detalle || "Sin detalle")); const dl = el("dl", { class: "cerebro-datos" }); for (const [k, v] of Object.entries(n.datos || {})) dl.append(el("dt", null, k), el("dd", null, String(v ?? "—"))); p.append(dl); }
  function nodoEn(e) { const c = $("cerebro-canvas"), r = c.getBoundingClientRect(), w = r.width, h = r.height; let mejor = null, distancia = 24; for (const n of datos.nodos) { const p = proyectar(n, w, h), d = Math.hypot(e.clientX - r.left - p.x, e.clientY - r.top - p.y); if (d < Math.max(distancia, p.r + 7)) { mejor = n; distancia = d; } } return mejor; }
  async function cargar() { const r = await api("/api/cerebro"); if (r.ok) { datos = r.data; colocar(); pintarLeyenda(); ultimo = Date.now(); } if (!raf) raf = requestAnimationFrame(dibujar); }
  function pintarLeyenda() { $("cerebro-leyenda").replaceChildren(...Object.entries(GRUPOS).map(([k, v]) => el("span", { class: "cerebro-leyenda-item grupo-" + k.replace("/", "-") }, v))); }
  async function cargarActividad() { if (!activo || document.hidden) return; const r = await api(`/api/cerebro/actividad?desde=${encodeURIComponent(ultimoAct)}`); if (r.ok) { actividad = [...actividad, ...(r.data.actividad || [])].slice(-100); ultimoAct = Date.now() / 1000; $("cerebro-acciones").textContent = `${actividad.filter((a) => a.ts > Date.now() / 1000 - 60).length} acciones en el último minuto`; if (!reducido.matches && !raf) raf = requestAnimationFrame(dibujar); } }
  function iniciar() { const c = $("cerebro-canvas"); c.addEventListener("pointerdown", (e) => { arrastre = { x: e.clientX, y: e.clientY }; c.setPointerCapture(e.pointerId); }); c.addEventListener("pointermove", (e) => { sobre = nodoEn(e); if (arrastre) { giro.x += (e.clientX - arrastre.x) * .008; giro.y += (e.clientY - arrastre.y) * .008; arrastre = { x: e.clientX, y: e.clientY }; } if (!raf) raf = requestAnimationFrame(dibujar); }); c.addEventListener("pointerup", (e) => { if (arrastre) { const n = nodoEn(e); if (n) { seleccion = n; pintarPanel(n); } } arrastre = null; }); c.addEventListener("wheel", (e) => { e.preventDefault(); zoom = Math.max(.55, Math.min(2.2, zoom * (e.deltaY < 0 ? 1.08 : .92))); if (!raf) raf = requestAnimationFrame(dibujar); }, { passive: false }); c.addEventListener("dblclick", () => { giro = { x: -.12, y: .08 }; zoom = 1; }); c.addEventListener("keydown", (e) => { if (e.key === "ArrowLeft") giro.x -= .08; if (e.key === "ArrowRight") giro.x += .08; if (e.key === "ArrowUp") giro.y -= .08; if (e.key === "ArrowDown") giro.y += .08; if (e.key === "+" || e.key === "=") zoom = Math.min(2.2, zoom * 1.1); if (e.key === "-") zoom = Math.max(.55, zoom * .9); if (!raf) raf = requestAnimationFrame(dibujar); }); addEventListener("resize", () => { if (activo && !raf) raf = requestAnimationFrame(dibujar); }); addEventListener("visibilitychange", () => { if (activo && !document.hidden && !raf) raf = requestAnimationFrame(dibujar); }); pintarLeyenda(); }
  function activar(si) { activo = si; clearInterval(reloj); if (!si) { cancelAnimationFrame(raf); raf = 0; return; } cargar(); cargarActividad(); reloj = setInterval(() => { if (!document.hidden) { cargar(); cargarActividad(); } }, 5000); }
  return { iniciar, activar };
})();
