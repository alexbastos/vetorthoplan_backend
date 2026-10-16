from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vetorthoplan.domain.cases import BiologicalSex, Case, CaseStatus
from vetorthoplan.domain.imaging import ImageKind, ImageUpload, ImageUploadStatus
from vetorthoplan.domain.jobs import IngestionJob, IngestionJobStatus


class CreateCaseRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Planejamento TPLO — joelho direito",
                "animal_name": "Paciente sintético 01",
                "species": "Canina",
                "breed": "Labrador Retriever",
                "sex": "FEMALE",
                "approximate_age_months": 72,
                "weight_kg": 31.4,
                "clinical_notes": "Fixture sintética para validação do fluxo.",
            }
        }
    )

    title: str = Field(min_length=1, max_length=200, description="Título identificável do caso")
    animal_name: str = Field(min_length=1, max_length=120, description="Nome ou código do animal")
    species: str = Field(min_length=1, max_length=80, description="Espécie do animal")
    breed: str | None = Field(default=None, max_length=120, description="Raça declarada")
    sex: BiologicalSex | None = Field(default=None, description="Sexo biológico declarado")
    birth_date: date | None = Field(default=None, description="Data de nascimento conhecida")
    approximate_age_months: int | None = Field(
        default=None,
        ge=0,
        le=600,
        description="Idade aproximada em meses; não combinar com birth_date",
    )
    weight_kg: Decimal | None = Field(
        default=None,
        gt=0,
        le=Decimal("99999.99"),
        max_digits=7,
        decimal_places=2,
        description="Peso em quilogramas",
    )
    clinical_notes: str | None = Field(default=None, max_length=4_000)


class CaseResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    title: str
    animal_name: str
    species: str
    breed: str | None
    sex: BiologicalSex | None
    birth_date: date | None
    approximate_age_months: int | None
    weight_kg: Decimal | None
    clinical_notes: str | None
    status: CaseStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, case: Case) -> "CaseResponse":
        return cls(**{field: getattr(case, field) for field in cls.model_fields})


class CaseListItemResponse(BaseModel):
    id: UUID
    title: str
    animal_name: str
    species: str
    breed: str | None
    sex: BiologicalSex | None
    status: CaseStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, case: Case) -> "CaseListItemResponse":
        return cls(**{field: getattr(case, field) for field in cls.model_fields})


class CaseListResponse(BaseModel):
    items: list[CaseListItemResponse]
    next_cursor: str | None = Field(
        description="Cursor opaco para a próxima página; nulo quando não houver mais resultados",
    )
    status_counts: dict[CaseStatus, int] = Field(
        description=(
            "Contagem de todos os casos do tenant que correspondem à busca, por status; "
            "independe dos filtros status e cursor da página."
        ),
    )


class CreateImageUploadRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "original_filename": "joelho-direito.dcm",
                "media_type": "application/dicom",
                "size_bytes": 8388608,
                "sha256": "0" * 64,
            }
        }
    )

    original_filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(
        min_length=1,
        max_length=64,
        description="Tipo declarado: application/dicom, image/dicom, image/png ou image/jpeg",
    )
    size_bytes: int = Field(ge=1, le=104_857_600)
    sha256: str = Field(
        min_length=64,
        max_length=64,
        description="SHA-256 hexadecimal calculado antes do envio",
    )


class PresignedPostResponse(BaseModel):
    method: str = Field(description="Sempre POST neste contrato")
    url: str
    fields: dict[str, str] = Field(
        description="Campos que devem acompanhar o arquivo no multipart/form-data",
    )
    expires_at: datetime


class ImageUploadResponse(BaseModel):
    upload_id: UUID
    image_id: UUID
    case_id: UUID
    kind: ImageKind
    media_type: str
    size_bytes: int
    sha256: str
    status: ImageUploadStatus
    upload: PresignedPostResponse


class CompletedImageUploadResponse(BaseModel):
    upload_id: UUID
    image_id: UUID
    case_id: UUID
    kind: ImageKind
    media_type: str
    size_bytes: int
    sha256: str
    status: ImageUploadStatus
    completed_at: datetime
    job_id: UUID
    job_status: IngestionJobStatus


class ImageResponse(BaseModel):
    id: UUID
    upload_id: UUID
    case_id: UUID
    original_filename: str
    kind: ImageKind
    media_type: str
    detected_media_type: str | None
    size_bytes: int
    sha256: str
    status: ImageUploadStatus
    width_px: int | None
    height_px: int | None
    rejection_code: str | None
    created_at: datetime
    completed_at: datetime | None
    processed_at: datetime | None
    metadata: dict[str, str]
    preview_available: bool
    preview_width_px: int | None
    preview_height_px: int | None

    @classmethod
    def from_domain(cls, image: ImageUpload) -> "ImageResponse":
        return cls(
            id=image.image_id,
            upload_id=image.id,
            case_id=image.case_id,
            original_filename=image.original_filename,
            kind=image.kind,
            media_type=image.media_type,
            detected_media_type=image.detected_media_type,
            size_bytes=image.size_bytes,
            sha256=image.sha256,
            status=image.status,
            width_px=image.width_px,
            height_px=image.height_px,
            rejection_code=image.rejection_code,
            created_at=image.created_at,
            completed_at=image.completed_at,
            processed_at=image.processed_at,
            metadata=image.metadata or {},
            preview_available=image.preview_object_key is not None,
            preview_width_px=image.preview_width_px,
            preview_height_px=image.preview_height_px,
        )


