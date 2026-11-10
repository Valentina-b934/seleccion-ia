"""OCR local con Tesseract: prepara la foto y devuelve el texto con su confianza de lectura.

La imagen nunca sale del servidor. Pasos de preparación:
  1. Girar según los metadatos EXIF (fotos de celular).
  2. Pasar a escala de grises.
  3. Ajustar el tamaño: reducir fotos enormes (MAX_LADO_IMAGEN) y ampliar las pequeñas para que la letra se lea.
  4. Corregir sombras: se estima el fondo con un desenfoque fuerte y se divide la imagen por él.
  5. Estirar el contraste.
"""
import logging
import os
import shutil
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from ..config import settings
from ..errores import OCRNoDisponible

log = logging.getLogger("seleccion")

RUTAS_WINDOWS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)
LADO_MINIMO = 1400


@dataclass
class ResultadoOCR:
    texto: str
    confianza: float  # 0 a 1
    palabras: int
    idiomas: str = ""
    ancho: int = 0
    alto: int = 0
    lineas: list[str] = field(default_factory=list)


def _ruta_tesseract() -> str | None:
    if settings.tesseract_cmd and os.path.exists(settings.tesseract_cmd):
        return settings.tesseract_cmd
    encontrado = shutil.which("tesseract")
    if encontrado:
        return encontrado
    for ruta in RUTAS_WINDOWS:
        if os.path.exists(ruta):
            return ruta
    return None


def _pytesseract():
    import pytesseract

    ruta = _ruta_tesseract()
    if not ruta:
        raise OCRNoDisponible()
    pytesseract.pytesseract.tesseract_cmd = ruta
    return pytesseract


def tesseract_disponible() -> bool:
    try:
        _pytesseract().get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


def _idiomas(pt) -> str:
    pedidos = [i for i in settings.ocr_idiomas.split("+") if i]
    try:
        instalados = set(pt.get_languages(config=""))
    except Exception:  # noqa: BLE001
        return settings.ocr_idiomas
    usables = [i for i in pedidos if i in instalados]
    if len(usables) < len(pedidos):
        log.warning("Faltan idiomas de Tesseract: %s", set(pedidos) - instalados)
    return "+".join(usables) or "eng"


def preparar(imagen: Image.Image) -> Image.Image:
    imagen = ImageOps.exif_transpose(imagen)
    if imagen.mode in ("RGBA", "LA", "P"):
        fondo = Image.new("RGB", imagen.size, "white")
        fondo.paste(imagen.convert("RGBA"), mask=imagen.convert("RGBA").split()[-1])
        imagen = fondo
    gris = imagen.convert("L")

    lado = max(gris.size)
    if lado > settings.max_lado_imagen:
        escala = settings.max_lado_imagen / lado
    elif lado < LADO_MINIMO:
        escala = LADO_MINIMO / lado
    else:
        escala = 1.0
    if escala != 1.0:
        gris = gris.resize((max(1, round(gris.width * escala)), max(1, round(gris.height * escala))), Image.LANCZOS)

    # Corrección de sombras: fondo estimado con un desenfoque grande; imagen / fondo.
    radio = max(15, max(gris.size) // 40)
    fondo = gris.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(radio))
    a = np.asarray(gris, dtype=np.float32)
    b = np.maximum(np.asarray(fondo, dtype=np.float32), 1.0)
    normal = np.clip(a / b * 255.0, 0, 255).astype(np.uint8)
    return ImageOps.autocontrast(Image.fromarray(normal), cutoff=1)


def leer(imagen: Image.Image) -> ResultadoOCR:
    pt = _pytesseract()
    lista = preparar(imagen)
    idiomas = _idiomas(pt)
    datos = pt.image_to_data(lista, lang=idiomas, config="--oem 1 --psm 3", output_type=pt.Output.DICT)

    lineas: dict[tuple, list[str]] = {}
    suma = peso = 0.0
    palabras = 0
    for i, palabra in enumerate(datos["text"]):
        palabra = (palabra or "").strip()
        try:
            conf = float(datos["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if not palabra or conf < 0:
            continue
        clave = (datos["block_num"][i], datos["par_num"][i], datos["line_num"][i])
        lineas.setdefault(clave, []).append(palabra)
        largo = min(len(palabra), 12)
        suma += conf * largo
        peso += largo
        palabras += 1

    texto_lineas = [" ".join(p) for _, p in sorted(lineas.items())]
    confianza = round((suma / peso) / 100.0, 3) if peso else 0.0
    return ResultadoOCR(
        texto="\n".join(texto_lineas), confianza=confianza, palabras=palabras, idiomas=idiomas,
        ancho=lista.width, alto=lista.height, lineas=texto_lineas,
    )
