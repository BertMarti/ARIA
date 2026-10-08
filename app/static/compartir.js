"use strict";
// «Compartir con ARIA» (Web Share Target del manifest): otra app del móvil abre /?title=…&text=…&url=…
// Se quita enseguida de la barra de direcciones, se muestra lo compartido (como texto) y el usuario elige
// «Resume esto» o «¿Qué opinas?». El enlace lo lee el servidor con la herramienta resumir_enlace (anti-SSRF).
const Compartir = (() => {
  const MAX = 2000;

  function leer() {
    const p = new URLSearchParams(location.search);
    const titulo = (p.get("title") || "").trim(), texto = (p.get("text") || "").trim();
    let url = (p.get("url") || "").trim();
    if (!titulo && !texto && !url) return null;
    // Muchas apps (Android) meten el enlace dentro de «text»: se saca para no repetirlo.
    if (!url) { const m = /https?:\/\/\S+/.exec(texto); if (m) url = m[0]; }
    if (url && !/^https?:\/\//i.test(url)) url = "";
    const partes = [];
    if (titulo && !texto.includes(titulo)) partes.push(titulo);
    if (texto) partes.push(texto);
    if (url && !texto.includes(url)) partes.push(url);
    return { contenido: partes.join("\n").slice(0, MAX), url };
  }

  function revisar() {
    const c = leer();
    if (!c) return;
    history.replaceState(null, "", "/#chat");
    const d = $("dlg-compartir");
    $("compartir-contenido").textContent = c.contenido;
    const pedir = (orden) => {
      d.close();
      location.hash = "chat";
      Chat.preguntar(orden + "\n\n" + c.contenido);
    };
    $("compartir-resume").onclick = () => pedir(c.url ? "Resume este enlace:" : "Resume esto:");
    $("compartir-opina").onclick = () => pedir(c.url ? "¿Qué opinas de este enlace?" : "¿Qué opinas de esto?");
    $("compartir-no").onclick = () => d.close();
    d.showModal();
    $("compartir-resume").focus();
  }
  return { revisar };
})();
