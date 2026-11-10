"""Capa ASGI que protege la aplicación existente.

Recibe cada petición antes que app/main.py y:
  1. Atiende sus propias rutas: /login, /logout, /api/sesion, /api/usuarios, /api/auditoria,
     /auditoria, /api/chat/olvidar, /_salud y /_sesion/sesion.js.
  2. Exige sesión (cookie firmada) y revisa el permiso del rol (ver permisos.py).
  3. Fija el usuario actual (contexto.py) para que los servicios sepan quién hace la acción.
  4. Registra en la tabla de auditoría las acciones que cambian datos, las de la IA,
     la consulta de fotos, los inicios de sesión y los accesos negados.

No modifica la aplicación interna: si se ejecuta app.main:app directamente, todo funciona como antes
(pero sin seguridad). En producción se ejecuta app.servidor:app.
"""
import json
import logging
import secrets
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs

import anyio

from . import permisos
from .almacen import ahora_iso, detalle_json
from .claves import crear_token, leer_token, verificar_clave
from .contexto import UsuarioActual, usuario_actual
from .paginas import PAGINA_AUDITORIA, SCRIPT_SESION, pagina_login

log = logging.getLogger("seleccion")

COOKIE = "sesion"
CLAVES_DETALLE = (
    "candidato_id", "lectura_id", "id", "estado", "resultado", "puntaje", "zona",
    "requiere_revision", "confianza_ocr", "confianza", "modelo", "flujo",
)
MAX_CAPTURA = 256 * 1024
MAX_FORMULARIO = 64 * 1024
INTENTOS_MAXIMOS = 5
VENTANA_INTENTOS = 600  # segundos
BLOQUEO = 300  # segundos


def extraer_detalle(cuerpo: bytes) -> dict:
    """Toma de la respuesta solo campos sin datos personales (ids, estado, puntaje, confianza)."""
    try:
        datos = json.loads(cuerpo or b"null")
    except ValueError:
        return {}
    if not isinstance(datos, dict):
        return {"elementos": len(datos)} if isinstance(datos, list) else {}
    detalle = {}
    fuentes = [datos] + [v for v in datos.values() if isinstance(v, dict)]
    for fuente in fuentes:
        for clave in CLAVES_DETALLE:
            valor = fuente.get(clave)
            if clave not in detalle and isinstance(valor, (str, int, float, bool)):
                detalle[clave] = valor
            elif clave == "confianza" and isinstance(valor, dict) and clave not in detalle:
                detalle[clave] = {k: v for k, v in valor.items() if isinstance(v, (int, float))}
    return detalle


