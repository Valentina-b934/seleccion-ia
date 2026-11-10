"""Avisos por Telegram: el nodo «Telegram» de n8n.

Si TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID están vacíos, el aviso se omite sin error.
Si Telegram falla, se reintenta 3 veces; si sigue fallando, el flujo continúa
(el candidato ya está guardado) y el fallo queda en el log y en el registro de la ejecución.
"""
import logging

import httpx
from tenacity import Retrying, stop_after_attempt, wait_exponential

from ..config import settings

log = logging.getLogger("seleccion")

_cliente_prueba = None  # las pruebas pueden inyectar un httpx.Client con transporte simulado


def configurado() -> bool:
    return bool(settings.telegram_token and settings.telegram_chat_id)


def avisar(texto: str) -> bool:
    """Envía un mensaje. Devuelve True si se envió, False si se omitió o falló."""
    if not configurado():
        log.info("Telegram sin configurar: aviso omitido")
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
    datos = {"chat_id": settings.telegram_chat_id, "text": texto[:4000]}
    try:
        for intento in Retrying(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8), reraise=True):
            with intento:
                cliente = _cliente_prueba or httpx.Client(timeout=15)
                try:
                    r = cliente.post(url, json=datos)
                    r.raise_for_status()
                finally:
                    if cliente is not _cliente_prueba:
                        cliente.close()
        return True
    except Exception as e:  # noqa: BLE001
        log.error("No se pudo enviar el aviso de Telegram: %s", type(e).__name__)
        return False


def mensaje_candidato(c: dict, accion: str) -> str:
    """Mismo contenido que el mensaje de n8n. Lleva el nombre (el canal es interno de Recursos Humanos), sin correo."""
    origen = "foto (módulo de visión)" if c.get("origen") == "foto" else "PDF"
    return (
        f"Nuevo candidato {c.get('candidato_id')}: {c.get('nombre')}\n"
        f"Cargo: {c.get('cargo')}\n"
        f"Puntaje: {c.get('puntaje')}/100 → {c.get('estado')}\n"
        f"Acción: {accion}\n"
        f"Profesión: {c.get('profesion')} · {c.get('experiencia_anios')} años\n"
        f"Origen: {origen}\n"
        f"Motivo: {c.get('justificacion')}"
    )
