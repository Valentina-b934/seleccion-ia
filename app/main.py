"""API del sistema de selección de personal (reemplaza a los flujos de n8n).

    uvicorn app.servidor:app --reload   ← con inicio de sesión, roles y auditoría (lo normal)
    uvicorn app.main:app --reload       ← sin seguridad, solo para depurar en tu computador

| Flujo de n8n                         | Ruta                          | Servicio                 |
|--------------------------------------|-------------------------------|--------------------------|
| Selección de personal con IA (carga) | POST /api/candidatos          | services/carga.py        |
| Lista de candidatos                  | GET  /api/candidatos          | services/lista.py        |
| Chat Selección de Personal           | POST /api/chat                | services/chat.py         |
| (nuevo) Módulo de visión             | POST /api/vision              | services/vision.py       |
| (nuevo) Resumen diario / reintentos  | hilo programado + /api/tareas | services/tareas.py       |
| Pestaña Executions                   | GET  /api/ejecuciones         | services/registro.py     |
"""
import functools
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .config import settings
from .errores import EntradaInvalida, ErrorDeUsuario, NoEncontrado
from .services import carga, chat, lectura, lista, llm, registro, tareas, telegram, vision

log = logging.getLogger("seleccion")
PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    db.configurar()
    os.makedirs(settings.imagenes_dir, exist_ok=True)
    tareas.iniciar()
    log.info("Modelos de IA en orden: %s", llm.nombres_modelos() or "ninguno configurado")
    yield
    tareas.detener()


app = FastAPI(
    title="Selección de personal con IA",
    description="Motor de automatización propio (antes n8n), módulo de visión y asistente con LangChain.",
    version="4.0",
    lifespan=ciclo_de_vida,
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origenes, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


# ───────────────────────── Errores con mensaje claro ─────────────────────────
@app.exception_handler(ErrorDeUsuario)
async def _error_usuario(_request: Request, e: ErrorDeUsuario):
    return JSONResponse(status_code=e.codigo, content={"detail": e.mensaje, "mensaje": e.mensaje})


@app.exception_handler(RequestValidationError)
async def _error_validacion(_request: Request, e: RequestValidationError):
    campos = ", ".join(str(err.get("loc", ["", "?"])[-1]) for err in e.errors())
    mensaje = f"Faltan datos o no son válidos: {campos}."
    return JSONResponse(status_code=422, content={"detail": mensaje, "mensaje": mensaje})


@app.exception_handler(Exception)
async def _error_inesperado(_request: Request, e: Exception):
    log.exception("Error inesperado: %s", e)
    mensaje = "Ocurrió un error inesperado en el servidor. Quedó en el registro; intenta de nuevo."
    return JSONResponse(status_code=500, content={"detail": mensaje, "mensaje": mensaje})


# ───────────────────────── Estado ─────────────────────────
@functools.lru_cache(maxsize=1)
def _ocr_disponible() -> bool:
    return lectura.tesseract_disponible()


@app.get("/api/estado", tags=["sistema"])
def estado():
    return {
        "ok": True,
        "modelos": llm.nombres_modelos(),
        "ocr": _ocr_disponible(),
        "telegram": telegram.configurado(),
        "cargos": lista.cargos(),
        "max_pdf_mb": settings.max_pdf_mb,
        "max_imagen_mb": settings.max_imagen_mb,
        "umbrales": {"alto": settings.umbral_alto, "medio": settings.umbral_medio, "ocr": settings.umbral_ocr,
                     "campo": settings.umbral_campo, "ocr_minimo": settings.umbral_ocr_minimo},
    }


# ───────────────────────── Flujo 1: carga de PDF ─────────────────────────
@app.post("/api/candidatos", tags=["flujos"], status_code=201)
def cargar_candidato(
    Archivo: UploadFile = File(..., description="Hoja de vida en PDF"),
    Nombre: str = Form(...),
    Correo: str = Form(...),
    Cargo: str = Form(...),
    Autorizacion: str = Form("false"),
):
    contenido = Archivo.file.read(settings.max_pdf_mb * 1024 * 1024 + 1)
    return carga.procesar_pdf(contenido, Archivo.filename or "hoja.pdf", Nombre, Correo, Cargo, Autorizacion)


# ───────────────────────── Flujo 2: lista ─────────────────────────
@app.get("/api/candidatos", tags=["flujos"])
def listar_candidatos():
    return lista.listar()


@app.delete("/api/candidatos/{candidato_id}", tags=["flujos"])
def suprimir_candidato(candidato_id: str):
    if not lista.eliminar(candidato_id):
        raise NoEncontrado("El candidato no existe.")
    return {"candidato_id": candidato_id, "estado": "suprimido"}


# ───────────────────────── Flujo 3: chat ─────────────────────────
@app.post("/api/chat", tags=["flujos"])
def preguntar(datos: dict = Body(...)):
    return chat.responder(str(datos.get("pregunta") or datos.get("chatInput") or ""))


# ───────────────────────── Flujo 4: módulo de visión ─────────────────────────
@app.post("/api/vision", tags=["visión"], status_code=201)
def subir_foto(
    Imagen: UploadFile = File(..., description="Foto JPG, PNG o WebP de la hoja de vida o ficha"),
    Nombre: str = Form(...),
    Correo: str = Form(...),
    Cargo: str = Form(...),
    Autorizacion: str = Form("false"),
):
    contenido = Imagen.file.read(settings.max_imagen_mb * 1024 * 1024 + 1)
    return vision.procesar_imagen(contenido, Imagen.filename or "foto.jpg", Nombre, Correo, Cargo, Autorizacion)


@app.get("/api/vision", tags=["visión"])
def listar_lecturas(estado: str | None = None):
    return vision.listar(estado)


@app.get("/api/vision/{lectura_id}", tags=["visión"])
def ver_lectura(lectura_id: int):
    return vision.obtener(lectura_id)


@app.get("/api/vision/{lectura_id}/imagen", tags=["visión"])
def ver_imagen(lectura_id: int):
    ruta, tipo = vision.ruta_imagen(lectura_id)
    return FileResponse(ruta, media_type=tipo, headers={"Cache-Control": "private, no-store"})


@app.post("/api/vision/{lectura_id}/confirmar", tags=["visión"])
def confirmar_lectura(lectura_id: int, datos: dict = Body(...)):
    campos = datos.get("campos")
    if not isinstance(campos, dict):
        raise EntradaInvalida('Envía {"campos": {...}} con los datos revisados.')
    return vision.confirmar(lectura_id, campos)


@app.post("/api/vision/{lectura_id}/rechazar", tags=["visión"])
def rechazar_lectura(lectura_id: int):
    return vision.rechazar(lectura_id)


# ───────────────────────── Ejecuciones y tareas ─────────────────────────
@app.get("/api/ejecuciones", tags=["sistema"])
def ver_ejecuciones(limite: int = 200, flujo: str | None = None):
    return registro.listar(max(1, min(limite, 1000)), flujo)


@app.post("/api/tareas/resumen", tags=["sistema"])
def tarea_resumen():
    return tareas.enviar_resumen()


@app.post("/api/tareas/reintentar", tags=["sistema"])
def tarea_reintentar():
    return tareas.reintentar_vision()


# ───────────────────────── Panel web ─────────────────────────
app.mount("/", StaticFiles(directory=PANEL, html=True), name="panel")
