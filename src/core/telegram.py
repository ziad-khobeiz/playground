import os
import requests
from typing import Optional

def send_message(message: str, chat_id: Optional[str] = None, bot_token: Optional[str] = None) -> bool:
    """
    Send a message to a Telegram chat.
    If chat_id is not provided, it attempts to use MY_TELEGRAM_UID from environment.
    If bot_token is not provided, it attempts to use APARTMENTS_BOT_TOKEN from environment.
    """
    if not bot_token:
        bot_token = os.getenv("APARTMENTS_BOT_TOKEN")
    if not chat_id:
        chat_id = os.getenv("MY_TELEGRAM_UID")

    if not bot_token or not chat_id:
        print("Error: APARTMENTS_BOT_TOKEN or MY_TELEGRAM_UID/chat_id not found.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        if 'response' in locals():
             print(f"Response text: {response.text}")
        return False
