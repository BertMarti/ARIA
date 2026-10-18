"use strict";
// Directo de una cámara: vídeo MSE (fMP4) que go2rtc manda por WebSocket a través de ARIA. Sin librerías.
const CamaraDirecto = (() => {
  const CODECS = ["avc1.640029", "avc1.64002A", "avc1.640033", "hvc1.1.6.L153.B0", "mp4a.40.2", "mp4a.40.5", "flac", "opus"];
  const soportados = () => CODECS.filter((c) => window.MediaSource && MediaSource.isTypeSupported('video/mp4; codecs="' + c + '"')).join(",");

  function dialogo(titulo, ...contenido) {
    const cerrar = el("button", { type: "button", class: "dialogo-cerrar", ariaLabel: "Cerrar" }, "×");
    const d = el("dialog", { class: "dialogo camara-dialogo" }, el("header", { class: "dialogo-cab" }, el("h2", null, titulo), cerrar),
      el("div", { class: "dialogo-cuerpo" }, ...contenido));
    cerrar.addEventListener("click", () => d.close());
    document.body.append(d);
    d.showModal();
    return d;
  }

  function abrir(camara) {
    const video = el("video", { class: "camara-video", autoplay: true, muted: true, playsInline: true, controls: true });
    const estado = el("p", { class: "muted camara-estado", role: "status" }, "Conectando con la cámara… (las de batería tardan unos segundos en despertar)");
    const foto = el("img", { class: "camara-video", alt: "Última imagen de " + camara.nombre, hidden: true });
    const d = dialogo(camara.nombre, video, foto, estado);
    let ws = null, url = null, cerrado = false;
    const fin = () => { cerrado = true; try { ws?.close(); } catch (_) { /* ya cerrado */ } if (url) URL.revokeObjectURL(url); d.remove(); };
    d.addEventListener("close", fin);

    // Sin MSE (algunos iPhone): una foto cada 5 s mientras el diálogo esté abierto.
    if (!soportados()) {
      video.hidden = true; foto.hidden = false;
      const refrescar = () => { if (cerrado) return; foto.src = "/api/hogar/camaras/foto?ip=" + encodeURIComponent(camara.ip) + "&t=" + Date.now(); };
      foto.addEventListener("load", () => { estado.textContent = "Imagen cada 5 segundos (este navegador no reproduce el directo)."; setTimeout(refrescar, 5000); });
      foto.addEventListener("error", () => { estado.textContent = "La cámara no ha enviado imagen."; });
      refrescar();
      return;
    }
    const ms = new MediaSource();
    url = URL.createObjectURL(ms);
    video.src = url;
    let sb = null;
    const cola = [];
    const volcar = () => {
      if (!sb || sb.updating || !cola.length) return;
      try { sb.appendBuffer(cola.shift()); } catch (_) { cola.length = 0; }
    };
    ms.addEventListener("sourceopen", () => {
      ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/api/hogar/camaras/directo?ip=" + encodeURIComponent(camara.ip));
      ws.binaryType = "arraybuffer";
      ws.addEventListener("open", () => ws.send(JSON.stringify({ type: "mse", value: soportados() })));
      ws.addEventListener("message", (e) => {
        if (typeof e.data === "string") {
          let m = {};
          try { m = JSON.parse(e.data); } catch (_) { return; }
          if (m.type === "mse" && !sb) {
            sb = ms.addSourceBuffer(m.value);
            sb.mode = "segments";
            sb.addEventListener("updateend", () => {
              // Siempre en directo: si se acumula retraso, se salta al final y se libera lo viejo.
              const b = video.buffered;
              if (b.length) {
                const final = b.end(b.length - 1);
                if (final - video.currentTime > 2) video.currentTime = final - 0.3;
                if (!sb.updating && video.currentTime - b.start(0) > 20) { try { sb.remove(b.start(0), video.currentTime - 10); return; } catch (_) { /* sigue */ } }
              }
              volcar();
            });
            estado.textContent = "En directo";
          } else if (m.type === "error") {
            estado.textContent = "La cámara no responde (¿dormida, sin batería o en modo privacidad?).";
          }
          return;
        }
        cola.push(e.data);
        volcar();
      });
      ws.addEventListener("close", () => { if (!cerrado && estado.textContent !== "En directo") estado.textContent = "No se ha podido abrir el directo de esta cámara."; else if (!cerrado) estado.textContent = "Directo terminado."; });
    }, { once: true });
  }
  return { abrir };
})();
