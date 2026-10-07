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
  function voz() {
    const t = $("tts-activar");
    if (!("speechSynthesis" in window)) { t.disabled = true; $("tts-nota").textContent = "Tu navegador no admite síntesis de voz."; return; }
    t.checked = Prefs.get("tts", "0") === "1";
    t.addEventListener("change", () => {
      Prefs.set("tts", t.checked ? "1" : "0");
      if (t.checked) { const u = new SpeechSynthesisUtterance("Voz activada."); u.lang = "es-ES"; speechSynthesis.speak(u); }
      else speechSynthesis.cancel();
    });
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
      if (r.ok) { $("form-pass").reset(); msg.className = "ok-txt"; msg.textContent = "Contraseña cambiada. Las demás sesiones se han cerrado."; }
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

  function activar() { cerebros(); modelos(); spotify(); acerca(); }
  function iniciar() { voz(); contrasena(); }
  return { iniciar, activar, modelos };
})();
