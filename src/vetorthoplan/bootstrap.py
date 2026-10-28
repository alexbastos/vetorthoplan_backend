import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from vetorthoplan.api.pagination import InvalidCursorError
from vetorthoplan.api.routes.cases import router as cases_router
from vetorthoplan.api.routes.health import router as health_router
from vetorthoplan.api.routes.image_uploads import router as image_uploads_router
from vetorthoplan.api.routes.images import router as images_router
from vetorthoplan.api.routes.implant_catalog import router as implant_catalog_router
from vetorthoplan.api.routes.plans import router as plans_router
from vetorthoplan.api.routes.tplo import router as tplo_router
from vetorthoplan.api.schemas import ErrorResponse
from vetorthoplan.application.errors import (
    CaseDeletionConflictError,
    CaseNotFoundError,
    ClinicalValidationError,
    IdempotencyKeyConflictError,
    ImageDeletionConflictError,
    ImageNotFoundError,
    ImageNotReadyError,
    ImagePlanFinalizationNotFoundError,
    ImagePlanFinalizedError,
    ImagePreviewUnavailableError,
    ImageUploadCancellationConflictError,
    ImageUploadCancelledError,
    ImageUploadDuplicateError,
    ImageUploadExpiredError,
    ImageUploadIdempotencyConflictError,
    ImageUploadLimitExceededError,
    ImageUploadNotFoundError,
    ImageUploadObjectInvalidError,
    ImageUploadSessionNotPendingError,
    IngestionJobNotFoundError,
    IngestionJobRetryNotAllowedError,
    PlanRevisionConflictError,
)
from vetorthoplan.domain.cases import CaseValidationError
from vetorthoplan.domain.imaging import ImageDisplayNameValidationError, ImagingValidationError


