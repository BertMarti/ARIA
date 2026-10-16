"use strict";
// Seguridad (solo admin): estado del escáner, informe con hallazgos por gravedad y bloqueos de Pi-hole.
const Seguridad = (() => {
  let iniciado = false, sondeo = null, ultimo = null;
  const GRAVEDAD = { alta: "Alta", media: "Media", baja: "Baja", info: "Info" };
  const fmtHora = (ts) => (ts ? new Date(ts * 1000).toLocaleString("es-ES", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—");
  const dialogo = (titulo, ...contenido) => {
    const cerrar = el("button", { type: "button", class: "dialogo-cerrar", ariaLabel: "Cerrar" }, "×");
    const cabecera = el("header", { class: "dialogo-cab" }, el("h2", null, titulo), cerrar);
    const d = el("dialog", { class: "dialogo" }, cabecera, el("div", { class: "dialogo-cuerpo" }, ...contenido));
    cerrar.addEventListener("click", () => d.close());
    document.body.append(d);
    d.addEventListener("close", () => d.remove());
    d.showModal();
    return d;
  };
  function aceptar(h, accion) {
    const motivo = el("textarea", { required: "", maxlength: "200", placeholder: "Por qué lo aceptas o revisas" });
    const dias = el("select", null, ...[30, 90, 365].map((n) => el("option", { value: String(n) }, `${n} días`)));
    const f = el("form", { class: "formulario" }, el("label", null, "Motivo", motivo), el("label", null, "Duración", dias), el("button", { type: "submit", class: "primario" }, "Guardar"));
    const d = dialogo(accion === "revisado" ? "Marcar como revisado" : "Aceptar riesgo", f);
    f.addEventListener("submit", async (e) => { e.preventDefault(); const r = await api(`/api/seguridad/hallazgos/${h.clave}/accion`, { method: "POST", json: { accion, motivo: motivo.value, dias: Number(dias.value) } }); d.close(); toast(r.ok ? r.data.mensaje : (r.data.error || "No se pudo aplicar."), r.ok ? "" : "mal"); if (r.ok) informe(); });
  }
  async function accion(h, a) {
    if (a.id === "aceptar" || a.id === "revisado") return aceptar(h, a.id);
    if (a.peligro) {
      const aviso = el("p", null, "Esta acción cambiará la configuración de red.");
      const continuar = el("button", { type: "button", class: "peligro" }, "Continuar");
      const d = dialogo("Confirmar acción", aviso, continuar);
      continuar.addEventListener("click", () => { d.close(); accion(h, { ...a, peligro: false }); });
      return;
    }
    const r = await api(`/api/seguridad/hallazgos/${h.clave}/accion`, { method: "POST", json: { accion: a.id } }); toast(r.ok ? r.data.mensaje : (r.data.error || "No se pudo aplicar."), r.ok ? "" : "mal"); if (r.ok) informe();
  }
  function bloqueRemedio(h) {
    const r = h.remedio || { pasos: [], acciones: [], comprobar: false };
    const botones = (r.acciones || []).map((a) => { const b = el("button", { type: "button", class: a.peligro ? "peligro pequeno" : "fantasma pequeno" }, a.texto); b.addEventListener("click", () => accion(h, a)); return b; });
    if (r.comprobar) { const b = el("button", { type: "button", class: "fantasma pequeno" }, "Ya está, compruébalo"); b.addEventListener("click", async () => { const x = await api(`/api/seguridad/hallazgos/${h.clave}/comprobar`, { method: "POST", json: {} }); toast(x.ok ? x.data.mensaje : (x.data.error || "No se pudo comprobar."), x.ok ? "" : "mal"); }); botones.push(b); }
    return el("div", { class: "remedio" }, el("strong", null, "Cómo arreglarlo"), el("ol", null, ...(r.pasos || []).map((p) => el("li", null, p))), el("div", { class: "botones" }, ...botones));
  }

  function pintarEscaner(e) {
    const c = $("seg-escaner").querySelector(".cuerpo");
    if (!e.disponible) { c.replaceChildren(el("p", { class: "muted" }, "El contenedor aria-escaner no está instalado (docker compose up -d --build).")); return; }
    const u = e.ultimo;
    c.replaceChildren(...[
      el("div", { class: "estado" }, el("span", { class: "punto " + (e.escaner_vivo ? (e.en_curso ? "aviso" : "ok") : "mal") }),
        e.escaner_vivo ? (e.en_curso ? "Escaneando…" : e.pendientes ? "Petición en cola" : "Preparado") : "Sin señal del escáner"),
      el("p", { class: "muted" }, u ? "Último: " + fmtHora(u.fin) + " · " + (u.perfil === "completo" ? "1000 puertos" : "100 puertos") + " · " + u.origen + " · " + u.hosts + " equipos" : "Aún no hay escaneos."),
      e.siguiente_programado ? el("p", { class: "muted" }, "Próximo programado: " + fmtHora(e.siguiente_programado)) : null,
      e.ultimo_error ? el("p", { class: "error" }, "Último error: " + e.ultimo_error) : null].filter(Boolean));
    const ocupado = !!(e.en_curso || e.pendientes);
    $("seg-escanear").disabled = ocupado; $("seg-escanear-completo").disabled = ocupado;
    clearTimeout(sondeo);
    if (ocupado) sondeo = setTimeout(async () => {
      const r = await api("/api/seguridad/escaneo");
      if (r.ok) { pintarEscaner(r.data); if (!r.data.en_curso && !r.data.pendientes) informe(); }
    }, 5000);
  }

  async function informe() {
    ultimo = null;
    $("seg-hallazgos").querySelector(".cuerpo").replaceChildren(el("p", { class: "muted" }, "Generando informe (puede consultar OSV/NVD)…"));
    const { ok, data } = await api("/api/seguridad/informe");
    if (!ok) { $("seg-hallazgos").querySelector(".cuerpo").textContent = data.error || "No se pudo generar."; return; }
    ultimo = data;
    $("seg-red").textContent = "Red analizada: " + data.red;
    pintarEscaner(data.estado_escaner);
    const r = data.resumen;
    const num = (v, t, cl) => el("div", { class: "numero" }, el("strong", { class: cl }, String(v)), el("span", { class: "muted" }, t));
    $("seg-resumen").querySelector(".cuerpo").replaceChildren(
      el("div", { class: "numeros" }, num(r.alta, "altas", "error"), num(r.media, "medias", "aviso-txt"), num(r.baja, "bajas", "")),
      el("p", { class: "muted" }, data.dispositivos + " dispositivos (" + data.desconocidos + " sin reconocer)" +
        (data.escaneo ? " · " + data.escaneo.hosts + " equipos y " + data.escaneo.puertos_abiertos + " puertos abiertos en el último escaneo" : "") + "."));
    const tarjetas = data.hallazgos.map((h) => el("li", { class: "fila hallazgo g-" + h.gravedad },
      el("div", { class: "fila-info" },
        el("strong", null, el("span", { class: "pildora gravedad g-" + h.gravedad }, GRAVEDAD[h.gravedad]), " ", h.titulo),
        h.detalle ? el("span", { class: "muted" }, h.detalle) : null,
        h.recomendacion ? el("span", { class: "recomendacion" }, "Qué hacer: " + h.recomendacion) : null,
        bloqueRemedio(h))));
    $("seg-hallazgos").querySelector(".cuerpo").replaceChildren(data.hallazgos.length ? el("ul", { class: "filas" }, ...tarjetas) : el("p", { class: "muted" }, "Sin hallazgos."));
    const aceptados = data.aceptados || [];
    if (aceptados.length) {
      const sec = el("details", { class: "aceptados" }, el("summary", null, `Aceptados y revisados (${aceptados.length})`), el("ul", { class: "filas" }, ...aceptados.map((h) => el("li", { class: "fila" }, el("div", { class: "fila-info" }, el("strong", null, h.titulo), el("span", { class: "muted" }, `${h.estado.motivo} · hasta ${fmtHora(h.estado.hasta)}`)), (() => { const b = el("button", { type: "button", class: "fantasma pequeno" }, "Reabrir"); b.addEventListener("click", async () => { await api(`/api/seguridad/hallazgos/${h.clave}/estado`, { method: "DELETE" }); informe(); }); return b; })()))));
      $("seg-hallazgos").querySelector(".cuerpo").append(sec);
    }
    const b = data.bloqueos;
    $("seg-bloqueos").querySelector(".cuerpo").replaceChildren(b.length
      ? el("div", { class: "rejilla" }, ...b.map((c) => el("div", null,
        el("h3", null, c.cliente + " · " + fmtNum(c.bloqueadas)),
        el("ol", { class: "top-lista" }, ...c.dominios.map((d) => el("li", null,
          el("span", { class: "dominio", title: d.dominio }, d.dominio),
          el("span", { class: "muted" }, fmtNum(d.veces) + " · " + d.tipo)))))))
      : el("p", { class: "muted" }, "Sin datos de Pi-hole."));
  }

  async function escanear(perfil) {
    const r = await api("/api/seguridad/escaneo", { method: "POST", json: { perfil } });
    if (!r.ok) { toast(r.data.error || "No se pudo pedir el escaneo.", "mal"); return; }
    toast("Escaneo solicitado. Tarda unos minutos.");
    const e = await api("/api/seguridad/escaneo");
    if (e.ok) pintarEscaner(e.data);
  }

  function iniciar() {
    if (iniciado) return; iniciado = true;
    $("seg-escanear").addEventListener("click", () => escanear("rapido"));
    $("seg-escanear-completo").addEventListener("click", () => escanear("completo"));
    $("seg-arreglar").addEventListener("click", () => {
      if (!ultimo) return;
      const opciones = ultimo.hallazgos.flatMap((h) => (h.remedio?.acciones || []).filter((a) => a.id === "revisado" || a.id.startsWith("conocido:")).map((a) => ({ h, a })));
       const checks = opciones.map(({ h, a }) => {
         const c = el("input", { type: "checkbox" });
         const aplicar = () => { const n = checks.filter((fila) => fila.querySelector("input").checked).length; boton.disabled = !n; boton.textContent = `Aplicar (${n})`; };
         c.addEventListener("change", aplicar);
         return el("label", { class: "check-fila" }, c, el("span", { class: "check-info" }, el("strong", null, a.texto), el("span", { class: "muted" }, h.titulo)), el("span", { class: "pildora gravedad g-" + h.gravedad }, GRAVEDAD[h.gravedad]));
       });
       const boton = el("button", { type: "submit", class: "primario" }, "Aplicar (0)");
       boton.disabled = true;
       const pie = el("div", { class: "dialogo-pie" }, el("button", { type: "button", class: "fantasma" }, "Cancelar"), boton);
       const vacio = el("p", { class: "dialogo-vacio muted" }, "No hay nada que ARIA pueda arreglar sola ahora mismo");
       const contenido = el("form", { class: "dialogo-formulario" }, el("p", { class: "dialogo-intro" }, "Selecciona las acciones seguras que quieres aplicar."), opciones.length ? el("div", { class: "dialogo-opciones" }, ...checks) : vacio, pie);
       const d = dialogo("Arreglar lo que ARIA puede", contenido);
       pie.firstChild.addEventListener("click", () => d.close());
      d.querySelector("form").addEventListener("submit", async (e) => { e.preventDefault(); for (let i = 0; i < checks.length; i++) if (checks[i].querySelector("input").checked) await accion(opciones[i].h, opciones[i].a); d.close(); });
    });
  }
  function activar(si) { if (si && Sesion.esAdmin) informe(); else clearTimeout(sondeo); }
  return { iniciar, activar };
})();
