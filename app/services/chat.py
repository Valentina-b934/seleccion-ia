"""Flujo «Chat Selección de Personal» de n8n.

Disparador: POST /api/chat (antes: Chat Trigger de n8n → Data Table → Basic LLM Chain).
El asistente responde con la tabla de candidatos actual (incluidos los que llegaron por foto)
y además conoce las lecturas del módulo de visión que esperan revisión humana.
Recuerda los últimos turnos de cada usuario (memoria de LangChain, ver llm.py).
"""
from .. import db
from ..errores import EntradaInvalida
from . import llm
from .registro import ejecucion

MAX_PREGUNTA = 600


def _contexto_vision() -> str:
    pendientes = db.listar_lecturas("pendiente", limite=50)
    if not pendientes:
        return "Módulo de visión: no hay fotos esperando revisión humana."
    lineas = [
        f"- lectura {p['id']} ({p['cargo']}, subida por {p.get('subido_por') or 'sin dato'}, "
        f"confianza OCR {round((p.get('confianza_ocr') or 0) * 100)} %)"
        for p in pendientes
    ]
    return (
        f"Módulo de visión: hay {len(pendientes)} foto(s) de hojas de vida esperando revisión humana "
        "(todavía no son candidatos). Si preguntan por pendientes, dilas así:\n" + "\n".join(lineas)
    )


def responder(pregunta: str) -> dict:
    pregunta = (pregunta or "").strip()
    if not pregunta:
        raise EntradaInvalida("Escribe una pregunta.")
    if len(pregunta) > MAX_PREGUNTA:
        raise EntradaInvalida(f"La pregunta es muy larga (máximo {MAX_PREGUNTA} caracteres).")
    with ejecucion("chat", {"pregunta": pregunta}) as e:
        candidatos = db.listar_candidatos()
        respuesta = llm.responder_chat(pregunta, candidatos, extra=_contexto_vision())
        e["resultado"] = {"candidatos_en_contexto": len(candidatos), "modelo": llm.ultimo_modelo(),
                          "respuesta_caracteres": len(str(respuesta))}  # la respuesta lleva nombres: no se guarda
        return {"respuesta": str(respuesta), "modelo": llm.ultimo_modelo()}
