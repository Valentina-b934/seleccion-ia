"""Enmascarado de datos personales en el texto de las hojas de vida en PDF.

Antes de enviar el texto de un PDF a la IA externa (OpenRouter, Groq o Gemini) se reemplazan
correo, teléfono, número de documento, dirección, enlaces a perfiles, fecha de nacimiento y
el nombre (cuando el texto lo rotula o aparece en el encabezado) por marcas como [CORREO].
Los datos que sirven para evaluar (profesión, experiencia, estudios, habilidades) no se tocan.

Es un enmascarado por patrones: reduce mucho lo que sale del servidor, pero no garantiza el 100 %.
Las fotos usan su propio enmascarado en el módulo de visión.
"""
import difflib
import re
import unicodedata

_CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_ENLACE = re.compile(r"(?:https?://|www\.)\S+|\b(?:linkedin|github|facebook|instagram)\.com/\S+", re.I)
_FECHA_NAC = re.compile(
    r"(fecha\s+de\s+nacimiento|nacimiento|f\.\s*nac\.?)\s*[:\-]?\s*[\w/.\- ]{6,25}?(?=\n|$|\s{2,}|,|;)", re.I
)
_DOCUMENTO_ROTULADO = re.compile(
    r"\b(c\.?\s?c\.?|c[ée]dula(?:\s+de\s+ciudadan[ií]a)?|t\.?\s?i\.?|documento(?:\s+de\s+identidad)?|"
    r"pasaporte|nit|n[uú]mero\s+de\s+identificaci[oó]n)\s*(?:no\.?|n[°º]|#|:)?\s*[\d.\s\-]{5,18}\d",
    re.I,
)
_DOCUMENTO_SUELTO = re.compile(r"\b\d{1,3}(?:\.\d{3}){2,3}\b|\b\d{8,10}\b")
_TELEFONO = re.compile(
    r"(?:\+?57[\s\-]?)?\(?\b3\d{2}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b"  # celular colombiano
    r"|(?:\+?57[\s\-]?)?\(?\b60\d\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b"  # fijo con indicativo nuevo (60X)
    r"|(?:tel[ée]fono|tel\.?|cel(?:ular)?\.?|m[oó]vil)\s*[:\-]?\s*\+?[\d\s\-().]{7,18}\d",
    re.I,
)
_DIRECCION = re.compile(
    r"\b(?:calle|cl|cll|carrera|cra|kr|cr|avenida|av|diagonal|dg|transversal|tv|manzana|mz)\.?\s*"
    r"\d+\s*[a-z]?\s*(?:bis)?\s*(?:#|no\.?|n[°º])\s*\d+\s*[a-z]?(?:\s*-\s*\d+)?(?:[^\n]{0,40})?",
    re.I,
)
_DIRECCION_ROTULADA = re.compile(r"(direcci[oó]n|domicilio|residencia)\s*:\s*[^\n]+", re.I)
_NOMBRE_ROTULADO = re.compile(r"(nombres?(?:\s+completos?)?|apellidos?)\s*:\s*([^\n]+)", re.I)

_NO_ES_NOMBRE = re.compile(
    r"hoja de vida|curr[ií]cul|perfil|resumen|experiencia|educaci|formaci|datos|contacto|habilidades|objetivo"
    r"|ingenier|tecn[oó]log|t[eé]cnic|desarroll|analista|administra|contador|licenciad|profesional|auxiliar"
    r"|estudiante|abogad|dise[ñn]ad|developer|engineer|manager|gerente|asesor|sistemas",
    re.I,
)
_PALABRA_NOMBRE = re.compile(r"^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+$|^[A-ZÁÉÍÓÚÑ]{2,}$|^(de|del|la|los)$")


def _nombre_de_encabezado(texto: str) -> str | None:
    """En una hoja de vida el nombre suele ser la primera línea: de 2 a 5 palabras, sin números."""
    for linea in texto.splitlines()[:4]:
        linea = linea.strip()
        if not linea:
            continue
        palabras = linea.split()
        if 2 <= len(palabras) <= 5 and not _NO_ES_NOMBRE.search(linea) and all(_PALABRA_NOMBRE.match(p) for p in palabras):
            return linea
        return None
    return None


def _quitar_nombre(texto: str, nombre: str) -> str:
    nombre = nombre.strip(" .,:;")
    if len(nombre) < 4:
        return texto
    return re.sub(re.escape(nombre), "[NOMBRE]", texto, flags=re.I)


def _sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _quitar_parecidas(texto: str, palabras: list[str]) -> str:
    """Oculta palabras que el OCR leyó con algún error (por ejemplo 'Rodriquez' por 'Rodríguez')."""
    objetivos = {_sin_tildes(p) for p in palabras if len(p) >= 4}
    if not objetivos:
        return texto

    def _cambiar(m):
        palabra = m.group(0)
        base = _sin_tildes(palabra)
        if len(base) >= 4 and any(difflib.SequenceMatcher(None, base, o).ratio() >= 0.8 for o in objetivos):
            return "[NOMBRE]"
        return palabra

    return re.sub(r"[A-Za-zÁÉÍÓÚÑáéíóúñÜü]{4,}", _cambiar, texto)


def enmascarar_texto(texto: str, nombres_conocidos=(), correos_conocidos=()) -> str:
    """Oculta los datos personales. `nombres_conocidos` y `correos_conocidos` son los que escribió
    quien subió el archivo (en el módulo de visión): se ocultan aunque el OCR los haya leído con errores."""
    if not texto:
        return texto
    for correo in correos_conocidos:
        if correo:
            texto = re.sub(re.escape(correo), "[CORREO]", texto, flags=re.I)
    nombres = [m.group(2) for m in _NOMBRE_ROTULADO.finditer(texto)] + [n for n in nombres_conocidos if n]
    encabezado = _nombre_de_encabezado(texto)
    if encabezado:
        nombres.append(encabezado)

    texto = _CORREO.sub("[CORREO]", texto)
    texto = _ENLACE.sub("[ENLACE]", texto)
    texto = _FECHA_NAC.sub(lambda m: f"{m.group(1)}: [FECHA_NACIMIENTO]", texto)
    texto = _DOCUMENTO_ROTULADO.sub(lambda m: f"{m.group(1)} [DOCUMENTO]", texto)
    texto = _TELEFONO.sub("[TELEFONO]", texto)
    texto = _DIRECCION_ROTULADA.sub(lambda m: f"{m.group(1)}: [DIRECCION]", texto)
    texto = _DIRECCION.sub("[DIRECCION]", texto)
    texto = _DOCUMENTO_SUELTO.sub("[DOCUMENTO]", texto)
    for nombre in nombres:
        texto = _quitar_nombre(texto, nombre)
    # Por si el nombre completo no coincidía exacto: cada palabra del nombre (de 4 letras o más).
    for nombre in nombres:
        for palabra in nombre.split():
            if len(palabra) >= 4 and _PALABRA_NOMBRE.match(palabra):
                texto = re.sub(rf"\b{re.escape(palabra)}\b", "[NOMBRE]", texto)
    palabras_nombre = [p for n in nombres_conocidos if n for p in n.split()]
    texto = _quitar_parecidas(texto, palabras_nombre)
    return re.sub(r"(\[NOMBRE\]\s*){2,}", "[NOMBRE] ", texto)
