"""Contraseñas cifradas y tokens de sesión firmados. Solo usa la biblioteca estándar.

- Contraseñas: PBKDF2 con SHA-256, sal aleatoria y 200 000 iteraciones. Nunca se guarda la clave.
- Sesión: un token con usuario, rol y vencimiento, firmado con HMAC (SESION_SECRETO).
  Si alguien lo modifica, la firma deja de coincidir y el token se rechaza.
"""
import base64
import hashlib
import hmac
import json
import os
import time

ITERACIONES = 200_000


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def _desde_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def cifrar_clave(clave: str) -> str:
    sal = os.urandom(16)
    huella = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, ITERACIONES)
    return f"pbkdf2_sha256${ITERACIONES}${_b64(sal)}${_b64(huella)}"


def verificar_clave(clave: str, guardada: str) -> bool:
    try:
        algoritmo, iteraciones, sal, huella = guardada.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        calculada = hashlib.pbkdf2_hmac("sha256", clave.encode(), _desde_b64(sal), int(iteraciones))
        return hmac.compare_digest(calculada, _desde_b64(huella))
    except (ValueError, TypeError):
        return False


def _firma(cuerpo: str, secreto: str) -> str:
    return _b64(hmac.new(secreto.encode(), cuerpo.encode(), hashlib.sha256).digest())


def crear_token(usuario: str, rol: str, secreto: str, horas: float, ahora: float | None = None) -> str:
    ahora = time.time() if ahora is None else ahora
    cuerpo = _b64(json.dumps({"u": usuario, "r": rol, "exp": int(ahora + horas * 3600)}).encode())
    return f"{cuerpo}.{_firma(cuerpo, secreto)}"


def leer_token(token: str, secreto: str, ahora: float | None = None) -> dict | None:
    """Devuelve {"usuario", "rol"} si el token es auténtico y no ha vencido; si no, None."""
    if not token or "." not in token:
        return None
    cuerpo, firma = token.rsplit(".", 1)
    if not hmac.compare_digest(firma, _firma(cuerpo, secreto)):
        return None
    try:
        datos = json.loads(_desde_b64(cuerpo))
    except (ValueError, TypeError):
        return None
    ahora = time.time() if ahora is None else ahora
    if not isinstance(datos, dict) or datos.get("exp", 0) < ahora:
        return None
    return {"usuario": datos.get("u", ""), "rol": datos.get("r", "")}
