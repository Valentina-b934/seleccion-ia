"""Páginas que sirve la capa de seguridad: inicio de sesión, auditoría y el script de sesión del panel."""

_ESTILO_BASE = """
:root{--fondo:#f5f6fa;--tarjeta:#fff;--texto:#161a2b;--suave:#5b6075;--borde:#dfe2ec;--acento:#2340e0;--error:#b42318;--ia:#7a3ff2}
@media (prefers-color-scheme:dark){:root{--fondo:#10121b;--tarjeta:#181b27;--texto:#e8eaf3;--suave:#a1a6bb;--borde:#2a2e3e;--acento:#7d8fff;--error:#ff8a80;--ia:#b79bff}}
*{box-sizing:border-box}body{margin:0;font-family:"Instrument Sans",system-ui,sans-serif;background:var(--fondo);color:var(--texto)}
.btn{font:inherit;border-radius:10px;padding:.65rem 1rem;border:1px solid var(--borde);background:var(--tarjeta);color:var(--texto);cursor:pointer}
.btn.primary{background:var(--acento);border-color:var(--acento);color:#fff;font-weight:600}
"""

PAGINA_LOGIN = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Iniciar sesión · Selección de personal</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;600;700&display=swap" rel="stylesheet">
<style>""" + _ESTILO_BASE + """
main{min-height:100vh;display:grid;place-items:center;padding:16px}
form{width:100%;max-width:380px;background:var(--tarjeta);border:1px solid var(--borde);border-radius:16px;padding:28px}
h1{font-size:1.35rem;margin:0 0 .25rem}p{color:var(--suave);margin:0 0 1.25rem;line-height:1.45}
label{display:block;font-weight:600;font-size:.9rem;margin:.9rem 0 .35rem}
input{width:100%;font:inherit;padding:.65rem .75rem;border-radius:10px;border:1px solid var(--borde);background:var(--fondo);color:var(--texto)}
.btn{width:100%;margin-top:1.25rem}.error{color:var(--error);font-weight:600;margin:1rem 0 0}
small{display:block;margin-top:1rem;color:var(--suave);line-height:1.4}
</style></head>
<body><main><form method="post" action="/login">
<h1>Selección de personal</h1><p>Inicia sesión para cargar hojas de vida, revisar candidatos y usar el asistente.</p>
<label for="usuario">Usuario</label><input id="usuario" name="usuario" autocomplete="username" required autofocus>
<label for="clave">Contraseña</label><input id="clave" name="clave" type="password" autocomplete="current-password" required>
<button class="btn primary" type="submit">Entrar</button>
__MENSAJE__
<small>Los datos personales se tratan según la Ley 1581 de 2012. Cada acción queda registrada con tu usuario.</small>
</form></main></body></html>"""

MENSAJES_LOGIN = {
    "1": "Usuario o contraseña incorrectos.",
    "bloqueado": "Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.",
    "salida": "Cerraste sesión.",
}


def pagina_login(codigo: str = "") -> str:
    mensaje = MENSAJES_LOGIN.get(codigo, "")
    clase = "error" if codigo in ("1", "bloqueado") else ""
    html = f'<p class="{clase}" role="alert">{mensaje}</p>' if mensaje else ""
    return PAGINA_LOGIN.replace("__MENSAJE__", html)


PAGINA_AUDITORIA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Auditoría · Selección de personal</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;600;700&display=swap" rel="stylesheet">
<style>""" + _ESTILO_BASE + """
.wrap{max-width:1200px;margin:0 auto;padding:24px 16px}
header{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between}
h1{margin:0;font-size:1.4rem}p{color:var(--suave)}
.filtros{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:16px 0}
.tabla{overflow-x:auto;background:var(--tarjeta);border:1px solid var(--borde);border-radius:14px}
table{border-collapse:collapse;width:100%;font-size:.88rem}th,td{padding:.55rem .7rem;border-bottom:1px solid var(--borde);text-align:left;vertical-align:top}
th{position:sticky;top:0;background:var(--tarjeta)}td.det{font-family:ui-monospace,monospace;font-size:.8rem;color:var(--suave);max-width:360px;word-break:break-word}
.ia{color:var(--ia);font-weight:700}.mal{color:var(--error);font-weight:700}a{color:var(--acento)}
</style></head>
<body><div class="wrap">
<header><div><h1>Registro de auditoría</h1><p>Quién hizo qué y cuándo. Las acciones de la IA están marcadas.</p></div>
<a class="btn" href="/">Volver al panel</a></header>
<div class="filtros"><label><input type="checkbox" id="soloIa"> Solo acciones de la IA</label>
<button class="btn" id="recargar" type="button">Actualizar</button><span id="conteo" role="status"></span></div>
<div class="tabla"><table><thead><tr><th>Fecha (UTC)</th><th>Usuario</th><th>Rol</th><th>Acción</th><th>Recurso</th><th>Resultado</th><th>IA</th><th>Detalle</th><th>IP</th></tr></thead>
<tbody id="filas"></tbody></table></div></div>
<script>
const $ = (s) => document.querySelector(s);
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
async function cargar() {
  const r = await fetch("/api/auditoria?limite=500" + ($("#soloIa").checked ? "&solo_ia=1" : ""));
  if (r.status === 401) { location.href = "/login"; return; }
  if (!r.ok) { $("#conteo").textContent = "No tienes permiso para ver la auditoría."; return; }
  const filas = await r.json();
  $("#conteo").textContent = filas.length + " registros";
  $("#filas").innerHTML = filas.map((f) => `<tr><td>${esc(f.fecha)}</td><td>${esc(f.usuario)}</td><td>${esc(f.rol)}</td>
    <td>${esc(f.accion)}</td><td>${esc(f.recurso)}</td><td class="${f.estado_http >= 400 ? "mal" : ""}">${esc(f.estado_http)}</td>
    <td class="ia">${f.es_ia ? "IA" : ""}</td><td class="det">${esc(f.detalle)}</td><td>${esc(f.ip)}</td></tr>`).join("");
}
$("#soloIa").addEventListener("change", cargar); $("#recargar").addEventListener("click", cargar); cargar();
</script></body></html>"""


