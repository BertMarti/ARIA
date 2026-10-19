"use strict";
// Navegación entre vistas (Chat, Centro de control, Ajustes) con #hash.
(() => {
  const VISTAS = ["inicio", "chat", "finanzas", "informacion", "red", "seguridad", "cerebro", "control", "hogar", "ajustes", "agenda", "notas", "compartir", "mapa", "hud"];
  const SOLO_ADMIN = ["control", "red", "seguridad"];
  const ACCIONES = { hablar: "chat", "manos-libres": "inicio", nota: "notas", hud: "hud", compartir: "compartir" };
  let accionEjecutada = false;
  function prepararHablar() {
    let boton = $("accion-hablar");
    if (boton) return boton;
    boton = el("button", { id: "accion-hablar", type: "button", class: "primario accion-hablar" }, "Toca para hablar");
    boton.addEventListener("click", () => { $("mic")?.click(); boton.remove(); });
    $("v-chat").prepend(boton);
    return boton;
  }
  function ejecutarAccion(accion) {
    if (accion === "hablar") { $("mic")?.click(); prepararHablar(); }
    else if (accion === "manos-libres") ManosLibres.iniciar();
    else if (accion === "nota") $("notas-texto")?.focus();
  }
  function mostrar() {
    const hash = location.hash.replace(/^#/, "");
    let [v, parametros] = hash.split("?");
    const accion = ACCIONES[v];
    if (accion) v = accion;
    if (!VISTAS.includes(v) || (SOLO_ADMIN.includes(v) && !Sesion.esAdmin) || (v !== "ajustes" && !puede(v))) v = "inicio";
    for (const n of VISTAS) $("v-" + n).hidden = n !== v;
    const bloqueada = Premium.vistaBloqueada(v);   // HUD y Cerebro sin Premium: tarjeta explicativa en su lugar
    document.body.classList.toggle("modo-hud", v === "hud" && !bloqueada);
    document.body.classList.toggle("vista-premium-bloqueada", bloqueada);
    document.querySelectorAll(".nav-btn[data-vista]").forEach((b) => b.classList.toggle("activo", b.dataset.vista === v));
    document.querySelector(".nav-btn.activo")?.scrollIntoView({ block: "nearest", inline: "nearest" });   // barra inferior en móvil
    Control.activar(v === "control");
    Hogar.activar(v === "hogar");
    Cerebro.activar(v === "cerebro" && !bloqueada);
    Inicio.activar(v === "inicio");
    Finanzas.activar(v === "finanzas");
    Informacion.activar(v === "informacion");
    Agenda.activar(v === "agenda");
    Notas.activar(v === "notas");
    Documentos.activar(v === "notas");
    Medios.activar(v === "compartir");
    Red.activar(v === "red");
    Seguridad.activar(v === "seguridad");
    Mapa.activar(v === "mapa");
    Hud.activar(v === "hud" && !bloqueada);
    if (v === "ajustes") { Ajustes.activar(); Usuarios.activar(); Memoria.activar(); Avisos.activar(); Rutinas.activar(); if (Sesion.esAdmin) { Modulos.pintarAjustes(); Automatizaciones.activar(); Accesos.activar(); Registro.activar(); } }
    document.title = "ARIA · " + { inicio: "Inicio", chat: "Chat", finanzas: "Finanzas", informacion: "Información", agenda: "Agenda", notas: "Notas", compartir: "Compartir", red: "Red", seguridad: "Seguridad", cerebro: "Cerebro", control: "Centro de control", hogar: "Hogar", ajustes: "Ajustes", mapa: "Mapa", hud: "HUD" }[v];
    if (v === "chat" && parametros) {
      const params = new URLSearchParams(parametros);
      const id = params.get("c");
      if (id) Chat.abrir(id, true);
      const pregunta = params.get("q");
      if (pregunta) {
        $("agente-sel").value = "aria";
        $("texto").value = pregunta;
        $("texto").focus();
      }
    }
    if (accion && !accionEjecutada) { accionEjecutada = true; ejecutarAccion(hash.split("?")[0]); }
  }
  document.querySelectorAll(".nav-btn[data-vista]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.vista; }));
  // Con mucho zoom la barra lateral solo enseña iconos: el nombre sale al pasar el ratón.
  document.querySelectorAll(".nav .nav-btn").forEach((b) => { if (!b.title) b.title = b.textContent.trim(); });
  window.addEventListener("hashchange", mostrar);
  (async () => {
    await cargarSesion();
    await Premium.cargar();
    ManosLibres.iniciarUI(); Chat.iniciar(); Control.iniciar(); Hogar.iniciar(); Cerebro.iniciar(); Finanzas.iniciar(); Informacion.iniciar(); Agenda.iniciar(); Notas.iniciar(); Documentos.iniciar(); Medios.iniciar(); Red.iniciar(); Seguridad.iniciar(); Inicio.iniciar(); Ajustes.iniciar(); Usuarios.iniciar(); Memoria.iniciar(); Avisos.iniciar(); Rutinas.iniciar(); Registro.iniciar(); Paleta.iniciar(); Mapa.iniciar(); Hud.iniciar();
    Premium.iniciar(); Chat.refrescarCerebro(); PingCompa.iniciar();
    if (new URLSearchParams(location.search).get("spotify")) history.replaceState(null, "", "/#ajustes");
    Compartir.revisar(); // «Compartir con ARIA» desde otra app del móvil (Web Share Target)
    // Invitados: fuera de la barra lo que su acceso no incluye
    document.querySelectorAll(".nav-btn[data-vista]").forEach((b) => { if (b.dataset.vista !== "ajustes" && !puede(b.dataset.vista)) b.hidden = true; });
    mostrar();
    setTimeout(() => Tour.iniciar(), 0);
  })();
})();
