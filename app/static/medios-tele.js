"use strict";

window.MediosTele = (() => {
  let ws, actual, oferta, dialog, lista, aviso, intervalo, seleccionado;

  const el = (tag, texto, clase) => {
    const nodo = document.createElement(tag);
    if (texto) nodo.textContent = texto;
    if (clase) nodo.className = clase;
    return nodo;
  };
  const api = (url, opciones) => fetch(url, opciones).then((r) => r.ok ? r.json() : r.json().then((x) => Promise.reject(x)));
  const wsUrl = () => `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/tele/canal`;
  const svg = (tipo) => {
    const n = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    n.setAttribute("viewBox", "0 0 24 24");
    n.setAttribute("aria-hidden", "true");
    n.classList.add("svg-ico", "medios-tele-icono");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", tipo === "altavoz" ? "M5 9v6h3l4 4V5L8 9H5zm11 1a4 4 0 0 1 0 4M18 7a8 8 0 0 1 0 10" : "M2 8V6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6M2 12a9 9 0 0 1 8 8M2 16a5 5 0 0 1 4 4M2 20h.01");
    n.append(path);
    return n;
  };
  function abrirWs() {
    if (ws && ws.readyState === WebSocket.OPEN) return Promise.resolve();
    return new Promise((resolve, reject) => {
      ws = new WebSocket(wsUrl());
      ws.onopen = resolve;
      ws.onerror = reject;
      ws.onmessage = async (e) => {
        const d = JSON.parse(e.data);
        if (d.tipo === "ofrecido") oferta = d;
        if (d.tipo === "pedir" && actual) {
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
        if (intervalo) clearInterval(intervalo);
        if (actual) mostrarAviso("El canal se ha cerrado. Mantén esta pestaña abierta y vuelve a intentarlo.");
      };
    });
  }
  function construir() {
    if (dialog) return;
    dialog = el("dialog", null, "medios-tele-dialogo");
    const cabecera = el("header", null, "medios-tele-cabecera");
    const marca = el("span", null, "medios-tele-marca");
    marca.append(svg("cast"));
    const titulos = el("div");
    titulos.append(el("h2", "Enviar a…"), el("p", null, "medios-tele-video"));
    const cerrar = el("button", "×", "medios-tele-cerrar");
    cerrar.type = "button";
    cerrar.setAttribute("aria-label", "Cerrar");
    cerrar.onclick = () => dialog.close();
    cabecera.append(marca, titulos, cerrar);
    dialog.append(cabecera);
    lista = el("section", null, "medios-tele-lista");
    dialog.append(lista);
    aviso = el("p", "Mantén esta pestaña abierta mientras ves el vídeo en la tele", "medios-tele-aviso");
    dialog.append(aviso);
    const pie = el("details", null, "medios-tele-pie");
    pie.append(el("summary", "¿Apple TV o Fire TV?"));
    const acciones = el("div", null, "medios-tele-vlc");
    const enlace = el("a", "Abrir en VLC");
    enlace.target = "_blank";
    const copiar = el("button", "Copiar", "fantasma");
    copiar.type = "button";
    copiar.onclick = () => navigator.clipboard?.writeText(enlace.href).then(() => copiar.textContent = "Copiado");
    acciones.append(enlace, copiar);
    pie.append(acciones);
    dialog.append(pie);
    document.body.append(dialog);
  }
  function mostrarAviso(texto) { if (aviso) aviso.textContent = texto; }
  function cargar() {
    lista.replaceChildren(el("p", "Buscando dispositivos…", "medios-tele-buscando"));
    return api("/api/tele/dispositivos").then((ds) => {
      ds.sort((a, b) => Number(b.video) - Number(a.video) || Number(a.grupo) - Number(b.grupo) || a.nombre.localeCompare(b.nombre));
      lista.replaceChildren();
      ds.forEach((d) => {
        const fila = el("button", null, "medios-tele-dispositivo");
        fila.type = "button";
        fila.append(svg(d.grupo || !d.video ? "altavoz" : "cast"));
        const texto = el("span", null, "medios-tele-datos");
        texto.append(el("strong", d.nombre), el("small", d.modelo || "Dispositivo"));
        fila.append(texto, el("span", d.tipo === "dlna" ? "DLNA" : "Cast", "medios-tele-etiqueta"));
        fila.onclick = () => enviar(d);
        lista.append(fila);
      });
      if (!ds.length) {
        lista.append(el("p", "No hay dispositivos en la red. Puedes añadir uno por IP.", "medios-tele-vacio"));
        añadirIp();
      }
    }).catch(() => lista.replaceChildren(el("p", "No se han podido buscar dispositivos.")));
  }
  function añadirIp() {
    const zona = el("div", null, "medios-tele-añadir");
    const ip = el("input");
    ip.placeholder = "192.168.1.20";
    ip.setAttribute("aria-label", "IP del dispositivo");
    const boton = el("button", "Añadir por IP", "fantasma");
    boton.type = "button";
    boton.onclick = () => api("/api/tele/dispositivos", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ip: ip.value }) }).then(cargar).catch(() => mostrarAviso("No se ha podido añadir esa IP."));
    zona.append(ip, boton);
    lista.append(zona);
  }
  function enviar(d) {
    seleccionado = d;
    return api("/api/tele/enviar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dispositivo: d.id, token: oferta.token, posicion: actual.posicion || 0, titulo: actual.nombre }) }).then(() => reproducir(d));
  }
  function reproducir(d) {
    lista.replaceChildren(el("p", `Reproduciendo en ${d.nombre}`, "medios-tele-reproduciendo"));
    const portada = el("div", null, "medios-tele-portada");
    portada.append(svg("cast"), el("strong", actual.nombre));
    lista.append(portada);
    const barra = el("input");
    barra.type = "range";
    barra.min = "0";
    barra.setAttribute("aria-label", "Progreso del vídeo");
    barra.onchange = () => controlar("buscar", Number(barra.value));
    lista.append(barra);
    const controles = el("div", null, "medios-tele-controles");
    [["−10 s", -10], ["Reproducir", "play"], ["Pausa", "pausa"], ["+10 s", 10], ["Detener", "stop"]].forEach(([texto, accion]) => {
      const boton = el("button", texto, accion === "stop" ? "peligro" : "fantasma");
      boton.type = "button";
      boton.onclick = () => typeof accion === "number" ? controlar("buscar", Math.max(0, Number(barra.value) + accion)) : controlar(accion);
      controles.append(boton);
    });
    const aquí = el("button", "Volver a este dispositivo", "fantasma");
    aquí.type = "button";
    aquí.onclick = () => document.querySelector("video")?.play();
    lista.append(controles, aquí);
    intervalo = setInterval(() => api(`/api/tele/estado?dispositivo=${encodeURIComponent(d.id)}`).then((x) => { barra.max = String(x.duracion || 0); barra.value = String(x.posicion || 0); }), 3000);
    const enlace = dialog.querySelector(".medios-tele-vlc a");
    if (enlace) enlace.href = oferta.url;
  }
  function controlar(accion, segundos) {
    return api("/api/tele/control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dispositivo: seleccionado.id, accion, segundos }) });
  }
  async function compartir(e) {
    actual = e.detail;
    await abrirWs();
    ws.send(JSON.stringify({ tipo: "ofrecer", huella: actual.huella, nombre: actual.nombre, tamano: actual.archivo.size, mime: actual.archivo.type }));
    construir();
    dialog.querySelector(".medios-tele-video").textContent = actual.nombre;
    dialog.showModal();
    cargar();
  }
  window.addEventListener("aria:medios-enviar", compartir);
  return { compartir };
})();
