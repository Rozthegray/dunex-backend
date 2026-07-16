import os
import httpx

# Render Environment Variables
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")  # e.g., "whatsapp:+14155238886"
ADMIN_WHATSAPP_NUMBER = os.getenv("ADMIN_WHATSAPP_NUMBER")    # e.g., "whatsapp:+2348000000000"


async def dispatch_whatsapp_alert(message: str):
    """
    Fires an alert to the Admin via Twilio WhatsApp API.
    Awaits execution to guarantee delivery (or at least a logged failure).
    """
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER, ADMIN_WHATSAPP_NUMBER]):
        print("🚨 WhatsApp env vars missing. Alert skipped.")
        return

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"

    payload = {
        "From": TWILIO_WHATSAPP_NUMBER,
        "To": ADMIN_WHATSAPP_NUMBER,
        "Body": message,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                data=payload,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                timeout=5.0,
            )

            if response.status_code not in (200, 201):
                print(f"🚨 WhatsApp Rejected Alert: {response.status_code} {response.text}")
            else:
                print("✅ WhatsApp Alert Dispatched Successfully.")

        except httpx.RequestError as e:
            print(f"🚨 WhatsApp Network Failure: {e}")