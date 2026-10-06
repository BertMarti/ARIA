"use strict";
// Centro de control: SHIELD-DNS, HEIMDALL, Sistema y Spotify.
const Control = (() => {
  let temporizador = null, finPausa = 0, relojPausa = null;

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
    for (const d of data.top_bloqueados) top.append(el("li", null, el("span", { class: "dominio", title: d.dominio }, d.dominio), el("span", { class: "muted" }, fmtNum(d.cuenta))));
    const pausas = el("div", { class: "botones" },
      ...[5, 30, 60].map((m) => el("button", { type: "button", class: "fantasma", onclick: () => pausar(m) }, "Pausar " + m + " min")),
      el("button", { type: "button", class: "primario", onclick: reanudar, disabled: data.bloqueo_activo }, "Reanudar"));
    c.replaceChildren(
      estado,
      el("div", { class: "numeros" }, numero(fmtNum(data.consultas), "consultas (24 h)"), numero(fmtNum(data.bloqueadas), "bloqueadas"), numero(data.porcentaje.toString().replace(".", ",") + " %", "bloqueo")),
      barra(data.porcentaje, 101, 101),
      el("h3", null, "Más bloqueados"), top, pausas,
      el("div", { class: "pie" }, el("span", { class: "muted" }, fmtNum(data.lista_negra) + " dominios en la lista"), enlaceExterno(data.panel, "Abrir panel Pi-hole")));
    cuentaAtras();
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
      el("div", { class: "pie" }, el("button", { type: "button", class: "primario", onclick: anadir }, "Añadir dispositivo"), enlaceExterno(data.panel, "Abrir panel wg-easy")));
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
    const c = cuerpoDe("card-sistema");
    const { ok, data } = await api("/api/system");
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
    return Promise.allSettled([shield(), vpn(), sistema(), spotify()]);
  }
  // Se refresca cada ~15 s solo mientras la vista está abierta y la pestaña visible.
  function activar(si) {
    clearInterval(temporizador); clearInterval(relojPausa); temporizador = null;
    if (!si) return;
    actualizar();
    temporizador = setInterval(() => { if (!document.hidden && !document.querySelector("dialog[open]")) actualizar(); }, 15000);
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden && temporizador) actualizar(); });

  function iniciar() { iniciarVpn(); iniciarSpotify(); }
  return { iniciar, activar };
})();
