"use strict";
// Finanzas: resumen mensual, categorías, presupuestos, movimientos e importación CSV (solo datos propios).
const Finanzas = (() => {
  let iniciado = false, categorias = [], movs = [], csvB64 = null, csvPrevia = null, busqueda = null;

  const euros = (c) => (Number(c) / 100).toLocaleString("es-ES", { style: "currency", currency: "EUR" });
  const mesActual = () => new Date().toISOString().slice(0, 7);
  const mes = () => $("fin-mes").value || mesActual();
  const fmtFecha = (iso) => { const [y, m, d] = iso.split("-"); return d + "/" + m + "/" + y; };

  function numero(valor, texto, clase) {
    return el("div", { class: "numero" }, el("strong", { class: clase || "" }, valor), el("span", { class: "muted" }, texto));
  }

  function opcionesCategorias(sel, primera) {
    const actual = sel.value;
    sel.replaceChildren(...(primera || []).map(([v, t]) => el("option", { value: v }, t)),
      ...categorias.map((c) => el("option", { value: c }, c)));
    sel.value = actual;
    if (sel.selectedIndex < 0 && sel.options.length) sel.selectedIndex = 0;
  }

  async function cargarResumen() {
    const { ok, data } = await api("/api/finanzas/resumen?mes=" + encodeURIComponent(mes()));
    if (!ok) { $("fin-resumen").querySelector(".cuerpo").textContent = data.error || "No se pudo cargar."; return; }
    categorias = data.categorias_disponibles || [];
    opcionesCategorias($("pres-cat"));
    opcionesCategorias($("mov-cat"), [["", "Automática"]]);
    opcionesCategorias($("ed-cat"), [["", "Sin categoría"]]);
    opcionesCategorias($("fin-filtro-cat"), [["", "Todas las categorías"], ["__sin__", "Sin categoría"]]);

    $("fin-resumen").querySelector(".cuerpo").replaceChildren(
      el("div", { class: "numeros" },
        numero(euros(data.ingresos), "ingresos", "ok-txt"), numero(euros(data.gastos), "gastos", "error"),
        numero(euros(data.balance), "balance", data.balance >= 0 ? "ok-txt" : "error")),
      el("p", { class: "muted" }, data.movimientos + " movimiento(s) en " + data.mes + "."));

    const cc = $("fin-categorias").querySelector(".cuerpo");
    if (!data.categorias.length) cc.replaceChildren(el("p", { class: "muted" }, "Sin gastos este mes."));
    else {
      const max = Math.max(...data.categorias.map((c) => c.total));
      cc.replaceChildren(...data.categorias.map((c) => el("div", { class: "metrica" },
        el("div", { class: "metrica-cab" }, el("span", null, c.categoria), el("span", { class: "muted" }, euros(c.total))),
        barra(c.total * 100 / max, 101, 101))));
    }

    const pc = $("fin-presupuestos").querySelector(".cuerpo");
    if (!data.presupuestos.length) pc.replaceChildren(el("p", { class: "muted" }, "Aún no hay presupuestos. Pon uno abajo."));
    else pc.replaceChildren(...data.presupuestos.map((p) => el("div", { class: "metrica" },
      el("div", { class: "metrica-cab" }, el("span", null, p.categoria),
        el("span", { class: p.superado ? "error" : "muted" }, euros(p.gastado) + " de " + euros(p.presupuesto))),
      barra(p.porcentaje, 80, 100))));
  }

  async function cargarMovimientos() {
    const q = new URLSearchParams({ mes: mes(), categoria: $("fin-filtro-cat").value, texto: $("fin-buscar").value.trim() });
    const { ok, data } = await api("/api/finanzas/movimientos?" + q);
    const tb = $("fin-tabla").querySelector("tbody");
    if (!ok) { tb.replaceChildren(el("tr", null, el("td", { colSpan: 5 }, data.error || "Error"))); return; }
    movs = data.movimientos;
    if (!movs.length) { tb.replaceChildren(el("tr", null, el("td", { colSpan: 5, class: "muted" }, "No hay movimientos con ese filtro."))); return; }
    tb.replaceChildren(...movs.map((m) => el("tr", null,
      el("td", null, fmtFecha(m.fecha)),
      el("td", { class: "concepto", title: m.concepto + (m.cuenta ? " · " + m.cuenta : "") }, m.concepto),
      el("td", null, m.categoria ? el("span", { class: "pildora" }, m.categoria) : el("span", { class: "muted" }, "—")),
      el("td", { class: "num " + (m.importe < 0 ? "error" : "ok-txt") }, euros(m.importe)),
      el("td", { class: "acciones-fila" },
        el("button", { type: "button", class: "icono-mini visible", title: "Editar", "aria-label": "Editar", onclick: () => editar(m) }, "✎"),
        el("button", { type: "button", class: "icono-mini visible", title: "Borrar", "aria-label": "Borrar", onclick: () => borrar(m) }, "✕")))));
  }

  function refrescar() { cargarResumen().then(cargarMovimientos); }

  function editar(m) {
    $("ed-fecha").value = m.fecha; $("ed-concepto").value = m.concepto;
    $("ed-importe").value = (m.importe / 100).toFixed(2).replace(".", ",");
    $("ed-cat").value = m.categoria || ""; $("ed-similares").checked = false;
    const d = $("dlg-mov");
    d.dataset.id = m.id;
    d.showModal();
  }

  async function guardarEdicion(e) {
    e.preventDefault();
    const d = $("dlg-mov");
    const r = await api("/api/finanzas/movimientos/" + d.dataset.id, { method: "PATCH", json: {
      fecha: $("ed-fecha").value, concepto: $("ed-concepto").value, importe: $("ed-importe").value,
      categoria: $("ed-cat").value || null, aplicar_a_similares: $("ed-similares").checked } });
    if (!r.ok) { toast(r.data.error || "No se pudo guardar.", "mal"); return; }
    d.close(); refrescar();
  }

  async function borrar(m) {
    if (!(await confirmar("Borrar movimiento", m.concepto + " (" + euros(m.importe) + ")", "Borrar"))) return;
    const r = await api("/api/finanzas/movimientos/" + m.id, { method: "DELETE" });
    if (!r.ok) toast(r.data.error || "No se pudo borrar.", "mal"); else refrescar();
  }

  async function apuntar(e) {
    e.preventDefault();
    const r = await api("/api/finanzas/movimientos", { method: "POST", json: {
      fecha: $("mov-fecha").value, concepto: $("mov-concepto").value, importe: $("mov-importe").value,
      categoria: $("mov-cat").value || null } });
    if (!r.ok) { toast(r.data.error || "No se pudo apuntar.", "mal"); return; }
    toast("Apuntado: " + r.data.movimiento.concepto + " " + euros(r.data.movimiento.importe));
    $("mov-concepto").value = ""; $("mov-importe").value = "";
    refrescar();
  }

  async function presupuesto(e) {
    e.preventDefault();
    const r = await api("/api/finanzas/presupuestos", { method: "POST", json: { categoria: $("pres-cat").value, importe: $("pres-importe").value } });
    if (!r.ok) { toast(r.data.error || "No se pudo guardar.", "mal"); return; }
    $("pres-importe").value = ""; cargarResumen();
  }

  // --- Sugerencias de categoría (nube, opcional) ---
  async function sugerir() {
    const b = $("fin-sugerir"); b.disabled = true; b.textContent = "Pensando…";
    const r = await api("/api/finanzas/sugerir", { method: "POST" });
    b.disabled = false; b.textContent = "Sugerir categorías (nube)";
    const zona = $("fin-sugerencias");
    if (!r.ok) { toast(r.data.error || "No se pudo sugerir.", "mal"); return; }
    if (!r.data.sugerencias.length) { toast("No hay movimientos sin categoría que sugerir."); zona.hidden = true; return; }
    zona.hidden = false;
    zona.replaceChildren(el("h3", null, "Sugerencias (revisa antes de aceptar)"),
      el("ul", { class: "filas" }, ...r.data.sugerencias.map((s) => {
        const li = el("li", { class: "fila" },
          el("div", { class: "fila-info" }, el("strong", null, s.concepto), el("span", { class: "muted" }, "→ " + s.categoria + " (regla: «" + s.patron + "»)")),
          el("div", { class: "fila-acc" }, el("button", { type: "button", class: "primario pequeno", onclick: async () => {
            const x = await api("/api/finanzas/reglas", { method: "POST", json: { patron: s.patron, categoria: s.categoria } });
            if (!x.ok) { toast(x.data.error || "No se pudo crear la regla.", "mal"); return; }
            li.remove(); refrescar();
          } }, "Aceptar")));
        return li;
      })));
  }

  // --- Importación CSV ---
  const CAMPOS = [["fecha", "Fecha"], ["concepto", "Concepto"], ["importe", "Importe"], ["debe", "Debe / cargo"], ["haber", "Haber / abono"], ["cuenta", "Cuenta"]];

  function leerArchivo(f) {
    return new Promise((ok, mal) => {
      const r = new FileReader();
      r.onload = () => { const b = new Uint8Array(r.result); let s = ""; for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000)); ok(btoa(s)); };
      r.onerror = mal; r.readAsArrayBuffer(f);
    });
  }

  function mapeoActual() {
    const m = {};
    for (const [k] of CAMPOS) { const v = $("map-" + k).value; m[k] = v === "" ? null : Number(v); }
    return m;
  }

  async function previa(mapeo) {
    const r = await api("/api/finanzas/importar/previa", { method: "POST", json: { archivo: csvB64, mapeo } });
    if (!r.ok) { toast(r.data.error || "No se pudo leer el archivo.", "mal"); $("csv-previa").hidden = true; return; }
    csvPrevia = r.data;
    const d = r.data;
    $("csv-previa").hidden = false;
    $("csv-info").textContent = d.total + " filas · separador «" + (d.separador === "\t" ? "tab" : d.separador) + "» · " + d.codificacion +
      " · decimal «" + d.decimal + "» · " + d.validas + " válidas" + (d.errores ? ", " + d.errores + " ignoradas" : "") + (d.aviso ? " · " + d.aviso : "");
    if (!mapeo) {
      $("csv-mapeo").replaceChildren(...CAMPOS.map(([k, t]) => {
        const s = el("select", { id: "map-" + k }, el("option", { value: "" }, "—"), ...d.cabecera.map((c, i) => el("option", { value: String(i) }, c || "(col. " + (i + 1) + ")")));
        s.value = d.mapeo[k] === null || d.mapeo[k] === undefined ? "" : String(d.mapeo[k]);
        s.addEventListener("change", () => previa(mapeoActual()));
        return el("label", null, t, s);
      }));
    }
    $("csv-muestra").querySelector("tbody").replaceChildren(...d.muestra.map((m) => el("tr", null,
      el("td", null, fmtFecha(m.fecha)), el("td", { class: "concepto" }, m.concepto),
      el("td", { class: "num " + (m.importe < 0 ? "error" : "ok-txt") }, euros(m.importe)))));
    $("csv-importar").disabled = !d.validas;
  }

  async function elegirArchivo() {
    const f = $("csv-archivo").files[0];
    if (!f) return;
    if (f.size > 2 * 1024 * 1024) { toast("El archivo es demasiado grande (máximo 2 MB).", "mal"); return; }
    csvB64 = await leerArchivo(f);
    previa(null);
  }

  async function importar() {
    const b = $("csv-importar"); b.disabled = true;
    const r = await api("/api/finanzas/importar", { method: "POST", json: { archivo: csvB64, mapeo: mapeoActual(), cuenta: $("csv-cuenta").value } });
    b.disabled = false;
    if (!r.ok) { toast(r.data.error || "No se pudo importar.", "mal"); return; }
    toast("Importados " + r.data.insertados + " movimientos; " + r.data.duplicados + " ya estaban" + (r.data.errores ? "; " + r.data.errores + " filas ignoradas" : "") + ".");
    cancelarCsv(); refrescar();
  }

  function cancelarCsv() { csvB64 = null; csvPrevia = null; $("csv-archivo").value = ""; $("csv-previa").hidden = true; }

  function iniciar() {
    if (iniciado) return; iniciado = true;
    $("fin-mes").value = mesActual();
    $("mov-fecha").value = new Date().toISOString().slice(0, 10);
    $("fin-mes").addEventListener("change", refrescar);
    $("fin-filtro-cat").addEventListener("change", cargarMovimientos);
    $("fin-buscar").addEventListener("input", () => { clearTimeout(busqueda); busqueda = setTimeout(cargarMovimientos, 300); });
    $("form-mov").addEventListener("submit", apuntar);
    $("form-presupuesto").addEventListener("submit", presupuesto);
    $("form-editar-mov").addEventListener("submit", guardarEdicion);
    $("dlg-mov").addEventListener("click", (e) => { if (e.target.closest("[data-cerrar]")) $("dlg-mov").close(); });
    $("fin-sugerir").addEventListener("click", sugerir);
    $("csv-archivo").addEventListener("change", elegirArchivo);
    $("csv-importar").addEventListener("click", importar);
    $("csv-cancelar").addEventListener("click", cancelarCsv);
  }

  function activar(si) { if (si) refrescar(); }
  return { iniciar, activar };
})();
