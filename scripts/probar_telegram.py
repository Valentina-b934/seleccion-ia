"""Comprueba el bot de Telegram, muestra tu chat_id y envía un mensaje de prueba.

    python scripts/probar_telegram.py

Antes: escríbele cualquier mensaje a tu bot en Telegram (o agrégalo a un grupo y escribe algo ahí).
"""
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402
from app.services import telegram  # noqa: E402


def main() -> int:
    token = settings.telegram_token
    if not token:
        print("✗ TELEGRAM_BOT_TOKEN está vacío en .env. Créalo con @BotFather (comando /newbot) y pégalo ahí.")
        return 1
    base = f"https://api.telegram.org/bot{token}"
    try:
        yo = httpx.get(f"{base}/getMe", timeout=15).json()
    except httpx.HTTPError as e:
        print(f"✗ No hay conexión con Telegram: {e}")
        return 1
    if not yo.get("ok"):
        print(f"✗ El token no es válido: {yo.get('description')}. Cópialo de nuevo desde @BotFather, sin espacios.")
        return 1
    print(f"✓ Bot encontrado: @{yo['result']['username']}")

    chats = {}
    for u in httpx.get(f"{base}/getUpdates", timeout=15).json().get("result", []):
        m = u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}
        chat = m.get("chat")
        if chat:
            chats[chat["id"]] = chat.get("title") or chat.get("first_name") or chat.get("username") or ""
    if chats:
        print("\nChats que le han escrito al bot (copia el número en TELEGRAM_CHAT_ID):")
        for cid, nombre in chats.items():
            print(f"   TELEGRAM_CHAT_ID={cid}    ({nombre})")
    else:
        print("\n– Todavía nadie le ha escrito al bot. Abre Telegram, busca "
              f"@{yo['result']['username']}, presiona Iniciar y escríbele «hola». Luego ejecuta esto otra vez.")

    if not settings.telegram_chat_id:
        print("\n✗ TELEGRAM_CHAT_ID está vacío en .env: pega ahí el número de arriba y vuelve a ejecutar.")
        return 1
    if telegram.avisar("✅ Prueba del sistema de selección de personal: los avisos de Telegram funcionan."):
        print(f"\n✓ Mensaje de prueba enviado al chat {settings.telegram_chat_id}. Revisa Telegram.")
        print("  Reinicia el servidor (Ctrl + C y uvicorn app.servidor:app --reload) para que use estos datos.")
        return 0
    print(f"\n✗ No se pudo enviar al chat {settings.telegram_chat_id}. Revisa que el número sea uno de la lista de arriba "
          "(los grupos empiezan con -) y que el bot siga en ese chat.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
