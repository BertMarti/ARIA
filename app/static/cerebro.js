"use strict";
// Grafo 3D propio: una proyección sencilla mantiene la vista ligera en la Raspberry.
const Cerebro = (() => {
  const COLORES = { "núcleo": [234, 250, 255], cerebros: [124, 140, 255], agentes: [56, 214, 255], herramientas: [52, 211, 153], módulos: [251, 191, 36], servicios: [96, 165, 250], canales: [244, 114, 182], datos: [203, 213, 225], túnel: [251, 146, 60], copias: [251, 146, 60] };
  const ESTADOS = { ok: [52, 211, 153], aviso: [251, 191, 36], mal: [239, 68, 68], apagado: [100, 116, 139] };
  const GRUPOS = { núcleo: "Núcleo", cerebros: "Cerebros", agentes: "Agentes", herramientas: "Herramientas", módulos: "Módulos", servicios: "Servicios", canales: "Canales", datos: "Datos", túnel: "Túnel", copias: "Copias" };
  const reducido = matchMedia("(prefers-reduced-motion: reduce)");
  let activo = false, raf = 0, reloj = 0, datos = { nodos: [], enlaces: [] }, seleccion = null, sobre = null, ultimo = 0, actividad = [], ultimoAct = 0;
  let giro = { x: -20 * Math.PI / 180, y: .08 }, zoom = .7, arrastre = null, desplegando = false;
  const $ = (id) => document.getElementById(id);
  const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
  const esGrupo = (n, g) => n.grupo === g;
  const radio = 260;
  const angulo = (i, total) => i / Math.max(1, total) * Math.PI * 2 - Math.PI / 2;

  function colocar() {
    const porGrupo = {};
    for (const n of datos.nodos) (porGrupo[n.grupo] ||= []).push(n);
    const zonas = {
      cerebros: (i, total) => { const a = angulo(i, total); return [Math.cos(a) * radio, -radio * .62, Math.sin(a) * radio]; },   // en pantalla, y negativa = arriba
      servicios: (i, total) => { const a = angulo(i, total); return [Math.cos(a) * radio, radio * .62, Math.sin(a) * radio]; },
      agentes: (i, total) => { const a = angulo(i, total); return [Math.cos(a) * radio * .55, 0, Math.sin(a) * radio * .55]; },
      herramientas: (i, total) => { const a = angulo(i, total); return [Math.cos(a) * radio, 0, Math.sin(a) * radio]; },
      módulos: (i, total) => [radio * .92, (i - (total - 1) / 2) * 32, (i % 2 ? 45 : -45)],
      canales: (i, total) => [-radio * .92, (i - (total - 1) / 2) * 32, (i % 2 ? 45 : -45)],
      datos: (i, total) => [(i - (total - 1) / 2) * 58, (i % 2) * 30 - 15, -radio * .88],
      túnel: (i, total) => [radio * .48 + i * 42, -radio * .82 + (i - (total - 1) / 2) * 30, 25],
      copias: (i, total) => [-radio * .48 - i * 42, -radio * .82 + (i - (total - 1) / 2) * 30, 25]
    };
    for (const [g, lista] of Object.entries(porGrupo)) lista.forEach((n, i) => {
      const p = g === "núcleo" ? [0, 0, 0] : (zonas[g] || zonas.datos)(i, lista.length);
      n.x = p[0]; n.y = p[1]; n.z = p[2]; n._radio = g === "núcleo" ? 18 : (g === "agentes" || g === "cerebros" ? 9 : 6);
    });
    // La separación es deliberadamente leve para conservar las capas arquitectónicas.
    for (let vuelta = 0; vuelta < 2; vuelta++) for (let i = 0; i < datos.nodos.length; i++) for (let j = i + 1; j < datos.nodos.length; j++) {
      const a = datos.nodos[i], b = datos.nodos[j], dx = a.x - b.x, dz = a.z - b.z, d = Math.hypot(dx, dz);
      if (d && d < 28 && a.grupo === b.grupo) { const empuje = (28 - d) * .18 / d; a.x += dx * empuje; a.z += dz * empuje; b.x -= dx * empuje; b.z -= dz * empuje; }
    }
  }
  function proyectar(n, w, h) {
    const cy = Math.cos(giro.y), sy = Math.sin(giro.y), cx = Math.cos(giro.x), sx = Math.sin(giro.x);
    const x1 = n.x * cy - n.z * sy, z1 = n.x * sy + n.z * cy, y1 = n.y * cx - z1 * sx, z = n.y * sx + z1 * cx;
     const p = 600 / (600 + z) * zoom;
     return { x: w / 2 + x1 * p, y: h / 2 + y1 * p, z, r: Math.max(2.5, (n._radio || 6) * p), p };
  }
  function pulsos(origen, destino) { return actividad.filter((a) => a.agente === origen || a.herramienta === destino || (origen === "aria" && destino.startsWith("herramientas-"))); }
  function dibujar(t) {
    raf = 0; if (!activo || document.hidden) return;
    const c = $("cerebro-canvas"), box = c.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1); if (!box.width) return;
    if (c.width !== box.width * dpr || c.height !== box.height * dpr) { c.width = box.width * dpr; c.height = box.height * dpr; }
    const x = c.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0); const w = box.width, h = box.height, quieto = reducido.matches;
     if (!quieto && !arrastre) giro.y += .0008; x.clearRect(0, 0, w, h);
    const centro = { x: w / 2, y: h / 2 }, grad = x.createRadialGradient(centro.x, centro.y, 5, centro.x, centro.y, Math.max(w, h) * .7); grad.addColorStop(0, "rgba(31,64,105,.18)"); grad.addColorStop(1, "rgba(4,8,16,0)"); x.fillStyle = grad; x.fillRect(0, 0, w, h);
     x.strokeStyle = "rgba(56,214,255,.035)"; x.lineWidth = 1; for (let i = -8; i <= 8; i++) { x.beginPath(); x.moveTo(w / 2 + i * 28, h * .55); x.lineTo(w / 2 + i * 110, h); x.stroke(); x.beginPath(); x.moveTo(0, h * .55 + i * 22); x.lineTo(w, h * .55 + i * 22); x.stroke(); }
     const ps = new Map(datos.nodos.map((n) => { const entrada = desplegando && !quieto ? Math.max(0, Math.min(1, (t - (n._inicio || 0)) / 1500)) : 1; return [n.id, proyectar(entrada < 1 ? { ...n, x: n.x * entrada, y: n.y * entrada, z: n.z * entrada } : n, w, h)]; }));
     const conectado = (id) => datos.enlaces.some((e) => (e.origen === id && (seleccion?.id === e.destino || sobre?.id === e.destino)) || (e.destino === id && (seleccion?.id === e.origen || sobre?.id === e.origen)));
     for (const e of datos.enlaces) { const a = ps.get(e.origen), b = ps.get(e.destino); if (!a || !b) continue; const resaltado = seleccion && (e.origen === seleccion.id || e.destino === seleccion.id) || sobre && (e.origen === sobre.id || e.destino === sobre.id); const enlace = datos.nodos.find((n) => n.id === (e.origen === seleccion?.id || e.origen === sobre?.id ? e.origen : e.destino)); const col = COLORES[enlace?.grupo] || [91, 115, 160]; x.strokeStyle = resaltado ? rgba(col, .72) : "rgba(91,115,160,.12)"; x.lineWidth = resaltado ? 1.25 : .7; x.beginPath(); x.moveTo(a.x, a.y); x.lineTo(b.x, b.y); x.stroke(); }
     const cercanos = [...datos.nodos].sort((a, b) => ps.get(a.id).z - ps.get(b.id).z).slice(0, 12);
     const candidatos = datos.nodos.map((n) => ({ n, prioridad: n.grupo === "núcleo" ? 0 : sobre?.id === n.id ? 1 : seleccion?.id === n.id || conectado(n.id) ? 2 : cercanos.includes(n) ? 3 : 9 })).filter((v) => v.prioridad < 9).sort((a, b) => a.prioridad - b.prioridad);
     const ocupadas = [];
     for (const [i, n] of datos.nodos.map((n, i) => [i, n]).sort((a, b) => ps.get(a[1].id).z - ps.get(b[1].id).z)) { const p = ps.get(n.id), col = COLORES[n.grupo] || COLORES.datos, estado = ESTADOS[n.estado] || ESTADOS.apagado, foco = sobre?.id === n.id || seleccion?.id === n.id; const entrada = desplegando && !quieto ? Math.max(0, Math.min(1, (t - (n._inicio || 0)) / 1500)) : 1; const escala = entrada < 1 ? entrada : 1; const pulso = actividad.some((a) => a.herramienta && n.id.includes(a.herramienta)) && !quieto ? 1 + Math.sin(t / 100 + i) * .1 : 1; const alpha = Math.max(.35, Math.min(1, .92 - p.z / 950)); x.globalCompositeOperation = "lighter"; x.fillStyle = rgba(col, alpha * .1); x.beginPath(); x.arc(p.x, p.y, p.r * 2.2 * pulso * escala, 0, Math.PI * 2); x.fill(); x.fillStyle = rgba(col, alpha * escala); x.beginPath(); x.arc(p.x, p.y, p.r * (foco ? 1.18 : 1) * escala, 0, Math.PI * 2); x.fill(); x.globalCompositeOperation = "source-over"; x.strokeStyle = rgba(estado, .95); x.lineWidth = 1; x.beginPath(); x.arc(p.x, p.y, (p.r + 2) * escala, 0, Math.PI * 2); x.stroke(); if (n.estado === "mal" && !quieto) { x.strokeStyle = rgba(estado, .35 + Math.sin(t / 300) * .2); x.lineWidth = 2; x.stroke(); } }
     dibujarEtiquetas(x, ps, candidatos, ocupadas, w, h);
     if (desplegando && datos.nodos.every((n) => t - (n._inicio || t) >= 1500)) desplegando = false;
     if (!quieto) raf = requestAnimationFrame(dibujar);
   }
   function dibujarEtiquetas(x, ps, candidatos, ocupadas, w, h) { x.font = "11px ui-monospace, monospace"; x.textAlign = "center"; const zonas = {}; for (const n of datos.nodos) { if (!zonas[n.grupo]) zonas[n.grupo] = { x: 0, y: 0, total: 0 }; const p = ps.get(n.id); zonas[n.grupo].x += p.x; zonas[n.grupo].y += p.y; zonas[n.grupo].total++; } for (const [g, z] of Object.entries(zonas)) { const px = z.x / z.total, py = z.y / z.total; x.fillStyle = "rgba(148,163,184,.42)"; x.font = "10px ui-monospace, monospace"; x.fillText((GRUPOS[g] || g).toUpperCase(), px, py); } for (const { n } of candidatos) { const p = ps.get(n.id), ancho = x.measureText(n.nombre).width + 12, caja = { left: p.x - ancho / 2, right: p.x + ancho / 2, top: p.y - p.r - 22, bottom: p.y - p.r - 5 }; if (caja.left < 3 || caja.right > w - 3 || ocupadas.some((o) => caja.left < o.right && caja.right > o.left && caja.top < o.bottom && caja.bottom > o.top)) continue; ocupadas.push(caja); x.fillStyle = "rgba(3,10,20,.78)"; x.fillRect(caja.left, caja.top, ancho, 17); x.fillStyle = "rgba(230,240,255,.92)"; x.fillText(n.nombre, p.x, caja.bottom - 4); } }
  function pintarPanel(n) { const p = $("cerebro-panel"); p.replaceChildren(); if (!n) { p.append(el("p", { class: "muted" }, "Selecciona un nodo para ver sus datos.")); return; } p.append(el("h2", null, n.nombre), el("p", { class: "cerebro-meta" }, `${n.grupo} · ${n.estado}`), el("p", { class: n.estado === "mal" ? "error" : "muted" }, n.detalle || "Sin detalle")); const dl = el("dl", { class: "cerebro-datos" }); for (const [k, v] of Object.entries(n.datos || {})) dl.append(el("dt", null, k), el("dd", null, String(v ?? "—"))); p.append(dl); }
  function nodoEn(e) { const c = $("cerebro-canvas"), r = c.getBoundingClientRect(), w = r.width, h = r.height; let mejor = null, distancia = 24; for (const n of datos.nodos) { const p = proyectar(n, w, h), d = Math.hypot(e.clientX - r.left - p.x, e.clientY - r.top - p.y); if (d < Math.max(distancia, p.r + 7)) { mejor = n; distancia = d; } } return mejor; }
   async function cargar() { const r = await api("/api/cerebro"); if (r.ok) { const primera = !datos.nodos.length; datos = r.data; colocar(); if (primera && !reducido.matches) { const ahora = performance.now(); datos.nodos.forEach((n, i) => { n._inicio = ahora + i * 18; }); desplegando = true; } pintarLeyenda(); ultimo = Date.now(); } if (!raf) raf = requestAnimationFrame(dibujar); }
   function pintarLeyenda() { const l = $("cerebro-leyenda"); l.replaceChildren(...Object.entries(GRUPOS).map(([k, v]) => el("span", { class: "cerebro-leyenda-item grupo-" + k.replace("/", "-"), "data-grupo": k }, v)), el("span", { class: "cerebro-anillo" }, "Anillo: estado")); }
  async function cargarActividad() { if (!activo || document.hidden) return; const r = await api(`/api/cerebro/actividad?desde=${encodeURIComponent(ultimoAct)}`); if (r.ok) { actividad = [...actividad, ...(r.data.actividad || [])].slice(-100); ultimoAct = Date.now() / 1000; $("cerebro-acciones").textContent = `${actividad.filter((a) => a.ts > Date.now() / 1000 - 60).length} acciones en el último minuto`; if (!reducido.matches && !raf) raf = requestAnimationFrame(dibujar); } }
   function iniciar() { const c = $("cerebro-canvas"); c.addEventListener("pointerdown", (e) => { arrastre = { x: e.clientX, y: e.clientY }; c.setPointerCapture(e.pointerId); }); c.addEventListener("pointermove", (e) => { sobre = nodoEn(e); if (arrastre) { giro.x += (e.clientY - arrastre.y) * .008; giro.y += (e.clientX - arrastre.x) * .008; arrastre = { x: e.clientX, y: e.clientY }; } if (!raf) raf = requestAnimationFrame(dibujar); }); c.addEventListener("pointerup", (e) => { if (arrastre) { const n = nodoEn(e); if (n) { seleccion = n; pintarPanel(n); } } arrastre = null; }); c.addEventListener("wheel", (e) => { e.preventDefault(); zoom = Math.max(.55, Math.min(2.2, zoom * (e.deltaY < 0 ? 1.08 : .92))); if (!raf) raf = requestAnimationFrame(dibujar); }, { passive: false }); c.addEventListener("dblclick", () => { giro = { x: -20 * Math.PI / 180, y: .08 }; zoom = .7; }); c.addEventListener("keydown", (e) => { if (e.key === "ArrowLeft") giro.y -= .08; if (e.key === "ArrowRight") giro.y += .08; if (e.key === "ArrowUp") giro.x -= .08; if (e.key === "ArrowDown") giro.x += .08; if (e.key === "+" || e.key === "=") zoom = Math.min(2.2, zoom * 1.1); if (e.key === "-") zoom = Math.max(.55, zoom * .9); if (!raf) raf = requestAnimationFrame(dibujar); }); addEventListener("resize", () => { if (activo && !raf) raf = requestAnimationFrame(dibujar); }); addEventListener("visibilitychange", () => { if (activo && !document.hidden && !raf) raf = requestAnimationFrame(dibujar); }); pintarLeyenda(); }
  function activar(si) { activo = si; clearInterval(reloj); if (!si) { cancelAnimationFrame(raf); raf = 0; return; } cargar(); cargarActividad(); reloj = setInterval(() => { if (!document.hidden) { cargar(); cargarActividad(); } }, 5000); }
  return { iniciar, activar };
})();
