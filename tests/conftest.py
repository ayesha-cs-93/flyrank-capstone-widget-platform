import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.models import Tenant
from app.auth import hash_key

TEST_DB_URL = "sqlite:///:memory:"

# StaticPool keeps a single shared connection across threads -- required for
# in-memory sqlite, since TestClient runs requests in a worker thread and the
# default pool gives each thread a brand-new (table-less) in-memory db.
engine = create_engine(
    TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # slowapi's Limiter keeps counters in a process-wide store keyed by
    # client IP. TestClient always hits from "testclient", so without a
    # reset here, quota used by one test carries into the next and causes
    # unrelated tests to see 429s.
    app.state.limiter.reset()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def tenant_with_key(db_session):
    raw_key = "test-api-key-123"
    tenant = Tenant(email="owner@example.com", api_key_hash=hash_key(raw_key))
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant, raw_key
