from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from vetorthoplan.api.pagination import InvalidCursorError
from vetorthoplan.api.routes.cases import router as cases_router
from vetorthoplan.api.routes.health import router as health_router
from vetorthoplan.api.routes.image_uploads import router as image_uploads_router
from vetorthoplan.api.routes.images import router as images_router
from vetorthoplan.api.routes.plans import router as plans_router
from vetorthoplan.api.schemas import ErrorResponse
from vetorthoplan.application.errors import (
    CaseNotFoundError,
    ImageNotFoundError,
    ImageNotReadyError,
    ImagePreviewUnavailableError,
    ImageUploadExpiredError,
    ImageUploadLimitExceededError,
    ImageUploadNotFoundError,
    ImageUploadObjectInvalidError,
    IngestionJobNotFoundError,
    PlanRevisionConflictError,
)
from vetorthoplan.domain.cases import CaseValidationError
from vetorthoplan.domain.imaging import ImagingValidationError


def create_app() -> FastAPI:
    app = FastAPI(
        title="VetOrthoPlan Backend API",
        version="0.7.0",
        summary="API clínica para planejamento ortopédico veterinário",
        description=(
            "Vertical slices do MVP TPLO: casos, upload e processamento inicial de radiografias. "
            "Use apenas dados sintéticos ou formalmente desidentificados neste estágio."
        ),
        contact={"name": "VetOrthoPlan"},
        license_info={"name": "Proprietary"},
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

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
    app.include_router(images_router)
    app.include_router(plans_router)
    return app


app = create_app()
