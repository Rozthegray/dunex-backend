import os
import httpx

# 🚨 Removed the fallback text so we know immediately if Render misses the variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID")

async def dispatch_telegram_alert(message: str):
    """
    Fires an alert to the Admin Telegram via Bot API.
    Awaits the response to guarantee execution before FastAPI closes the request.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("🚨 Telegram env vars missing. Alert skipped.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_ADMIN_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    # 🚨 Direct await to guarantee execution before the user's request closes
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=5.0)
            
            # If Telegram blocks it, this prints the exact reason to your Render logs
            if response.status_code != 200:
                print(f"🚨 Telegram Rejected Alert: {response.text}")
            else:
                print("✅ Telegram Alert Dispatched Successfully.")
                
        except Exception as e:
            print(f"🚨 Telegram Network Failure: {e}")