def create_app() -> FastAPI:
    app = FastAPI(
        title="VetOrthoPlan Backend API",
        version="0.9.0",
        summary="API clínica para planejamento ortopédico veterinário",
        description=(
            "Vertical slices do MVP TPLO: casos, upload e processamento inicial de radiografias. "
            "Use apenas dados sintéticos ou formalmente desidentificados neste estágio. "
            "A identidade é configurada por ambiente; o modo JWT valida tokens da authentication_api "
            "e mantém isolamento clínico por tenant."
        ),
        contact={"name": "VetOrthoPlan"},
        license_info={"name": "Proprietary"},
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    default_openapi = app.openapi

    def openapi_with_revision() -> dict[str, object]:
        schema = default_openapi()
        schema["info"]["x-git-branch"] = os.getenv("VETORTHOPLAN_GIT_BRANCH", "unknown")
        schema["info"]["x-git-commit"] = os.getenv("VETORTHOPLAN_GIT_COMMIT", "unknown")
        return schema

    app.openapi = openapi_with_revision

    @app.exception_handler(CaseNotFoundError)
    async def case_not_found_error_handler(
        _request: Request,
        exc: CaseNotFoundError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="CASE_NOT_FOUND",
            message=str(exc),
            details={"case_id": str(exc.case_id)},
        )
        return JSONResponse(status_code=404, content=error.model_dump())

    @app.exception_handler(CaseDeletionConflictError)
    async def case_deletion_conflict_handler(
        _request: Request, exc: CaseDeletionConflictError
    ) -> JSONResponse:
        error = ErrorResponse(
            code="CASE_DELETE_NOT_ALLOWED",
            message=str(exc),
            details={"reason": exc.reason, "case_id": str(exc.case_id)},
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(InvalidCursorError)
    async def invalid_cursor_error_handler(
        _request: Request,
        exc: InvalidCursorError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="INVALID_CURSOR",
            message=str(exc),
        )
        return JSONResponse(status_code=422, content=error.model_dump())

    @app.exception_handler(CaseValidationError)
    async def case_validation_error_handler(
        _request: Request,
        exc: CaseValidationError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="CASE_VALIDATION_ERROR",
            message=str(exc),
            details={"field": exc.field} if exc.field else {},
        )
        return JSONResponse(status_code=422, content=error.model_dump())

    @app.exception_handler(IdempotencyKeyConflictError)
    async def idempotency_key_conflict_handler(
        _request: Request,
        _exc: IdempotencyKeyConflictError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IDEMPOTENCY_KEY_REUSED",
            message="A chave de idempotência já foi usada com dados diferentes.",
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(ImagingValidationError)
    async def imaging_validation_error_handler(
        _request: Request,
        exc: ImagingValidationError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_UPLOAD_VALIDATION_ERROR",
            message=str(exc),
            details={"field": exc.field} if exc.field else {},
        )
        return JSONResponse(status_code=422, content=error.model_dump())

    @app.exception_handler(ImageDisplayNameValidationError)
    async def image_display_name_validation_handler(
        _request: Request, exc: ImageDisplayNameValidationError
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_DISPLAY_NAME_INVALID",
            message=str(exc),
            details={"field": exc.field} if exc.field else {},
        )
        return JSONResponse(status_code=422, content=error.model_dump())

    @app.exception_handler(ImageUploadLimitExceededError)
    async def image_upload_limit_error_handler(
        _request: Request,
        exc: ImageUploadLimitExceededError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_UPLOAD_LIMIT_EXCEEDED",
            message=str(exc),
            details={"case_id": str(exc.case_id), "limit": exc.limit},
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(ImageUploadDuplicateError)
    async def image_upload_duplicate_error_handler(
        _request: Request,
        exc: ImageUploadDuplicateError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_UPLOAD_DUPLICATE",
            message=str(exc),
            details=(
                {"existing_image_id": str(exc.existing_image_id)} if exc.existing_image_id is not None else {}
            ),
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(ImageUploadIdempotencyConflictError)
    async def image_upload_idempotency_conflict_handler(
        _request: Request,
        exc: ImageUploadIdempotencyConflictError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_UPLOAD_IDEMPOTENCY_KEY_REUSED",
            message=str(exc),
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(ImageUploadNotFoundError)
    async def image_upload_not_found_error_handler(
        _request: Request,
        exc: ImageUploadNotFoundError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_UPLOAD_NOT_FOUND",
            message=str(exc),
            details={"upload_id": str(exc.upload_id)},
        )
        return JSONResponse(status_code=404, content=error.model_dump())

    @app.exception_handler(ImageUploadExpiredError)
    async def image_upload_expired_error_handler(
        _request: Request,
        exc: ImageUploadExpiredError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_UPLOAD_EXPIRED",
            message=str(exc),
            details={"upload_id": str(exc.upload_id)},
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(ImageUploadCancelledError)
    async def image_upload_cancelled_error_handler(
        _request: Request,
        exc: ImageUploadCancelledError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_UPLOAD_CANCELLED",
            message=str(exc),
            details={"upload_id": str(exc.upload_id)},
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(ImageUploadSessionNotPendingError)
    async def image_upload_session_not_pending_handler(
        _request: Request,
        exc: ImageUploadSessionNotPendingError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_UPLOAD_SESSION_NOT_PENDING",
            message=str(exc),
            details={"upload_id": str(exc.upload_id)},
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(ImageUploadCancellationConflictError)
    async def image_upload_cancellation_conflict_handler(
        _request: Request,
        exc: ImageUploadCancellationConflictError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_UPLOAD_CANCELLATION_CONFLICT",
            message=str(exc),
            details={"upload_id": str(exc.upload_id)},
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(ImageUploadObjectInvalidError)
    async def image_upload_object_invalid_error_handler(
        _request: Request,
        exc: ImageUploadObjectInvalidError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_UPLOAD_OBJECT_INVALID",
            message=str(exc),
            details={"upload_id": str(exc.upload_id), "reason": exc.reason},
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(ImageNotFoundError)
    async def image_not_found_error_handler(
        _request: Request,
        exc: ImageNotFoundError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_NOT_FOUND",
            message=str(exc),
            details={"image_id": str(exc.image_id)},
        )
        return JSONResponse(status_code=404, content=error.model_dump())

    @app.exception_handler(ImageDeletionConflictError)
    async def image_deletion_conflict_error_handler(
        _request: Request,
        exc: ImageDeletionConflictError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_DELETION_CONFLICT",
            message=str(exc),
            details={"image_id": str(exc.image_id)},
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(IngestionJobNotFoundError)
    async def ingestion_job_not_found_error_handler(
        _request: Request,
        exc: IngestionJobNotFoundError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="INGESTION_JOB_NOT_FOUND",
            message=str(exc),
            details={"job_id": str(exc.job_id)},
        )
        return JSONResponse(status_code=404, content=error.model_dump())

    @app.exception_handler(IngestionJobRetryNotAllowedError)
    async def ingestion_job_retry_not_allowed_handler(
        _request: Request,
        exc: IngestionJobRetryNotAllowedError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="INGESTION_JOB_RETRY_NOT_ALLOWED",
            message=str(exc),
            details={"job_id": str(exc.job_id)},
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(ImagePreviewUnavailableError)
    async def image_preview_unavailable_error_handler(
        _request: Request,
        exc: ImagePreviewUnavailableError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_PREVIEW_UNAVAILABLE",
            message=str(exc),
            details={"image_id": str(exc.image_id)},
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(ImageNotReadyError)
    async def image_not_ready_error_handler(
        _request: Request,
        exc: ImageNotReadyError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_NOT_READY",
            message=str(exc),
            details={"image_id": str(exc.image_id)},
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(PlanRevisionConflictError)
    async def plan_revision_conflict_error_handler(
        _request: Request,
        exc: PlanRevisionConflictError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="PLAN_REVISION_CONFLICT",
            message=str(exc),
            details={"current_revision": exc.current_revision},
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(ImagePlanFinalizedError)
    async def image_plan_finalized_error_handler(
        _request: Request,
        exc: ImagePlanFinalizedError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_PLAN_FINALIZED",
            message=str(exc),
            details={"image_id": str(exc.image_id), "finalization_version": exc.version},
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    @app.exception_handler(ImagePlanFinalizationNotFoundError)
    async def image_plan_finalization_not_found_handler(
        _request: Request,
        exc: ImagePlanFinalizationNotFoundError,
    ) -> JSONResponse:
        error = ErrorResponse(
            code="IMAGE_PLAN_FINALIZATION_NOT_FOUND",
            message=str(exc),
            details={"image_id": str(exc.image_id)},
        )
        return JSONResponse(status_code=404, content=error.model_dump())

    @app.exception_handler(ClinicalValidationError)
    async def clinical_validation_error_handler(
        _request: Request,
        exc: ClinicalValidationError,
    ) -> JSONResponse:
        error = ErrorResponse(code="CLINICAL_VALIDATION_INVALID", message=str(exc))
        return JSONResponse(status_code=422, content=error.model_dump())

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(part) for part in error["loc"] if part != "body"),
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        error = ErrorResponse(
            code="REQUEST_VALIDATION_ERROR",
            message="A requisição contém campos inválidos.",
            details={"errors": errors},
        )
        return JSONResponse(status_code=422, content=error.model_dump())

    app.include_router(health_router)
    app.include_router(cases_router)
    app.include_router(image_uploads_router)
    app.include_router(implant_catalog_router)
    app.include_router(images_router)
    app.include_router(plans_router)
    app.include_router(tplo_router)
    return app


app = create_app()
