"use strict";
const Documentos = (() => {
  let iniciado = false;
  const formato = (n) => n < 1024 * 1024 ? `${Math.ceil(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`;
  async function cargar() {
    const r = await api("/api/documentos");
    if (!r.ok) { toast(r.data?.error || "No se pudieron cargar tus documentos.", "mal"); return; }
    const docs = r.data.documentos || [], total = docs.reduce((s, d) => s + d.tamano, 0);
    $("documentos-cuota").textContent = `Uso: ${formato(total)} de 300 MB · ${docs.length} de 200 documentos`;
    $("documentos-lista").replaceChildren(...docs.map(fila));
    if (!docs.length) $("documentos-lista").append(el("li", { class: "muted" }, "Aún no tienes documentos."));
  }
  function fila(d) {
    const estado = d.estado === "procesando" ? "Procesando…" : d.estado === "listo" ? "Listo" : `Error: ${d.error || "no se pudo leer"}`;
    const acciones = [];
    if (d.estado === "listo") acciones.push(el("a", { href: `/api/documentos/${d.id}/archivo`, class: "fantasma pequeno", download: "" }, "Descargar"));
    const borrar = el("button", { type: "button", class: "fantasma pequeno" }, "Borrar");
    borrar.addEventListener("click", async () => { if (await confirmar("Borrar documento", `«${d.nombre}» se eliminará.`, "Borrar")) { await api(`/api/documentos/${d.id}`, { method: "DELETE" }); cargar(); } });
    acciones.push(borrar);
    return el("li", { class: "nota-item documento-item" }, el("div", { class: "nota-cuerpo" }, el("strong", null, d.nombre), el("span", { class: "nota-meta" }, `${d.paginas || 0} páginas · ${formato(d.tamano)} · ${estado}`)), el("div", { class: "nota-acciones" }, ...acciones));
  }
  async function subir(archivos) {
    for (const archivo of archivos) {
      const form = new FormData(); form.append("archivo", archivo);
      const r = await api("/api/documentos", { method: "POST", body: form });
      if (!r.ok) toast(r.data?.error || `No se pudo subir ${archivo.name}.`, "mal");
    }
    cargar();
  }
  function iniciar() {
    if (iniciado) return; iniciado = true;
    $("documentos-input").addEventListener("change", (e) => subir(e.target.files));
    const zona = $("documentos-soltar");
    zona.addEventListener("dragover", (e) => { e.preventDefault(); zona.classList.add("arrastrando"); });
    zona.addEventListener("dragleave", () => zona.classList.remove("arrastrando"));
    zona.addEventListener("drop", (e) => { e.preventDefault(); zona.classList.remove("arrastrando"); subir(e.dataTransfer.files); });
    $("documentos-pregunta").addEventListener("submit", (e) => { e.preventDefault(); const q = encodeURIComponent($("documentos-texto").value.trim()); if (q) { location.hash = `#chat?q=${q}`; } });
  }
  function activar(si) { if (si) cargar(); }
  return { iniciar, activar };
})();
