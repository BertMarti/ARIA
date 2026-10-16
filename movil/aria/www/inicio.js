// Sin empaquetador: Capacitor expone sus plugins en window.Capacitor.Plugins.
const { Preferences } = window.Capacitor.Plugins;

const clave = 'aria_url';
const formulario = document.querySelector('#formulario');
const campo = document.querySelector('#url');
const error = document.querySelector('#error');
const reintentar = document.querySelector('#reintentar');

function normalizar(valor) {
  const url = new URL(valor.trim());
  if (url.protocol !== 'https:' || url.username || url.password || url.pathname !== '/' && url.pathname !== '') throw new Error('Usa una URL https:// sin ruta.');
  return `${url.origin}/`;
}

async function conectar(valor) {
  try { const url = normalizar(valor); await Preferences.set({ key: clave, value: url }); window.location.assign(url); }
  catch (e) { error.textContent = e.message || 'La URL no es válida.'; error.hidden = false; }
}

async function iniciar() {
  const guardada = (await Preferences.get({ key: clave })).value;
  if (new URLSearchParams(location.search).get('cambiar') === '1') { if (guardada) campo.value = guardada; return; }
  if (guardada) { document.querySelector('h1').textContent = 'Conectando…'; formulario.hidden = true; document.querySelector('.nota').hidden = true; window.location.assign(guardada); }
}
formulario.addEventListener('submit', e => { e.preventDefault(); conectar(campo.value); });
reintentar.addEventListener('click', () => conectar(campo.value));
iniciar().catch(() => { error.textContent = 'No se ha podido leer la configuración.'; error.hidden = false; reintentar.hidden = false; });
