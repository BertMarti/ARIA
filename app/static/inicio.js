"use strict";
// Inicio: saludo, menú en tarjetas numeradas, lanzador de aplicaciones con estado en vivo, acciones rápidas y mini-sistema.
const Inicio = (() => {
  let temporizador = null, puertos = { shield_web: 8443, vpn: 51843 };

  let usuario = "";
  function saludo() {
    const h = new Date().getHours();
    const s = h >= 6 && h < 13 ? "Buenos días" : h >= 13 && h < 21 ? "Buenas tardes" : "Buenas noches";
    $("saludo").textContent = usuario ? s + ", " + usuario : s;
    const f = new Date().toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });
    $("inicio-fecha").textContent = f.charAt(0).toUpperCase() + f.slice(1);
  }

  function tile(id, estado, texto, titulo) {
    const t = $(id);
    const p = t.querySelector(".tile-punto");
    p.className = "punto tile-punto " + estado; p.title = titulo || "";
    const info = t.querySelector(".tile-info"); if (info) info.textContent = texto;
  }

  async function estados() {
    const [sh, vp, sp, sis] = await Promise.all([api("/api/shield"), api("/api/vpn/clients"), (Sesion.funciones.spotify ? api("/api/spotify/status") : Promise.resolve({ data: {} })), api("/api/system")]);
    const s = sh.data, v = vp.data, p = sp.data;
    if (s.conectado) tile("tile-shield", "ok", fmtNum(s.bloqueadas) + " anuncios bloqueados (24 h)", s.bloqueo_activo ? "Activo" : "En pausa");
    else if (s.error) tile("tile-shield", "mal", "Sin respuesta", "Caído");
    else tile("tile-shield", "", "No instalado / sin conectar", "No instalado");
    if (v.conectado) tile("tile-vpn", "ok", v.clientes.filter((c) => c.conectado).length + " de " + v.clientes.length + " dispositivos conectados", "Activo");
    else if (v.error) tile("tile-vpn", "mal", "Sin respuesta", "Caído");
    else tile("tile-vpn", "", "No instalado / sin conectar", "No instalado");
    if (!Sesion.funciones.spotify) { /* aparcado: la tarjeta está oculta */ }
    else if (!p.configurado) tile("tile-spotify", "", "Abrir Spotify en una pestaña nueva", "Control desde ARIA sin configurar");
    else tile("tile-spotify", p.conectado ? "ok" : "aviso", p.conectado ? "Control desde ARIA activo" : "Pendiente de conectar", "");
    Control.pintarSistema($("inicio-sistema").querySelector(".cuerpo"), sis);
  }

  async function copiarSecreto(boton) {
    const r = await api("/api/secret/" + boton.dataset.secreto, { method: "POST" });
    if (!r.ok) { toast(r.data.error || "No se pudo obtener la contraseña.", "mal"); return; }
    try { await navigator.clipboard.writeText(r.data.password); }
    catch (_) {
      const ta = el("textarea", { value: r.data.password }); document.body.append(ta); ta.select();
      try { document.execCommand("copy"); } catch (_e) { /* sin portapapeles */ }
      ta.remove();
    }
    toast("Contraseña copiada" + (r.data.usuario ? " (usuario: " + r.data.usuario + ")" : "") + ". Pégala en el panel.");
  }

  async function pausar() {
    const r = await api("/api/shield/pause", { method: "POST", json: { minutos: 5 } });
    toast(r.ok ? "Anuncios sin bloquear durante 5 minutos." : (r.data.error || "No se pudo pausar."), r.ok ? "" : "mal"); estados();
  }
  async function reanudar() {
    const r = await api("/api/shield/resume", { method: "POST" });
    toast(r.ok ? "Bloqueador de anuncios reanudado." : (r.data.error || "No se pudo reanudar."), r.ok ? "" : "mal"); estados();
  }
  async function resumenSistema() {
    const { ok, data: d } = await api("/api/system");
    if (!ok) { toast("No se pudo leer el sistema.", "mal"); return; }
    const partes = [];
    if (d.temperatura != null) partes.push(d.temperatura.toString().replace(".", ",") + " °C");
    if (d.memoria) partes.push("RAM " + Math.round(d.memoria.porcentaje) + " %");
    if (d.disco) partes.push("disco " + Math.round(d.disco.porcentaje) + " %");
    toast("Sistema: " + partes.join(" · ") + " · encendida " + d.uptime_texto);
  }

  // --- Resumen diario (/api/resumen-diario): la misma fuente que Telegram y el HUD; todo con nodos del DOM ---
  const eur = (n, dec = 2) => Number(n).toLocaleString("es-ES", { style: "currency", currency: "EUR", minimumFractionDigits: dec, maximumFractionDigits: dec, useGrouping: "always" });
  const pct = (p, signo = true) => (signo && p > 0 ? "+" : "") + Number(p).toLocaleString("es-ES", { minimumFractionDigits: signo ? 2 : 1, maximumFractionDigits: signo ? 2 : 1 }) + " %";
  const hora = (iso) => String(iso || "").slice(11, 16);
  // Iconos de trazo (SVG), no emojis: se ven igual en cualquier sistema
  const ICONOS = {
    tiempo: "M12 3v2M5.6 5.6l1.4 1.4M3 12h2M17 7l1.4-1.4M8.5 13a3.5 3.5 0 1 1 6.6 1.6M7 20h10a3 3 0 0 0 0-6 4.5 4.5 0 0 0-8.6-1A3.5 3.5 0 0 0 7 20z",
    apps: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z", red: "M2 9a15 15 0 0 1 20 0M5.5 12.5a10 10 0 0 1 13 0M9 16a5 5 0 0 1 6 0M12 20h.01",
    dinero: "M3 6h18v12H3zM12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM6 9v.01M18 15v.01", bolsa: "M3 17l6-6 4 4 8-8M15 7h6v6",
    agenda: "M4 6h16v14H4zM4 10h16M8 3v5M16 3v5", escudo: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z", llave: "M7 14a4 4 0 1 1 3.9-5H21v3h-2v3h-3v-3h-5.1A4 4 0 0 1 7 14z",
    cerebro: "M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 1V4.5A3 3 0 0 0 9 4zM15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-6 1",
    chip: "M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4", rayo: "M13 3 4 14h7l-1 7 9-11h-7z", disco: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3v12c0 1.7-3.6 3-8 3s-8-1.3-8-3zM4 6c0 1.7 3.6 3 8 3s8-1.3 8-3",
  };
  function ico(nombre, clase = "rd-ico") {
    const NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg"), path = document.createElementNS(NS, "path");
    svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("class", clase); svg.setAttribute("aria-hidden", "true");
    path.setAttribute("d", ICONOS[nombre] || ICONOS.apps); svg.append(path); return svg;
  }
  function tarjetaR(icono, titulo, clase, ...hijos) {
    return el("article", { class: "rd-card " + (clase || "") },
      el("header", { class: "rd-cab" }, el("span", { class: "rd-emoji" }, ico(icono)), el("h3", null, titulo)), ...hijos);
  }
  function barra(valor, aviso) {
    const b = el("div", { class: "rd-barra" + (aviso ? " aviso" : "") }), f = el("span");
    f.style.width = Math.max(0, Math.min(100, Number(valor) || 0)) + "%"; b.append(f); return b;
  }
  function fila(icono, etq, valor, clase) { return el("div", { class: "rd-fila " + (clase || "") }, el("span", { class: "muted rd-etq" }, icono ? ico(icono, "rd-ico-p") : null, etq), el("strong", null, valor)); }
  function chipCambio(c) { return c == null ? null : el("span", { class: "rd-chip " + (c >= 0 ? "sube" : "baja") }, (c >= 0 ? "▲ " : "▼ ") + pct(c)); }
  function pintarResumen(d) {
    const c = $("resumen-cuerpo"); c.replaceChildren();
    const t = d.tiempo;
    if (t) c.append(tarjetaR("tiempo", "El tiempo · " + t.ciudad, "rd-tiempo",
      el("div", { class: "rd-grande" }, (t.actual ?? t.max) + " °C"), el("p", { class: "rd-sub" }, t.cielo.charAt(0).toUpperCase() + t.cielo.slice(1)),
      el("div", { class: "rd-mini" }, el("span", null, "↓ " + t.min + " °C"), el("span", null, "↑ " + t.max + " °C"), el("span", null, "Lluvia " + (t.lluvia ?? "—") + " %")),
      t.aviso_manana ? el("p", { class: "rd-alerta" }, "⚠ " + t.aviso_manana) : null));
    const lz = d.luz;
    if (lz) {
      const kwh = (p) => p.toLocaleString("es-ES", { minimumFractionDigits: 3, maximumFractionDigits: 3 }) + " €/kWh";
      const NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg"), hAct = new Date().getHours();
      const max = Math.max(...lz.serie), min = Math.min(...lz.serie);
      svg.setAttribute("viewBox", "0 0 240 60"); svg.setAttribute("preserveAspectRatio", "none"); svg.setAttribute("class", "rd-luz-graf"); svg.setAttribute("aria-hidden", "true");
      lz.serie.forEach((p, i) => {
        const r = document.createElementNS(NS, "rect"), alto = 8 + (p - min) / ((max - min) || 1) * 50;
        r.setAttribute("x", i * 10 + 1); r.setAttribute("y", 60 - alto); r.setAttribute("width", 8); r.setAttribute("height", alto); r.setAttribute("rx", 1.5);
        r.setAttribute("class", (p <= lz.media * .9 ? "barata" : p >= lz.media * 1.1 ? "cara" : "media") + (i === hAct ? " ahora" : ""));
        svg.append(r);
      });
      c.append(tarjetaR("rayo", "Precio de la luz", "rd-luz",
        el("div", { class: "rd-grande" }, (lz.ahora ? lz.ahora.precio : lz.media).toLocaleString("es-ES", { minimumFractionDigits: 3, maximumFractionDigits: 3 }) + " €"),
        el("p", { class: "rd-sub" }, "por kWh · " + (lz.ahora ? "ahora, " + ({ barata: "hora barata", media: "precio medio", cara: "hora cara" }[lz.nivel] || "") : "media de hoy")),
        svg, el("div", { class: "rd-luz-ejes" }, el("span", null, "0 h"), el("span", null, "12 h"), el("span", null, "23 h")),
        fila(null, "Más barata", lz.barata.hora + ":00 · " + kwh(lz.barata.precio).replace("/kWh", "")),
        fila(null, "Más cara", lz.cara.hora + ":00 · " + kwh(lz.cara.precio).replace("/kWh", ""), "aviso"),
        lz.mejores_restantes?.length ? el("p", { class: "rd-nota" }, "Mejores horas que quedan: " + lz.mejores_restantes.map((x) => x.hora + " h").join(", ")) : null));
    }
    const a = d.aplicaciones;
    if (a) {
      const filas = [el("p", { class: "rd-veredicto " + (a.ok ? "ok" : "mal") }, a.ok ? "✓ Todo en orden" : "⚠ " + a.problemas.length + (a.problemas.length === 1 ? " cosa que revisar" : " cosas que revisar"))];
      if (!a.ok) filas.push(el("ul", { class: "rd-problemas" }, ...a.problemas.map((p) => el("li", null, p.charAt(0).toUpperCase() + p.slice(1)))));
      if (a.shield) filas.push(fila("escudo", "SHIELD-DNS", fmtNum(a.shield.bloqueadas) + " bloqueos · " + pct(a.shield.porcentaje, false)));
      if (a.heimdall) filas.push(fila("llave", "HEIMDALL", a.heimdall.conectados + " de " + a.heimdall.total + " conectados"));
      if (a.aria) filas.push(fila("cerebro", "Cerebros de IA", a.aria.listos + " de " + a.aria.total + " listos"));
      const r = a.raspberry;
      if (r) {
        if (r.temperatura != null) filas.push(fila("chip", "Raspberry Pi", String(r.temperatura).replace(".", ",") + " °C", r.temperatura >= 75 ? "aviso" : ""));
        if (r.encendida) filas.push(fila(null, "Encendida", r.encendida));
        if (r.ram != null) filas.push(el("div", { class: "rd-medidor" }, el("span", { class: "muted" }, "RAM " + r.ram + " %"), barra(r.ram, r.ram > 85)));
        if (r.disco != null) filas.push(el("div", { class: "rd-medidor" }, el("span", { class: "muted" }, "Disco " + r.disco + " %"), barra(r.disco, r.disco > 85)));
      }
      if (a.copia) filas.push(fila("disco", "Copia", a.copia.disponible ? "hace " + a.copia.hace : "no disponible", a.copia.antigua ? "aviso" : ""));
      c.append(tarjetaR("apps", "Tus aplicaciones", "rd-apps", ...filas));
    }
    if (d.red) {
      const rd = d.red, cuerpo = [el("div", { class: "rd-grande" }, String(rd.total)), el("p", { class: "rd-sub" }, "dispositivos en la red")];
      cuerpo.push(el("p", null, rd.nuevos.length ? rd.nuevos.length + " nuevos en 24 h: " + rd.nuevos.slice(0, 4).map((x) => x.nombre).join(", ") : "Sin dispositivos nuevos en 24 h"));
      if (rd.n_desconocidos) cuerpo.push(el("a", { class: "rd-alerta", href: "#red" }, rd.n_desconocidos + " sin identificar →"));
      c.append(tarjetaR("red", "Red", "rd-red", ...cuerpo));
    }
    const f = d.finanzas;
    if (f) {
      const cuerpo = [el("div", { class: "rd-grande" }, eur(f.gastos / 100)), el("p", { class: "rd-sub" }, "gastado en " + f.mes_texto)];
      if (f.mes_anterior_mismo_dia) {
        const dif = Math.round((f.gastos - f.mes_anterior_mismo_dia) * 100 / f.mes_anterior_mismo_dia);
        cuerpo.push(el("p", null, el("span", { class: "rd-chip " + (dif > 0 ? "baja" : "sube") }, (dif > 0 ? "▲ " : "▼ ") + Math.abs(dif) + " %"), " frente al mes pasado a estas alturas"));
      }
      for (const p of (f.presupuestos || []).slice().sort((x, y) => y.porcentaje - x.porcentaje).slice(0, 3))
        cuerpo.push(el("div", { class: "rd-medidor" }, el("span", { class: "muted" }, p.categoria + " · " + Math.round(p.porcentaje) + " %"), barra(p.porcentaje, p.superado)));
      c.append(tarjetaR("dinero", "Finanzas", "rd-fin", ...cuerpo));
    }
    const inv = d.inversiones;
    if (inv) {
      const lista = el("ul", { class: "rd-inv" }, ...inv.valores.map((v) => el("li", null,
        el("span", { class: "rd-inv-nombre" }, v.nombre || v.simbolo), el("strong", null, eur(v.precio, v.precio >= 1000 ? 0 : 2)), chipCambio(v.variacion_dia))));
      c.append(tarjetaR("bolsa", "Mis inversiones", "rd-inv-card", lista,
        inv.total_posiciones ? fila(null, "Total de tus posiciones", eur(inv.total_posiciones)) : null,
        el("a", { class: "rd-enlace", href: "#informacion" }, "Ver gráficas →")));
    }
    const ag = d.agenda || {}, items = [];
    for (const e of ag.eventos || []) items.push(el("li", null, el("span", { class: "rd-hora" }, e.todo_el_dia ? "Día" : hora(e.inicio)), el("span", null, e.titulo + (e.lugar ? " · " + e.lugar : ""))));
    for (const r of d.recordatorios || []) items.push(el("li", null, el("span", { class: "rd-hora" }, hora(r.cuando)), el("span", null, r.texto)));
    for (const cu of ag.cumpleanos || []) items.push(el("li", null, el("span", { class: "rd-hora" }, "Cumple"), el("span", null, cu.nombre + (cu.edad ? " (" + cu.edad + ")" : "") + " · " + new Date(cu.fecha + "T12:00").toLocaleDateString("es-ES", { weekday: "long", day: "numeric" }))));
    c.append(tarjetaR("agenda", "Hoy", "rd-hoy", items.length ? el("ul", { class: "rd-agenda" }, ...items) : el("p", { class: "muted" }, "Día despejado: sin eventos ni recordatorios."),
      el("a", { class: "rd-enlace", href: "#agenda" }, "Abrir la agenda →")));
    if (d.cierre) c.append(el("p", { class: "rd-cierre" }, d.cierre));
  }
  // --- Menú principal en tarjetas numeradas (mismo sistema visual que el escaparate) ---
  // Cada tarjeta: vista a la que lleva, etiqueta mono, título, un dato vivo del resumen y su estado.
  const MENU = [
    { vista: "hud", etq: "Presencia", titulo: "Modo HUD", destacada: true, visual: () => el("span", { class: "mi-v-orbe" }, el("i"), el("i"), el("i")),
      dato: () => "ARIA a pantalla completa", estado: () => ["Activo", "ok"] },
    { vista: "resumen", etq: "Hoy", titulo: "Resumen del día", destacada: true, visual: visualResumen, dato: datoResumen,
      estado: (d) => !d ? ["Cargando", ""] : d.aplicaciones && !d.aplicaciones.ok ? ["Aviso", "aviso"] : ["Al día", "ok"] },
    { vista: "agenda", etq: "Tiempo", titulo: "Agenda", dato: datoAgenda, estado: () => ["Activo", "ok"],
      visual: () => el("span", { class: "mi-v-cal" }, ...Array.from({ length: 7 }, (_, i) => el("i", { class: i === (new Date().getDay() + 6) % 7 ? "hoy" : "" }))) },
    { vista: "red", etq: "Casa", titulo: "Tu casa", admin: true, visual: () => el("span", { class: "mi-v-red" }, el("i"), el("i"), el("i"), el("i"), el("i")),
      dato: (d) => d?.red ? d.red.total + " dispositivos" + (d.aplicaciones?.shield ? " · " + fmtNum(d.aplicaciones.shield.bloqueadas) + " anuncios fuera" : "") : "Red, VPN y anuncios",
      estado: (d) => d?.red?.n_desconocidos ? ["Aviso", "aviso"] : ["Activo", "ok"] },
    { vista: "informacion", etq: "Mundo", titulo: "Información", visual: visualInversiones,
      dato: (d) => d?.inversiones ? "Tus inversiones y noticias" : "Noticias y mercados", estado: () => ["Activo", "ok"] },
    { vista: "mapa", etq: "Lugar", titulo: "Mapa", visual: () => el("span", { class: "mi-v-mapa" }, el("i")), dato: () => "Tu zona, el tiempo y rutas", estado: () => ["Activo", "ok"] },
    { vista: "chat", etq: "Conversación", titulo: "Chat", visual: () => el("span", { class: "mi-v-lineas" }, el("i"), el("i"), el("i")),
      dato: (d) => d?.aplicaciones?.aria ? d.aplicaciones.aria.listos + " de " + d.aplicaciones.aria.total + " cerebros listos" : "Habla o escribe a ARIA", estado: () => ["Activo", "ok"] },
    { vista: "finanzas", etq: "Dinero", titulo: "Finanzas", visual: () => el("span", { class: "mi-v-barras" }, el("i"), el("i"), el("i"), el("i")),
      dato: (d) => d?.finanzas ? eur(d.finanzas.gastos / 100, 0) + " en " + d.finanzas.mes_texto : "Gastos y presupuestos", estado: () => ["Activo", "ok"] },
    { pronto: true, etq: "En construcción", titulo: "ARIA PRO", visual: () => el("span", { class: "mi-v-lineas pronto" }, el("i"), el("i"), el("i")),
      dato: () => "Briefing hablado, voz propia y ARIA flotante", estado: () => ["Pronto", "pronto"] },
  ];
  function visualResumen(d) {
    const t = d?.tiempo, lz = d?.luz;
    return el("span", { class: "mi-v-resumen" },
      el("strong", null, t ? (t.actual ?? t.max) + "°" : "—"),
      el("span", null, t ? t.cielo : "Cargando…"),
      lz ? el("span", { class: "mi-v-luz " + (lz.nivel || "") }, "Luz " + (lz.ahora ? lz.ahora.precio : lz.media).toLocaleString("es-ES", { minimumFractionDigits: 3, maximumFractionDigits: 3 }) + " €/kWh") : null);
  }
  function datoResumen(d) {
    if (!d) return "El tiempo, la luz, tu casa y tu día";
    const a = d.aplicaciones;
    return a && !a.ok ? a.problemas.length + (a.problemas.length === 1 ? " cosa que revisar" : " cosas que revisar") : "Todo en orden en casa";
  }
  function datoAgenda(d) {
    if (!d) return "Eventos, recordatorios y cumpleaños";
    const ag = d.agenda || {}, ahora = new Date().toTimeString().slice(0, 5);
    const lista = [...(ag.eventos || []).filter((e) => !e.todo_el_dia).map((e) => [hora(e.inicio), e.titulo]),
      ...(d.recordatorios || []).map((r) => [hora(r.cuando), r.texto])].sort((x, y) => x[0].localeCompare(y[0]));
    const total = (ag.eventos || []).length + (d.recordatorios || []).length, sig = lista.find((x) => x[0] >= ahora);
    return sig ? "Próximo: " + sig[0] + " · " + sig[1] : total ? total + " cosas hoy, nada más pendiente" : "Día despejado";
  }
  function visualInversiones(d) {
    const v = (d?.inversiones?.valores || []).slice(0, 3);
    if (!v.length) return el("span", { class: "mi-v-lineas" }, el("i"), el("i"), el("i"));
    return el("span", { class: "mi-v-inv" }, ...v.map((x) => el("span", null, el("span", null, x.nombre || x.simbolo), chipCambio(x.variacion_dia))));
  }
  function pintarMenu(d) {
    const cont = $("menu-inicio"); if (!cont) return;
    const visibles = MENU.filter((m) => !(m.admin && !Sesion.esAdmin));
    cont.replaceChildren(...visibles.map((m, i) => {
      const [estado, clase] = m.estado(d), visual = el("span", { class: "mi-visual" }, m.visual(d));
      visual.setAttribute("aria-hidden", "true");
      const hijos = [
        el("span", { class: "mi-cab" }, el("span", { class: "mi-num" }, String(i + 1).padStart(2, "0")), el("span", null, m.etq)),
        visual, el("span", { class: "mi-nombre" }, m.titulo), el("span", { class: "mi-dato" }, m.dato(d)),
        el("span", { class: "mi-estado " + clase }, estado),
      ];
      if (m.pronto) {   // rellena lo que quede de su fila en la rejilla de 4 columnas
        const usadas = visibles.slice(0, i).reduce((n, x) => n + (x.destacada ? 2 : 1), 0);
        return el("div", { class: "mi-carta pronto relleno-" + (4 - usadas % 4) }, ...hijos);
      }
      const a = el("a", { class: "mi-carta" + (m.destacada ? " destacada" : ""), href: "#" + m.vista }, ...hijos);
      if (m.vista === "resumen") a.addEventListener("click", (e) => { e.preventDefault(); abrirResumen(); });
      return a;
    }));
  }
  async function abrirResumen() {
    Prefs.set("resumen_cerrado", "");
    await resumen(false);
    $("resumen-hoy").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }
  function luzRaton(e) {   // brillo que sigue al ratón dentro de cada tarjeta (CSSOM: lo permite la CSP)
    const c = e.target.closest?.(".mi-carta"); if (!c) return;
    const r = c.getBoundingClientRect();
    c.style.setProperty("--mx", ((e.clientX - r.left) / r.width * 100).toFixed(1) + "%");
    c.style.setProperty("--my", ((e.clientY - r.top) / r.height * 100).toFixed(1) + "%");
  }
  function reloj() { const r = $("mi-reloj"); if (r) r.textContent = new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }); }

  async function resumen(refrescar) {
    const tarjeta = $("resumen-hoy");
    const { ok, data } = await api("/api/resumen-diario" + (refrescar ? "?refrescar=1" : ""));
    if (ok && data.fecha) pintarMenu(data);
    if (!ok || !data.fecha) { tarjeta.hidden = true; return; }
    if (!refrescar && Prefs.get("resumen_cerrado", "") === data.fecha) { tarjeta.hidden = true; return; }
    pintarResumen(data); tarjeta.hidden = false; tarjeta.dataset.fecha = data.fecha;
  }

  function activar(si) {
    clearInterval(temporizador); temporizador = null;
    if (!si) return;
    saludo(); reloj(); estados(); resumen(false); Modulos.pintarInicio();
    let vueltas = 0;
    temporizador = setInterval(() => {
      reloj();
      if (document.hidden || document.querySelector("dialog[open]")) return;
      estados(); Modulos.pintarInicio();
      if (++vueltas % 20 === 0) resumen(false);   // cada 5 min (el servidor lo cachea 10 min)
    }, 15000);
  }

  async function iniciar() {
    const { data } = await api("/api/info");
    if (data.puertos) puertos = data.puertos;
    usuario = Sesion.nombre || data.usuario || ""; saludo();
    $("tile-shield-a").href = enlacePanel("shield", "https://" + location.hostname + ":" + puertos.shield_web + "/admin");
    $("tile-vpn-a").href = enlacePanel("vpn", "https://" + location.hostname + ":" + puertos.vpn);
    document.querySelectorAll("[data-secreto]").forEach((b) => b.addEventListener("click", () => copiarSecreto(b)));
    if (Sesion.esAdmin) {
    $("qa-pausar").addEventListener("click", pausar);
    $("qa-reanudar").addEventListener("click", reanudar);
    $("qa-vpn").addEventListener("click", () => Control.anadir());
    }
    $("qa-sistema").addEventListener("click", resumenSistema);
    Voz.botonMic($("preguntar-mic"), (t) => { $("preguntar-texto").value = t; $("form-preguntar").requestSubmit(); });
    pintarMenu(null);
    $("menu-inicio").addEventListener("pointermove", luzRaton, { passive: true });
    $("resumen-cerrar").addEventListener("click", () => { Prefs.set("resumen_cerrado", $("resumen-hoy").dataset.fecha || ""); $("resumen-hoy").hidden = true; });
    $("resumen-actualizar").addEventListener("click", async () => { await resumen(true); toast("Resumen actualizado."); });
    const escuchar = $("resumen-escuchar");
    escuchar.addEventListener("click", async () => {
      if (escuchar.getAttribute("aria-pressed") === "true") { Voz.parar(); return; }
      escuchar.setAttribute("aria-pressed", "true"); escuchar.textContent = "■ Parar";
      try { await Voz.briefing(); } finally { escuchar.setAttribute("aria-pressed", "false"); escuchar.textContent = "▶ Escuchar"; }
    });
    $("form-preguntar").addEventListener("submit", (e) => {
      e.preventDefault();
      const t = $("preguntar-texto").value.trim(); if (!t) return;
      $("preguntar-texto").value = ""; location.hash = "chat"; Chat.preguntar(t);
    });
  }
  return { iniciar, activar };
})();
