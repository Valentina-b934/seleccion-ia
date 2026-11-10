"""Tareas programadas del motor (el «Schedule Trigger» de n8n, ahora en código).

Un hilo en segundo plano se despierta cada TAREAS_MINUTOS y hace dos cosas:

1. Cola de reintento del módulo de visión: si una foto quedó sin interpretar porque la IA no respondió,
   la vuelve a enviar (plan B ante cuota agotada).
2. Resumen diario por Telegram a la hora RESUMEN_HORA (hora de Colombia por defecto): candidatos nuevos
   de las últimas 24 horas por zona y fotos que esperan revisión humana. Se envía una sola vez por día
   (se consulta el registro de ejecuciones, así que un reinicio no lo repite).

Ambas tareas también se pueden ejecutar a mano (solo admin): POST /api/tareas/resumen y /api/tareas/reintentar.
Cada ejecución queda en el registro con los flujos «resumen_diario» y «reintento_vision».
"""
import logging
import threading
from datetime import datetime, timedelta, timezone

from .. import db
from ..config import settings
from . import telegram, vision
from .registro import ejecucion

log = logging.getLogger("seleccion")

_parar = threading.Event()
_hilo: threading.Thread | None = None


def _ahora_local() -> datetime:
    return datetime.now(timezone(timedelta(hours=settings.zona_horaria_horas)))


def armar_resumen(horas: int = 24) -> dict:
    limite = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat(timespec="seconds")
    nuevos = [c for c in db.listar_candidatos() if (c.get("fecha") or "") >= limite]
    por_zona = {"alto": 0, "medio": 0, "bajo": 0}
    for c in nuevos:
        por_zona[c.get("zona") or "bajo"] = por_zona.get(c.get("zona") or "bajo", 0) + 1
    pendientes = db.listar_lecturas("pendiente", limite=200)
    mejores = sorted(nuevos, key=lambda c: -int(c.get("puntaje") or 0))[:3]
    lineas = [
        f"Resumen de selección ({_ahora_local():%Y-%m-%d})",
        f"Candidatos nuevos en {horas} h: {len(nuevos)}",
        f"  · Preseleccionados (80+): {por_zona['alto']}",
        f"  · En revisión (60-79): {por_zona['medio']}",
        f"  · Descartados (<60): {por_zona['bajo']}",
        f"Fotos esperando revisión humana: {len(pendientes)}",
    ]
    if mejores:
        lineas.append("Mejores puntajes: " + "; ".join(f"{c['candidato_id']} ({c['puntaje']})" for c in mejores))
    return {"texto": "\n".join(lineas), "nuevos": len(nuevos), "pendientes": len(pendientes), **por_zona}


def enviar_resumen() -> dict:
    with ejecucion("resumen_diario", {"horas": 24}) as e:
        resumen = armar_resumen()
        enviado = telegram.avisar(resumen["texto"])
        e["resultado"] = {k: v for k, v in resumen.items() if k != "texto"} | {"aviso_telegram": enviado}
        return {**resumen, "aviso_telegram": enviado}


def reintentar_vision() -> dict:
    with ejecucion("reintento_vision") as e:
        resultado = vision.reintentar_pendientes_ia()
        e["resultado"] = resultado
        return resultado


def _resumen_de_hoy_enviado() -> bool:
    hoy = _ahora_local().date()
    for ej in db.listar_ejecuciones(limite=20, flujo="resumen_diario"):
        try:
            fecha = datetime.fromisoformat(ej["fecha"]).astimezone(_ahora_local().tzinfo).date()
        except (TypeError, ValueError):
            continue
        if fecha == hoy and ej["estado"] == "ok":
            return True
    return False


def ciclo() -> None:
    """Una vuelta del programador. Nunca lanza errores: el hilo debe seguir vivo."""
    try:
        if any(x.get("ia_pendiente") for x in db.listar_lecturas("pendiente", limite=200)):
            reintentar_vision()
    except Exception as e:  # noqa: BLE001
        log.error("Tarea de reintento falló: %s", e)
    try:
        if _ahora_local().hour >= settings.resumen_hora and not _resumen_de_hoy_enviado():
            enviar_resumen()
    except Exception as e:  # noqa: BLE001
        log.error("Tarea de resumen falló: %s", e)


def _bucle():
    log.info("Tareas programadas activas: cada %s minutos", settings.tareas_minutos)
    while not _parar.wait(max(1, settings.tareas_minutos) * 60):
        ciclo()


def iniciar() -> None:
    global _hilo
    if not settings.tareas_activas or (_hilo and _hilo.is_alive()):
        return
    _parar.clear()
    _hilo = threading.Thread(target=_bucle, name="tareas-programadas", daemon=True)
    _hilo.start()


def detener() -> None:
    _parar.set()
