from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.use_cases import (
    CancelImageUpload,
    CompleteImageUpload,
    CreateCase,
    CreateImageUpload,
    DeleteImage,
    GetCase,
    GetImage,
    GetImagePlan,
    GetImagePreview,
    GetIngestionJob,
    ListCaseImages,
    ListCases,
    RetryIngestionJob,
    SaveImagePlan,
)
from vetorthoplan.config.settings import Settings, get_settings
from vetorthoplan.infrastructure.authentication.identity_mapping import (
    resolve_actor_id,
    resolve_tenant_id,
)
from vetorthoplan.infrastructure.authentication.jwks import (
    JWKSKeyProvider,
    JWKSUnavailableError,
    SigningKeyNotFoundError,
)
from vetorthoplan.infrastructure.clock import SystemClock
from vetorthoplan.infrastructure.database.case_repository import SqlAlchemyCaseRepository
from vetorthoplan.infrastructure.database.image_plan_repository import SqlAlchemyImagePlanRepository
from vetorthoplan.infrastructure.database.image_upload_repository import (
    SqlAlchemyImageUploadRepository,
)
from vetorthoplan.infrastructure.database.ingestion_job_queue import (
    SqlAlchemyIngestionJobQueue,
)
from vetorthoplan.infrastructure.database.session import get_database_session
from vetorthoplan.infrastructure.id_generator import UuidGenerator
from vetorthoplan.infrastructure.storage import S3PresignedPostStorage

_bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=8)
def _get_jwks_provider(url: str, cache_seconds: int, timeout_seconds: float) -> JWKSKeyProvider:
    return JWKSKeyProvider(url, cache_seconds, timeout_seconds)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credencial de acesso inválida ou ausente.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_tenant_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> TenantContext:
    if settings.identity_mode == "local":
        return TenantContext(tenant_id=settings.local_tenant_id, actor_id=settings.local_actor_id)

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    try:
        token_header = jwt.get_unverified_header(credentials.credentials)
        if token_header.get("alg") != "RS256" or not isinstance(token_header.get("kid"), str):
            raise _unauthorized()
        assert settings.jwks_url is not None
        provider = _get_jwks_provider(
            settings.jwks_url,
            settings.jwks_cache_seconds,
            settings.jwks_timeout_seconds,
        )
        signing_key = await provider.get_key(token_header["kid"])
        claims: dict[str, Any] = jwt.decode(
            credentials.credentials,
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
        # The API accepts only tokens issued specifically for this audience.
        if claims.get("aud") != settings.jwt_audience:
            raise _unauthorized()
        for claim_name in ("sub", "sid", "jti", "org_id"):
            claim_value = claims.get(claim_name)
            if not isinstance(claim_value, str) or not claim_value.strip():
                raise _unauthorized()
        if len(claims["sub"]) > 255 or len(claims["org_id"]) > 255:
            raise _unauthorized()
        if claims.get("tokenUse") != "access":
            raise _unauthorized()
    except JWKSUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível validar a credencial no momento.",
        ) from exc
    except SigningKeyNotFoundError as exc:
        raise _unauthorized() from exc
    except HTTPException:
        raise
    except (jwt.InvalidTokenError, jwt.PyJWKError, TypeError, ValueError, KeyError) as exc:
        raise _unauthorized() from exc

    assert settings.jwt_issuer is not None
    actor_id = await resolve_actor_id(session, settings.jwt_issuer, claims["sub"])
    tenant_id = await resolve_tenant_id(session, settings.jwt_issuer, claims["org_id"])
    return TenantContext(tenant_id=tenant_id, actor_id=actor_id)


