"use strict";
// Centro de control: SHIELD-DNS, HEIMDALL, Sistema y Spotify.
const Control = (() => {
  let temporizador = null, temporizadorDirecto = null, finPausa = 0, relojPausa = null;

  function noConectado(cuerpo, msg, ayuda) {
    cuerpo.replaceChildren(
      el("div", { class: "no-conectado" },
        el("div", { class: "estado" }, el("span", { class: "punto" }), "No conectado"),
        el("p", { class: "muted" }, msg),
        ayuda ? el("p", { class: "muted" }, ayuda) : null));
  }
  function fallo(cuerpo, msg) {
    cuerpo.replaceChildren(el("div", { class: "estado" }, el("span", { class: "punto mal" }), "Sin respuesta"), el("p", { class: "muted" }, msg));
  }
  const cuerpoDe = (id) => $(id).querySelector(".cuerpo");

  // --- SHIELD-DNS ---
  async function shield() {
    const c = cuerpoDe("card-shield");
    const { data } = await api("/api/shield");
    if (!data.conectado) {
      if (data.error) fallo(c, data.mensaje);
      else noConectado(c, data.mensaje, "Después de editar .env ejecuta «docker compose up -d» (o vuelve a lanzar install.sh).");
      return;
    }
    finPausa = data.temporizador ? Date.now() + data.temporizador * 1000 : 0;
    const estado = el("div", { class: "estado" }, el("span", { class: "punto " + (data.bloqueo_activo ? "ok" : "aviso") }),
      data.bloqueo_activo ? "Bloqueo activo" : "Bloqueo en pausa", el("span", { class: "muted", id: "cuenta-pausa" }));
    const numero = (v, t) => el("div", { class: "numero" }, el("strong", null, v), el("span", { class: "muted" }, t));
    const top = el("ol", { class: "top-lista" });
    if (!data.top_bloqueados.length) top.append(el("li", { class: "muted" }, "Sin datos todavía."));
    for (const d of data.top_bloqueados) top.append(el("li", null, marquesina(el("span", { class: "dominio", tabIndex: 0 }), d.dominio), el("span", { class: "muted" }, fmtNum(d.cuenta))));
    const pausas = el("div", { class: "botones" },
      ...[5, 30, 60].map((m) => el("button", { type: "button", class: "fantasma", onclick: () => pausar(m) }, "Pausar " + m + " min")),
      el("button", { type: "button", class: "primario", onclick: reanudar, disabled: data.bloqueo_activo }, "Reanudar"));
    let listas = null;
    try { listas = (await api("/api/sistema/listas")).data; } catch (_) { /* SHIELD puede no estar disponible */ }
    c.replaceChildren(
      estado,
      el("div", { class: "numeros" }, numero(fmtNum(data.consultas), "consultas (24 h)"), numero(fmtNum(data.bloqueadas), "bloqueadas"), numero(data.porcentaje.toString().replace(".", ",") + " %", "bloqueo")),
      barra(data.porcentaje, 101, 101),
      el("h3", null, "Listas de bloqueo"), el("div", { class: "estado-listas" }, listas && listas.dominios ? fmtNum(listas.dominios) + " dominios" : "No disponible",
        el("button", { type: "button", class: "fantasma pequeno", onclick: actualizarListas }, "Actualizar listas")),
      el("h3", null, "Más bloqueados"), top, pausas,
      el("div", { class: "pie" }, el("span", { class: "muted" }, fmtNum(data.lista_negra) + " dominios en la lista"), enlaceExterno(enlacePanel("shield", data.panel), "Abrir panel Pi-hole")));
    cuentaAtras();
  }
  async function actualizarListas(e) {
    const b = e.currentTarget; b.disabled = true; b.textContent = "Actualizando…";
    const r = await api("/api/sistema/listas/actualizar", { method: "POST" });
    toast(r.ok ? "Listas actualizadas." : (r.data.error || "No se pudieron actualizar las listas."), r.ok ? "" : "mal");
    shield();
  }
  function cuentaAtras() {
    clearInterval(relojPausa);
    const pintar = () => {
      const e = $("cuenta-pausa"); if (!e) return;
      const s = Math.max(0, Math.round((finPausa - Date.now()) / 1000));
      e.textContent = finPausa && s ? " · se reanuda en " + Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0") : "";
    };
    pintar(); if (finPausa) relojPausa = setInterval(pintar, 1000);
  }
  async function pausar(m) {
    const r = await api("/api/shield/pause", { method: "POST", json: { minutos: m } });
    toast(r.ok ? "Bloqueador en pausa " + m + " min." : (r.data.error || "No se pudo pausar."), r.ok ? "" : "mal");
    shield();
  }
  async function reanudar() {
    const r = await api("/api/shield/resume", { method: "POST" });
    toast(r.ok ? "Bloqueador reanudado." : (r.data.error || "No se pudo reanudar."), r.ok ? "" : "mal");
    shield();
  }

  // --- HEIMDALL ---
  async function vpn() {
    const c = cuerpoDe("card-heimdall");
    const { data } = await api("/api/vpn/clients");
    if (!data.conectado) {
      if (data.error) fallo(c, data.mensaje);
      else noConectado(c, data.mensaje, "Usa el usuario y la contraseña del panel de HEIMDALL (WG_ADMIN_USER / WG_ADMIN_PASSWORD).");
      return;
    }
    const conectados = data.clientes.filter((x) => x.conectado).length;
    const lista = el("ul", { class: "dispositivos" });
    if (!data.clientes.length) lista.append(el("li", { class: "muted" }, "Aún no hay dispositivos."));
    for (const d of data.clientes) {
      const clase = !d.activo ? "mal" : d.conectado ? "ok" : "";
      lista.append(el("li", { class: "dispositivo" + (d.activo ? "" : " apagado") },
        el("span", { class: "punto " + clase, title: !d.activo ? "Desactivado" : d.conectado ? "Conectado" : "Sin conexión" }),
        el("div", { class: "disp-info" },
          el("strong", null, d.nombre), el("span", { class: "muted" }, (d.ip || "") + " · ↓ " + fmtBytes(d.recibido) + " ↑ " + fmtBytes(d.enviado))),
        el("div", { class: "disp-acc" },
          el("button", { type: "button", class: "fantasma pequeno", onclick: () => verQr(d) }, "QR"),
          el("button", { type: "button", class: "fantasma pequeno", onclick: () => alternar(d) }, d.activo ? "Desactivar" : "Activar"),
          el("button", { type: "button", class: "peligro pequeno", onclick: () => borrar(d), "aria-label": "Eliminar " + d.nombre }, "Eliminar"))));
    }
    c.replaceChildren(
      el("div", { class: "estado" }, el("span", { class: "punto ok" }), conectados + " de " + data.clientes.length + " conectados"),
      lista,
      el("div", { class: "pie" }, el("button", { type: "button", class: "primario", onclick: anadir }, "Añadir dispositivo"), enlaceExterno(enlacePanel("vpn", data.panel), "Abrir panel wg-easy")));
  }
  async function alternar(d) {
    const r = await api("/api/vpn/clients/" + d.id + "/" + (d.activo ? "disable" : "enable"), { method: "POST" });
    if (!r.ok) toast(r.data.error || "No se pudo cambiar.", "mal");
    vpn();
  }
  async function borrar(d) {
    if (!(await confirmar("Eliminar dispositivo", "«" + d.nombre + "» perderá el acceso a la VPN y su configuración dejará de funcionar.", "Eliminar"))) return;
    const r = await api("/api/vpn/clients/" + d.id, { method: "DELETE" });
    toast(r.ok ? "Dispositivo eliminado." : (r.data.error || "No se pudo eliminar."), r.ok ? "" : "mal");
    vpn();
  }
  function mostrarQr(id, nombre) {
    $("vpn-titulo").textContent = nombre;
    $("form-vpn").hidden = true; $("vpn-resultado").hidden = false;
    $("vpn-qr").src = "/api/vpn/clients/" + id + "/qrcode.svg?t=" + Date.now();
    $("vpn-conf").href = "/api/vpn/clients/" + id + "/config";
    const d = $("dlg-vpn"); if (!d.open) d.showModal();
  }
  function verQr(d) { mostrarQr(d.id, d.nombre); }
  function anadir() {
    $("vpn-titulo").textContent = "Añadir dispositivo";
    $("form-vpn").hidden = false; $("vpn-resultado").hidden = true; $("vpn-nombre").value = "";
    $("dlg-vpn").showModal(); $("vpn-nombre").focus();
  }
  function iniciarVpn() {
    $("form-vpn").addEventListener("submit", async (e) => {
      e.preventDefault();
      const nombre = $("vpn-nombre").value.trim();
      const btn = e.submitter; if (btn) btn.disabled = true;
      const r = await api("/api/vpn/clients", { method: "POST", json: { nombre } });
      if (btn) btn.disabled = false;
      if (!r.ok) { toast(r.data.error || "No se pudo crear el dispositivo.", "mal"); return; }
      mostrarQr(r.data.id, nombre); vpn();
    });
    $("dlg-vpn").addEventListener("click", (e) => { if (e.target.closest("[data-cerrar]")) $("dlg-vpn").close(); });
    $("dlg-vpn").addEventListener("close", () => { $("vpn-qr").removeAttribute("src"); });
  }

  // --- Sistema ---
  async function sistema() {
    return pintarSistema(cuerpoDe("card-sistema"), (await api("/api/system")));
  }
  function linea(datos, clave) {
    const svg = el("svg", { viewBox: "0 0 300 80", class: "grafica", role: "img", "aria-label": clave });
    const vals = datos.map((x) => Number(x[clave])).filter(Number.isFinite);
    if (!vals.length) return svg;
    const max = Math.max(...vals, 1), min = Math.min(...vals, 0), rango = max - min || 1;
    const puntos = vals.map((v, i) => `${(i / Math.max(vals.length - 1, 1)) * 300},${76 - ((v - min) / rango) * 68}`).join(" ");
    svg.append(el("polyline", { points: puntos, fill: "none", stroke: "currentColor", "stroke-width": "2" }));
    return svg;
  }
  async function directo() {
    const c = cuerpoDe("card-directo");
    const r = await api("/api/sistema/directo");
    if (!r.ok) { fallo(c, r.data.error || "No se pudo leer la telemetría."); return; }
    const d = r.data, s = d.sistema || {}, cs = d.contenedores || [];
    const tabla = el("table", { class: "tabla" }, el("thead", null, el("tr", null, el("th", null, "Contenedor"), el("th", null, "CPU"), el("th", null, "Memoria"), el("th", null, "Red"))), el("tbody"));
    for (const x of cs) tabla.lastChild.append(el("tr", null, el("td", null, x.nombre || "-"), el("td", null, Number(x.cpu || 0).toFixed(1) + " %"), el("td", null, x.memoria == null ? "-" : fmtBytes(x.memoria)), el("td", null, fmtBytes(x.red_rx || 0) + " / " + fmtBytes(x.red_tx || 0))));
    const hist = (await api("/api/sistema/historial?horas=1")).data.historial || [];
    c.replaceChildren(el("div", { class: "numeros" }, el("div", { class: "numero" }, el("strong", null, Number(s.cpu || 0).toFixed(1) + " %"), el("span", { class: "muted" }, "CPU")), el("div", { class: "numero" }, el("strong", null, s.temperatura == null ? "-" : s.temperatura + " °C"), el("span", { class: "muted" }, "Temperatura"))), el("div", { class: "graficas" }, linea(hist, "cpu"), linea(hist, "temperatura")), tabla, el("button", { type: "button", class: "peligro", onclick: reiniciar }, "Reiniciar la Raspberry"));
  }
  async function reiniciar() {
    if (!(await confirmar("Reiniciar la Raspberry", "La Raspberry se apagará en 15 segundos.", "Reiniciar"))) return;
    const r = await api("/api/sistema/reiniciar", { method: "POST", json: { confirmar: true } });
    if (!r.ok) { toast(r.data.error || "No se pudo programar el reinicio.", "mal"); return; }
    const boton = document.querySelector("#card-directo .peligro"), inicio = Date.now();
    const reloj = setInterval(async () => {
      const quedan = Math.max(0, 15 - Math.floor((Date.now() - inicio) / 1000));
      if (boton) boton.textContent = quedan ? "Reiniciando en " + quedan + " s" : "Volviendo…";
      if (!quedan) {
        try { const h = await fetch("/health", { cache: "no-store" }); if (h.ok) { clearInterval(reloj); location.reload(); } } catch (_) { /* la Pi está reiniciando */ }
      }
    }, 1000);
    toast("Reinicio programado. Volviendo…");
  }
  function pintarSistema(c, { ok, data }) {
    if (!ok) { fallo(c, "No se pudo leer el estado."); return; }
    const filas = [];
    const fila = (t, valor, b) => el("div", { class: "metrica" }, el("div", { class: "metrica-cab" }, el("span", { class: "muted" }, t), el("strong", null, valor)), b);
    if (data.temperatura != null) filas.push(fila("Temperatura CPU", data.temperatura.toString().replace(".", ",") + " °C", barra(data.temperatura / 85 * 100, 82, 94)));
    if (data.memoria) filas.push(fila("Memoria RAM", fmtBytes(data.memoria.usada) + " / " + fmtBytes(data.memoria.total), barra(data.memoria.porcentaje, 80, 92)));
    if (data.disco) filas.push(fila("Disco", fmtBytes(data.disco.usado) + " / " + fmtBytes(data.disco.total), barra(data.disco.porcentaje, 80, 92)));
    c.replaceChildren(...filas,
      el("div", { class: "pie dos" },
        el("span", { class: "muted" }, "Encendida " + data.uptime_texto),
        el("span", { class: "muted" }, data.carga ? "Carga " + data.carga.map((x) => x.toFixed(2).replace(".", ",")).join(" · ") : "")));
  }

  // --- Spotify ---
  async function spotify() {
    const c = $("spotify-cuerpo"), ctrl = $("spotify-ctrl");
    const { data: s } = await api("/api/spotify/status");
    c.replaceChildren(); ctrl.hidden = true;
    if (!s.configurado) {
      noConectado(c, "Spotify no está configurado.", "Mira Ajustes → Spotify para conectarlo (requiere cuenta Premium).");
    } else if (!s.conectado) {
      c.append(el("div", { class: "estado" }, el("span", { class: "punto aviso" }), "Sin conectar"), el("a", { href: "/spotify/login", class: "boton primario" }, "Conectar Spotify"));
    } else {
      ctrl.hidden = false;
      if (s.error) c.append(el("div", { class: "error" }, s.error));
      else if (s.ahora && s.ahora.titulo) c.append(el("div", { class: "ahora" }, (s.ahora.reproduciendo ? "▶ " : "⏸ ") + s.ahora.titulo), el("div", { class: "muted" }, s.ahora.artistas || ""));
      else c.append(el("div", { class: "muted" }, "Nada en reproducción."));
    }
  }
  function iniciarSpotify() {
    document.querySelectorAll("[data-sp]").forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true;
      const r = await api("/api/spotify/" + b.dataset.sp, { method: "POST" });
      if (!r.ok) toast(r.data.error || "Error de Spotify.", "mal");
      b.disabled = false; setTimeout(spotify, 800);
    }));
  }

  function actualizar() {
    const h = $("control-hora"); if (h) h.textContent = "Actualizado " + new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    return Promise.allSettled([shield(), vpn(), sistema(), directo(), ...(Sesion.funciones.spotify ? [spotify()] : [])]);
  }
  // Se refresca cada ~15 s solo mientras la vista está abierta y la pestaña visible.
  function activar(si) {
    clearInterval(temporizador); clearInterval(temporizadorDirecto); clearInterval(relojPausa); temporizador = temporizadorDirecto = null;
    if (!si) return;
    actualizar();
    temporizadorDirecto = setInterval(() => { if (!document.hidden && !document.querySelector("dialog[open]")) directo(); }, 5000);
    temporizador = setInterval(() => { if (!document.hidden && !document.querySelector("dialog[open]")) actualizar(); }, 15000);
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden && temporizador) actualizar(); });

  function iniciar() { iniciarVpn(); iniciarSpotify(); }
  return { iniciar, activar, anadir, mostrarQr, pintarSistema };
})();
