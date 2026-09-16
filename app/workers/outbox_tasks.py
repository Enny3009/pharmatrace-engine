import asyncio
from datetime import datetime, timezone
from kombu import Connection, Exchange, Producer
from sqlalchemy import select
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.outbox import OutboxEvent
from app.workers.celery_app import celery_app


async def _relay_outbox() -> int:
    relayed_count = 0
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        # Polling with row-level lock skipping locked rows (High-throughput parallel safety)
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == "PENDING")
            .order_by(OutboxEvent.created_at.asc())
            .limit(50)
            .with_for_update(skip_locked=True)
        )
        events = (await session.execute(stmt)).scalars().all()

        if not events:
            return 0

        # Direct Kombu AMQP Exchange Publisher
        exchange = Exchange("pharma.events", type="topic", durable=True)
        with Connection(settings.CELERY_BROKER_URL) as conn:
            with Producer(conn) as producer:
                for ev in events:
                    try:
                        routing_key = f"event.{ev.event_type.lower()}"
                        producer.publish(
                            ev.payload,
                            exchange=exchange,
                            routing_key=routing_key,
                            declare=[exchange],
                            headers={"org_id": str(ev.organization_id)},
                        )
                        ev.status = "PROCESSED"
                        ev.processed_at = now
                        relayed_count += 1
                    except Exception:
                        ev.attempts += 1
                        if ev.attempts >= 5:
                            ev.status = "FAILED"

        await session.commit()

    return relayed_count


@celery_app.task(name="app.workers.outbox_tasks.relay_outbox_events")
def relay_outbox_events() -> int:
    return asyncio.run(_relay_outbox())