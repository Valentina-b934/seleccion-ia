"""Errores con un mensaje pensado para la persona que usa el panel.

Cada servicio lanza uno de estos errores y app/main.py lo convierte en una respuesta JSON
{"detail": mensaje, "mensaje": mensaje} con el código HTTP indicado. Así el panel siempre
muestra un texto claro y nunca un error técnico.
"""


class ErrorDeUsuario(Exception):
    codigo = 400
    mensaje_por_defecto = "No se pudo completar la acción."

    def __init__(self, mensaje: str | None = None):
        self.mensaje = mensaje or self.mensaje_por_defecto
        super().__init__(self.mensaje)


class EntradaInvalida(ErrorDeUsuario):
    codigo = 400
    mensaje_por_defecto = "Los datos enviados no son válidos."


class NoEncontrado(ErrorDeUsuario):
    codigo = 404
    mensaje_por_defecto = "No se encontró el registro."


class ConflictoDeEstado(ErrorDeUsuario):
    codigo = 409
    mensaje_por_defecto = "El registro ya fue procesado."


class ArchivoIlegible(ErrorDeUsuario):
    codigo = 422
    mensaje_por_defecto = "No se pudo leer el archivo."


class ServicioIANoDisponible(ErrorDeUsuario):
    """Plan B agotado: ningún modelo respondió tras los reintentos."""

    codigo = 503
    mensaje_por_defecto = (
        "El servicio de IA no está disponible en este momento (cuota gratuita agotada o caída del proveedor). "
        "No se perdió nada: intenta de nuevo en unos minutos."
    )


class OCRNoDisponible(ErrorDeUsuario):
    codigo = 503
    mensaje_por_defecto = (
        "El lector de imágenes (Tesseract) no está instalado en el servidor. "
        "Instálalo o configura TESSERACT_CMD en el archivo .env."
    )
