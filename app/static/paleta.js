"use strict";
// Paleta de órdenes (Ctrl+K / ⌘K): ir a una sección, conversación nueva, manos libres y ejecutar una rutina.
// Accesible: <dialog> modal (el resto de la página queda inerte), el foco no sale del cuadro de texto (Tab
// incluido), la lista es un listbox con aria-activedescendant, ↑/↓/Inicio/Fin para moverse, Intro para
// elegir y Esc para cerrar (devuelve el foco a donde estaba).
const Paleta = (() => {
  let opciones = [], datos = [], visibles = [], activa = 0, previo = null, temporizador = null, peticion = null;

  const norm = (t) => String(t || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const ir = (v) => () => { location.hash = v; };
  const ICONOS = { nota: "M5 5h14v14H5z M8 9h8 M8 12h8 M8 15h5", evento: "M5 6h14v13H5z M8 3v6 M16 3v6 M5 10h14", cumpleanos: "M12 4a3 3 0 0 1 3 3v2h2a2 2 0 0 1 2 2v7H5v-7a2 2 0 0 1 2-2h2V7a3 3 0 0 1 3-3z", recordatorio: "M6 5h12v14H6z M9 3v4 M15 3v4 M8 11h8 M8 15h5", conversacion: "M4 5h16v11H9l-5 4z M8 9h8 M8 12h5", recuerdo: "M12 4l2.2 4.5 4.8.7-3.5 3.5.8 4.8-4.3-2.3-4.3 2.3.8-4.8L5 9.2l4.8-.7z" };
  function icono(tipo) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", ICONOS[tipo] || ICONOS.nota); path.setAttribute("fill", "none"); path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "1.7"); path.setAttribute("stroke-linecap", "round"); path.setAttribute("stroke-linejoin", "round");
    svg.append(path); return svg;
  }

  function base() {
    const ops = [
      { t: "Ir a Inicio", g: "Ir a", a: ir("inicio") },
      { t: "Ir al Chat", g: "Ir a", a: ir("chat") },
      { t: "Ir a Finanzas", g: "Ir a", a: ir("finanzas") },
      { t: "Ir al Mapa", g: "Ir a", a: ir("mapa") },
      { t: "Ir a Red", g: "Ir a", a: ir("red"), admin: true },
      { t: "Ir a Seguridad", g: "Ir a", a: ir("seguridad"), admin: true },
      { t: "Ir al Centro de control", g: "Ir a", a: ir("control"), admin: true },
      { t: "Ir a Ajustes", g: "Ir a", a: ir("ajustes") },
      { t: "Abrir modo HUD", g: "Ir a", a: ir("hud") },
      ...(Flotante.disponible() ? [{ t: "ARIA flotante", g: "Voz", a: () => Flotante.abrir() }] : []),
      { t: "Ir a Rutinas (Ajustes)", g: "Ir a", a: () => irA("ajustes-rutinas") },
      { t: "Ir a Recordatorios (Ajustes)", g: "Ir a", a: () => irA("ajustes-recordatorios") },
      { t: "Ir a Avisos (Ajustes)", g: "Ir a", a: () => irA("ajustes-avisos") },
      { t: "Nueva conversación", g: "Chat", a: () => { location.hash = "chat"; $("nuevo").click(); } },
      { t: ManosLibres.activa() ? "Desactivar manos libres (voz)" : "Activar manos libres (voz: di «Aria»)", g: "Voz",
        a: () => (ManosLibres.activa() ? ManosLibres.parar() : ManosLibres.iniciar()) },
    ];
    return ops.filter((o) => !o.admin || Sesion.esAdmin);
  }
  function irA(id) {
    location.hash = "ajustes";
    setTimeout(() => { const e = $(id); if (e) { e.scrollIntoView({ block: "start" }); const f = e.querySelector("h2"); if (f) { f.tabIndex = -1; f.focus(); } } }, 50);
  }

  function pintar() {
    const q = norm($("paleta-texto").value).trim().split(/\s+/).filter(Boolean);
    const ordenes = opciones.filter((o) => q.every((p) => norm(o.t + " " + o.g).includes(p)));
    const encontrados = datos.filter((o) => q.every((p) => norm(o.t + " " + o.detalle).includes(p)));
    visibles = ordenes.concat(encontrados);
    if (activa >= visibles.length) activa = Math.max(0, visibles.length - 1);
    const ul = $("paleta-lista");
    ul.replaceChildren();
    if (encontrados.length) ul.append(el("li", { class: "paleta-grupo", role: "presentation" }, "En tus datos"));
    if (!visibles.length) {
      const li = el("li", { class: "muted paleta-vacia" }, "Ninguna orden coincide.");
      ul.append(li);
    }
    visibles.forEach((o, i) => {
      const esDato = i >= ordenes.length;
      const li = el("li", { id: "paleta-op-" + i, class: "paleta-op" + (i === activa ? " activa" : "") },
        esDato ? icono(o.tipo) : null, el("span", null, o.t),
        el("span", { class: "muted pequeno-txt" }, esDato ? o.detalle : o.g));
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", i === activa ? "true" : "false");
      li.addEventListener("mousedown", (e) => e.preventDefault()); // el foco se queda en el cuadro de texto
      li.addEventListener("click", () => elegir(i));
      ul.append(li);
    });
    const t = $("paleta-texto");
    if (visibles.length) t.setAttribute("aria-activedescendant", "paleta-op-" + activa);
    else t.removeAttribute("aria-activedescendant");
    const sel = $("paleta-op-" + activa);
    if (sel) sel.scrollIntoView({ block: "nearest" });
  }

  function mover(n) {
    if (!visibles.length) return;
    activa = (activa + n + visibles.length) % visibles.length;
    pintar();
  }

  function elegir(i) {
    const o = visibles[i];
    if (!o) return;
    cerrar();
    try { o.a ? o.a() : (location.hash = o.enlace); } catch (_) { toast("No se pudo hacer eso.", "mal"); }
  }

  async function abrir() {
    const d = $("dlg-paleta");
    if (d.open) return;
    previo = document.activeElement;
    opciones = base(); activa = 0;
    $("paleta-texto").value = "";
    d.showModal();
    $("paleta-texto").focus();
    pintar();
    // Las rutinas se añaden en cuanto llegan (sin bloquear la apertura).
    try {
      const rs = await Rutinas.lista();
      if (!d.open) return;
      opciones = opciones.concat(rs.map((r) => ({ t: "Ejecutar rutina «" + r.nombre + "»", g: "Rutinas", a: () => Rutinas.ejecutar(r.id) })));
      pintar();
    } catch (_) { /* sin rutinas */ }
  }

  function cerrar() {
    const d = $("dlg-paleta");
    if (d.open) d.close();
  }

  function iniciar() {
    const d = $("dlg-paleta"), t = $("paleta-texto");
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (d.open) cerrar(); else if (!document.querySelector("dialog[open]")) abrir();
      }
    });
    t.addEventListener("input", () => {
      activa = 0; datos = []; pintar();
      if (temporizador) clearTimeout(temporizador);
      if (peticion) peticion.abort();
      const q = t.value.trim();
      if (q.length < 2) return;
      temporizador = setTimeout(async () => {
        peticion = new AbortController();
        try {
          const r = await api("/api/buscar?q=" + encodeURIComponent(q), { signal: peticion.signal });
          if (r.ok && t.value.trim() === q) { datos = (r.data.resultados || []).map((x) => ({ ...x, t: x.titulo, g: "En tus datos" })); pintar(); }
        } catch (_) { /* se cancela al seguir escribiendo */ }
      }, 250);
    });
    d.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); mover(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); mover(-1); }
      else if (e.key === "Home" && visibles.length) { e.preventDefault(); activa = 0; pintar(); }
      else if (e.key === "End" && visibles.length) { e.preventDefault(); activa = visibles.length - 1; pintar(); }
      else if (e.key === "Enter") { e.preventDefault(); elegir(activa); }
      else if (e.key === "Tab") { e.preventDefault(); t.focus(); } // trampa de foco: solo hay un control
    });
    // Esc lo gestiona el propio <dialog>; al cerrar, el foco vuelve a donde estaba (salvo que la orden lo haya movido).
    d.addEventListener("close", () => {
      const sinFoco = !document.activeElement || document.activeElement === document.body;
      if (sinFoco && previo && document.contains(previo) && previo.focus) previo.focus();
      previo = null;
    });
    d.addEventListener("click", (e) => { if (e.target === d) cerrar(); }); // clic en el fondo
  }
  return { iniciar, abrir, cerrar };
})();
