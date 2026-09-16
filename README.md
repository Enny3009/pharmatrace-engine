# PharmaTrace Enterprise Ledger

PharmaTrace is an FDA 21 CFR Part 11 compliant pharmaceutical supply chain and inventory ledger. Designed for biopharmaceutical manufacturers and cGMP distribution networks, this backend engine guarantees strict data integrity, handles concurrent stock allocations, and maintains an immutable cryptographic audit trail.

## Core Architecture

This platform diverges from standard CRUD applications by implementing enterprise-grade state management, transactionality, and asynchronous background processing.

* **Primary Runtime:** Python 3.12+ / FastAPI
* **ACID Ledger:** PostgreSQL 16
* **Concurrency & Caching:** Redis 7.2
* **Asynchronous Workers:** Celery 5.4 / RabbitMQ 3.13
* **WORM Storage:** MinIO (S3-compatible)

## Technical Highlights

### 1. Two-Tier Concurrency Lock Engine
Pharmaceutical inventory operations cannot tolerate race conditions. Stock issuance implements a two-tier locking mechanism to completely eliminate negative balance anomalies under high-throughput concurrent requests.
* **Tier 1:** Distributed `SET NX EX` locks via Redis serialize incoming worker requests.
* **Tier 2:** PostgreSQL `SELECT ... FOR UPDATE` row-level locks guarantee atomic balance deduction.
* **Tier 3:** Optimistic concurrency counters reject stale states.

### 2. FDA 21 CFR Part 11 Electronic Signatures & Cryptographic Audit Ledger (ALCOA+)
Every critical operation requires dual-factor re-authentication. State mutations are appended to an immutable `audit_ledger`.
* **Hash Chaining:** Each row computes an SHA-256 digest binding the snapshot payload, the user, the timestamp, and the `previous_hash`.
* **Tamper Detection:** A dedicated integrity verification endpoint recalculates the entire chain from the organization's Genesis Hash to detect direct database manipulation.
* **Separation of Duties (SoD):** Hardcoded RBAC constraints prevent self-approval (e.g., a user cannot approve their own inventory adjustment or purchase order).

### 3. Transactional Outbox Pattern
Domain events are guaranteed at-least-once delivery to the RabbitMQ broker without dual-write inconsistencies.
* Events are committed to an `outbox_events` table within the same ACID PostgreSQL transaction as the primary mutation.
* A Celery polling worker uses `SELECT ... FOR UPDATE SKIP LOCKED` to efficiently relay events to downstream subscribers.

### 4. Idempotency & Resiliency
All mutation endpoints (`POST`, `PATCH`) enforce idempotency.
* Requests supply an `Idempotency-Key` header.
* Responses are cached in PostgreSQL/Redis. Duplicate requests bypass execution and return the cached `response_body` and `status_code`, preventing double-charging or duplicate inventory deduction during network retries.

### 5. Automated Compliance & FEFO Operations
* **FEFO Allocation Engine:** Queries resolve available stock dynamically sorted by nearest `expiry_date` ascending and `quantity_available` descending, bypassing quarantined or recalled lots.
* **Cold-Chain Excursions:** IoT temperature ingestions automatically quarantine physical storage locations and trigger compliance incidents if thresholds are breached for >15 minutes or exceed a critical delta.
* **Celery Beat Sweeps:** Scheduled background workers execute 30-day expiry sweeps, notifying QA officers of approaching deadlines.

## Local Development Setup

1. **Clone and configure the environment:**
   ```bash
   git clone [https://github.com/yourusername/pharmatrace-engine.git](https://github.com/yourusername/pharmatrace-engine.git)
   cd pharmatrace-engine
   cp .env.example .env