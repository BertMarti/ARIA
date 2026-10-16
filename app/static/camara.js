"use strict";
// Cámara: solo se abre tras una petición explícita y se apaga en cualquier salida.
const Camara = (() => {
  const disponible = () => !!(window.isSecureContext && navigator.mediaDevices?.getUserMedia);
  let dialogo = null, stream = null, resolver = null, reloj = null, anterior = null;

  function limpiar() {
    clearTimeout(reloj); reloj = null;
    if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
    const d = dialogo; dialogo = null; resolver = null;
    if (d?.open) d.close();
    d?.remove();
    if (anterior?.focus) anterior.focus();
    anterior = null;
  }
  function cancelar() { if (resolver) resolver(null); limpiar(); }
  function cerrar(e) { if (resolver && !e?.detail) resolver(null); limpiar(); }
  function enfocar(e) {
    if (e.key !== "Tab" || !dialogo) return;
    const foc = [...dialogo.querySelectorAll("button:not(:disabled), [tabindex]:not([tabindex=\"-1\"])" )];
    if (!foc.length) return;
    const i = foc.indexOf(document.activeElement);
    if (e.shiftKey && (i <= 0 || i < 0)) { e.preventDefault(); foc.at(-1).focus(); }
    else if (!e.shiftKey && (i === foc.length - 1 || i < 0)) { e.preventDefault(); foc[0].focus(); }
  }
  function construir() {
    const video = el("video", { class: "camara-video", autoplay: true, muted: true, playsInline: true, "aria-label": "Vista previa de la cámara" });
    const estado = el("p", { class: "camara-encendida", role: "status" }, "● Cámara encendida");
    const hacer = el("button", { type: "button", class: "primario camara-foto", "aria-label": "Hacer foto" }, "Hacer foto");
    const cambiar = el("button", { type: "button", class: "fantasma camara-cambiar", "aria-label": "Cambiar cámara" }, "Cambiar cámara");
    const cancelarBtn = el("button", { type: "button", class: "fantasma", "aria-label": "Cancelar" }, "Cancelar");
    dialogo = el("dialog", { class: "camara-dialogo", "aria-labelledby": "camara-titulo" },
      el("h2", { id: "camara-titulo" }, "¿Qué ves?"), estado, video,
      el("div", { class: "camara-acciones" }, hacer, cambiar, cancelarBtn));
    dialogo.setAttribute("aria-labelledby", "camara-titulo");
    video.setAttribute("aria-label", "Vista previa de la cámara");
    hacer.setAttribute("aria-label", "Hacer foto"); cambiar.setAttribute("aria-label", "Cambiar cámara"); cancelarBtn.setAttribute("aria-label", "Cancelar");
    hacer.addEventListener("click", async () => {
      if (!stream || !video.videoWidth) return;
      const c = document.createElement("canvas"), k = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight));
      c.width = Math.max(1, Math.round(video.videoWidth * k)); c.height = Math.max(1, Math.round(video.videoHeight * k));
      const g = c.getContext("2d"); g.drawImage(video, 0, 0, c.width, c.height);
      const p = new Promise((ok) => c.toBlob(ok, "image/jpeg", .85));
      const r = resolver; limpiar();
      r(await p);
    });
    cambiar.addEventListener("click", async () => {
      if (!stream) return;
      const dispositivos = await navigator.mediaDevices.enumerateDevices();
      const cams = dispositivos.filter((d) => d.kind === "videoinput");
      if (cams.length < 2) return;
      const actual = stream.getVideoTracks()[0]?.getSettings().deviceId;
      const siguiente = cams[(cams.findIndex((d) => d.deviceId === actual) + 1) % cams.length];
      try {
        const nuevo = await navigator.mediaDevices.getUserMedia({ video: { deviceId: { exact: siguiente.deviceId }, width: { ideal: 1280 } } });
        stream.getTracks().forEach((t) => t.stop()); stream = nuevo; video.srcObject = nuevo;
      } catch (e) { toast(error(e), "mal"); }
    });
    cancelarBtn.addEventListener("click", cancelar);
    dialogo.addEventListener("cancel", (e) => { e.preventDefault(); cancelar(); });
    dialogo.addEventListener("close", cerrar);
    dialogo.addEventListener("keydown", enfocar);
    document.body.append(dialogo);
    return { video, cambiar };
  }
  function error(e) {
    if (e?.name === "NotAllowedError" || e?.name === "SecurityError") return "Permiso de cámara denegado. Actívalo desde el candado de la barra de direcciones.";
    if (e?.name === "NotFoundError" || e?.name === "OverconstrainedError") return "No se encontró ninguna cámara.";
    if (e?.name === "InsecureContextError") return "La cámara solo funciona por HTTPS.";
    return "No se pudo abrir la cámara.";
  }
  async function capturar() {
    if (!disponible()) { toast("La cámara solo funciona por HTTPS.", "mal"); return null; }
    if (resolver) cancelar();
    anterior = document.activeElement;
    const ui = construir();
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1280 } } });
      ui.video.srcObject = stream;
      const cams = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
      ui.cambiar.hidden = cams.length < 2;
      dialogo.showModal(); ui.video.focus();
      reloj = setTimeout(cancelar, 60000);
      return await new Promise((ok) => { resolver = ok; });
    } catch (e) { limpiar(); toast(error(e), "mal"); return null; }
  }
  document.addEventListener("visibilitychange", () => { if (document.hidden && resolver) cancelar(); });
  addEventListener("pagehide", () => { if (resolver) cancelar(); });
  return { disponible, capturar };
})();
