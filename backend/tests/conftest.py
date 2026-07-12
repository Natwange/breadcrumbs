"""Shared test fixtures for API tests."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.security import JWTVerifier
from app.db.session import get_db
from app.deps import get_verifier_dep
from app.main import app
from app.models import (
    Base,
    Organization,
    OrganizationMember,
    OrganizationSettings,
    UserProfile,
)

TEST_SECRET = "unit-test-secret-value"
TEST_SUPABASE_URL = "https://test.supabase.co"
TEST_AUDIENCE = "authenticated"
TEST_ISSUER = f"{TEST_SUPABASE_URL}/auth/v1"


def make_token(
    subject: str,
    email: str,
    *,
    secret: str = TEST_SECRET,
    audience: str = TEST_AUDIENCE,
    issuer: str = TEST_ISSUER,
    expires_in: int = 3600,
) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": subject,
        "email": email,
        "aud": audience,
        "iss": issuer,
        "role": "authenticated",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def auth_headers(token: str, organization_id: uuid.UUID | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if organization_id is not None:
        headers["X-Organization-Id"] = str(organization_id)
    return headers


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    test_settings = Settings(
        supabase_url=TEST_SUPABASE_URL,
        supabase_jwt_secret=TEST_SECRET,
        supabase_jwt_audience=TEST_AUDIENCE,
    )
    verifier = JWTVerifier(test_settings)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_verifier_dep] = lambda: verifier

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture()
def engine(session_factory: sessionmaker[Session]):
    """Expose the underlying engine for model-only tests."""
    return session_factory.kw["bind"]


@pytest.fixture()
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Database session for direct model tests (no HTTP layer)."""
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def seed_org_member(
    db: Session,
    *,
    role: str,
    email: str | None = None,
) -> tuple[UserProfile, Organization, OrganizationMember]:
    user_id = uuid.uuid4()
    user = UserProfile(id=user_id, email=email or f"{role}@example.com")
    org = Organization(name="Acme", slug=f"acme-{user_id.hex[:8]}")
    db.add_all([user, org])
    db.flush()

    member = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role=role,
        status="active",
    )
    settings = OrganizationSettings(organization_id=org.id)
    db.add_all([member, settings])
    db.commit()
    return user, org, member
