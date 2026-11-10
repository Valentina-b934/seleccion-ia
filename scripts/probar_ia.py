"""Prueba cada proveedor de IA por separado y muestra el error exacto.

    python scripts/probar_ia.py

Úsalo cuando el panel diga «El servicio de IA no está disponible»: indica qué proveedor falla y por qué.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402
from app.services import llm  # noqa: E402

PISTAS = [
    (("401", "unauthorized", "invalid api key", "api key not valid", "api_key_invalid", "user not found"),
     "La clave no es válida: cópiala de nuevo completa, sin espacios ni comillas, y reinicia el servidor."),
    (("no endpoints found matching your data policy", "data policy"),
     "OpenRouter: en openrouter.ai/settings/privacy activa la opción que permite usar modelos gratuitos "
     "(«Enable free endpoints that may train on inputs» / publicación de prompts) y guarda."),
    (("404", "not found", "no endpoints found", "is not a valid model", "does not exist", "not supported"),
     "El nombre del modelo ya no existe. Busca uno vigente (en OpenRouter: openrouter.ai/models con el filtro «Free», "
     "termina en :free) y cámbialo en OPENROUTER_MODEL / GEMINI_MODEL / GROQ_MODEL del .env."),
    (("429", "rate limit", "quota", "resource_exhausted", "too many requests"),
     "Límite de uso: espera un minuto. En OpenRouter las cuentas sin créditos tienen pocas peticiones diarias en modelos :free."),
    (("timeout", "timed out", "connect", "ssl", "proxy"),
     "Problema de conexión: revisa internet, el antivirus o el proxy de la red."),
]


def pista(texto: str) -> str:
    t = texto.lower()
    for claves, consejo in PISTAS:
        if any(c in t for c in claves):
            return consejo
    return "Revisa el mensaje de error de arriba."


HOJA = """Camila Restrepo. Ingeniera de sistemas con 6 años de experiencia en Python, FastAPI, Django y React.
Desarrolladora senior en Soluciones Andinas (2022 - actual). Ingeniería de Sistemas, UTP (2019).
Certificaciones: AWS Certified Developer."""


def main() -> int:
    modelos = {"openrouter": settings.openrouter_model, "gemini": settings.gemini_model,
               "groq": settings.groq_model, "ollama": settings.ollama_model}
    print(f"LLM_PROVIDERS = {settings.llm_providers}\n")
    settings.llm_reintentos = 1
    algun_ok = False
    for nombre in settings.llm_providers:
        print(f"── {nombre} (modelo: {modelos.get(nombre, '?')})")
        try:
            modelo = llm._construir(nombre)
        except Exception as e:  # noqa: BLE001
            print(f"   ✗ No se pudo crear el cliente: {type(e).__name__}: {e}\n")
            continue
        if modelo is None:
            print("   – Omitido: no tiene clave en .env (o falta instalar su paquete).\n")
            continue
        try:
            r = modelo.invoke("Responde solo con la palabra: listo")
            print(f"   ✓ Responde: {llm.texto_de_respuesta(r)[:80]}")
        except Exception as e:  # noqa: BLE001
            texto = f"{type(e).__name__}: {e}"
            print(f"   ✗ {texto[:600]}")
            print(f"   → {pista(texto)}\n")
            continue
        # Prueba real: la misma extracción que hace el sistema con una hoja de vida.
        try:
            llm.usar_modelos([modelo])
            datos = llm.extraer_datos(HOJA, "Desarrollador de software")
            print(f"   ✓ Extrae una hoja de vida: profesión «{datos.profesion}», {datos.experiencia_anios} años, "
                  f"puntaje {datos.puntaje}\n")
            algun_ok = True
        except Exception as e:  # noqa: BLE001
            causa = e.__cause__ or e
            print(f"   ✗ Responde, pero falla al extraer la hoja de vida: {type(causa).__name__}: {str(causa)[:400]}")
            print("   → Prueba con otro modelo o vuelve a intentar (openrouter/free puede elegir otro).\n")
        finally:
            llm.usar_modelos(None)
    print("Resultado:", "al menos un proveedor funciona." if algun_ok else "ningún proveedor respondió.")
    return 0 if algun_ok else 1


if __name__ == "__main__":
    sys.exit(main())
