"""Usuario de la petición en curso.

La capa de seguridad lo fija antes de entregar la petición a la aplicación, así cualquier
servicio (por ejemplo la memoria del chat) sabe quién está usando el sistema sin cambiar
las firmas de las funciones existentes. Sin sesión (pruebas, scripts) vale "anonimo".
"""
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class UsuarioActual:
    usuario: str = "anonimo"
    rol: str = "ninguno"


usuario_actual: ContextVar[UsuarioActual] = ContextVar("usuario_actual", default=UsuarioActual())


def nombre_usuario_actual() -> str:
    return usuario_actual.get().usuario
