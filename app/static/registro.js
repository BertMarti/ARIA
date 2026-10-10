"use strict";
const Registro = (() => {
  let iniciado = false;
  const fecha = (ts) => new Date(ts * 1000).toLocaleString("es-ES", { dateStyle: "short", timeStyle: "medium" });

  function pintar(data) {
    const tb = $("registro-tabla").querySelector("tbody");
    if (!data.filas.length) {
      tb.replaceChildren(el("tr", null, el("td", { colSpan: 7, class: "muted" }, "Sin actividad registrada.")));
      etiquetarTabla($("registro-tabla"));
      return;
    }
    tb.replaceChildren(...data.filas.map((f) => {
      const texto = f.resultado || "";
      const resultado = el("span", { class: f.ok ? "ok" : "mal", title: texto }, (f.ok ? "✓ " : "✗ ") + texto.slice(0, 80));
      return el("tr", null, el("td", { class: "mono" }, fecha(f.ts)), el("td", null, f.usuario || "Usuario eliminado"),
        el("td", null, f.origen), el("td", null, f.agente || "ARIA"), el("td", { class: "mono" }, f.herramienta),
        el("td", null, resultado), el("td", { class: "num mono" }, String(f.ms)));
    }));
    etiquetarTabla($("registro-tabla"));
  }

  async function cargar() {
    const params = new URLSearchParams({ limite: "100" });
    if ($("registro-usuario").value) params.set("usuario", $("registro-usuario").value);
    if ($("registro-herramienta").value) params.set("herramienta", $("registro-herramienta").value);
    if ($("registro-errores").checked) params.set("errores", "1");
    const r = await api("/api/registro?" + params);
    if (!r.ok) { toast(r.data.error || "No se pudo cargar el registro.", "mal"); return; }
    pintar(r.data);
    const actual = $("registro-herramienta").value;
    $("registro-herramienta").replaceChildren(el("option", { value: "" }, "Todas"), ...r.data.herramientas.map((h) => el("option", { value: h }, h)));
    $("registro-herramienta").value = actual;
  }

  async function iniciar() {
    if (iniciado) return;
    iniciado = true;
    const r = await api("/api/users");
    if (r.ok) $("registro-usuario").replaceChildren(el("option", { value: "" }, "Todos"), ...r.data.usuarios.map((u) => el("option", { value: u.id }, u.nombre || u.email)));
    $("registro-actualizar").addEventListener("click", cargar);
    $("registro-usuario").addEventListener("change", cargar);
    $("registro-herramienta").addEventListener("change", cargar);
    $("registro-errores").addEventListener("change", cargar);
  }
  function activar() { iniciar().then(cargar); }
  return { iniciar, activar };
})();
