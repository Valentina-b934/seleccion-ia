"""Reglas de decisión: el nodo «Switch» de n8n.

80 o más  → zona alta  → Preseleccionado (citar a entrevista)
60 a 79   → zona media → En revisión (revisión manual)
menos 60  → zona baja  → Descartado (archivar)

Los umbrales salen de UMBRAL_ALTO y UMBRAL_MEDIO en .env.
"""
from dataclasses import dataclass

from ..config import settings


@dataclass(frozen=True)
class Decision:
    zona: str
    estado: str
    accion: str


def zona(puntaje: int) -> Decision:
    puntaje = int(puntaje or 0)
    if puntaje >= settings.umbral_alto:
        return Decision("alto", "Preseleccionado", "Citar a entrevista")
    if puntaje >= settings.umbral_medio:
        return Decision("medio", "En revisión", "Revisión manual por Recursos Humanos")
    return Decision("bajo", "Descartado", "Archivar la hoja de vida")
