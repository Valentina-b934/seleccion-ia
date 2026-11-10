"""Pruebas de inicio de sesión, permisos por rol y auditoría.

No necesitan internet, claves ni base de datos: usan una aplicación interna simulada
y el almacén en memoria.
"""
import asyncio
import json

from app.seguridad import permisos
from app.seguridad.almacen import AlmacenMemoria
from app.seguridad.claves import cifrar_clave, crear_token, leer_token, verificar_clave
from app.seguridad.contexto import usuario_actual
from app.seguridad.envoltura import Protector, extraer_detalle

SECRETO = "secreto-de-prueba"


class AppInterna:
    """Imita a app/main.py: responde JSON y anota qué usuario vio cada petición."""

    def __init__(self):
        self.vistas = []

    async def __call__(self, scope, receive, send):
        self.vistas.append((scope["method"], scope["path"], usuario_actual.get().usuario))
        if scope["path"] == "/api/vision" and scope["method"] == "POST":
            datos = {"lectura_id": 7, "estado": "guardado", "nombre": "Ana Ruiz", "correo": "ana@x.com"}
        elif scope["path"] == "/api/chat":
            datos = {"respuesta": "Hola"}
        else:
            datos = {"ok": True}
        cuerpo = json.dumps(datos).encode()
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": cuerpo})


def crear():
    almacen = AlmacenMemoria()
    olvidados = []
    app = Protector(
        AppInterna(), almacen, SECRETO,
        usuarios_iniciales=[("admin", "Admin.2026", "admin"), ("reclutador", "Recluta.2026", "reclutador"),
                            ("consulta", "Consulta.2026", "consulta")],
        al_olvidar_chat=olvidados.append,
    )
    return app, almacen, olvidados


def pedir(app, metodo, ruta, cookie=None, cuerpo=b"", tipo=b"application/x-www-form-urlencoded", query=b""):
    cabeceras = [(b"content-type", tipo)]
    if cookie:
        cabeceras.append((b"cookie", f"sesion={cookie}".encode()))
    scope = {"type": "http", "method": metodo, "path": ruta, "query_string": query, "headers": cabeceras,
             "client": ("10.0.0.1", 1234)}
    salida = {"cuerpo": b""}
    enviado = {"listo": False}

    async def receive():
        if enviado["listo"]:
            return {"type": "http.disconnect"}
        enviado["listo"] = True
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    async def send(mensaje):
        if mensaje["type"] == "http.response.start":
            salida["estado"] = mensaje["status"]
            salida["cabeceras"] = {k.decode(): v.decode() for k, v in mensaje["headers"]}
        else:
            salida["cuerpo"] += mensaje.get("body", b"")

    asyncio.run(app(scope, receive, send))
    return salida


def entrar(app, usuario, clave):
    r = pedir(app, "POST", "/login", cuerpo=f"usuario={usuario}&clave={clave}".encode())
    galleta = r["cabeceras"].get("set-cookie", "")
    return r, (galleta.split(";")[0].split("=", 1)[1] if "sesion=" in galleta else None)


# ───────────────────────── Claves y tokens ─────────────────────────
def test_la_clave_se_guarda_cifrada_y_se_verifica():
    guardada = cifrar_clave("Secreta.123")
    assert "Secreta.123" not in guardada
    assert verificar_clave("Secreta.123", guardada)
    assert not verificar_clave("otra", guardada)


def test_token_alterado_o_vencido_se_rechaza():
    token = crear_token("ana", "reclutador", SECRETO, horas=1, ahora=1000)
    assert leer_token(token, SECRETO, ahora=1500) == {"usuario": "ana", "rol": "reclutador"}
    assert leer_token(token, SECRETO, ahora=1000 + 3601) is None
    assert leer_token(token, "otro-secreto", ahora=1500) is None
    cuerpo, firma = token.split(".")
    falso = crear_token("ana", "admin", "secreto-del-atacante", horas=1, ahora=1000).split(".")[0]
    assert leer_token(f"{falso}.{firma}", SECRETO, ahora=1500) is None


# ───────────────────────── Permisos ─────────────────────────
def test_tabla_de_permisos():
    assert permisos.permitido("reclutador", "POST", "/api/vision")
    assert permisos.permitido("reclutador", "GET", "/api/vision/3/imagen")
    assert not permisos.permitido("consulta", "POST", "/api/vision")
    assert not permisos.permitido("consulta", "GET", "/api/vision/3/imagen")
    assert permisos.permitido("consulta", "GET", "/api/candidatos")
    assert permisos.permitido("consulta", "POST", "/api/chat")
    assert not permisos.permitido("reclutador", "GET", "/api/ejecuciones")
    assert not permisos.permitido("reclutador", "GET", "/docs")
    assert permisos.permitido("admin", "GET", "/api/ejecuciones")
    assert not permisos.permitido("intruso", "GET", "/api/candidatos")


def test_rutas_publicas_y_plantillas():
    assert permisos.es_publica("GET", "/styles.css")
    assert permisos.es_publica("GET", "/login")
    assert not permisos.es_publica("GET", "/")
    assert not permisos.es_publica("GET", "/api/candidatos")
    assert not permisos.es_publica("GET", "/openapi.json")
    assert permisos.plantilla("/api/vision/12/confirmar") == ("/api/vision/{id}/confirmar", "12")


# ───────────────────────── Inicio de sesión ─────────────────────────
def test_sin_sesion_la_api_responde_401_y_el_panel_redirige():
    app, _, _ = crear()
    assert pedir(app, "GET", "/api/candidatos")["estado"] == 401
    r = pedir(app, "GET", "/")
    assert r["estado"] == 303 and r["cabeceras"]["location"] == "/login"
    assert pedir(app, "GET", "/styles.css")["estado"] == 200  # archivos estáticos sin datos


