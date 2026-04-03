import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 🚨 Production Credentials pulled securely from the server environment
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.mailtrap.io") # e.g., live.smtp.mailtrap.io
SMTP_PORT = int(os.getenv("SMTP_PORT", 587)) # Standard secure SMTP port
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "DUNEX Support <support@dunexmarkets.com>")

def _send_email(to_email: str, subject: str, html_content: str, category: str):
    """Internal helper to dispatch emails securely."""
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        print(f"[WARNING] Email skipped for {to_email}. SMTP credentials missing.")
        return

    msg = MIMEMultipart()
    msg['From'] = FROM_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(html_content, 'html'))

    try:
        # 🚨 Live production servers REQUIRE the starttls() handshake!
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls() 
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"[SMTP] {category} transmission sent to {to_email}")
    except Exception as e:
        print(f"[SMTP ERROR] {category} Dispatch Failed: {e}")

def send_onboarding_email(to_email: str, full_name: str):
    html = f"""... (Paste your exact onboarding HTML template here) ..."""
    _send_email(to_email, "DUNEX MARKETS: Vault Established & KYC Required", html, "Onboarding")

def send_password_reset_email(to_email: str, reset_code: str):
    html = f"""... (Paste your exact password reset HTML template here) ..."""
    _send_email(to_email, "DUNEX MARKETS: Vault Recovery Code", html, "Password Reset")

def send_admin_broadcast_email(to_email: str, subject: str, message_body: str):
    html = f"""... (Paste your exact admin broadcast HTML template here) ..."""
    _send_email(to_email, subject, html, "Broadcast")
