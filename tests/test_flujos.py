"""Pruebas unitarias de los flujos migrados desde n8n: carga, decisión, Telegram, lista, chat y registro."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import settings
from app.main import app
from app.services import decision, llm, telegram

from .conftest import HOJA_PDF, json_ia, modelo_que_falla, modelo_que_responde, pdf_con_texto


@pytest.fixture
def cliente():
    with TestClient(app) as c:
        yield c


def subir_pdf(cliente, contenido=None, **campos):
    datos = {"Nombre": "Laura Pérez", "Correo": "laura.perez@gmail.com", "Cargo": "Analista de datos",
             "Autorizacion": "true", **campos}
    archivo = {"Archivo": ("hoja.pdf", contenido if contenido is not None else pdf_con_texto(HOJA_PDF), "application/pdf")}
    return cliente.post("/api/candidatos", data=datos, files=archivo)


# ───────────────────────── Decisión (nodo Switch) ─────────────────────────
@pytest.mark.parametrize("puntaje, zona, estado", [
    (100, "alto", "Preseleccionado"), (80, "alto", "Preseleccionado"), (79, "medio", "En revisión"),
    (60, "medio", "En revisión"), (59, "bajo", "Descartado"), (0, "bajo", "Descartado"),
])
def test_zonas_de_decision(puntaje, zona, estado):
    d = decision.zona(puntaje)
    assert (d.zona, d.estado) == (zona, estado)


def test_los_umbrales_salen_de_la_configuracion(monkeypatch):
    monkeypatch.setattr(settings, "umbral_alto", 90)
    assert decision.zona(85).zona == "medio"


# ───────────────────────── Flujo de carga ─────────────────────────
def test_carga_de_pdf_guarda_el_candidato_con_su_estado(cliente):
    llm.usar_modelos([modelo_que_responde(json_ia(puntaje=85))])
    r = subir_pdf(cliente)
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["candidato_id"] == "CAN-0001"
    assert (c["puntaje"], c["zona"], c["estado"], c["origen"]) == (85, "alto", "Preseleccionado", "pdf")
    assert c["modelo"] == "modelo-1"
    assert db.buscar_candidato("CAN-0001")["nombre"] == "Laura Pérez"


def test_a_la_ia_no_llegan_datos_personales_del_pdf(cliente):
    recibidos = []
    llm.usar_modelos([modelo_que_responde(json_ia(), recibidos)])
    subir_pdf(cliente)
    enviado = recibidos[0]
    assert "laura.perez@gmail.com" not in enviado and "315 678 9012" not in enviado
    assert "[CORREO]" in enviado and "Python" in enviado


def test_carga_sin_autorizacion_se_rechaza_y_queda_registrada(cliente):
    llm.usar_modelos([modelo_que_responde(json_ia())])
    r = subir_pdf(cliente, Autorizacion="false")
    assert r.status_code == 400 and "Ley 1581" in r.json()["mensaje"]
    ej = db.listar_ejecuciones(flujo="carga")[0]
    assert ej["estado"] == "error" and "Ley 1581" in ej["error"]
    assert db.listar_candidatos() == []


@pytest.mark.parametrize("contenido, codigo, texto", [
    (b"no soy un pdf", 400, "no es un PDF"),
    (b"", 400, "vacío"),
    (pdf_con_texto(["hola"]), 422, "escaneado"),
])
def test_archivos_invalidos_dan_un_mensaje_claro(cliente, contenido, codigo, texto):
    llm.usar_modelos([modelo_que_responde(json_ia())])
    r = subir_pdf(cliente, contenido=contenido)
    assert r.status_code == codigo and texto in r.json()["mensaje"]


def test_correo_invalido(cliente):
    r = subir_pdf(cliente, Correo="no-es-correo")
    assert r.status_code == 400 and "correo" in r.json()["mensaje"]


def test_si_la_ia_no_responde_el_usuario_recibe_503_y_no_se_guarda_nada(cliente, monkeypatch):
    monkeypatch.setattr(settings, "llm_reintentos", 2)
    llm.usar_modelos([modelo_que_falla(), modelo_que_falla()])
    r = subir_pdf(cliente)
    assert r.status_code == 503 and "intenta de nuevo" in r.json()["mensaje"]
    assert db.listar_candidatos() == []
    assert db.listar_ejecuciones(flujo="carga")[0]["estado"] == "error"


def test_plan_b_el_segundo_modelo_responde_y_queda_anotado(cliente):
    llm.usar_modelos([modelo_que_falla(), modelo_que_responde(json_ia(puntaje=61))])
    r = subir_pdf(cliente)
    assert r.status_code == 201 and r.json()["modelo"] == "modelo-2" and r.json()["estado"] == "En revisión"


# ───────────────────────── Telegram ─────────────────────────
def _telegram_simulado(monkeypatch, respuesta):
    monkeypatch.setattr(settings, "telegram_token", "123:abc")
    monkeypatch.setattr(settings, "telegram_chat_id", "999")
    enviados = []

    def manejar(peticion):
        enviados.append(json.loads(peticion.content))
        return respuesta(len(enviados))

    telegram._cliente_prueba = httpx.Client(transport=httpx.MockTransport(manejar))
    return enviados


def test_avisa_por_telegram_con_el_mismo_mensaje_de_n8n(cliente, monkeypatch):
    enviados = _telegram_simulado(monkeypatch, lambda n: httpx.Response(200, json={"ok": True}))
    llm.usar_modelos([modelo_que_responde(json_ia(puntaje=90))])
    r = subir_pdf(cliente)
    assert r.json()["aviso_telegram"] is True
    texto = enviados[0]["text"]
    assert "CAN-0001" in texto and "90/100" in texto and "Citar a entrevista" in texto
    assert "laura.perez@gmail.com" not in texto


def test_si_telegram_falla_se_reintenta_y_el_candidato_igual_se_guarda(cliente, monkeypatch):
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _s: None)
    enviados = _telegram_simulado(monkeypatch, lambda n: httpx.Response(502))
    llm.usar_modelos([modelo_que_responde(json_ia())])
    r = subir_pdf(cliente)
    assert r.status_code == 201 and r.json()["aviso_telegram"] is False
    assert len(enviados) == 3  # tres intentos


def test_sin_configurar_telegram_se_omite():
    assert telegram.avisar("hola") is False


# ───────────────────────── Lista, chat, supresión y registro ─────────────────────────
def test_lista_y_supresion(cliente):
    llm.usar_modelos([modelo_que_responde(json_ia())])
    subir_pdf(cliente)
    assert [c["candidato_id"] for c in cliente.get("/api/candidatos").json()] == ["CAN-0001"]
    assert cliente.delete("/api/candidatos/CAN-0001").status_code == 200
    assert cliente.get("/api/candidatos").json() == []
    assert cliente.delete("/api/candidatos/CAN-0001").status_code == 404


def test_el_chat_usa_la_tabla_y_conoce_las_fotos_pendientes(cliente):
    llm.usar_modelos([modelo_que_responde(json_ia())])
    subir_pdf(cliente)
    db.insertar_lectura({"fecha": db.ahora(), "cargo": "Contador", "estado": "pendiente", "confianza_ocr": 0.62})
    recibidos = []
    llm.usar_modelos([modelo_que_responde("Laura tiene 72 puntos.", recibidos)])
    r = cliente.post("/api/chat", json={"pregunta": "¿Quién va primero?"})
    assert r.status_code == 200 and r.json()["respuesta"] == "Laura tiene 72 puntos."
    assert "CAN-0001" in recibidos[0] and "1 foto(s)" in recibidos[0]


def test_el_chat_valida_la_pregunta(cliente):
    assert cliente.post("/api/chat", json={"pregunta": "  "}).status_code == 400
    assert cliente.post("/api/chat", json={"pregunta": "x" * 700}).status_code == 400


def test_el_registro_guarda_fecha_entrada_y_resultado_sin_datos_personales(cliente):
    llm.usar_modelos([modelo_que_responde(json_ia(puntaje=85))])
    subir_pdf(cliente)
    ej = cliente.get("/api/ejecuciones?flujo=carga").json()[0]
    assert ej["estado"] == "ok" and ej["fecha"] and ej["duracion_ms"] >= 0
    assert ej["entrada"]["archivo"] == "hoja.pdf" and ej["resultado"]["candidato_id"] == "CAN-0001"
    assert "laura" not in json.dumps(ej).lower()


def test_estado_del_sistema(cliente):
    llm.usar_modelos([modelo_que_responde("{}")])
    s = cliente.get("/api/estado").json()
    assert s["ok"] and s["modelos"] == ["modelo-1"] and "Analista de datos" in s["cargos"]


def test_el_panel_se_sirve_desde_el_mismo_servidor(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and "Selección de personal" in r.text
    assert cliente.get("/app.js").status_code == 200
