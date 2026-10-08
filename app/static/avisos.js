"use strict";
// Avisos: campana con los avisos sin leer, Ajustes → Avisos (Telegram, notificaciones push, tipos,
// horas de silencio, resumen de buenos días) y Recordatorios. Todo el texto entra con textContent.
const Avisos = (() => {
  const SEV = { grave: "Importante", aviso: "Aviso", info: "Info" };
  const VISTAS_OK = ["inicio", "chat", "finanzas", "red", "seguridad", "control", "ajustes", "hud", "mapa", "agenda", "informacion"];
  let estado = null; // respuesta de /api/avisos/ajustes

  const hace = (ts) => {
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 60) return "ahora";
    if (s < 3600) return "hace " + Math.floor(s / 60) + " min";
    if (s < 86400) return "hace " + Math.floor(s / 3600) + " h";
    return new Date(ts * 1000).toLocaleDateString("es-ES", { day: "numeric", month: "short" });
  };
  const msg = (id, t, malo) => { const m = $(id); m.className = malo ? "error" : "muted"; m.textContent = t || ""; };

  // --- Campana ---------------------------------------------------------------------------------------
  async function refrescarCampana() {
    const { ok, data } = await api("/api/avisos");
    if (!ok) return;
    const n = data.no_leidos || 0, num = $("campana-num");
    num.hidden = n === 0;
    num.textContent = n > 99 ? "99+" : String(n);
    $("campana").setAttribute("aria-label", n ? `Avisos (${n} sin leer)` : "Avisos");
    const ul = $("avisos-lista");
    ul.replaceChildren();
    if (!data.avisos.length) ul.append(el("li", { class: "muted avisos-vacio" }, "No hay avisos."));
    for (const a of data.avisos) {
      const li = el("li", { class: "av-item sev-" + a.severidad + (a.leido ? " leido" : "") },
        el("div", { class: "av-item-cab" }, el("span", { class: "av-item-sev" }, SEV[a.severidad] || "Aviso"),
          el("span", { class: "muted pequeno-txt" }, hace(a.creado))),
        el("p", { class: "av-item-txt" }, a.texto));
      const acc = el("div", { class: "av-item-acc" });
      if (a.enlace && VISTAS_OK.includes(a.enlace)) {
        acc.append(el("a", { href: "#" + a.enlace, class: "pequeno-txt", onclick: () => { leer(a); cerrar(); } }, "Ver"));
      }
      if (!a.leido) acc.append(el("button", { type: "button", class: "fantasma pequeno", onclick: () => leer(a) }, "Marcar como leído"));
      li.append(acc);
      ul.append(li);
    }
  }
  async function leer(a) {
    if (a.leido) return;
    await api(`/api/avisos/${a.id}/leido`, { method: "POST" });
    refrescarCampana();
  }
  function abrir() { $("avisos-panel").hidden = false; $("campana").setAttribute("aria-expanded", "true"); refrescarCampana(); }
  function cerrar() { $("avisos-panel").hidden = true; $("campana").setAttribute("aria-expanded", "false"); }

  // --- Ajustes: guardar --------------------------------------------------------------------------------
  function recoger() {
    const a = structuredClone(estado.ajustes);
    document.querySelectorAll("#av-tipos input[data-tipo]").forEach((c) => { a.tipos[c.dataset.tipo] = c.checked; });
    a.silencio = { activo: $("av-silencio").checked, desde: $("av-desde").value || "23:00", hasta: $("av-hasta").value || "08:00" };
    a.briefing = { activo: $("av-briefing").checked, hora: $("av-briefing-hora").value || "08:00", canal: $("av-briefing-canal").value };
    a.informe = { activo: $("av-informe").checked, dia: Number($("av-informe-dia").value), hora: $("av-informe-hora").value || "20:00", canal: $("av-informe-canal").value };
    const tgc = $("av-canal-telegram"), pc = $("av-canal-push"), vz = $("av-voz");
    if (tgc) a.canales.telegram = tgc.checked;
    if (pc) a.canales.push = pc.checked;
    if (vz) a.voz_telegram = vz.checked;
    return a;
  }
  async function guardar() {
    const x = await api("/api/avisos/ajustes", { method: "POST", json: recoger() });
    if (!x.ok) { msg("av-msg", x.data.error || "No se pudo guardar.", true); return; }
    estado.ajustes = x.data.ajustes;
    msg("av-msg", "Guardado.");
  }

  // --- Telegram ----------------------------------------------------------------------------------------
  function pintarTelegram() {
    const z = $("tg-zona"), t = estado.telegram;
    z.className = "";
    z.replaceChildren();
    if (!t.configurado) {
      z.append(el("p", { class: "muted" }, "El bot de Telegram aún no está creado. Para activarlo (lo hace el administrador):"),
        el("ol", { class: "muted pasos" },
          el("li", null, "En Telegram, habla con @BotFather y envía /newbot (nombre: ARIA; usuario: el que quieras, acabado en «bot»)."),
          el("li", null, "Copia el token que te da y ponlo en el archivo .env de ARIA: TELEGRAM_BOT_TOKEN=…"),
          el("li", null, "Reinicia ARIA (docker compose up -d) y comprueba el token: docker compose exec app python -m aria.telegram --probar"),
          el("li", null, "Vuelve aquí y pulsa «Vincular Telegram».")));
      return;
    }
    z.append(el("p", { class: "muted" }, "Bot: ", t.bot ? el("strong", null, "@" + t.bot) : "sin conexión con Telegram"));
    const ul = el("ul", { class: "filas" });
    if (!t.chats.length) ul.append(el("li", { class: "muted" }, "Ningún chat vinculado todavía."));
    for (const c of t.chats) {
      ul.append(el("li", { class: "fila" },
        el("div", { class: "fila-info" }, el("span", null, c.nombre || "Chat " + c.chat_id),
          el("span", { class: "muted pequeno-txt" }, "Vinculado el " + new Date(c.vinculado * 1000).toLocaleDateString("es-ES"))),
        el("div", { class: "fila-acc" }, el("button", { type: "button", class: "peligro pequeno", onclick: () => desvincular(c) }, "Desvincular"))));
    }
    const codigo = el("div", { id: "tg-codigo", class: "tg-codigo", hidden: true });
    z.append(ul, el("div", { class: "botones" }, el("button", { type: "button", class: "primario", onclick: vincular }, "Vincular Telegram")), codigo,
      interruptor("av-canal-telegram", "Enviarme los avisos por Telegram", estado.ajustes.canales.telegram),
      interruptor("av-voz", "Responder también con voz a mis notas de voz", estado.ajustes.voz_telegram));
  }
  async function vincular() {
    const x = await api("/api/telegram/vincular", { method: "POST" });
    const c = $("tg-codigo");
    c.hidden = false;
    if (!x.ok) { c.replaceChildren(el("p", { class: "error" }, x.data.error || "No se pudo crear el código.")); return; }
    const hasta = new Date(x.data.expira * 1000).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
    c.replaceChildren(
      el("p", null, "Tu código: ", el("strong", { class: "codigo-grande" }, x.data.codigo), el("span", { class: "muted" }, " (caduca a las " + hasta + ", un solo uso)")),
      el("p", null, enlaceExterno(x.data.enlace, "Abrir Telegram y vincular")),
      el("p", { class: "muted pequeno-txt" }, "O busca @" + x.data.bot + " en Telegram y envíale: /start " + x.data.codigo + ". Luego recarga esta página."));
  }
  async function desvincular(c) {
    if (!(await confirmar("Desvincular Telegram", "Ese chat dejará de recibir avisos y de hablar con ARIA.", "Desvincular"))) return;
    const x = await api("/api/telegram/chats/" + c.chat_id, { method: "DELETE" });
    if (!x.ok) { msg("av-msg", x.data.error || "No se pudo desvincular.", true); return; }
    cargar();
  }
  function interruptor(id, texto, marcado) {
    const i = el("input", { type: "checkbox", id, checked: !!marcado });
    i.addEventListener("change", guardar);
    return el("label", { class: "interruptor" }, i, el("span", null, texto));
  }

  // --- Push --------------------------------------------------------------------------------------------
  const b64aBytes = (s) => {
    const b = atob((s + "=".repeat((4 - (s.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(b, (c) => c.charCodeAt(0));
  };
  const pushPosible = () => window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  async function registrarSW() {
    if (!pushPosible()) return null;
    try { return await navigator.serviceWorker.register("/sw.js", { scope: "/" }); } catch (_) { return null; }
  }
  function nombreDispositivo() {
    const ua = navigator.userAgent;
    const so = /iPhone|iPad/.test(ua) ? "iPhone/iPad" : /Android/.test(ua) ? "Android" : /Mac/.test(ua) ? "Mac" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "Dispositivo";
    const nav = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "";
    return (so + (nav ? " · " + nav : "")).slice(0, 40);
  }
  function pintarPush() {
    const z = $("push-zona"), p = estado.push;
    z.className = "";
    z.replaceChildren();
    if (p.url_publica) $("push-url").textContent = p.url_publica;
    const nombre = el("input", { id: "push-nombre", maxLength: 40, value: nombreDispositivo(), ariaLabel: "Nombre de este dispositivo" });
    const activar = el("button", { type: "button", class: "primario", onclick: () => suscribir(nombre.value) }, "Activar notificaciones en este dispositivo");
    if (!pushPosible()) {
      activar.disabled = true;
      z.append(el("p", { class: "muted" }, window.isSecureContext
        ? "Este navegador no admite notificaciones push (en iPhone, abre ARIA desde la pantalla de inicio)."
        : "Aquí no se pueden activar: entra por la dirección pública con certificado válido."));
    }
    const ul = el("ul", { class: "filas" });
    if (!p.dispositivos.length) ul.append(el("li", { class: "muted" }, "Ningún dispositivo suscrito."));
    for (const d of p.dispositivos) {
      ul.append(el("li", { class: "fila" },
        el("div", { class: "fila-info" }, el("span", null, d.nombre),
          el("span", { class: "muted pequeno-txt" }, "Desde el " + new Date(d.creado * 1000).toLocaleDateString("es-ES") + (d.ultimo_envio ? " · último aviso " + hace(d.ultimo_envio) : ""))),
        el("div", { class: "fila-acc" }, el("button", { type: "button", class: "peligro pequeno", onclick: () => quitar(d) }, "Quitar"))));
    }
    z.append(el("div", { class: "fila-form" }, nombre, activar), ul,
      el("div", { class: "botones" }, el("button", { type: "button", class: "fantasma pequeno", disabled: !p.dispositivos.length, onclick: probarPush }, "Enviar notificación de prueba")),
      interruptor("av-canal-push", "Enviarme los avisos como notificación", estado.ajustes.canales.push));
  }
  async function suscribir(nombre) {
    try {
      const permiso = await Notification.requestPermission();
      if (permiso !== "granted") { msg("av-msg", "Has bloqueado las notificaciones para ARIA en este navegador.", true); return; }
      const reg = await registrarSW();
      if (!reg) { msg("av-msg", "No se pudo instalar el service worker (¿certificado válido?).", true); return; }
      await navigator.serviceWorker.ready;
      let sub = await reg.pushManager.getSubscription();
      if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64aBytes(estado.push.clave) });
      const x = await api("/api/push/suscripciones", { method: "POST", json: { suscripcion: sub.toJSON(), nombre } });
      if (!x.ok) { msg("av-msg", x.data.error || "No se pudo guardar la suscripción.", true); return; }
      msg("av-msg", "Notificaciones activadas en este dispositivo.");
      cargar();
    } catch (e) {
      msg("av-msg", "No se pudieron activar las notificaciones: " + (e && e.message ? e.message : e), true);
    }
  }
  async function quitar(d) {
    const x = await api("/api/push/suscripciones/" + d.id, { method: "DELETE" });
    if (!x.ok) { msg("av-msg", x.data.error || "No se pudo quitar.", true); return; }
    cargar();
  }
  async function probarPush() {
    const x = await api("/api/push/prueba", { method: "POST" });
    if (!x.ok) { msg("av-msg", x.data.error || "No se pudo enviar.", true); return; }
    msg("av-msg", x.data.enviados ? `Enviada a ${x.data.enviados} dispositivo(s).` : "No llegó a ningún dispositivo." + (x.data.borrados ? " Se quitaron suscripciones caducadas." : ""), !x.data.enviados);
    if (x.data.borrados) cargar();
  }

  // --- Recordatorios ---------------------------------------------------------------------------------------
  async function cargarRecordatorios() {
    const { ok, data } = await api("/api/recordatorios");
    const ul = $("rec-lista");
    if (!ok) { ul.replaceChildren(el("li", { class: "error" }, "No se pudieron leer los recordatorios.")); return; }
    ul.replaceChildren();
    if (!data.recordatorios.length) ul.append(el("li", { class: "muted" }, "No tienes recordatorios pendientes."));
    for (const r of data.recordatorios) {
      ul.append(el("li", { class: "fila" },
        el("div", { class: "fila-info" }, el("span", null, r.texto), el("span", { class: "muted pequeno-txt" }, r.descripcion)),
        el("div", { class: "fila-acc" }, el("button", { type: "button", class: "peligro pequeno", onclick: () => borrarRec(r) }, "Borrar"))));
    }
  }
  async function borrarRec(r) {
    const x = await api("/api/recordatorios/" + r.id, { method: "DELETE" });
    if (!x.ok) { msg("rec-msg", x.data.error || "No se pudo borrar.", true); return; }
    cargarRecordatorios();
  }

  // --- Carga de Ajustes → Avisos ---------------------------------------------------------------------------
  async function cargar() {
    const { ok, data } = await api("/api/avisos/ajustes");
    if (!ok) { $("tg-zona").textContent = "No se pudieron leer los ajustes de avisos."; return; }
    estado = data;
    const a = data.ajustes, tipos = $("av-tipos");
    tipos.replaceChildren();
    if (!data.tipos.length) tipos.append(el("p", { class: "muted" }, "Recibirás tus recordatorios y el resumen de buenos días."));
    for (const t of data.tipos) {
      const i = el("input", { type: "checkbox", checked: !!a.tipos[t.id], dataset: { tipo: t.id } });
      i.addEventListener("change", guardar);
      tipos.append(el("label", { class: "interruptor" }, i, el("span", null, t.nombre)));
    }
    $("av-silencio").checked = a.silencio.activo; $("av-desde").value = a.silencio.desde; $("av-hasta").value = a.silencio.hasta;
    $("av-briefing").checked = a.briefing.activo; $("av-briefing-hora").value = a.briefing.hora; $("av-briefing-canal").value = a.briefing.canal;
    const informe = a.informe || { activo: true, dia: 6, hora: "20:00", canal: "telegram" };
    $("av-informe").checked = informe.activo; $("av-informe-dia").value = String(informe.dia); $("av-informe-hora").value = informe.hora; $("av-informe-canal").value = informe.canal;
    pintarTelegram();
    pintarPush();
    cargarRecordatorios();
  }

  function iniciar() {
    $("campana").addEventListener("click", () => ($("avisos-panel").hidden ? abrir() : cerrar()));
    $("avisos-todos").addEventListener("click", async () => { await api("/api/avisos/leidos", { method: "POST" }); refrescarCampana(); });
    $("avisos-ajustes").addEventListener("click", cerrar);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("avisos-panel").hidden) cerrar(); });
    document.addEventListener("click", (e) => { if (!$("avisos-panel").hidden && !e.target.closest(".campana-zona")) cerrar(); });
    for (const id of ["av-silencio", "av-desde", "av-hasta", "av-briefing", "av-briefing-hora", "av-briefing-canal", "av-informe", "av-informe-dia", "av-informe-hora", "av-informe-canal"]) $(id).addEventListener("change", guardar);
    $("av-probar").addEventListener("click", async () => {
      const x = await api("/api/avisos/probar", { method: "POST" });
      if (!x.ok) { msg("av-msg", x.data.error || "No se pudo probar.", true); return; }
      const c = x.data.canales.map((n) => ({ telegram: "Telegram", push: "notificación" }[n] || n));
      msg("av-msg", "Aviso de prueba en la campana" + (c.length ? " y por " + c.join(" y ") : " (ningún otro canal activo)") + ".");
      refrescarCampana();
    });
    $("form-rec").addEventListener("submit", async (e) => {
      e.preventDefault();
      const x = await api("/api/recordatorios", { method: "POST", json: { texto: $("rec-texto").value, cuando: $("rec-cuando").value, repetir: $("rec-repetir").value } });
      if (!x.ok) { msg("rec-msg", x.data.error || "No se pudo crear.", true); return; }
      $("rec-texto").value = ""; msg("rec-msg", "Te lo recordaré " + x.data.recordatorio.descripcion + ".");
      cargarRecordatorios();
    });
    refrescarCampana();
    setInterval(() => { if (!document.hidden) refrescarCampana(); }, 60000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) refrescarCampana(); });
    // Mantiene el service worker al día si ya hay notificaciones activadas en este navegador.
    if (pushPosible() && Notification.permission === "granted") registrarSW();
  }
  return { iniciar, activar: cargar, refrescar: refrescarCampana };
})();
