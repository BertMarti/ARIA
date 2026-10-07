"use strict";
// Chat: conversaciones persistentes en el servidor, streaming, detener, copiar, voz.
const Chat = (() => {
  const caja = () => $("mensajes");
  let convId = null;
  let abort = null;          // AbortController del envío en curso
  let enCurso = false;

  const NOMBRES_HERRAMIENTA = {
    fecha_hora: "Consultando la hora", estado_servicios: "Comprobando servicios",
    estado_bloqueador: "Consultando el bloqueador", pausar_bloqueador: "Pausando el bloqueador",
    reanudar_bloqueador: "Reanudando el bloqueador", dispositivos_vpn: "Consultando la VPN",
    estado_sistema: "Consultando la Raspberry", spotify_play: "Spotify: reproducir", spotify_pause: "Spotify: pausa",
    spotify_siguiente: "Spotify: siguiente", spotify_anterior: "Spotify: anterior", spotify_actual: "Spotify: ahora suena",
    spotify_buscar_y_reproducir: "Buscando en Spotify", buscar_en_netflix: "Buscando en Netflix",
    buscar_en_internet: "Buscando en internet…", noticias: "Buscando noticias…",
    registrar_movimiento: "Apuntando movimiento", resumen_mes: "Resumen del mes", gastos_por_categoria: "Gastos por categoría",
    comparar_meses: "Comparando meses", presupuesto: "Fijando presupuesto", estado_presupuestos: "Revisando presupuestos",
    buscar_movimientos: "Buscando movimientos", estado_red: "Salud de la red", dispositivos_red: "Dispositivos de la red",
    dispositivos_nuevos: "Dispositivos nuevos", marcar_dispositivo_conocido: "Marcando dispositivo",
    medir_latencia: "Midiendo latencia", test_velocidad: "Test de velocidad", informe_seguridad: "Informe de seguridad",
    escanear_red: "Pidiendo escaneo", estado_escaneo: "Estado del escáner", bloqueos_por_cliente: "Bloqueos por dispositivo",
  };
  let agentes = {};             // id -> {nombre, icono, descripcion}
  let agentePendiente = "aria"; // agente elegido antes de crear la conversación
  let agenteVista = "aria";     // el que muestra el selector
  const BUSQUEDA = new Set(["buscar_en_internet", "noticias"]);
  const SUGERENCIAS = [
    "¿Cuántos anuncios has bloqueado hoy?", "¿Qué temperatura tiene la Raspberry?",
    "¿Qué dispositivos hay en la VPN?", "Explícame qué es un DNS",
  ];

  function abajo() { const c = caja(); c.scrollTop = c.scrollHeight; }

  function vacio() {
    const c = caja();
    c.replaceChildren(el("div", { class: "bienvenida" },
      el("img", { src: "/static/icon.svg", alt: "", width: 64, height: 64 }),
      el("h2", null, "¿En qué puedo ayudarte?"),
      el("p", { class: "muted" }, "Pregúntame por el bloqueador, la VPN, la Raspberry o la música."),
      el("div", { class: "sugerencias" }, ...SUGERENCIAS.map((s) =>
        el("button", { type: "button", class: "fantasma", onclick: () => enviar(s) }, s)))));
  }

  function chip(nombre, args, texto) {
    const etiqueta = NOMBRES_HERRAMIENTA[nombre] || nombre;
    const c = el("div", { class: "chip", title: texto || "" }, el("span", { class: "chip-ico", "aria-hidden": "true" }, "⚙"), etiqueta);
    botonQr(c, nombre, args, texto);
    return c;
  }
  // Si la herramienta creó un dispositivo VPN, se ofrece abrir su QR (nunca se muestran claves en el chat).
  function botonQr(c, nombre, args, texto) {
    const m = nombre === "crear_dispositivo_vpn" && /\(id (\d+)\)/.exec(texto || "");
    if (!m || c.querySelector(".chip-qr")) return;
    const nom = String((args && args.nombre) || "dispositivo").trim();
    c.append(el("button", { type: "button", class: "chip-qr", onclick: () => Control.mostrarQr(m[1], nom) }, "Ver QR"));
  }

  // Enlaces a las fuentes de una búsqueda. Se construyen con el DOM (textContent) y solo http/https.
  function fuentes(texto) {
    const lista = [], vistos = new Set();
    for (const l of String(texto || "").split("\n")) {
      const m = /^\s+(https?:\/\/\S+)\s*$/.exec(l);
      if (!m) continue;
      let u;
      try { u = new URL(m[1]); } catch (_) { continue; }
      if ((u.protocol !== "http:" && u.protocol !== "https:") || vistos.has(u.href)) continue;
      vistos.add(u.href);
      lista.push(el("a", { href: u.href, target: "_blank", rel: "noopener noreferrer nofollow", title: u.href },
        u.hostname.replace(/^www\./, "")));
    }
    return lista.length ? el("div", { class: "fuentes" }, el("span", { class: "muted" }, "Fuentes:"), ...lista) : null;
  }
  function ponerFuentes(chipNodo, nombre, texto) {
    if (!BUSQUEDA.has(nombre) || !chipNodo || chipNodo.nextSibling?.classList?.contains("fuentes")) return;
    const f = fuentes(texto);
    if (f) chipNodo.after(f);
  }

  function botonCopiar(obtener) {
    const b = el("button", { type: "button", class: "copiar", title: "Copiar", "aria-label": "Copiar mensaje" }, "Copiar");
    b.addEventListener("click", async () => {
      const t = obtener();
      try { await navigator.clipboard.writeText(t); }
      catch (_) {
        const ta = el("textarea", { value: t }); document.body.append(ta); ta.select();
        try { document.execCommand("copy"); } catch (_e) { /* sin portapapeles */ }
        ta.remove();
      }
      b.textContent = "Copiado"; setTimeout(() => { b.textContent = "Copiar"; }, 1500);
    });
    return b;
  }

  // Mensaje de usuario o de ARIA. Devuelve { nodo, actualizar(texto) }.
  function addMsg(rol, texto, cerebro, agente) {
    const cont = el("div", { class: "md" });
    const nodo = el("div", { class: "msg " + rol }, cont);
    let actual = texto || "";
    if (actual) renderMd(actual, cont);
    const badge = el("span", { class: "cerebro-badge", title: "Cerebro que respondió" });
    const agBadge = el("span", { class: "agente-badge", title: "Agente que respondió" });
    const ponerBadge = (t) => { badge.textContent = t || ""; badge.hidden = !t; };
    const ponerAgente = (id) => {
      const a = agentes[id] || (id ? { nombre: id } : null);
      agBadge.textContent = a ? a.nombre : ""; agBadge.hidden = !a;
      agBadge.className = "agente-badge ag-" + (id || "aria");
    };
    ponerBadge(cerebro); ponerAgente(agente);
    if (rol === "bot") nodo.append(el("div", { class: "msg-pie" }, agBadge, badge, botonCopiar(() => actual)));
    caja().append(nodo);
    return { nodo, ponerBadge, ponerAgente, actualizar(t) { actual = t; renderMd(t, cont); } };
  }
  // --- Selector de agente ---
  async function cargarAgentes() {
    const { ok, data } = await api("/api/agentes");
    if (!ok) return;
    agentes = {};
    const sel = $("agente-sel");
    sel.replaceChildren();
    for (const a of data.agentes) {
      agentes[a.id] = a;
      sel.append(el("option", { value: a.id, title: a.descripcion }, a.id === "aria" ? "ARIA (automático)" : a.nombre));
    }
    ponerSelector(agenteVista);
  }
  function ponerSelector(id) { agenteVista = id || "aria"; $("agente-sel").value = agentes[agenteVista] ? agenteVista : "aria"; }
  async function cambiarAgente() {
    const id = $("agente-sel").value;
    if (!convId) { agentePendiente = id; return; }
    const r = await api("/api/conversations/" + encodeURIComponent(convId), { method: "PATCH", json: { agente: id } });
    if (!r.ok) toast(r.data.error || "No se pudo cambiar de agente.", "mal");
    else toast("Esta conversación usará " + (agentes[id] ? agentes[id].nombre : id) + ".");
  }
  // Cerebro que está en cabeza de la cadena (cabecera del chat).
  async function refrescarCerebro() {
    const { ok, data } = await api("/api/info");
    if (ok && data.cerebro) $("modelo-activo").textContent = data.cerebro.etiqueta;
  }
  let pensandoNodo = null;
  function pensando(en) {
    if (en && !pensandoNodo) { pensandoNodo = el("div", { class: "msg aviso pensando" }, "pensando…"); caja().append(pensandoNodo); abajo(); }
    else if (!en && pensandoNodo) { pensandoNodo.remove(); pensandoNodo = null; }
  }
  function addAviso(texto) { caja().append(el("div", { class: "msg aviso" }, texto)); abajo(); }

  function ponerEstado(en) {
    enCurso = en;
    $("enviar").hidden = en; $("detener").hidden = !en;
    $("texto").disabled = false;
  }

  async function enviar(texto) {
    texto = (texto || "").trim();
    if (!texto || enCurso) return;
    if (window.speechSynthesis) speechSynthesis.cancel();
    if (!caja().querySelector(".msg")) caja().replaceChildren();
    addMsg("user", texto); abajo();
    ponerEstado(true);
    abort = new AbortController();
    let burbuja = null, acumulado = "", ultimoChip = null, ultimoArgs = {}, todo = "", etiqueta = "", agente = "";
    try {
      const r = await fetch("/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: abort.signal,
        body: JSON.stringify(convId ? { conversation_id: convId, message: texto }
          : { conversation_id: null, message: texto, agente: agentePendiente }),
      });
      if (r.status === 401) { location.href = "/login"; return; }
      if (!r.ok) throw new Error("HTTP " + r.status);
      for await (const ev of lineasNdjson(r)) {
        if (ev.type === "conv") {
          convId = ev.id; $("chat-titulo").textContent = ev.titulo; cargarLista();
        } else if (ev.type === "agente") {
          agente = ev.id; if (burbuja) burbuja.ponerAgente(agente);
        } else if (ev.type === "cerebro") {
          etiqueta = ev.etiqueta; if (burbuja) burbuja.ponerBadge(etiqueta);
        } else if (ev.type === "pensando") {
          pensando(true);
        } else if (ev.type === "reinicio") {
          pensando(false); acumulado = ""; if (burbuja) { burbuja.nodo.remove(); burbuja = null; }
        } else if (ev.type === "token") {
          pensando(false);
          if (!burbuja) { burbuja = addMsg("bot", "", etiqueta, agente); }
          acumulado += ev.text; todo += ev.text; burbuja.actualizar(acumulado); abajo();
        } else if (ev.type === "herramienta") {
          pensando(false); burbuja = null; acumulado = ""; todo += "\n";
          ultimoArgs = ev.args; ultimoChip = chip(ev.name, ev.args); if (BUSQUEDA.has(ev.name)) ultimoChip.classList.add("buscando"); caja().append(ultimoChip); abajo();
        } else if (ev.type === "resultado") {
          if (ultimoChip) { ultimoChip.title = ev.text; ultimoChip.classList.remove("buscando"); ultimoChip.classList.add("hecho"); botonQr(ultimoChip, ev.name, ultimoArgs, ev.text); ponerFuentes(ultimoChip, ev.name, ev.text); abajo(); }
        } else if (ev.type === "aviso" || ev.type === "error") { pensando(false); addAviso(ev.text); }
      }
      hablar(todo);
    } catch (e) {
      if (e.name === "AbortError") addAviso("Respuesta detenida.");
      else addAviso("Error de conexión con ARIA.");
    } finally {
      pensando(false); abort = null; ponerEstado(false); cargarLista(); refrescarCerebro(); $("texto").focus();
    }
  }

  function detener() { if (abort) abort.abort(); }

  function hablar(texto) {
    if (Prefs.get("tts", "0") !== "1" || !window.speechSynthesis || !texto.trim()) return;
    const u = new SpeechSynthesisUtterance(mdATexto(texto).slice(0, 1500));
    const voces = speechSynthesis.getVoices();
    const voz = voces.find((v) => /^es[-_]ES/i.test(v.lang)) || voces.find((v) => /^es/i.test(v.lang));
    if (voz) { u.voice = voz; u.lang = voz.lang; } else u.lang = "es-ES";
    speechSynthesis.speak(u);
  }

  // --- Conversaciones ---
  async function cargarLista() {
    const { ok, data } = await api("/api/conversations");
    if (!ok) return;
    const ul = $("lista-convs");
    ul.replaceChildren();
    if (!data.conversaciones.length) ul.append(el("li", { class: "muted vacio" }, "Aún no hay conversaciones."));
    for (const c of data.conversaciones) ul.append(itemConv(c));
  }

  function itemConv(c) {
    const titulo = marquesina(el("button", { type: "button", class: "conv-titulo" }), c.titulo);
    titulo.addEventListener("click", () => abrir(c.id));
    const ren = el("button", { type: "button", class: "icono-mini", title: "Renombrar", "aria-label": "Renombrar" }, "✎");
    const del = el("button", { type: "button", class: "icono-mini", title: "Borrar", "aria-label": "Borrar conversación" }, "✕");
    const li = el("li", { class: "conv" + (c.id === convId ? " activa" : "") }, titulo, ren, del);
    ren.addEventListener("click", () => {
      const inp = el("input", { class: "conv-edit", value: c.titulo, maxLength: 120, "aria-label": "Nuevo título" });
      li.replaceChildren(inp); inp.focus(); inp.select();
      let hecho = false;
      const fin = async (guardar) => {
        if (hecho) return; hecho = true;
        const t = inp.value.trim();
        if (guardar && t && t !== c.titulo) {
          const r = await api("/api/conversations/" + encodeURIComponent(c.id), { method: "PATCH", json: { titulo: t } });
          if (r.ok && c.id === convId) $("chat-titulo").textContent = t;
        }
        cargarLista();
      };
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") fin(true); else if (e.key === "Escape") fin(false); });
      inp.addEventListener("blur", () => fin(true));
    });
    del.addEventListener("click", async () => {
      if (!(await confirmar("Borrar conversación", "«" + c.titulo + "» se eliminará para siempre.", "Borrar"))) return;
      const r = await api("/api/conversations/" + encodeURIComponent(c.id), { method: "DELETE" });
      if (!r.ok) { toast("No se pudo borrar.", "mal"); return; }
      if (c.id === convId) nueva();
      cargarLista();
    });
    return li;
  }

  async function abrir(id, silencioso) {
    if (enCurso) detener();
    const { ok, data } = await api("/api/conversations/" + encodeURIComponent(id));
    if (!ok) {
      if (silencioso) { nueva(); } else toast("No se pudo abrir la conversación.", "mal");
      return;
    }
    convId = data.id; $("chat-titulo").textContent = data.titulo;
    caja().replaceChildren();
    for (const m of data.mensajes) {
      if (m.role === "tool") {
        let j = {}; try { j = JSON.parse(m.content); } catch (_) { /* ignorar */ }
        caja().append(chip(j.name || "herramienta", j.args || {}, j.text));
        caja().lastChild.classList.add("hecho");
        ponerFuentes(caja().lastChild, j.name, j.text);
      } else addMsg(m.role === "user" ? "user" : "bot", m.content, m.cerebro, m.role === "user" ? null : m.agente);
    }
    ponerSelector(data.agente);
    if (!data.mensajes.length) vacio();
    abajo(); cerrarLista(); cargarLista();
    localStorageConv(id);
  }

  function nueva() {
    if (enCurso) detener();
    convId = null; $("chat-titulo").textContent = "Conversación nueva";
    agentePendiente = "aria"; ponerSelector("aria");
    vacio(); cerrarLista(); localStorageConv(null);
    $("texto").focus(); cargarLista();
  }
  function localStorageConv(id) { Prefs.set("conv", id || ""); }

  function abrirLista() { $("convs").classList.add("abierto"); $("convs-fondo").hidden = false; }
  function cerrarLista() { $("convs").classList.remove("abierto"); $("convs-fondo").hidden = true; }

  function iniciar() {
    $("form").addEventListener("submit", (e) => { e.preventDefault(); const t = $("texto").value; if (t.trim() && !enCurso) { $("texto").value = ""; autoajustar(); enviar(t); } });
    $("texto").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("form").requestSubmit(); } });
    $("texto").addEventListener("input", autoajustar);
    $("detener").addEventListener("click", detener);
    $("nuevo").addEventListener("click", nueva);
    $("agente-sel").addEventListener("change", cambiarAgente);
    cargarAgentes();
    $("btn-convs").addEventListener("click", abrirLista);
    $("convs-fondo").addEventListener("click", cerrarLista);
    const ultima = Prefs.get("conv", "");
    if (ultima) abrir(ultima, true); else vacio();
    cargarLista();
  }
  function autoajustar() { const t = $("texto"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 160) + "px"; }

  function preguntar(texto, agente) { nueva(); if (agente) { agentePendiente = agente; ponerSelector(agente); } enviar(texto); }
  return { iniciar, preguntar, refrescarCerebro };
})();