# Se carga en panel/index.html antes de app.js. No cambia la lógica del panel: solo agrega la barra
# de sesión, envía a /login cuando la sesión vence y oculta lo que el rol no puede usar.
SCRIPT_SESION = r"""(() => {
  const fetchOriginal = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const r = await fetchOriginal(...args);
    if (r.status === 401) { location.href = "/login"; }
    return r;
  };

  const ROLES = { admin: "Administrador", reclutador: "Reclutador", consulta: "Consulta" };

  async function iniciar() {
    let sesion;
    try {
      const r = await fetchOriginal("/api/sesion");
      if (!r.ok) return;
      sesion = await r.json();
    } catch { return; }

    const barra = document.createElement("div");
    barra.className = "sesion";
    barra.style.cssText = "display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;font-size:.9rem";
    const nombre = document.createElement("span");
    nombre.textContent = `${sesion.usuario} · ${ROLES[sesion.rol] || sesion.rol}`;
    barra.append(nombre);
    if (sesion.permisos.auditoria) {
      const a = document.createElement("a");
      a.href = "/auditoria"; a.className = "btn ghost"; a.textContent = "Auditoría";
      barra.append(a);
    }
    const salir = document.createElement("form");
    salir.method = "post"; salir.action = "/logout"; salir.style.margin = "0";
    salir.innerHTML = '<button type="submit" class="btn ghost">Salir</button>';
    barra.append(salir);
    (document.querySelector(".top-inner") || document.body).append(barra);

    if (!sesion.permisos.subir) {
      const tab = document.getElementById("tab-cargar");
      const panel = document.getElementById("panel-cargar");
      if (tab) tab.hidden = true;
      if (panel) panel.hidden = true;
      document.getElementById("tab-candidatos")?.click();
    }

    const nueva = document.getElementById("btnNuevaConversacion");
    nueva?.addEventListener("click", async () => {
      await fetchOriginal("/api/chat/olvidar", { method: "POST" });
      const mensajes = document.getElementById("mensajes");
      if (mensajes) [...mensajes.querySelectorAll(".msg")].slice(1).forEach((m) => m.remove());
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();
"""
