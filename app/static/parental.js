"use strict";
// Control parental por dispositivo (solo admin): pausar internet, bloquear servicios y horarios.
// Todo es DNS (SHIELD-DNS): el panel lo dice con claridad. El servidor decide y valida; esto solo pinta.
const Parental = (() => {
  let datos = { servicios: [], dispositivos: [], protegidas: [], limitacion: "" };
  const AVISO_DNS_PRIVADO = "Si el dispositivo tiene un servidor de DNS privado puesto a mano, se quedará sin internet hasta que lo cambie a «Automático».";
  let actual = null; // { clave, nombre, ip }
  const DIAS = ["L", "M", "X", "J", "V", "S", "D"];

  const porClave = () => new Map(datos.dispositivos.map((e) => [e.clave, e]));
  const hhmm = (ts) => new Date(ts * 1000).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
  const nombreServicio = (id) => (datos.servicios.find((s) => s.id === id) || { nombre: id }).nombre;
  const protegido = (ip) => datos.protegidas.includes(ip);

  async function cargar() {
    const r = await api("/api/red/control");
    if (r.ok) datos = r.data;
    return r.ok;
  }

  // Resumen corto para la tabla de dispositivos.
  function resumen(e) {
    if (!e) return null;
    const t = [];
    if (e.pausado) t.push(e.pausa_manual ? (e.pausa_hasta ? "Pausado hasta " + hhmm(e.pausa_hasta) : "Pausado") : "Pausado por horario");
    if (e.servicios_bloqueados.length) t.push("Sin " + e.servicios_bloqueados.map(nombreServicio).join(", "));
    if (!t.length && e.horarios.length) t.push(e.horarios.length + " horario(s)");
    return t.length ? t.join(" · ") : null;
  }

  function celda(d, estados) {
    if (protegido(d.ip)) return el("span", { class: "muted pequeno-txt" }, "protegido");
    const e = estados.get(d.clave);
    const txt = resumen(e);
    return el("div", null,
      txt ? el("span", { class: "pildora par-pausa" }, txt) : null,
      el("button", { type: "button", class: "fantasma pequeno", onclick: () => abrir(d) }, "Control"));
  }

  async function llamar(ruta, json, metodo) {
    const r = await api(ruta, { method: metodo || "POST", json });
    if (!r.ok) { toast(r.data.error || "No se pudo completar.", "mal"); return false; }
    if (r.data.aviso) toast("Guardado, pero no se aplicó aún: " + r.data.aviso, "mal");
    await cargar(); pintar(); if (typeof Red !== "undefined") Red.recargar();
    return true;
  }

  function pintar() {
    const e = porClave().get(actual.clave);
    const c = $("par-cuerpo");
    $("par-titulo").textContent = "Control: " + actual.nombre;
    const estado = resumen(e) || "Sin restricciones ahora mismo";
    const pausa = el("div", { class: "par-seccion" }, el("h3", null, "Internet"),
      el("p", { class: "muted" }, "Ahora: " + estado + "."),
      el("div", { class: "botones" },
        ...[[30, "30 min"], [60, "1 hora"], [120, "2 horas"], [240, "4 horas"]].map(([m, t]) =>
          el("button", { type: "button", class: "fantasma pequeno", onclick: () => llamar("/api/red/control/pausa", { clave: actual.clave, minutos: m }) }, "Pausar " + t)),
        el("button", { type: "button", class: "peligro pequeno", onclick: () => llamar("/api/red/control/pausa", { clave: actual.clave, minutos: null }) }, "Pausar hasta reanudar"),
        el("button", { type: "button", class: "primario pequeno", onclick: () => llamar("/api/red/control/reanudar", { clave: actual.clave }) }, "Reanudar")),
      e && e.por_horario ? el("p", { class: "muted par-aviso" }, "Un horario mantiene el internet cortado ahora; termina solo.") : null);

    const manuales = new Set(e ? e.servicios_manuales : []);
    const bloqueados = new Set(e ? e.servicios_bloqueados : []);
    const servicios = el("div", { class: "par-seccion" }, el("h3", null, "Bloquear servicios"),
      el("div", { class: "par-servicios" }, ...datos.servicios.map((s) => {
        const cb = el("input", { type: "checkbox", checked: manuales.has(s.id) });
        cb.addEventListener("change", () => llamar("/api/red/control/servicio", { clave: actual.clave, servicio: s.id, bloquear: cb.checked }));
        return el("label", s.id === "dns-privado" ? { title: AVISO_DNS_PRIVADO } : null, cb,
          s.nombre + (bloqueados.has(s.id) && !manuales.has(s.id) ? " (por horario)" : ""));
      })),
      el("p", { class: "muted par-aviso" }, "«DNS privado / DoH» obliga al dispositivo a usar el DNS de casa, así no se salta el bloqueador ni el control parental. " + AVISO_DNS_PRIVADO));

    const horarios = el("div", { class: "par-seccion" }, el("h3", null, "Horarios"),
      ...((e && e.horarios) || []).map((h) => el("div", { class: "par-horario" + (h.activo ? " activo" : "") },
        el("span", null, h.texto + (h.activo ? " (activo ahora)" : "")),
        el("button", { type: "button", class: "fantasma pequeno", onclick: () => llamar("/api/red/control/horarios/" + h.id, undefined, "DELETE") }, "Quitar"))),
      formularioHorario());

    c.replaceChildren(
      el("p", { class: "muted par-aviso" }, datos.limitacion || "Solo bloquea por DNS."),
      pausa, servicios, horarios);
  }

  function formularioHorario() {
    const que = el("select", { ariaLabel: "Qué se corta" },
      el("option", { value: "" }, "Sin internet"),
      ...datos.servicios.map((s) => el("option", { value: s.id }, "Sin " + s.nombre)));
    const dias = DIAS.map((d, i) => ({ i, cb: el("input", { type: "checkbox", checked: i < 5 }), d }));
    const desde = el("input", { type: "time", value: "23:00", required: true, ariaLabel: "Desde" });
    const hasta = el("input", { type: "time", value: "08:00", required: true, ariaLabel: "Hasta" });
    const f = el("form", { class: "formulario" },
      el("p", { class: "muted par-aviso" }, "Los días son los de inicio; si «hasta» es menor que «desde» el tramo cruza la medianoche."),
      que,
      el("div", { class: "par-dias" }, ...dias.map((x) => el("label", null, x.cb, x.d))),
      el("div", { class: "par-hora" }, "de", desde, "a", hasta),
      el("div", { class: "botones" }, el("button", { type: "submit", class: "primario pequeno" }, "Añadir horario")));
    f.addEventListener("submit", (ev) => {
      ev.preventDefault();
      llamar("/api/red/control/horarios", { clave: actual.clave, servicio: que.value || null,
        dias: dias.filter((x) => x.cb.checked).map((x) => x.i), desde: desde.value, hasta: hasta.value });
    });
    return f;
  }

  async function abrir(d) {
    actual = { clave: d.clave, nombre: d.alias || d.nombre || d.fabricante || d.ip, ip: d.ip };
    await cargar(); pintar();
    $("dlg-parental").showModal();
  }

  function iniciar() { $("par-cerrar").addEventListener("click", () => $("dlg-parental").close()); }
  return { iniciar, cargar, celda, porClave, abrir, estados: () => porClave() };
})();
