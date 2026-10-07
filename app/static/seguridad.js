"use strict";
// Seguridad (solo admin): estado del escáner, informe con hallazgos por gravedad y bloqueos de Pi-hole.
const Seguridad = (() => {
  let iniciado = false, sondeo = null;
  const GRAVEDAD = { alta: "Alta", media: "Media", baja: "Baja", info: "Info" };
  const fmtHora = (ts) => (ts ? new Date(ts * 1000).toLocaleString("es-ES", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—");

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
    $("seg-hallazgos").querySelector(".cuerpo").replaceChildren(el("p", { class: "muted" }, "Generando informe (puede consultar OSV/NVD)…"));
    const { ok, data } = await api("/api/seguridad/informe");
    if (!ok) { $("seg-hallazgos").querySelector(".cuerpo").textContent = data.error || "No se pudo generar."; return; }
    $("seg-red").textContent = "Red analizada: " + data.red;
    pintarEscaner(data.estado_escaner);
    const r = data.resumen;
    const num = (v, t, cl) => el("div", { class: "numero" }, el("strong", { class: cl }, String(v)), el("span", { class: "muted" }, t));
    $("seg-resumen").querySelector(".cuerpo").replaceChildren(
      el("div", { class: "numeros" }, num(r.alta, "altas", "error"), num(r.media, "medias", "aviso-txt"), num(r.baja, "bajas", "")),
      el("p", { class: "muted" }, data.dispositivos + " dispositivos (" + data.desconocidos + " sin reconocer)" +
        (data.escaneo ? " · " + data.escaneo.hosts + " equipos y " + data.escaneo.puertos_abiertos + " puertos abiertos en el último escaneo" : "") + "."));
    $("seg-hallazgos").querySelector(".cuerpo").replaceChildren(data.hallazgos.length
      ? el("ul", { class: "filas" }, ...data.hallazgos.map((h) => el("li", { class: "fila hallazgo g-" + h.gravedad },
        el("div", { class: "fila-info" },
          el("strong", null, el("span", { class: "pildora gravedad g-" + h.gravedad }, GRAVEDAD[h.gravedad]), " ", h.titulo),
          h.detalle ? el("span", { class: "muted" }, h.detalle) : null,
          h.recomendacion ? el("span", { class: "recomendacion" }, "Qué hacer: " + h.recomendacion) : null))))
      : el("p", { class: "muted" }, "Sin hallazgos."));
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
  }
  function activar(si) { if (si && Sesion.esAdmin) informe(); else clearTimeout(sondeo); }
  return { iniciar, activar };
})();
