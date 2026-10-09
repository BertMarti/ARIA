"use strict";
// Ajustes → Usuarios → Accesos por invitación (solo administradores): solicitudes desde /acceso y límites de cada invitado.
const Accesos = (() => {
  let info = null;
  const NOMBRES = { inicio: "Inicio", chat: "Chat", finanzas: "Finanzas", informacion: "Información", agenda: "Agenda", mapa: "Mapa", hud: "HUD" };
  const fecha = (ts) => new Date(ts * 1000).toLocaleString("es-ES", { dateStyle: "medium", timeStyle: "short" });
  const caduca = (ts) => !ts ? "sin caducidad" : ts * 1000 < Date.now() ? "caducado" : "hasta el " + new Date(ts * 1000).toLocaleDateString("es-ES", { day: "numeric", month: "long" });

  function avisoCf(cf) {
    if (cf === "hecho" || cf === null || cf === undefined) return "";
    return cf === "manual" ? " Añade su email al grupo «Invitados ARIA» de Cloudflare Access." : " Cloudflare: " + cf;
  }

  function selectorPerfil(actual) {
    const s = el("select", { "aria-label": "Perfil" });
    for (const [id, p] of Object.entries(info.perfiles)) s.append(el("option", { value: id, selected: id === actual }, p.nombre));
    return s;
  }

  function pendiente(s) {
    const perfil = selectorPerfil("visita");
    const aprobar = el("button", { type: "button", class: "primario pequeno" }, "Aprobar");
    aprobar.addEventListener("click", async () => {
      aprobar.disabled = true;
      const r = await api("/api/acceso/solicitudes/" + s.id + "/aprobar", { method: "POST", json: { perfil: perfil.value } });
      toast(r.ok ? s.nombre + " ya tiene acceso." + avisoCf(r.data.cloudflare) : (r.data.error || "No se pudo aprobar."), r.ok ? "" : "mal");
      cargar();
    });
    const rechazar = el("button", { type: "button", class: "fantasma pequeno" }, "Rechazar");
    rechazar.addEventListener("click", async () => {
      const r = await api("/api/acceso/solicitudes/" + s.id + "/rechazar", { method: "POST" });
      toast(r.ok ? "Solicitud rechazada." : (r.data.error || "No se pudo rechazar."), r.ok ? "" : "mal");
      cargar();
    });
    return el("li", { class: "fila" },
      el("div", { class: "fila-info" }, el("strong", null, s.nombre), el("span", { class: "muted" }, s.email + " · " + fecha(s.creado)),
        el("span", null, "«" + s.motivo + "»")),
      el("div", { class: "fila-acc" }, perfil, aprobar, rechazar));
  }

  function editor(i) {
    const l = i.limites, f = el("div", { class: "acc-editor" });
    const secc = Object.keys(NOMBRES).map((s) => {
      const c = el("input", { type: "checkbox", checked: l.secciones.includes(s), disabled: s === "inicio" });
      c.dataset.seccion = s; return el("label", { class: "interruptor" }, c, el("span", null, NOMBRES[s]));
    });
    const num = (v, max) => el("input", { type: "number", min: 0, max, value: v, class: "acc-num" });
    const msj = num(l.mensajes_dia, 1000), img = num(l.imagenes_dia, 200);
    const voz = el("select", null, ...[["completa", "Su voz elegida (gasta cuota)"], ["local", "Voz local"], ["no", "Sin voz"]]
      .map(([v, t]) => el("option", { value: v, selected: l.voz === v }, t)));
    const op = (k, t) => { const c = el("input", { type: "checkbox", checked: !!l[k] }); c.dataset.op = k; return el("label", { class: "interruptor" }, c, el("span", null, t)); };
    const ops = [op("busqueda", "Búsqueda en internet"), op("memoria", "Memoria"), op("telegram", "Telegram"), op("rutinas", "Rutinas")];
    const guardar = el("button", { type: "button", class: "primario pequeno" }, "Guardar límites");
    guardar.addEventListener("click", async () => {
      const limites = { secciones: secc.map((x) => x.firstChild).filter((c) => c.checked).map((c) => c.dataset.seccion),
        mensajes_dia: Number(msj.value) || 0, imagenes_dia: Number(img.value) || 0, voz: voz.value };
      for (const x of ops) limites[x.firstChild.dataset.op] = x.firstChild.checked;
      const r = await api("/api/acceso/invitados/" + i.user_id, { method: "PATCH", json: { perfil: i.perfil, limites } });
      toast(r.ok ? "Límites guardados." : (r.data.error || "No se pudieron guardar."), r.ok ? "" : "mal");
      cargar();
    });
    f.append(el("p", { class: "muted" }, "Secciones"), el("div", { class: "acc-opciones" }, ...secc),
      el("div", { class: "fila-form" }, el("label", null, "Mensajes al día ", msj), el("label", null, "Imágenes al día ", img), el("label", null, "Voz ", voz)),
      el("div", { class: "acc-opciones" }, ...ops), guardar);
    return el("details", { class: "acc-detalles" }, el("summary", null, "Personalizar"), f);
  }

  function invitado(i) {
    const perfil = selectorPerfil(i.perfil);
    perfil.addEventListener("change", async () => {
      const r = await api("/api/acceso/invitados/" + i.user_id, { method: "PATCH", json: { perfil: perfil.value } });
      toast(r.ok ? "Perfil cambiado." : (r.data.error || "No se pudo cambiar."), r.ok ? "" : "mal"); cargar();
    });
    const mas = el("button", { type: "button", class: "fantasma pequeno", title: "Acceso durante 7 días más desde hoy" }, "+7 días");
    mas.addEventListener("click", async () => {
      const r = await api("/api/acceso/invitados/" + i.user_id, { method: "PATCH", json: { dias: 7, reactivar: true } });
      toast(r.ok ? "Acceso ampliado 7 días." + avisoCf(r.data.cloudflare) : (r.data.error || "No se pudo ampliar."), r.ok ? "" : "mal"); cargar();
    });
    const revocar = el("button", { type: "button", class: "peligro pequeno", disabled: !i.activo }, "Revocar");
    revocar.addEventListener("click", async () => {
      if (!(await confirmar("Revocar acceso", i.nombre + " dejará de poder entrar ahora mismo. Sus datos se conservan.", "Revocar"))) return;
      const r = await api("/api/acceso/invitados/" + i.user_id + "/revocar", { method: "POST" });
      toast(r.ok ? "Acceso revocado." + avisoCf(r.data.cloudflare) : (r.data.error || "No se pudo revocar."), r.ok ? "" : "mal"); cargar();
    });
    const l = i.limites;
    const resumen = l.secciones.map((s) => NOMBRES[s]).join(", ") + " · " + l.mensajes_dia + " mensajes/día · voz " + l.voz;
    return el("li", { class: "fila" },
      el("div", { class: "fila-info" }, el("strong", null, i.nombre),
        el("span", { class: "muted" }, i.email + " · " + (i.activo ? caduca(l.caduca) : "revocado")),
        el("span", { class: "muted" }, resumen), editor(i)),
      el("div", { class: "fila-acc" }, perfil, mas, revocar));
  }

  async function cargar() {
    const r = await api("/api/acceso");
    if (!r.ok) return;
    info = r.data;
    $("accesos-cf").hidden = info.cloudflare;
    const p = $("accesos-pendientes"), v = $("accesos-invitados");
    p.replaceChildren(...(info.pendientes.length ? info.pendientes.map(pendiente) : [el("li", { class: "muted" }, "No hay solicitudes pendientes.")]));
    v.replaceChildren(...(info.invitados.length ? info.invitados.map(invitado) : [el("li", { class: "muted" }, "Aún no hay invitados.")]));
  }

  function activar() { if (Sesion.esAdmin) cargar(); }
  return { activar };
})();
