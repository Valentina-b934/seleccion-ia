"""Flujo «Selección de personal con IA» de n8n: carga de una hoja de vida en PDF.

Disparador: POST /api/candidatos (antes: Webhook de n8n).
Pasos:  validar → leer el PDF → enmascarar datos personales → IA extrae y puntúa (con reintentos y plan B)
        → zona de decisión (Switch) → guardar con su estado → aviso de Telegram → registro de la ejecución.

`registrar_candidato()` es el tramo final que comparten el PDF y el módulo de visión: así una foto
confiable (o una lectura confirmada por una persona) dispara exactamente el mismo proceso de negocio.
"""
import re

from .. import db
from ..errores import EntradaInvalida
from . import decision, llm, pdf, telegram
from .registro import ejecucion

_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def validar_datos(nombre: str, correo: str, cargo: str, autorizacion) -> tuple[str, str, str]:
    nombre, correo, cargo = (nombre or "").strip(), (correo or "").strip().lower(), (cargo or "").strip()
    if not _autorizado(autorizacion):
        raise EntradaInvalida(
            "Falta la autorización de tratamiento de datos (Ley 1581 de 2012). Marca la casilla para continuar."
        )
    if len(nombre) < 3:
        raise EntradaInvalida("Escribe el nombre del candidato.")
    if not _CORREO.match(correo):
        raise EntradaInvalida(f"El correo «{correo}» no es válido.")
    if len(cargo) < 3:
        raise EntradaInvalida("Elige el cargo al que aplica.")
    return nombre[:150], correo[:150], cargo[:120]


def _autorizado(valor) -> bool:
    return str(valor).strip().lower() in ("1", "true", "si", "sí", "on", "yes")


def registrar_candidato(datos: dict, nombre: str, correo: str, cargo: str, origen: str,
                        archivo: str = "", lectura_id: int | None = None, modelo: str = "") -> dict:
    """Aplica la decisión, guarda el candidato y avisa por Telegram. Devuelve la fila guardada."""
    d = decision.zona(datos.get("puntaje", 0))
    fila = db.insertar_candidato({
        "fecha": db.ahora(),
        "nombre": nombre,
        "correo": correo,
        "cargo": cargo,
        "profesion": datos.get("profesion") or "No indica",
        "experiencia_anios": int(datos.get("experiencia_anios") or 0),
        "habilidades": datos.get("habilidades") or "No indica",
        "educacion": datos.get("educacion") or "No indica",
        "certificaciones": datos.get("certificaciones") or "No indica",
        "puntaje": int(datos.get("puntaje") or 0),
        "justificacion": datos.get("justificacion") or "",
        "resumen": datos.get("resumen") or "",
        "zona": d.zona,
        "estado": d.estado,
        "origen": origen,
        "archivo": archivo[:255],
        "lectura_id": lectura_id,
        "autorizacion": True,
        "modelo": modelo,
    })
    enviado = telegram.avisar(telegram.mensaje_candidato(fila, d.accion))
    if enviado:
        db.actualizar_candidato(fila["candidato_id"], aviso_telegram=True)
        fila["aviso_telegram"] = True
    fila["accion"] = d.accion
    return fila


def procesar_pdf(contenido: bytes, nombre_archivo: str, nombre: str, correo: str, cargo: str, autorizacion) -> dict:
    entrada = {"archivo": nombre_archivo, "cargo": cargo, "bytes": len(contenido or b"")}
    with ejecucion("carga", entrada) as e:
        nombre, correo, cargo = validar_datos(nombre, correo, cargo, autorizacion)
        texto = pdf.extraer_texto(contenido, nombre_archivo)
        datos = llm.extraer_datos(texto, cargo)  # el texto se enmascara dentro de llm.extraer_datos
        fila = registrar_candidato(
            datos.model_dump(), nombre, correo, cargo, "pdf", archivo=nombre_archivo, modelo=llm.ultimo_modelo()
        )
        e["resultado"] = {
            "candidato_id": fila["candidato_id"], "puntaje": fila["puntaje"], "zona": fila["zona"],
            "estado": fila["estado"], "aviso_telegram": fila["aviso_telegram"], "modelo": fila["modelo"],
        }
        return fila
