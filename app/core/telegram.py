import os
import httpx
import asyncio

# You will add these to your Render / .env file
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_FROM_BOTFATHER")
TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "YOUR_CHAT_ID")

async def dispatch_telegram_alert(message: str):
    """
    Fires an asynchronous alert to the Admin Telegram via Bot API.
    Fails silently so it never interrupts the main user flow.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("Telegram env vars missing. Alert skipped.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_ADMIN_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    # We use a quick background task to ensure it doesn't block the API response
    async def _send():
        async with httpx.AsyncClient() as client:
            try:
                await client.post(url, json=payload, timeout=5.0)
            except Exception as e:
                print(f"Telegram Alert Failed: {e}")

    asyncio.create_task(_send())