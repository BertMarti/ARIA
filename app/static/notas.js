"use strict";
const Notas = (() => {
  let categoria = "", hechas = false, datos = [], modo = "notas", iniciado = false, temporizador;
  const nombres = { "": "Todas", mejora: "Mejoras", idea: "Ideas", compra: "Compra", general: "General" };
  async function cargar() {
    const q = new URLSearchParams({ estado: hechas ? "hecha" : "abierta" });
    if (categoria) q.set("categoria", categoria);
    const r = await api("/api/notas?" + q);
    if (!r.ok) { toast(r.data?.error || "No se pudieron cargar las notas.", "mal"); return; }
    datos = r.data.notas || []; pintar();
  }
  function pintar() {
    const vistas = $("notas-vistas");
    vistas.replaceChildren(...[["notas", "Notas"], ["listas", "Listas"]].map(([id, nombre]) => {
      const b = el("button", { type: "button", class: "pestana" + (modo === id ? " activo" : ""), "aria-selected": String(modo === id) }, nombre);
      b.addEventListener("click", () => { modo = id; pintar(); if (modo === "listas") cargarListas(); }); return b;
    }));
    $("notas-form").hidden = modo !== "notas";
    $("notas-controles").hidden = modo !== "notas";
    $("notas-lista").hidden = modo !== "notas";
    $("listas-seccion").hidden = modo !== "listas";
    if (modo !== "notas") return;
    const tabs = $("notas-pestanas");
    tabs.replaceChildren(...Object.entries(nombres).map(([id, nombre]) => {
      const b = el("button", { type: "button", class: "pestana" + (id === categoria ? " activo" : ""), role: "tab", "aria-selected": String(id === categoria) }, nombre);
      b.addEventListener("click", () => { categoria = id; cargar(); }); return b;
    }));
    const ul = $("notas-lista");
    ul.replaceChildren(...datos.map((n) => fila(n)));
    if (!datos.length) ul.append(el("li", { class: "muted" }, hechas ? "No hay notas hechas." : "No tienes notas abiertas."));
  }
  async function cargarListas() {
    const r = await api("/api/listas");
    if (!r.ok) { toast(r.data?.error || "No se pudieron cargar las listas.", "mal"); return; }
    $("listas-cuerpo").replaceChildren(...(r.data.listas || []).map(tarjetaLista));
  }
  function tarjetaLista(l) {
    const pendientes = l.items.filter((i) => !i.hecho), hechosLista = l.items.filter((i) => i.hecho);
    const entrada = el("input", { type: "text", maxlength: 120, placeholder: "Añadir artículos…", "aria-label": "Añadir a " + l.nombre });
    const form = el("form", { class: "lista-anadir" }, entrada, el("button", { type: "submit", class: "fantasma pequeno" }, "Añadir"));
    form.addEventListener("submit", async (e) => { e.preventDefault(); const r = await api(`/api/listas/${l.id}/items`, { method: "POST", json: { texto: entrada.value } }); if (r.ok) cargarListas(); else toast(r.data?.error || "No se pudo añadir.", "mal"); });
    const item = (i) => { const c = el("input", { type: "checkbox", checked: Boolean(i.hecho), class: "lista-check", "aria-label": "Marcar " + i.texto }); c.addEventListener("change", async () => { const r = await api(`/api/lista-items/${i.id}`, { method: "PATCH", json: { hecho: c.checked } }); if (r.ok) cargarListas(); else c.checked = !c.checked; }); return el("li", { class: i.hecho ? "lista-item hecho" : "lista-item" }, c, el("span", null, (i.cantidad ? i.cantidad + " " : "") + i.texto), l.compartida_con === "todos" ? el("small", { class: "muted" }, "Añadido por " + (i.autor_nombre || "otro miembro")) : null); };
    const vaciar = el("button", { type: "button", class: "fantasma pequeno" }, "Vaciar hechos");
    vaciar.addEventListener("click", async () => { const r = await api(`/api/listas/${l.id}/vaciar`, { method: "POST" }); if (r.ok) cargarListas(); });
    return el("article", { class: "tarjeta lista-tarjeta" }, el("header", null, el("span", { class: "lista-icono" }, l.icono), el("h2", null, l.nombre), el("span", { class: "pildora" }, String(l.pendientes))), form, el("ul", { class: "lista-items" }, ...pendientes.map(item), ...(hechosLista.length ? [el("li", { class: "lista-separador muted" }, "Hechos"), ...hechosLista.map(item)] : [])), hechosLista.length ? vaciar : null);
  }
  function fila(n) {
    const texto = el("span", { class: "nota-texto" }, n.texto), input = el("input", { type: "checkbox", checked: n.estado === "hecha", "aria-label": "Marcar nota como hecha" });
    input.addEventListener("change", async () => { const r = await api(`/api/notas/${n.id}`, { method: "PATCH", json: { estado: input.checked ? "hecha" : "abierta" } }); if (r.ok) cargar(); else input.checked = !input.checked; });
    const editar = el("button", { type: "button", class: "fantasma pequeno" }, "Editar");
    editar.addEventListener("click", () => editarFila(n, texto, editar));
    const borrar = el("button", { type: "button", class: "fantasma pequeno" }, "Borrar");
    borrar.addEventListener("click", async () => { if (await confirmar("Borrar nota", `«${n.texto}» se eliminará.`, "Borrar")) { const r = await api(`/api/notas/${n.id}`, { method: "DELETE" }); if (r.ok) cargar(); } });
    return el("li", { class: "nota-item" }, input, el("div", { class: "nota-cuerpo" }, texto, el("span", { class: "nota-meta" }, nombres[n.categoria] + " · desde " + n.origen + " · " + new Date(n.creado * 1000).toLocaleDateString("es-ES"))), el("div", { class: "nota-acciones" }, editar, borrar));
  }
  function editarFila(n, texto, boton) {
    const input = el("input", { value: n.texto, maxlength: 1000, class: "nota-edicion" }); texto.replaceWith(input); boton.textContent = "Guardar";
    boton.onclick = async () => { const r = await api(`/api/notas/${n.id}`, { method: "PATCH", json: { texto: input.value } }); if (r.ok) cargar(); else toast(r.data?.error || "No se pudo editar.", "mal"); };
    input.focus();
  }
  function iniciar() { if (iniciado) return; iniciado = true; $("notas-form").addEventListener("submit", async (e) => { e.preventDefault(); const r = await api("/api/notas", { method: "POST", json: { texto: $("notas-texto").value, categoria: $("notas-categoria").value } }); if (!r.ok) { toast(r.data?.error || "No se pudo guardar.", "mal"); return; } $("notas-form").reset(); cargar(); }); $("notas-hechas").addEventListener("change", (e) => { hechas = e.target.checked; cargar(); }); }
  function activar(si) { if (!si) { clearInterval(temporizador); return; } cargar(); clearInterval(temporizador); temporizador = setInterval(() => { if (!document.hidden && modo === "listas") cargarListas(); }, 20000); }
  return { iniciar, activar };
})();
