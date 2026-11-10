"""Tareas programadas y prueba de integración completa: seguridad + motor + visión + chat."""
import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import settings
from app.main import app as aplicacion
from app.seguridad.almacen import AlmacenSQL
from app.seguridad.envoltura import Protector
from app.services import lectura, llm, tareas
from app.services.lectura import ResultadoOCR

from .conftest import imagen_con_texto, json_ia, modelo_que_responde
from .test_vision import TEXTO_OCR, ia_formulario


def _candidato(puntaje, zona):
    db.insertar_candidato({"fecha": db.ahora(), "nombre": "X Y", "correo": "x@y.co", "cargo": "Contador",
                           "puntaje": puntaje, "zona": zona, "estado": "-"})


# ───────────────────────── Tareas programadas ─────────────────────────
def test_resumen_diario_cuenta_por_zona_y_pendientes():
    _candidato(90, "alto"), _candidato(85, "alto"), _candidato(40, "bajo")
    db.insertar_lectura({"fecha": db.ahora(), "estado": "pendiente"})
    r = tareas.enviar_resumen()
    assert (r["nuevos"], r["alto"], r["bajo"], r["pendientes"]) == (3, 2, 1, 1)
    assert "CAN-0001 (90)" in r["texto"]
    assert db.listar_ejecuciones(flujo="resumen_diario")[0]["estado"] == "ok"


def test_el_ciclo_envia_el_resumen_una_sola_vez_por_dia(monkeypatch):
    monkeypatch.setattr(settings, "resumen_hora", 0)
    tareas.ciclo()
    tareas.ciclo()
    assert len(db.listar_ejecuciones(flujo="resumen_diario")) == 1


def test_el_ciclo_reintenta_las_fotos_sin_ia(monkeypatch):
    monkeypatch.setattr(settings, "resumen_hora", 99)  # sin resumen en esta prueba
    db.insertar_lectura({"fecha": db.ahora(), "estado": "pendiente", "ia_pendiente": True, "cargo": "Contador",
                         "nombre": "Ana", "correo": "a@b.co", "texto_enmascarado": TEXTO_OCR, "confianza_ocr": 0.9})
    llm.usar_modelos([modelo_que_responde(ia_formulario(puntaje=70))])
    tareas.ciclo()
    assert db.listar_ejecuciones(flujo="reintento_vision")[0]["resultado"]["reintentadas"] == 1


# ───────────────────────── Integración con la capa de seguridad ─────────────────────────
@pytest.fixture
def sistema(monkeypatch):
    monkeypatch.setattr(lectura, "leer", lambda _img: ResultadoOCR(TEXTO_OCR, 0.66, len(TEXTO_OCR.split())))
    protegido = Protector(
        aplicacion, AlmacenSQL(settings.database_url), "secreto-de-prueba",
        usuarios_iniciales=settings.usuarios_iniciales(),
    )
    with TestClient(protegido) as c:
        yield c, protegido.almacen


def entrar(c, usuario, clave):
    c.cookies.clear()
    r = c.post("/login", data={"usuario": usuario, "clave": clave}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_recorrido_completo_con_roles_y_auditoria(sistema):
    c, almacen = sistema
    assert c.get("/api/candidatos").status_code == 401

    # 1. El reclutador sube una foto dudosa: queda pendiente y se registra quién la subió.
    entrar(c, "reclutador", "Recluta.2026")
    llm.usar_modelos([modelo_que_responde(ia_formulario(puntaje=58))])
    r = c.post("/api/vision", data={"Nombre": "Andrés Rodríguez", "Correo": "andres@x.co",
                                     "Cargo": "Desarrollador de software", "Autorizacion": "true"},
               files={"Imagen": ("ficha.jpg", imagen_con_texto(["x"]), "image/jpeg")})
    assert r.status_code == 201 and r.json()["estado"] == "requiere_revision"
    lectura_id = r.json()["lectura_id"]
    assert db.obtener_lectura(lectura_id)["subido_por"] == "reclutador"

    # 2. Consulta no puede ver la foto ni confirmar.
    entrar(c, "consulta", "Consulta.2026")
    assert c.get(f"/api/vision/{lectura_id}/imagen").status_code == 403
    assert c.post(f"/api/vision/{lectura_id}/confirmar", json={"campos": {}}).status_code == 403

    # 3. El reclutador confirma con una corrección: la visión dispara el proceso (candidato + estado).
    entrar(c, "reclutador", "Recluta.2026")
    llm.usar_modelos([modelo_que_responde(json_ia(puntaje=82))])
    campos = {"profesion": "Ingeniero de sistemas", "experiencia_anios": 5, "habilidades": "Python, SQL",
              "educacion": "Ingeniería de Sistemas", "certificaciones": "No indica"}
    r = c.post(f"/api/vision/{lectura_id}/confirmar", json={"campos": campos})
    assert r.json()["candidato"]["estado"] == "Preseleccionado"
    assert db.obtener_lectura(lectura_id)["revisado_por"] == "reclutador"

    # 4. El chatbot usa el resultado de la visión.
    recibidos = []
    llm.usar_modelos([modelo_que_responde("Andrés (CAN-0001) llegó por foto.", recibidos)])
    assert c.post("/api/chat", json={"pregunta": "¿Quién llegó por foto?"}).status_code == 200
    assert '"origen": "foto"' in recibidos[0] and "CAN-0001" in recibidos[0]

    # 5. El admin ve la auditoría con las acciones de la IA y sin datos personales.
    entrar(c, "admin", "Admin.2026")
    eventos = c.get("/api/auditoria?solo_ia=1").json()
    acciones = {e["accion"] for e in eventos}
    assert {"POST /api/vision", "POST /api/vision/{id}/confirmar", "POST /api/chat"} <= acciones
    assert all("andres@x.co" not in e["detalle"] for e in almacen.auditoria(500))
    assert c.get("/api/ejecuciones").status_code == 200
    assert c.post("/api/tareas/resumen").status_code == 200


def test_reclutador_no_ejecuta_tareas_de_admin(sistema):
    c, _ = sistema
    entrar(c, "reclutador", "Recluta.2026")
    assert c.post("/api/tareas/resumen").status_code == 403
    assert c.get("/api/ejecuciones").status_code == 403
