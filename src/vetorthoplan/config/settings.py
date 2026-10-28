from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from vetorthoplan.domain.planning.clinical_protocol import parse_clinical_protocol
from vetorthoplan.domain.planning.rotation_table import parse_rotation_table


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["local", "test", "development", "staging", "production"] = "local"
    identity_mode: Literal["local", "jwt"] = "local"
    jwt_issuer: str | None = None
    jwt_audience: str = "vetorthoplan-api"
    jwks_url: str | None = None
    jwks_cache_seconds: int = Field(default=300, ge=30, le=3600)
    jwks_timeout_seconds: float = Field(default=3.0, gt=0, le=15)
    jwt_clock_skew_seconds: int = Field(default=30, ge=0, le=120)
    local_tenant_id: UUID = UUID("00000000-0000-4000-8000-000000000001")
    local_actor_id: UUID = UUID("00000000-0000-4000-8000-000000000002")
    database_url: str = (
        "postgresql+asyncpg://vetorthoplan:vetorthoplan@localhost:5432/vetorthoplan"
    )
    storage_bucket: str = "vetorthoplan-uploads-local"
    storage_region: str = "us-east-1"
    storage_endpoint_url: str | None = None
    storage_public_endpoint_url: str | None = None
    upload_url_expires_seconds: int = Field(default=300, ge=60, le=900)
    preview_url_expires_seconds: int = Field(default=300, ge=60, le=900)
    storage_clock_skew_seconds: float = Field(default=5.0, ge=0, le=60)
    max_uploads_per_case: int = Field(default=20, ge=1, le=100)
    worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=60)
    tplo_rotation_table_version: str | None = Field(default=None, min_length=1, max_length=100)
    tplo_rotation_table_source: str | None = Field(default=None, min_length=1, max_length=300)
    tplo_rotation_table_json: str | None = None
    tplo_rotation_table_target_slope_degrees: float | None = Field(default=None, gt=0, lt=90)
    tplo_clinical_protocol_json: str | None = None
    implant_catalog_admin_token: str | None = Field(default=None, min_length=32)
    implant_catalog_conversion_service_url: str | None = None
    implant_catalog_conversion_service_token: str | None = None
    implant_catalog_conversion_timeout_seconds: float = Field(default=120, gt=0, le=600)
    # Deprecated aliases kept so existing deployments can migrate configuration gradually.
    oda_conversion_service_url: str | None = None
    oda_conversion_service_token: str | None = None
    oda_conversion_timeout_seconds: float = Field(default=120, gt=0, le=600)

    @model_validator(mode="after")
    def reject_local_identity_outside_safe_environments(self) -> "Settings":
        try:
            parse_clinical_protocol(self.tplo_clinical_protocol_json)
        except (ValueError, TypeError) as exc:
            raise ValueError("TPLO_CLINICAL_PROTOCOL_JSON contém um protocolo inválido") from exc
        try:
            parse_rotation_table(
                self.tplo_rotation_table_version,
                self.tplo_rotation_table_source,
                self.tplo_rotation_table_json,
                self.tplo_rotation_table_target_slope_degrees,
            )
        except (ValueError, TypeError) as exc:
            raise ValueError("Configuração da tabela TPLO inválida") from exc
        if self.identity_mode == "local" and self.app_env not in {"local", "development", "test"}:
            raise ValueError(
                "IDENTITY_MODE=local não é permitido fora dos ambientes local, development ou test."
            )
        if self.identity_mode == "jwt":
            if not self.jwt_issuer or not self.jwt_issuer.strip() or not self.jwks_url:
                raise ValueError("JWT_ISSUER e JWKS_URL são obrigatórios com IDENTITY_MODE=jwt.")
            if len(self.jwt_issuer) > 500:
                raise ValueError("JWT_ISSUER deve ter no máximo 500 caracteres.")
            if not self.jwt_audience.strip():
                raise ValueError("JWT_AUDIENCE não pode ser vazio.")
            if not self.jwks_url.strip():
                raise ValueError("JWKS_URL não pode ser vazio.")
            if not self.jwks_url.startswith("https://") and self.app_env not in {"local", "test"}:
                raise ValueError("JWKS_URL deve usar HTTPS fora dos ambientes local e test.")
        converter_url = self.implant_catalog_conversion_service_url or self.oda_conversion_service_url
        if converter_url and self.app_env not in {"local", "test"}:
            if not converter_url.startswith("https://"):
                raise ValueError(
                    "IMPLANT_CATALOG_CONVERSION_SERVICE_URL deve usar HTTPS fora dos ambientes local e test."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
