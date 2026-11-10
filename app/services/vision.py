"""Módulo de visión: lectura de fotos de hojas de vida y fichas de candidato (caso «lectura de formularios físicos»).

Disparador: POST /api/vision (foto desde la web o la cámara del celular).

  foto → validar → guardar con nombre aleatorio (fuera de la carpeta pública) → OCR local (Tesseract)
       → ¿ilegible? se rechaza y se pide repetirla (no se llama a la IA)
       → enmascarar datos personales → IA estructura los campos con su confianza (LangChain, plan B)
       → confianza final por campo = mínimo(IA, presencia real en el texto, calidad del OCR)
       → ¿confiable?  sí: registrar_candidato() → zona, estado, Telegram (mismo proceso que el PDF)
                      no: queda «pendiente» para revisión humana (confirmar o descartar)

Si la IA no responde (cuota agotada), la foto no se pierde: queda pendiente con `ia_pendiente`
(cola de reintento). La tarea programada la reintenta y una persona también puede completarla a mano.
"""
import difflib
import hashlib
import io
import logging
import os
import re
import secrets
import unicodedata

from PIL import Image, UnidentifiedImageError

from .. import db
from ..config import settings
from ..errores import ArchivoIlegible, ConflictoDeEstado, EntradaInvalida, NoEncontrado, ServicioIANoDisponible
from ..seguridad.contexto import nombre_usuario_actual
from . import lectura, llm
from .carga import registrar_candidato, validar_datos
from .llm import CAMPOS_VISION
from .privacidad import enmascarar_texto
from .registro import ejecucion

log = logging.getLogger("seleccion")

Image.MAX_IMAGE_PIXELS = 60_000_000  # protege contra imágenes gigantes (descompresión maliciosa)
FORMATOS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
MIN_PALABRAS = 12
OBLIGATORIOS = ("profesion", "habilidades")
NOMBRES_CAMPOS = {
    "profesion": "profesión", "experiencia_anios": "años de experiencia", "habilidades": "habilidades",
    "educacion": "educación", "certificaciones": "certificaciones",
}
CONSEJO_FOTO = (
    "Toma la foto de frente, con luz pareja, sin sombras ni reflejos, con el documento completo en el encuadre "
    "y la letra nítida."
)
_VACIO = {"", "no indica", "no aplica", "n/a", "ninguna", "ninguno"}
_COMUNES = {"de", "del", "la", "las", "los", "el", "en", "y", "con", "para", "por", "una", "uno", "sus", "the", "and"}


