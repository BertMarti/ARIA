"use strict";
// Ajustes: cerebros, modelos, voz, contraseña, Spotify y Acerca de.
const Ajustes = (() => {
  let descargando = false;

  // --- Modelos ---
  async function modelos() {
    const { data: m } = await api("/api/models");
    $("modelo-activo").textContent = m.activo;
    const inst = $("modelos-instalados"), cur = $("modelos-curados");
    inst.replaceChildren(); cur.replaceChildren();
    if (!m.ollama) { inst.append(el("li", { class: "error" }, "Ollama no responde.")); return; }
    const nombres = new Set(m.instalados.map((x) => x.nombre));
    if (!m.instalados.length) inst.append(el("li", { class: "muted" }, "No hay ningún modelo instalado."));
    for (const x of m.instalados) {
      const activo = x.nombre === m.activo;
      inst.append(el("li", { class: "fila" },
        el("div", { class: "fila-info" }, el("strong", null, x.nombre), el("span", { class: "muted" }, fmtBytes(x.tamano))),
        activo ? el("span", { class: "pildora ok" }, "Activo")
          : el("div", { class: "fila-acc" },
              el("button", { type: "button", class: "primario pequeno", onclick: () => activar(x.nombre) }, "Usar"),
              el("button", { type: "button", class: "peligro pequeno", onclick: () => borrar(x.nombre) }, "Borrar"))));
    }
    if (!m.activo_instalado) inst.prepend(el("li", { class: "aviso-txt" }, "El modelo activo («" + m.activo + "») no está descargado."));
    for (const c of m.curados) {
      const esta = nombres.has(c.nombre);
      cur.append(el("li", { class: "fila" },
        el("div", { class: "fila-info" }, el("strong", null, c.nombre), el("span", { class: "muted" }, c.descripcion + " · " + c.tamano)),
        esta ? el("span", { class: "pildora" }, "Instalado")
          : el("button", { type: "button", class: "fantasma pequeno", disabled: descargando, onclick: () => descargar(c.nombre) }, "Descargar")));
    }
  }
  async function activar(nombre) {
    const r = await api("/api/models/activate", { method: "POST", json: { model: nombre } });
    toast(r.ok ? "Modelo activo: " + nombre : (r.data.error || "No se pudo cambiar."), r.ok ? "" : "mal");
    modelos();
  }
  async function borrar(nombre) {
    if (!(await confirmar("Borrar modelo", "Se eliminará «" + nombre + "» del disco. Podrás volver a descargarlo.", "Borrar"))) return;
    const r = await api("/api/models", { method: "DELETE", json: { model: nombre } });
    toast(r.ok ? "Modelo borrado." : (r.data.error || "No se pudo borrar."), r.ok ? "" : "mal");
    modelos();
  }
  async function descargar(nombre) {
    descargando = true; modelos();
    const zona = $("pull-zona"), bar = $("pull-bar"), est = $("pull-estado");
    zona.hidden = false; bar.style.width = "0%"; est.textContent = "Descargando " + nombre + "…";
    let ok = false;
    try {
      const r = await fetch("/api/models/pull", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model: nombre }) });
      if (r.status === 401) { location.href = "/login"; return; }
      for await (const ev of lineasNdjson(r)) {
        if (ev.type === "progreso") {
          est.textContent = nombre + ": " + ev.estado + (ev.total ? " (" + Math.round((ev.completado || 0) * 100 / ev.total) + " %)" : "");
          if (ev.total) bar.style.width = Math.round((ev.completado || 0) * 100 / ev.total) + "%";
        } else if (ev.type === "error") est.textContent = ev.text;
        else if (ev.type === "fin") ok = true;
      }
    } catch (_) { est.textContent = "Error durante la descarga."; }
    if (ok) toast("Modelo descargado: " + nombre);
    descargando = false; zona.hidden = !!ok; modelos();
  }

  // --- Cerebros ---
  const ESTADO_PUNTO = { configurado: "ok", sin_clave: "", espera: "aviso", sin_conexion: "aviso", clave_invalida: "mal" };
  async function cerebros() {
    const { ok, data } = await api("/api/brains");
    const ul = $("cerebros-lista");
    if (!ok) { ul.replaceChildren(el("li", { class: "error" }, "No se pudo leer la cadena de cerebros.")); return; }
    ul.replaceChildren();
    const lista = data.cerebros;
    const guardar = async (nuevo) => {
      const r = await api("/api/brains", { method: "POST", json: {
        orden: nuevo.map((c) => c.id), desactivados: nuevo.filter((c) => !c.activo).map((c) => c.id) } });
      if (!r.ok) toast(r.data.error || "No se pudo guardar.", "mal");
      cerebros(); Chat.refrescarCerebro();
    };
    lista.forEach((c, i) => {
      const mover = (d) => { const n = lista.slice(); [n[i], n[i + d]] = [n[i + d], n[i]]; guardar(n); };
      const tog = el("input", { type: "checkbox", checked: c.activo, disabled: c.bloqueado, "aria-label": "Activar " + c.nombre });
      tog.addEventListener("change", () => guardar(lista.map((x) => (x.id === c.id ? { ...x, activo: tog.checked } : x))));
      let detalle = c.detalle;
      if (c.estado === "sin_clave") detalle = "falta la clave: rellena " + c.clave_var + " en .env";
      else if (c.clave_var) detalle = "clave configurada ✔ · " + detalle;
      else if (c.id === "ollama_cloud" && c.estado === "clave_invalida") detalle = "sin sesión: ejecuta «docker exec -it aria-ollama ollama signin»";
      const res = el("span", { class: "muted cerebro-res", role: "status" });
      const probar = el("button", { type: "button", class: "fantasma pequeno" }, "Probar");
      probar.addEventListener("click", async () => {
        probar.disabled = true; res.className = "muted cerebro-res"; res.textContent = "probando…";
        const r = await api("/api/brains/test", { method: "POST", json: { id: c.id } });
        probar.disabled = false;
        if (r.ok && r.data.ok) { res.className = "ok-txt cerebro-res"; res.textContent = "OK en " + (r.data.ms / 1000).toFixed(1).replace(".", ",") + " s (primer token " + (r.data.primer_token_ms / 1000).toFixed(1).replace(".", ",") + " s)"; }
        else { res.className = "error cerebro-res"; res.textContent = r.data.error || "Falló la prueba."; }
        setTimeout(() => { cerebros(); Chat.refrescarCerebro(); }, 1500);
      });
      ul.append(el("li", { class: "fila" },
        el("div", { class: "fila-info" },
          el("strong", null, (i + 1) + ". " + c.nombre, c.primero ? el("span", { class: "pildora ok cerebro-primero" }, "en cabeza") : null),
          el("span", { class: "muted" }, c.modelo + (c.nube ? "" : " · modelo de Ajustes → Modelos")),
          el("span", { class: "estado" }, el("span", { class: "punto " + (ESTADO_PUNTO[c.estado] || "") }), detalle),
          res),
        el("div", { class: "fila-acc" },
          el("button", { type: "button", class: "fantasma pequeno", disabled: i === 0, "aria-label": "Subir " + c.nombre, onclick: () => mover(-1) }, "↑"),
          el("button", { type: "button", class: "fantasma pequeno", disabled: i === lista.length - 1, "aria-label": "Bajar " + c.nombre, onclick: () => mover(1) }, "↓"),
          el("label", { class: "interruptor" }, tog, el("span", null, c.bloqueado ? "Siempre" : "Activo")),
          probar)));
    });
  }

  // --- Voz ---
  const fmtVel = (v) => Number(v).toFixed(2).replace(/0$/, "").replace(".", ",") + "×";
  async function listarMics() {
    const sel = $("voz-mic");
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
    const elegido = Prefs.get("mic", "");
    const mics = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput" && d.deviceId && d.deviceId !== "default");
    sel.replaceChildren(el("option", { value: "" }, "Predeterminado del sistema"),
      ...mics.map((d, i) => el("option", { value: d.deviceId, selected: d.deviceId === elegido }, d.label || "Micrófono " + (i + 1))));
  }
  let prueba = null;
  async function probarMic() {
    if (prueba) { prueba(); return; }
    const b = $("voz-probar-mic"), zona = $("voz-nivel-zona"), barraNivel = $("voz-nivel");
    let stream;
    try { stream = await Voz.abrirMic(); } catch (e) { toast(Voz.errorMic(e), "mal"); return; }
    listarMics(); // con permiso ya se ven los nombres
    const c = new AudioContext(), an = c.createAnalyser(); an.fftSize = 1024;
    c.createMediaStreamSource(stream).connect(an);
    const datos = new Float32Array(an.fftSize);
    let max = 0, vivo = true;
    zona.hidden = false; b.textContent = "Parar prueba";
    const pintar = () => {
      if (!vivo) return;
      an.getFloatTimeDomainData(datos);
      let s = 0; for (const v of datos) s += v * v;
      const nivel = Math.min(100, Math.sqrt(s / datos.length) * 400);
      max = Math.max(max, nivel);
      barraNivel.style.width = nivel + "%";
      requestAnimationFrame(pintar);
    };
    pintar();
    const fin = () => {
      vivo = false; prueba = null; clearTimeout(t);
      stream.getTracks().forEach((x) => x.stop()); c.close().catch(() => {});
      b.textContent = "Probar micrófono"; barraNivel.style.width = "0%";
      $("voz-nivel-txt").textContent = max > 8 ? "El micrófono funciona." : "Apenas se oye nada: revisa el micrófono elegido.";
    };
    const t = setTimeout(fin, 6000);
    prueba = fin;
  }
  async function estadoVoz() {
    const { ok, data } = await api("/api/voz/estado");
    if (!ok) return;
    const stt = data.groq ? (data.local ? "Groq (local de respaldo)" : "Groq (el respaldo local no responde)") : (data.local ? "local en la Raspberry" : "no disponible");
    $("voz-estado").textContent = "Transcripción: " + stt + " · Voz de ARIA: " + (data.local ? "Piper en la Raspberry" : "la del navegador (Piper no responde)") + ".";
  }
  function voz() {
    const t = $("tts-activar");
    t.checked = Prefs.get("tts", "0") === "1";
    t.addEventListener("change", () => {
      Prefs.set("tts", t.checked ? "1" : "0");
      if (t.checked) Voz.hablar("Leeré las respuestas en voz alta."); else Voz.parar();
    });
    const vel = $("voz-vel");
    vel.value = Prefs.get("voz_vel", "1"); $("voz-vel-txt").textContent = fmtVel(vel.value);
    vel.addEventListener("input", () => { Prefs.set("voz_vel", vel.value); $("voz-vel-txt").textContent = fmtVel(vel.value); });
    $("voz-probar").addEventListener("click", () => Voz.hablar("Hola, soy ARIA. Así sueno a esta velocidad."));
    $("voz-mic").addEventListener("change", (e) => Prefs.set("mic", e.target.value));
    $("voz-probar-mic").addEventListener("click", probarMic);
    const manos = $("voz-manos");
    manos.addEventListener("change", () => (manos.checked ? ManosLibres.iniciar() : ManosLibres.parar()));
    ManosLibres.alCambiar((on) => { manos.checked = on; });
    if (!Voz.micDisponible()) {
      for (const id of ["voz-mic", "voz-probar-mic", "voz-manos"]) $(id).disabled = true;
      $("voz-estado").textContent = "El micrófono solo funciona por HTTPS.";
    }
  }

  // --- Contraseña ---
  function contrasena() {
    $("form-pass").addEventListener("submit", async (e) => {
      e.preventDefault();
      const msg = $("pass-msg"); msg.className = "muted"; msg.textContent = "";
      const j = { actual: $("pass-actual").value, nueva: $("pass-nueva").value, repetida: $("pass-repetida").value };
      if (j.nueva.length < 10) { msg.className = "error"; msg.textContent = "La contraseña nueva debe tener al menos 10 caracteres."; return; }
      if (j.nueva !== j.repetida) { msg.className = "error"; msg.textContent = "Las contraseñas nuevas no coinciden."; return; }
      const r = await api("/api/password", { method: "POST", json: j });
      if (r.ok) { Sesion.tienePassword = true; $("pass-actual").required = true; $("pass-actual-et").hidden = false; $("form-pass").reset(); msg.className = "ok-txt"; msg.textContent = "Contraseña cambiada. Las demás sesiones se han cerrado."; }
      else { msg.className = "error"; msg.textContent = r.data.error || "No se pudo cambiar la contraseña."; }
    });
  }

  // --- Spotify ---
  async function spotify() {
    const c = $("ajustes-spotify").querySelector(".cuerpo");
    const { data: s } = await api("/api/spotify/status");
    c.replaceChildren();
    if (!s.configurado) {
      c.append(el("div", { class: "estado" }, el("span", { class: "punto" }), "No configurado"),
        el("p", { class: "muted" }, "Crea una app en developer.spotify.com/dashboard, añade la Redirect URI " + s.redirect_uri + " y rellena SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET en .env (después: docker compose up -d). Requiere Spotify Premium."));
    } else if (!s.conectado) {
      c.append(el("div", { class: "estado" }, el("span", { class: "punto aviso" }), "Configurado, sin conectar"), el("a", { href: "/spotify/login", class: "boton primario" }, "Conectar Spotify"));
    } else {
      c.append(el("div", { class: "estado" }, el("span", { class: "punto ok" }), "Conectado"), el("a", { href: "/spotify/login", class: "boton fantasma" }, "Volver a conectar"));
    }
  }

  async function acerca() {
    const { data } = await api("/api/info");
    $("acerca-cuerpo").replaceChildren(
      el("div", null, el("strong", null, "ARIA " + (data.version || "")), " — centro de control del laboratorio doméstico."),
      el("div", null, "Modelo local: ", el("code", null, data.modelo || "?")),
      el("div", null, "Cerebro en cabeza: ", el("code", null, (data.cerebro && data.cerebro.etiqueta) || "?")),
      el("div", null, "El cerebro local no sale de casa; los de la nube (Ollama Cloud, Groq, Gemini) reciben tus mensajes para responder."));
  }

  function activar() {
    pintarSecciones(); dosPasos();
    estadoVoz(); listarMics().catch(() => {});
    if (Sesion.esAdmin) { cerebros(); modelos(); if (Sesion.funciones.spotify) spotify(); acerca(); }
    if (!Sesion.tienePassword) { $("pass-actual").required = false; $("pass-actual-et").hidden = true; }
  }
  // --- Verificación en dos pasos ---
  async function dosPasos() {
    const c = $("dosp-cuerpo"), r = await api("/api/2fa");
    if (!r.ok) { c.textContent = "No disponible."; return; }
    if (r.data.activa) {
      const cod = el("input", { inputMode: "numeric", maxLength: 16, placeholder: "Código o código de recuperación", autocomplete: "one-time-code" });
      const b = el("button", { type: "button", class: "peligro pequeno" }, "Desactivar");
      b.addEventListener("click", async () => {
        const x = await api("/api/2fa/desactivar", { method: "POST", json: { codigo: cod.value } });
        toast(x.ok ? "Verificación en dos pasos desactivada." : x.data.error, x.ok ? "" : "mal"); if (x.ok) dosPasos();
      });
      c.replaceChildren(el("p", { class: "dosp-ok" }, "✓ Activada"), el("p", { class: "muted pequeno-txt" }, `Te quedan ${r.data.recuperacion} códigos de recuperación.`),
        el("label", null, "Para desactivarla, escribe un código actual", cod), el("div", { class: "botones" }, b));
      return;
    }
    const b = el("button", { type: "button", class: "primario" }, "Activar");
    b.addEventListener("click", preparar2fa);
    c.replaceChildren(el("p", { class: "muted" }, "Desactivada."), el("div", { class: "botones" }, b));
  }
  async function preparar2fa() {
    const c = $("dosp-cuerpo"), r = await api("/api/2fa/preparar", { method: "POST" });
    if (!r.ok) { toast(r.data.error || "No se pudo preparar.", "mal"); return; }
    const cod = el("input", { inputMode: "numeric", maxLength: 8, placeholder: "123456", autocomplete: "one-time-code", class: "dosp-codigo" });
    const ok = el("button", { type: "submit", class: "primario" }, "Confirmar y activar");
    const f = el("form", { class: "dosp-form" }, el("label", null, "3. Escribe el código que muestra la app", cod), el("div", { class: "botones" }, ok));
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const x = await api("/api/2fa/activar", { method: "POST", json: { codigo: cod.value } });
      if (!x.ok) { toast(x.data.error, "mal"); return; }
      c.replaceChildren(el("p", { class: "dosp-ok" }, "✓ Activada"),
        el("p", null, "Guarda estos códigos de recuperación en un sitio seguro. Cada uno sirve una vez si pierdes el móvil. No se volverán a mostrar."),
        el("ol", { class: "dosp-rec" }, ...x.data.recuperacion.map((k) => el("li", null, k))),
        (() => { const b = el("button", { type: "button", class: "fantasma pequeno" }, "Copiar códigos"); b.addEventListener("click", () => navigator.clipboard?.writeText(x.data.recuperacion.join("\n")).then(() => toast("Códigos copiados."))); return b; })(),
        (() => { const b = el("button", { type: "button", class: "primario pequeno" }, "Ya los he guardado"); b.addEventListener("click", dosPasos); return b; })());
    });
    c.replaceChildren(el("p", null, "1. Abre tu app de autenticación y añade una cuenta escaneando este código:"),
      el("img", { src: r.data.qr, alt: "Código QR para la app de autenticación", class: "dosp-qr", width: 200, height: 200 }),
      el("p", { class: "muted pequeno-txt" }, "2. ¿No puedes escanearlo? Escribe esta clave a mano: ", el("code", { class: "dosp-clave" }, r.data.secreto)), f);
    cod.focus();
  }

  // --- Secciones: menú lateral (pestañas en el móvil) y buscador; cada tarjeta pertenece a una sección ---
  const SECCIONES = [
    { id: "general", nombre: "General", desc: "Voz, contraseña, verificación en dos pasos y versión.", ico: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM3 12h2M19 12h2M12 3v2M12 19v2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4", tarjetas: ["ajustes-voz", "ajustes-pass", "ajustes-2fa", "ajustes-acerca"] },
    { id: "avisos", nombre: "Avisos", desc: "Campana, Telegram, notificaciones, resumen diario y recordatorios.", ico: "M6 16V11a6 6 0 1 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0", tarjetas: ["ajustes-avisos", "ajustes-recordatorios"] },
    { id: "automatizar", nombre: "Automatización", desc: "Rutinas programadas y reglas «si pasa esto, haz aquello».", ico: "M13 3 4 14h7l-1 7 9-11h-7z", tarjetas: ["ajustes-rutinas", "ajustes-automatizaciones"] },
    { id: "memoria", nombre: "Memoria", desc: "Lo que ARIA recuerda de ti, tu diario y tus proyectos.", ico: "M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 1V4.5A3 3 0 0 0 9 4zM15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-6 1", tarjetas: ["ajustes-memoria"] },
    { id: "ia", nombre: "Inteligencia artificial", desc: "Cerebros en la nube y modelos locales.", ico: "M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4", tarjetas: ["ajustes-cerebros", "ajustes-modelos"] },
    { id: "usuarios", nombre: "Usuarios", desc: "Quién puede entrar y con qué permisos.", ico: "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21a7 7 0 0 1 14 0M17 11a3 3 0 1 0 0-6M22 21a5 5 0 0 0-5-5", tarjetas: ["ajustes-usuarios"] },
    { id: "apps", nombre: "Aplicaciones", desc: "Módulos, integraciones y certificado HTTPS.", ico: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z", tarjetas: ["ajustes-modulos", "ajustes-spotify", "ajustes-certificado"] },
  ];
  let seccion = Prefs.get("ajustes_seccion", "general");
  const visibleRol = (id) => { const t = $(id); return t && (!t.classList.contains("solo-admin") || Sesion.esAdmin); };
  function icoSec(d) {
    const NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg"), p = document.createElementNS(NS, "path");
    svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("aria-hidden", "true"); svg.setAttribute("class", "ajustes-ico"); p.setAttribute("d", d); svg.append(p); return svg;
  }
  function pintarSecciones() {
    const busca = $("ajustes-buscar").value.trim().toLowerCase(), secs = SECCIONES.filter((x) => x.tarjetas.some(visibleRol));
    if (!secs.some((x) => x.id === seccion)) seccion = secs[0]?.id;
    $("ajustes-nav").replaceChildren(...secs.map((x) => {
      const b = el("button", { type: "button", class: "ajustes-sec" + (x.id === seccion && !busca ? " activo" : "") }, icoSec(x.ico), el("span", null, x.nombre));
      b.setAttribute("aria-current", x.id === seccion && !busca ? "page" : "false");
      b.addEventListener("click", () => { seccion = x.id; Prefs.set("ajustes_seccion", x.id); $("ajustes-buscar").value = ""; pintarSecciones(); $("ajustes-cont").scrollIntoView({ block: "nearest" }); });
      return b;
    }));
    const navAct = $("ajustes-nav").querySelector(".activo");
    if (navAct) $("ajustes-nav").scrollLeft = navAct.offsetLeft - 8;   // en el móvil, la pestaña elegida queda a la vista
    const actual = SECCIONES.find((x) => x.id === seccion);
    $("ajustes-desc").textContent = busca ? "Resultados de «" + busca + "»" : actual ? actual.desc : "";
    let alguna = false;
    for (const x of SECCIONES) for (const id of x.tarjetas) {
      const t = $(id); if (!t) continue;
      const ok = busca ? t.textContent.toLowerCase().includes(busca) : x.id === seccion;
      t.classList.toggle("fuera-seccion", !ok);
      if (ok && visibleRol(id) && !t.hidden) alguna = true;
    }
    $("ajustes-vacio").hidden = alguna;
  }
  function iniciar() {
    voz(); contrasena();
    $("ajustes-buscar").addEventListener("input", pintarSecciones);
    pintarSecciones();
  }
  return { iniciar, activar, modelos };
})();
