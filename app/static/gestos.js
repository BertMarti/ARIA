"use strict";
// Control del HUD con una mano. El vídeo y las imágenes de MediaPipe permanecen en el navegador.
const Gestos = (() => {
  const URL_WASM = "/static/vendor/mediapipe/wasm";
  const URL_MODELO = "/static/vendor/mediapipe/hand_landmarker.task";
  const reducido = matchMedia("(prefers-reduced-motion: reduce)");
  let landmarker = null, stream = null, video = null, canvas = null, ctx = null, vista = null;
  let encendido = false, frame = 0, ultimoFrame = 0, ultimaMano = 0, inicioPinza = 0, ultimoClic = 0, ciclo = 0;
  let puño = null, puñoDesde = 0, ampliada = null, ultimoPulgar = 0, pulgarDesde = 0, inicioDeslizar = null;
  let etiqueta = null, etiquetaTimer = 0, preparando = null;

  function disponible() {
    if (!navigator.mediaDevices?.getUserMedia || typeof WebAssembly === "undefined") return false;
    try {
      // Comprueba que el navegador puede cargar WebAssembly antes de mostrar la opción.
      return WebAssembly.validate(new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0]));
    } catch (_) { return false; }
  }
  function emitir(nombre, detalle) { window.dispatchEvent(new CustomEvent("aria:gesto-" + nombre, { detail: detalle || {} })); }
  function rotulo(texto, x, y) {
    if (!etiqueta) return;
    etiqueta.textContent = texto; etiqueta.style.left = x + "px"; etiqueta.style.top = y + "px"; etiqueta.classList.add("visible");
    clearTimeout(etiquetaTimer); etiquetaTimer = setTimeout(() => etiqueta.classList.remove("visible"), 850);
  }
  function crearVista() {
    vista = el("div", { class: "gestos-vista" }); vista.hidden = true;
    video = el("video", { muted: "", playsinline: "" }); video.muted = true; video.setAttribute("aria-hidden", "true");
    canvas = el("canvas", { width: "320", height: "240" }); canvas.setAttribute("aria-hidden", "true"); ctx = canvas.getContext("2d");
    vista.append(video, canvas, el("span", { class: "gestos-estado" }, "● Cámara (gestos)"));
    etiqueta = el("span", { class: "gestos-rotulo" }); $("v-hud").append(vista, etiqueta);
  }
  async function preparar() {
    if (preparando) return preparando;
    preparando = (async () => {
      const v = await import("/static/vendor/mediapipe/vision_bundle.mjs");
      const fs = await v.FilesetResolver.forVisionTasks(URL_WASM);
      try { return await v.HandLandmarker.createFromOptions(fs, { baseOptions: { modelAssetPath: URL_MODELO, delegate: "GPU" }, runningMode: "VIDEO", numHands: 1 }); }
      catch (_) { return v.HandLandmarker.createFromOptions(fs, { baseOptions: { modelAssetPath: URL_MODELO, delegate: "CPU" }, runningMode: "VIDEO", numHands: 1 }); }
    })();
    try { landmarker = await preparando; return landmarker; } finally { preparando = null; }
  }
  function dibujar(puntos) {
    if (!ctx) return; ctx.clearRect(0, 0, 320, 240); if (!puntos) return;
    const lineas = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[17,18],[18,19],[19,20],[0,17]];
    ctx.strokeStyle = "rgba(56,214,255,.85)"; ctx.lineWidth = 3; ctx.beginPath();
    for (const [a,b] of lineas) { ctx.moveTo(puntos[a].x * 320, puntos[a].y * 240); ctx.lineTo(puntos[b].x * 320, puntos[b].y * 240); } ctx.stroke();
    ctx.fillStyle = "#e8f4ff"; for (const p of puntos) { ctx.beginPath(); ctx.arc(p.x * 320, p.y * 240, 3, 0, Math.PI * 2); ctx.fill(); }
  }
  function abierta(p) { return [8, 12, 16, 20].every((i) => p[i].y < p[i - 2].y - .025); }
  function cerrada(p) { return [8, 12, 16, 20].every((i) => Math.hypot(p[i].x - p[0].x, p[i].y - p[0].y) < .22); }
  function pulgarArriba(p) { return p[4].y < p[3].y && [8, 12, 16, 20].every((i) => p[i].y > p[i - 2].y); }
  function punto(p) { return { x: 1 - p[8].x, y: p[8].y }; }
  function cursor(p) {
    const sec = $("v-hud"), r = sec.getBoundingClientRect(), q = punto(p), x = r.left + q.x * r.width, y = r.top + q.y * r.height;
    sec.style.setProperty("--px", (q.x - .5).toFixed(3)); sec.style.setProperty("--py", (q.y - .5).toFixed(3));
    const c = $("hud-cursor"); c.style.transform = `translate(${x}px, ${y}px)`;
    if (optsCursor()) c.style.opacity = "1";
    return { x, y };
  }
  function optsCursor() { return $("v-hud")?.classList.contains("con-cursor"); }
  function procesar(p, ahora) {
    const q = cursor(p), abiertaAhora = abierta(p), cerradaAhora = cerrada(p), pinza = Math.hypot(p[4].x - p[8].x, p[4].y - p[8].y) < .05;
    if (pinza) { inicioPinza ||= ahora; if (ahora - inicioPinza >= 120 && ahora - ultimoClic > 600) { ultimoClic = ahora; inicioPinza = 0; const n = document.elementFromPoint(q.x, q.y); n?.click(); $("hud-cursor").classList.add("gestos-destello"); setTimeout(() => $("hud-cursor").classList.remove("gestos-destello"), reducido.matches ? 0 : 360); rotulo("Clic", q.x, q.y); } } else inicioPinza = 0;
    const tarjeta = document.elementFromPoint(q.x, q.y)?.closest?.(".hud-card");
    if (cerradaAhora && tarjeta) { if (puño !== tarjeta) { if (ampliada === tarjeta) { tarjeta.classList.remove("ampliada"); ampliada = null; rotulo("Cerrar", q.x, q.y); } else { puño = tarjeta; puñoDesde = ahora; tarjeta.classList.add("agarrada"); rotulo("Agarrar", q.x, q.y); } } else if (ahora - puñoDesde >= 1500 && ampliada !== tarjeta) { ampliada?.classList.remove("ampliada"); ampliada = tarjeta; tarjeta.classList.add("ampliada"); rotulo("Ampliar", q.x, q.y); } }
    if (abiertaAhora && puño) { puño.classList.remove("agarrada"); puño = null; }
    if (abiertaAhora) {
      if (!inicioDeslizar) inicioDeslizar = { x: q.x, y: q.y, t: ahora };
      else if (ahora - inicioDeslizar.t < 400 && (Math.abs(q.x - inicioDeslizar.x) > .35 || Math.abs(q.y - inicioDeslizar.y) > .35)) { const dx = q.x - inicioDeslizar.x, dy = q.y - inicioDeslizar.y; emitir(Math.abs(dx) > Math.abs(dy) ? "tema" : "panel", { direccion: Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "siguiente" : "anterior") : (dy < 0 ? "abrir" : "cerrar") }); rotulo(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "Tema ▶" : "◀ Tema") : (dy < 0 ? "Opciones" : "Cerrar"), q.x, q.y); inicioDeslizar = null; }
    } else inicioDeslizar = null;
    if (pulgarArriba(p)) { pulgarDesde ||= ahora; if (ahora - pulgarDesde > 1000 && ahora - ultimoPulgar > 2000) { ultimoPulgar = ahora; emitir("briefing"); rotulo("Briefing", q.x, q.y); } } else pulgarDesde = 0;
  }
  function bucle(ahora) {
    if (!encendido || !video || video.readyState < 2) return;
    if (ahora - ultimoFrame >= 66) { ultimoFrame = ahora; const r = landmarker.detectForVideo(video, ahora); const p = r.landmarks?.[0]; dibujar(p); if (p) { ultimaMano = ahora; procesar(p, ahora); } else if (ahora - ultimaMano > 300000) desactivar(); }
    frame = video.requestVideoFrameCallback ? video.requestVideoFrameCallback(bucle) : requestAnimationFrame(bucle);
  }
  async function activar() {
    if (encendido) return true; if (!disponible()) { toast("Tu navegador no permite gestos con cámara (WebAssembly/SIMD no disponible).", "mal"); return false; }
    const miCiclo = ++ciclo;
    try { crearVista(); landmarker = landmarker || await preparar(); const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: 640, height: 480 } }); if (miCiclo !== ciclo) { s.getTracks().forEach((t) => t.stop()); return false; } stream = s; video.srcObject = stream; await video.play(); encendido = true; ultimaMano = performance.now(); vista.hidden = false; frame = video.requestVideoFrameCallback ? video.requestVideoFrameCallback(bucle) : requestAnimationFrame(bucle); return true; }
    catch (_) { desactivar(); toast("No se pudo activar la cámara para los gestos. Comprueba el permiso del navegador.", "mal"); return false; }
  }
  function desactivar() { ciclo++; encendido = false; if (frame) { video?.cancelVideoFrameCallback?.(frame); cancelAnimationFrame(frame); frame = 0; } stream?.getTracks().forEach((t) => t.stop()); stream = null; if (video) video.srcObject = null; vista && (vista.hidden = true); puño?.classList.remove("agarrada"); ampliada?.classList.remove("ampliada"); puño = null; ampliada = null; }
  document.addEventListener("visibilitychange", () => { if (document.hidden) desactivar(); });
  return { disponible, activar, desactivar, activo: () => encendido };
})();
