"""Base de datos del sistema: candidatos, ejecuciones y lecturas_vision.

SQLite en desarrollo (se crea sola en data/) y PostgreSQL (Neon o Supabase) al desplegar:
solo cambia DATABASE_URL. Las tablas de usuarios y auditoría viven en app/seguridad/almacen.py
y usan la misma base.
"""
import json
import logging
import os
import threading
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, Float, Integer, MetaData, String, Table, Text, create_engine, delete, insert, select, update,
)

from .config import settings
from .seguridad.almacen import normalizar_url

log = logging.getLogger("seleccion")

meta = MetaData()

candidatos = Table(
    "candidatos", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("candidato_id", String(20), unique=True, index=True),
    Column("fecha", String(32), nullable=False),
    Column("nombre", String(150), nullable=False),
    Column("correo", String(150), nullable=False),
    Column("cargo", String(120), nullable=False),
    Column("profesion", String(200), default="No indica"),
    Column("experiencia_anios", Integer, default=0),
    Column("habilidades", Text, default=""),
    Column("educacion", Text, default="No indica"),
    Column("certificaciones", Text, default="No indica"),
    Column("puntaje", Integer, default=0),
    Column("justificacion", Text, default=""),
    Column("resumen", Text, default=""),
    Column("zona", String(10), default="bajo"),
    Column("estado", String(30), default="Descartado"),
    Column("origen", String(10), default="pdf"),  # pdf | foto
    Column("archivo", String(255), default=""),
    Column("lectura_id", Integer, nullable=True),
    Column("autorizacion", Boolean, default=True),
    Column("modelo", String(60), default=""),
    Column("aviso_telegram", Boolean, default=False),
)

ejecuciones = Table(
    "ejecuciones", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("fecha", String(32), nullable=False, index=True),
    Column("flujo", String(40), nullable=False, index=True),
    Column("estado", String(10), nullable=False),  # ok | error
    Column("duracion_ms", Integer, default=0),
    Column("usuario", String(60), default=""),
    Column("entrada", Text, default="{}"),
    Column("resultado", Text, default="{}"),
    Column("error", Text, default=""),
)

lecturas_vision = Table(
    "lecturas_vision", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("fecha", String(32), nullable=False),
    Column("archivo_original", String(255), default=""),
    Column("archivo_guardado", String(255), default=""),
    Column("sha256", String(64), default=""),
    Column("cargo", String(120), default=""),
    Column("nombre", String(150), default=""),
    Column("correo", String(150), default=""),
    Column("subido_por", String(60), default="sin-sesion"),
    Column("revisado_por", String(60), nullable=True),
    Column("fecha_revision", String(32), nullable=True),
    Column("estado", String(20), default="pendiente"),  # pendiente | guardada | rechazada | ilegible
    Column("confianza_ocr", Float, default=0.0),
    Column("confianza", Text, default="{}"),
    Column("campos", Text, default="{}"),
    Column("motivos", Text, default="[]"),
    Column("texto_enmascarado", Text, default=""),
    Column("corregido", Boolean, default=False),
    Column("ia_pendiente", Boolean, default=False),  # la IA no respondió: la lectura queda en cola de reintento
    Column("candidato_id", String(20), nullable=True),
    Column("modelo", String(60), default=""),
)

_JSON = {"confianza", "campos", "motivos", "entrada", "resultado"}
_engine = None
_candado = threading.Lock()


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def configurar(url: str | None = None):
    """Crea el motor y las tablas. Se puede llamar de nuevo con otra URL (las pruebas usan una base temporal)."""
    global _engine
    url = normalizar_url(url or settings.database_url)
    opciones: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        ruta = url.split("///", 1)[-1]
        if ruta and ruta != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
        opciones["connect_args"] = {"check_same_thread": False, "timeout": 15}
    with _candado:
        if _engine is not None:
            _engine.dispose()
        _engine = create_engine(url, **opciones)
        meta.create_all(_engine)
    return _engine


def engine():
    if _engine is None:
        configurar()
    return _engine


def _fila(f) -> dict:
    datos = dict(f._mapping)
    for clave in _JSON & datos.keys():
        try:
            datos[clave] = json.loads(datos[clave] or "null")
        except (TypeError, ValueError):
            pass
    return datos


def _a_texto(valores: dict) -> dict:
    return {k: (json.dumps(v, ensure_ascii=False, default=str) if k in _JSON and not isinstance(v, str) else v)
            for k, v in valores.items()}


# ───────────────────────── Candidatos ─────────────────────────
def insertar_candidato(valores: dict) -> dict:
    with engine().begin() as c:
        nuevo_id = c.execute(insert(candidatos).values(**_a_texto(valores))).inserted_primary_key[0]
        c.execute(update(candidatos).where(candidatos.c.id == nuevo_id).values(candidato_id=f"CAN-{nuevo_id:04d}"))
        return _fila(c.execute(select(candidatos).where(candidatos.c.id == nuevo_id)).one())


def actualizar_candidato(candidato_id: str, **valores) -> None:
    with engine().begin() as c:
        c.execute(update(candidatos).where(candidatos.c.candidato_id == candidato_id).values(**_a_texto(valores)))


def listar_candidatos() -> list[dict]:
    with engine().connect() as c:
        return [_fila(f) for f in c.execute(select(candidatos).order_by(candidatos.c.id)).all()]


def buscar_candidato(candidato_id: str) -> dict | None:
    with engine().connect() as c:
        f = c.execute(select(candidatos).where(candidatos.c.candidato_id == candidato_id)).first()
    return _fila(f) if f else None


def borrar_candidato(candidato_id: str) -> bool:
    with engine().begin() as c:
        return c.execute(delete(candidatos).where(candidatos.c.candidato_id == candidato_id)).rowcount > 0


# ───────────────────────── Ejecuciones ─────────────────────────
def insertar_ejecucion(valores: dict) -> int:
    with engine().begin() as c:
        return c.execute(insert(ejecuciones).values(**_a_texto(valores))).inserted_primary_key[0]


def listar_ejecuciones(limite: int = 200, flujo: str | None = None) -> list[dict]:
    consulta = select(ejecuciones).order_by(ejecuciones.c.id.desc()).limit(limite)
    if flujo:
        consulta = consulta.where(ejecuciones.c.flujo == flujo)
    with engine().connect() as c:
        return [_fila(f) for f in c.execute(consulta).all()]


# ───────────────────────── Lecturas del módulo de visión ─────────────────────────
def insertar_lectura(valores: dict) -> dict:
    with engine().begin() as c:
        nuevo_id = c.execute(insert(lecturas_vision).values(**_a_texto(valores))).inserted_primary_key[0]
        return _fila(c.execute(select(lecturas_vision).where(lecturas_vision.c.id == nuevo_id)).one())


def actualizar_lectura(lectura_id: int, **valores) -> None:
    with engine().begin() as c:
        c.execute(update(lecturas_vision).where(lecturas_vision.c.id == lectura_id).values(**_a_texto(valores)))


def obtener_lectura(lectura_id: int) -> dict | None:
    with engine().connect() as c:
        f = c.execute(select(lecturas_vision).where(lecturas_vision.c.id == lectura_id)).first()
    return _fila(f) if f else None


def listar_lecturas(estado: str | None = None, limite: int = 200) -> list[dict]:
    consulta = select(lecturas_vision).order_by(lecturas_vision.c.id.desc()).limit(limite)
    if estado:
        consulta = consulta.where(lecturas_vision.c.estado == estado)
    with engine().connect() as c:
        return [_fila(f) for f in c.execute(consulta).all()]
