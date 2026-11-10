"""Flujo «Lista de candidatos» de n8n: devuelve la tabla para el panel.

Disparador: GET /api/candidatos (antes: Webhook GET de n8n que leía la Data Table).
"""
from .. import db
from .registro import ejecucion

CARGOS_POR_DEFECTO = [
    "Desarrollador de software",
    "Analista de datos",
    "Auxiliar administrativo",
    "Asesor comercial",
    "Técnico de soporte",
    "Contador",
]


def listar() -> list[dict]:
    with ejecucion("lista") as e:
        filas = db.listar_candidatos()
        e["resultado"] = {"elementos": len(filas)}
        return filas


def cargos() -> list[str]:
    usados = [c["cargo"] for c in db.listar_candidatos()]
    return list(dict.fromkeys(CARGOS_POR_DEFECTO + usados))


def eliminar(candidato_id: str) -> bool:
    """Supresión de datos a solicitud del titular (Ley 1581): borra el registro del candidato."""
    with ejecucion("supresion", {"candidato_id": candidato_id}) as e:
        borrado = db.borrar_candidato(candidato_id)
        e["resultado"] = {"candidato_id": candidato_id, "borrado": borrado}
        return borrado
