"use strict";

window.MediosTele = (() => {
  let ws;
  let actual;
  let oferta;
  let dialog;
  let lista;
  let aviso;
  let intervalo;
  let progreso;
  let reintentos = 0;

  const el = (tag, texto, clase) => {
    const n = document.createElement(tag);
    if (texto) {
      n.textContent = texto;
    }
    if (clase) {
      n.className = clase;
    }
    return n;
  };

  const api = (url, opciones) => fetch(url, opciones).then((r) => r.ok
    ? r.json()
    : r.json().then((x) => Promise.reject(x)));

  const wsUrl = () => `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/tele/canal`;

  function abrirWs() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }
    return new Promise((resolve, reject) => {
      ws = new WebSocket(wsUrl());
      ws.onopen = resolve;
      ws.onerror = reject;
      ws.onmessage = async (e) => {
        const d = JSON.parse(e.data);
        if (d.tipo === "ofrecido") {
          oferta = d;
          if (actual && actual.subtitulos && d.mime === "text/vtt") {
            actual.vtt = d.url;
          } else if (actual) {
            actual.url = d.url;
            const campo = document.getElementById("medios-tele-url");
            if (campo) {
              campo.value = d.url;
            }
          }
        } else if (d.tipo === "pedir" && actual) {
          try {
            const datos = await actual.archivo.slice(d.inicio, d.fin + 1).arrayBuffer();
            const frame = new Uint8Array(4 + datos.byteLength);
            new DataView(frame.buffer).setUint32(0, d.id);
            frame.set(new Uint8Array(datos), 4);
            ws.send(frame);
          } catch (_) {
            ws.send(JSON.stringify({ tipo: "error", id: d.id }));
          }
        }
      };
      ws.onclose = () => {
        if (intervalo) {
          clearInterval(intervalo);
        }
        if (actual && reintentos < 3) {
          reintentos += 1;
          mostrarAviso(`El canal se ha cortado. Reintentando (${reintentos}/3)...`);
          setTimeout(() => abrirWs().then(() => ws.send(JSON.stringify({
            tipo: "ofrecer",
            huella: actual.huella,
            nombre: actual.nombre,
            tamano: actual.archivo.size,
            mime: actual.archivo.type,
          }))).catch(() => {}), 500 * reintentos);
        } else if (actual) {
          mostrarAviso("El canal se ha cerrado. Mantén esta pestaña abierta y vuelve a intentarlo.");
        }
      };
    });
  }

  function construir() {
    if (dialog) {
      return;
    }
    dialog = el("dialog");
    dialog.id = "dlg-medios-tele";
    dialog.className = "tarjeta";
    const cab = el("header");
    cab.append(el("h2", "Enviar a la tele"));
    const cerrar = el("button", "Cerrar", "fantasma");
    cerrar.type = "button";
    cerrar.onclick = () => dialog.close();
    cab.append(cerrar);
    dialog.append(cab);
    lista = el("div");
    dialog.append(lista);
    const actualizar = el("button", "Actualizar", "fantasma");
    actualizar.type = "button";
    actualizar.onclick = cargar;
    dialog.append(actualizar);
    const ip = el("input");
    ip.placeholder = "192.168.1.20";
    ip.setAttribute("aria-label", "IP de la tele");
    const añadir = el("button", "Añadir por IP", "fantasma");
    añadir.type = "button";
    añadir.onclick = () => api("/api/tele/dispositivos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ip: ip.value }),
    }).then(cargar).catch(() => mostrarAviso("No se ha podido añadir esa IP."));
    const fila = el("p");
    fila.append(ip, añadir);
    dialog.append(fila);
    aviso = el("p", "Mantén esta pestaña abierta mientras ves el vídeo de la tele", "medios-tele-aviso");
    dialog.append(aviso);
    document.body.append(dialog);
  }

  function mostrarAviso(texto) {
    if (aviso) {
      aviso.textContent = texto;
    }
  }

  function cargar() {
    lista.replaceChildren(el("p", "Buscando teles..."));
    return api("/api/tele/dispositivos").then((ds) => {
      lista.replaceChildren();
      ds.forEach((d) => {
        const b = el("button", `${d.nombre} (${d.tipo})`, "fantasma");
        b.type = "button";
        b.onclick = () => enviar(d);
        lista.append(b);
      });
      if (!ds.length) {
        lista.append(el("p", "No se han encontrado teles en la red."));
      }
    });
  }

  function enviar(d) {
    api("/api/tele/enviar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dispositivo: d.id, token: oferta.token, posicion: actual.posicion || 0,
        titulo: actual.nombre }),
    }).then(() => {
      mostrarAviso(`Reproduciendo en ${d.nombre}`);
      lista.replaceChildren();
      [["play", "Reproducir"], ["pausa", "Pausa"], ["stop", "Detener"]].forEach(([accion, texto]) => {
        const b = el("button", texto, "fantasma");
        b.type = "button";
        b.onclick = () => api("/api/tele/control", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ dispositivo: d.id, accion }),
        });
        lista.append(b);
      });
      const barra = el("input");
      barra.type = "range";
      barra.min = "0";
      barra.value = String(actual.posicion || 0);
      barra.setAttribute("aria-label", "Buscar en el vídeo");
      barra.onchange = () => api("/api/tele/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dispositivo: d.id, accion: "buscar", segundos: Number(barra.value) }),
      });
      lista.append(barra);
      intervalo = setInterval(() => api(`/api/tele/estado?dispositivo=${encodeURIComponent(d.id)}`).then((x) => {
        progreso = x;
        barra.max = String(x.duracion || 0);
        barra.value = String(x.posicion || 0);
      }), 3000);
    });
  }

  async function compartir(e) {
    actual = e.detail;
    reintentos = 0;
    await abrirWs();
    ws.send(JSON.stringify({ tipo: "ofrecer", huella: actual.huella, nombre: actual.nombre,
      tamano: actual.archivo.size, mime: actual.archivo.type }));
    if (actual.subtitulos) {
      ws.send(JSON.stringify({ tipo: "subtitulos", huella: actual.huella,
        tamano: actual.subtitulos.size }));
    }
    construir();
    dialog.showModal();
    cargar();
  }

  window.addEventListener("aria:medios-enviar", compartir);
  return { compartir };
})();
