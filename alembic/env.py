import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from alembic import context
from dotenv import load_dotenv

# 🛑 IMPORT EVERY SINGLE MODEL HERE SO ALEMBIC SEES THEM ALL
from app.domains.users.models import Base, User
from app.domains.wallet.models import Wallet, LedgerTransaction, PaymentMethod
from app.domains.trade.models import SubWallet, TradeExecution
from app.domains.chat.models import ChatMessage, SupportTicket

# Import the pre-configured engine
from app.db.session import engine as fixed_engine 

# Load environment variables
load_dotenv()

config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Alembic will now scan Base.metadata knowing about ALL the tables above
target_metadata = Base.metadata

# ... (Keep the rest of your do_run_migrations and run_migrations_online code exactly the same below this)

def do_run_migrations(connection):
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        compare_type=True, # Detects changes in column types
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    """Run migrations in 'online' mode asynchronously."""
    
    # 2. FORCE Alembic to use our custom SSL-fixed engine
    connectable = fixed_engine

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

# Run the async execution
if context.is_offline_mode():
    print("Offline mode is not supported with this async setup.")
else:
    asyncio.run(run_migrations_online())