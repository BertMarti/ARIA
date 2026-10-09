"use strict";
// Agenda: calendario mensual, semana y lista, con cumpleaños. Todo el texto entra con nodos del DOM.
const Agenda = (() => {
  const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
  const DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"];
  const REPITE = { semanal: "cada semana", mensual: "cada mes", anual: "cada año" };
  let modo = "mes", ancla = hoy0(), elegido = hoy0(), eventos = [], cumples = [], editando = null, editandoCumple = null, cargando = 0;

  function hoy0() { const d = new Date(); d.setHours(0, 0, 0, 0); return d; }
  const pad = (n) => String(n).padStart(2, "0");
  const isoDia = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const isoMin = (d) => `${isoDia(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const sumar = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const lunes = (d) => sumar(d, -((d.getDay() + 6) % 7));
  const mismoDia = (a, b) => isoDia(a) === isoDia(b);
  const mayus = (t) => t.charAt(0).toUpperCase() + t.slice(1);
  const hora = (iso) => String(iso || "").slice(11, 16);
  const diaDe = (iso) => String(iso || "").slice(0, 10);
  const largo = (d) => mayus(d.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" }));

  function rango() {
    if (modo === "mes") { const ini = lunes(new Date(ancla.getFullYear(), ancla.getMonth(), 1)); return [ini, sumar(ini, 42)]; }
    if (modo === "semana") { const ini = lunes(ancla); return [ini, sumar(ini, 7)]; }
    return [hoy0(), sumar(hoy0(), 60)];
  }
  function titulo() {
    if (modo === "mes") return mayus(MESES[ancla.getMonth()]) + " " + ancla.getFullYear();
    if (modo === "semana") {
      const [a, b] = rango(), f = sumar(b, -1);
      return `${a.getDate()}${a.getMonth() !== f.getMonth() ? " de " + MESES[a.getMonth()] : ""} – ${f.getDate()} de ${MESES[f.getMonth()]} ${f.getFullYear()}`;
    }
    return "Próximos 60 días";
  }

  async function cargar() {
    const n = ++cargando, [a, b] = rango();
    const [x, y] = await Promise.all([api(`/api/agenda?desde=${isoDia(a)}&hasta=${isoDia(b)}`), api("/api/cumpleanos?dias=366")]);
    if (n !== cargando) return;   // llegó tarde: ya se pidió otro rango
    if (!x.ok) { toast(x.data?.error || "No se pudo cargar la agenda.", "mal"); return; }
    eventos = (x.data.eventos || []).sort((p, q) => String(p.inicio).localeCompare(String(q.inicio)));
    cumples = y.ok ? y.data.cumpleanos || [] : [];
    pintar();
  }

  function delDia(d) {
    const k = isoDia(d);
    return eventos.filter((e) => diaDe(e.inicio) === k).sort((a, b) => (b.todo_el_dia - a.todo_el_dia) || String(a.inicio).localeCompare(String(b.inicio)));
  }
  const cumplesDelDia = (d) => cumples.filter((c) => c.dia === d.getDate() && c.mes === d.getMonth() + 1);

  function chip(e) {
    const b = el("button", { type: "button", class: "ag-chip" + (e.todo_el_dia ? " todo" : ""), title: (e.todo_el_dia ? "" : hora(e.inicio) + " · ") + e.titulo + (e.lugar ? " · " + e.lugar : "") },
      e.todo_el_dia ? null : el("span", { class: "ag-chip-hora" }, hora(e.inicio)), el("span", { class: "ag-chip-txt" }, e.titulo));
    b.addEventListener("click", (ev) => { ev.stopPropagation(); abrir(e); });
    return b;
  }
  function chipCumple(c) {
    const b = el("button", { type: "button", class: "ag-chip cumple", title: "Cumpleaños de " + c.nombre }, el("span", { class: "ag-chip-txt" }, c.nombre));
    b.addEventListener("click", (ev) => { ev.stopPropagation(); abrirCumple(c); });
    return b;
  }
  function pulsable(nodo, fn) {
    nodo.tabIndex = 0;
    nodo.addEventListener("click", fn);
    nodo.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); fn(); } });
    return nodo;
  }

  function pintarMes() {
    const [ini] = rango(), cal = el("div", { class: "ag-mes" });
    cal.append(...DIAS.map((d) => el("div", { class: "ag-dsem" }, d)));
    for (let i = 0; i < 42; i++) {
      const d = sumar(ini, i), evs = delDia(d), cus = cumplesDelDia(d);
      const celda = el("div", { class: "ag-celda", ariaLabel: largo(d) + (evs.length ? `, ${evs.length} eventos` : "") + (cus.length ? `, ${cus.length} cumpleaños` : "") });
      if (d.getMonth() !== ancla.getMonth()) celda.classList.add("fuera");
      if (mismoDia(d, hoy0())) celda.classList.add("hoy");
      if (mismoDia(d, elegido)) celda.classList.add("elegido");
      if (d.getDay() === 0 || d.getDay() === 6) celda.classList.add("finde");
      const items = [...cus.map(chipCumple), ...evs.map(chip)];
      celda.append(el("span", { class: "ag-num" }, String(d.getDate())),
        el("div", { class: "ag-chips" }, ...items.slice(0, 3), items.length > 3 ? el("span", { class: "ag-mas" }, `+${items.length - 3} más`) : null),
        el("div", { class: "ag-puntos", ariaHidden: "true" }, ...items.slice(0, 4).map((_, j) => el("i", { class: j < cus.length ? "cumple" : "" }))));
      pulsable(celda, () => elegir(d));
      celda.addEventListener("dblclick", () => nuevo(d));
      cal.append(celda);
    }
    return cal;
  }

  function pintarSemana() {
    const [ini] = rango(), cont = el("div", { class: "ag-semana" });
    for (let i = 0; i < 7; i++) {
      const d = sumar(ini, i), evs = delDia(d), cus = cumplesDelDia(d);
      const col = el("section", { class: "ag-col" + (mismoDia(d, hoy0()) ? " hoy" : "") + (mismoDia(d, elegido) ? " elegido" : ""), ariaLabel: largo(d) },
        el("header", null, el("span", { class: "ag-col-dia" }, DIAS[i]), el("strong", null, String(d.getDate()))),
        el("div", { class: "ag-col-cuerpo" }, ...cus.map(chipCumple), ...evs.map(chip),
          !evs.length && !cus.length ? el("span", { class: "ag-vacio" }, "Libre") : null));
      pulsable(col, () => elegir(d));
      col.addEventListener("dblclick", () => nuevo(d));
      cont.append(col);
    }
    return cont;
  }

  function filaEvento(e) {
    const detalle = [e.lugar, e.repeticion && e.repeticion !== "ninguna" ? "↻ " + REPITE[e.repeticion] : ""].filter(Boolean).join(" · ");
    return pulsable(el("li", { class: "ag-item" },
      el("span", { class: "ag-item-hora" }, e.todo_el_dia ? "Todo el día" : hora(e.inicio) + (e.fin ? "–" + hora(e.fin) : "")),
      el("div", { class: "ag-item-txt" }, el("strong", null, e.titulo), detalle ? el("span", { class: "muted" }, detalle) : null)), () => abrir(e));
  }
  function filaCumple(c, d) {
    const edad = c.anio ? d.getFullYear() - c.anio : null;
    return pulsable(el("li", { class: "ag-item cumple" }, el("span", { class: "ag-item-hora ag-rosa" }, "Cumple"),
      el("div", { class: "ag-item-txt" }, el("strong", null, "Cumpleaños de " + c.nombre), edad ? el("span", { class: "muted" }, `Cumple ${edad}`) : null)), () => abrirCumple(c));
  }

  function pintarLista() {
    const cont = el("div", { class: "ag-agenda" }), [ini, fin] = rango();
    for (let d = new Date(ini); d < fin; d = sumar(d, 1)) {
      const evs = delDia(d), cus = cumplesDelDia(d);
      if (!evs.length && !cus.length) continue;
      cont.append(el("h3", { class: "ag-grupo" + (mismoDia(d, hoy0()) ? " hoy" : "") }, mismoDia(d, hoy0()) ? "Hoy · " + largo(d) : largo(d)),
        el("ul", { class: "ag-lista" }, ...cus.map((c) => filaCumple(c, d)), ...evs.map(filaEvento)));
    }
    if (!cont.children.length) cont.append(el("p", { class: "muted ag-vacio-grande" }, "Nada en los próximos 60 días. Pulsa «+ Evento» para añadir el primero."));
    return cont;
  }

  function pintarLateral() {
    $("agenda-dia-titulo").textContent = mismoDia(elegido, hoy0()) ? "Hoy" : largo(elegido);
    const ul = $("agenda-dia");
    ul.replaceChildren(...cumplesDelDia(elegido).map((c) => filaCumple(c, elegido)), ...delDia(elegido).map(filaEvento));
    if (!ul.children.length) {
      const b = el("button", { type: "button", class: "fantasma pequeno" }, "+ Añadir un evento");
      b.addEventListener("click", () => nuevo(elegido));
      ul.append(el("li", { class: "ag-vacio-dia" }, el("span", { class: "muted" }, "Día libre."), b));
    }
    const hoy = hoy0(), prox = cumples.slice().sort((a, b) => a.fecha.localeCompare(b.fecha)).slice(0, 8);
    $("agenda-cumples").replaceChildren(...prox.map((c) => {
      const dias = Math.round((new Date(c.fecha + "T00:00") - hoy) / 864e5);
      return pulsable(el("li", { class: "ag-cumple" + (dias <= 7 ? " pronto" : "") },
        el("span", { class: "ag-cumple-fecha" }, el("strong", null, String(c.dia)), el("small", null, MESES[c.mes - 1].slice(0, 3))),
        el("div", { class: "ag-item-txt" }, el("strong", null, c.nombre),
          el("span", { class: "muted" }, (dias === 0 ? "¡Hoy!" : dias === 1 ? "Mañana" : `En ${dias} días`) + (c.edad ? ` · cumple ${c.edad}` : "")))), () => abrirCumple(c));
    }));
    if (!prox.length) $("agenda-cumples").append(el("li", { class: "muted" }, "Aún no hay cumpleaños. Añádelos y ARIA te avisará."));
  }

  function pintar() {
    $("agenda-rango").textContent = titulo();
    document.querySelectorAll(".agenda-tab").forEach((b) => { b.classList.toggle("activo", b.dataset.modo === modo); b.setAttribute("aria-selected", String(b.dataset.modo === modo)); });
    $("agenda-cal").replaceChildren(modo === "mes" ? pintarMes() : modo === "semana" ? pintarSemana() : pintarLista());
    $("agenda-prev").disabled = $("agenda-next").disabled = modo === "lista";
    pintarLateral();
  }
  function elegir(d) {
    const cambiaMes = modo === "mes" && d.getMonth() !== ancla.getMonth();
    elegido = new Date(d);
    if (cambiaMes) { ancla = new Date(d.getFullYear(), d.getMonth(), 1); cargar(); } else pintar();
  }
  function mover(n) {
    ancla = modo === "mes" ? new Date(ancla.getFullYear(), ancla.getMonth() + n, 1) : sumar(ancla, 7 * n);
    cargar();
  }

  // --- Diálogo de evento ---
  function todoDia() {
    const t = $("agenda-todo-dia").checked;
    document.querySelectorAll("#form-agenda .ag-hora").forEach((x) => { x.hidden = t; x.querySelector("input").disabled = t; });
  }
  function nuevo(d) {
    editando = null;
    $("form-agenda").reset();
    $("agenda-dlg-titulo").textContent = "Nuevo evento";
    $("agenda-fecha").value = isoDia(d instanceof Date ? d : elegido);
    $("agenda-hora").value = "10:00"; $("agenda-hora-fin").value = "11:00";
    $("agenda-borrar").hidden = true; $("agenda-serie-nota").hidden = true;
    todoDia(); $("dlg-agenda").showModal(); $("agenda-titulo").focus();
  }
  function abrir(e) {
    editando = e;
    $("form-agenda").reset();
    $("agenda-dlg-titulo").textContent = "Editar evento";
    $("agenda-titulo").value = e.titulo; $("agenda-lugar").value = e.lugar || ""; $("agenda-notas").value = e.notas || "";
    $("agenda-fecha").value = diaDe(e.inicio); $("agenda-hora").value = hora(e.inicio) || "10:00"; $("agenda-hora-fin").value = hora(e.fin);
    $("agenda-todo-dia").checked = !!e.todo_el_dia; $("agenda-repeticion").value = e.repeticion || "ninguna";
    const aviso = e.aviso_min == null ? "" : String(e.aviso_min);
    if (![...$("agenda-aviso").options].some((o) => o.value === aviso)) $("agenda-aviso").append(el("option", { value: aviso }, aviso + " min antes"));
    $("agenda-aviso").value = aviso;
    $("agenda-borrar").hidden = false; $("agenda-serie-nota").hidden = (e.repeticion || "ninguna") === "ninguna";
    todoDia(); $("dlg-agenda").showModal();
  }
  async function guardar(ev) {
    ev.preventDefault();
    const todo = $("agenda-todo-dia").checked, fecha = $("agenda-fecha").value;
    let inicio = todo ? fecha + "T00:00" : fecha + "T" + ($("agenda-hora").value || "00:00");
    let fin = !todo && $("agenda-hora-fin").value ? fecha + "T" + $("agenda-hora-fin").value : null;
    if (fin && fin <= inicio) { toast("La hora de fin debe ser posterior a la de inicio.", "mal"); return; }
    if (editando && editando.serie_inicio && diaDe(editando.serie_inicio) !== diaDe(editando.inicio)) {
      // Se editó una repetición concreta: la serie se desplaza lo mismo que se movió esta repetición
      const delta = new Date(inicio) - new Date(editando.inicio.slice(0, 16));
      const base = new Date(new Date(editando.serie_inicio.slice(0, 16)).getTime() + delta);
      if (fin) fin = isoMin(new Date(base.getTime() + (new Date(fin) - new Date(inicio))));
      inicio = isoMin(base);
    }
    const datos = { titulo: $("agenda-titulo").value, inicio, fin, todo_el_dia: todo, lugar: $("agenda-lugar").value, notas: $("agenda-notas").value,
      repeticion: $("agenda-repeticion").value, aviso_min: $("agenda-aviso").value === "" ? null : Number($("agenda-aviso").value) };
    const r = editando ? await api(`/api/agenda/${editando.id}`, { method: "PATCH", json: datos }) : await api("/api/agenda", { method: "POST", json: datos });
    if (!r.ok) { toast(r.data?.error || "No se pudo guardar.", "mal"); return; }
    $("dlg-agenda").close(); toast(editando ? "Evento actualizado." : "Evento creado.");
    elegido = new Date(fecha + "T00:00"); cargar();
  }
  async function borrar() {
    if (!editando) return;
    const serie = editando.repeticion && editando.repeticion !== "ninguna";
    if (!(await confirmar("Borrar evento", `«${editando.titulo}»${serie ? " y todas sus repeticiones" : ""} dejará de aparecer.`, "Borrar"))) return;
    const r = await api(`/api/agenda/${editando.id}`, { method: "DELETE" });
    if (!r.ok) { toast(r.data?.error || "No se pudo borrar.", "mal"); return; }
    $("dlg-agenda").close(); toast("Evento borrado."); cargar();
  }

  // --- Diálogo de cumpleaños ---
  function nuevoCumple() {
    editandoCumple = null; $("form-cumple").reset();
    $("cumple-dlg-titulo").textContent = "Nuevo cumpleaños"; $("cumple-borrar").hidden = true;
    $("cumple-dia").value = elegido.getDate(); $("cumple-mes").value = String(elegido.getMonth() + 1);
    $("cumple-anio").max = new Date().getFullYear();
    $("dlg-cumple").showModal(); $("cumple-nombre").focus();
  }
  function abrirCumple(c) {
    editandoCumple = c; $("form-cumple").reset();
    $("cumple-dlg-titulo").textContent = "Cumpleaños de " + c.nombre; $("cumple-borrar").hidden = false;
    $("cumple-nombre").value = c.nombre; $("cumple-dia").value = c.dia; $("cumple-mes").value = String(c.mes);
    $("cumple-anio").value = c.anio || ""; $("cumple-aviso").value = String(c.aviso_dias || 0); $("cumple-notas").value = c.notas || "";
    $("dlg-cumple").showModal();
  }
  async function guardarCumple(ev) {
    ev.preventDefault();
    const datos = { nombre: $("cumple-nombre").value, dia: Number($("cumple-dia").value), mes: Number($("cumple-mes").value),
      anio: $("cumple-anio").value ? Number($("cumple-anio").value) : null, aviso_dias: Number($("cumple-aviso").value), notas: $("cumple-notas").value };
    const r = editandoCumple ? await api(`/api/cumpleanos/${editandoCumple.id}`, { method: "PATCH", json: datos }) : await api("/api/cumpleanos", { method: "POST", json: datos });
    if (!r.ok) { toast(r.data?.error || "No se pudo guardar.", "mal"); return; }
    $("dlg-cumple").close(); toast("Cumpleaños guardado."); cargar();
  }
  async function borrarCumple() {
    if (!editandoCumple || !(await confirmar("Borrar cumpleaños", `Se olvidará el cumpleaños de ${editandoCumple.nombre}.`, "Borrar"))) return;
    const r = await api(`/api/cumpleanos/${editandoCumple.id}`, { method: "DELETE" });
    if (!r.ok) { toast(r.data?.error || "No se pudo borrar.", "mal"); return; }
    $("dlg-cumple").close(); toast("Cumpleaños borrado."); cargar();
  }

  // --- Sincronizar con otros calendarios ---
  function pintarSincro(activa, ruta) {
    const url = ruta ? location.origin + ruta : "";
    $("sincro-enlace").hidden = !url; $("sincro-url").value = url;
    $("sincro-webcal").hidden = !url; if (url) $("sincro-webcal").href = url.replace(/^https?:/, "webcal:");
    $("sincro-quitar").hidden = !activa;
    $("sincro-crear").textContent = activa ? "Crear un enlace nuevo" : "Crear enlace";
    $("sincro-estado").textContent = url ? "Copia el enlace ahora: por seguridad, ARIA no lo vuelve a mostrar." : activa ? "Tienes un enlace activo. Si lo has perdido, crea uno nuevo (el anterior dejará de funcionar)." : "No tienes ningún enlace activo.";
  }
  async function sincro() {
    const r = await api("/api/agenda/suscripcion");
    pintarSincro(r.ok && r.data.activa, null); $("dlg-sincro").showModal();
  }
  async function crearEnlace() {
    if ($("sincro-quitar").hidden === false && !(await confirmar("Crear un enlace nuevo", "El enlace anterior dejará de funcionar en los calendarios donde lo tengas.", "Crear"))) return;
    const r = await api("/api/agenda/suscripcion", { method: "POST" });
    if (!r.ok) { toast(r.data?.error || "No se pudo crear.", "mal"); return; }
    pintarSincro(true, r.data.ruta); $("sincro-url").select();
  }

  function iniciar() {
    $("agenda-sincronizar").addEventListener("click", sincro);
    $("sincro-crear").addEventListener("click", crearEnlace);
    $("sincro-copiar").addEventListener("click", async () => { try { await navigator.clipboard.writeText($("sincro-url").value); toast("Enlace copiado."); } catch (_) { $("sincro-url").select(); toast("Selecciona y copia el enlace.", "mal"); } });
    $("sincro-quitar").addEventListener("click", async () => {
      if (!(await confirmar("Desactivar el enlace", "Los calendarios suscritos dejarán de actualizarse.", "Desactivar"))) return;
      await api("/api/agenda/suscripcion", { method: "DELETE" }); pintarSincro(false, null); toast("Enlace desactivado.");
    });
    $("dlg-sincro").addEventListener("click", (e) => { if (e.target.closest("[data-cerrar]")) $("dlg-sincro").close(); });
    $("cumple-mes").append(...MESES.map((m, i) => el("option", { value: String(i + 1) }, mayus(m))));
    $("agenda-nuevo").addEventListener("click", () => nuevo(elegido));
    $("agenda-nuevo-cumple").addEventListener("click", nuevoCumple);
    $("form-agenda").addEventListener("submit", guardar);
    $("form-cumple").addEventListener("submit", guardarCumple);
    $("agenda-borrar").addEventListener("click", borrar);
    $("cumple-borrar").addEventListener("click", borrarCumple);
    $("agenda-todo-dia").addEventListener("change", todoDia);
    for (const id of ["dlg-agenda", "dlg-cumple"]) $(id).addEventListener("click", (e) => { if (e.target.closest("[data-cerrar]")) $(id).close(); });
    $("agenda-hoy").addEventListener("click", () => { ancla = hoy0(); elegido = hoy0(); cargar(); });
    $("agenda-prev").addEventListener("click", () => mover(-1));
    $("agenda-next").addEventListener("click", () => mover(1));
    document.querySelectorAll(".agenda-tab").forEach((b) => b.addEventListener("click", () => { modo = b.dataset.modo; Prefs.set("agenda_modo", modo); ancla = new Date(elegido); cargar(); }));
    modo = Prefs.get("agenda_modo", matchMedia("(max-width: 700px)").matches ? "lista" : "mes");
  }
  return { iniciar, activar: (si) => { if (si) cargar(); } };
})();
