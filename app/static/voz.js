"use strict";
// Voz: pulsar para hablar, leer en voz alta (Piper en la Raspberry, con la voz del navegador
// como respaldo) y «manos libres» con la palabra «Aria». El audio no se guarda en ningún sitio.
const Voz = (() => {
  const MAX_GRAB_MS = 30000;
  const MIN_GRAB_MS = 400;
  const MANTENER_MS = 350;   // pulsación más larga que esto = «mantener para hablar»
  let ctx = null;            // AudioContext para reproducir (se desbloquea con el primer gesto)

  function audioCtx() {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    return ctx;
  }
  for (const t of ["pointerdown", "keydown"]) {
    addEventListener(t, () => { try { audioCtx(); } catch (_) { /* sin WebAudio */ } }, { once: true, capture: true });
  }

  const micDisponible = () => !!(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  function restricciones() {
    const id = Prefs.get("mic", "");
    const a = { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true };
    if (id) a.deviceId = { exact: id };
    return { audio: a };
  }
  async function abrirMic() {
    if (!micDisponible()) throw Object.assign(new Error("inseguro"), { name: "Inseguro" });
    try { return await navigator.mediaDevices.getUserMedia(restricciones()); }
    catch (e) {
      if (e.name === "OverconstrainedError" || e.name === "NotFoundError") {
        Prefs.set("mic", ""); // el micrófono elegido ya no existe: se usa el predeterminado
        return navigator.mediaDevices.getUserMedia(restricciones());
      }
      throw e;
    }
  }
  // Micrófono que entrega silencio absoluto (silenciado en los cascos o en Windows, o el equivocado):
  // sin esto, Whisper «oye» frases inventadas como «Gracias.».
  const SILENCIO = 0.002;  // pico máximo (0-1) por debajo del cual no hay voz que transcribir
  function avisoSilencio(nombre) {
    return "No llega sonido del micrófono" + (nombre ? " «" + nombre.replace(/\s*\([0-9a-f]{4}:[0-9a-f]{4}\)$/i, "") + "»" : "") +
      ". Puede estar silenciado (en los cascos, la varilla o el botón de silencio; o en Windows: Configuración → Sonido → Entrada) " +
      "o ser otro el que usas: elígelo en Ajustes → Voz.";
  }
  async function picoAudio(blob) {
    const Ctx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    if (!Ctx) return 1;
    const audio = await new Ctx(1, 16000, 16000).decodeAudioData(await blob.arrayBuffer());
    let m = 0;
    for (let c = 0; c < audio.numberOfChannels; c++) for (const v of audio.getChannelData(c)) { const a = Math.abs(v); if (a > m) m = a; }
    return m;
  }

  function errorMic(e) {
    if (e && e.name === "NotAllowedError") return "Permiso de micrófono denegado. Actívalo desde el candado de la barra de direcciones.";
    if (e && e.name === "NotFoundError") return "No se encontró ningún micrófono.";
    if (e && e.name === "Inseguro") return "El micrófono solo funciona por HTTPS.";
    return "No se pudo abrir el micrófono.";
  }

  // --- Pulsar para hablar --------------------------------------------------------------------
  function tipoGrabacion() {
    if (!window.MediaRecorder) return null;
    for (const t of ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"]) if (MediaRecorder.isTypeSupported(t)) return t;
    return "";
  }

  async function transcribir(blob) {
    const r = await fetch("/api/voz/transcribir", { method: "POST", headers: { "Content-Type": blob.type || "audio/webm" }, body: blob });
    if (r.status === 401) { location.href = "/login"; throw new Error("Sesión caducada."); }
    let d = {};
    try { d = await r.json(); } catch (_) { /* sin JSON */ }
    if (!r.ok) throw new Error(d.error || "No se pudo transcribir.");
    return d;
  }

  // Botón de micrófono: mantener pulsado y soltar envía; un toque empieza y otro toque termina.
  function botonMic(boton, alTexto) {
    let g = null;            // grabación en curso
    let ocupado = false;
    const etiqueta = boton.getAttribute("aria-label");
    let reloj = "";
    const poner = (estado, texto) => {
      boton.classList.toggle("grabando", estado === "grabando");
      boton.classList.toggle("ocupado", estado === "ocupado");
      boton.setAttribute("aria-pressed", estado === "grabando" ? "true" : "false");
      boton.setAttribute("aria-label", texto || etiqueta);
      boton.title = texto || etiqueta;
      const t = boton.querySelector(".mic-tiempo"); if (t) t.textContent = estado === "grabando" ? reloj : "";
    };
    async function empezar() {
      if (g || ocupado) return;
      const tipo = tipoGrabacion();
      if (tipo === null) { toast("Tu navegador no permite grabar audio.", "mal"); return; }
      ocupado = true;
      let stream;
      try { stream = await abrirMic(); } catch (e) { ocupado = false; toast(errorMic(e), "mal"); return; }
      ocupado = false;
      parar();  // si ARIA estaba hablando, se calla
      const rec = new MediaRecorder(stream, tipo ? { mimeType: tipo, audioBitsPerSecond: 32000 } : {});
      const trozos = [];
      g = { rec, stream, inicio: Date.now(), trozos };
      rec.ondataavailable = (e) => { if (e.data && e.data.size) trozos.push(e.data); };
      rec.start(250);
      const tic = () => { if (!g) return; const s = Math.floor((Date.now() - g.inicio) / 1000); reloj = "0:" + String(s).padStart(2, "0"); poner("grabando", "Grabando 0:" + String(s).padStart(2, "0") + " · suelta o pulsa para enviar"); };
      tic(); g.reloj = setInterval(tic, 500);
      g.limite = setTimeout(() => terminar(true), MAX_GRAB_MS);
    }
    async function terminar(enviar) {
      if (!g) return;
      const { rec, stream, inicio, trozos } = g;
      const nombreMic = (stream.getAudioTracks()[0] || {}).label || "";
      clearInterval(g.reloj); clearTimeout(g.limite); g = null;
      const fin = new Promise((res) => { rec.onstop = res; });
      try { rec.stop(); } catch (_) { /* ya parado */ }
      await fin;
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(trozos, { type: (rec.mimeType || "audio/webm") });
      trozos.length = 0;
      if (!enviar) { poner("libre"); return; }
      if (Date.now() - inicio < MIN_GRAB_MS || !blob.size) { poner("libre"); toast("Mantén pulsado el micrófono mientras hablas."); return; }
      poner("ocupado", "Transcribiendo…"); ocupado = true;
      try {
        if ((await picoAudio(blob).catch(() => 1)) < SILENCIO) { toast(avisoSilencio(nombreMic), "mal"); return; }
        const d = await transcribir(blob);
        if (d.texto) alTexto(d.texto); else toast("No te he entendido. Prueba otra vez.");
      } catch (e) { toast(e.message, "mal"); }
      finally { ocupado = false; poner("libre"); }
    }
    let pulsado = 0, ignorarSoltar = false;
    boton.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      if (g) { ignorarSoltar = true; terminar(true); return; }
      ignorarSoltar = false; pulsado = Date.now(); empezar();
    });
    boton.addEventListener("pointerup", () => {
      if (ignorarSoltar) { ignorarSoltar = false; return; }
      if (Date.now() - pulsado >= MANTENER_MS) {
        // Puede que el micrófono aún se esté abriendo: se espera un poco.
        const esperar = () => (g ? terminar(true) : ocupado ? setTimeout(esperar, 50) : null);
        esperar();
      }
    });
    boton.addEventListener("click", (e) => { if (e.detail === 0) { if (g) terminar(true); else empezar(); } }); // teclado
    boton.addEventListener("contextmenu", (e) => e.preventDefault());
    document.addEventListener("visibilitychange", () => { if (document.hidden && g) terminar(false); });
    if (!micDisponible()) { boton.disabled = true; boton.title = "El micrófono necesita HTTPS."; }
  }

  // --- Leer en voz alta ----------------------------------------------------------------------
  let turno = 0, fuente = null;
  const velocidad = () => Math.min(1.5, Math.max(0.7, Number(Prefs.get("voz_vel", "1")) || 1));

  function trocear(texto, max) {
    const frases = texto.match(/[^.!?…\n]+[.!?…]*[\s]*|\n+/g) || [texto];
    const out = []; let act = "";
    for (let f of frases) {
      f = f.replace(/\s+/g, " ");
      while (f.length > max) { const k = f.lastIndexOf(" ", max) > 0 ? f.lastIndexOf(" ", max) : max; out.push(f.slice(0, k)); f = f.slice(k); }
      if ((act + f).length > max && act.trim()) { out.push(act); act = ""; }
      act += f;
    }
    if (act.trim()) out.push(act);
    return out.map((s) => s.trim()).filter(Boolean);
  }

  async function pedir(texto) {
    try {
      const r = await fetch("/api/voz/hablar", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texto, velocidad: velocidad() }) });
      return r.ok ? await r.arrayBuffer() : null;
    } catch (_) { return null; }
  }

  function reproducir(buf, mio) {
    return new Promise(async (res) => {
      try {
        const c = audioCtx();
        const audio = await c.decodeAudioData(buf);
        if (mio !== turno) { res(); return; }
        const s = c.createBufferSource(); s.buffer = audio; s.connect(c.destination);
        s.onended = () => { if (fuente === s) fuente = null; res(); };
        fuente = s; s.start();
      } catch (_) { res(); }
    });
  }

  function hablarNavegador(texto, mio) {
    return new Promise((res) => {
      if (!window.speechSynthesis || mio !== turno) { res(); return; }
      const u = new SpeechSynthesisUtterance(texto);
      const voces = speechSynthesis.getVoices();
      const v = voces.find((x) => /^es[-_]ES/i.test(x.lang)) || voces.find((x) => /^es/i.test(x.lang));
      if (v) { u.voice = v; u.lang = v.lang; } else u.lang = "es-ES";
      u.rate = velocidad(); u.onend = u.onerror = () => res();
      speechSynthesis.speak(u);
    });
  }

  // Lee un texto (Markdown) en voz alta. La promesa se resuelve al terminar o al pararla.
  async function hablar(texto) {
    parar();
    const mio = turno;
    const limpio = mdATexto(texto || "").trim().slice(0, 1500);
    if (!limpio) return;
    const partes = trocear(limpio, 280);
    let siguiente = pedir(partes[0]);
    for (let i = 0; i < partes.length; i++) {
      const buf = await siguiente;
      if (mio !== turno) return;
      if (!buf) { await hablarNavegador(partes.slice(i).join(" "), mio); return; } // respaldo
      if (i + 1 < partes.length) siguiente = pedir(partes[i + 1]);
      await reproducir(buf, mio);
      if (mio !== turno) return;
    }
  }

  function parar() {
    turno++;
    if (fuente) { try { fuente.stop(); } catch (_) { /* ya parada */ } fuente = null; }
    if (window.speechSynthesis) speechSynthesis.cancel();
  }

  function pitido() {
    try {
      const c = audioCtx(), o = c.createOscillator(), g = c.createGain(), t = c.currentTime;
      o.frequency.setValueAtTime(660, t); o.frequency.setValueAtTime(990, t + 0.09);
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.25, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);
      o.connect(g); g.connect(c.destination); o.start(t); o.stop(t + 0.24);
    } catch (_) { /* sin audio */ }
  }

  return { botonMic, hablar, parar, pitido, abrirMic, errorMic, avisoSilencio, micDisponible, audioCtx, trocear };
})();

