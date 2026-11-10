"""Memoria del chat con LangChain: cada usuario tiene su conversación y se puede borrar."""
from langchain_core.runnables import RunnableLambda

from app.config import settings
from app.seguridad.contexto import UsuarioActual, usuario_actual
from app.services import llm

FILAS = [{"candidato_id": "CAN-1", "nombre": "Ana Ruiz", "puntaje": 90}]


def _modelo_que_anota(recibidos):
    def _modelo(prompt_value):
        recibidos.append(prompt_value.to_string())
        return f"respuesta {len(recibidos)}"

    return RunnableLambda(_modelo)


def _como(usuario):
    return usuario_actual.set(UsuarioActual(usuario, "reclutador"))


def test_la_segunda_pregunta_recibe_la_primera():
    llm.olvidar_memoria()
    recibidos = []
    llm.usar_modelos([_modelo_que_anota(recibidos)])
    ficha = _como("ana")
    try:
        llm.responder_chat("¿Quién tiene mejor puntaje?", FILAS)
        llm.responder_chat("¿Y qué estudió?", FILAS)
    finally:
        usuario_actual.reset(ficha)
    assert "¿Quién tiene mejor puntaje?" in recibidos[1]
    assert "respuesta 1" in recibidos[1]


def test_cada_usuario_tiene_su_propia_conversacion():
    llm.olvidar_memoria()
    recibidos = []
    llm.usar_modelos([_modelo_que_anota(recibidos)])
    for usuario, pregunta in (("ana", "pregunta de ana"), ("luis", "pregunta de luis")):
        ficha = _como(usuario)
        try:
            llm.responder_chat(pregunta, FILAS)
        finally:
            usuario_actual.reset(ficha)
    assert "pregunta de ana" not in recibidos[1]


def test_olvidar_y_limite_de_turnos(monkeypatch):
    llm.olvidar_memoria()
    monkeypatch.setattr(settings, "chat_memoria_turnos", 2)
    llm.usar_modelos([_modelo_que_anota([])])
    ficha = _como("ana")
    try:
        for i in range(5):
            llm.responder_chat(f"pregunta {i}", FILAS)
        assert len(llm.historial_chat("ana")) == 4  # 2 turnos: 2 preguntas y 2 respuestas
        llm.olvidar_memoria("ana")
        assert llm.historial_chat("ana") == []
    finally:
        usuario_actual.reset(ficha)


def test_sin_memoria_si_se_desactiva(monkeypatch):
    llm.olvidar_memoria()
    monkeypatch.setattr(settings, "chat_memoria_turnos", 0)
    llm.usar_modelos([_modelo_que_anota([])])
    llm.responder_chat("hola", FILAS)
    assert llm.historial_chat("anonimo") == []
