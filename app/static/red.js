"use strict";
// Red (solo admin): salud, latencia, test de velocidad, historial (SVG propio) y dispositivos de la LAN.
const Red = (() => {
  let iniciado = false;
  const SVG = "http://www.w3.org/2000/svg";
  const fmtHora = (ts) => new Date(ts * 1000).toLocaleString("es-ES", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  const fmtNumero = (v) => (v === null || v === undefined ? "—" : String(v).replace(".", ","));

  function svg(tag, attrs, ...hijos) {
    const e = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, String(v));
    for (const h of hijos) if (h) e.append(h);
    return e;
  }

  // Gráfica de líneas sencilla: series = [{nombre, clase, puntos:[[ts, valor]]}]
  function grafica(titulo, unidad, series) {
    const W = 360, H = 150, M = { i: 34, d: 8, a: 10, b: 20 };
    const todos = series.flatMap((s) => s.puntos.filter((p) => p[1] !== null && p[1] !== undefined));
    if (!todos.length) return el("p", { class: "muted" }, titulo + ": sin datos todavía.");
    const t0 = Math.min(...todos.map((p) => p[0])), t1 = Math.max(...todos.map((p) => p[0]));
    const vmax = Math.max(...todos.map((p) => p[1])) * 1.15 || 1;
    const x = (t) => M.i + (t1 === t0 ? (W - M.i - M.d) / 2 : (t - t0) * (W - M.i - M.d) / (t1 - t0));
    const y = (v) => H - M.b - v * (H - M.a - M.b) / vmax;
    const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "grafica", role: "img", "aria-label": titulo });
    for (const f of [0, 0.5, 1]) {
      const v = vmax * f;
      g.append(svg("line", { x1: M.i, x2: W - M.d, y1: y(v), y2: y(v), class: "g-rejilla" }),
        svg("text", { x: M.i - 4, y: y(v) + 3, class: "g-eje", "text-anchor": "end" }, document.createTextNode(Math.round(v))));
    }
    g.append(svg("text", { x: M.i, y: H - 4, class: "g-eje" }, document.createTextNode(fmtHora(t0))),
      svg("text", { x: W - M.d, y: H - 4, class: "g-eje", "text-anchor": "end" }, document.createTextNode(fmtHora(t1))));
    for (const s of series) {
      const pts = s.puntos.filter((p) => p[1] !== null && p[1] !== undefined);
      if (!pts.length) continue;
      g.append(svg("polyline", { points: pts.map((p) => x(p[0]).toFixed(1) + "," + y(p[1]).toFixed(1)).join(" "), class: "g-linea " + s.clase }));
      for (const p of pts) g.append(svg("circle", { cx: x(p[0]).toFixed(1), cy: y(p[1]).toFixed(1), r: 2.2, class: "g-punto " + s.clase },
        svg("title", null, document.createTextNode(s.nombre + ": " + fmtNumero(p[1]) + " " + unidad + " · " + fmtHora(p[0])))));
    }
    const leyenda = el("div", { class: "g-leyenda" }, ...series.map((s) => el("span", { class: "g-ley " + s.clase }, s.nombre)));
    return el("figure", { class: "g-fig" }, el("figcaption", { class: "muted" }, titulo + " (" + unidad + ")"), g, leyenda);
  }

  async function salud() {
    const c = $("red-salud").querySelector(".cuerpo");
    const { ok, data } = await api("/api/red/salud");
    if (!ok) { c.textContent = data.error || "No se pudo cargar."; return; }
    const lat = (data.latencia && data.latencia.destinos) || [];
    const v = data.velocidad;
    c.replaceChildren(
      el("ul", { class: "top-lista" }, ...lat.map((d) => el("li", null,
        el("span", null, el("span", { class: "punto " + (d.media_ms === null ? "mal" : d.perdida ? "aviso" : "ok") }), " ", d.nombre + " (" + d.ip + ")"),
        el("span", { class: "muted" }, d.media_ms === null ? "sin respuesta" : fmtNumero(d.media_ms) + " ms" + (d.perdida ? " · " + d.perdida + " % perdidos" : "") + (d.metodo === "tcp" ? " (TCP)" : ""))))),
      el("p", { class: "muted" }, "DNS (SHIELD): " + data.dns + " · VPN: " + data.vpn +
        (data.vpn_clientes ? " (" + data.vpn_clientes.conectados + "/" + data.vpn_clientes.dispositivos + " conectados)" : "")),
      el("p", { class: "muted" }, v ? "Velocidad: " + fmtNumero(v.bajada_mbps) + " Mbps ↓ · " + fmtNumero(v.subida_mbps) + " Mbps ↑ · " + fmtHora(v.ts) : "Aún no hay ningún test de velocidad."));
  }

  async function historial() {
    const c = $("red-historial").querySelector(".cuerpo");
    const { ok, data } = await api("/api/red/historial?dias=7");
    if (!ok) { c.textContent = data.error || "No se pudo cargar."; return; }
    const L = data.latencia;
    c.replaceChildren(
      grafica("Latencia media", "ms", [
        { nombre: "Router", clase: "s1", puntos: L.map((p) => [p.ts, p.router]) },
        { nombre: "Cloudflare", clase: "s2", puntos: L.map((p) => [p.ts, p.Cloudflare]) },
        { nombre: "Google", clase: "s3", puntos: L.map((p) => [p.ts, p.Google]) }]),
      grafica("Velocidad", "Mbps", [
        { nombre: "Bajada", clase: "s1", puntos: data.velocidad.map((p) => [p.ts, p.bajada_mbps]) },
        { nombre: "Subida", clase: "s2", puntos: data.velocidad.map((p) => [p.ts, p.subida_mbps]) }]));
  }

  async function dispositivos() {
    const tb = $("red-tabla").querySelector("tbody");
    const { ok, data } = await api("/api/red/dispositivos");
    if (!ok) { tb.replaceChildren(el("tr", null, el("td", { colSpan: 7 }, data.error || "No se pudo cargar."))); return; }
    const ds = data.dispositivos;
    const u = data.ultimo_escaneo;
    $("red-nota").textContent = ds.length + " dispositivos (" + ds.filter((d) => !d.conocido).length + " sin reconocer). Nombres y última consulta DNS de Pi-hole; MAC, fabricante y puertos del último escaneo" +
      (u ? " (" + fmtHora(u.fin) + ")." : " (aún no hay ninguno: lánzalo en Seguridad).");
    if (!ds.length) { tb.replaceChildren(el("tr", null, el("td", { colSpan: 7, class: "muted" }, "Sin dispositivos."))); return; }
    tb.replaceChildren(...ds.map((d) => {
      const alias = el("input", { value: d.alias || "", placeholder: d.nombre || d.fabricante || "sin nombre", maxLength: 40, class: "alias", "aria-label": "Alias" });
      alias.addEventListener("change", () => marcar(d.clave, d.conocido, alias.value));
      return el("tr", { class: d.conocido ? "" : "nuevo" },
        el("td", null, alias, d.alias && d.nombre ? el("div", { class: "muted pequeno-txt" }, d.nombre) : null),
        el("td", { class: "mono" }, d.ip),
        el("td", null, d.fabricante || "—"),
        el("td", { class: "mono" }, d.mac || "—"),
        el("td", { class: "muted" }, d.ultima_consulta ? fmtHora(d.ultima_consulta) : "—"),
        el("td", { class: "mono" }, d.puertos ? (d.puertos.join(", ") || "ninguno") : "—"),
        el("td", null, d.conocido
          ? el("button", { type: "button", class: "fantasma pequeno", onclick: () => marcar(d.clave, false) }, "Olvidar")
          : el("button", { type: "button", class: "primario pequeno", onclick: () => marcar(d.clave, true) }, "Marcar como conocido")));
    }));
  }

  async function marcar(clave, conocido, alias) {
    const json = { clave, conocido };
    if (alias !== undefined) json.alias = alias;
    const r = await api("/api/red/dispositivos/conocido", { method: "POST", json });
    if (!r.ok) toast(r.data.error || "No se pudo guardar.", "mal"); else dispositivos();
  }

  async function accion(boton, ruta, texto) {
    boton.disabled = true; const t = boton.textContent; boton.textContent = texto;
    const r = await api(ruta, { method: "POST" });
    boton.disabled = false; boton.textContent = t;
    if (!r.ok) toast(r.data.error || "No se pudo completar.", "mal");
    salud(); historial();
    return r;
  }

  function cargar() { $("red-hora").textContent = new Date().toLocaleTimeString("es-ES"); salud(); historial(); dispositivos(); }

  function iniciar() {
    if (iniciado) return; iniciado = true;
    $("red-latencia").addEventListener("click", () => accion($("red-latencia"), "/api/red/latencia", "Midiendo…"));
    $("red-velocidad").addEventListener("click", async () => {
      const r = await accion($("red-velocidad"), "/api/red/velocidad", "Midiendo (unos segundos)…");
      if (r.ok) toast("Velocidad: " + fmtNumero(r.data.bajada_mbps) + " Mbps ↓, " + fmtNumero(r.data.subida_mbps) + " Mbps ↑");
    });
    $("red-conocer-todos").addEventListener("click", async () => {
      if (!(await confirmar("Marcar todos como conocidos", "Todos los dispositivos actuales dejarán de aparecer como «sin reconocer».", "Marcar"))) return;
      await api("/api/red/dispositivos/conocer-todos", { method: "POST" }); dispositivos();
    });
  }

  function activar(si) { if (si && Sesion.esAdmin) cargar(); }
  return { iniciar, activar };
})();
