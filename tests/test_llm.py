import pytest

from app.config import settings
from app.errores import ServicioIANoDisponible
from app.services import llm

from .conftest import ModeloIntermitente, json_ia, modelo_que_falla, modelo_que_responde


def test_extrae_los_campos_del_json():
    llm.usar_modelos([modelo_que_responde(json_ia(puntaje=85, experiencia_anios=5))])
    datos = llm.extraer_datos("texto de la hoja de vida", "Analista de datos")
    assert datos.puntaje == 85
    assert datos.experiencia_anios == 5
    assert "JavaScript" in datos.habilidades


def test_acepta_json_dentro_de_un_bloque_markdown():
    llm.usar_modelos([modelo_que_responde("```json\n" + json_ia(puntaje=66) + "\n```")])
    assert llm.extraer_datos("x", "y").puntaje == 66


def test_corrige_valores_fuera_de_rango_o_con_otro_formato():
    texto = json_ia(puntaje=130, experiencia_anios="3.4", habilidades=["SQL", "Python"])
    llm.usar_modelos([modelo_que_responde(texto)])
    datos = llm.extraer_datos("x", "y")
    assert datos.puntaje == 100
    assert datos.experiencia_anios == 3
    assert datos.habilidades == "SQL, Python"


def test_reintenta_y_termina_bien():
    modelo = ModeloIntermitente(fallos=2, texto=json_ia())
    llm.usar_modelos([modelo.modelo])
    assert llm.extraer_datos("x", "y").puntaje == 72
    assert modelo.llamadas == 3  # 2 fallos + 1 éxito


def test_falla_si_se_agotan_los_reintentos(monkeypatch):
    monkeypatch.setattr(settings, "llm_reintentos", 2)
    modelo = ModeloIntermitente(fallos=5, texto=json_ia())
    llm.usar_modelos([modelo.modelo])
    with pytest.raises(ServicioIANoDisponible):
        llm.extraer_datos("x", "y")
    assert modelo.llamadas == 2


def test_plan_b_usa_el_segundo_modelo_si_el_primero_falla():
    llm.usar_modelos([modelo_que_falla(), modelo_que_responde(json_ia(puntaje=64))])
    assert llm.extraer_datos("x", "y").puntaje == 64


def test_plan_b_cuando_el_primer_modelo_devuelve_basura():
    llm.usar_modelos([modelo_que_responde("lo siento, no puedo"), modelo_que_responde(json_ia(puntaje=55))])
    assert llm.extraer_datos("x", "y").puntaje == 55


def test_sin_modelos_configurados_da_un_mensaje_claro():
    llm.usar_modelos([])
    with pytest.raises(ServicioIANoDisponible) as e:
        llm.extraer_datos("x", "y")
    assert "GROQ_API_KEY" in e.value.mensaje


def test_el_chat_recibe_los_candidatos_en_el_prompt():
    recibido = {}

    def _modelo(prompt_value):
        recibido["texto"] = prompt_value.to_string()
        return "Respuesta de prueba"

    from langchain_core.runnables import RunnableLambda

    llm.usar_modelos([RunnableLambda(_modelo)])
    filas = [{"candidato_id": "CAN-1", "nombre": "Ana Ruiz", "puntaje": 90}]
    assert llm.responder_chat("¿Quién tiene mejor puntaje?", filas) == "Respuesta de prueba"
    assert "Ana Ruiz" in recibido["texto"]
    assert "¿Quién tiene mejor puntaje?" in recibido["texto"]


def test_contexto_del_chat_respeta_el_limite(monkeypatch):
    monkeypatch.setattr(settings, "max_contexto_chat", 600)
    filas = [
        {"candidato_id": f"CAN-{i}", "nombre": f"Persona {i}", "justificacion": "x" * 200, "puntaje": i}
        for i in range(30)
    ]
    texto, omitidos = llm.preparar_contexto(filas)
    assert len(texto) <= 600
    assert omitidos > 0
    assert "CAN-29" in texto  # se conservan los más recientes


def test_se_puede_construir_el_cliente_de_openrouter(monkeypatch):
    llm.usar_modelos(None)
    monkeypatch.setattr(settings, "openrouter_api_key", "clave-falsa")
    monkeypatch.setattr(settings, "groq_api_key", "")
    monkeypatch.setattr(settings, "google_api_key", "")
    monkeypatch.setattr(settings, "llm_providers", ["openrouter", "groq", "gemini"])
    assert llm.nombres_modelos() == ["openrouter"]  # los proveedores sin clave se omiten


def test_se_pueden_construir_los_clientes_de_groq_y_gemini(monkeypatch):
    """Comprueba que los parámetros de LangChain son válidos (sin llamar a internet)."""
    monkeypatch.setattr(settings, "groq_api_key", "clave-falsa")
    monkeypatch.setattr(settings, "google_api_key", "clave-falsa")
    monkeypatch.setattr(settings, "llm_providers", ["groq", "gemini"])
    llm.usar_modelos(None)
    assert llm.nombres_modelos() == ["groq", "gemini"]


def test_tolera_modelos_que_piensan_en_voz_alta_o_agregan_texto():
    """openrouter/free a veces elige modelos de razonamiento: <think>...</think> o texto antes del JSON."""
    llm.usar_modelos([modelo_que_responde("<think>Analizo el perfil...</think>\nAquí está:\n" + json_ia(puntaje=83) + "\nEspero que sirva.")])
    assert llm.extraer_datos("x", "y").puntaje == 83


def test_tolera_contenido_en_partes_como_gemini_3():
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    partes = [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": json_ia(puntaje=77)}]
    llm.usar_modelos([RunnableLambda(lambda _p: AIMessage(content=partes))])
    assert llm.extraer_datos("x", "y").puntaje == 77
    llm.usar_modelos([RunnableLambda(lambda _p: AIMessage(content=[{"type": "text", "text": "<think>a</think>Hola"}]))])
    assert llm.responder_chat("hola", []) == "Hola"
