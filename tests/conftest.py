import pytest

pytest_plugins = ("pytest_asyncio.plugin",)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import app.database as database_module
from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Background tasks (e.g. the recommendation job runner) can't use
    # Depends(get_db) since they run outside a request; they import
    # SessionLocal directly from app.database. Patch that module attribute
    # so background work also binds to this test's in-memory engine.
    original_session_local = database_module.SessionLocal
    database_module.SessionLocal = TestingSession

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    database_module.SessionLocal = original_session_local
