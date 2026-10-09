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
    if (rs[0].ok) {
      // El resumen llega en Markdown: se pinta con el renderizador seguro, sin la línea final de «Fuentes:» (las fuentes ya están en las fichas)
      const texto = String(rs[0].data.resumen || "").split("\n").filter((l) => !/^\s*(\*\*)?fuentes?:?/i.test(l)).join("\n").trim();
      if (texto) { const caja = el("div", { class: "info-resumen-texto" }); renderMd(texto, caja); resumen.append(el("h3", { class: "info-resumen-tit" }, "En resumen"), caja); }
      else resumen.append(nodo("p", "No hay cerebro en la nube: se muestran solo titulares.", "muted"));
    }
    if (!rs[1].ok) { lista.append(el("li", { class: "muted" }, rs[1].data?.error || "No se pudieron cargar las noticias.")); return; }
    for (const n of rs[1].data.noticias || []) {
      const fecha = n.fecha ? new Date(n.fecha + "T12:00") : null;
      const cuando = fecha && !isNaN(fecha) ? fecha.toLocaleDateString("es-ES", { day: "numeric", month: "short" }) : "";
      lista.append(el("li", { class: "noticia" }, el("a", { href: n.url, target: "_blank", rel: "noopener noreferrer", class: "noticia-enlace" },
        el("span", { class: "noticia-fuente" }, el("span", { class: "noticia-inicial" }, (n.dominio || "?").charAt(0).toUpperCase()), n.dominio || "Fuente", cuando ? el("span", { class: "muted" }, " · " + cuando) : null),
        el("strong", { class: "noticia-titulo" }, n.titulo),
        n.extracto ? el("span", { class: "noticia-extracto" }, n.extracto) : null)));
    }
    if (!lista.children.length) lista.append(el("li", { class: "muted" }, "Sin noticias recientes de este tema."));
  }
  const eur = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 2 });
  const eurFino = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 4 });
  const num = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 6 });
  const dinero = (x) => (x == null ? "—" : (Math.abs(x) < 1 ? eurFino : eur).format(x));
  const pct = (x) => (x == null ? null : (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(2).replace(".", ",") + " %");
  function chip(etiqueta, valor) {
    const t = pct(valor);
    return el("span", { class: "chip-var " + (valor == null ? "nulo" : valor >= 0 ? "sube" : "baja"), title: etiqueta },
      etiqueta + " ", el("b", null, t == null ? "s/d" : (valor >= 0 ? "▲ " : "▼ ") + t));
  }
  function grafica(serie) {
    const v = (serie || []).filter((x) => x != null);
    if (v.length < 2) return null;
    const ns = "http://www.w3.org/2000/svg", w = 160, h = 44, min = Math.min(...v), max = Math.max(...v), r = max - min || 1;
    const pts = v.map((y, k) => `${(k / (v.length - 1) * w).toFixed(1)},${(h - 3 - (y - min) / r * (h - 6)).toFixed(1)}`).join(" ");
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`); svg.setAttribute("class", "mini-grafica " + (v[v.length - 1] >= v[0] ? "sube" : "baja"));
    svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Evolución del último periodo");
    const area = document.createElementNS(ns, "polygon"); area.setAttribute("points", `0,${h} ${pts} ${w},${h}`); area.setAttribute("class", "area");
    const linea = document.createElementNS(ns, "polyline"); linea.setAttribute("points", pts); linea.setAttribute("class", "linea");
    svg.append(area, linea);
    return svg;
  }
  async function pintarMercados() {
    const r = await api("/api/informacion/mercados"), zona = $("info-mercados"); zona.replaceChildren();
    if (!r.ok) { zona.append(nodo("p", r.data.error || "No se pudieron cargar los mercados.", "muted")); return; }
    (r.data.valores || []).forEach((v) => {
      const diaria = v.variacion_dia ?? v.variacion;
      const cab = el("div", { class: "inv-cab" }, el("strong", null, v.nombre || v.simbolo), el("small", { class: "muted" }, v.simbolo));
      if (v.error) { zona.append(el("article", { class: "tarjeta inversion" }, cab, el("p", { class: "muted" }, v.error))); return; }
      const precio = el("div", { class: "inv-precio" }, dinero(v.precio),
        diaria == null ? null : el("span", { class: "inv-dia " + (diaria >= 0 ? "sube" : "baja") }, (diaria >= 0 ? "▲ " : "▼ ") + pct(diaria)));
      const origen = v.divisa_original ? el("small", { class: "muted" }, "Convertido desde " + v.divisa_original) : null;
      const serie = (v.cierre || []).slice(-30);
      const periodos = el("div", { class: "inv-periodos" }, chip("Semana", v.variacion_semana), chip("Mes", v.variacion_mes), chip("Año", v.variacion_ano));
      let pos = null;
      if (v.valor_posicion != null) {
        const g = Number(v.ganancia_euros);
        pos = el("div", { class: "inv-posicion" },
          el("span", null, "Tu posición: ", el("b", null, dinero(v.valor_posicion))),
          el("span", { class: g >= 0 ? "sube" : "baja" }, (g >= 0 ? "Ganas " : "Pierdes ") + dinero(Math.abs(g)) + " (" + pct(v.ganancia_porcentaje) + ")"));
      }
      zona.append(el("article", { class: "tarjeta inversion" }, cab, precio, origen, grafica(serie), periodos, pos));
    });
  }
  // «1.234,5» (formato español) y «0.5» valen los dos.
  const limpiar = (t) => { t = String(t || "").trim().replace(/\s|€/g, ""); return t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t; };
  async function pintarCartera() {
    const r = await api("/api/informacion/seguimiento"), ul = $("info-cartera-lista"); ul.replaceChildren();
    const valores = r.ok ? (r.data.valores || []) : [];
    if (!valores.length) ul.append(el("li", { class: "muted" }, "Aún no sigues ningún valor: se muestran IBEX 35, S&P 500, Bitcoin y Ethereum."));
    for (const v of valores) {
      const cant = el("input", { type: "text", inputMode: "decimal", value: v.cantidad == null ? "" : num.format(v.cantidad), placeholder: "Cantidad", ariaLabel: "Cantidad de " + v.nombre });
      const pm = el("input", { type: "text", inputMode: "decimal", value: v.precio_medio == null ? "" : num.format(v.precio_medio), placeholder: "Precio medio €", ariaLabel: "Precio medio de " + v.nombre });
      const guardar = el("button", { type: "button", class: "fantasma pequeno" }, "Guardar");
      guardar.addEventListener("click", async () => {
        const x = await api("/api/informacion/seguimiento", { method: "POST", json: { simbolo: v.simbolo, nombre: v.nombre, cantidad: limpiar(cant.value), precio_medio: limpiar(pm.value) } });
        toast(x.ok ? "Guardado." : (x.data.error || "No se pudo guardar."), x.ok ? "" : "mal"); if (x.ok) pintarMercados();
      });
      const quitar = el("button", { type: "button", class: "fantasma pequeno peligro" }, "Quitar");
      quitar.addEventListener("click", async () => { await api("/api/informacion/seguimiento/" + v.id, { method: "DELETE" }); pintarCartera(); pintarMercados(); });
      ul.append(el("li", { class: "cartera-fila" }, el("div", null, el("strong", null, v.nombre), el("small", { class: "muted" }, " " + v.simbolo)), el("div", { class: "fila-form" }, cant, pm, guardar, quitar)));
    }
  }
  async function buscar(ev) {
    ev.preventDefault();
    const q = $("info-buscar-texto").value.trim(), ul = $("info-buscar-resultados"); ul.replaceChildren(el("li", { class: "muted" }, "Buscando…"));
    const r = await api("/api/informacion/buscar?q=" + encodeURIComponent(q)); ul.replaceChildren();
    const res = r.ok ? (r.data.resultados || []) : [];
    if (!res.length) { ul.append(el("li", { class: "muted" }, r.ok ? "Sin resultados. Prueba con otro nombre o con el símbolo exacto." : (r.data.error || "El buscador no responde."))); return; }
    for (const x of res.slice(0, 8)) {
      const b = el("button", { type: "button", class: "primario pequeno" }, "Añadir");
      b.addEventListener("click", async () => {
        const y = await api("/api/informacion/seguimiento", { method: "POST", json: { simbolo: x.simbolo, nombre: x.nombre } });
        toast(y.ok ? "Añadido a tus inversiones." : (y.data.error || "No se pudo añadir."), y.ok ? "" : "mal");
        if (y.ok) { ul.replaceChildren(); $("info-buscar-texto").value = ""; pintarCartera(); pintarMercados(); }
      });
      ul.append(el("li", { class: "cartera-fila" }, el("div", null, el("strong", null, x.nombre || x.simbolo), el("small", { class: "muted" }, " " + x.simbolo + (x.tipo ? " · " + x.tipo : ""))), b));
    }
  }
  function iniciar() {
    $("info-editar").addEventListener("click", () => { $("info-temas-editar").value = temas.join("\n"); $("info-buscar-resultados").replaceChildren(); pintarCartera(); $("dlg-info").showModal(); });
    $("info-buscar").addEventListener("submit", buscar);
    $("info-form").addEventListener("submit", async (ev) => { ev.preventDefault(); const r = await api("/api/informacion/temas", { method: "POST", json: { temas: $("info-temas-editar").value.split("\n") } }); if (!r.ok) { toast(r.data.error || "No se han podido guardar los temas.", "error"); return; } $("dlg-info").close(); await cargar(); });
    $("dlg-info").querySelector("[data-cerrar]").addEventListener("click", () => $("dlg-info").close());
  }
  function activar(on) { if (on) cargar(); }
  return { iniciar, activar };
})();
