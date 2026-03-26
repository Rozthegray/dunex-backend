import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# We use RabbitMQ for absolute message durability in financial applications
RABBITMQ_URL = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")

celery_app = Celery(
    "fintech_worker",
    broker=RABBITMQ_URL,
    include=["app.workers.email_tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Lagos",
    enable_utc=True,
    # Crucial for fintech: Tasks must be explicitly acknowledged after successful execution
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)