class ImageListResponse(BaseModel):
    items: list[ImageResponse]


class ImagePreviewResponse(BaseModel):
    url: str
    media_type: str
    width_px: int
    height_px: int
    expires_at: datetime


class IngestionJobResponse(BaseModel):
    id: UUID
    case_id: UUID
    image_id: UUID
    upload_id: UUID
    status: IngestionJobStatus
    attempts: int
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_domain(cls, job: IngestionJob) -> "IngestionJobResponse":
        return cls(**{field: getattr(job, field) for field in cls.model_fields})


class PlanPoint(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class PlanCalibration(BaseModel):
    kind: Literal["REFERENCE_LINE"] = "REFERENCE_LINE"
    start: PlanPoint
    end: PlanPoint
    known_length_mm: float = Field(gt=0, le=10_000)


class PlanLine(BaseModel):
    id: UUID
    type: Literal["LINE"]
    start: PlanPoint
    end: PlanPoint
    label: str | None = Field(default=None, max_length=120)


class PlanAngle(BaseModel):
    id: UUID
    type: Literal["ANGLE"]
    start: PlanPoint
    vertex: PlanPoint
    end: PlanPoint
    label: str | None = Field(default=None, max_length=120)


class PlanCircle(BaseModel):
    id: UUID
    type: Literal["CIRCLE"]
    center: PlanPoint
    edge: PlanPoint
    label: str | None = Field(default=None, max_length=120)


class PlanTplo(BaseModel):
    id: UUID
    type: Literal["TPLO"]
    center: PlanPoint
    edge: PlanPoint
    rotation_degrees: float = Field(ge=-180, le=180)
    label: str | None = Field(default=None, max_length=120)


PlanObject = Annotated[PlanLine | PlanAngle | PlanCircle | PlanTplo, Field(discriminator="type")]


class TploPlanMetadata(BaseModel):
    """Clinical inputs recorded before automated TPLO calculations are available."""

    laterality: Literal["LEFT", "RIGHT"]
    projection: Literal["MEDIOLATERAL", "CRANIOCAUDAL", "UNKNOWN"] = "UNKNOWN"
    image_quality: Literal["ACCEPTABLE", "LIMITED", "REJECTED"] = "LIMITED"
    eligibility: Literal["PENDING", "ELIGIBLE", "INELIGIBLE"] = "PENDING"
    eligibility_reasons: list[str] = Field(default_factory=list, max_length=10)
    current_slope_degrees: float | None = Field(default=None, ge=0, le=90)
    target_slope_degrees: float | None = Field(default=None, ge=0, le=90)
    notes: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_eligibility(self) -> "TploPlanMetadata":
        if self.image_quality == "REJECTED" and self.eligibility == "ELIGIBLE":
            raise ValueError("Imagem rejeitada não pode ser elegível para planejamento TPLO")
        if self.eligibility == "ELIGIBLE" and self.projection != "MEDIOLATERAL":
            raise ValueError("Planejamento TPLO elegível requer projeção mediolateral")
        if self.eligibility == "INELIGIBLE" and not self.eligibility_reasons:
            raise ValueError("eligibility_reasons é obrigatório quando a imagem é inelegível")
        return self


class PlanDocument(BaseModel):
    schema_version: Literal[1] = 1
    calibration: PlanCalibration | None = None
    tplo: TploPlanMetadata | None = None
    objects: list[PlanObject] = Field(default_factory=list, max_length=500)


class SaveImagePlanRequest(BaseModel):
    base_revision: int = Field(ge=0)
    document: PlanDocument


class ImagePlanResponse(BaseModel):
    image_id: UUID
    revision: int
    document: PlanDocument
    updated_at: datetime | None


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, object] = Field(
        default_factory=dict,
        description=(
            "Campos dependem de code. REQUEST_VALIDATION_ERROR: errors[], cada item com field e type. "
            "CASE_VALIDATION_ERROR: field opcional. IMAGE_UPLOAD_OBJECT_INVALID: upload_id e reason."
        ),
    )
    trace_id: str | None = None


class ValidationFieldError(BaseModel):
    field: str = Field(description="Nome do campo em snake_case")
    type: str = Field(description="Tipo estável de validação, por exemplo greater_than")


class RequestValidationDetails(BaseModel):
    errors: list[ValidationFieldError]


class CaseValidationDetails(BaseModel):
    field: str | None = Field(default=None, description="Campo relacionado à regra de domínio")


class CreateCaseValidationErrorResponse(BaseModel):
    code: Literal["REQUEST_VALIDATION_ERROR", "CASE_VALIDATION_ERROR"]
    message: str
    details: RequestValidationDetails | CaseValidationDetails
    trace_id: str | None = None


class IdempotencyKeyConflictResponse(BaseModel):
    code: Literal["IDEMPOTENCY_KEY_REUSED"]
    message: str
    details: dict[str, object] = Field(default_factory=dict)
    trace_id: str | None = None
