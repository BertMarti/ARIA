"use strict";
const Notas = (() => {
  let categoria = "", hechas = false, datos = [], iniciado = false;
  const nombres = { "": "Todas", mejora: "Mejoras", idea: "Ideas", compra: "Compra", general: "General" };
  async function cargar() {
    const q = new URLSearchParams({ estado: hechas ? "hecha" : "abierta" });
    if (categoria) q.set("categoria", categoria);
    const r = await api("/api/notas?" + q);
    if (!r.ok) { toast(r.data?.error || "No se pudieron cargar las notas.", "mal"); return; }
    datos = r.data.notas || []; pintar();
  }
  function pintar() {
    const tabs = $("notas-pestanas");
    tabs.replaceChildren(...Object.entries(nombres).map(([id, nombre]) => {
      const b = el("button", { type: "button", class: "pestana" + (id === categoria ? " activo" : ""), role: "tab", "aria-selected": String(id === categoria) }, nombre);
      b.addEventListener("click", () => { categoria = id; cargar(); }); return b;
    }));
    const ul = $("notas-lista");
    ul.replaceChildren(...datos.map((n) => fila(n)));
    if (!datos.length) ul.append(el("li", { class: "muted" }, hechas ? "No hay notas hechas." : "No tienes notas abiertas."));
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
  function activar(si) { if (si) cargar(); }
  return { iniciar, activar };
})();
