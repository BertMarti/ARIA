"use strict";
// Ajustes → Memoria: lo que ARIA recuerda del usuario (solo lo suyo), el diario y el aprendizaje automático.
const Memoria = (() => {
  const fechaCorta = (ts) => new Date(ts * 1000).toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "numeric" });
  function fechaDia(f) {
    const [y, m, d] = f.split("-").map(Number);
    const t = new Date(y, m - 1, d).toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });
    return t.charAt(0).toUpperCase() + t.slice(1);
  }
  function aviso(texto, malo) { const m = $("mem-msg"); m.className = malo ? "error" : "muted"; m.textContent = texto || ""; }

  async function editar(r) {
    const nuevo = el("input", { value: r.texto, maxLength: 300, "aria-label": "Editar recuerdo" });
    const li = $("mem-r-" + r.id);
    const info = li.querySelector(".fila-info"), acc = li.querySelector(".fila-acc");
    const guardar = el("button", { type: "button", class: "primario pequeno" }, "Guardar");
    const cancelar = el("button", { type: "button", class: "fantasma pequeno", onclick: () => cargar() }, "Cancelar");
    guardar.addEventListener("click", async () => {
      const x = await api("/api/memoria/" + r.id, { method: "PATCH", json: { texto: nuevo.value } });
      if (!x.ok) { aviso(x.data.error || "No se pudo guardar.", true); return; }
      aviso(""); cargar();
    });
    info.replaceChildren(nuevo); acc.replaceChildren(guardar, cancelar); nuevo.focus();
  }
  async function borrar(r) {
    const x = await api("/api/memoria/" + r.id, { method: "DELETE" });
    if (!x.ok) { aviso(x.data.error || "No se pudo borrar.", true); return; }
    aviso("Recuerdo borrado."); cargar();
  }
  async function borrarDia(f) {
    const x = await api("/api/diario/" + f, { method: "DELETE" });
    if (!x.ok) { aviso(x.data.error || "No se pudo borrar.", true); return; }
    cargar();
  }

  async function cargar() {
    const { ok, data } = await api("/api/memoria");
    const ul = $("mem-lista"), dia = $("mem-diario");
    if (!ok) { ul.replaceChildren(el("li", { class: "error" }, "No se pudo leer la memoria.")); return; }
    $("mem-aprender").checked = !!data.aprender;
    $("mem-cuenta").textContent = "(" + data.recuerdos.length + " de " + data.max + ")";
    ul.replaceChildren();
    if (!data.recuerdos.length) ul.append(el("li", { class: "muted" }, "Todavía no recuerdo nada de ti."));
    for (const r of data.recuerdos) {
      ul.append(el("li", { class: "fila", id: "mem-r-" + r.id },
        el("div", { class: "fila-info" }, el("span", null, r.texto),
          el("span", { class: "muted" }, (r.origen === "auto" ? "Aprendido solo" : "Me lo pediste") + " · " + fechaCorta(r.creado))),
        el("div", { class: "fila-acc" },
          el("button", { type: "button", class: "fantasma pequeno", onclick: () => editar(r) }, "Editar"),
          el("button", { type: "button", class: "peligro pequeno", onclick: () => borrar(r) }, "Borrar"))));
    }
    dia.replaceChildren();
    if (!data.diario.length) dia.append(el("li", { class: "muted" }, "Todavía no hay resúmenes de días. Se escriben cada madrugada (03:30)."));
    for (const e of data.diario) {
      dia.append(el("li", { class: "fila" },
        el("div", { class: "fila-info" }, el("strong", null, fechaDia(e.fecha)),
          ...e.resumen.split("\n").filter(Boolean).map((l) => el("span", { class: "muted" }, l))),
        el("div", { class: "fila-acc" }, el("button", { type: "button", class: "peligro pequeno", onclick: () => borrarDia(e.fecha) }, "Borrar"))));
    }
  }

  function iniciar() {
    $("form-mem").addEventListener("submit", async (e) => {
      e.preventDefault();
      const x = await api("/api/memoria", { method: "POST", json: { texto: $("mem-nuevo").value } });
      if (!x.ok) { aviso(x.data.error || "No se pudo guardar.", true); return; }
      $("mem-nuevo").value = ""; aviso(x.data.creado ? "Anotado." : "Ya lo tenía anotado."); cargar();
    });
    $("mem-aprender").addEventListener("change", async () => {
      const t = $("mem-aprender"), x = await api("/api/memoria/ajustes", { method: "POST", json: { aprender: t.checked } });
      if (!x.ok) { t.checked = !t.checked; aviso(x.data.error || "No se pudo guardar.", true); }
      else aviso(t.checked ? "ARIA aprenderá de tus conversaciones." : "ARIA ya no aprenderá sola de tus conversaciones.");
    });
    $("mem-borrar-todo").addEventListener("click", async () => {
      if (!(await confirmar("Borrar toda mi memoria", "Se borrarán todos tus recuerdos y el diario. Tus conversaciones no se tocan.", "Borrar todo"))) return;
      const x = await api("/api/memoria", { method: "DELETE" });
      aviso(x.ok ? "Memoria borrada." : (x.data.error || "No se pudo borrar."), !x.ok); cargar();
    });
  }
  return { iniciar, activar: cargar };
})();
