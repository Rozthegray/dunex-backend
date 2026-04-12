import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 🚨 Zoho Credentials from your .env
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.zoho.com")
# 🚨 CRITICAL FIX: Defaulted to 465 to match the SMTP_SSL engine!
SMTP_PORT = int(os.getenv("SMTP_PORT", 465)) 
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "Dunex Support <support@dunexmarkets.com>")
ADMIN_ALERT_EMAIL = os.getenv("ADMIN_ALERT_EMAIL", "admin@dunexmarkets.com")

LOGO_URL = "https://res.cloudinary.com/dkpicfvgv/image/upload/icon_oo2lbm.png"

def _send_zoho_email(to_email: str, subject: str, raw_body: str, category: str):
    """Internal helper to dispatch branded emails securely via Zoho."""
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        print(f"[WARNING] Email skipped for {to_email}. Zoho credentials missing.")
        return

    msg = MIMEMultipart()
    msg['From'] = FROM_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject
    
    # 🚨 Master HTML Wrapper for ALL emails
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

    msg.attach(MIMEText(html_template, 'html'))

    try:
        # 🚨 CRITICAL FIX: Use SMTP_SSL for Port 465 on Render
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            # Do NOT add server.starttls() here. Port 465 encrypts automatically.
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"[ZOHO SMTP] {category} successfully sent to {to_email}")
    except Exception as e:
        print(f"[ZOHO ERROR] {category} Dispatch Failed: {e}")

# ---------------------------------------------------------
# Public Email Functions
# ---------------------------------------------------------

def send_onboarding_email(to_email: str, full_name: str):
    body = f"Welcome to Dunex Markets, {full_name}. Please complete your KYC to unlock full trading capabilities."
    _send_zoho_email(to_email, "Welcome to Dunex Markets", body, "Onboarding")

def send_password_reset_email(to_email: str, reset_code: str):
    body = f"Your password reset code is: <strong>{reset_code}</strong>. This code expires in 15 minutes."
    _send_zoho_email(to_email, "Dunex Markets: Password Reset", body, "Password Reset")

def send_admin_broadcast_email(to_email: str, subject: str, message_body: str):
    _send_zoho_email(to_email, subject, message_body, "Admin Broadcast")

def send_admin_new_chat_alert(user_email: str, first_message: str):
    """Fires an email to the admin when a user initiates a live chat."""
    body = f"""
    <h3 style="color: #D4AF37;">New Live Chat Initiated</h3>
    <p><strong>User:</strong> {user_email}</p>
    <p><strong>Message:</strong> "{first_message}"</p>
    <br>
    <a href="https://dunexmarkets.com/admin/chat" style="background-color: #D4AF37; color: #05050A; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: bold;">Reply in Dashboard</a>
    """
    _send_zoho_email(ADMIN_ALERT_EMAIL, f"New Chat from {user_email}", body, "Live Chat Alert")
