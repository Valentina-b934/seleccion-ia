"""El evaluador de fotos calcula bien los aciertos (con la IA simulada)."""
import csv
import os
import shutil

import pytest

from app.services import lectura, llm

from .conftest import json_ia, modelo_que_responde

SIMULADAS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "evaluacion", "fotos_simuladas")
pytestmark = pytest.mark.skipif(not lectura.tesseract_disponible(), reason="Tesseract no está instalado")


def test_compara_campos_con_tolerancia():
    from scripts import evaluar

    assert evaluar.acierto("profesion", "Ingeniero de sistemas", "Ingeniero de Sistemas")
    assert evaluar.acierto("experiencia_anios", "5", 5) and not evaluar.acierto("experiencia_anios", "5", 4)
    assert evaluar.acierto("habilidades", "Python, SQL, Excel, Power BI", "python, sql, excel, PowerBI")
    assert not evaluar.acierto("habilidades", "Python, SQL, Excel, Power BI", "Python")
    assert evaluar.acierto("certificaciones", "No indica", "No indica")
    assert not evaluar.acierto("certificaciones", "No indica", "CCNA")


def test_evalua_una_carpeta_y_escribe_el_informe(tmp_path):
    from scripts import evaluar

    with open(os.path.join(SIMULADAS, "etiquetas.csv"), encoding="utf-8") as f:
        primera = next(csv.DictReader(f))
    shutil.copy(os.path.join(SIMULADAS, primera["archivo"]), tmp_path)
    with open(tmp_path / "etiquetas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(primera))
        w.writeheader()
        w.writerow(primera)
    respuesta = json_ia(profesion=primera["profesion"], experiencia_anios=int(primera["experiencia_anios"]),
                        habilidades=primera["habilidades"], educacion=primera["educacion"],
                        certificaciones=primera["certificaciones"], confianza={})
    llm.usar_modelos([modelo_que_responde(respuesta)])
    assert evaluar.main([str(tmp_path)]) == 0
    informe = (tmp_path / "resultados_evaluacion.md").read_text(encoding="utf-8")
    assert "| **Todos los campos** | 5 de 5 | **100.0 %** |" in informe
    assert (tmp_path / "resultados_evaluacion.csv").exists()
