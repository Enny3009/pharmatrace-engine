# app/workers/celery_app.py
from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue
from app.core.config import settings

# Declare Dead-Letter Exchange (DLX)
dlx = Exchange("pharma.dlx", type="direct")
default_exchange = Exchange("pharma.direct", type="direct")

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
    task_queues=[
        Queue(
            "q.pharma.outbox",
            exchange=default_exchange,
            routing_key="outbox",
            queue_arguments={
                "x-dead-letter-exchange": "pharma.dlx",
                "x-dead-letter-routing-key": "dlx",
            },
        ),
        Queue(
            "q.pharma.compliance",
            exchange=default_exchange,
            routing_key="compliance",
            queue_arguments={
                "x-dead-letter-exchange": "pharma.dlx",
                "x-dead-letter-routing-key": "dlx",
            },
        ),
        Queue("q.pharma.dlx", exchange=dlx, routing_key="dlx"),
    ],
    task_default_queue="q.pharma.outbox",
    task_routes={
        "app.workers.outbox_tasks.*": {"queue": "q.pharma.outbox"},
        "app.workers.compliance_tasks.*": {"queue": "q.pharma.compliance"},
    },
    beat_schedule={
        "poll-transactional-outbox-every-10s": {
            "task": "app.workers.outbox_tasks.relay_outbox_events",
            "schedule": 10.0,
        },
        "sweep-expiring-batches-every-hour": {
            "task": "app.workers.compliance_tasks.sweep_expiring_batches",
            "schedule": crontab(minute=30),
        },
        "verify-audit-chain-every-hour": {
            "task": "app.workers.compliance_tasks.sweep_audit_integrity",
            "schedule": crontab(minute=0),
        },
    },
)