import os
import resend
from celery.exceptions import MaxRetriesExceededError

# THE FIX: Correctly targeting the celery.py file!
from app.workers.celery import celery_app 

resend.api_key = os.getenv("RESEND_API_KEY")

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_welcome_email(self, email: str, full_name: str):
    """
    Asynchronously dispatches a welcome email via Resend.
    If the Resend API is temporarily down, Celery will retry up to 3 times.
    """
    try:
        html_content = f"""
        <h2>Welcome to Dunex Markets, {full_name or 'Trader'}!</h2>
        <p>Your account is successfully registered. You can now access the trading dashboard.</p>
        <p>Please complete your KYC to unlock withdrawals.</p>
        """

        response = resend.Emails.send({
            "from": "Dunex Support <onboarding@yourdomain.com>", # Update with your verified domain later
            "to": [email],
            "subject": "Welcome to Dunex Markets",
            "html": html_content
        })

        return {"status": "success", "resend_id": response.get("id")}
    
    except Exception as exc:
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            print(f"Failed to send welcome email to {email} after 3 attempts.")
            return {"status": "failed", "error": str(exc)}