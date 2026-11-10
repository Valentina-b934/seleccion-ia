"""Tablas de usuarios y de auditoría.

Usa la misma base de datos del sistema (DATABASE_URL): SQLite en desarrollo y PostgreSQL
(Neon o Supabase) al desplegar. Las tablas se crean solas la primera vez.

AlmacenMemoria cumple el mismo contrato sin base de datos; lo usan las pruebas.
"""
import json
import logging
import os
import threading
from datetime import datetime, timezone

from .claves import cifrar_clave

log = logging.getLogger("seleccion")

COLUMNAS_LECTURA = ("subido_por", "revisado_por")


def ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalizar_url(url: str) -> str:
    """Neon y Supabase entregan 'postgres://...'; SQLAlchemy con psycopg 3 necesita 'postgresql+psycopg://'."""
    for prefijo in ("postgres://", "postgresql://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url[len(prefijo):]
    return url


class AlmacenMemoria:
    """Versión en memoria (para pruebas). Mismo contrato que AlmacenSQL."""

    def __init__(self):
        self.usuarios: dict[str, dict] = {}
        self.eventos: list[dict] = []
        self.lecturas_marcadas: list[tuple] = []

    def iniciar(self, usuarios_iniciales=()):
        for usuario, clave, rol in usuarios_iniciales:
            if usuario not in self.usuarios:
                self.crear_usuario(usuario, clave, rol)

    def buscar_usuario(self, usuario: str):
        return self.usuarios.get(usuario)

    def crear_usuario(self, usuario: str, clave: str, rol: str):
        if usuario in self.usuarios:
            raise ValueError("El usuario ya existe")
        self.usuarios[usuario] = {
            "usuario": usuario, "clave_hash": cifrar_clave(clave), "rol": rol, "activo": True, "creado": ahora_iso(),
        }

    def listar_usuarios(self):
        return [{k: v for k, v in u.items() if k != "clave_hash"} for u in self.usuarios.values()]

    def registrar(self, evento: dict):
        self.eventos.append({"id": len(self.eventos) + 1, **evento})

    def auditoria(self, limite: int = 200, solo_ia: bool = False):
        filas = [e for e in reversed(self.eventos) if e.get("es_ia") or not solo_ia]
        return filas[:limite]

    def marcar_lectura(self, lectura_id, columna: str, usuario: str):
        self.lecturas_marcadas.append((lectura_id, columna, usuario))


class AlmacenSQL:
    def __init__(self, url: str):
        from sqlalchemy import Boolean, Column, Integer, MetaData, String, Table, Text, create_engine

        url = normalizar_url(url)
        opciones: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            ruta = url.split("///", 1)[-1]
            if ruta and ruta != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
            opciones["connect_args"] = {"check_same_thread": False, "timeout": 15}
        self.engine = create_engine(url, **opciones)
        self.meta = MetaData()
        self.t_usuarios = Table(
            "usuarios", self.meta,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("usuario", String(60), unique=True, nullable=False),
            Column("clave_hash", String(255), nullable=False),
            Column("rol", String(20), nullable=False),
            Column("activo", Boolean, nullable=False, default=True),
            Column("creado", String(32), nullable=False),
        )
        self.t_auditoria = Table(
            "auditoria", self.meta,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("fecha", String(32), nullable=False, index=True),
            Column("usuario", String(60), nullable=False),
            Column("rol", String(20), nullable=False),
            Column("accion", String(120), nullable=False),
            Column("recurso", String(120), nullable=False, default=""),
            Column("estado_http", Integer, nullable=False, default=0),
            Column("es_ia", Boolean, nullable=False, default=False),
            Column("detalle", Text, nullable=False, default=""),
            Column("ip", String(64), nullable=False, default=""),
        )
        self._lock = threading.Lock()

    def iniciar(self, usuarios_iniciales=()):
        self.meta.create_all(self.engine)
        for usuario, clave, rol in usuarios_iniciales:
            if not self.buscar_usuario(usuario):
                try:
                    self.crear_usuario(usuario, clave, rol)
                    log.info("Usuario inicial creado: %s (%s)", usuario, rol)
                except Exception as e:  # noqa: BLE001  (otro proceso pudo crearlo al tiempo)
                    log.warning("No se creó el usuario inicial %s: %s", usuario, e)

    def buscar_usuario(self, usuario: str):
        from sqlalchemy import select

        with self.engine.connect() as c:
            fila = c.execute(select(self.t_usuarios).where(self.t_usuarios.c.usuario == usuario)).first()
        return dict(fila._mapping) if fila else None

    def crear_usuario(self, usuario: str, clave: str, rol: str):
        from sqlalchemy import insert

        if self.buscar_usuario(usuario):
            raise ValueError("El usuario ya existe")
        with self.engine.begin() as c:
            c.execute(insert(self.t_usuarios).values(
                usuario=usuario, clave_hash=cifrar_clave(clave), rol=rol, activo=True, creado=ahora_iso(),
            ))

    def listar_usuarios(self):
        from sqlalchemy import select

        t = self.t_usuarios
        with self.engine.connect() as c:
            filas = c.execute(select(t.c.usuario, t.c.rol, t.c.activo, t.c.creado).order_by(t.c.usuario)).all()
        return [dict(f._mapping) for f in filas]

    def registrar(self, evento: dict):
        from sqlalchemy import insert

        columnas = {c.name for c in self.t_auditoria.columns} - {"id"}
        with self.engine.begin() as c:
            c.execute(insert(self.t_auditoria).values(**{k: v for k, v in evento.items() if k in columnas}))

    def auditoria(self, limite: int = 200, solo_ia: bool = False):
        from sqlalchemy import select

        t = self.t_auditoria
        consulta = select(t).order_by(t.c.id.desc()).limit(limite)
        if solo_ia:
            consulta = consulta.where(t.c.es_ia.is_(True))
        with self.engine.connect() as c:
            return [dict(f._mapping) for f in c.execute(consulta).all()]

    def marcar_lectura(self, lectura_id, columna: str, usuario: str):
        """Escribe quién subió o revisó una foto en la tabla lecturas_vision (si la columna existe).

        Solo reemplaza el valor provisional 'sin-sesion' o un valor vacío. Si la tabla usa otros nombres,
        no pasa nada: la tabla de auditoría ya guarda quién hizo cada acción.
        """
        from sqlalchemy import text

        if columna not in COLUMNAS_LECTURA or lectura_id in (None, ""):
            return
        valor = int(lectura_id) if str(lectura_id).isdigit() else str(lectura_id)
        sql = text(
            f"UPDATE lecturas_vision SET {columna} = :u "
            f"WHERE id = :id AND ({columna} IS NULL OR {columna} = '' OR {columna} = 'sin-sesion')"
        )
        try:
            with self.engine.begin() as c:
                c.execute(sql, {"u": usuario, "id": valor})
        except Exception as e:  # noqa: BLE001
            log.debug("No se pudo marcar %s en lecturas_vision: %s", columna, e)


def detalle_json(datos: dict) -> str:
    return json.dumps(datos, ensure_ascii=False, default=str)[:1000]
