// Página «Crear secreto» de RUNA dentro de ARIA. Cifra en el navegador y sube solo el cifrado a
// /api/modulos/runa/secretos (con la sesión de ARIA); ARIA lo reenvía a RUNA por la red interna.
// Todo el texto se pinta con textContent: nada se interpreta como HTML.
import { MAX_TEXTO, sellar } from "/api/modulos/runa/web/runa-cripto.mjs";

const $ = (id) => document.getElementById(id);
const CADUCIDAD = { 300: "5 minutos", 3600: "1 hora", 86400: "1 día", 604800: "7 días" };
const ERRORES = {
  400: "ARIA o RUNA rechazaron la petición. Recarga la página e inténtalo de nuevo.",
  401: "Tu sesión de ARIA ha caducado. Recarga la página para entrar de nuevo.",
  403: "No tienes permiso para crear secretos o tu sesión ha caducado.",
  429: "Demasiados secretos seguidos. Espera un minuto.",
  502: "RUNA no responde ahora mismo. Inténtalo en unos minutos.",
  507: "RUNA no tiene espacio para más secretos ahora mismo.",
};
// Sin caracteres que se confunden (0/O, 1/l/I), igual que runa_generar.
const ALFABETO = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789-_.!@#%+=?";

function contrasenaAleatoria(n = 20) {
  const limite = 256 - (256 % ALFABETO.length);   // sin sesgo de módulo
  let out = "";
  while (out.length < n) {
    for (const b of crypto.getRandomValues(new Uint8Array(n * 2))) {
      if (b < limite && out.length < n) out += ALFABETO[b % ALFABETO.length];
    }
  }
  return out;
}

function estado(texto) { $("estado").textContent = texto; }
function error(texto) { $("error").textContent = texto; $("error").hidden = !texto; }
function actualizar() { $("enviar").disabled = !$("texto").value.trim() || $("texto").value.length > MAX_TEXTO; }

$("texto").addEventListener("input", actualizar);
$("generar").addEventListener("click", () => {
  $("texto").value = contrasenaAleatoria();
  actualizar();
  estado("Contraseña generada en el cuadro de texto.");
  $("texto").focus();
  $("texto").select();
});

$("crear").addEventListener("submit", async (e) => {
  e.preventDefault();
  const texto = $("texto").value;
  const pass = $("pass").value;
  const ttl = Number($("ttl").value);
  const vistas = Number($("vistas").value);
  if (!texto.trim()) return;
  error("");
  $("enviar").disabled = true;
  $("enviar").textContent = pass ? "Cifrando (con contraseña tarda un poco)…" : "Cifrando…";
  try {
    const s = await sellar(texto, pass);
    const r = await fetch("/api/modulos/runa/secretos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      cache: "no-store",
      body: JSON.stringify({ ciphertext: s.ciphertext, verifier: s.verifier, linkVerifier: s.linkVerifier, ttl, views: vistas }),
    });
    if (!r.ok) throw new Error(ERRORES[r.status] || "No se pudo crear el secreto. Inténtalo de nuevo.");
    const datos = await r.json();
    if (!/^[A-Za-z0-9_-]{22}$/.test(datos.id || "") || !/^https:\/\//.test(datos.base || "")) {
      throw new Error("Respuesta inesperada de ARIA.");
    }
    // La llave (fragmento) se une aquí: nunca ha salido del navegador.
    $("enlace").value = `${datos.base}/s/${datos.id}#${s.fragmento}`;
    $("resumen").textContent = `Caduca en ${CADUCIDAD[ttl]} · ${vistas} ${vistas === 1 ? "lectura" : "lecturas"}.`;
    $("aviso-pass").hidden = !pass;
    $("compartir").hidden = typeof navigator.share !== "function";
    $("texto").value = "";
    $("pass").value = "";
    $("formulario").hidden = true;
    $("resultado").hidden = false;
    $("titulo-ok").focus();
    estado("Enlace creado.");
  } catch (err) {
    error(err instanceof Error && err.message ? err.message : "No se pudo cifrar el secreto en este navegador.");
  } finally {
    $("enviar").textContent = "Cifrar y crear enlace";
    actualizar();
  }
});

$("copiar").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("enlace").value);
    estado("Enlace copiado. Pégalo en WhatsApp, Telegram o donde quieras.");
  } catch {
    $("enlace").select();
    estado("Selecciona y copia el enlace (Ctrl+C).");
  }
});

$("compartir").addEventListener("click", async () => {
  try {
    await navigator.share({ title: "Secreto de un solo uso", url: $("enlace").value });
  } catch { /* cancelado */ }
});

$("otro").addEventListener("click", () => {
  $("enlace").value = "";
  $("resultado").hidden = true;
  $("formulario").hidden = false;
  estado("");
  $("texto").focus();
});

actualizar();