// «Manos libres»: el navegador envía el micrófono (PCM 16 kHz) por WebSocket; aria-voz avisa
// cuando oye «Aria», recorta lo que se dice después y ARIA responde en voz alta.
const ManosLibres = (() => {
  let activa = false, ws = null, stream = null, ctxMic = null, enviando = false, avisoCierre = true;
  const cambios = [];

  function estado(texto, clase) {
    const b = $("manos-libres");
    b.hidden = !activa;
    b.className = "manos-libres " + (clase || "");
    $("ml-texto").textContent = texto;
    document.title = (activa ? "● " : "") + document.title.replace(/^● /, "");
  }
  function avisar() { for (const f of cambios) f(activa); }

  async function iniciar() {
    if (activa) return;
    if (!Voz.micDisponible() || !window.AudioWorkletNode || !window.WebSocket) { toast("Tu navegador no permite el modo manos libres aquí.", "mal"); avisar(); return; }
    activa = true; avisoCierre = true; avisar();
    estado("Abriendo el micrófono…", "abriendo");
    try {
      stream = await Voz.abrirMic();
      ctxMic = new AudioContext();
      await ctxMic.audioWorklet.addModule((document.querySelector('meta[name="aria-worklet"]') || {}).content || "/static/pcm-worklet.js");
      const src = ctxMic.createMediaStreamSource(stream);
      const nodo = new AudioWorkletNode(ctxMic, "pcm16k");
      const mudo = ctxMic.createGain(); mudo.gain.value = 0;
      src.connect(nodo); nodo.connect(mudo); mudo.connect(ctxMic.destination);
      // Si en los primeros 3 s no llega ni el ruido de fondo, el micrófono está silenciado: se avisa una vez.
      let bloques = 0, pico = 0, avisado = false;
      const nombreMic = (stream.getAudioTracks()[0] || {}).label || "";
      nodo.port.onmessage = (e) => {
        if (!avisado) {
          for (const v of new Int16Array(e.data)) { const a = v < 0 ? -v : v; if (a > pico) pico = a; }
          if (pico >= 65) avisado = true;  // 65/32768 = SILENCIO
          else if (++bloques >= 38) { avisado = true; toast(Voz.avisoSilencio(nombreMic), "mal"); estado("Manos libres: no llega sonido del micrófono", "abriendo"); }
        }
        if (enviando && ws && ws.readyState === 1) ws.send(e.data);
      };
    } catch (e) { parar(); toast(Voz.errorMic(e), "mal"); return; }
    if (!activa) { parar(); return; }
    ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/api/voz/despertar");
    ws.binaryType = "arraybuffer";
    ws.onmessage = (e) => { let ev = {}; try { ev = JSON.parse(e.data); } catch (_) { return; } manejar(ev); };
    ws.onclose = () => { if (activa) { const aviso = avisoCierre; parar(); if (aviso) toast("Se cerró la escucha de voz.", "mal"); } };
  }

  function escuchar() {
    if (!activa) return;
    if (ws && ws.readyState === 1) ws.send('{"type":"reiniciar"}');
    enviando = true;
    estado("Manos libres: escuchando «Aria»", "escuchando");
  }

  async function manejar(ev) {
    if (!activa) return;
    if (ev.type === "listo" || ev.type === "nada") escuchar();
    else if (ev.type === "despierta") { Voz.parar(); Voz.pitido(); estado("Te escucho…", "oyendo"); }
    else if (ev.type === "procesando") { enviando = false; estado("Transcribiendo…", "pensando"); }
    else if (ev.type === "error") { toast(ev.text, "mal"); avisoCierre = false; escuchar(); }
    else if (ev.type === "texto") {
      enviando = false;
      if (!ev.text) { escuchar(); return; }
      estado("«" + ev.text + "»", "pensando");
      const respuesta = await Chat.enviarDesdeVoz(ev.text);
      if (!activa) return;
      if (respuesta) { estado("Respondiendo… (di «Aria» al terminar)", "hablando"); await Voz.hablar(respuesta); }
      escuchar();
    }
  }

  function parar() {
    const estaba = activa;
    activa = false; enviando = false;
    if (ws) { ws.onclose = null; try { ws.close(); } catch (_) { /* ya cerrado */ } ws = null; }
    if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
    if (ctxMic) { ctxMic.close().catch(() => {}); ctxMic = null; }
    estado("", "");
    if (estaba) avisar();
  }

  function iniciarUI() {
    $("ml-parar").addEventListener("click", parar);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden && activa) { parar(); toast("Manos libres se ha detenido: la pestaña dejó de estar visible."); }
    });
    addEventListener("pagehide", parar);
  }

  return { iniciar, parar, iniciarUI, activa: () => activa, alCambiar: (f) => cambios.push(f) };
})();
