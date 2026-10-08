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
    const [sh, vp, sp, sis] = await Promise.all([api("/api/shield"), api("/api/vpn/clients"), api("/api/spotify/status"), api("/api/system")]);
    const s = sh.data, v = vp.data, p = sp.data;
    if (s.conectado) tile("tile-shield", "ok", fmtNum(s.bloqueadas) + " anuncios bloqueados (24 h)", s.bloqueo_activo ? "Activo" : "En pausa");
    else if (s.error) tile("tile-shield", "mal", "Sin respuesta", "Caído");
    else tile("tile-shield", "", "No instalado / sin conectar", "No instalado");
    if (v.conectado) tile("tile-vpn", "ok", v.clientes.filter((c) => c.conectado).length + " de " + v.clientes.length + " dispositivos conectados", "Activo");
    else if (v.error) tile("tile-vpn", "mal", "Sin respuesta", "Caído");
    else tile("tile-vpn", "", "No instalado / sin conectar", "No instalado");
    if (!p.configurado) tile("tile-spotify", "", "Abrir Spotify en una pestaña nueva", "Control desde ARIA sin configurar");
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

  // --- Resumen de buenos días («Tu resumen de hoy») ---
  const num = (n) => fmtNum(n);
  const dec = (v) => String(v).replace(".", ",");
  function lista(items) { return el("ul", { class: "resumen-lista" }, ...items.map((t) => el("li", null, t))); }
  function bloque(titulo, contenido) { return el("section", { class: "resumen-bloque" }, el("h3", null, titulo), contenido); }
  function pintarResumen(d) {
    const c = $("resumen-cuerpo"); c.replaceChildren();
    c.append(el("p", { class: "resumen-saludo" }, el("strong", null, d.saludo), " · " + d.fecha_texto));
    if (d.tiempo) c.append(bloque("El tiempo", el("p", null, d.tiempo.ciudad + ": " + d.tiempo.cielo + (d.tiempo.actual != null ? ", ahora " + d.tiempo.actual + " °C" : "") + ", entre " + d.tiempo.min + " y " + d.tiempo.max + " °C" + (d.tiempo.lluvia != null ? " · lluvia " + d.tiempo.lluvia + " %" : ""))));
    if (d.ayer) c.append(bloque("Ayer", lista(d.ayer.resumen.split("\n").map((l) => l.replace(/^[-•\s]+/, "")).filter(Boolean))));
    const casa = d.casa || {}, f = [];
    const a = casa.anuncios;
    f.push(a ? num(a.bloqueadas) + " anuncios bloqueados " + (a.dia === "ayer" ? "ayer" : "(últimas 24 h)") + " (" + dec(a.porcentaje) + " % de " + num(a.consultas) + " consultas)" : "Anuncios bloqueados: no disponible");
    if (casa.vpn) {
      const v = casa.vpn;
      f.push(v.disponible ? "VPN: " + v.conectados + " de " + v.total + " dispositivos conectados ahora" + (v.ultimas_24h.length ? "; en 24 h: " + v.ultimas_24h.join(", ") : "") : "VPN: no disponible");
    }
    const s = casa.sistema;
    if (s) f.push("Raspberry: " + [s.temperatura != null ? dec(s.temperatura) + " °C" : null, s.ram != null ? "RAM " + s.ram + " %" : null, s.disco != null ? "disco " + s.disco + " %" : null].filter(Boolean).join(" · "));
    if (casa.copia) f.push("Última copia fuera de la Pi: " + (casa.copia.disponible ? casa.copia.hace + (casa.copia.antigua ? " (antigua)" : "") : "no disponible"));
    c.append(bloque("En casa", lista(f)));
    if (d.recuerdos && d.recuerdos.length) c.append(bloque("Por si te viene bien hoy", lista(d.recuerdos)));
  }
  async function resumen(refrescar) {
    const tarjeta = $("resumen-hoy");
    const { ok, data } = await api("/api/briefing" + (refrescar ? "?refrescar=1" : ""));
    if (!ok || !data.fecha) { tarjeta.hidden = true; return; }
    if (!refrescar && Prefs.get("resumen_cerrado", "") === data.fecha) { tarjeta.hidden = true; return; }
    pintarResumen(data); tarjeta.hidden = false; tarjeta.dataset.fecha = data.fecha;
  }

  function activar(si) {
    clearInterval(temporizador); temporizador = null;
    if (!si) return;
    saludo(); estados(); resumen(false);
    temporizador = setInterval(() => { if (!document.hidden && !document.querySelector("dialog[open]")) estados(); }, 15000);
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
