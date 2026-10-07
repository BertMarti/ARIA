"use strict";
// Ajustes → Usuarios (solo administradores; el servidor lo impone igualmente con 403).
const Usuarios = (() => {
  const fecha = (ts) => (ts ? new Date(ts * 1000).toLocaleString("es-ES", { dateStyle: "medium", timeStyle: "short" }) : "nunca");

  async function cambiar(u, cambio, ok) {
    const r = await api("/api/users/" + u.id, { method: "PATCH", json: cambio });
    toast(r.ok ? ok : (r.data.error || "No se pudo guardar."), r.ok ? "" : "mal");
    lista();
  }

  async function eliminar(u) {
    if (!(await confirmar("Eliminar usuario", "Se eliminará a " + u.nombre + " (" + u.email + ") y todas sus conversaciones. No se puede deshacer.", "Eliminar"))) return;
    const r = await api("/api/users/" + u.id, { method: "DELETE" });
    toast(r.ok ? "Usuario eliminado." : (r.data.error || "No se pudo eliminar."), r.ok ? "" : "mal");
    lista();
  }

  function ponerPassword(u) {
    $("passuser-titulo").textContent = "Contraseña para casa: " + u.nombre;
    $("passuser-valor").value = "";
    $("form-passuser").dataset.id = u.id;
    $("dlg-passuser").showModal(); $("passuser-valor").focus();
  }

  async function lista() {
    const ul = $("usuarios-lista");
    const { ok, data } = await api("/api/users");
    if (!ok) { ul.replaceChildren(el("li", { class: "error" }, data.error || "No se pudo leer la lista de usuarios.")); return; }
    ul.replaceChildren();
    for (const u of data.usuarios) {
      const rol = el("select", { "aria-label": "Rol de " + u.nombre, disabled: u.protegido });
      rol.append(el("option", { value: "usuario", selected: u.rol === "usuario" }, "Usuario"),
                 el("option", { value: "admin", selected: u.rol === "admin" }, "Administrador"));
      rol.addEventListener("change", () => cambiar(u, { rol: rol.value }, "Rol cambiado."));
      ul.append(el("li", { class: "fila" },
        el("div", { class: "fila-info" },
          el("strong", null, u.nombre, u.email === Sesion.email ? el("span", { class: "pildora cerebro-primero" }, "tú") : null),
          el("span", { class: "muted" }, u.email + (u.usuario ? " · usuario «" + u.usuario + "»" : "")),
          el("span", { class: "muted" }, "Último acceso: " + fecha(u.ultimo_acceso) + (u.tiene_password ? " · con contraseña para casa" : " · sin contraseña para casa"))),
        el("div", { class: "fila-acc" },
          el("span", { class: "pildora" + (u.activo ? " ok" : " apagada") }, u.activo ? "Activo" : "Desactivado"),
          rol,
          el("button", { type: "button", class: "fantasma pequeno", disabled: u.protegido,
            onclick: () => cambiar(u, { activo: !u.activo }, u.activo ? "Usuario desactivado." : "Usuario activado.") }, u.activo ? "Desactivar" : "Activar"),
          el("button", { type: "button", class: "fantasma pequeno", onclick: () => ponerPassword(u) }, "Poner contraseña para casa"),
          el("button", { type: "button", class: "peligro pequeno", disabled: u.protegido, onclick: () => eliminar(u) }, "Eliminar"))));
    }
  }

  function iniciar() {
    if (!Sesion.esAdmin) return;
    $("form-invitar").addEventListener("submit", async (e) => {
      e.preventDefault();
      const msg = $("inv-msg"); msg.className = "muted"; msg.textContent = "";
      const r = await api("/api/users", { method: "POST", json: {
        email: $("inv-email").value.trim(), nombre: $("inv-nombre").value.trim(), rol: $("inv-rol").value } });
      if (r.ok) { $("form-invitar").reset(); msg.className = "ok-txt"; msg.textContent = "Usuario invitado. Recuerda autorizar también su email en Cloudflare Access."; lista(); }
      else { msg.className = "error"; msg.textContent = r.data.error || "No se pudo invitar."; }
    });
    $("form-passuser").addEventListener("submit", async (e) => {
      e.preventDefault();
      const r = await api("/api/users/" + e.currentTarget.dataset.id + "/password", { method: "POST", json: { password: $("passuser-valor").value } });
      if (r.ok) { $("dlg-passuser").close(); toast("Contraseña guardada."); lista(); }
      else toast(r.data.error || "No se pudo guardar la contraseña.", "mal");
    });
    $("dlg-passuser").addEventListener("click", (e) => { if (e.target.closest("[data-cerrar]")) $("dlg-passuser").close(); });
  }

  function activar() { if (Sesion.esAdmin) lista(); }
  return { iniciar, activar };
})();