def get_create_case(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> CreateCase:
    return CreateCase(
        repository=SqlAlchemyCaseRepository(session),
        id_generator=UuidGenerator(),
        clock=SystemClock(),
    )


def get_list_cases(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> ListCases:
    return ListCases(repository=SqlAlchemyCaseRepository(session))


def get_case(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> GetCase:
    return GetCase(repository=SqlAlchemyCaseRepository(session))


def get_create_image_upload(
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CreateImageUpload:
    return CreateImageUpload(
        case_repository=SqlAlchemyCaseRepository(session),
        upload_repository=SqlAlchemyImageUploadRepository(session),
        storage=S3PresignedPostStorage(
            bucket=settings.storage_bucket,
            region=settings.storage_region,
            endpoint_url=settings.storage_endpoint_url,
            presign_endpoint_url=settings.storage_public_endpoint_url,
            expires_in_seconds=settings.upload_url_expires_seconds,
        ),
        id_generator=UuidGenerator(),
        clock=SystemClock(),
        expires_in_seconds=settings.upload_url_expires_seconds,
        max_uploads_per_case=settings.max_uploads_per_case,
        environment=settings.app_env,
    )


def get_complete_image_upload(
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CompleteImageUpload:
    return CompleteImageUpload(
        repository=SqlAlchemyImageUploadRepository(session),
        job_queue=SqlAlchemyIngestionJobQueue(session),
        storage=S3PresignedPostStorage(
            bucket=settings.storage_bucket,
            region=settings.storage_region,
            endpoint_url=settings.storage_endpoint_url,
            presign_endpoint_url=settings.storage_public_endpoint_url,
            expires_in_seconds=settings.upload_url_expires_seconds,
        ),
        id_generator=UuidGenerator(),
        clock=SystemClock(),
        storage_clock_skew_seconds=settings.storage_clock_skew_seconds,
    )


def get_cancel_image_upload(
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CancelImageUpload:
    return CancelImageUpload(
        uploads=SqlAlchemyImageUploadRepository(session),
        storage=S3PresignedPostStorage(
            bucket=settings.storage_bucket,
            region=settings.storage_region,
            endpoint_url=settings.storage_endpoint_url,
            expires_in_seconds=settings.upload_url_expires_seconds,
        ),
    )


def get_ingestion_job(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> GetIngestionJob:
    return GetIngestionJob(
        SqlAlchemyIngestionJobQueue(session),
        SqlAlchemyImageUploadRepository(session),
    )


def get_retry_ingestion_job(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> RetryIngestionJob:
    return RetryIngestionJob(
        jobs=SqlAlchemyIngestionJobQueue(session),
        images=SqlAlchemyImageUploadRepository(session),
        clock=SystemClock(),
    )


def get_list_case_images(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> ListCaseImages:
    return ListCaseImages(
        case_repository=SqlAlchemyCaseRepository(session),
        image_repository=SqlAlchemyImageUploadRepository(session),
    )


def get_image(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> GetImage:
    return GetImage(SqlAlchemyImageUploadRepository(session))


def get_delete_image(
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DeleteImage:
    return DeleteImage(
        images=SqlAlchemyImageUploadRepository(session),
        plans=SqlAlchemyImagePlanRepository(session),
        jobs=SqlAlchemyIngestionJobQueue(session),
        storage=S3PresignedPostStorage(
            bucket=settings.storage_bucket,
            region=settings.storage_region,
            endpoint_url=settings.storage_endpoint_url,
            expires_in_seconds=settings.upload_url_expires_seconds,
        ),
        clock=SystemClock(),
    )


def get_image_preview(
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GetImagePreview:
    return GetImagePreview(
        repository=SqlAlchemyImageUploadRepository(session),
        storage=S3PresignedPostStorage(
            bucket=settings.storage_bucket,
            region=settings.storage_region,
            endpoint_url=settings.storage_endpoint_url,
            presign_endpoint_url=settings.storage_public_endpoint_url,
            expires_in_seconds=settings.preview_url_expires_seconds,
        ),
        clock=SystemClock(),
    )


def get_image_plan(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> GetImagePlan:
    return GetImagePlan(
        plans=SqlAlchemyImagePlanRepository(session),
        images=SqlAlchemyImageUploadRepository(session),
    )


def get_save_image_plan(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> SaveImagePlan:
    return SaveImagePlan(
        plans=SqlAlchemyImagePlanRepository(session),
        images=SqlAlchemyImageUploadRepository(session),
        id_generator=UuidGenerator(),
        clock=SystemClock(),
    )


TenantContextDependency = Annotated[TenantContext, Depends(get_tenant_context)]
CreateCaseDependency = Annotated[CreateCase, Depends(get_create_case)]
ListCasesDependency = Annotated[ListCases, Depends(get_list_cases)]
GetCaseDependency = Annotated[GetCase, Depends(get_case)]
CreateImageUploadDependency = Annotated[CreateImageUpload, Depends(get_create_image_upload)]
CompleteImageUploadDependency = Annotated[
    CompleteImageUpload,
    Depends(get_complete_image_upload),
]
CancelImageUploadDependency = Annotated[CancelImageUpload, Depends(get_cancel_image_upload)]
GetIngestionJobDependency = Annotated[GetIngestionJob, Depends(get_ingestion_job)]
RetryIngestionJobDependency = Annotated[RetryIngestionJob, Depends(get_retry_ingestion_job)]
ListCaseImagesDependency = Annotated[ListCaseImages, Depends(get_list_case_images)]
GetImageDependency = Annotated[GetImage, Depends(get_image)]
DeleteImageDependency = Annotated[DeleteImage, Depends(get_delete_image)]
GetImagePreviewDependency = Annotated[GetImagePreview, Depends(get_image_preview)]
GetImagePlanDependency = Annotated[GetImagePlan, Depends(get_image_plan)]
SaveImagePlanDependency = Annotated[SaveImagePlan, Depends(get_save_image_plan)]
