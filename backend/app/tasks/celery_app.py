
"""Celery application configuration."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery = Celery(
    "csapp",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.invoice_tasks",
        "app.tasks.notification_tasks",
        "app.tasks.adjustment_tasks",
        "app.tasks.batch_tasks",
    ],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=60,
    task_max_retries=3,
    broker_connection_retry_on_startup=True,
)

# Beat schedule – periodic tasks
celery.conf.beat_schedule = {
    "check-overdue-invoices-daily": {
        "task": "app.tasks.invoice_tasks.check_overdue_invoices",
        "schedule": crontab(hour=6, minute=0),  # 06:00 daily
    },
    "generate-monthly-invoices": {
        "task": "app.tasks.invoice_tasks.generate_monthly_invoices",
        "schedule": crontab(day_of_month=1, hour=3, minute=0),  # 1st of month, 03:00
    },
    "send-payment-reminders": {
        "task": "app.tasks.notification_tasks.send_payment_reminders",
        "schedule": crontab(hour=9, minute=0),  # 09:00 daily
    },
    "apply-annual-adjustments": {
        "task": "app.tasks.adjustment_tasks.apply_annual_adjustments",
        "schedule": crontab(day_of_month=1, hour=2, minute=0),  # 1st of month, 02:00
    },
    "send-admin-alerts-daily": {
        "task": "app.tasks.adjustment_tasks.send_admin_alerts",
        "schedule": crontab(hour=7, minute=30),  # 07:30 daily
    },
    "send-whatsapp-reminders": {
        "task": "app.tasks.notification_tasks.send_whatsapp_reminders",
        "schedule": crontab(hour=9, minute=30),  # 09:30 daily
    },
    "overdue-escalation-daily": {
        "task": "app.tasks.notification_tasks.overdue_escalation",
        "schedule": crontab(hour=8, minute=0),  # 08:00 daily
    },
    "check-cycle-completions-daily": {
        "task": "app.tasks.notification_tasks.check_cycle_completions",
        "schedule": crontab(hour=4, minute=0),  # 04:00 daily
    },
}
