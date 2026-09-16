from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "pharmatrace_workers",
    broker=settings.CELERY_BROKER_URL,
    include=[
        "app.workers.outbox_tasks",
        "app.workers.compliance_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_queue="q.pharma.outbox",
    task_routes={
        "app.workers.outbox_tasks.*": {"queue": "q.pharma.outbox"},
        "app.workers.compliance_tasks.*": {"queue": "q.pharma.compliance"},
    },
    # Periodic Celery Beat Schedules
    beat_schedule={
        "poll-transactional-outbox-every-10s": {
            "task": "app.workers.outbox_tasks.relay_outbox_events",
            "schedule": 10.0,
        },
        "verify-audit-chain-every-hour": {
            "task": "app.workers.compliance_tasks.sweep_audit_integrity",
            "schedule": crontab(minute=0),
        },
    },
)