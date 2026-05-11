import requests

from config import TELEGRAM_TOKEN


def send_telegram_message(chat_id, text: str):
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_BOT_TOKEN ausente.")
        return {"status": "error", "detail": "TELEGRAM_BOT_TOKEN ausente"}

    send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    telegram_response = requests.post(
        send_url,
        json={"chat_id": chat_id, "text": text[:4000]},
        timeout=20,
    )

    print("TELEGRAM RESPONSE:", telegram_response.text)
    return {"status": "ok"}