# ───────────────────────── Utilidades ─────────────────────────
def _normal(t: str) -> str:
    t = unicodedata.normalize("NFD", str(t).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _palabras(t: str) -> list[str]:
    return [p for p in re.findall(r"[a-z0-9+#.]+", _normal(t)) if len(p) >= 3 and p not in _COMUNES]


def vacio(valor) -> bool:
    return str(valor or "").strip().lower() in _VACIO


def presencia(campo: str, valor, texto: str) -> float:
    """Qué parte del valor aparece de verdad en el texto leído (0 a 1). Detecta datos inventados por la IA."""
    if campo == "experiencia_anios":
        try:
            anios = int(valor)
        except (TypeError, ValueError):
            return 0.3
        if anios == 0:
            return 0.7
        # Un número igual en el texto confirma; si no aparece puede ser una suma de periodos (plausible, no seguro).
        return 1.0 if re.search(rf"\b{anios}\b", texto) else 0.65
    if vacio(valor):
        return 1.0  # «No indica» no es un dato inventado; la falta de un campo obligatorio se revisa aparte
    fichas = _palabras(valor)
    if not fichas:
        return 0.5
    disponibles = set(_palabras(texto))
    puntos = 0.0
    for f in fichas:
        if f in disponibles:
            puntos += 1
        elif difflib.get_close_matches(f, disponibles, n=1, cutoff=0.8):
            puntos += 0.8  # error típico de OCR (letra cambiada)
    return round(puntos / len(fichas), 3)


def calcular_confianza(campos: dict, confianza_ia: dict, texto: str, confianza_ocr: float) -> dict[str, float]:
    return {
        c: round(min(float(confianza_ia.get(c, 0.5)), presencia(c, campos.get(c), texto), confianza_ocr), 3)
        for c in CAMPOS_VISION
    }


def motivos_revision(campos: dict, confianza: dict, confianza_ocr: float) -> list[str]:
    motivos = []
    if confianza_ocr < settings.umbral_ocr:
        motivos.append(f"La foto se leyó con calidad media ({round(confianza_ocr * 100)} %).")
    dudosos = [f"{NOMBRES_CAMPOS[c]} ({round(v * 100)} %)" for c, v in confianza.items() if v < settings.umbral_campo]
    if dudosos:
        motivos.append("Campos dudosos: " + ", ".join(dudosos) + ".")
    for c in OBLIGATORIOS:
        if vacio(campos.get(c)):
            motivos.append(f"No se encontró {NOMBRES_CAMPOS[c]}.")
    return motivos


def _abrir(contenido: bytes, nombre_archivo: str) -> tuple[Image.Image, str]:
    if not contenido:
        raise EntradaInvalida(f"La imagen «{nombre_archivo}» está vacía.")
    if len(contenido) > settings.max_imagen_mb * 1024 * 1024:
        raise EntradaInvalida(f"La imagen «{nombre_archivo}» supera el límite de {settings.max_imagen_mb} MB.")
    if contenido[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        raise EntradaInvalida(
            "Las fotos HEIC del iPhone no se pueden leer. En Ajustes > Cámara > Formatos elige «Más compatible» "
            "(JPG) o comparte la foto como JPG."
        )
    try:
        imagen = Image.open(io.BytesIO(contenido))
        imagen.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise EntradaInvalida(f"«{nombre_archivo}» no es una imagen JPG o PNG válida.") from e
    if imagen.format not in FORMATOS:
        raise EntradaInvalida(f"Formato {imagen.format} no admitido. Usa JPG, PNG o WebP.")
    return imagen, FORMATOS[imagen.format]


def _ruta(nombre_guardado: str) -> str:
    base = os.path.abspath(settings.imagenes_dir)
    ruta = os.path.abspath(os.path.join(base, nombre_guardado))
    if not ruta.startswith(base + os.sep):
        raise NoEncontrado("Imagen no encontrada.")
    return ruta


def _borrar_foto(nombre_guardado: str) -> None:
    if not nombre_guardado:
        return
    try:
        os.remove(_ruta(nombre_guardado))
    except FileNotFoundError:
        pass
    except OSError as e:
        log.error("No se pudo borrar la foto %s: %s", nombre_guardado, e)


def _usuario() -> str:
    u = nombre_usuario_actual()
    return "sin-sesion" if u == "anonimo" else u


def _respuesta(lect: dict, candidato: dict | None = None) -> dict:
    return {
        "estado": "guardado" if lect["estado"] == "guardada" else "requiere_revision",
        "lectura_id": lect["id"],
        "candidato_id": lect.get("candidato_id"),
        "lectura": publica(lect),
        "candidato": candidato,
    }


def publica(lect: dict) -> dict:
    """Lo que se muestra de una lectura (sin rutas internas ni huella)."""
    return {
        "id": lect["id"], "fecha": lect["fecha"], "archivo_original": lect["archivo_original"],
        "cargo": lect["cargo"], "nombre": lect["nombre"], "estado": lect["estado"],
        "subido_por": lect.get("subido_por"), "revisado_por": lect.get("revisado_por"),
        "fecha_revision": lect.get("fecha_revision"), "confianza_ocr": lect.get("confianza_ocr"),
        "confianza": lect.get("confianza") or {}, "campos": lect.get("campos") or {},
        "motivos": lect.get("motivos") or [], "corregido": bool(lect.get("corregido")),
        "ia_pendiente": bool(lect.get("ia_pendiente")), "candidato_id": lect.get("candidato_id"),
        "modelo": lect.get("modelo") or "", "tiene_imagen": bool(lect.get("archivo_guardado")),
    }


def _interpretar(texto: str, cargo: str, confianza_ocr: float) -> dict:
    """Llama a la IA y arma campos, confianza y motivos. Lanza ServicioIANoDisponible si el plan B se agota."""
    resultado = llm.extraer_formulario(texto, cargo)
    campos = {c: getattr(resultado, c) for c in CAMPOS_VISION}
    campos.update(puntaje=resultado.puntaje, justificacion=resultado.justificacion, resumen=resultado.resumen)
    confianza = calcular_confianza(campos, resultado.confianza, texto, confianza_ocr)
    return {"campos": campos, "confianza": confianza, "motivos": motivos_revision(campos, confianza, confianza_ocr),
            "modelo": llm.ultimo_modelo()}


# ───────────────────────── Flujo principal ─────────────────────────
def procesar_imagen(contenido: bytes, nombre_archivo: str, nombre: str, correo: str, cargo: str, autorizacion) -> dict:
    entrada = {"archivo": nombre_archivo, "cargo": cargo, "bytes": len(contenido or b"")}
    with ejecucion("vision", entrada) as e:
        nombre, correo, cargo = validar_datos(nombre, correo, cargo, autorizacion)
        imagen, extension = _abrir(contenido, nombre_archivo)

        ocr = lectura.leer(imagen)  # OCRNoDisponible si falta Tesseract (antes de guardar nada)
        e["resultado"] = {"confianza_ocr": ocr.confianza, "palabras": ocr.palabras}
        if ocr.confianza < settings.umbral_ocr_minimo or ocr.palabras < MIN_PALABRAS:
            db.insertar_lectura({
                "fecha": db.ahora(), "archivo_original": nombre_archivo[:255], "sha256": hashlib.sha256(contenido).hexdigest(),
                "cargo": cargo, "nombre": nombre, "correo": correo, "subido_por": _usuario(), "estado": "ilegible",
                "confianza_ocr": ocr.confianza, "motivos": ["Foto ilegible: no se guardó ni se envió a la IA."],
            })
            raise ArchivoIlegible(
                f"No se pudo leer la foto «{nombre_archivo}» (calidad de lectura {round(ocr.confianza * 100)} %). "
                + CONSEJO_FOTO
            )

        guardado = secrets.token_hex(16) + extension
        os.makedirs(settings.imagenes_dir, exist_ok=True)
        with open(_ruta(guardado), "wb") as f:
            f.write(contenido)

        texto = enmascarar_texto(ocr.texto, nombres_conocidos=[nombre], correos_conocidos=[correo])
        base = {
            "fecha": db.ahora(), "archivo_original": nombre_archivo[:255], "archivo_guardado": guardado,
            "sha256": hashlib.sha256(contenido).hexdigest(), "cargo": cargo, "nombre": nombre, "correo": correo,
            "subido_por": _usuario(), "confianza_ocr": ocr.confianza, "texto_enmascarado": texto,
        }
        try:
            interpretado = _interpretar(texto, cargo, ocr.confianza)
        except ServicioIANoDisponible:
            # Plan B del módulo de visión: la foto queda en cola y una persona puede completarla a mano.
            lect = db.insertar_lectura({
                **base, "estado": "pendiente", "ia_pendiente": True,
                "campos": {c: "" for c in CAMPOS_VISION},
                "confianza": {c: 0.0 for c in CAMPOS_VISION},
                "motivos": ["La IA no respondió (cuota agotada o caída). La foto quedó guardada: el sistema la "
                            "reintentará solo, o puedes completar los campos a mano."],
            })
            e["resultado"].update(lectura_id=lect["id"], estado="pendiente", ia_pendiente=True)
            return _respuesta(lect)

        requiere = bool(interpretado["motivos"])
        lect = db.insertar_lectura({
            **base, "estado": "pendiente", "campos": interpretado["campos"], "confianza": interpretado["confianza"],
            "motivos": interpretado["motivos"], "modelo": interpretado["modelo"],
        })
        candidato = None
        if not requiere:
            candidato = _guardar_candidato(lect, interpretado["campos"], interpretado["modelo"])
            lect = db.obtener_lectura(lect["id"])
        e["resultado"].update(
            lectura_id=lect["id"], estado=lect["estado"], requiere_revision=requiere,
            confianza=interpretado["confianza"], modelo=interpretado["modelo"],
            candidato_id=lect.get("candidato_id"),
        )
        return _respuesta(lect, candidato)


def _guardar_candidato(lect: dict, campos: dict, modelo: str, corregido: bool = False) -> dict:
    fila = registrar_candidato(
        campos, lect["nombre"], lect["correo"], lect["cargo"], "foto",
        archivo=lect["archivo_original"], lectura_id=lect["id"], modelo=modelo,
    )
    cambios = {"estado": "guardada", "candidato_id": fila["candidato_id"], "campos": campos, "corregido": corregido,
               "ia_pendiente": False}
    if corregido or lect.get("ia_pendiente") or lect.get("motivos"):
        cambios.update(revisado_por=_usuario(), fecha_revision=db.ahora())
    db.actualizar_lectura(lect["id"], **cambios)
    return fila


# ───────────────────────── Revisión humana ─────────────────────────
def _pendiente(lectura_id: int) -> dict:
    lect = db.obtener_lectura(lectura_id)
    if not lect:
        raise NoEncontrado("La lectura no existe.")
    if lect["estado"] != "pendiente":
        raise ConflictoDeEstado(f"La lectura {lectura_id} ya está {lect['estado']}.")
    return lect


def _limpiar_campos(campos: dict) -> dict:
    limpio = {}
    for c in CAMPOS_VISION:
        valor = campos.get(c, "")
        if c == "experiencia_anios":
            try:
                valor = int(float(valor or 0))
            except (TypeError, ValueError):
                raise EntradaInvalida("Los años de experiencia deben ser un número.") from None
            if not 0 <= valor <= 60:
                raise EntradaInvalida("Los años de experiencia deben estar entre 0 y 60.")
        else:
            valor = re.sub(r"\s+", " ", str(valor or "")).strip()[:1000] or "No indica"
        limpio[c] = valor
    for c in OBLIGATORIOS:
        if vacio(limpio[c]):
            raise EntradaInvalida(f"Completa el campo {NOMBRES_CAMPOS[c]} antes de guardar.")
    return limpio


def confirmar(lectura_id: int, campos: dict) -> dict:
    with ejecucion("vision_confirmar", {"lectura_id": lectura_id}) as e:
        lect = _pendiente(lectura_id)
        nuevos = _limpiar_campos(campos or {})
        anteriores = lect.get("campos") or {}
        corregido = any(str(nuevos[c]) != str(anteriores.get(c, "")) for c in CAMPOS_VISION)
        datos = {**nuevos, "puntaje": anteriores.get("puntaje", 0), "justificacion": anteriores.get("justificacion", ""),
                 "resumen": anteriores.get("resumen", "")}
        modelo = lect.get("modelo") or ""
        if corregido or lect.get("ia_pendiente"):
            # Los datos cambiaron: la IA vuelve a calcular el puntaje con lo que confirmó la persona.
            texto = (f"Profesión: {nuevos['profesion']}\nExperiencia: {nuevos['experiencia_anios']} años\n"
                     f"Habilidades: {nuevos['habilidades']}\nEducación: {nuevos['educacion']}\n"
                     f"Certificaciones: {nuevos['certificaciones']}")
            try:
                calculo = llm.extraer_datos(texto, lect["cargo"])
                datos.update(puntaje=calculo.puntaje, justificacion=calculo.justificacion, resumen=calculo.resumen)
                modelo = llm.ultimo_modelo()
            except ServicioIANoDisponible:
                if lect.get("ia_pendiente"):
                    raise ServicioIANoDisponible(
                        "Los datos están bien, pero la IA no responde para calcular el puntaje. La lectura sigue "
                        "pendiente: vuelve a confirmarla en unos minutos."
                    ) from None
                datos["justificacion"] = (datos["justificacion"] + " (Puntaje de la lectura original: la IA no "
                                          "respondió al recalcular con las correcciones.)").strip()
        fila = _guardar_candidato(lect, datos, modelo, corregido=corregido)
        e["resultado"] = {"lectura_id": lectura_id, "candidato_id": fila["candidato_id"], "corregido": corregido,
                          "puntaje": fila["puntaje"], "estado": fila["estado"]}
        return {"estado": "guardado", "lectura_id": lectura_id, "candidato_id": fila["candidato_id"],
                "corregido": corregido, "candidato": fila}


def rechazar(lectura_id: int) -> dict:
    with ejecucion("vision_rechazar", {"lectura_id": lectura_id}) as e:
        lect = _pendiente(lectura_id)
        _borrar_foto(lect.get("archivo_guardado"))
        db.actualizar_lectura(lectura_id, estado="rechazada", archivo_guardado="", revisado_por=_usuario(),
                              fecha_revision=db.ahora(), texto_enmascarado="")
        e["resultado"] = {"lectura_id": lectura_id, "estado": "rechazada"}
        return {"estado": "rechazada", "lectura_id": lectura_id}


def reintentar_pendientes_ia(limite: int = 10) -> dict:
    """Cola de reintento: vuelve a pedir a la IA las lecturas que quedaron sin interpretar."""
    hechas = fallidas = 0
    for lect in [x for x in db.listar_lecturas("pendiente", limite=200) if x.get("ia_pendiente")][:limite]:
        try:
            r = _interpretar(lect.get("texto_enmascarado") or "", lect["cargo"], lect.get("confianza_ocr") or 0)
        except ServicioIANoDisponible:
            fallidas += 1
            break  # si la IA sigue caída, no tiene sentido insistir con las demás
        db.actualizar_lectura(lect["id"], campos=r["campos"], confianza=r["confianza"], modelo=r["modelo"],
                              motivos=r["motivos"], ia_pendiente=False)
        lect = db.obtener_lectura(lect["id"])
        if not r["motivos"]:
            _guardar_candidato(lect, r["campos"], r["modelo"])
        hechas += 1
    return {"reintentadas": hechas, "fallidas": fallidas}


# ───────────────────────── Consultas ─────────────────────────
def obtener(lectura_id: int) -> dict:
    lect = db.obtener_lectura(lectura_id)
    if not lect:
        raise NoEncontrado("La lectura no existe.")
    return publica(lect)


def listar(estado: str | None = None) -> list[dict]:
    return [publica(x) for x in db.listar_lecturas(estado or None)]


def ruta_imagen(lectura_id: int) -> tuple[str, str]:
    lect = db.obtener_lectura(lectura_id)
    if not lect or not lect.get("archivo_guardado"):
        raise NoEncontrado("La foto no existe o fue borrada.")
    ruta = _ruta(lect["archivo_guardado"])
    if not os.path.exists(ruta):
        raise NoEncontrado("La foto ya no está en el servidor (el disco del plan gratuito se reinicia).")
    tipo = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(os.path.splitext(ruta)[1], "image/jpeg")
    return ruta, tipo
