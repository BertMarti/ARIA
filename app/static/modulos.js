"use strict";
// Módulos: mosaicos en Inicio (con su salud) y la tarjeta Ajustes → Módulos (solo admin).
// Todo el texto de los manifiestos va con textContent / nodos del DOM (nunca innerHTML).
const Modulos = (() => {
  const NS = "http://www.w3.org/2000/svg";
  // Iconos que puede elegir un manifiesto (mismo conjunto que modulos.ICONOS en el servidor).
  const ICONOS = {
    app: [["rect", { x: 4, y: 4, width: 7, height: 7, rx: 1.5 }], ["rect", { x: 13, y: 4, width: 7, height: 7, rx: 1.5 }], ["rect", { x: 4, y: 13, width: 7, height: 7, rx: 1.5 }], ["rect", { x: 13, y: 13, width: 7, height: 7, rx: 1.5 }]],
    web: [["circle", { cx: 12, cy: 12, r: 9 }], ["path", { d: "M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18" }]],
    escudo: [["path", { d: "M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z" }]],
    candado: [["rect", { x: 5, y: 11, width: 14, height: 10, rx: 2 }], ["path", { d: "M8 11V8a4 4 0 0 1 8 0v3" }]],
    servidor: [["rect", { x: 4, y: 4, width: 16, height: 7, rx: 1.5 }], ["rect", { x: 4, y: 13, width: 16, height: 7, rx: 1.5 }], ["path", { d: "M8 7.5h.01M8 16.5h.01" }]],
    grafica: [["path", { d: "M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6" }]],
    casa: [["path", { d: "M3 11 12 3l9 8v10h-6v-6H9v6H3z" }]],
    musica: [["path", { d: "M9 18V5l11-2v13" }], ["circle", { cx: 6, cy: 18, r: 3 }], ["circle", { cx: 17, cy: 16, r: 3 }]],
    nube: [["path", { d: "M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 9a4.5 4.5 0 0 0 1 9z" }]],
    reloj: [["circle", { cx: 12, cy: 12, r: 9 }], ["path", { d: "M12 7v5l3 2" }]],
    herramienta: [["path", { d: "M14.5 5.5a4 4 0 0 0 4.9 4.9L20 11l-9 9-3-3 9-9 .6-.6a4 4 0 0 0-4.9-4.9z" }]],
    red: [["circle", { cx: 12, cy: 5, r: 2 }], ["circle", { cx: 5, cy: 19, r: 2 }], ["circle", { cx: 19, cy: 19, r: 2 }], ["path", { d: "M12 7v5M12 12l-6 5.5M12 12l6 5.5" }]],
    camara: [["path", { d: "M4 8h3l2-2h6l2 2h3v11H4z" }], ["circle", { cx: 12, cy: 13, r: 3.5 }]],
    documento: [["path", { d: "M6 3h8l4 4v14H6z" }], ["path", { d: "M14 3v4h4M9 12h6M9 16h6" }]],
  };
  const ESTADOS = { activo: "Activo", sin_configurar: "Sin configurar", error: "Error", desactivado: "Desactivado" };

  function icono(nombre) {
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "svg-ico"); svg.setAttribute("viewBox", "0 0 24 24");
    for (const [tag, attrs] of ICONOS[nombre] || ICONOS.app) {
      const n = document.createElementNS(NS, tag);
      for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
      svg.append(n);
    }
    return svg;
  }

  function decorativo(n) { n.setAttribute("aria-hidden", "true"); return n; }

  // «{host}» = el nombre con el que se ha entrado en ARIA. Solo http(s) (el servidor ya lo valida).
  function urlDe(m) {
    if (!m.url) return null;
    try {
      const u = new URL(m.url.split("{host}").join(location.hostname));
      return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
    } catch (_) { return null; }
  }

  async function cargar() {
    const r = await api("/api/modulos");
    return r.ok && Array.isArray(r.data.modulos) ? r.data.modulos : null;
  }

  function estadoTile(m) {
    if (m.estado === "error") return ["mal", "Error al cargar el módulo", "Error"];
    if (m.estado === "sin_configurar") return ["aviso", "Sin configurar", "Sin configurar"];
    if (m.salud === "ok") return ["ok", m.descripcion || "Funcionando", "Funcionando"];
    if (m.salud === "mal") return ["mal", "Sin respuesta", "Caído"];
    return ["", m.descripcion || "Abrir", ""];
  }

  // --- Inicio: un mosaico por módulo con «url» (las aplicaciones integradas ya tienen el suyo) ---
  async function pintarInicio() {
    const cont = $("lanzador");
    const lista = await cargar();
    cont.querySelectorAll(".tile-modulo").forEach((n) => n.remove());
    if (!lista) return;
    for (const m of lista) {
      const href = urlDe(m);
      if (m.integrado || !href || m.estado === "desactivado") continue;
      const [punto, info, titulo] = estadoTile(m);
      cont.append(el("article", { class: "app-tile tile-modulo", dataset: { modulo: m.id } },
        el("a", { class: "tile-enlace", href, target: "_blank", rel: "noopener noreferrer" },
          decorativo(el("span", { class: "tile-ico" }, icono(m.icono))),
          el("strong", null, m.nombre), el("span", { class: "muted tile-info" }, info)),
        el("span", { class: "punto tile-punto " + punto, title: titulo })));
    }
  }

  // --- Ajustes → Módulos (admin) ---
  function lineaEnv(titulo, lista) {
    if (!lista || !lista.length) return null;
    return el("span", { class: "muted" }, titulo + ": ",
      ...lista.flatMap((v, i) => [i ? ", " : "", el("code", null, v.nombre), v.definida ? "" : " (sin definir)"]));
  }
  function fila(m) {
    const pil = m.estado === "activo" ? "pildora ok" : m.estado === "error" ? "pildora mod-error" : "pildora apagada";
    const info = el("div", { class: "fila-info" },
      el("strong", null, m.nombre + (m.version ? " · " + m.version : "")),
      m.integrado ? el("span", { class: "muted" }, "Aplicación integrada (su código está en el núcleo de ARIA)") : null,
      m.descripcion ? el("span", { class: "muted" }, m.descripcion) : null,
      m.herramientas && m.herramientas.length ? el("span", { class: "muted" }, "Herramientas: " + m.herramientas.map((h) => h.nombre).join(", ")) : null,
      m.chequeos && m.chequeos.length ? el("span", { class: "muted" }, "Avisos: " + m.chequeos.join(", ")) : null,
      m.rutas && m.rutas.length ? el("span", { class: "muted" }, "Endpoints: " + m.rutas.join(" · ")) : null,
      lineaEnv("Necesita", m.env), lineaEnv("Opcional", m.env_opcional),
      m.error ? el("span", { class: "error" }, m.error) : null);
    const lado = el("div", { class: "fila-acc" },
      m.salud ? el("span", { class: "punto " + (m.salud === "ok" ? "ok" : m.salud === "aviso" ? "aviso" : "mal"), title: m.salud === "ok" ? "Responde" : "No responde" }) : null,
      el("span", { class: pil }, ESTADOS[m.estado] || m.estado));
    return el("li", { class: "fila" }, decorativo(el("span", { class: "tile-ico mod-ico" }, icono(m.icono))), info, lado);
  }
  async function pintarAjustes() {
    const ul = $("modulos-lista");
    if (!ul) return;
    const lista = await cargar();
    if (!lista) { ul.replaceChildren(el("li", { class: "error" }, "No se pudo leer la lista de módulos.")); return; }
    ul.replaceChildren(...lista.map(fila));
    if (!lista.some((m) => !m.integrado)) ul.append(el("li", { class: "muted" }, "No hay módulos instalados. Copia modulos/_plantilla para crear el tuyo."));
  }

  return { pintarInicio, pintarAjustes, icono, urlDe };
})();