def test_login_correcto_crea_cookie_segura_y_deja_entrar():
    app, almacen, _ = crear()
    r, cookie = entrar(app, "reclutador", "Recluta.2026")
    assert r["estado"] == 303 and cookie
    assert "HttpOnly" in r["cabeceras"]["set-cookie"]
    assert pedir(app, "GET", "/api/candidatos", cookie=cookie)["estado"] == 200
    sesion = json.loads(pedir(app, "GET", "/api/sesion", cookie=cookie)["cuerpo"])
    assert sesion["rol"] == "reclutador" and sesion["permisos"]["subir"] and not sesion["permisos"]["auditoria"]
    assert any(e["accion"] == "LOGIN" for e in almacen.eventos)


def test_login_fallido_se_audita_y_se_bloquea_tras_varios_intentos():
    app, almacen, _ = crear()
    for _ in range(5):
        r, cookie = entrar(app, "admin", "mala")
        assert cookie is None and r["cabeceras"]["location"] == "/login?error=1"
    r, _ = entrar(app, "admin", "Admin.2026")  # aun con la clave buena, espera el bloqueo
    assert r["cabeceras"]["location"] == "/login?error=bloqueado"
    assert sum(e["accion"] == "LOGIN fallido" for e in almacen.eventos) == 5


def test_cerrar_sesion_borra_la_cookie_y_la_memoria_del_chat():
    app, _, olvidados = crear()
    _, cookie = entrar(app, "consulta", "Consulta.2026")
    r = pedir(app, "POST", "/logout", cookie=cookie)
    assert "Max-Age=0" in r["cabeceras"]["set-cookie"]
    assert olvidados == ["consulta"]


# ───────────────────────── Roles en la práctica ─────────────────────────
def test_consulta_no_puede_subir_fotos_y_queda_registrado():
    app, almacen, _ = crear()
    _, cookie = entrar(app, "consulta", "Consulta.2026")
    r = pedir(app, "POST", "/api/vision", cookie=cookie)
    assert r["estado"] == 403
    assert app.app.vistas == []  # la petición nunca llegó a la aplicación
    negado = almacen.eventos[-1]
    assert negado["estado_http"] == 403 and negado["usuario"] == "consulta"


def test_solo_admin_ve_auditoria_y_crea_usuarios():
    app, almacen, _ = crear()
    _, recl = entrar(app, "reclutador", "Recluta.2026")
    _, adm = entrar(app, "admin", "Admin.2026")
    assert pedir(app, "GET", "/api/auditoria", cookie=recl)["estado"] == 403
    assert pedir(app, "GET", "/api/auditoria", cookie=adm)["estado"] == 200
    nuevo = json.dumps({"usuario": "maria.rh", "clave": "Clave.Larga1", "rol": "reclutador"}).encode()
    assert pedir(app, "POST", "/api/usuarios", cookie=recl, cuerpo=nuevo, tipo=b"application/json")["estado"] == 403
    assert pedir(app, "POST", "/api/usuarios", cookie=adm, cuerpo=nuevo, tipo=b"application/json")["estado"] == 201
    corto = json.dumps({"usuario": "x", "clave": "1", "rol": "jefe"}).encode()
    assert pedir(app, "POST", "/api/usuarios", cookie=adm, cuerpo=corto, tipo=b"application/json")["estado"] == 400
    assert almacen.buscar_usuario("maria.rh")["rol"] == "reclutador"


# ───────────────────────── Auditoría de la IA ─────────────────────────
def test_subir_foto_queda_auditado_sin_datos_personales_y_con_quien_la_subio():
    app, almacen, _ = crear()
    _, cookie = entrar(app, "reclutador", "Recluta.2026")
    assert pedir(app, "POST", "/api/vision", cookie=cookie)["estado"] == 200
    evento = almacen.eventos[-1]
    assert evento["accion"] == "POST /api/vision" and evento["es_ia"] and evento["recurso"] == "7"
    assert "Ana" not in evento["detalle"] and "ana@x.com" not in evento["detalle"]
    assert almacen.lecturas_marcadas == [("7", "subido_por", "reclutador")]
    assert app.app.vistas[-1] == ("POST", "/api/vision", "reclutador")  # el servicio sabe quién es


def test_confirmar_lectura_registra_quien_reviso():
    app, almacen, _ = crear()
    _, cookie = entrar(app, "reclutador", "Recluta.2026")
    pedir(app, "POST", "/api/vision/9/confirmar", cookie=cookie)
    assert almacen.eventos[-1]["accion"] == "POST /api/vision/{id}/confirmar"
    assert ("9", "revisado_por", "reclutador") in almacen.lecturas_marcadas


def test_el_chat_se_audita_como_accion_de_ia_y_las_consultas_no_llenan_el_registro():
    app, almacen, _ = crear()
    _, cookie = entrar(app, "consulta", "Consulta.2026")
    antes = len(almacen.eventos)
    pedir(app, "GET", "/api/candidatos", cookie=cookie)
    assert len(almacen.eventos) == antes
    pedir(app, "POST", "/api/chat", cookie=cookie)
    assert almacen.eventos[-1]["es_ia"] and almacen.eventos[-1]["accion"] == "POST /api/chat"


def test_el_detalle_solo_toma_campos_permitidos():
    detalle = extraer_detalle(json.dumps({
        "candidato_id": "CAN-1", "puntaje": 80, "nombre": "Luis", "correo": "l@x.co",
        "lectura": {"confianza": {"profesion": 0.9}, "telefono": "3001234567"},
    }).encode())
    assert detalle == {"candidato_id": "CAN-1", "puntaje": 80, "confianza": {"profesion": 0.9}}
