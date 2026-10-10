"use strict";
// Chat: conversaciones persistentes en el servidor, streaming, detener, copiar, leer en voz alta.
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
    resumir_enlace: "Leyendo el enlace…", crear_rutina: "Creando rutina", mis_rutinas: "Consultando rutinas",
    borrar_rutina: "Borrando rutina", mapa_ir: "Abriendo el mapa", ruta: "Calculando ruta", sitios_cerca: "Buscando sitios cercanos",
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
      el("p", { class: "muted" }, Sesion.funciones.spotify ? "Pregúntame por el bloqueador, la VPN, la Raspberry o la música." : "Pregúntame por el bloqueador, la VPN, la Raspberry o lo que quieras."),
      el("div", { class: "sugerencias" }, ...SUGERENCIAS.map((s) =>
        el("button", { type: "button", class: "fantasma", onclick: () => enviar(s) }, s)))));
  }

  function chip(nombre, args, texto) {
    const etiqueta = NOMBRES_HERRAMIENTA[nombre] || nombre;
    const c = el("div", { class: "chip", title: texto || "" }, el("span", { class: "chip-ico", "aria-hidden": "true" }, "⚙"), etiqueta);
    botonQr(c, nombre, args, texto);
    botonMapa(c, nombre, texto);
    return c;
  }
  // Si la herramienta creó un dispositivo VPN, se ofrece abrir su QR (nunca se muestran claves en el chat).
  function botonQr(c, nombre, args, texto) {
    const m = nombre === "crear_dispositivo_vpn" && /\(id (\d+)\)/.exec(texto || "");
    if (!m || c.querySelector(".chip-qr")) return;
    const nom = String((args && args.nombre) || "dispositivo").trim();
    c.append(el("button", { type: "button", class: "chip-qr", onclick: () => Control.mostrarQr(m[1], nom) }, "Ver QR"));
  }

  function botonMapa(c, nombre, texto) {
    if (!new Set(["mapa_ir", "ruta", "sitios_cerca"]).has(nombre)) return;
    const m = /(#mapa(?:\?[^\s]+)?)/.exec(texto || "");
    const b = el("button", { type: "button", class: "chip-qr" }, "Abrir en el mapa");
    b.addEventListener("click", () => { location.hash = m ? m[1] : "mapa"; }); c.append(b);
  }

  // «Leer en voz alta» de un mensaje (Piper; si no está disponible, la voz del navegador).
  let leyendo = null;
  function botonLeer(obtener) {
    const b = el("button", { type: "button", class: "copiar", title: "Leer en voz alta", "aria-label": "Leer en voz alta" }, "Leer");
    b.addEventListener("click", async () => {
      if (leyendo === b) { Voz.parar(); return; }
      if (leyendo) leyendo.textContent = "Leer";
      leyendo = b; b.textContent = "Parar";
      try { await Voz.hablar(obtener()); } finally { if (leyendo === b) { leyendo = null; b.textContent = "Leer"; } }
    });
    return b;
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
  // `imagen`: miniatura (data URL) del mensaje del usuario. En el historial la imagen no existe: «[imagen]».
  function addMsg(rol, texto, cerebro, agente, imagen) {
    const cont = el("div", { class: "md" });
    const nodo = el("div", { class: "msg " + rol }, cont);
    let actual = texto || "";
    if (rol === "user" && actual.startsWith("[imagen]")) {
      actual = actual.slice(8).trim();
      if (!imagen) nodo.prepend(el("span", { class: "msg-img-ph", title: "Las imágenes no se guardan" }, "Imagen"));
    }
    if (imagen) nodo.prepend(el("img", { class: "msg-img", src: imagen, alt: "Imagen enviada" }));
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
    if (rol === "bot") nodo.append(el("div", { class: "msg-pie" }, agBadge, badge, botonLeer(() => actual), botonCopiar(() => actual)));
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
    window.dispatchEvent(new CustomEvent("aria:estado", { detail: { estado: en ? "pensando" : "reposo" } }));
    if (en && !pensandoNodo) { pensandoNodo = el("div", { class: "msg aviso pensando" }, "pensando…"); caja().append(pensandoNodo); abajo(); }
    else if (!en && pensandoNodo) { pensandoNodo.remove(); pensandoNodo = null; }
  }
  function addAviso(texto) { caja().append(el("div", { class: "msg aviso" }, texto)); abajo(); }

  function ponerEstado(en) {
    enCurso = en;
    $("enviar").hidden = en; $("detener").hidden = !en;
    $("texto").disabled = false;
  }

  // --- Imagen adjunta: se reduce en el navegador (máx. 1600 px, JPEG) y viaja con el mensaje ---
  const MAX_LADO = 1600, MAX_BYTES = 5 * 1024 * 1024, TIPOS_IMG = ["image/jpeg", "image/png", "image/webp"];
  let adjunto = null;   // { datos: data URL JPEG, miniatura: data URL pequeña }
  function lienzo(bmp, lado) {
    const k = Math.min(1, lado / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(bmp.width * k)); c.height = Math.max(1, Math.round(bmp.height * k));
    const g = c.getContext("2d");
    g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height);   // PNG con transparencia -> fondo blanco
    g.drawImage(bmp, 0, 0, c.width, c.height);
    return c;
  }
  function aDataUrl(blob) {
    return new Promise((ok, mal) => { const f = new FileReader(); f.onload = () => ok(f.result); f.onerror = mal; f.readAsDataURL(blob); });
  }
  async function prepararImagen(file) {
    if (!file || !TIPOS_IMG.includes(file.type)) { toast("Solo puedo ver imágenes JPEG, PNG o WebP.", "mal"); return; }
    if (file.size > 40 * 1024 * 1024) { toast("La imagen es demasiado grande.", "mal"); return; }
    let bmp;
    try { bmp = await createImageBitmap(file); } catch (_) { toast("No pude leer esa imagen.", "mal"); return; }
    try {
      const c = lienzo(bmp, MAX_LADO);
      let blob = null;
      for (const q of [0.85, 0.7, 0.5]) {
        blob = await new Promise((ok) => c.toBlob(ok, "image/jpeg", q));   // recodificar quita EXIF/GPS
        if (blob && blob.size <= MAX_BYTES) break;
      }
      if (!blob || blob.size > MAX_BYTES) { toast("La imagen es demasiado grande (máximo 5 MB).", "mal"); return; }
      adjunto = { datos: await aDataUrl(blob), miniatura: lienzo(bmp, 240).toDataURL("image/jpeg", 0.7) };
      $("adjunto-img").src = adjunto.miniatura;
      $("adjunto-info").textContent = c.width + "×" + c.height + " · " + fmtBytes(blob.size);
      $("adjunto").hidden = false;
      $("texto").focus();
    } finally { if (bmp.close) bmp.close(); }
  }
  function quitarAdjunto() { adjunto = null; $("adjunto").hidden = true; $("adjunto-img").removeAttribute("src"); $("imagen-input").value = ""; }

  // Propuesta de apuntar un gasto leído de un ticket. Se apunta solo si el usuario pulsa «Registrar gasto».
  function tarjetaTicket(ev) {
    const fila = (k, v) => [el("dt", null, k), el("dd", null, String(v ?? ""))];
    const estado = el("p", { class: "muted" });
    const si = el("button", { type: "button", class: "primario pequeno" }, "Registrar gasto");
    const no = el("button", { type: "button", class: "fantasma pequeno" }, "Descartar");
    const botones = el("div", { class: "botones" }, si, no);
    const t = el("div", { class: "ticket" }, el("strong", null, "¿Apunto este gasto en tus finanzas?"),
      el("dl", null, ...fila("Comercio", ev.comercio), ...fila("Fecha", ev.fecha), ...fila("Total", ev.importe), ...fila("Categoría", ev.categoria)),
      botones, estado);
    const ruta = "/api/vision/tickets/" + encodeURIComponent(ev.token || "");
    const fin = (texto) => { botones.remove(); estado.textContent = texto; };
    si.addEventListener("click", async () => {
      si.disabled = no.disabled = true;
      const r = await api(ruta, { method: "POST" });
      if (r.ok) { fin(r.data.texto || "Apuntado."); toast("Gasto apuntado en Finanzas."); }
      else { fin(r.data.error || "No se pudo apuntar."); }
    });
    no.addEventListener("click", async () => { si.disabled = no.disabled = true; await api(ruta, { method: "DELETE" }); fin("Descartado."); });
    return t;
  }

  async function errorHttp(r) {
    try { const j = await r.json(); if (j && j.error) return j.error; } catch (_) { /* sin JSON */ }
    return "Error de conexión con ARIA.";
  }

  // Envía un mensaje. Devuelve el texto de la respuesta (para leerlo en voz alta).
  let lectura = Promise.resolve();   // lectura en voz alta de la última respuesta (streaming)
  async function enviar(texto, opciones = {}) {
    texto = (texto || "").trim();
    const img = adjunto;
    if ((!texto && !img) || enCurso) return "";
    Voz.parar();
    if (!caja().querySelector(".msg")) caja().replaceChildren();
    addMsg("user", texto, null, null, img ? img.miniatura : null); abajo();
    if (img) quitarAdjunto();
    ponerEstado(true);
    abort = new AbortController();
    let burbuja = null, acumulado = "", ultimoChip = null, ultimoArgs = {}, todo = "", etiqueta = "", agente = "";
    // Voz en streaming: si hay que leer la respuesta, empieza a sonar en cuanto termina la primera frase
    const leer = opciones.leerEnVivo || (!opciones.sinLeer && Prefs.get("tts", "0") === "1");
    let lector = leer ? Voz.lector() : null;
    lectura = Promise.resolve();
    try {
      const cuerpo = convId ? { conversation_id: convId, message: texto }
        : { conversation_id: null, message: texto, agente: agentePendiente };
      if (img) cuerpo.imagen = img.datos;
      const r = await fetch("/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: abort.signal,
        body: JSON.stringify(cuerpo),
      });
      if (r.status === 401) { location.href = "/login"; return ""; }
      if (!r.ok) { addAviso(await errorHttp(r)); return ""; }
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
          if (lector) { todo = ""; lector = Voz.lector(); }   // otro cerebro vuelve a empezar: lo dicho se descarta
        } else if (ev.type === "token") {
          pensando(false);
          if (!burbuja) { burbuja = addMsg("bot", "", etiqueta, agente); }
           acumulado += ev.text; todo += ev.text; burbuja.actualizar(acumulado); abajo();
           if (lector) lector.empujar(todo);
           window.dispatchEvent(new CustomEvent("aria:hud-texto", { detail: { texto: todo } }));
        } else if (ev.type === "herramienta") {
          pensando(false); burbuja = null; acumulado = ""; todo += "\n";
          ultimoArgs = ev.args; ultimoChip = chip(ev.name, ev.args); if (BUSQUEDA.has(ev.name)) ultimoChip.classList.add("buscando"); caja().append(ultimoChip); abajo();
        } else if (ev.type === "resultado") {
          if (ultimoChip) { ultimoChip.title = ev.text; ultimoChip.classList.remove("buscando"); ultimoChip.classList.add("hecho"); botonQr(ultimoChip, ev.name, ultimoArgs, ev.text); ponerFuentes(ultimoChip, ev.name, ev.text); abajo(); }
        } else if (ev.type === "ticket") {
          if (ev.token) { caja().append(tarjetaTicket(ev)); abajo(); }
        } else if (ev.type === "aviso" || ev.type === "error") { pensando(false); addAviso(ev.text); }
      }
      if (lector) lectura = lector.fin(todo);
    } catch (e) {
      if (lector) Voz.parar();
      if (e.name === "AbortError") addAviso("Respuesta detenida.");
      else addAviso("Error de conexión con ARIA.");
    } finally {
      pensando(false); abort = null; ponerEstado(false); cargarLista(); refrescarCerebro();
      if (!opciones.sinLeer) $("texto").focus();
    }
    return todo.trim();
  }

  function detener() { if (abort) abort.abort(); }

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
    $("form").addEventListener("submit", (e) => { e.preventDefault(); const t = $("texto").value; if ((t.trim() || adjunto) && !enCurso) { $("texto").value = ""; autoajustar(); enviar(t); } });
    // Imagen: botón, pegar (Ctrl+V) y arrastrar y soltar.
    if (Sesion.funciones && Sesion.funciones.vision === false) $("adjuntar").hidden = true;
    $("adjuntar").addEventListener("click", () => $("imagen-input").click());
    $("imagen-input").addEventListener("change", (e) => { const f = e.target.files && e.target.files[0]; if (f) prepararImagen(f); });
    $("adjunto-quitar").addEventListener("click", quitarAdjunto);
    $("texto").addEventListener("paste", (e) => {
      const it = [...((e.clipboardData && e.clipboardData.items) || [])].find((i) => i.kind === "file" && i.type.startsWith("image/"));
      if (it) { e.preventDefault(); prepararImagen(it.getAsFile()); }
    });
    for (const zona of [caja(), $("form")]) {
      zona.addEventListener("dragover", (e) => { if ([...(e.dataTransfer?.types || [])].includes("Files")) { e.preventDefault(); zona.classList.add("soltar"); } });
      zona.addEventListener("dragleave", () => zona.classList.remove("soltar"));
      zona.addEventListener("drop", (e) => {
        zona.classList.remove("soltar");
        const f = [...(e.dataTransfer?.files || [])].find((x) => x.type.startsWith("image/"));
        if (f) { e.preventDefault(); prepararImagen(f); }
      });
    }
    $("texto").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("form").requestSubmit(); } });
    $("texto").addEventListener("input", autoajustar);
    $("detener").addEventListener("click", detener);
    $("nuevo").addEventListener("click", nueva);
    $("agente-sel").addEventListener("change", cambiarAgente);
    cargarAgentes();
    $("btn-convs").addEventListener("click", abrirLista);
    $("convs-fondo").addEventListener("click", cerrarLista);
    Voz.botonMic($("mic"), (t) => { $("texto").value = t; autoajustar(); $("form").requestSubmit(); });
    const manos = $("btn-manos");
    manos.addEventListener("click", () => (ManosLibres.activa() ? ManosLibres.parar() : ManosLibres.iniciar()));
    ManosLibres.alCambiar((on) => { manos.setAttribute("aria-pressed", on ? "true" : "false"); manos.classList.toggle("activo", on); });
    const ultima = Prefs.get("conv", "");
    if (ultima) abrir(ultima, true); else vacio();
    cargarLista();
  }
  function autoajustar() { const t = $("texto"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 160) + "px"; }

  function preguntar(texto, agente) { nueva(); if (agente) { agentePendiente = agente; ponerSelector(agente); } enviar(texto); }
  // Desde «manos libres»: se muestra el chat y se envía como un mensaje escrito (mismo agente
  // elegido en el selector y mismo enrutado), sin el autoleer (lo lee ManosLibres).
  // `leer`: la respuesta se lee en streaming mientras llega; Chat.lectura() se resuelve cuando termina de sonar.
  async function enviarDesdeVoz(texto, leer = false) {
    if (location.hash !== "#chat") location.hash = "chat";
    if (enCurso) { toast("Espera a que termine la respuesta anterior."); return ""; }
    return enviar(texto, { sinLeer: true, leerEnVivo: leer });
  }
  return { iniciar, preguntar, refrescarCerebro, enviarDesdeVoz, lectura: () => lectura };
})();
