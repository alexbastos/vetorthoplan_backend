"""End-to-end JWT, organization isolation, and idempotency checks against PostgreSQL.

Set VETORTHOPLAN_TEST_DATABASE_URL to a dedicated test database. Every test creates
and drops a uniquely named schema and never truncates or mutates public tables.
"""

import os
from base64 import b64encode
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from vetorthoplan.api import dependencies
from vetorthoplan.api.dependencies import get_database_session
from vetorthoplan.bootstrap import create_app
from vetorthoplan.config.settings import Settings, get_settings
from vetorthoplan.infrastructure.database.models import (
    AuthOrganizationMappingModel,
    AuthSubjectMappingModel,
    Base,
    CaseIdempotencyModel,
    CaseModel,
)

ISSUER = "https://identity.integration.test"
AUDIENCE = "vetorthoplan-api"
SUBJECT = f"integration-user-{uuid4()}"
ORGANIZATION_A = f"integration-org-a-{uuid4()}"
ORGANIZATION_B = f"integration-org-b-{uuid4()}"


class JwksProviderStub:
    def __init__(self, public_key: str) -> None:
        self.public_key = public_key

    async def get_key(self, _kid: str) -> str:
        return self.public_key


@pytest_asyncio.fixture
async def integration_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, bytes]]:
    database_url = os.environ.get("VETORTHOPLAN_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VETORTHOPLAN_TEST_DATABASE_URL is not configured")
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("VETORTHOPLAN_TEST_DATABASE_URL must use postgresql+asyncpg")

    schema = f"vet_it_{uuid4().hex}"
    admin_engine = create_async_engine(database_url, pool_pre_ping=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = (
        "-----BEGIN PUBLIC KEY-----\n"
        + b64encode(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        ).decode("ascii")
        + "\n-----END PUBLIC KEY-----"
    )

    try:
        async with admin_engine.begin() as connection:
            await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')

        engine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"server_settings": {"search_path": schema}},
        )
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=[
                        AuthSubjectMappingModel.__table__,
                        AuthOrganizationMappingModel.__table__,
                        CaseModel.__table__,
                        CaseIdempotencyModel.__table__,
                    ],
                )
            )
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async def database_session():
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        settings = Settings(
            app_env="test",
            identity_mode="jwt",
            jwt_issuer=ISSUER,
            jwt_audience=AUDIENCE,
            jwks_url="https://identity.integration.test/.well-known/jwks.json",
        )
        monkeypatch.setattr(
            dependencies,
            "_get_jwks_provider",
            lambda *_args: JwksProviderStub(public_key),
        )
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_database_session] = database_session

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client, private_pem

        await engine.dispose()
    finally:
        async with admin_engine.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin_engine.dispose()


def _organization_token(private_key: bytes, organization_id: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": ISSUER,
            "sub": SUBJECT,
            "aud": AUDIENCE,
            "exp": now.timestamp() + 300,
            "iat": now.timestamp(),
            "jti": str(uuid4()),
            "sid": str(uuid4()),
            "tokenUse": "access",
            "org_id": organization_id,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "integration-kid"},
    )


@pytest.mark.asyncio
async def test_valid_jwt_scopes_idempotency_to_organization_and_actor(
    integration_client: tuple[AsyncClient, bytes],
) -> None:
    client, private_key = integration_client
    request_headers_a = {
        "Authorization": f"Bearer {_organization_token(private_key, ORGANIZATION_A)}",
        "Idempotency-Key": "same-key-across-organizations",
    }
    request_headers_b = {
        "Authorization": f"Bearer {_organization_token(private_key, ORGANIZATION_B)}",
        "Idempotency-Key": "same-key-across-organizations",
    }
    request_body = {"title": "Caso de teste", "animal_name": "Paciente sintético", "species": "Canina"}

    first = await client.post("/api/v1/cases", headers=request_headers_a, json=request_body)
    replay = await client.post(
        "/api/v1/cases",
        headers={
            **request_headers_a,
            "Authorization": f"Bearer {_organization_token(private_key, ORGANIZATION_A)}",
        },
        json=request_body,
    )
    other_organization = await client.post("/api/v1/cases", headers=request_headers_b, json=request_body)
    changed_payload = await client.post(
        "/api/v1/cases",
        headers={
            **request_headers_a,
            "Authorization": f"Bearer {_organization_token(private_key, ORGANIZATION_A)}",
        },
        json={**request_body, "title": "Payload diferente"},
    )

    assert first.status_code == replay.status_code == other_organization.status_code == 201
    assert first.json()["id"] == replay.json()["id"]
    assert other_organization.json()["id"] != first.json()["id"]
    assert other_organization.json()["tenant_id"] != first.json()["tenant_id"]
    assert changed_payload.status_code == 409
    assert changed_payload.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

    list_a = await client.get(
        "/api/v1/cases",
        headers={"Authorization": f"Bearer {_organization_token(private_key, ORGANIZATION_A)}"},
    )
    list_b = await client.get(
        "/api/v1/cases",
        headers={"Authorization": f"Bearer {_organization_token(private_key, ORGANIZATION_B)}"},
    )
    assert [item["id"] for item in list_a.json()["items"]] == [first.json()["id"]]
    assert [item["id"] for item in list_b.json()["items"]] == [other_organization.json()["id"]]
