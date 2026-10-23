"use strict";
// Directo de una cámara: vídeo MSE (fMP4) que go2rtc manda por WebSocket a través de ARIA. Sin librerías.
const CamaraDirecto = (() => {
  const CODECS = ["avc1.640029", "avc1.64002A", "avc1.640033", "hvc1.1.6.L153.B0", "mp4a.40.2", "mp4a.40.5", "flac", "opus"];
  const soportados = () => CODECS.filter((c) => window.MediaSource && MediaSource.isTypeSupported('video/mp4; codecs="' + c + '"')).join(",");

  // Hablar por la cámara: micrófono -> WebRTC (solo envío) -> go2rtc -> altavoz de la cámara. La señalización va por
  // el WebSocket de ARIA (con sesión); el audio, directo a la Pi por el puerto 8555 (en casa o con la VPN).
  function hablar(camara, aviso) {
    let pc = null, ws = null, pista = null;
    const parar = () => {
      try { ws?.close(); } catch (_) { /* ya cerrado */ }
      try { pc?.close(); } catch (_) { /* ya cerrado */ }
      pista?.stop();
      pc = ws = pista = null;
    };
    const empezar = async () => {
      if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) { aviso("Este navegador no permite hablar por la cámara."); return false; }
      try {
        pista = (await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })).getAudioTracks()[0];
      } catch (_) { aviso("Sin permiso para usar el micrófono."); return false; }
      pc = new RTCPeerConnection({ iceServers: [] });
      pc.addTransceiver(pista, { direction: "sendonly" });
      ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/api/hogar/camaras/directo?ip=" + encodeURIComponent(camara.ip));
      const enviar = (tipo, valor) => { if (ws?.readyState === 1) ws.send(JSON.stringify({ type: tipo, value: valor })); };
      pc.addEventListener("icecandidate", (e) => { if (e.candidate) enviar("webrtc/candidate", e.candidate.candidate); });
      pc.addEventListener("connectionstatechange", () => {
        if (!pc) return;
        if (pc.connectionState === "connected") aviso("Hablando: te escuchan por la cámara.");
        else if (pc.connectionState === "failed") aviso("No se puede hablar desde aquí: funciona en casa o con la VPN HEIMDALL conectada.");
      });
      ws.addEventListener("open", async () => {
        const oferta = await pc.createOffer();
        await pc.setLocalDescription(oferta);
        enviar("webrtc/offer", oferta.sdp);
      });
      ws.addEventListener("message", async (e) => {
        if (typeof e.data !== "string" || !pc) return;
        let m = {};
        try { m = JSON.parse(e.data); } catch (_) { return; }
        if (m.type === "webrtc/answer") await pc.setRemoteDescription({ type: "answer", sdp: m.value });
        else if (m.type === "webrtc/candidate" && m.value) { try { await pc.addIceCandidate({ candidate: m.value, sdpMid: "0" }); } catch (_) { /* candidato no válido */ } }
        else if (m.type === "error") aviso("La cámara no acepta audio ahora mismo.");
      });
      aviso("Conectando el micrófono con la cámara…");
      return true;
    };
    return { empezar, parar };
  }

  function dialogo(titulo, ...contenido) {
    const cerrar = el("button", { type: "button", class: "dialogo-cerrar", ariaLabel: "Cerrar" }, "×");
    const d = el("dialog", { class: "dialogo camara-dialogo" }, el("header", { class: "dialogo-cab" }, el("h2", null, titulo), cerrar),
      el("div", { class: "dialogo-cuerpo" }, ...contenido));
    cerrar.addEventListener("click", () => d.close());
    document.body.append(d);
    d.showModal();
    return d;
  }

  // Posiciones guardadas en la cámara (solo con motor): tocar una la mueve allí; «Guardar esta posición» apunta la vista
  // actual con un nombre; la × borra (las fijas de fábrica no se pueden borrar). Se cargan al abrir el visor.
  function posiciones(camara, enviar) {
    const lista = el("div", { class: "camara-posiciones-lista" });
    const aviso = el("p", { class: "muted camara-posiciones-aviso", role: "status" }, "Cargando posiciones…");
    const ruta = "/api/hogar/camaras/posiciones";
    const pintar = (items) => {
      lista.replaceChildren(...items.map((p) => {
        const ir = el("button", { type: "button", class: "fantasma pequeno camara-posicion-ir", title: "Ir a " + p.nombre }, p.nombre);
        ir.addEventListener("click", async () => { ir.disabled = true; try { await enviar(ruta + "/ir", { ip: camara.ip, id: p.id }); } finally { ir.disabled = false; } });
        const quitar = p.fija ? null : el("button", { type: "button", class: "camara-posicion-quitar", title: "Borrar", ariaLabel: "Borrar la posición " + p.nombre }, "×");
        quitar?.addEventListener("click", async () => {
          if (!await confirmar("Borrar posición", "¿Borrar la posición «" + p.nombre + "» de la cámara?", "Borrar")) return;
          quitar.disabled = true;
          const r = await api(ruta + "?ip=" + encodeURIComponent(camara.ip) + "&id=" + encodeURIComponent(p.id), { method: "DELETE" });
          if (r.ok) pintar(r.data.posiciones || []); else { quitar.disabled = false; toast(r.data.error || "No se ha podido borrar la posición.", "mal"); }
        });
        return el("span", { class: "camara-posicion" }, ir, quitar);
      }));
      aviso.hidden = items.length > 0;
      aviso.textContent = items.length ? "" : "Sin posiciones guardadas: mueve la cámara y guarda la vista.";
    };
    const nombre = el("input", { type: "text", maxLength: 30, required: true, placeholder: "Nombre (p. ej. puerta)", ariaLabel: "Nombre de la posición" });
    const formulario = el("form", { class: "camara-posiciones-nueva", hidden: true }, nombre, el("button", { type: "submit", class: "primario pequeno" }, "Guardar"));
    const nueva = el("button", { type: "button", class: "fantasma pequeno", ariaExpanded: "false" }, "＋ Guardar esta posición");
    nueva.addEventListener("click", () => { formulario.hidden = !formulario.hidden; nueva.ariaExpanded = String(!formulario.hidden); if (!formulario.hidden) nombre.focus(); });
    formulario.addEventListener("submit", async (e) => {
      e.preventDefault();
      const r = await enviar(ruta, { ip: camara.ip, nombre: nombre.value.trim() });
      if (r.ok) { pintar(r.data.posiciones || []); formulario.hidden = true; nueva.ariaExpanded = "false"; nombre.value = ""; toast("Posición guardada."); }
    });
    api(ruta + "?ip=" + encodeURIComponent(camara.ip)).then((r) => {
      if (r.ok) pintar(r.data.posiciones || []); else aviso.textContent = r.data.error || "No se han podido cargar las posiciones.";
    });
    return el("div", { class: "camara-posiciones", role: "group", ariaLabel: "Posiciones guardadas" },
      el("div", { class: "camara-posiciones-cab" }, el("span", { class: "camara-posiciones-titulo" }, "Posiciones"), nueva), lista, aviso, formulario);
  }

  // Controles como en la app Tapo: mover (si tiene motor), posiciones, privacidad, detecciones, LED, foto, sonido y pantalla completa.
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
    const admin = Sesion.esAdmin;   // quien solo mira: ver, sonido, foto, pantalla completa y la luz LED
    if (camara.ptz && admin) {
      const mover = (dir) => () => enviar("/api/hogar/camaras/mover", { ip: camara.ip, direccion: dir });
      partes.push(el("div", { class: "camara-ptz", role: "group", ariaLabel: "Mover la cámara" },
        el("span"), boton("▲", "Arriba", mover("arriba")), el("span"),
        boton("◀", "Izquierda", mover("izquierda")), el("span", { class: "camara-ptz-centro" }), boton("▶", "Derecha", mover("derecha")),
        el("span"), boton("▼", "Abajo", mover("abajo")), el("span")));
      partes.push(posiciones(camara, enviar));
    }
    const ajustes = [["privacidad", "Privacidad (lente tapada)"], ["movimiento", "Detección de movimiento"], ["personas", "Detección de personas"], ["led", "Luz indicadora (LED)"]]
      .filter(([campo]) => camara[campo] !== undefined && (admin || campo === "led"))
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
    const avisoHablar = el("p", { class: "muted camara-hablar-aviso", role: "status" });
    const microfono = hablar(camara, (t) => { avisoHablar.textContent = t; });
    let hablando = false;
    const botonHablar = boton("Hablar", "Hablar por la cámara", async () => {
      if (hablando) { microfono.parar(); hablando = false; botonHablar.textContent = "Hablar"; botonHablar.classList.remove("activo"); avisoHablar.textContent = ""; return; }
      if (await microfono.empezar()) { hablando = true; botonHablar.textContent = "Dejar de hablar"; botonHablar.classList.add("activo"); }
    }, "primario pequeno");
    video.addEventListener("aria:cerrar-camara", () => microfono.parar());
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
      el("div", { class: "botones camara-botones" }, admin ? botonHablar : null, sonido, completa, instantanea, bateria), admin ? avisoHablar : null);
  }

  // `fragmento` ({dia, inicio, fin}): se abre directamente en Grabaciones reproduciendo ese clip (sin arrancar el directo).
  function abrir(camara, alCambiar, fragmento) {
    const video = el("video", { class: "camara-video", autoplay: true, muted: true, playsInline: true });
    const estado = el("p", { class: "muted camara-estado", role: "status" }, "Conectando con la cámara… (las de batería tardan unos segundos en despertar)");
    const foto = el("img", { class: "camara-video", alt: "Última imagen de " + camara.nombre, hidden: true });
    const grabaciones = el("section", { class: "camara-grabaciones", hidden: true });
    const directo = el("div", { class: "camara-directo" }, el("div", null, video, foto, estado), controles(camara, video, alCambiar));
    const pestañaDirecto = el("button", { type: "button", class: "fantasma pequeno", ariaPressed: "true" }, "Directo");
    const pestañaGrabaciones = el("button", { type: "button", class: "fantasma pequeno", ariaPressed: "false" }, "Grabaciones");
    const seleccionar = (mostrarGrabaciones) => {
      directo.hidden = mostrarGrabaciones; grabaciones.hidden = !mostrarGrabaciones;
      pestañaDirecto.ariaPressed = String(!mostrarGrabaciones); pestañaGrabaciones.ariaPressed = String(mostrarGrabaciones);
      if (mostrarGrabaciones) { if (soportados()) pararDirecto(); if (!grabaciones.dataset.cargadas) cargarGrabaciones(); }
      else if (soportados() && pausado) iniciarDirecto();
      else if (!soportados() && !foto.src) refrescarFoto?.();
    };
    pestañaDirecto.addEventListener("click", () => seleccionar(false));
    pestañaGrabaciones.addEventListener("click", () => seleccionar(true));
    const d = dialogo(camara.nombre, Sesion.esAdmin ? el("div", { class: "camara-pestanas" }, pestañaDirecto, pestañaGrabaciones) : null,
      el("div", { class: "camara-visor" }, directo, grabaciones));
    let ws = null, url = null, cerrado = false, refrescarFoto = null;
    const fin = () => { video.dispatchEvent(new Event("aria:cerrar-camara")); cerrado = true; try { ws?.close(); } catch (_) { /* ya cerrado */ } if (url) URL.revokeObjectURL(url); d.remove(); };
    d.addEventListener("close", fin);

    async function cargarGrabaciones() {
      grabaciones.dataset.cargadas = "1";
      const estadoCarga = el("p", { class: "muted", role: "status" }, "Cargando días con grabaciones…");
      const selector = el("select", { ariaLabel: "Día de grabación", disabled: true });
      const lista = el("div", { class: "camara-fragmentos" });
      grabaciones.replaceChildren(estadoCarga, selector, lista);
      const r = await api("/api/hogar/camaras/grabaciones/dias?ip=" + encodeURIComponent(camara.ip));
      if (!r.ok || !(r.data.dias || []).length) { estadoCarga.textContent = r.data.error || "No hay grabaciones disponibles."; return; }
      estadoCarga.remove();
      for (const dia of r.data.dias) selector.append(el("option", { value: dia }, new Date(dia + "T12:00:00").toLocaleDateString("es-ES")));
      selector.disabled = false;
      const cargarDia = async () => {
        lista.replaceChildren(el("p", { class: "muted", role: "status" }, "Cargando fragmentos…"));
        const f = await api("/api/hogar/camaras/grabaciones?ip=" + encodeURIComponent(camara.ip) + "&dia=" + encodeURIComponent(selector.value));
        if (!f.ok) { lista.replaceChildren(el("p", { class: "error" }, f.data.error || "No se han podido cargar los fragmentos.")); return; }
        lista.replaceChildren(...(f.data.fragmentos || []).map((fragmento) => {
          const duracion = fragmento.fin - fragmento.inicio;
          const boton = el("button", { type: "button", class: "fantasma", "ariaLabel": "Reproducir grabación" },
            new Date(fragmento.inicio * 1000).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }) + "–" +
            new Date(fragmento.fin * 1000).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }) + " (" + Math.floor(duracion / 60) + ":" + String(duracion % 60).padStart(2, "0") + ")");
          boton.addEventListener("click", () => reproducir({ ...fragmento, dia: selector.value }));
          return boton;
        }));
        if (!lista.children.length) lista.append(el("p", { class: "muted" }, "No hay fragmentos para ese día."));
      };
      selector.addEventListener("change", cargarDia);
      cargarDia();
    }
    function reproducir(fragmento) {
      const videoGrabacion = el("video", { class: "camara-video", controls: true, playsInline: true, preload: "metadata" });
      const aviso = el("p", { class: "muted", role: "status" }, "La cámara está preparando el vídeo…");
      const descargar = el("a", { class: "fantasma", download: "grabacion.mp4", hidden: true }, "Descargar");
      videoGrabacion.src = "/api/hogar/camaras/grabaciones/clip?ip=" + encodeURIComponent(camara.ip) + "&dia=" + encodeURIComponent(fragmento.dia) + "&inicio=" + fragmento.inicio + "&fin=" + fragmento.fin;
      videoGrabacion.addEventListener("loadedmetadata", () => { aviso.hidden = true; descargar.hidden = false; descargar.href = videoGrabacion.src; });
      videoGrabacion.addEventListener("error", () => { aviso.textContent = "No se ha podido reproducir el vídeo."; });
      grabaciones.prepend(el("div", { class: "camara-reproductor" }, videoGrabacion, aviso, descargar));
    }

    // Sin MSE (algunos iPhone): una foto cada 5 s mientras el diálogo esté abierto.
    if (!soportados()) {
      video.hidden = true; foto.hidden = false;
      const refrescar = () => { if (cerrado) return; foto.src = "/api/hogar/camaras/foto?ip=" + encodeURIComponent(camara.ip) + "&t=" + Date.now(); };
      foto.addEventListener("load", () => { estado.textContent = "Imagen cada 5 segundos (este navegador no reproduce el directo)."; setTimeout(refrescar, 5000); });
      foto.addEventListener("error", () => { estado.textContent = "La cámara no ha enviado imagen."; });
      refrescarFoto = refrescar;
      if (fragmento && Sesion.esAdmin) { seleccionar(true); reproducir(fragmento); } else refrescar();
      return;
    }
    // El directo se para al ver las grabaciones: la cámara (sobre todo las de batería) no atiende las dos cosas a la vez.
    let pausado = false;
    function pararDirecto() {
      pausado = true;
      try { ws?.close(); } catch (_) { /* ya cerrado */ }
      ws = null;
      video.removeAttribute("src"); video.load();
      if (url) { URL.revokeObjectURL(url); url = null; }
    }
    function iniciarDirecto() {
      pausado = false;
      estado.textContent = "Conectando con la cámara…";
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
        ws.addEventListener("close", () => { if (cerrado || pausado) return; estado.textContent = estado.textContent !== "En directo" ? "No se ha podido abrir el directo de esta cámara." : "Directo terminado."; });
      }, { once: true });
    }
    if (fragmento && Sesion.esAdmin) { pausado = true; seleccionar(true); reproducir(fragmento); } else iniciarDirecto();
  }
  // Desde la lista de eventos: el visor de la cámara abierto en Grabaciones con ese fragmento.
  function abrirGrabacion(camara, dia, inicio, fin, alCambiar) { return abrir(camara, alCambiar, { dia, inicio, fin }); }
  return { abrir, abrirGrabacion };
})();
