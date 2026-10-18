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

  // Controles como en la app Tapo: mover (si tiene motor), privacidad, detecciones, LED, foto, sonido y pantalla completa.
  function controles(camara, video, alCambiar) {
    const enviar = async (ruta, json) => {
      const r = await api(ruta, { method: "POST", json });
      if (!r.ok) toast(r.data.error || "La cámara no ha respondido.", "mal");
      return r;
    };
    const boton = (texto, titulo, accion, clase = "fantasma pequeno") => {
      const b = el("button", { type: "button", class: clase, title: titulo, ariaLabel: titulo }, texto);
      b.addEventListener("click", async () => { b.disabled = true; try { await accion(); } finally { b.disabled = false; } });
      return b;
    };
    const partes = [];
    if (camara.ptz) {
      const mover = (dir) => () => enviar("/api/hogar/camaras/mover", { ip: camara.ip, direccion: dir });
      partes.push(el("div", { class: "camara-ptz", role: "group", ariaLabel: "Mover la cámara" },
        el("span"), boton("▲", "Arriba", mover("arriba")), el("span"),
        boton("◀", "Izquierda", mover("izquierda")), el("span", { class: "camara-ptz-centro" }), boton("▶", "Derecha", mover("derecha")),
        el("span"), boton("▼", "Abajo", mover("abajo")), el("span")));
    }
    const ajustes = [["privacidad", "Privacidad (lente tapada)"], ["movimiento", "Detección de movimiento"], ["personas", "Detección de personas"], ["led", "Luz indicadora (LED)"]]
      .filter(([campo]) => camara[campo] !== undefined)
      .map(([campo, texto]) => {
        const c = el("input", { type: "checkbox", checked: !!camara[campo] });
        c.addEventListener("change", async () => {
          c.disabled = true;
          const r = await enviar("/api/hogar/camaras/ajuste", { ip: camara.ip, campo, valor: c.checked });
          if (r.ok) { Object.assign(camara, r.data.camara); alCambiar?.(camara); } else c.checked = !c.checked;
          c.disabled = false;
        });
        return el("label", { class: "interruptor hogar-interruptor" }, c, el("span", null, texto));
      });
    const sonido = boton("Activar sonido", "Activar o quitar el sonido", () => { video.muted = !video.muted; sonido.textContent = video.muted ? "Activar sonido" : "Quitar sonido"; });
    const completa = boton("Pantalla completa", "Pantalla completa", () => (video.requestFullscreen || video.webkitEnterFullscreen)?.call(video));
    const instantanea = boton("Guardar foto", "Guardar una foto", async () => {
      const r = await fetch("/api/hogar/camaras/foto?ip=" + encodeURIComponent(camara.ip));
      if (!r.ok) { toast("La cámara no ha enviado imagen.", "mal"); return; }
      const a = el("a", { href: URL.createObjectURL(await r.blob()), download: camara.nombre.replace(/[^\wáéíóúñ -]/gi, "") + " " + new Date().toLocaleString("es-ES").replace(/[/:]/g, "-") + ".jpg" });
      a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    });
    const bateria = camara.bateria !== undefined ? el("span", { class: "camara-bateria" + (camara.bateria < 20 ? " baja" : "") }, "Batería: " + camara.bateria + " %") : null;
    return el("div", { class: "camara-controles" }, ...partes,
      el("div", { class: "camara-ajustes" }, ...ajustes),
      el("div", { class: "botones camara-botones" }, sonido, completa, instantanea, bateria));
  }

  function abrir(camara, alCambiar) {
    const video = el("video", { class: "camara-video", autoplay: true, muted: true, playsInline: true });
    const estado = el("p", { class: "muted camara-estado", role: "status" }, "Conectando con la cámara… (las de batería tardan unos segundos en despertar)");
    const foto = el("img", { class: "camara-video", alt: "Última imagen de " + camara.nombre, hidden: true });
    const d = dialogo(camara.nombre, el("div", { class: "camara-visor" }, el("div", null, video, foto, estado), controles(camara, video, alCambiar)));
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
