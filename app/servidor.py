"""Punto de entrada con seguridad (semana 4).

    uvicorn app.servidor:app --reload

Toma la aplicación de app/main.py tal como está y la envuelve con inicio de sesión,
permisos por rol y auditoría. app/main.py no se modifica.
"""
import logging

from .config import settings
from .main import app as aplicacion
from .seguridad.almacen import AlmacenSQL
from .seguridad.envoltura import Protector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _olvidar_chat(usuario: str) -> None:
    from .services import llm

    llm.olvidar_memoria(usuario)


app = Protector(
    aplicacion,
    almacen=AlmacenSQL(settings.database_url),
    secreto=settings.sesion_secreto,
    horas=settings.sesion_horas,
    cookie_segura=settings.cookie_segura,
    usuarios_iniciales=settings.usuarios_iniciales(),
    al_olvidar_chat=_olvidar_chat,
)
