import os
import asyncio
from datetime import datetime, timedelta
from celery import shared_task
from sqlalchemy import select
from app.db.session import SessionLocal
from app.domains.wallet.models import Wallet
from app.domains.users.models import User
from app.core.email import _send_api_email

# Celery task to sweep the database
@shared_task
def sweep_inactive_wallets():
    asyncio.run(_async_sweep_wallets())

async def _async_sweep_wallets():
    async with SessionLocal() as db:
        now = datetime.utcnow()
        
        query = select(Wallet, User).join(User, Wallet.user_id == User.id).where(Wallet.is_locked == False)
        result = await db.execute(query)
        active_accounts = result.all()

        for wallet, user in active_accounts:
            # If no deposit date exists (legacy users), skip or set to today
            if not wallet.last_deposit_date:
                wallet.last_deposit_date = now
                continue

            days_inactive = (now - wallet.last_deposit_date).days

            if days_inactive == 30:
                # 🚨 30-Day Warning Email
                body = "Your account has been inactive for 30 days. To prevent a lockdown and a $500 reactivation fine, please initiate a deposit within the next 30 days."
                _send_api_email(user.email, "Action Required: Account Inactivity Warning", body)
                
            elif days_inactive == 55:
                # 🚨 5-Day Countdown Warning
                body = "URGENT: Your account will be locked in 5 days due to 60 days of inactivity. Initiate a deposit immediately to avoid the $500 reactivation fine."
                _send_api_email(user.email, "URGENT: Account Lockdown Countdown", body)
                
            elif days_inactive >= 60:
                # 🚨 LOCKDOWN EXECUTION
                wallet.is_locked = True
                wallet.lockdown_fine_owed = 500.00
                
                body = "Your account has been locked due to 60 days of inactivity. To restore access and trading capabilities, you must pay the $500 reactivation fine from your dashboard."
                _send_api_email(user.email, "Account Locked - Reactivation Required", body)
                
        await db.commit()
