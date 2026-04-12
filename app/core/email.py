import os
import requests

# 🚨 Using Mailtrap HTTP API to bypass Render's SMTP Firewall
MAILTRAP_API_TOKEN = os.getenv("MAILTRAP_API_TOKEN", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "support@dunexmarkets.com")
ADMIN_ALERT_EMAIL = os.getenv("ADMIN_ALERT_EMAIL", "rozthegrey@gmail.com")

LOGO_URL = "https://res.cloudinary.com/dkpicfvgv/image/upload/icon_oo2lbm.png"

def _send_api_email(to_email: str, subject: str, raw_body: str, category: str):
    """Internal helper to dispatch emails via HTTPS API (Port 443)"""
    if not MAILTRAP_API_TOKEN:
        print(f"[WARNING] Email skipped for {to_email}. API Token missing.")
        return

    # Master HTML Wrapper
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

    # Mailtrap's official API Endpoint
    url = "https://send.api.mailtrap.io/api/send"
    
    headers = {
        "Authorization": f"Bearer {MAILTRAP_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "from": {"email": FROM_EMAIL, "name": "Dunex Support"},
        "to": [{"email": to_email}],
        "subject": subject,
        "html": html_template,
        "category": category
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"[HTTP EMAIL] {category} successfully sent to {to_email}")
        else:
            print(f"[HTTP ERROR] {category} Failed: {response.text}")
    except Exception as e:
        print(f"[HTTP CRASH] {category} Dispatch Failed: {e}")

# ---------------------------------------------------------
# Public Email Functions 
# ---------------------------------------------------------

def send_onboarding_email(to_email: str, full_name: str):
    body = f"""
    <h2 style="color: #D4AF37; margin-top: 0;">Welcome to Dunex Markets, {full_name}.</h2>
    <p>Your secure trading vault has been successfully established. We are thrilled to have you join our platform.</p>
    <p>To unlock your full portfolio capabilities—including  live trading, and withdrawals—please complete your brief identity verification (KYC) within your dashboard.</p>
    <br>
    <a href="https://www.dunexmarkets.com/dashboard" style="background-color: #D4AF37; color: #05050A; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Access Your Dashboard</a>
    <br><br>
    <p>If you need any assistance getting started, our support team is available 24/7 via the live chat in your account.</p>
    <p>Best regards,<br><strong>The Dunex Markets Team</strong></p>
    """
    _send_api_email(to_email, "Dunex Markets: Vault Established & KYC Required", body, "Onboarding")

def send_password_reset_email(to_email: str, reset_code: str):
    # Note: Update the href URL below if your frontend reset route is different!
    reset_link = "https://www.dunexmarkets.com/reset-password"
    
    body = f"""
    <h2 style="color: #D4AF37; margin-top: 0;">Vault Recovery Initiated</h2>
    <p>We received a request to reset the passphrase for your Dunex Markets account.</p>
    
    <p>Your secure 6-digit recovery code is:</p>
    <div style="background-color: #1f2937; padding: 20px; border-radius: 8px; text-align: center; margin: 25px 0; border: 1px solid #374151;">
        <span style="font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #D4AF37;">{reset_code}</span>
    </div>
    
    <p>This code is valid for the next <strong>15 minutes</strong>.</p>
    <br>
    <a href="{reset_link}" style="background-color: #D4AF37; color: #05050A; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Enter Recovery Code</a>
    <br><br>
    <p style="font-size: 14px; color: #9ca3af; border-top: 1px solid #1f2937; padding-top: 20px; margin-top: 20px;">
        <strong>Security Notice:</strong> If you did not request a password reset, please ignore this email or contact our support team immediately. Your vault remains fully secured.
    </p>
    """
    
    _send_api_email(to_email, "Dunex Markets: Vault Recovery Code", body, "Password Reset")
def send_admin_broadcast_email(to_email: str, subject: str, message_body: str):
    _send_api_email(to_email, subject, message_body, "Admin Broadcast")

def send_admin_new_chat_alert(user_email: str, first_message: str):
    body = f"""
    <h3 style="color: #D4AF37;">New Live Chat Initiated</h3>
    <p><strong>User:</strong> {user_email}</p>
    <p><strong>Message:</strong> "{first_message}"</p>
    <br>
    <a href="https://dunexmarkets.com/admin/chat" style="background-color: #D4AF37; color: #05050A; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: bold;">Reply in Dashboard</a>
    """
    _send_api_email(ADMIN_ALERT_EMAIL, f"New Chat from {user_email}", body, "Live Chat Alert")
