"use strict";
// Inicio: saludo, lanzador de aplicaciones con estado en vivo, acciones rápidas y mini-sistema.
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

  // --- Resumen diario: una sola fuente de datos y DOM seguro ---
  const num = (n) => fmtNum(n);
  const dec = (v) => String(v).replace(".", ",");
  function icono(tipo) {
    const paths = { tiempo: "M12 3v18M5 8h14M7 16h10", apps: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z", red: "M12 4v7m0 0-6 6m6-6 6 6M8 4h8", dinero: "M4 6h16v12H4zM7 12h10", bolsa: "M5 8h14v12H5zM8 8V5h8v3", agenda: "M5 4v3m14-3v3M4 9h16M5 6h14v14H5z" };
    return el("svg", { class: "resumen-icono", viewBox: "0 0 24 24", "aria-hidden": "true" }, el("path", { d: paths[tipo] || paths.apps }));
  }
  function tarjetaResumen(tipo, titulo, contenido, clase = "") { return el("article", { class: "resumen-card " + clase }, el("div", { class: "resumen-card-cab" }, icono(tipo), el("h3", null, titulo)), contenido); }
  function progreso(valor) { const b = el("div", { class: "resumen-barra" }); const f = el("span"); f.style.width = Math.max(0, Math.min(100, Number(valor) || 0)) + "%"; b.append(f); return b; }
  function cifra(texto, detalle = "") { return el("div", { class: "resumen-cifra" }, el("strong", null, texto), el("span", { class: "muted" }, detalle)); }
  function pintarResumen(d) {
    const c = $("resumen-cuerpo"); c.replaceChildren();
    c.append(el("p", { class: "resumen-saludo" }, el("strong", null, d.saludo), " · " + d.fecha_texto));
    if (d.tiempo) c.append(tarjetaResumen("tiempo", "El tiempo", cifra((d.tiempo.actual ?? "—") + " °C", d.tiempo.ciudad + " · " + d.tiempo.min + "–" + d.tiempo.max + " °C · lluvia " + d.tiempo.lluvia + " %")));
    const a = d.aplicaciones;
    if (a) {
      const cuerpo = el("div", { class: "resumen-apps" }, el("p", { class: "resumen-veredicto" }, a.veredicto || ""));
      if (a.shield) cuerpo.append(el("p", null, "SHIELD-DNS · " + num(a.shield.consultas) + " consultas · " + num(a.shield.bloqueadas) + " bloqueos (" + a.shield.porcentaje + " %)") );
      if (a.heimdall) cuerpo.append(el("p", null, "HEIMDALL · " + a.heimdall.conectados + " de " + a.heimdall.total + " conectados"));
      if (a.raspberry) { cuerpo.append(el("p", null, "Raspberry · " + (a.raspberry.temperatura ?? "—") + " °C · RAM " + (a.raspberry.ram ?? "—") + " %")); cuerpo.append(progreso(a.raspberry.ram)); cuerpo.append(progreso(a.raspberry.disco)); }
      c.append(tarjetaResumen("apps", "Tus aplicaciones", cuerpo, "resumen-apps-card"));
    }
    if (d.red) c.append(tarjetaResumen("red", "Red", el("p", null, d.red.nuevos.length ? d.red.nuevos.length + " dispositivos nuevos" : "Sin dispositivos nuevos")));
    if (d.finanzas) { const f = d.finanzas; c.append(tarjetaResumen("dinero", "Finanzas", el("div", null, cifra((f.gastos / 100).toFixed(2).replace(".", ",") + " €", "este mes · anterior " + (f.mes_anterior / 100).toFixed(2).replace(".", ",") + " €"), ...f.presupuestos.slice(0, 3).map((p) => el("div", { class: "resumen-presupuesto" }, el("span", null, p.categoria), progreso(p.porcentaje)))))); }
    if (d.inversiones) c.append(tarjetaResumen("bolsa", "Mis inversiones", el("p", null, d.inversiones.valores.map((v) => v.nombre + ": " + (v.precio ?? "sin datos") + " €").join(" · "))));
    const ag = d.agenda || {}; c.append(tarjetaResumen("agenda", "Hoy", el("p", null, (ag.eventos || []).length + " eventos · " + (d.recordatorios || []).length + " recordatorios")));
  }
  async function resumen(refrescar) {
    const tarjeta = $("resumen-hoy");
    const { ok, data } = await api("/api/resumen-diario");
    if (!ok || !data.fecha) { tarjeta.hidden = true; return; }
    if (!refrescar && Prefs.get("resumen_cerrado", "") === data.fecha) { tarjeta.hidden = true; return; }
    pintarResumen(data); tarjeta.hidden = false; tarjeta.dataset.fecha = data.fecha;
  }

  function activar(si) {
    clearInterval(temporizador); temporizador = null;
    if (!si) return;
    saludo(); estados(); resumen(false); Modulos.pintarInicio();
     temporizador = setInterval(() => { if (!document.hidden && !document.querySelector("dialog[open]")) { estados(); resumen(true); Modulos.pintarInicio(); } }, 300000);
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
    $("resumen-cerrar").addEventListener("click", () => { Prefs.set("resumen_cerrado", $("resumen-hoy").dataset.fecha || ""); $("resumen-hoy").hidden = true; });
    $("resumen-actualizar").addEventListener("click", async () => { await resumen(true); toast("Resumen actualizado."); });
    $("form-preguntar").addEventListener("submit", (e) => {
      e.preventDefault();
      const t = $("preguntar-texto").value.trim(); if (!t) return;
      $("preguntar-texto").value = ""; location.hash = "chat"; Chat.preguntar(t);
    });
  }
  return { iniciar, activar };
})();
