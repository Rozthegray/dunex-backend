import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 🚨 Production Credentials (matching your Mailtrap settings)
SMTP_SERVER = os.getenv("SMTP_SERVER", "live.smtp.mailtrap.io")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "api") # Hardcoded to 'api' based on Mailtrap specs
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "6b9f657061b7a057dc0a94458e996164") # Put your Mailtrap API Token in Render!
FROM_EMAIL = os.getenv("FROM_EMAIL", "Dunex Support <support@dunexmarkets.com>")

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
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #05050a; color: #ffffff; padding: 40px; border-radius: 12px; border: 1px solid #1f2937;">
        <h2 style="color: #3b82f6; margin-bottom: 20px;">DUNEX MARKETS</h2>
        <h3 style="font-size: 24px; margin-bottom: 15px;">Welcome to Dunex Markets, {full_name}!</h3>
        
        <p style="color: #9ca3af; line-height: 1.6; font-size: 16px; margin-bottom: 25px;">
            Your new account has been successfully created. We are excited to provide you with a safe, secure, and easy way to manage your trades.
        </p>
        
        <div style="background-color: #111827; padding: 20px; border-radius: 8px; margin-bottom: 25px; border-left: 4px solid #3b82f6;">
            <p style="margin: 0; color: #e5e7eb; font-weight: bold; font-size: 16px;">Next Step: Please Verify Your Identity</p>
            <p style="margin: 10px 0 0 0; color: #9ca3af; font-size: 15px; line-height: 1.5;">
                To keep your money safe and allow you to make deposits, we need to do a quick identity check. Please log in to complete this simple step.
            </p>
        </div>
        
        <a href="https://app.dunexmarkets.com" style="display: inline-block; background-color: #2563eb; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px;">Log In to Your Account</a>
        
        <p style="color: #6b7280; font-size: 12px; margin-top: 40px; border-top: 1px solid #1f2937; padding-top: 20px;">
            © 2026 Dunex Markets Ltd. Secure and Private.
        </p>
    </div>
    """
    # 🚨 Updated the subject line to be friendly and clear
    _send_email(to_email, "Welcome to Dunex Markets - Please Verify Your Account", html, "Onboarding")

def send_password_reset_email(to_email: str, reset_code: str):
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #05050a; color: #ffffff; padding: 40px; border-radius: 12px; border: 1px solid #1f2937;">
        <h2 style="color: #3b82f6; margin-bottom: 20px;">DUNEX MARKETS</h2>
        <h3 style="font-size: 20px; margin-bottom: 15px;">Vault Recovery Initiated</h3>
        <p style="color: #9ca3af; line-height: 1.6; margin-bottom: 25px;">
            We received a request to reset the security credentials for your account. Use the authorization code below to proceed:
        </p>
        <div style="background-color: #111827; padding: 25px; text-align: center; border-radius: 8px; margin-bottom: 25px; letter-spacing: 4px; font-size: 32px; font-weight: bold; color: #60a5fa;">
            {reset_code}
        </div>
        <p style="color: #ef4444; font-size: 14px; margin-bottom: 25px;">
            If you did not initiate this request, please contact our support team immediately.
        </p>
        <p style="color: #6b7280; font-size: 12px; margin-top: 40px; border-top: 1px solid #1f2937; padding-top: 20px;">
            © 2026 Dunex Markets Ltd. Security Protocol.
        </p>
    </div>
    """
    _send_email(to_email, "DUNEX MARKETS: Vault Recovery Code", html, "Password Reset")

def send_admin_broadcast_email(to_email: str, subject: str, message_body: str):
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #05050a; color: #ffffff; padding: 40px; border-radius: 12px; border: 1px solid #1f2937;">
        <h2 style="color: #3b82f6; margin-bottom: 20px;">DUNEX MARKETS</h2>
        <h3 style="font-size: 18px; margin-bottom: 20px; border-bottom: 1px solid #1f2937; padding-bottom: 10px;">Official Network Update</h3>
        <p style="color: #d1d5db; line-height: 1.6; white-space: pre-line;">
            {message_body}
        </p>
        <p style="color: #6b7280; font-size: 12px; margin-top: 40px; border-top: 1px solid #1f2937; padding-top: 20px;">
            This is an automated administrative broadcast from Dunex Markets. 
        </p>
    </div>
    """
    _send_email(to_email, subject, html, "Broadcast")
