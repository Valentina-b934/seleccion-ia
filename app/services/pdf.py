"""Lectura del texto de un PDF (antes: nodo «Extract from File» de n8n)."""
import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ..config import settings
from ..errores import ArchivoIlegible, EntradaInvalida

MIN_CARACTERES = 80


def validar(contenido: bytes, nombre_archivo: str) -> None:
    if not contenido:
        raise EntradaInvalida(f"El archivo «{nombre_archivo}» está vacío.")
    if len(contenido) > settings.max_pdf_mb * 1024 * 1024:
        raise EntradaInvalida(f"El PDF «{nombre_archivo}» supera el límite de {settings.max_pdf_mb} MB.")
    if not contenido.startswith(b"%PDF"):
        raise EntradaInvalida(f"«{nombre_archivo}» no es un PDF válido.")


def extraer_texto(contenido: bytes, nombre_archivo: str = "archivo.pdf") -> str:
    validar(contenido, nombre_archivo)
    try:
        lector = PdfReader(io.BytesIO(contenido))
        if lector.is_encrypted:
            raise ArchivoIlegible(f"El PDF «{nombre_archivo}» tiene contraseña. Súbelo sin protección.")
        texto = "\n".join((pagina.extract_text() or "") for pagina in lector.pages[:15])
    except ArchivoIlegible:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as e:
        raise ArchivoIlegible(f"No se pudo leer el PDF «{nombre_archivo}»: el archivo parece dañado.") from e
    texto = "\n".join(linea.rstrip() for linea in texto.splitlines()).strip()
    if len(texto) < MIN_CARACTERES:
        raise ArchivoIlegible(
            f"El PDF «{nombre_archivo}» no tiene texto seleccionable (parece escaneado). "
            "Súbelo como foto (JPG o PNG) para leerlo con el módulo de visión."
        )
    return texto
