import os
import asyncio
import mailtrap as mt

# 🚨 Pulls from your .env
MAILTRAP_API_TOKEN = os.getenv("MAILTRAP_TOKEN")
FROM_EMAIL = os.getenv("FROM_EMAIL", "support@dunexmarkets.com")
ADMIN_ALERT_EMAIL = os.getenv("ADMIN_ALERT_EMAIL", "admin@dunexmarkets.com")
LOGO_URL = "https://res.cloudinary.com/dkpicfvgv/image/upload/icon_oo2lbm.png"

def _send_api_email_sync(to_email: str, subject: str, raw_body: str, category: str):
    """Internal helper to dispatch branded emails over HTTPS via Mailtrap."""
    if not MAILTRAP-API_TOKEN:
        print(f"[WARNING] Email skipped for {to_email}. Mailtrap Token missing.")
        return

    html_template = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #05050a; color: #ffffff; padding: 40px; border-radius: 12px; border: 1px solid #1f2937;">
        <div style="text-align: left; margin-bottom: 30px;">
            <img src="{LOGO_URL}" alt="Dunex Markets" style="max-height: 40px; width: auto;" />
        </div>
        <div style="color: #d1d5db; line-height: 1.6; font-size: 16px;">
            {raw_body}
        </div>
        <p style="color: #6b7280; font-size: 12px; margin-top: 40px; border-top: 1px solid #1f2937; padding-top: 20px;">
            This is an automated message from Dunex Markets. Do not reply to this email directly.
        </p>
    </div>
    """

    # Build the Mailtrap payload
    mail = mt.Mail(
        sender=mt.Address(email=FROM_EMAIL, name="Dunex Support"),
        to=[mt.Address(email=to_email)],
        subject=subject,
        html=html_template,
        category=category
    )

    try:
        # Fire via API, completely bypassing SMTP firewalls
        client = mt.MailtrapClient(token=MAILTRAP_API_TOKEN)
        client.send(mail)
        print(f"[MAILTRAP API] {category} successfully sent to {to_email}")
    except Exception as e:
        print(f"[MAILTRAP ERROR] {category} Dispatch Failed: {e}")

# 🚨 THE BRIDGE FIX: Keeps the chat router from crashing
def _send_api_email(to_email: str, subject: str, body: str):
    _send_api_email_sync(to_email, subject, body, "Chat System Alert")

# ---------------------------------------------------------
# Public Email Functions (Fully Async via HTTPS)
# ---------------------------------------------------------

async def send_onboarding_email(to_email: str, full_name: str):
    body = f"Welcome to Dunex Markets, {full_name}. Please complete your KYC to unlock full trading capabilities."
    await asyncio.to_thread(_send_api_email_sync, to_email, "Welcome to Dunex Markets", body, "Onboarding")

async def send_password_reset_email(to_email: str, reset_code: str):
    body = f"Your password reset code is: <strong>{reset_code}</strong>. This code expires in 15 minutes."
    await asyncio.to_thread(_send_api_email_sync, to_email, "Dunex Markets: Password Reset", body, "Password Reset")

async def send_admin_broadcast_email(to_email: str, subject: str, message_body: str):
    await asyncio.to_thread(_send_api_email_sync, to_email, subject, message_body, "Admin Broadcast")

async def send_admin_new_chat_alert(user_email: str, first_message: str):
    body = f"""
    <h3 style="color: #D4AF37;">New Live Chat Initiated</h3>
    <p><strong>User:</strong> {user_email}</p>
    <p><strong>Message:</strong> "{first_message}"</p>
    <br>
    <a href="https://dunexmarkets.com/admin/chat" style="background-color: #D4AF37; color: #05050A; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: bold;">Reply in Dashboard</a>
    """
    await asyncio.to_thread(_send_api_email_sync, ADMIN_ALERT_EMAIL, f"New Chat from {user_email}", body, "Live Chat Alert")

async def send_rejection_email(user_email: str, user_name: str, amount: float, reason: str):
    body = f"""
    <h2 style="color: #D4AF37; margin-bottom: 20px;">Withdrawal Update</h2>
    <p style="font-size: 16px; color: #E2E8F4;">Hello {user_name},</p>
    <p style="font-size: 15px; color: #8E8E93; line-height: 1.6;">
        Your recent withdrawal request for <strong style="color: #FFFFFF;">${abs(amount):,.2f}</strong> could not be processed at this time.
    </p>
    <p style="font-size: 14px; color: #8E8E93; margin-top: 24px; text-transform: uppercase; letter-spacing: 1px;">
        Reason from Administrator:
    </p>
    <blockquote style="border-left: 4px solid #D4AF37; padding: 15px; background-color: #12121A; margin: 0 0 24px 0; color: #E2E8F4; font-style: italic; border-radius: 0 8px 8px 0;">
        "{reason}"
    </blockquote>
    <p style="font-size: 14px; color: #8E8E93; line-height: 1.6;">
        Please address this issue and submit a new request, or contact our Live Support directly from your dashboard if you need assistance.
    </p>
    """
    await asyncio.to_thread(_send_api_email_sync, user_email, "Important Update Regarding Your Withdrawal", body, "Withdrawal Rejection")