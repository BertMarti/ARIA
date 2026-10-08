"use strict";
const Informacion = (() => {
  let temas = [], activo = "";
  const nodo = (tag, texto, clase) => el(tag, { class: clase || "" }, texto);
  async function cargar() {
    const r = await api("/api/informacion/temas");
    if (!r.ok) return;
    temas = r.data.temas || []; activo = activo && temas.includes(activo) ? activo : temas[0];
    pintarTemas(); await Promise.all([pintarNoticias(), pintarMercados()]);
  }
  function pintarTemas() {
    const tabs = $("info-temas"), lista = $("info-temas-lista"); tabs.replaceChildren(); lista.replaceChildren();
    temas.forEach((t) => {
      const b = el("button", { type: "button", class: "fantasma pequeno" }, t);
      b.classList.toggle("activo", t === activo); b.addEventListener("click", async () => { activo = t; pintarTemas(); await pintarNoticias(); }); tabs.append(b);
      lista.append(el("li", null, nodo("span", t)));
    });
  }
  async function pintarNoticias() {
    if (!activo) return;
    const rs = await Promise.all([api("/api/informacion/resumen?tema=" + encodeURIComponent(activo)), api("/api/informacion/noticias?tema=" + encodeURIComponent(activo))]);
    const resumen = $("info-resumen"), lista = $("info-noticias"); resumen.replaceChildren(); lista.replaceChildren();
    if (rs[0].ok) { if (rs[0].data.resumen) resumen.append(nodo("p", rs[0].data.resumen)); else resumen.append(nodo("p", "No hay cerebro en la nube: se muestran solo titulares.", "muted")); }
    if (rs[1].ok) (rs[1].data.noticias || []).forEach((n) => { const a = el("a", { href: n.url, target: "_blank", rel: "noopener noreferrer" }, n.titulo); lista.append(el("li", null, a, nodo("small", (n.dominio || "") + (n.fecha ? " · " + n.fecha : ""), "muted"))); });
  }
  async function pintarMercados() {
    const r = await api("/api/informacion/mercados"), zona = $("info-mercados"); zona.replaceChildren();
    if (!r.ok) { zona.append(nodo("p", r.data.error || "No se pudieron cargar los mercados.", "muted")); return; }
    (r.data.valores || []).forEach((v) => {
      const diaria = v.variacion_dia ?? v.variacion;
      const cambio = diaria == null ? "" : ` · ${Number(diaria).toFixed(2)} %`;
      const divisa = v.divisa_original ? ` EUR (original: ${v.divisa_original})` : ` ${v.divisa || ""}`;
      const posicion = v.valor_posicion == null ? null : nodo("small", `Posición: ${Number(v.valor_posicion).toFixed(2)} EUR · ` +
        `P/L: ${Number(v.ganancia_euros).toFixed(2)} EUR (${Number(v.ganancia_porcentaje).toFixed(2)} %)`);
      const variaciones = v.precio == null ? null : nodo("small", `Día${cambio} · semana: ${v.variacion_semana == null ? "sin datos" : Number(v.variacion_semana).toFixed(2) + " %"} · mes: ${v.variacion_mes == null ? "sin datos" : Number(v.variacion_mes).toFixed(2) + " %"} · año: ${v.variacion_ano == null ? "sin datos" : Number(v.variacion_ano).toFixed(2) + " %"}`);
      zona.append(el("article", { class: "tarjeta mercado" }, nodo("strong", v.nombre || v.simbolo), nodo("span", v.error || `${v.precio ?? "sin datos"}${divisa}`), nodo("small", cambio, Number(diaria) >= 0 ? "sube" : "baja"), posicion, variaciones));
    });
  }
  function iniciar() {
    $("info-editar").addEventListener("click", () => { $("info-temas-editar").value = temas.join("\n"); $("dlg-info").showModal(); });
    $("info-form").addEventListener("submit", async (ev) => { ev.preventDefault(); const r = await api("/api/informacion/temas", { method: "POST", json: { temas: $("info-temas-editar").value.split("\n") } }); if (!r.ok) { toast(r.data.error || "No se han podido guardar los temas.", "error"); return; } $("dlg-info").close(); await cargar(); });
    $("dlg-info").querySelector("[data-cerrar]").addEventListener("click", () => $("dlg-info").close());
  }
  function activar(on) { if (on) cargar(); }
  return { iniciar, activar };
})();
