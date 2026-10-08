"use strict";
// Ajustes → Rutinas: lista, crear, editar, pausar, borrar y «Ejecutar ahora». Todo el texto con textContent.
const Rutinas = (() => {
  const DIAS = ["L", "M", "X", "J", "V", "S", "D"];
  const DIAS_LARGOS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
  const CANAL = { telegram: "Telegram", push: "notificación", ambos: "Telegram y notificación", web: "solo la campana" };
  const ESTADO = { ok: "bien", error: "con error", sin_nube: "saltada (sin nube)", omitida: "saltada (ARIA estaba apagada)" };
  let datos = { rutinas: [], agentes: [] };
  let editando = null; // id de la rutina en edición
  let cargada = false;

  const msg = (t, malo) => { const m = $("rut-msg"); m.className = malo ? "error" : "muted"; m.textContent = t || ""; };
  const fecha = (ts) => new Date(ts * 1000).toLocaleString("es-ES", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const nombreAgente = (id) => (datos.agentes.find((a) => a.id === id) || { nombre: id }).nombre;

  async function cargar() {
    const { ok, data } = await api("/api/rutinas");
    if (!ok) { $("rut-lista").replaceChildren(el("li", { class: "error" }, data.error || "No se pudieron leer las rutinas.")); return null; }
    datos = data; cargada = true;
    $("rut-aviso-nube").hidden = data.nube !== false;
    const sel = $("rut-agente"), previo = sel.value;
    sel.replaceChildren(...data.agentes.map((a) => el("option", { value: a.id }, a.nombre)));
    if (previo && data.agentes.some((a) => a.id === previo)) sel.value = previo;
    pintar();
    return data.rutinas;
  }

  function pintar() {
    const ul = $("rut-lista");
    ul.replaceChildren();
    if (!datos.rutinas.length) ul.append(el("li", { class: "muted" }, "Aún no tienes rutinas."));
    for (const r of datos.rutinas) {
      const info = el("div", { class: "fila-info" },
        el("span", null, el("strong", null, r.nombre), r.activa ? "" : el("span", { class: "pildora apagada rut-pausa" }, "En pausa")),
        el("span", { class: "muted pequeno-txt" }, r.descripcion + " · " + nombreAgente(r.agente) + " · por " + (CANAL[r.canal] || r.canal)),
        el("span", { class: "muted pequeno-txt rut-prompt" }, "«" + r.prompt + "»"),
        el("span", { class: "muted pequeno-txt" },
          (r.activa && r.proxima ? "Próxima: " + fecha(r.proxima) : "") +
          (r.ultima ? (r.activa && r.proxima ? " · " : "") + "Última: " + fecha(r.ultima) + " (" + (ESTADO[r.ultimo_estado] || r.ultimo_estado) + ")" : "")));
      const acc = el("div", { class: "fila-acc" },
        el("button", { type: "button", class: "primario pequeno", disabled: r.en_curso, onclick: () => ejecutar(r.id) }, r.en_curso ? "Ejecutando…" : "Ejecutar ahora"),
        el("button", { type: "button", class: "fantasma pequeno", onclick: () => editar(r) }, "Editar"),
        el("button", { type: "button", class: "fantasma pequeno", ariaPressed: String(!r.activa), onclick: () => pausar(r) }, r.activa ? "Pausar" : "Reanudar"),
        el("button", { type: "button", class: "peligro pequeno", onclick: () => borrar(r) }, "Borrar"));
      ul.append(el("li", { class: "fila" }, info, acc));
    }
    const lleno = datos.limites && datos.rutinas.length >= datos.limites.max;
    $("rut-guardar").disabled = lleno && editando === null;
    if (lleno && editando === null) msg(`Has llegado al máximo de ${datos.limites.max} rutinas.`);
  }

  function tipoCambiado() {
    const cada = $("rut-tipo").value === "cada";
    $("rut-hora-et").hidden = cada; $("rut-hora").required = !cada;
    $("rut-horas-et").hidden = !cada;
    $("rut-dias").hidden = cada; $("rut-dias-nota").hidden = cada;
  }

  function recoger() {
    const tipo = $("rut-tipo").value;
    const horario = tipo === "cada"
      ? { tipo, horas: parseInt($("rut-horas").value, 10) || 0 }
      : { tipo, hora: $("rut-hora").value, dias: [...document.querySelectorAll("#rut-dias input:checked")].map((c) => Number(c.dataset.dia)) };
    return { nombre: $("rut-nombre").value, prompt: $("rut-prompt").value, horario, agente: $("rut-agente").value, canal: $("rut-canal").value };
  }

  function limpiarForm() {
    editando = null;
    $("form-rut").reset();
    $("rut-form-titulo").textContent = "Nueva rutina";
    $("rut-guardar").textContent = "Crear rutina";
    $("rut-cancelar").hidden = true;
    tipoCambiado();
    pintar();
  }

  function editar(r) {
    editando = r.id;
    $("rut-nombre").value = r.nombre; $("rut-prompt").value = r.prompt;
    $("rut-tipo").value = r.horario.tipo;
    if (r.horario.tipo === "cada") $("rut-horas").value = r.horario.horas;
    else $("rut-hora").value = r.horario.hora;
    document.querySelectorAll("#rut-dias input").forEach((c) => { c.checked = r.horario.tipo === "diaria" && r.horario.dias.includes(Number(c.dataset.dia)); });
    $("rut-agente").value = r.agente; $("rut-canal").value = r.canal;
    $("rut-form-titulo").textContent = "Editar «" + r.nombre + "»";
    $("rut-guardar").textContent = "Guardar cambios"; $("rut-guardar").disabled = false;
    $("rut-cancelar").hidden = false;
    tipoCambiado();
    $("rut-nombre").focus();
  }

  async function guardar(e) {
    e.preventDefault();
    const cuerpo = recoger();
    const x = editando === null
      ? await api("/api/rutinas", { method: "POST", json: cuerpo })
      : await api("/api/rutinas/" + editando, { method: "PATCH", json: cuerpo });
    if (!x.ok) { msg(x.data.error || "No se pudo guardar.", true); return; }
    msg((editando === null ? "Rutina creada: " : "Guardada: ") + x.data.rutina.descripcion + ".");
    limpiarForm();
    await cargar();
  }

  async function pausar(r) {
    const x = await api("/api/rutinas/" + r.id, { method: "PATCH", json: { activa: !r.activa } });
    if (!x.ok) { msg(x.data.error || "No se pudo cambiar.", true); return; }
    msg(r.activa ? "Rutina en pausa." : "Rutina reanudada.");
    cargar();
  }

  async function borrar(r) {
    if (!(await confirmar("Borrar rutina", "«" + r.nombre + "» dejará de ejecutarse.", "Borrar"))) return;
    const x = await api("/api/rutinas/" + r.id, { method: "DELETE" });
    if (!x.ok) { msg(x.data.error || "No se pudo borrar.", true); return; }
    if (editando === r.id) limpiarForm();
    msg("Rutina borrada.");
    cargar();
  }

  // También la usa la paleta (Ctrl+K). El resultado llega a la campana y por los canales de la rutina.
  async function ejecutar(id) {
    const x = await api("/api/rutinas/" + id + "/ejecutar", { method: "POST" });
    if (!x.ok) { toast(x.data.error || "No se pudo ejecutar.", "mal"); return; }
    toast(x.data.nube === false ? "Solo está el cerebro local: la rutina se salta y te dejo una nota en la campana." : "Ejecutando la rutina… el resultado llegará a la campana.");
    if (cargada) cargar();
    // La respuesta tarda unos segundos: se refresca la campana y la lista hasta que termine.
    let n = 0;
    const t = setInterval(async () => {
      n++;
      Avisos.refrescar();
      const rs = cargada ? await cargar() : null;
      if (n >= 12 || (rs && !rs.some((r) => r.id === id && r.en_curso))) clearInterval(t);
    }, 8000);
  }

  async function lista() {
    if (!cargada) await cargar();
    return datos.rutinas;
  }

  function iniciar() {
    const dias = $("rut-dias");
    DIAS.forEach((d, i) => {
      const c = el("input", { type: "checkbox", dataset: { dia: String(i) } });
      c.setAttribute("aria-label", DIAS_LARGOS[i]);
      const letra = el("span", null, d);
      letra.setAttribute("aria-hidden", "true");
      dias.append(el("label", { class: "rut-dia", title: DIAS_LARGOS[i] }, c, letra));
    });
    $("rut-tipo").addEventListener("change", tipoCambiado);
    $("form-rut").addEventListener("submit", guardar);
    $("rut-cancelar").addEventListener("click", () => { limpiarForm(); msg(""); });
    tipoCambiado();
  }
  return { iniciar, activar: cargar, ejecutar, lista };
})();
