"""
Dunex Markets — Notification Service
Handles WhatsApp Business API, SendGrid email, Expo push notifications, and Telegram Alerts.
Set these env vars:
  WHATSAPP_TOKEN, WHATSAPP_PHONE_ID, ADMIN_WHATSAPP_NUMBER
  SENDGRID_API_KEY, ADMIN_EMAIL, FROM_EMAIL
  EXPO_ACCESS_TOKEN (optional)
"""
import os
import asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.domains.notifications.models import Notification

# 🚨 Import the Telegram dispatcher
from app.core.telegram import dispatch_telegram_alert

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
ADMIN_WHATSAPP_NUMBER = os.getenv("ADMIN_WHATSAPP_NUMBER", "")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@dunexmarkets.com")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@dunexmarkets.com")
EXPO_ACCESS_TOKEN = os.getenv("EXPO_ACCESS_TOKEN", "")


async def _log(db: AsyncSession, notif_type: str, status: str, payload: dict, user_id=None):
    n = Notification(user_id=user_id, type=notif_type, status=status, payload=payload)
    db.add(n)
    await db.commit()


async def send_whatsapp_to_admin(user_email: str, message_preview: str, db: AsyncSession):
    """Send a WhatsApp template message to admin when user opens/sends chat."""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID or not ADMIN_WHATSAPP_NUMBER:
        print(f"[WhatsApp] SKIP — env vars not set. Would notify admin: {user_email}: {message_preview[:60]}")
        return

    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": ADMIN_WHATSAPP_NUMBER,
        "type": "template",
        "template": {
            "name": "customer_support_alert",
            "language": {"code": "en_US"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": user_email},
                        {"type": "text", "text": message_preview[:100]},
                    ],
                }
            ],
        },
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}, timeout=10)
        status = "sent" if r.status_code == 200 else "failed"
        await _log(db, "whatsapp", status, {"to": ADMIN_WHATSAPP_NUMBER, "user": user_email, "response": r.text[:200]})
    except Exception as e:
        await _log(db, "whatsapp", "failed", {"error": str(e)})
        print(f"[WhatsApp] Error: {e}")


async def send_admin_email_alert(user_email: str, message_preview: str, db: AsyncSession):
    """Email admin for critical alerts."""
    if not SENDGRID_API_KEY:
        print(f"[Email] SKIP — SENDGRID_API_KEY not set.\nTO: {ADMIN_EMAIL}\nSUBJECT: Alert regarding {user_email}")
        return

    url = "https://api.sendgrid.com/v3/mail/send"
    payload = {
        "personalizations": [{"to": [{"email": ADMIN_EMAIL}]}],
        "from": {"email": FROM_EMAIL, "name": "Dunex Markets"},
        "subject": f"System Alert: Activity from {user_email}",
        "content": [
            {
                "type": "text/html",
                "value": f"""
                <div style="font-family:sans-serif;max-width:560px;margin:auto;">
                  <h2 style="color:#1e293b;">System Notification</h2>
                  <p><strong>User:</strong> {user_email}</p>
                  <div style="background:#f1f5f9;border-left:4px solid #3b82f6;padding:12px 16px;border-radius:4px;margin:16px 0;">
                    {message_preview}
                  </div>
                  <a href="https://admin.dunexmarkets.com" style="display:inline-block;background:#3b82f6;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none;">
                    Open Admin Dashboard
                  </a>
                </div>
                """,
            }
        ],
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers={"Authorization": f"Bearer {SENDGRID_API_KEY}"}, timeout=10)
        status = "sent" if r.status_code in (200, 202) else "failed"
        await _log(db, "email", status, {"to": ADMIN_EMAIL, "user": user_email, "status_code": r.status_code})
    except Exception as e:
        await _log(db, "email", "failed", {"error": str(e)})
        print(f"[Email] Error: {e}")


async def send_push_to_user(expo_token: str, title: str, body: str, db: AsyncSession, user_id=None):
    """Send Expo push notification to mobile user."""
    if not expo_token:
        return

    url = "https://exp.host/--/api/v2/push/send"
    payload = {
        "to": expo_token,
        "title": title,
        "body": body,
        "sound": "default",
        "data": {"screen": "chat"},
    }
    headers = {"Content-Type": "application/json"}
    if EXPO_ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {EXPO_ACCESS_TOKEN}"

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers, timeout=10)
        status = "sent" if r.status_code == 200 else "failed"
        await _log(db, "push", status, {"token": expo_token[:20], "title": title}, user_id=user_id)
    except Exception as e:
        await _log(db, "push", "failed", {"error": str(e)}, user_id=user_id)
        print(f"[Push] Error: {e}")


# ─────────────────────────────────────────────
# 🚨 CENTRALIZED ADMIN NOTIFICATION TRIGGERS
# ─────────────────────────────────────────────

async def notify_admin_new_chat(user_email: str, message: str, db: AsyncSession):
    """Fires when a user sends a live chat message."""
    tg_msg = f"💬 <b>New Live Chat</b>\n<b>User:</b> {user_email}\n<b>Message:</b> {message[:100]}"
    
    await asyncio.gather(
        send_whatsapp_to_admin(user_email, message, db),
        send_admin_email_alert(user_email, f"Live Chat: {message}", db),
        dispatch_telegram_alert(tg_msg)
    )

async def notify_admin_support_ticket(user_email: str, subject: str, message: str, db: AsyncSession):
    """Fires when a user submits a support ticket."""
    tg_msg = f"🎫 <b>New Support Ticket</b>\n<b>User:</b> {user_email}\n<b>Subject:</b> {subject}\n<b>Message:</b> {message[:100]}"
    
    await asyncio.gather(
        send_admin_email_alert(user_email, f"Ticket - {subject}: {message}", db),
        dispatch_telegram_alert(tg_msg)
    )

async def notify_admin_deposit(user_email: str, amount: float, currency: str, db: AsyncSession):
    """Fires when a deposit is initiated or completed."""
    tg_msg = f"💰 <b>New Deposit</b>\n<b>User:</b> {user_email}\n<b>Amount:</b> {amount} {currency}"
    
    await asyncio.gather(
        send_admin_email_alert(user_email, f"Initiated a deposit of {amount} {currency}", db),
        dispatch_telegram_alert(tg_msg)
    )

async def notify_admin_withdrawal(user_email: str, amount: float, currency: str, db: AsyncSession):
    """Fires when a user requests a withdrawal."""
    tg_msg = f"🏦 <b>Withdrawal Request</b>\n<b>User:</b> {user_email}\n<b>Amount:</b> {amount} {currency}"
    
    await asyncio.gather(
        send_admin_email_alert(user_email, f"Requested a withdrawal of {amount} {currency}", db),
        dispatch_telegram_alert(tg_msg)
    )

async def notify_admin_new_user(user_email: str, db: AsyncSession):
    """Fires when a new user completes registration."""
    tg_msg = f"👤 <b>New User Registration</b>\n<b>Email:</b> {user_email}"
    
    await asyncio.gather(
        send_admin_email_alert(user_email, "Successfully registered a new account.", db),
        dispatch_telegram_alert(tg_msg)
      )
