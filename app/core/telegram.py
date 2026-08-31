import os
import httpx

# 🚨 Removed the fallback text so we know immediately if Render misses the variable
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
            response = await client.post(url, json=payload, timeout=10.0)
            
            if response.status_code != 200:
                print(f"🚨 Telegram Rejected Alert: {response.text}")
            else:
                print("✅ Telegram Alert Dispatched Successfully.")
                
        except Exception as e:
            print(f"🚨 Telegram Network Failure: {e}")


# ─────────────────────────────────────────────
# 🚨 SPECIFIC EVENT TRIGGERS (Live Chat, Users, Emails)
# ─────────────────────────────────────────────

async def notify_telegram_new_user(email: str):
    """Trigger when a new user registers."""
    msg = f"👤 <b>New User Registration</b>\n<b>Email:</b> {email}"
    await dispatch_telegram_alert(msg)

async def notify_telegram_live_chat(email: str, message: str):
    """Trigger when a user sends a message in the Live Chat."""
    msg = f"💬 <b>New Live Chat</b>\n<b>User:</b> {email}\n<b>Message:</b> {message[:100]}"
    await dispatch_telegram_alert(msg)

async def notify_telegram_support_ticket(email: str, subject: str, message: str):
    """Trigger when a user submits a support ticket."""
    msg = f"🎫 <b>New Support Ticket</b>\n<b>User:</b> {email}\n<b>Subject:</b> {subject}\n<b>Message:</b> {message[:100]}"
    await dispatch_telegram_alert(msg)
    
async def notify_telegram_email_sent(to_email: str, subject: str):
    """Trigger when an important system email is dispatched."""
    msg = f"📧 <b>System Email Dispatched</b>\n<b>To:</b> {to_email}\n<b>Subject:</b> {subject}"
    await dispatch_telegram_alert(msg)

async def notify_telegram_deposit(email: str, amount: float, currency: str = "USD"):
    """Trigger when a deposit is initiated."""
    msg = f"💰 <b>New Deposit</b>\n<b>User:</b> {email}\n<b>Amount:</b> {amount} {currency}"
    await dispatch_telegram_alert(msg)

async def notify_telegram_withdrawal(email: str, amount: float, currency: str = "USD"):
    """Trigger when a withdrawal is requested."""
    msg = f"🏦 <b>Withdrawal Request</b>\n<b>User:</b> {email}\n<b>Amount:</b> {amount} {currency}"
    await dispatch_telegram_alert(msg)
