"""Validate VetOrthoPlan's JWT identity integration before deployment."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import jwt
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from vetorthoplan.config.settings import Settings
from vetorthoplan.infrastructure.authentication.jwks import (
    JWKSKeyProvider,
    JWKSUnavailableError,
    SigningKeyNotFoundError,
)


class PreflightError(Exception):
    """A safe-to-display integration check failure."""


async def check_token(settings: Settings, token: str) -> None:
    assert settings.jwks_url is not None
    assert settings.jwt_issuer is not None
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise PreflightError("VET_PREFLIGHT_TOKEN não é um JWT válido.") from exc

    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise PreflightError("O token deve usar RS256 e conter kid no cabeçalho.")

    provider = JWKSKeyProvider(
        settings.jwks_url,
        settings.jwks_cache_seconds,
        settings.jwks_timeout_seconds,
    )

    try:
        signing_key = await provider.get_key(header["kid"])
    except JWKSUnavailableError as exc:
        raise PreflightError("Não foi possível consultar o JWKS configurado.") from exc
    except SigningKeyNotFoundError as exc:
        raise PreflightError("O JWKS não contém a chave kid do token.") from exc
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            key=signing_key,
            algorithms=["RS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            leeway=settings.jwt_clock_skew_seconds,
            options={
                "require": [
                    "iss",
                    "sub",
                    "aud",
                    "exp",
                    "iat",
                    "jti",
                    "sid",
                    "tokenUse",
                    "org_id",
                ]
            },
        )
    except (jwt.InvalidTokenError, jwt.PyJWKError, TypeError, ValueError, KeyError) as exc:
        raise PreflightError(
            "Token rejeitado: verifique assinatura, issuer, audiência, validade e claims obrigatórios."
        ) from exc

    if claims.get("aud") != settings.jwt_audience:
        raise PreflightError("A audiência do token não corresponde a JWT_AUDIENCE.")
    if claims.get("tokenUse") != "access":
        raise PreflightError("O token não é do tipo access.")
    for name in ("sub", "sid", "jti", "org_id"):
        value = claims.get(name)
        if not isinstance(value, str) or not value.strip():
            raise PreflightError(f"O token não contém um {name} válido.")
    if len(claims["sub"]) > 255 or len(claims["org_id"]) > 255:
        raise PreflightError("sub ou org_id excede o tamanho aceito pelo Vet.")


async def check_database(settings: Settings) -> None:
    alembic_config = Config("alembic.ini")
    expected_heads = set(ScriptDirectory.from_config(alembic_config).get_heads())
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            db_heads = set(
                (await connection.execute(text("SELECT version_num FROM alembic_version")))
                .scalars()
                .all()
            )
            if db_heads != expected_heads:
                expected = ", ".join(sorted(expected_heads)) or "nenhuma"
                actual = ", ".join(sorted(db_heads)) or "nenhuma"
                raise PreflightError(
                    f"Banco fora da versão atual do Vet (atual: {actual}; esperado: {expected}). "
                    "Aplique alembic upgrade head no banco configurado para o Vet."
                )

            mappings_exist = await connection.scalar(
                text(
                    "SELECT to_regclass('auth_subject_mappings') IS NOT NULL "
                    "AND to_regclass('auth_organization_mappings') IS NOT NULL"
                )
            )
            if not mappings_exist:
                raise PreflightError("As tabelas de mapeamento de identidade não existem no banco do Vet.")
    except PreflightError:
        raise
    except Exception as exc:
        raise PreflightError("Não foi possível conectar ou conferir as migrations do banco do Vet.") from exc
    finally:
        await engine.dispose()


async def main() -> int:
    try:
        settings = Settings()
        if settings.identity_mode != "jwt":
            raise PreflightError("Configure IDENTITY_MODE=jwt para executar este preflight.")
        token = os.environ.get("VET_PREFLIGHT_TOKEN", "").strip()
        if not token:
            raise PreflightError(
                "Defina VET_PREFLIGHT_TOKEN com um access token válido da organização para o Vet."
            )

        await check_token(settings, token)
        print("[OK] Configuração JWT e token de organização válidos.")
        await check_database(settings)
        print("[OK] Banco conectado, migrations atualizadas e tabelas de mapeamento disponíveis.")
        print("Preflight de identidade concluído.")
        return 0
    except (ValueError, PreflightError) as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
