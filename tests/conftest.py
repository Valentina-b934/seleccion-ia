"""Utilidades compartidas por las pruebas.

Ninguna prueba usa internet ni claves: la IA se simula con RunnableLambda de LangChain,
la base de datos es un SQLite temporal y Telegram queda sin configurar (salvo donde se simula).
"""
import io
import json

import pytest
from langchain_core.runnables import RunnableLambda
from PIL import Image, ImageDraw, ImageFont

from app import db
from app.config import settings
from app.services import llm, telegram


# ───────────────────────── Aislamiento de cada prueba ─────────────────────────
@pytest.fixture(autouse=True)
def entorno_aislado(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'prueba.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    monkeypatch.setattr(settings, "imagenes_dir", str(tmp_path / "imagenes"))
    monkeypatch.setattr(settings, "llm_espera", 0.0)
    monkeypatch.setattr(settings, "telegram_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    monkeypatch.setattr(settings, "tareas_activas", False)
    db.configurar(url)
    llm.olvidar_memoria()
    yield
    llm.usar_modelos(None)
    telegram._cliente_prueba = None


# ───────────────────────── IA simulada ─────────────────────────
def json_ia(**cambios) -> str:
    datos = {
        "profesion": "Ingeniero de sistemas",
        "experiencia_anios": 4,
        "habilidades": "Python, SQL, JavaScript",
        "puntaje": 72,
        "justificacion": "Cumple con la experiencia y las habilidades principales.",
        "resumen": "Desarrollador con experiencia en aplicaciones web.",
        "educacion": "Ingeniería de Sistemas",
        "certificaciones": "No indica",
    }
    datos.update(cambios)
    return json.dumps(datos, ensure_ascii=False)


def modelo_que_responde(texto: str, recibidos: list | None = None):
    def _modelo(prompt_value):
        if recibidos is not None:
            recibidos.append(prompt_value.to_string())
        return texto

    return RunnableLambda(_modelo)


def modelo_que_falla(error: Exception | None = None):
    def _modelo(_prompt_value):
        raise error or RuntimeError("429 cuota agotada")

    return RunnableLambda(_modelo)


class ModeloIntermitente:
    """Falla las primeras `fallos` llamadas y luego responde `texto`."""

    def __init__(self, fallos: int, texto: str):
        self.fallos, self.texto, self.llamadas = fallos, texto, 0
        self.modelo = RunnableLambda(self._llamar)

    def _llamar(self, _prompt_value):
        self.llamadas += 1
        if self.llamadas <= self.fallos:
            raise TimeoutError("el proveedor no respondió")
        return self.texto


# ───────────────────────── Archivos de prueba ─────────────────────────
def pdf_con_texto(lineas: list[str]) -> bytes:
    """Arma un PDF mínimo válido con texto seleccionable (sin librerías externas)."""
    def _esc(t: str) -> str:
        return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    flujo = "BT /F1 11 Tf 50 780 Td 14 TL " + " ".join(f"({_esc(l)}) '" for l in lineas) + " ET"
    flujo_b = flujo.encode("latin-1", "replace")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(flujo_b)).encode() + b" >>\nstream\n" + flujo_b + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for i, obj in enumerate(objetos, 1):
        posiciones.append(len(salida))
        salida += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    for p in posiciones:
        salida += f"{p:010d} 00000 n \n".encode()
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(salida)


HOJA_PDF = [
    "Laura Marcela Perez Gomez",
    "Ingeniera de sistemas",
    "Correo: laura.perez@gmail.com  Celular: 315 678 9012",
    "Perfil: desarrolladora con 4 anios de experiencia en Python y SQL.",
    "Experiencia: Analista de datos en Acme S.A.S. (2021 a 2025).",
    "Educacion: Ingenieria de Sistemas, UIS (2020).",
    "Habilidades: Python, SQL, Power BI, trabajo en equipo.",
]


def fuente(tamano: int):
    try:
        return ImageFont.load_default(size=tamano)
    except TypeError:  # Pillow antiguo
        return ImageFont.load_default()


def imagen_con_texto(lineas: list[str], formato: str = "JPEG", ancho: int = 1400) -> bytes:
    alto = 120 + 56 * len(lineas)
    img = Image.new("RGB", (ancho, alto), "white")
    d = ImageDraw.Draw(img)
    f = fuente(34)
    for i, linea in enumerate(lineas):
        d.text((60, 60 + i * 56), linea, fill="black", font=f)
    buf = io.BytesIO()
    img.save(buf, formato, quality=92)
    return buf.getvalue()


def imagen_vacia(formato: str = "PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (235, 235, 235)).save(buf, formato)
    return buf.getvalue()
