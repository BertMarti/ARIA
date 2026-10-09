const q = new URLSearchParams(location.search);
const err = document.getElementById("error");
if (q.get("e") === "1") { err.textContent = "Usuario o contraseña incorrectos."; err.hidden = false; }
if (q.get("e") === "bloqueado") {
  err.textContent = "Demasiados intentos. Espera " + (parseInt(q.get("s"), 10) || 300) + " s e inténtalo de nuevo.";
  err.hidden = false;
}
if (q.get("e") === "caducado") { err.textContent = "Ha pasado demasiado tiempo: vuelve a escribir la contraseña."; err.hidden = false; }
if (q.get("paso") === "codigo") {
  document.getElementById("form-login").hidden = true;
  const f = document.getElementById("form-codigo"); f.hidden = false; f.querySelector("input").focus();
  if (q.get("e") === "codigo") { const e2 = document.getElementById("error-codigo"); e2.textContent = "Código incorrecto o ya usado. Espera al siguiente e inténtalo otra vez."; e2.hidden = false; }
}
