"""Registro de ejecuciones: el equivalente a la pestaña «Executions» de n8n.

Cada flujo se ejecuta dentro de `with ejecucion("carga", entrada) as e:` y al terminar queda una fila
en la tabla `ejecuciones` con fecha, flujo, usuario, entrada, resultado, duración y error (si lo hubo).
La entrada y el resultado pasan por `limpiar()`, que quita correos, nombres y teléfonos.
Si guardar el registro falla, el flujo no se cae: solo se escribe el problema en el log.
"""
import logging
import time
from contextlib import contextmanager

from .. import db
from ..errores import ErrorDeUsuario
from ..seguridad.contexto import nombre_usuario_actual

log = logging.getLogger("seleccion")

PRIVADOS = {"nombre", "correo", "telefono", "documento", "direccion", "texto", "texto_enmascarado"}


def limpiar(datos):
    if isinstance(datos, dict):
        return {k: limpiar(v) for k, v in datos.items() if k not in PRIVADOS}
    if isinstance(datos, list):
        return [limpiar(v) for v in datos[:50]]
    if isinstance(datos, str) and len(datos) > 300:
        return datos[:300] + "…"
    return datos


def _guardar(flujo, estado, inicio, entrada, resultado, error=""):
    try:
        db.insertar_ejecucion({
            "fecha": db.ahora(),
            "flujo": flujo,
            "estado": estado,
            "duracion_ms": int((time.perf_counter() - inicio) * 1000),
            "usuario": nombre_usuario_actual(),
            "entrada": limpiar(entrada or {}),
            "resultado": limpiar(resultado or {}),
            "error": error[:500],
        })
    except Exception as e:  # noqa: BLE001
        log.error("No se pudo guardar el registro de la ejecución %s: %s", flujo, e)


@contextmanager
def ejecucion(flujo: str, entrada: dict | None = None):
    """Mide y registra un flujo. Dentro del bloque se llena `info["resultado"]`."""
    info = {"resultado": {}}
    inicio = time.perf_counter()
    try:
        yield info
    except ErrorDeUsuario as e:
        _guardar(flujo, "error", inicio, entrada, info["resultado"], f"{type(e).__name__}: {e.mensaje}")
        log.warning("Flujo %s terminó con error controlado: %s", flujo, e.mensaje)
        raise
    except Exception as e:
        _guardar(flujo, "error", inicio, entrada, info["resultado"], f"{type(e).__name__}: {e}")
        log.exception("Flujo %s falló", flujo)
        raise
    else:
        _guardar(flujo, "ok", inicio, entrada, info["resultado"])
        log.info("Flujo %s ok en %d ms", flujo, int((time.perf_counter() - inicio) * 1000))


def listar(limite: int = 200, flujo: str | None = None) -> list[dict]:
    return db.listar_ejecuciones(limite, flujo)
