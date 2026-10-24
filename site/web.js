"use strict";

(() => {
  const root = document.documentElement;
  const themeButton = document.getElementById("tema");
  const savedTheme = (() => { try { return localStorage.getItem("aria-tema"); } catch (error) { return null; } })();
  if (savedTheme === "light" || savedTheme === "dark") root.setAttribute("data-theme", savedTheme);
  // Tema efectivo: el elegido a mano o, si no hay, el del sistema.
  const systemLight = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;
  const isLight = () => (root.getAttribute("data-theme") || (systemLight?.matches ? "light" : "dark")) === "light";
  const updateThemeLabel = () => {
    if (!themeButton) return;
    const light = isLight();
    themeButton.setAttribute("aria-pressed", String(light));
    themeButton.setAttribute("title", light ? "Pasar a modo oscuro" : "Pasar a modo claro");
    themeButton.textContent = light ? "☀" : "◐";
  };
  updateThemeLabel();
  systemLight?.addEventListener?.("change", updateThemeLabel);
  themeButton?.addEventListener("click", () => {
    const next = isLight() ? "dark" : "light";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("aria-tema", next); } catch (error) { /* El modo sigue funcionando sin almacenamiento. */ }
    updateThemeLabel();
  });

  const canvas = document.getElementById("ping-portada");
  if (canvas && typeof Ping === "function") new Ping(canvas, { escala: 1.1, global: true, sigueMs: 6000 });

  const dialog = document.getElementById("galeria");
  const enlarged = document.getElementById("imagen-ampliada");
  const caption = document.getElementById("pie-imagen");
  const close = document.getElementById("cerrar-galeria");
  let trigger = null;
  document.querySelectorAll(".captura").forEach((button) => {
    button.addEventListener("click", () => {
      if (!dialog || !enlarged || !caption) return;
      trigger = button;
      enlarged.setAttribute("src", button.dataset.image || "");
      enlarged.setAttribute("alt", button.dataset.alt || "Captura de ARIA");
      caption.textContent = button.dataset.caption || "Captura de ARIA";
      if (typeof dialog.showModal === "function") dialog.showModal();
    });
  });
  const closeDialog = () => { if (dialog?.open) dialog.close(); };
  close?.addEventListener("click", closeDialog);
  dialog?.addEventListener("click", (event) => { if (event.target === dialog) closeDialog(); });
  dialog?.addEventListener("close", () => { trigger?.focus(); trigger = null; });

  const copy = document.getElementById("copiar");
  const command = document.getElementById("comando");
  const status = document.getElementById("estado-copia");
  copy?.addEventListener("click", async () => {
    if (!command || !status) return;
    try {
      await navigator.clipboard.writeText(command.textContent);
      status.textContent = "Copiado. Ya puedes pegarlo en la terminal.";
    } catch (error) {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(command);
      selection?.removeAllRanges();
      selection?.addRange(range);
      status.textContent = "Seleccionado: pulsa Ctrl+C";
    }
  });
})();