class Protector:
    def __init__(
        self,
        app,
        almacen,
        secreto: str,
        horas: float = 8,
        cookie_segura: bool = False,
        usuarios_iniciales=(),
        al_olvidar_chat=None,
    ):
        self.app = app
        self.almacen = almacen
        self.secreto = secreto or secrets.token_urlsafe(32)
        if not secreto:
            log.warning("SESION_SECRETO está vacío: se generó uno temporal y las sesiones se cierran al reiniciar")
        self.horas = horas
        self.cookie_segura = cookie_segura
        self.usuarios_iniciales = list(usuarios_iniciales)
        self.al_olvidar_chat = al_olvidar_chat
        self._iniciado = False
        self._candado = None
        self._fallos: dict[tuple, list[float]] = {}
        self._propias = {
            ("GET", "/login"): self._ver_login,
            ("POST", "/login"): self._iniciar_sesion,
            ("GET", "/logout"): self._cerrar_sesion,
            ("POST", "/logout"): self._cerrar_sesion,
            ("GET", "/api/sesion"): self._ver_sesion,
            ("GET", "/api/usuarios"): self._listar_usuarios,
            ("POST", "/api/usuarios"): self._crear_usuario,
            ("GET", "/api/auditoria"): self._ver_auditoria,
            ("GET", "/auditoria"): self._pagina_auditoria,
            ("POST", "/api/chat/olvidar"): self._olvidar_chat,
            ("GET", "/_salud"): self._salud,
            ("GET", "/_sesion/sesion.js"): self._script_sesion,
        }

    # ───────────────────────── Entrada ASGI ─────────────────────────
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":  # lifespan y websockets pasan sin cambios
            await self.app(scope, receive, send)
            return
        await self._asegurar_inicio()

        metodo = scope["method"]
        ruta = permisos.normalizar(scope.get("path", "/"))
        sesion = self._sesion_de(scope)

        manejador = self._propias.get((metodo, ruta))
        if manejador:
            await manejador(scope, receive, send, sesion)
            return

        if permisos.es_publica(metodo, ruta):
            await self.app(scope, receive, send)
            return

        if not sesion:
            if ruta.startswith("/api"):
                await self._json(send, 401, {"detail": "Inicia sesión para continuar.", "mensaje": "Inicia sesión para continuar."})
            else:
                await self._redirigir(send, "/login")
            return

        if not permisos.permitido(sesion["rol"], metodo, ruta):
            await self._auditar(scope, sesion, f"{metodo} {permisos.plantilla(ruta)[0]}", 403, detalle={"motivo": "sin permiso"})
            mensaje = "Tu rol no tiene permiso para esta acción."
            if ruta.startswith("/api"):
                await self._json(send, 403, {"detail": mensaje, "mensaje": mensaje})
            else:
                await self._html(send, 403, f"<p>{mensaje} <a href='/'>Volver</a></p>")
            return

        ficha = usuario_actual.set(UsuarioActual(sesion["usuario"], sesion["rol"]))
        try:
            if permisos.debe_auditarse(metodo, ruta):
                await self._reenviar_auditando(scope, receive, send, sesion, metodo, ruta)
            else:
                await self.app(scope, receive, send)
        finally:
            usuario_actual.reset(ficha)

    async def _asegurar_inicio(self):
        if self._iniciado:
            return
        if self._candado is None:
            self._candado = anyio.Lock()
        async with self._candado:
            if not self._iniciado:
                await anyio.to_thread.run_sync(self.almacen.iniciar, self.usuarios_iniciales)
                self._iniciado = True

    # ───────────────────────── Reenvío con auditoría ─────────────────────────
    async def _reenviar_auditando(self, scope, receive, send, sesion, metodo, ruta):
        estado = {"codigo": 500, "json": False, "cuerpo": bytearray()}

        async def enviar(mensaje):
            if mensaje["type"] == "http.response.start":
                estado["codigo"] = mensaje["status"]
                tipo = dict(mensaje.get("headers") or []).get(b"content-type", b"")
                estado["json"] = b"json" in tipo
            elif mensaje["type"] == "http.response.body" and estado["json"]:
                if len(estado["cuerpo"]) < MAX_CAPTURA:
                    estado["cuerpo"].extend(mensaje.get("body", b""))
            await send(mensaje)

        try:
            await self.app(scope, receive, enviar)
        finally:
            nombre, id_ruta = permisos.plantilla(ruta)
            detalle = extraer_detalle(bytes(estado["cuerpo"])) if estado["json"] else {}
            recurso = str(id_ruta or detalle.get("lectura_id") or detalle.get("candidato_id") or detalle.get("id") or "")
            await self._auditar(
                scope, sesion, f"{metodo} {nombre}", estado["codigo"], recurso=recurso,
                es_ia=permisos.es_accion_ia(metodo, ruta), detalle=detalle,
            )
            if 200 <= estado["codigo"] < 300:
                await self._marcar_lectura(nombre, recurso, sesion["usuario"])

    async def _marcar_lectura(self, nombre: str, recurso: str, usuario: str):
        columna = None
        if nombre == "/api/vision":
            columna = "subido_por"
        elif nombre in ("/api/vision/{id}/confirmar", "/api/vision/{id}/rechazar"):
            columna = "revisado_por"
        if columna and recurso:
            try:
                await anyio.to_thread.run_sync(self.almacen.marcar_lectura, recurso, columna, usuario)
            except Exception as e:  # noqa: BLE001
                log.debug("marcar_lectura falló: %s", e)

    async def _auditar(self, scope, sesion, accion, codigo, recurso="", es_ia=False, detalle=None):
        evento = {
            "fecha": ahora_iso(),
            "usuario": (sesion or {}).get("usuario", "anonimo"),
            "rol": (sesion or {}).get("rol", "ninguno"),
            "accion": accion[:120],
            "recurso": str(recurso)[:120],
            "estado_http": int(codigo),
            "es_ia": bool(es_ia),
            "detalle": detalle_json(detalle or {}),
            "ip": self._ip(scope),
        }
        try:
            await anyio.to_thread.run_sync(self.almacen.registrar, evento)
        except Exception as e:  # noqa: BLE001  (la auditoría nunca debe tumbar la petición)
            log.error("No se pudo guardar la auditoría: %s", e)

    # ───────────────────────── Rutas propias ─────────────────────────
    async def _ver_login(self, scope, receive, send, sesion):
        if sesion:
            await self._redirigir(send, "/")
            return
        codigo = parse_qs(scope.get("query_string", b"").decode()).get("error", [""])[0]
        await self._html(send, 200, pagina_login(codigo))

    async def _iniciar_sesion(self, scope, receive, send, sesion):
        datos = await self._leer_formulario(scope, receive)
        usuario = (datos.get("usuario") or "").strip().lower()[:60]
        clave = datos.get("clave") or ""
        llave = (self._ip(scope), usuario)
        if self._bloqueado(llave):
            await self._auditar(scope, {"usuario": usuario or "?", "rol": "ninguno"}, "LOGIN bloqueado", 429)
            await self._redirigir(send, "/login?error=bloqueado")
            return
        fila = await anyio.to_thread.run_sync(self.almacen.buscar_usuario, usuario) if usuario else None
        if not fila or not fila.get("activo", True) or not verificar_clave(clave, fila["clave_hash"]):
            self._fallos.setdefault(llave, []).append(time.time())
            await self._auditar(scope, {"usuario": usuario or "?", "rol": "ninguno"}, "LOGIN fallido", 401)
            await self._redirigir(send, "/login?error=1")
            return
        self._fallos.pop(llave, None)
        token = crear_token(fila["usuario"], fila["rol"], self.secreto, self.horas)
        await self._auditar(scope, {"usuario": fila["usuario"], "rol": fila["rol"]}, "LOGIN", 200)
        await self._redirigir(send, "/", cookie=self._cookie(token, int(self.horas * 3600)))

    async def _cerrar_sesion(self, scope, receive, send, sesion):
        if sesion:
            await self._auditar(scope, sesion, "LOGOUT", 200)
            if self.al_olvidar_chat:
                await anyio.to_thread.run_sync(self.al_olvidar_chat, sesion["usuario"])
        await self._redirigir(send, "/login?error=salida", cookie=self._cookie("", 0))

    async def _ver_sesion(self, scope, receive, send, sesion):
        if not sesion:
            await self._json(send, 401, {"detail": "Sin sesión"})
            return
        rol = sesion["rol"]
        await self._json(send, 200, {
            "usuario": sesion["usuario"],
            "rol": rol,
            "permisos": {
                "subir": permisos.permitido(rol, "POST", "/api/vision"),
                "ver_imagenes": permisos.permitido(rol, "GET", "/api/vision/1/imagen"),
                "auditoria": permisos.permitido(rol, "GET", "/api/auditoria"),
            },
        })

    async def _solo_admin(self, send, sesion) -> bool:
        if not sesion:
            await self._json(send, 401, {"detail": "Inicia sesión para continuar."})
            return False
        if sesion["rol"] != "admin":
            await self._json(send, 403, {"detail": "Solo el administrador puede hacer esto."})
            return False
        return True

    async def _listar_usuarios(self, scope, receive, send, sesion):
        if await self._solo_admin(send, sesion):
            await self._json(send, 200, await anyio.to_thread.run_sync(self.almacen.listar_usuarios))

    async def _crear_usuario(self, scope, receive, send, sesion):
        if not await self._solo_admin(send, sesion):
            return
        datos = await self._leer_formulario(scope, receive)
        usuario = (datos.get("usuario") or "").strip().lower()
        clave, rol = datos.get("clave") or "", datos.get("rol") or ""
        error = None
        if not (3 <= len(usuario) <= 40) or not all(c.isalnum() or c in "._-" for c in usuario):
            error = "El usuario debe tener de 3 a 40 letras, números, punto, guion o guion bajo."
        elif len(clave) < 8:
            error = "La contraseña debe tener al menos 8 caracteres."
        elif rol not in permisos.ROLES:
            error = "Rol no válido. Usa admin, reclutador o consulta."
        if not error:
            try:
                await anyio.to_thread.run_sync(self.almacen.crear_usuario, usuario, clave, rol)
            except ValueError as e:
                error = str(e)
        if error:
            await self._json(send, 400, {"detail": error, "mensaje": error})
            return
        await self._auditar(scope, sesion, "POST /api/usuarios", 201, recurso=usuario, detalle={"rol": rol})
        await self._json(send, 201, {"usuario": usuario, "rol": rol})

    async def _ver_auditoria(self, scope, receive, send, sesion):
        if not await self._solo_admin(send, sesion):
            return
        parametros = parse_qs(scope.get("query_string", b"").decode())
        try:
            limite = max(1, min(1000, int(parametros.get("limite", ["200"])[0])))
        except ValueError:
            limite = 200
        solo_ia = parametros.get("solo_ia", ["0"])[0] in ("1", "true", "si")
        await self._json(send, 200, await anyio.to_thread.run_sync(self.almacen.auditoria, limite, solo_ia))

    async def _pagina_auditoria(self, scope, receive, send, sesion):
        if not sesion:
            await self._redirigir(send, "/login")
        elif sesion["rol"] != "admin":
            await self._html(send, 403, "<p>Solo el administrador puede ver la auditoría. <a href='/'>Volver</a></p>")
        else:
            await self._html(send, 200, PAGINA_AUDITORIA)

    async def _olvidar_chat(self, scope, receive, send, sesion):
        if not sesion:
            await self._json(send, 401, {"detail": "Inicia sesión para continuar."})
            return
        if self.al_olvidar_chat:
            await anyio.to_thread.run_sync(self.al_olvidar_chat, sesion["usuario"])
        await self._json(send, 200, {"ok": True})

    async def _salud(self, scope, receive, send, sesion):
        await self._json(send, 200, {"estado": "ok"})

    async def _script_sesion(self, scope, receive, send, sesion):
        await self._responder(send, 200, SCRIPT_SESION.encode(), "application/javascript; charset=utf-8")

    # ───────────────────────── Utilidades ─────────────────────────
    def _sesion_de(self, scope):
        for nombre, valor in scope.get("headers") or []:
            if nombre == b"cookie":
                galleta = SimpleCookie()
                try:
                    galleta.load(valor.decode("latin-1"))
                except Exception:  # noqa: BLE001
                    return None
                if COOKIE in galleta:
                    return leer_token(galleta[COOKIE].value, self.secreto)
        return None

    def _cookie(self, valor: str, segundos: int) -> bytes:
        partes = [f"{COOKIE}={valor}", "Path=/", "HttpOnly", "SameSite=Lax", f"Max-Age={segundos}"]
        if self.cookie_segura:
            partes.append("Secure")
        return "; ".join(partes).encode()

    @staticmethod
    def _ip(scope) -> str:
        for nombre, valor in scope.get("headers") or []:
            if nombre == b"x-forwarded-for":
                return valor.decode("latin-1").split(",")[0].strip()[:64]
        cliente = scope.get("client")
        return (cliente[0] if cliente else "")[:64]

    def _bloqueado(self, llave) -> bool:
        ahora = time.time()
        recientes = [t for t in self._fallos.get(llave, []) if ahora - t < VENTANA_INTENTOS]
        self._fallos[llave] = recientes
        return len(recientes) >= INTENTOS_MAXIMOS and ahora - recientes[-1] < BLOQUEO

    @staticmethod
    async def _leer_formulario(scope, receive) -> dict:
        cuerpo = bytearray()
        while True:
            mensaje = await receive()
            cuerpo.extend(mensaje.get("body", b""))
            if len(cuerpo) > MAX_FORMULARIO or not mensaje.get("more_body"):
                break
        tipo = dict(scope.get("headers") or []).get(b"content-type", b"")
        texto = bytes(cuerpo[:MAX_FORMULARIO]).decode("utf-8", "replace")
        if b"json" in tipo:
            try:
                datos = json.loads(texto or "{}")
                return {k: str(v) for k, v in datos.items()} if isinstance(datos, dict) else {}
            except ValueError:
                return {}
        return {k: v[0] for k, v in parse_qs(texto).items()}

    @staticmethod
    async def _responder(send, codigo: int, cuerpo: bytes, tipo: str, extra=()):
        cabeceras = [(b"content-type", tipo.encode()), (b"content-length", str(len(cuerpo)).encode()),
                     (b"cache-control", b"no-store"), *extra]
        await send({"type": "http.response.start", "status": codigo, "headers": cabeceras})
        await send({"type": "http.response.body", "body": cuerpo})

    async def _json(self, send, codigo, datos):
        await self._responder(send, codigo, json.dumps(datos, ensure_ascii=False, default=str).encode(),
                              "application/json; charset=utf-8")

    async def _html(self, send, codigo, html: str):
        await self._responder(send, codigo, html.encode(), "text/html; charset=utf-8")

    async def _redirigir(self, send, destino: str, cookie: bytes | None = None):
        extra = [(b"location", destino.encode())]
        if cookie is not None:
            extra.append((b"set-cookie", cookie))
        await self._responder(send, 303, b"", "text/plain; charset=utf-8", extra)
