"use strict";
// Tour de primera visita, guiado por Ping y sin navegar si la interfaz no está disponible.
const Tour = (() => {
  const VERSION = "3.0", MARCA = "aria_tour_visto";
  let paso = -1, activo = false, capa, foco, indice, turno = 0;
  const movil = () => matchMedia("(pointer: coarse)").matches || innerWidth < 900;
  const visto = () => { try { return localStorage.getItem(MARCA) === VERSION; } catch (_) { return false; } };
  const marcar = () => { try { localStorage.setItem(MARCA, VERSION); } catch (_) { /* almacenamiento no disponible */ } };
  const excluido = () => document.fullscreenElement || document.body.classList.contains("modo-hud") || location.hash === "#ajustes" && $("prueba-perfiles")?.offsetParent;
  const pasos = [
    { texto: "¡Eh, mira! Soy Ping, tu guía luminoso. Te enseño ARIA en un momento.", selector: "#saludo" },
    { texto: "¡Eh, mira! Pregúntale a ARIA lo que necesites desde aquí, sin buscar menús.", selector: "#preguntar-texto" },
    { texto: "¡Eh, mira! El micrófono sirve para hablar; activa manos libres si quieres que te escuche.", selector: "#preguntar-mic" },
    { texto: "¡Eh, mira! En la campana te espero: si pasa algo, vengo yo a avisarte.", selector: "#campana" },
    { texto: "¡Eh, mira! Estas tarjetas son tu mapa rápido: cada número abre una parte de ARIA.", selector: "#menu-inicio" },
    { texto: "¡Eh, mira! El HUD convierte tu casa y tus datos en una cabina de mando visual.", selector: ".mi-carta[href=\"#hud\"]" },
    { texto: "¡Eh, mira! En Compartir mandas tus vídeos a la tele y los tienes organizados.", selector: "#v-compartir", vista: "compartir", movil: "compartir" },
    { texto: "¡Eh, mira! En Ajustes tienes la app de Android, el widget y los atajos de Siri.", selector: "#ajustes-android", vista: "ajustes", seccion: "general", movil: "ajustes" },
    { texto: "¡Ya está! Si me necesitas, toca la tarjeta 09 y volvemos a dar una vuelta.", selector: ".mi-carta[href=\"#inicio\"]" },
  ];
  function mostrarVista(def) {
    if (movil()) return;
    const vista = def.vista || "inicio";   // al volver «Atrás» desde Compartir hay que regresar al inicio
    if ((location.hash.replace("#", "") || "inicio") !== vista) location.hash = vista;
    if (def.seccion) Ajustes.irSeccion(def.seccion);
  }
  function encontrar(def) {
    const selector = movil() && def.movil ? ".nav-btn[data-vista=\"" + def.movil + "\"]" : def.selector;
    const elemento = document.querySelector(selector);
    return elemento && !elemento.hidden && elemento.offsetParent !== null ? elemento : null;
  }
  function hueco(elemento) {
    const r = elemento.getBoundingClientRect(), margen = 8;
    const abajo = r.bottom + margen, arriba = r.top - margen, izquierda = r.left - margen, derecha = r.right + margen;
    capa.style.clipPath = "polygon(0 0, 100% 0, 100% 100%, 0 100%, 0 " + abajo + "px, " + izquierda + "px " + abajo + "px, " + izquierda + "px " + arriba + "px, " + derecha + "px " + arriba + "px, " + derecha + "px " + abajo + "px, 0 " + abajo + "px)";
  }
  function limpiarFoco() { foco?.classList.remove("tour-foco"); foco = null; }
  function cerrar() {
    activo = false; turno++; limpiarFoco(); capa?.remove(); capa = null; indice?.remove(); indice = null;
    PingCompa.ocultar(); document.querySelector(".ping-compa-lienzo")?.classList.remove("tour-ping"); paso = -1;
  }
  function siguiente() { cargar(paso + 1, 1); }
  function anterior() { cargar(paso - 1, -1); }
  function bocadillo(def) {
    const botones = [{ texto: "Atrás", clase: "fantasma pequeno", accion: anterior },
      { texto: paso === pasos.length - 1 ? "Terminar" : "Siguiente", clase: "primario pequeno", accion: siguiente },
      { texto: "Saltar tour", clase: "fantasma pequeno", accion: cerrar }].filter((b) => !(b.texto === "Atrás" && paso < 1));
    const b = PingCompa.decir(def.texto, botones);
    if (!b) {
      cerrar();   // Ping no está disponible (pestaña oculta): mejor no dejar la pantalla atenuada
      return;
    }
    b.classList.add("tour-bocadillo");
    b.prepend(el("p", { class: "tour-indice" }, paso + 1 + "/" + pasos.length));
    colocarJunto(b, foco);
    b.querySelector("button.primario")?.focus();
  }
  // El bocadillo nunca tapa lo que se explica: debajo del elemento si cabe, si no encima.
  function colocarJunto(b, elemento) {
    if (!elemento) return;
    const r = elemento.getBoundingClientRect();
    const alto = b.offsetHeight;
    const abajo = r.bottom + 14;
    const arriba = r.top - alto - 14;
    const top = abajo + alto <= innerHeight - 12 ? abajo : Math.max(12, arriba);
    const left = Math.min(innerWidth - b.offsetWidth - 12, Math.max(12, r.left + r.width / 2 - b.offsetWidth / 2));
    b.style.top = top + "px";
    b.style.left = left + "px";
  }
  // Cada llamada invalida los reintentos de la anterior: así «Atrás» y «Siguiente» nunca se pelean por la vista.
  // Si un paso no aparece en ~2 s (sección oculta, sin permiso…), se salta en la dirección en que íbamos.
  function cargar(numero, sentido = 1, intentos = 0) {
    const mio = ++turno;
    limpiarFoco();
    while (numero >= 0 && numero < pasos.length) {
      const def = pasos[numero];
      if (intentos === 0) mostrarVista(def);
      const elemento = encontrar(def);
      if (elemento) { paso = numero; foco = elemento; break; }
      if (!movil() && intentos < 25) {
        setTimeout(() => { if (activo && turno === mio) cargar(numero, sentido, intentos + 1); }, 80);
        return;
      }
      numero += sentido; intentos = 0;
    }
    if (numero >= pasos.length) { cerrar(); marcar(); return; }
    if (numero < 0) { cargar(0, 1); return; }
    foco.classList.add("tour-foco"); hueco(foco); PingCompa.volarA(foco); bocadillo(pasos[paso]);
  }
  function iniciar(opciones = {}) {
    const vista = location.hash.replace("#", "") || "inicio";
    if (activo || excluido() || !puede("inicio") || !opciones.forzar && (!movil() || visto() || vista !== "inicio")) return;
    activo = true; marcar(); capa = el("div", { class: "tour-capa", ariaHidden: "true" }); document.body.append(capa);
    document.querySelector(".ping-compa-lienzo")?.classList.add("tour-ping");
    cargar(0);
  }
  addEventListener("resize", () => { if (activo && foco) { hueco(foco); PingCompa.volarA(foco); } });
  addEventListener("keydown", (e) => { if (!activo) return; if (e.key === "Escape") cerrar(); else if (e.key === "ArrowRight") siguiente(); else if (e.key === "ArrowLeft" && paso > 0) anterior(); });
  return { iniciar };
})();
