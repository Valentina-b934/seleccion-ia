"""Quién puede hacer qué. Un solo lugar para leer y explicar los permisos.

| Acción                                              | admin | reclutador | consulta |
|-----------------------------------------------------|:-----:|:----------:|:--------:|
| Ver el panel, la lista de candidatos y las lecturas |   sí  |     sí     |    sí    |
| Preguntar al asistente (chat)                       |   sí  |     sí     |    sí    |
| Ver las fotos subidas                               |   sí  |     sí     |    no    |
| Subir PDF o fotos, confirmar o descartar lecturas   |   sí  |     sí     |    no    |
| Ver ejecuciones, auditoría, usuarios y /docs        |   sí  |     no     |    no    |
| Ejecutar a mano las tareas programadas              |   sí  |     no     |    no    |
"""
import re

ROLES = ("admin", "reclutador", "consulta")

SOLO_ADMIN = (
    "/api/ejecuciones", "/api/auditoria", "/api/usuarios", "/api/tareas", "/docs", "/redoc", "/openapi.json", "/auditoria",
)
RUTAS_PUBLICAS = ("/login", "/_salud", "/_sesion/sesion.js")
LECTURA = ("GET", "HEAD")
_IMAGEN = re.compile(r"^/api/vision/[^/]+/imagen$")


def normalizar(ruta: str) -> str:
    return ruta.rstrip("/") or "/"


def es_pagina(ruta: str) -> bool:
    return ruta == "/" or ruta.endswith(".html")


def _empieza(ruta: str, prefijo: str) -> bool:
    return ruta == prefijo or ruta.startswith(prefijo + "/")


def es_solo_admin(ruta: str) -> bool:
    return any(_empieza(ruta, p) for p in SOLO_ADMIN)


def es_publica(metodo: str, ruta: str) -> bool:
    """Rutas que no piden sesión: la página de inicio de sesión y los archivos estáticos (CSS, JS, íconos)."""
    ruta = normalizar(ruta)
    if metodo == "OPTIONS" or ruta in RUTAS_PUBLICAS:
        return True
    return (
        metodo in LECTURA
        and not ruta.startswith("/api")
        and not es_pagina(ruta)
        and not es_solo_admin(ruta)
    )


def permitido(rol: str, metodo: str, ruta: str) -> bool:
    ruta = normalizar(ruta)
    if rol not in ROLES:
        return False
    if rol == "admin":
        return True
    if es_solo_admin(ruta):
        return False
    if metodo in LECTURA:
        if _IMAGEN.match(ruta):
            return rol == "reclutador"
        return True
    if ruta in ("/api/chat", "/api/chat/olvidar", "/logout"):
        return True
    return rol == "reclutador"


def es_accion_ia(metodo: str, ruta: str) -> bool:
    """Peticiones en las que interviene la IA: carga de PDF, módulo de visión y chat."""
    ruta = normalizar(ruta)
    return metodo == "POST" and (
        ruta == "/api/candidatos" or _empieza(ruta, "/api/vision") or ruta == "/api/chat"
        or ruta == "/api/tareas/reintentar"
    )


def debe_auditarse(metodo: str, ruta: str) -> bool:
    ruta = normalizar(ruta)
    if not ruta.startswith("/api"):
        return False
    return metodo not in (*LECTURA, "OPTIONS") or bool(_IMAGEN.match(ruta))


def plantilla(ruta: str) -> tuple[str, str]:
    """Cambia los identificadores de la ruta por {id}. Devuelve (plantilla, id encontrado)."""
    partes, encontrado = [], ""
    for parte in normalizar(ruta).split("/"):
        if parte and re.search(r"\d", parte) and not parte.startswith("api"):
            encontrado = encontrado or parte
            partes.append("{id}")
        else:
            partes.append(parte)
    return "/".join(partes) or "/", encontrado
