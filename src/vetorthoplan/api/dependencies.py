from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.use_cases import (
    CompleteImageUpload,
    CreateCase,
    CreateImageUpload,
    GetCase,
    GetImage,
    GetImagePlan,
    GetImagePreview,
    GetIngestionJob,
    ListCaseImages,
    ListCases,
    SaveImagePlan,
)
from vetorthoplan.config.settings import Settings, get_settings
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


def get_tenant_context(settings: Annotated[Settings, Depends(get_settings)]) -> TenantContext:
    if settings.identity_mode != "local":
        raise RuntimeError("O adapter JWT ainda não foi implementado.")
    return TenantContext(tenant_id=settings.local_tenant_id, actor_id=settings.local_actor_id)


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
            expires_in_seconds=settings.upload_url_expires_seconds,
        ),
        id_generator=UuidGenerator(),
        clock=SystemClock(),
        storage_clock_skew_seconds=settings.storage_clock_skew_seconds,
    )


def get_ingestion_job(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> GetIngestionJob:
    return GetIngestionJob(SqlAlchemyIngestionJobQueue(session))


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
GetIngestionJobDependency = Annotated[GetIngestionJob, Depends(get_ingestion_job)]
ListCaseImagesDependency = Annotated[ListCaseImages, Depends(get_list_case_images)]
GetImageDependency = Annotated[GetImage, Depends(get_image)]
GetImagePreviewDependency = Annotated[GetImagePreview, Depends(get_image_preview)]
GetImagePlanDependency = Annotated[GetImagePlan, Depends(get_image_plan)]
SaveImagePlanDependency = Annotated[SaveImagePlan, Depends(get_save_image_plan)]
