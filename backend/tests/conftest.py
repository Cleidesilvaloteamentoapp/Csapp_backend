"""Shared test fixtures."""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.company import Company
from app.models.enums import CompanyStatus, UserRole
from app.models.user import Profile

# Use a test database URL (append _test to the DB name)
TEST_DATABASE_URL = settings.DATABASE_URL.rsplit("/", 1)[0] + "/csapp_test"

engine_test = create_async_engine(TEST_DATABASE_URL, echo=False)
async_session_test = async_sessionmaker(engine_test, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables before tests and drop after."""
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional test database session."""
    async with async_session_test() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with overridden DB dependency."""

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Pre-built entities
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_company(db_session: AsyncSession) -> Company:
    """Create a test company."""
    company = Company(
        id=uuid.uuid4(),
        name="Test Company",
        slug="test-company",
        status=CompanyStatus.ACTIVE,
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def test_company_b(db_session: AsyncSession) -> Company:
    """Create a second test company for isolation tests."""
    company = Company(
        id=uuid.uuid4(),
        name="Other Company",
        slug="other-company",
        status=CompanyStatus.ACTIVE,
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def super_admin(db_session: AsyncSession, test_company: Company) -> Profile:
    """Create a super_admin user."""
    profile = Profile(
        id=uuid.uuid4(),
        company_id=test_company.id,
        role=UserRole.SUPER_ADMIN,
        full_name="Super Admin",
        email="superadmin@test.com",
        cpf_cnpj="00000000000",
        phone="11999990000",
        hashed_password=hash_password("TestPass123!"),
    )
    db_session.add(profile)
    await db_session.flush()
    return profile


@pytest_asyncio.fixture
async def company_admin(db_session: AsyncSession, test_company: Company) -> Profile:
    """Create a company_admin user."""
    profile = Profile(
        id=uuid.uuid4(),
        company_id=test_company.id,
        role=UserRole.COMPANY_ADMIN,
        full_name="Company Admin",
        email="admin@test.com",
        cpf_cnpj="11111111111",
        phone="11999991111",
        hashed_password=hash_password("TestPass123!"),
    )
    db_session.add(profile)
    await db_session.flush()
    return profile


@pytest_asyncio.fixture
async def company_admin_b(db_session: AsyncSession, test_company_b: Company) -> Profile:
    """Create an admin for the second company (isolation tests)."""
    profile = Profile(
        id=uuid.uuid4(),
        company_id=test_company_b.id,
        role=UserRole.COMPANY_ADMIN,
        full_name="Other Admin",
        email="otheradmin@test.com",
        cpf_cnpj="22222222222",
        phone="11999992222",
        hashed_password=hash_password("TestPass123!"),
    )
    db_session.add(profile)
    await db_session.flush()
    return profile


@pytest_asyncio.fixture
async def client_user(db_session: AsyncSession, test_company: Company) -> Profile:
    """Create a client-role user."""
    profile = Profile(
        id=uuid.uuid4(),
        company_id=test_company.id,
        role=UserRole.CLIENT,
        full_name="Client User",
        email="client@test.com",
        cpf_cnpj="33333333333",
        phone="11999993333",
        hashed_password=hash_password("TestPass123!"),
    )
    db_session.add(profile)
    await db_session.flush()
    return profile


# ---------------------------------------------------------------------------
# Auth header helpers
# ---------------------------------------------------------------------------


def auth_headers(profile: Profile) -> dict[str, str]:
    """Generate Authorization headers from a profile."""
    token = create_access_token(
        user_id=str(profile.id),
        company_id=str(profile.company_id),
        role=profile.role.value,
    )
    return {"Authorization": f"Bearer {token}"}
