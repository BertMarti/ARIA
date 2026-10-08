"use strict";
// Lista y pausa de reglas. La creación avanzada se valida siempre en el servidor.
const Automatizaciones = (() => {
  let cargada = false;
  let enlazada = false;
  let tipos = [];
  async function cargar() {
    const r = await api("/api/automatizaciones");
    const ul = $("auto-lista");
    if (!r.ok) { ul.replaceChildren(el("li", { class: "error" }, r.data.error || "No se pudieron leer las automatizaciones.")); return; }
    ul.replaceChildren();
    tipos = r.data.tipos || [];
    $("auto-aviso").replaceChildren(...tipos.map((t) => el("option", { value: t }, t)));
    if (!r.data.automatizaciones.length) ul.append(el("li", { class: "muted" }, "No hay automatizaciones."));
    for (const a of r.data.automatizaciones) {
      const estado = a.activa ? "Activa" : "En pausa";
      const boton = el("button", { type: "button", class: "fantasma pequeno" }, a.activa ? "Pausar" : "Reanudar");
      boton.addEventListener("click", async () => { await api("/api/automatizaciones/" + a.id, { method: "PATCH", json: { activa: !a.activa } }); cargar(); });
      ul.append(el("li", { class: "fila" }, el("div", { class: "fila-info" }, el("strong", null, a.nombre), el("span", { class: "muted" }, estado + " · " + a.disparador.tipo)), el("div", { class: "fila-acc" }, boton)));
    }
    cargada = true;
  }
  function disparador() {
    const t = $("auto-tipo").value;
    if (t === "aviso") return { tipo: t, aviso: $("auto-aviso").value };
    if (t === "hora") return { tipo: t, hora: $("auto-hora").value, dias: [] };
    return { tipo: t, metrica: "temperatura", operador: ">", valor: Number($("auto-valor").value) };
  }
  function activar() {
    if (!cargada) cargar();
    if (enlazada) return;
    enlazada = true;
    $("auto-nueva").addEventListener("click", () => $("auto-dialog").showModal());
    $("auto-cancelar").addEventListener("click", () => $("auto-dialog").close());
    $("auto-tipo").addEventListener("change", () => { const t = $("auto-tipo").value; $("auto-aviso-et").hidden = t !== "aviso"; $("auto-hora-et").hidden = t !== "hora"; $("auto-umbral-et").hidden = t !== "umbral"; });
    $("auto-form").addEventListener("submit", async (e) => { e.preventDefault(); const accion = $("auto-accion").value; const acciones = [{ tipo: accion, ...(accion === "avisar" ? { texto: $("auto-texto").value } : {}), ...(accion === "pausar_bloqueador" ? { minutos: 5 } : {}), ...(accion === "ejecutar_rutina" ? { rutina_id: Number($("auto-rutina").value) } : {}) }]; const condiciones = accion === "pausar_internet_dispositivo" && $("auto-aviso").value === "dispositivo_nuevo" ? { dispositivo_desconocido: true, desde: "00:00", hasta: "07:00" } : {}; const r = await api("/api/automatizaciones", { method: "POST", json: { nombre: $("auto-nombre").value, disparador: disparador(), condiciones, acciones } }); $("auto-msg").textContent = r.ok ? "Automatización creada." : (r.data.error || "No se pudo crear."); if (r.ok) { $("auto-dialog").close(); cargar(); } });
    document.querySelectorAll("[data-auto-plantilla]").forEach((b) => b.addEventListener("click", () => { const p = b.dataset.autoPlantilla; const noche = p === "noche"; $("auto-nombre").value = noche ? "Desconocido de noche" : p === "temperatura" ? "Temperatura alta" : p === "shield" ? "SHIELD-DNS caído" : "Rutina diaria"; $("auto-accion").value = noche ? "pausar_internet_dispositivo" : p === "rutina" ? "ejecutar_rutina" : "avisar"; if (noche || p === "shield") $("auto-aviso").value = noche ? "dispositivo_nuevo" : "servicios"; $("auto-dialog").showModal(); $("auto-tipo").value = noche || p === "shield" ? "aviso" : p === "rutina" ? "hora" : "umbral"; $("auto-rutina-et").hidden = p !== "rutina"; $("auto-tipo").dispatchEvent(new Event("change")); }));
  }
  return { activar };
})();
