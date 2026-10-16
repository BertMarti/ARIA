"use strict";
/* Reproductor local: los archivos nunca salen del navegador. */
const Medios = (() => {
  const EXT = new Set("mp4 m4v mkv webm mov avi wmv flv ts m2ts mts mpg mpeg ogv 3gp mp3 flac m4a aac ogg opus wav".split(" "));
  const AUDIO = new Set("mp3 flac m4a aac ogg opus wav".split(" "));
  const SUB = new Set(["srt", "vtt"]);
  const ASPECTOS = ["Original", "16:9", "4:3", "2,35:1", "Rellenar"];
  const estado = {
    archivos: [], urls: new Map(), subtitulos: new Map(), progreso: new Map(),
    actual: -1, activo: false, repetir: 0, aleatorio: false, aspecto: 0,
    retraso: 0, bucleA: null, bucleB: null, mostrarRestante: false
  };
  let db, guardado, saveTimer, idleTimer, gain, audio, fuente;

  const $m = (id) => $(id);
  const video = () => $m("medios-video");
  const extension = (nombre) => nombre.toLowerCase().split(".").pop() || "";
  const esMedia = (f) => EXT.has(extension(f.name));
  const esSubtitulo = (f) => SUB.has(extension(f.name));
  const nombreRuta = (f) => f._ruta || f.webkitRelativePath || f.name;
  const nombreLimpio = (n) => n.replace(/\.[^.]+$/, "").replace(/[._-]+/g, " ").trim();
  const natural = (a, b) => a.localeCompare(b, "es", { numeric: true, sensitivity: "base" });

  function segundos(valor) {
    const n = Math.max(0, Number(valor) || 0), h = Math.floor(n / 3600);
    const m = Math.floor(n % 3600 / 60), s = String(Math.floor(n % 60)).padStart(2, "0");
    return (h ? h + ":" : "") + m + ":" + s;
  }

  function mostrarOSD(texto, duracion = 1500) {
    const panel = $m("medios-osd");
    panel.textContent = texto;
    clearTimeout(mostrarOSD.temporizador);
    mostrarOSD.temporizador = setTimeout(() => { panel.textContent = ""; }, duracion);
  }

  function ponerOSDConBoton(texto, etiqueta, accion) {
    const panel = $m("medios-osd");
    panel.replaceChildren(el("span", null, texto), el("button", { type: "button", class: "fantasma pequeno" }, etiqueta));
    panel.lastChild.addEventListener("click", accion);
    clearTimeout(mostrarOSD.temporizador);
    mostrarOSD.temporizador = setTimeout(() => panel.replaceChildren(), 5000);
  }

  async function huella(f) {
    const texto = `${f.name}|${f.size}|${f.lastModified}`;
    const datos = new TextEncoder().encode(texto);
    const hash = await crypto.subtle.digest("SHA-256", datos);
    return [...new Uint8Array(hash)].map((x) => x.toString(16).padStart(2, "0")).join("");
  }

  function convertirSRT(texto) {
    const limpio = texto.replace(/^\uFEFF/, "").replace(/\r/g, "");
    return "WEBVTT\n\n" + limpio.replace(/(\d\d:\d\d:\d\d),(\d{3})/g, "$1.$2");
  }

  // «Capítulo 2.es.srt», «Capítulo 2.spa.srt» o «Capítulo 2.srt» → «capítulo 2» (como el vídeo sin extensión)
  function baseSubtitulo(nombre) {
    return nombre.replace(/\.(srt|vtt)$/i, "").replace(/\.(es|spa|esp|en|eng|forced)$/i, "").toLowerCase();
  }

  function subtituloPara(f) {
    return subtitulosPara(f)[0] || null;
  }

  function subtitulosPara(f) {
    const base = f.name.replace(/\.[^.]+$/, "").toLowerCase();
    return estado.archivos.filter((x) => esSubtitulo(x) && baseSubtitulo(x.name) === base);
  }

  function leerEntrada(entrada, ruta = "") {
    return new Promise((resolver) => {
      if (entrada.isFile) {
        entrada.file((f) => {
          Object.defineProperty(f, "_ruta", { value: ruta + f.name });
          resolver([f]);
        }, () => resolver([]));
        return;
      }
      if (!entrada.isDirectory) { resolver([]); return; }
      const lector = entrada.createReader(), resultado = [];
      const leer = () => lector.readEntries(async (entradas) => {
        if (!entradas.length) { resolver(resultado.flat()); return; }
        resultado.push(...await Promise.all(entradas.map((x) => leerEntrada(x, ruta + entrada.name + "/"))));
        leer();
      }, () => resolver(resultado.flat()));
      leer();
    });
  }

  async function archivosDeManija(handle, ruta = "") {
    const resultado = [];
    for await (const [nombre, entrada] of handle.entries()) {
      if (entrada.kind === "file") {
        const f = await entrada.getFile();
        Object.defineProperty(f, "_ruta", { value: ruta + nombre });
        resultado.push(f);
      } else resultado.push(...await archivosDeManija(entrada, ruta + nombre + "/"));
    }
    return resultado;
  }

  function abrirDB() {
    return new Promise((resolver) => {
      try {
        const peticion = indexedDB.open("aria-medios", 1);
        peticion.onupgradeneeded = () => peticion.result.createObjectStore("carpetas");
        peticion.onsuccess = () => resolver(peticion.result);
        peticion.onerror = () => resolver(null);
      } catch (_) { resolver(null); }
    });
  }

  async function leerCarpetaGuardada() {
    if (!db) db = await abrirDB();
    if (!db) return null;
    return new Promise((resolver) => {
      const peticion = db.transaction("carpetas").objectStore("carpetas").get("ultima");
      peticion.onsuccess = () => resolver(peticion.result || null);
      peticion.onerror = () => resolver(null);
    });
  }

  async function guardarCarpeta(handle) {
    if (!db) db = await abrirDB();
    try { db?.transaction("carpetas", "readwrite").objectStore("carpetas").put(handle, "ultima"); } catch (_) { /* opcional */ }
  }

  async function continuarConCarpeta() {
    const handle = await leerCarpetaGuardada();
    if (!handle) return;
    try {
      const permiso = await handle.queryPermission({ mode: "read" });
      if (permiso !== "granted" && await handle.requestPermission({ mode: "read" }) !== "granted") return;
      cargar(await archivosDeManija(handle), handle.name);
    } catch (_) { toast("No se ha podido abrir esa carpeta.", "mal"); }
  }

  function liberarURLs() {
    for (const url of estado.urls.values()) URL.revokeObjectURL(url);
    for (const datos of estado.subtitulos.values()) URL.revokeObjectURL(datos.url);
    estado.urls.clear();
    estado.subtitulos.clear();
  }

  async function cargar(archivos, raiz = "") {
    guardarProgreso();
    liberarURLs();
    estado.archivos = archivos.filter((f) => esMedia(f) || esSubtitulo(f));
    estado.archivos.sort((a, b) => natural(nombreRuta(a), nombreRuta(b)));
    const huellas = [];
    for (const f of estado.archivos) if (esMedia(f)) { f._huella = await huella(f); huellas.push(f._huella); }
    const respuesta = await api("/api/medios/progreso?" + huellas.map((h) => "h=" + encodeURIComponent(h)).join("&"));
    estado.progreso = new Map((respuesta.data.progreso || []).map((p) => [p.huella, p]));
    pintarLista();
    const primero = estado.archivos.findIndex(esMedia);
    if (primero >= 0) reproducir(primero);
    const n = estado.archivos.filter(esMedia).length;
    $m("medios-soltar").textContent = n === 1 ? "1 archivo preparado" : `${n} archivos preparados`;
  }

  function duracionDe(i) {
    const p = estado.progreso.get(estado.archivos[i]?._huella);
    const duracion = estado.archivos[i]?._duracion || p?.duracion;
    return duracion ? segundos(duracion) : "";
  }

  function filaMedia(i, f) {
    const progreso = estado.progreso.get(f._huella), barra = el("span", { class: "medios-item-barra" });
    const avance = progreso?.duracion ? Math.min(100, progreso.posicion / progreso.duracion * 100) : 0;
    barra.setAttribute("aria-hidden", "true");
    barra.style.setProperty("--avance", `${avance}%`);
    const meta = progreso?.visto ? "Visto" : progreso ? segundos(progreso.posicion) : "";
    const li = el("li", { class: "medios-item", tabIndex: 0, dataset: { indice: i } },
      el("span", { class: "medios-item-nombre" }, nombreLimpio(f.name)),
      el("span", { class: "medios-item-meta" }, [meta, duracionDe(i)].filter(Boolean).join(" · ")), barra);
    li.addEventListener("dblclick", () => reproducir(i));
    li.addEventListener("keydown", (e) => { if (e.key === "Enter") reproducir(i); });
    return li;
  }

  function pintarSeguir() {
    const lista = $m("medios-seguir"), recientes = [...estado.progreso.values()]
      .filter((p) => !p.visto).sort((a, b) => b.ts - a.ts).slice(0, 6);
    lista.replaceChildren();
    $m("medios-seguir-titulo").hidden = !recientes.length;
    for (const progreso of recientes) {
      const indice = estado.archivos.findIndex((f) => f._huella === progreso.huella);
      if (indice < 0) continue;
      const fila = el("li", { class: "medios-seguir-item", tabIndex: 0 },
        progreso.nombre, ` · ${segundos(progreso.posicion)}`);
      fila.addEventListener("click", () => reproducir(indice));
      fila.addEventListener("keydown", (e) => { if (e.key === "Enter") reproducir(indice); });
      lista.append(fila);
    }
  }

  function pintarLista() {
    const lista = $m("medios-lista-items"), consulta = ($m("medios-buscar").value || "").toLowerCase();
    const grupos = new Map();
    lista.replaceChildren();
    for (const [i, f] of estado.archivos.entries()) {
      if (!esMedia(f) || !nombreRuta(f).toLowerCase().includes(consulta)) continue;
      const partes = nombreRuta(f).split("/");
      const grupo = partes.slice(0, -1).join("/") || "Raíz";
      if (!grupos.has(grupo)) grupos.set(grupo, []);
      grupos.get(grupo).push([i, f]);
    }
    for (const [grupo, items] of grupos) {
      lista.append(el("li", { class: "medios-grupo" }, grupo));
      for (const [i, f] of items) lista.append(filaMedia(i, f));
    }
    pintarSeguir();
    pintarActivo();
  }

  async function crearURLSubtitulo(subtitulo) {
    if (estado.subtitulos.has(subtitulo)) return estado.subtitulos.get(subtitulo);
    const texto = await subtitulo.text();
    const blob = new Blob([convertirSRT(texto)], { type: "text/vtt" });
    const url = URL.createObjectURL(blob);
    estado.subtitulos.set(subtitulo, { url, blob });
    return { url, blob };
  }

  async function reproducir(indice) {
    const f = estado.archivos[indice];
    if (indice < 0 || !f || !esMedia(f)) return;
    guardarProgreso();
    estado.actual = indice;
    const v = video(), escena = $m("medios-escena");
    v.pause();
    v.replaceChildren();
    v.src = estado.urls.get(f) || URL.createObjectURL(f);
    estado.urls.set(f, v.src);
    $m("medios-titulo").textContent = nombreRuta(f);
    $m("medios-error").hidden = true;
    const subtitulos = subtitulosPara(f);
    for (const [i, subtitulo] of subtitulos.entries()) {
      const datos = await crearURLSubtitulo(subtitulo);
      const track = el("track", { kind: "subtitles", label: subtitulo.name, srclang: "es" });
      track.src = datos.url;
      track.default = i === 0;
      v.append(track);
      if (i === 0) track.track.mode = "showing";   // como VLC: si hay subtítulos, se ven desde el principio
    }
    v.onloadedmetadata = () => {
      f._duracion = v.duration;
      pintarLista();
      reanudar(f);
    };
    v.onerror = () => mostrarError();
    v.onloadeddata = () => {
      if (!AUDIO.has(extension(f.name)) && !v.videoWidth && v.duration) mostrarError();
    };
    v.load();
    v.play().catch(() => {});
    escena.classList.remove("controles-ocultos");
    pintarActivo();
  }

  function reanudar(f) {
    const progreso = estado.progreso.get(f._huella), v = video();
    if (!progreso || progreso.posicion <= 10 || progreso.posicion >= v.duration * 0.95) return;
    v.currentTime = progreso.posicion;
    ponerOSDConBoton(`Reanudado en ${segundos(progreso.posicion)}`, "Desde el principio", () => {
      v.currentTime = 0;
      $m("medios-osd").replaceChildren();
    });
  }

  function mostrarError() {
    const error = $m("medios-error");
    error.textContent = "Tu navegador no puede reproducir este formato (seguramente H.265/HEVC o un códec antiguo). " +
      "Prueba a enviarlo a la tele, que suele poder.";
    error.hidden = false;
  }

  function pintarActivo() {
    document.querySelectorAll(".medios-item").forEach((fila) => {
      fila.classList.toggle("activo", Number(fila.dataset.indice) === estado.actual);
    });
  }

  function listaMedia() {
    return estado.archivos.map((f, i) => esMedia(f) ? i : -1).filter((i) => i >= 0);
  }

  function siguiente(direccion = 1) {
    const lista = listaMedia();
    if (!lista.length) return;
    if (estado.repetir === 1 && direccion > 0) { reproducir(estado.actual); return; }
    const posicion = estado.aleatorio ? Math.floor(Math.random() * lista.length) : lista.indexOf(estado.actual);
    reproducir(lista[(posicion + direccion + lista.length) % lista.length]);
  }

  async function guardarProgreso() {
    const f = estado.archivos[estado.actual], v = video();
    if (!f || !esMedia(f) || !Number.isFinite(v.currentTime)) return;
    const h = f._huella || await huella(f);
    f._huella = h;
    const respuesta = await api("/api/medios/progreso", {
      method: "POST", json: { huella: h, nombre: nombreRuta(f).slice(0, 200), posicion: v.currentTime,
        duracion: v.duration || 0 }, keepalive: true
    });
    if (respuesta.ok) { estado.progreso.set(h, respuesta.data.progreso); pintarLista(); }
  }

  function programarGuardado() {
    if (saveTimer) return;
    saveTimer = setTimeout(() => { saveTimer = null; guardarProgreso(); }, 5000);
  }

  function iniciarAudio() {
    if (!audio) {
      audio = new AudioContext();
      fuente = audio.createMediaElementSource(video());
      gain = audio.createGain();
      fuente.connect(gain).connect(audio.destination);
    }
    if (audio.state === "suspended") audio.resume();
  }

  function volumen(valor, avisar = true) {
    const n = Math.max(0, Math.min(200, Number(valor) || 0));
    $m("medios-volumen").value = n;
    iniciarAudio();
    gain.gain.value = n / 100;
    video().volume = Math.min(1, n / 100);
    if (avisar) mostrarOSD(`Volumen ${n} %`);
  }

  function cambiarVelocidad(valor) {
    const n = Math.round(Math.max(0.1, Math.min(4, Number(valor))) * 100) / 100;
    video().playbackRate = n;
    $m("medios-velocidad").value = String(n);
    mostrarOSD(`Velocidad ${n.toFixed(2).replace(".", ",")}x`);
  }

  function cambiarAspecto() {
    estado.aspecto = (estado.aspecto + 1) % ASPECTOS.length;
    const v = video();
    ASPECTOS.forEach((_, i) => v.classList.toggle("aspecto-" + i, i === estado.aspecto));
    $m("medios-aspecto").textContent = ASPECTOS[estado.aspecto];
    mostrarOSD(`Aspecto ${ASPECTOS[estado.aspecto]}`);
  }

  function cambiarRepetir() {
    estado.repetir = (estado.repetir + 1) % 3;
    const nombres = ["no", "una", "todas"];
    $m("medios-repetir").textContent = "↻ " + nombres[estado.repetir];
    mostrarOSD("Repetir: " + nombres[estado.repetir]);
  }

  function cambiarSubtitulos() {
    const pistas = video().textTracks;
    if (!pistas.length) { mostrarOSD("Subtítulos: sin subtítulos"); return; }
    const actual = [...pistas].findIndex((pista) => pista.mode === "showing");
    const siguientePista = actual + 1;
    for (const pista of pistas) pista.mode = "disabled";
    if (siguientePista >= pistas.length) { mostrarOSD("Subtítulos: sin subtítulos"); return; }
    pistas[siguientePista].mode = "showing";
    mostrarOSD("Subtítulos: " + pistas[siguientePista].label);
  }

  function retrasarSubtitulos(cambio) {
    const pista = video().textTracks[0];
    if (!pista?.cues) return;
    estado.retraso += cambio;
    for (const cue of pista.cues) { cue.startTime += cambio / 1000; cue.endTime += cambio / 1000; }
    mostrarOSD(`Subtítulos: retraso ${estado.retraso} ms`);
  }

  function alternarBucle() {
    const v = video();
    if (estado.bucleA === null) { estado.bucleA = v.currentTime; mostrarOSD("Bucle A: " + segundos(v.currentTime)); return; }
    if (estado.bucleB === null) {
      estado.bucleB = v.currentTime;
      if (estado.bucleB <= estado.bucleA) estado.bucleB = null;
      mostrarOSD(estado.bucleB === null ? "Bucle B debe estar después de A" : "Bucle A-B activado");
      return;
    }
    estado.bucleA = estado.bucleB = null;
    mostrarOSD("Bucle A-B desactivado");
  }

  function captura() {
    const v = video();
    if (!v.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d").drawImage(v, 0, 0);
    const f = estado.archivos[estado.actual];
    const enlace = el("a", { download: nombreLimpio(f?.name || "captura") + ".png", href: canvas.toDataURL("image/png") });
    enlace.click();
  }

  function mostrarInformacion() {
    const f = estado.archivos[estado.actual], v = video();
    if (!f) return;
    mostrarOSD(`${nombreRuta(f)} · ${v.videoWidth}×${v.videoHeight} · ${segundos(v.duration)} · ${fmtBytes(f.size)}`, 5000);
  }

  function mostrarAyuda() {
    let dialogo = $m("medios-ayuda-panel");
    if (!dialogo) {
      dialogo = el("dialog", { id: "medios-ayuda-panel", class: "modal", ariaLabel: "Atajos de teclado" });
      dialogo.append(el("h2", null, "Atajos de VLC"), el("p", null,
        "Espacio pausa · F o doble clic pantalla completa · Esc salir · S detener · N/P siguiente/anterior · M silencio · " +
        "←/→ 10 s · Mayús ←/→ 3 s · Alt ←/→ 10 s · Ctrl ←/→ 1 min · Ctrl+Alt ←/→ 5 min · ↑/↓ volumen · " +
        "rueda volumen · [ ] velocidad · = normal · E fotograma · A aspecto · V subtítulos · G/H retraso · L repetir · " +
        "R aleatorio · T tiempo · I información · Mayús+S captura · 0–9 posición · ? ayuda"),
      el("button", { type: "button", class: "primario" }, "Cerrar"));
      dialogo.lastChild.addEventListener("click", () => dialogo.close());
      document.body.append(dialogo);
    }
    dialogo.showModal();
  }

  function alternarPantallaCompleta() {
    const escena = $m("medios-escena");
    if (document.fullscreenElement) document.exitFullscreen?.();
    else escena.requestFullscreen?.();
  }

  function manejarRueda(e) {
    if (!estado.activo) return;
    e.preventDefault();
    volumen(Number($m("medios-volumen").value) + (e.deltaY < 0 ? 5 : -5));
  }

  function atajos(e) {
    if (!estado.activo || ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName) ||
      document.activeElement.isContentEditable) return;
    const v = video(), k = e.key.toLowerCase();
    if (k === "escape") { if (document.fullscreenElement) document.exitFullscreen?.(); else return; }
    else if (k === " " || k === "spacebar") {
      e.preventDefault(); iniciarAudio(); v.paused ? v.play() : v.pause();
      mostrarOSD(v.paused ? "Pausa" : "Reproduciendo");
    }
    else if (k === "f") { alternarPantallaCompleta(); mostrarOSD("Pantalla completa"); }
    else if (k === "s" && e.shiftKey) { captura(); mostrarOSD("Captura PNG guardada"); }
    else if (k === "s") { v.pause(); v.currentTime = 0; mostrarOSD("Detenido"); }
    else if (k === "n") { siguiente(); mostrarOSD("Siguiente"); }
    else if (k === "p") { siguiente(-1); mostrarOSD("Anterior"); }
    else if (k === "m") { v.muted = !v.muted; mostrarOSD(v.muted ? "Silencio" : "Sonido"); }
    else if (k === "arrowright" || k === "arrowleft") desplazar(e);
    else if (k === "arrowup" || k === "arrowdown") volumen(Number($m("medios-volumen").value) + (k === "arrowup" ? 5 : -5));
    else if (k === "[") cambiarVelocidad(v.playbackRate - 0.1);
    else if (k === "]") cambiarVelocidad(v.playbackRate + 0.1);
    else if (k === "=") cambiarVelocidad(1);
    else if (k === "e") { v.pause(); v.currentTime += 1 / 30; mostrarOSD("Fotograma +1/30 s"); }
    else if (k === "a") cambiarAspecto();
    else if (k === "v") cambiarSubtitulos();
    else if (k === "g") retrasarSubtitulos(-50);
    else if (k === "h") retrasarSubtitulos(50);
    else if (k === "l") cambiarRepetir();
    else if (k === "r") {
      estado.aleatorio = !estado.aleatorio;
      mostrarOSD(estado.aleatorio ? "Aleatorio activado" : "Aleatorio desactivado");
    }
    else if (k === "t") alternarTiempo();
    else if (k === "i") mostrarInformacion();
    else if (k === "?") mostrarAyuda();
    else if (/^[0-9]$/.test(k) && v.duration) {
      v.currentTime = Number(k) / 10 * v.duration;
      mostrarOSD(`${Number(k) * 10} %`);
    }
    else return;
    e.preventDefault();
  }

  function desplazar(e) {
    const signo = e.key === "ArrowRight" ? 1 : -1;
    const segundosSalto = e.ctrlKey && e.altKey ? 300 : e.ctrlKey ? 60 : e.shiftKey ? 3 : 10;
    video().currentTime += signo * segundosSalto;
    mostrarOSD(`${segundos(video().currentTime)} · ${signo > 0 ? "+" : "-"}${segundosSalto} s`);
  }

  function alternarTiempo() {
    estado.mostrarRestante = !estado.mostrarRestante;
    pintarTiempo();
  }

  function pintarTiempo() {
    const v = video(), restante = Math.max(0, v.duration - v.currentTime);
    $m("medios-tiempo").textContent = estado.mostrarRestante ? `-${segundos(restante)}` :
      `${segundos(v.currentTime)} / ${segundos(v.duration)}`;
  }

  function prepararControles() {
    const v = video(), escena = $m("medios-escena"), controles = $m("medios-controles");
    $m("medios-play").addEventListener("click", () => { iniciarAudio(); v.paused ? v.play() : v.pause(); });
    $m("medios-stop").addEventListener("click", () => { v.pause(); v.currentTime = 0; });
    $m("medios-prev").addEventListener("click", () => siguiente(-1));
    $m("medios-next").addEventListener("click", () => siguiente());
    $m("medios-mute").addEventListener("click", () => { v.muted = !v.muted; mostrarOSD(v.muted ? "Silencio" : "Sonido"); });
    $m("medios-volumen").addEventListener("input", (e) => volumen(e.target.value));
    $m("medios-velocidad").addEventListener("change", (e) => cambiarVelocidad(e.target.value));
    $m("medios-repetir").addEventListener("click", cambiarRepetir);
    $m("medios-aleatorio").addEventListener("click", () => {
      estado.aleatorio = !estado.aleatorio;
      mostrarOSD(estado.aleatorio ? "Aleatorio activado" : "Aleatorio desactivado");
    });
    $m("medios-aspecto").addEventListener("click", cambiarAspecto);
    $m("medios-subtitulos").addEventListener("click", cambiarSubtitulos);
    $m("medios-captura").addEventListener("click", captura);
    $m("medios-info").addEventListener("click", mostrarInformacion);
    $m("medios-full").addEventListener("click", alternarPantallaCompleta);
    $m("medios-ayuda").addEventListener("click", mostrarAyuda);
    $m("medios-bucle").addEventListener("click", alternarBucle);
    $m("medios-tiempo").addEventListener("click", alternarTiempo);
    $m("medios-progreso").addEventListener("input", (e) => {
      if (v.duration) v.currentTime = e.target.value / 1000 * v.duration;
    });
    $m("medios-progreso").addEventListener("pointermove", (e) => {
      if (!v.duration) return;
      const rect = e.currentTarget.getBoundingClientRect(), tiempo = (e.clientX - rect.left) / rect.width * v.duration;
      e.currentTarget.title = segundos(tiempo);
    });
    $m("medios-escena").addEventListener("dblclick", alternarPantallaCompleta);
    $m("medios-video").addEventListener("wheel", manejarRueda, { passive: false });
    v.addEventListener("timeupdate", () => {
      $m("medios-progreso").value = v.duration ? v.currentTime / v.duration * 1000 : 0;
      pintarTiempo();
      if (estado.bucleB !== null && v.currentTime >= estado.bucleB) v.currentTime = estado.bucleA;
      if (!v.paused) programarGuardado();
    });
    v.addEventListener("pause", guardarProgreso);
    v.addEventListener("ended", () => {
      if (estado.repetir === 1) reproducir(estado.actual);
      else if (estado.repetir === 2) siguiente();
    });
    v.addEventListener("durationchange", pintarTiempo);
    v.addEventListener("mousemove", () => mostrarControles(true));
    escena.addEventListener("fullscreenchange", () => mostrarControles(true));
    controles.addEventListener("mousemove", () => mostrarControles(true));
  }

  function mostrarControles(mostrar) {
    const escena = $m("medios-escena");
    if (!document.fullscreenElement) { escena.classList.remove("controles-ocultos"); return; }
    escena.classList.toggle("controles-ocultos", !mostrar);
    clearTimeout(idleTimer);
    if (mostrar) idleTimer = setTimeout(() => escena.classList.add("controles-ocultos"), 2500);
  }

  function prepararArchivos() {
    $m("medios-carpeta").addEventListener("click", async () => {
      if (!window.showDirectoryPicker) { $m("medios-input-dir").click(); return; }
      try {
        const handle = await window.showDirectoryPicker({ mode: "read" });
        await guardarCarpeta(handle);
        cargar(await archivosDeManija(handle), handle.name);
      } catch (_) { /* cancelado */ }
    });
    $m("medios-archivos").addEventListener("click", () => $m("medios-input").click());
    $m("medios-input").addEventListener("change", (e) => cargar([...e.target.files]));
    $m("medios-input-dir").addEventListener("change", (e) => cargar([...e.target.files]));
    const zona = $m("medios-soltar");
    ["dragenter", "dragover"].forEach((tipo) => zona.addEventListener(tipo, (e) => {
      e.preventDefault(); zona.classList.add("arrastrando");
    }));
    zona.addEventListener("dragleave", () => zona.classList.remove("arrastrando"));
    zona.addEventListener("drop", async (e) => {
      e.preventDefault(); zona.classList.remove("arrastrando");
      const archivos = [];
      for (const item of e.dataTransfer.items) {
        const entrada = item.webkitGetAsEntry?.();
        if (entrada) archivos.push(...await leerEntrada(entrada));
        else if (item.getAsFile()) archivos.push(item.getAsFile());
      }
      cargar(archivos);
    });
    $m("medios-buscar").addEventListener("input", pintarLista);
    $m("medios-vaciar").addEventListener("click", () => {
      video().pause(); liberarURLs(); estado.archivos = []; estado.actual = -1; pintarLista();
      $m("medios-titulo").textContent = "Abre una carpeta o unos archivos para empezar";
    });
    $m("medios-enviar").addEventListener("click", enviarATele);
  }

  async function enviarATele() {
    const f = estado.archivos[estado.actual];
    if (!f) return;
    const h = f._huella || await huella(f);
    window.dispatchEvent(new CustomEvent("aria:medios-enviar", {
      detail: { archivo: f, huella: h, nombre: nombreRuta(f), posicion: video().currentTime, subtitulos: subtituloPara(f) }
    }));
    if (!window.MediosTele) toast("Muy pronto");
  }

  async function prepararContinuar() {
    const handle = await leerCarpetaGuardada();
    if (!handle) return;
    const zona = $m("medios-continuar");
    zona.hidden = false;
    const boton = el("button", { type: "button", class: "fantasma" }, `Continuar con “${handle.name}”`);
    boton.addEventListener("click", continuarConCarpeta);
    zona.replaceChildren(boton);
  }

  function iniciar() {
    if (!$m("medios-video") || Medios.iniciado) return;
    Medios.iniciado = true;
    prepararControles();
    prepararArchivos();
    document.addEventListener("keydown", atajos);
    document.addEventListener("visibilitychange", guardarProgreso);
    window.addEventListener("pagehide", guardarProgreso);
    prepararContinuar();
  }

  function activar(activo) { estado.activo = activo; }
  function archivo(huellaArchivo) { return estado.archivos.find((f) => f._huella === huellaArchivo) || null; }
  function subtitulo(huellaArchivo) {
    const f = archivo(huellaArchivo), s = f && subtituloPara(f);
    return s ? estado.subtitulos.get(s)?.blob || s : null;
  }

  return { iniciar, activar, archivo, subtitulo };
})();
window.Medios = Medios;
