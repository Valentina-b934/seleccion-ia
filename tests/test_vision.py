"""Módulo de visión: confianza por campo, revisión humana, plan B, privacidad y almacenamiento.

La mayoría simula el OCR para que las pruebas sean exactas. Las del final usan Tesseract de verdad
y se omiten solas si no está instalado.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import settings
from app.main import app
from app.services import lectura, llm, vision
from app.services.lectura import ResultadoOCR

from .conftest import imagen_con_texto, imagen_vacia, json_ia, modelo_que_falla, modelo_que_responde

TEXTO_OCR = """HOJA DE VIDA
Nombre: Andrés Felipe Rodríguez
Correo: andres.rodriguez@gmail.com Celular: 312 456 7890
Profesión: Ingeniero de sistemas
Experiencia: 4 años como desarrollador backend
Habilidades: Python, SQL, JavaScript
Educación: Ingeniería de Sistemas, UTP
Certificaciones: No indica"""


@pytest.fixture
def cliente():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def ocr(monkeypatch):
    """Permite fijar lo que 'lee' el OCR en cada prueba."""
    estado = {"texto": TEXTO_OCR, "confianza": 0.91}

    def falso(_imagen):
        palabras = len(estado["texto"].split())
        return ResultadoOCR(texto=estado["texto"], confianza=estado["confianza"], palabras=palabras)

    monkeypatch.setattr(lectura, "leer", falso)
    return estado


def subir_foto(cliente, contenido=None, nombre_archivo="ficha.jpg", **campos):
    datos = {"Nombre": "Andrés Felipe Rodríguez", "Correo": "andres.rodriguez@gmail.com",
             "Cargo": "Desarrollador de software", "Autorizacion": "true", **campos}
    contenido = contenido if contenido is not None else imagen_con_texto(["Hoja de vida"])
    return cliente.post("/api/vision", data=datos, files={"Imagen": (nombre_archivo, contenido, "image/jpeg")})


def ia_formulario(**cambios):
    confianza = cambios.pop("confianza", {c: 0.95 for c in llm.CAMPOS_VISION})
    return json_ia(confianza=confianza, **cambios)


# ───────────────────────── Confianza por campo ─────────────────────────
def test_presencia_detecta_datos_que_no_estan_en_el_texto():
    assert vision.presencia("habilidades", "Python, SQL", TEXTO_OCR) == 1.0
    assert vision.presencia("habilidades", "Pyth0n, SQL", TEXTO_OCR) >= 0.8  # error típico de OCR
    assert vision.presencia("habilidades", "Kubernetes, Rust", TEXTO_OCR) == 0.0  # inventado por la IA
    assert vision.presencia("experiencia_anios", 4, TEXTO_OCR) == 1.0
    assert vision.presencia("experiencia_anios", 9, TEXTO_OCR) < 0.7
    assert vision.presencia("certificaciones", "No indica", TEXTO_OCR) == 1.0


def test_la_confianza_final_es_la_mas_baja_de_las_tres():
    campos = {"profesion": "Ingeniero de sistemas", "experiencia_anios": 4, "habilidades": "Python, Rust",
              "educacion": "Ingeniería de Sistemas", "certificaciones": "No indica"}
    conf_ia = {c: 0.9 for c in campos} | {"profesion": 0.4}
    conf = vision.calcular_confianza(campos, conf_ia, TEXTO_OCR, 0.8)
    assert conf["profesion"] == 0.4  # manda la IA
    assert conf["habilidades"] == 0.5  # manda la presencia (Rust no está)
    assert conf["educacion"] == 0.8  # manda el OCR


def test_motivos_de_revision(monkeypatch):
    campos = {"profesion": "No indica", "habilidades": "Python"}
    motivos = vision.motivos_revision(campos, {"profesion": 0.9, "habilidades": 0.3}, 0.65)
    texto = " ".join(motivos)
    assert "calidad media" in texto and "habilidades (30 %)" in texto and "No se encontró profesión" in texto
    assert vision.motivos_revision({"profesion": "X", "habilidades": "Y"}, {"profesion": 0.9}, 0.9) == []


# ───────────────────────── Flujo completo ─────────────────────────
def test_foto_confiable_crea_el_candidato_y_dispara_el_proceso(cliente, ocr):
    llm.usar_modelos([modelo_que_responde(ia_formulario(puntaje=84, habilidades="Python, SQL, JavaScript"))])
    r = subir_foto(cliente)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["estado"] == "guardado" and d["candidato_id"] == "CAN-0001"
    c = d["candidato"]
    assert (c["origen"], c["estado"], c["zona"]) == ("foto", "Preseleccionado", "alto")
    lect = db.obtener_lectura(d["lectura_id"])
    assert lect["estado"] == "guardada" and lect["candidato_id"] == "CAN-0001"
    assert lect["sha256"] and lect["archivo_guardado"].endswith(".jpg")
    assert lect["archivo_guardado"] != "ficha.jpg"  # nombre aleatorio
    assert os.path.exists(os.path.join(settings.imagenes_dir, lect["archivo_guardado"]))


def test_a_la_ia_solo_llega_el_texto_sin_datos_personales(cliente, ocr):
    recibidos = []
    llm.usar_modelos([modelo_que_responde(ia_formulario(), recibidos)])
    subir_foto(cliente)
    enviado = recibidos[0]
    for dato in ("andres.rodriguez@gmail.com", "312 456 7890", "Andrés", "Rodríguez"):
        assert dato not in enviado, dato
    assert "Python" in enviado and "[CORREO]" in enviado


def test_el_nombre_mal_leido_por_el_ocr_tambien_se_oculta(cliente, ocr):
    ocr["texto"] = TEXTO_OCR.replace("Rodríguez", "Rodriquez").replace("Nombre:", "")
    recibidos = []
    llm.usar_modelos([modelo_que_responde(ia_formulario(), recibidos)])
    subir_foto(cliente)
    assert "Rodriquez" not in recibidos[0]


def test_lectura_dudosa_pide_revision_humana(cliente, ocr):
    ocr["confianza"] = 0.66
    llm.usar_modelos([modelo_que_responde(ia_formulario(habilidades="Python, Kubernetes"))])
    d = subir_foto(cliente).json()
    assert d["estado"] == "requiere_revision" and d["candidato_id"] is None
    assert any("calidad media" in m for m in d["lectura"]["motivos"])
    assert d["lectura"]["confianza"]["habilidades"] < settings.umbral_campo
    assert db.listar_candidatos() == []
    assert [x["id"] for x in vision.listar("pendiente")] == [d["lectura_id"]]


def test_foto_ilegible_se_rechaza_sin_llamar_a_la_ia(cliente, ocr):
    ocr["confianza"] = 0.30
    recibidos = []
    llm.usar_modelos([modelo_que_responde(ia_formulario(), recibidos)])
    r = subir_foto(cliente)
    assert r.status_code == 422 and "de frente" in r.json()["mensaje"]
    assert recibidos == []
    assert os.listdir(settings.imagenes_dir) == []  # no se guardó la foto
    assert db.listar_lecturas()[0]["estado"] == "ilegible"


def test_si_la_ia_no_responde_la_foto_queda_en_cola(cliente, ocr, monkeypatch):
    monkeypatch.setattr(settings, "llm_reintentos", 1)
    llm.usar_modelos([modelo_que_falla()])
    d = subir_foto(cliente).json()
    assert d["estado"] == "requiere_revision" and d["lectura"]["ia_pendiente"]
    assert "reintentará" in d["lectura"]["motivos"][0]
    # La IA vuelve: la cola de reintento la procesa sola.
    llm.usar_modelos([modelo_que_responde(ia_formulario(puntaje=81))])
    assert vision.reintentar_pendientes_ia() == {"reintentadas": 1, "fallidas": 0}
    lect = db.obtener_lectura(d["lectura_id"])
    assert lect["estado"] == "guardada" and not lect["ia_pendiente"]


def test_confirmar_con_correcciones_recalcula_el_puntaje(cliente, ocr):
    ocr["confianza"] = 0.66
    llm.usar_modelos([modelo_que_responde(ia_formulario(puntaje=50))])
    lectura_id = subir_foto(cliente).json()["lectura_id"]
    llm.usar_modelos([modelo_que_responde(json_ia(puntaje=88))])
    campos = {"profesion": "Ingeniero de sistemas", "experiencia_anios": 6, "habilidades": "Python, SQL, Django",
              "educacion": "Ingeniería de Sistemas", "certificaciones": "AWS Cloud Practitioner"}
    r = cliente.post(f"/api/vision/{lectura_id}/confirmar", json={"campos": campos})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["corregido"] and d["candidato"]["puntaje"] == 88 and d["candidato"]["estado"] == "Preseleccionado"
    assert d["candidato"]["experiencia_anios"] == 6
    lect = db.obtener_lectura(lectura_id)
    assert lect["estado"] == "guardada" and lect["corregido"] and lect["fecha_revision"]
    assert cliente.post(f"/api/vision/{lectura_id}/confirmar", json={"campos": campos}).status_code == 409


def test_confirmar_sin_cambios_conserva_el_puntaje_de_la_ia(cliente, ocr):
    ocr["confianza"] = 0.66
    llm.usar_modelos([modelo_que_responde(ia_formulario(puntaje=64))])
    d = subir_foto(cliente).json()
    llm.usar_modelos([modelo_que_falla()])  # no debe llamarse
    r = cliente.post(f"/api/vision/{d['lectura_id']}/confirmar", json={"campos": d["lectura"]["campos"]})
    assert r.json()["candidato"]["puntaje"] == 64 and not r.json()["corregido"]


def test_confirmar_valida_los_campos(cliente, ocr):
    ocr["confianza"] = 0.66
    llm.usar_modelos([modelo_que_responde(ia_formulario())])
    lectura_id = subir_foto(cliente).json()["lectura_id"]
    malos = {"profesion": "", "experiencia_anios": 3, "habilidades": "Python"}
    assert "profesión" in cliente.post(f"/api/vision/{lectura_id}/confirmar", json={"campos": malos}).json()["mensaje"]
    malos = {"profesion": "Ing", "experiencia_anios": 99, "habilidades": "Python"}
    assert cliente.post(f"/api/vision/{lectura_id}/confirmar", json={"campos": malos}).status_code == 400


def test_descartar_borra_la_foto(cliente, ocr):
    ocr["confianza"] = 0.66
    llm.usar_modelos([modelo_que_responde(ia_formulario())])
    lectura_id = subir_foto(cliente).json()["lectura_id"]
    assert cliente.get(f"/api/vision/{lectura_id}/imagen").status_code == 200
    assert cliente.post(f"/api/vision/{lectura_id}/rechazar").json()["estado"] == "rechazada"
    assert os.listdir(settings.imagenes_dir) == []
    assert cliente.get(f"/api/vision/{lectura_id}/imagen").status_code == 404


@pytest.mark.parametrize("contenido, nombre, texto", [
    (b"\x00\x00\x00\x18ftypheic" + b"0" * 50, "foto.heic", "HEIC"),
    (b"esto no es una imagen", "foto.jpg", "no es una imagen"),
])
def test_imagenes_no_validas(cliente, ocr, contenido, nombre, texto):
    r = subir_foto(cliente, contenido=contenido, nombre_archivo=nombre)
    assert r.status_code == 400 and texto in r.json()["mensaje"]


def test_imagen_demasiado_grande(cliente, ocr, monkeypatch):
    monkeypatch.setattr(settings, "max_imagen_mb", 0)
    assert "límite" in subir_foto(cliente).json()["mensaje"]


def test_el_registro_de_vision_no_guarda_datos_personales(cliente, ocr):
    llm.usar_modelos([modelo_que_responde(ia_formulario())])
    subir_foto(cliente)
    ej = db.listar_ejecuciones(flujo="vision")[0]
    assert ej["estado"] == "ok" and "confianza" in ej["resultado"]
    assert "andres" not in json.dumps(ej).lower()


def test_sin_tesseract_el_mensaje_es_claro(cliente, monkeypatch):
    monkeypatch.setattr(settings, "tesseract_cmd", "")
    monkeypatch.setattr(lectura.shutil, "which", lambda _n: None)
    monkeypatch.setattr(lectura, "RUTAS_WINDOWS", ())
    r = subir_foto(cliente)
    assert r.status_code == 503 and "Tesseract" in r.json()["mensaje"]


# ───────────────────────── OCR real (se omite si no hay Tesseract) ─────────────────────────
requiere_tesseract = pytest.mark.skipif(not lectura.tesseract_disponible(), reason="Tesseract no está instalado")


@requiere_tesseract
def test_ocr_real_lee_una_ficha_generada():
    from PIL import Image
    import io

    lineas = ["HOJA DE VIDA", "Profesion: Ingeniero de sistemas", "Experiencia: 4 anios en desarrollo web",
              "Habilidades: Python, SQL, JavaScript", "Educacion: Universidad Tecnologica de Pereira"]
    r = lectura.leer(Image.open(io.BytesIO(imagen_con_texto(lineas))))
    assert r.confianza > 0.7 and r.palabras >= 15
    for palabra in ("Ingeniero", "Python", "SQL", "Pereira"):
        assert palabra in r.texto


@requiere_tesseract
def test_ocr_real_marca_baja_confianza_en_una_imagen_vacia():
    from PIL import Image
    import io

    r = lectura.leer(Image.open(io.BytesIO(imagen_vacia())))
    assert r.palabras < vision.MIN_PALABRAS
