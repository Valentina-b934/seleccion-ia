"""Configuración del sistema. Todo sale de variables de entorno (archivo .env).

Las claves de API NUNCA van en el código: se leen aquí desde el entorno.
"""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env(nombre: str, defecto: str = "") -> str:
    return os.environ.get(nombre, defecto).strip()


def _env_int(nombre: str, defecto: int) -> int:
    try:
        return int(_env(nombre, str(defecto)))
    except ValueError:
        return defecto


def _env_float(nombre: str, defecto: float) -> float:
    try:
        return float(_env(nombre, str(defecto)))
    except ValueError:
        return defecto


def _lista(texto: str) -> list[str]:
    return [p.strip() for p in texto.split(",") if p.strip()]


@dataclass
class Configuracion:
    # Base de datos (SQLite en desarrollo; PostgreSQL de Neon o Supabase al desplegar)
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///./data/candidatos.db"))

    # Modelos de IA, en orden de preferencia. Si el primero falla se usa el siguiente.
    llm_providers: list[str] = field(default_factory=lambda: _lista(_env("LLM_PROVIDERS", "openrouter,gemini")))
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    groq_model: str = field(default_factory=lambda: _env("GROQ_MODEL", "llama-3.3-70b-versatile"))
    google_api_key: str = field(default_factory=lambda: _env("GOOGLE_API_KEY"))
    gemini_model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-3.8-flash"))
    # OpenRouter (compatible con la API de OpenAI). Los modelos gratuitos terminan en ":free".
    openrouter_api_key: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY"))
    openrouter_model: str = field(default_factory=lambda: _env("OPENROUTER_MODEL", "openrouter/free"))
    openrouter_url: str = field(default_factory=lambda: _env("OPENROUTER_URL", "https://openrouter.ai/api/v1"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "llama3.1"))
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))

    # Reintentos ante fallos del modelo
    llm_reintentos: int = field(default_factory=lambda: _env_int("LLM_REINTENTOS", 3))
    llm_espera: float = field(default_factory=lambda: _env_float("LLM_ESPERA_SEGUNDOS", 2.0))
    llm_timeout: float = field(default_factory=lambda: _env_float("LLM_TIMEOUT_SEGUNDOS", 40.0))

    # Telegram (opcional: si faltan, los avisos se omiten y queda constancia en el registro)
    telegram_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID"))

    # Reglas de decisión (las mismas del nodo Switch de n8n)
    umbral_alto: int = field(default_factory=lambda: _env_int("UMBRAL_ALTO", 80))
    umbral_medio: int = field(default_factory=lambda: _env_int("UMBRAL_MEDIO", 60))

    # Límites
    max_pdf_mb: int = field(default_factory=lambda: _env_int("MAX_PDF_MB", 10))
    max_contexto_chat: int = field(default_factory=lambda: _env_int("MAX_CONTEXTO_CHAT", 60000))

    # ── Módulo de visión ──
    # Ruta de Tesseract si no está en el PATH (en Windows se busca sola en la carpeta por defecto)
    tesseract_cmd: str = field(default_factory=lambda: _env("TESSERACT_CMD"))
    ocr_idiomas: str = field(default_factory=lambda: _env("OCR_IDIOMAS", "spa+eng"))
    imagenes_dir: str = field(default_factory=lambda: _env("IMAGENES_DIR", "data/imagenes"))
    max_imagen_mb: int = field(default_factory=lambda: _env_int("MAX_IMAGEN_MB", 10))
    max_lado_imagen: int = field(default_factory=lambda: _env_int("MAX_LADO_IMAGEN", 2600))
    # Si la lectura del OCR o la confianza de un campo baja de estos valores (0 a 1),
    # la persona revisa los datos antes de guardar. Se calibran con las pruebas con fotos reales.
    umbral_ocr: float = field(default_factory=lambda: _env_float("UMBRAL_OCR", 0.70))
    umbral_campo: float = field(default_factory=lambda: _env_float("UMBRAL_CAMPO", 0.60))
    # Por debajo de este valor la foto se rechaza sin llamar a la IA (no tiene caso analizar texto ilegible).
    umbral_ocr_minimo: float = field(default_factory=lambda: _env_float("UMBRAL_OCR_MINIMO", 0.45))

    # ── Tareas programadas (cron propio del motor) ──
    tareas_activas: bool = field(default_factory=lambda: _env("TAREAS_ACTIVAS", "true").lower() in ("1", "true", "si", "sí"))
    tareas_minutos: int = field(default_factory=lambda: _env_int("TAREAS_MINUTOS", 30))
    resumen_hora: int = field(default_factory=lambda: _env_int("RESUMEN_HORA", 8))
    zona_horaria_horas: int = field(default_factory=lambda: _env_int("ZONA_HORARIA_HORAS", -5))  # Colombia

    # Orígenes permitidos si el panel se abre desde otro puerto (por ejemplo Live Server)
    cors_origenes: list[str] = field(
        default_factory=lambda: _lista(_env("CORS_ORIGENES", "http://127.0.0.1:5500,http://localhost:5500"))
    )

    # ── Memoria del chat (semana 4) ──
    # Cuántos turnos (pregunta y respuesta) recuerda el asistente por usuario. 0 la desactiva.
    chat_memoria_turnos: int = field(default_factory=lambda: _env_int("CHAT_MEMORIA_TURNOS", 6))

    # ── Inicio de sesión y roles (semana 4) ──
    # Secreto con el que se firman las sesiones. En producción debe ser largo y aleatorio.
    sesion_secreto: str = field(default_factory=lambda: _env("SESION_SECRETO"))
    sesion_horas: float = field(default_factory=lambda: _env_float("SESION_HORAS", 8.0))
    # true cuando el sitio corre con HTTPS (Render, Railway): la cookie solo viaja cifrada.
    cookie_segura: bool = field(default_factory=lambda: _env("COOKIE_SEGURA", "false").lower() in ("1", "true", "si", "sí"))
    # Usuarios que se crean solos la primera vez (si ya existen, no se tocan).
    clave_admin: str = field(default_factory=lambda: _env("CLAVE_ADMIN", "Admin.2026"))
    clave_reclutador: str = field(default_factory=lambda: _env("CLAVE_RECLUTADOR", "Recluta.2026"))
    clave_consulta: str = field(default_factory=lambda: _env("CLAVE_CONSULTA", "Consulta.2026"))

    def usuarios_iniciales(self) -> list[tuple[str, str, str]]:
        return [
            ("admin", self.clave_admin, "admin"),
            ("reclutador", self.clave_reclutador, "reclutador"),
            ("consulta", self.clave_consulta, "consulta"),
        ]


settings = Configuracion()
