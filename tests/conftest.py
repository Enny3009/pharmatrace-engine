from collections.abc import AsyncGenerator
import uuid
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import hash_password
from app.main import app
from app.models.organization import Organization
from app.models.user import Role, User

test_engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    echo=False,
    poolclass=NullPool,
)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    test_redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    async def override_get_redis():
        return test_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver/api/v1") as ac:
        yield ac

    app.dependency_overrides.clear()
    await test_redis.aclose()


@pytest_asyncio.fixture
async def test_auth_context():
    """Provisions a distinct test organization, admin, and QA officer with explicit UUIDs."""
    org_id = uuid.uuid4()
    admin_role_id = uuid.uuid4()
    qa_role_id = uuid.uuid4()
    admin_user_id = uuid.uuid4()
    qa_user_id = uuid.uuid4()

    org = Organization(
        id=org_id,
        name=f"Test Pharma Corp {org_id.hex[:6]}",
        legal_name="Test Pharma Corporation Inc.",
        license_number=f"FDA-TST-{org_id.hex[:6]}",
        genesis_hash=f"test_genesis_{org_id.hex}",
    )

    role_admin = Role(
        id=admin_role_id,
        organization_id=org_id,
        name="ADMIN",
        description="Administrator",
    )
    role_qa = Role(
        id=qa_role_id,
        organization_id=org_id,
        name="QA_OFFICER",
        description="Quality Officer",
    )

    pwd_hash = hash_password("SecurePassword2026!")
    admin_user = User(
        id=admin_user_id,
        organization_id=org_id,
        role_id=admin_role_id,
        email=f"admin_{org_id.hex[:6]}@testpharma.com",
        password_hash=pwd_hash,
        first_name="Admin",
        last_name="Tester",
        is_active=True,
    )
    qa_user = User(
        id=qa_user_id,
        organization_id=org_id,
        role_id=qa_role_id,
        email=f"qa_{org_id.hex[:6]}@testpharma.com",
        password_hash=pwd_hash,
        first_name="QA",
        last_name="Tester",
        is_active=True,
    )

    async with TestingSessionLocal() as session:
        session.add_all([org, role_admin, role_qa, admin_user, qa_user])
        await session.commit()

    return {
        "organization_id": org_id,
        "admin_email": admin_user.email,
        "admin_id": admin_user.id,
        "qa_email": qa_user.email,
        "qa_id": qa_user.id,
        "password": "SecurePassword2026!",
    }