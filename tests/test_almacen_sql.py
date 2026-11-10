"""Tablas de usuarios y auditoría sobre una base SQLite temporal (la misma lógica sirve para PostgreSQL)."""
import sqlite3

import pytest

pytest.importorskip("sqlalchemy")

from app.seguridad.almacen import AlmacenSQL, normalizar_url  # noqa: E402
from app.seguridad.claves import verificar_clave  # noqa: E402


@pytest.fixture
def almacen(tmp_path):
    a = AlmacenSQL(f"sqlite:///{tmp_path / 'prueba.db'}")
    a.iniciar([("admin", "Admin.2026", "admin"), ("consulta", "Consulta.2026", "consulta")])
    return a


def test_crea_usuarios_iniciales_una_sola_vez(almacen):
    almacen.iniciar([("admin", "OtraClave.1", "admin")])  # reiniciar no cambia la clave
    fila = almacen.buscar_usuario("admin")
    assert fila["rol"] == "admin" and verificar_clave("Admin.2026", fila["clave_hash"])
    assert {u["usuario"] for u in almacen.listar_usuarios()} == {"admin", "consulta"}
    assert all("clave_hash" not in u for u in almacen.listar_usuarios())


def test_no_permite_usuarios_repetidos(almacen):
    with pytest.raises(ValueError):
        almacen.crear_usuario("admin", "x" * 10, "admin")


def test_registra_y_filtra_auditoria(almacen):
    base = {"fecha": "2026-11-09T10:00:00+00:00", "usuario": "admin", "rol": "admin", "recurso": "",
            "estado_http": 200, "detalle": "{}", "ip": "127.0.0.1"}
    almacen.registrar({**base, "accion": "LOGIN", "es_ia": False})
    almacen.registrar({**base, "accion": "POST /api/vision", "es_ia": True, "recurso": "3"})
    todo = almacen.auditoria(10)
    assert [e["accion"] for e in todo] == ["POST /api/vision", "LOGIN"]  # lo más reciente primero
    assert [e["accion"] for e in almacen.auditoria(10, solo_ia=True)] == ["POST /api/vision"]


def test_marca_quien_subio_la_foto_solo_si_estaba_sin_sesion(tmp_path):
    ruta = tmp_path / "vision.db"
    with sqlite3.connect(ruta) as c:
        c.execute("CREATE TABLE lecturas_vision (id INTEGER PRIMARY KEY, subido_por TEXT, revisado_por TEXT)")
        c.execute("INSERT INTO lecturas_vision VALUES (1, 'sin-sesion', NULL), (2, 'otra-persona', NULL)")
    a = AlmacenSQL(f"sqlite:///{ruta}")
    a.marcar_lectura("1", "subido_por", "reclutador")
    a.marcar_lectura("2", "subido_por", "reclutador")
    a.marcar_lectura("1", "revisado_por", "admin")
    a.marcar_lectura("1", "columna_inventada", "admin")  # se ignora sin error
    with sqlite3.connect(ruta) as c:
        filas = c.execute("SELECT id, subido_por, revisado_por FROM lecturas_vision ORDER BY id").fetchall()
    assert filas == [(1, "reclutador", "admin"), (2, "otra-persona", None)]


def test_url_de_neon_se_adapta_a_psycopg():
    assert normalizar_url("postgres://u:c@h/db") == "postgresql+psycopg://u:c@h/db"
    assert normalizar_url("postgresql://u:c@h/db") == "postgresql+psycopg://u:c@h/db"
    assert normalizar_url("sqlite:///./data/x.db") == "sqlite:///./data/x.db"
