"""Send a report to Telegram with the Bot API (token and chat id from .env)."""
import os

import requests

MAX_LEN = 4000  # Telegram allows 4096 characters per message


def send(text: str, chat_id: str | None = None) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
    if not (token and chat_id):
        print("----- [telegram not configured, printing] -----")
        print(text)
        return
    while text:
        part, text = text[:MAX_LEN], text[MAX_LEN:]
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": part,
                                "disable_web_page_preview": True}, timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"Telegram send failed {r.status_code}: {r.text[:200]}")
