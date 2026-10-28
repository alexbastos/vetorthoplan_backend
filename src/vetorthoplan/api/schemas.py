import math
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vetorthoplan.domain.cases import AgeSource, BiologicalSex, Case, CaseStatus
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
    sex: BiologicalSex = Field(description="Sexo biológico; UNKNOWN é aceito como valor explícito")
    birth_date: date | None = Field(default=None, description="Data de nascimento conhecida")
    approximate_age_months: int | None = Field(
        default=None,
        ge=0,
        le=600,
        description=(
            "Idade em meses completos na data de criação do caso. Pode acompanhar birth_date "
            "quando igual à idade calculada nessa data."
        ),
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
    age_source: AgeSource | None = Field(description="DECLARED ou BIRTH_DATE; nulo se idade desconhecida")
    age_reference_date: date | None = Field(
        description="Data usada como referência para approximate_age_months"
    )
    weight_kg: Decimal | None
    clinical_notes: str | None
    status: CaseStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, case: Case) -> "CaseResponse":
        values = {field: getattr(case, field) for field in cls.model_fields}
        if case.approximate_age_months is None and case.birth_date is not None:
            reference_date = case.age_reference_date or case.created_at.date()
            values["approximate_age_months"] = Case._months_completed(case.birth_date, reference_date)
        return cls(**values)


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


def _parse_dicom_decimal_values(
    metadata: dict[str, str] | None,
    key: str,
    *,
    expected_count: int = 2,
) -> tuple[float, ...] | None:
    raw_value = (metadata or {}).get(key)
    if not raw_value:
        return None
    try:
        values = tuple(float(part) for part in raw_value.split("\\"))
    except ValueError:
        return None
    if len(values) != expected_count or not all(math.isfinite(value) for value in values):
        return None
    if key in {"pixel_spacing", "imager_pixel_spacing"} and any(value <= 0 for value in values):
        return None
    return values


class ImageResponse(BaseModel):
    id: UUID
    upload_id: UUID
    job_id: UUID | None = Field(
        description="Job de ingestão associado; nulo enquanto a confirmação ainda não criou o job"
    )
    case_id: UUID
    original_filename: str
    display_name: str | None
    kind: ImageKind
    media_type: str
    detected_media_type: str | None
    size_bytes: int
    sha256: str
    status: ImageUploadStatus
    width_px: int | None
    height_px: int | None
    rejection_code: str | None = Field(
        description=(
            "Código estável de rejeição de conteúdo: empty_content, checksum_mismatch, "
            "format_mismatch, malformed_image, dimensions_exceeded, "
            "unsupported_transfer_syntax, unsupported_dicom_pixels, malformed_dicom ou "
            "unsupported_dicom_structure. Códigos e mensagens: docs/FRONTEND_PROCESSAMENTO_IMAGENS.md."
        )
    )
    created_at: datetime
    completed_at: datetime | None
    processed_at: datetime | None
    metadata: dict[str, str]
    preview_available: bool
    preview_width_px: int | None
    preview_height_px: int | None
    pixel_spacing_mm: tuple[float, float] | None = Field(
        description="Espaçamento DICOM [linhas, colunas] em milímetros, quando informado e válido"
    )
    imager_pixel_spacing_mm: tuple[float, float] | None = Field(
        description="Imager Pixel Spacing DICOM [linhas, colunas] em milímetros, quando válido"
    )
    image_orientation_patient: tuple[float, float, float, float, float, float] | None = Field(
        description="Cossenos direcionais DICOM da primeira e segunda linhas de pixels"
    )

    @classmethod
    def from_domain(cls, image: ImageUpload, *, job_id: UUID | None = None) -> "ImageResponse":
        return cls(
            id=image.image_id,
            upload_id=image.id,
            job_id=job_id,
            case_id=image.case_id,
            original_filename=image.original_filename,
            display_name=image.display_name,
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
            pixel_spacing_mm=_parse_dicom_decimal_values(image.metadata, "pixel_spacing"),
            imager_pixel_spacing_mm=_parse_dicom_decimal_values(image.metadata, "imager_pixel_spacing"),
            image_orientation_patient=_parse_dicom_decimal_values(
                image.metadata, "image_orientation_patient", expected_count=6
            ),
        )


class ImageListResponse(BaseModel):
    items: list[ImageResponse]


class RenameImageRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": {"display_name": "Membro anterior direito - lateral.png"}},
    )
    display_name: str = Field(min_length=1, max_length=255)


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
    error_code: str | None = Field(
        description=(
            "Código estável da falha: códigos de conteúdo listados em rejection_code, "
            "upload_not_found ou processing_failed. Mensagens seguras e recuperação: "
            "docs/FRONTEND_PROCESSAMENTO_IMAGENS.md."
        )
    )
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_domain(cls, job: IngestionJob) -> "IngestionJobResponse":
        return cls(**{field: getattr(job, field) for field in cls.model_fields})


class ImageIngestionJobResponse(BaseModel):
    job: IngestionJobResponse | None = Field(
        description="Job associado à imagem; nulo enquanto a confirmação ainda não criou o job"
    )


class PlanPoint(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class PlanCalibrationResult(BaseModel):
    calibration_id: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="Fingerprint da referência manual e das dimensões da imagem.",
    )
    reference_length_px: float = Field(gt=0, description="Comprimento da referência na imagem original.")
    mm_per_pixel: float = Field(gt=0, description="Escala calculada a partir da medida manual informada.")


class PlanDerivedMeasurement(BaseModel):
    status: Literal["CALCULATED", "CALIBRATION_REQUIRED", "IMAGE_DIMENSIONS_REQUIRED"] = Field(
        description="Estado do cálculo geométrico feito pelo backend."
    )
    calibration_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    values: dict[str, float] = Field(default_factory=dict, description="Valores geométricos derivados.")
    units: dict[str, Literal["mm", "degrees"]] = Field(
        default_factory=dict, description="Unidade de cada medida."
    )


class PlanTploSimulation(BaseModel):
    status: Literal["SIMULATED", "CALIBRATION_REQUIRED", "IMAGE_DIMENSIONS_REQUIRED", "FRAGMENT_REQUIRED"]
    calibration_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    center_px: dict[str, float] = Field(default_factory=dict)
    radius_mm: float | None = Field(default=None, gt=0)
    rotation_degrees: float | None = Field(default=None, ge=-180, le=180)
    affine_matrix: list[list[float]] = Field(default_factory=list)
    transformed_fragment_points_px: list[dict[str, float]] = Field(
        default_factory=list,
        description="Contorno resultante após rotação, em pixels da imagem original.",
    )


class PlanFragment(BaseModel):
    points: list[PlanPoint] = Field(min_length=3, max_length=500)
    label: str | None = Field(default=None, max_length=120)


class PlanReferenceLineCalibration(BaseModel):
    kind: Literal["REFERENCE_LINE"] = "REFERENCE_LINE"
    start: PlanPoint
    end: PlanPoint
    known_length_mm: float = Field(gt=0, le=10_000)
    result: PlanCalibrationResult | None = Field(
        default=None, description="Resultado calculado pelo backend; não enviar como fonte da calibração."
    )

    @model_validator(mode="after")
    def validate_reference(self) -> "PlanReferenceLineCalibration":
        if self.start == self.end:
            raise ValueError("A linha de calibração precisa ter comprimento maior que zero")
        return self


class PlanReferenceCircleCalibration(BaseModel):
    kind: Literal["REFERENCE_CIRCLE"] = "REFERENCE_CIRCLE"
    center: PlanPoint
    edge: PlanPoint
    known_diameter_mm: float = Field(gt=0, le=10_000)
    result: PlanCalibrationResult | None = Field(
        default=None, description="Resultado calculado pelo backend; não enviar como fonte da calibração."
    )

    @model_validator(mode="after")
    def validate_reference(self) -> "PlanReferenceCircleCalibration":
        if self.center == self.edge:
            raise ValueError("O raio de calibração precisa ser maior que zero")
        return self


PlanCalibration = Annotated[
    PlanReferenceLineCalibration | PlanReferenceCircleCalibration,
    Field(discriminator="kind"),
]


class PlanLine(BaseModel):
    id: UUID
    type: Literal["LINE"]
    start: PlanPoint
    end: PlanPoint
    label: str | None = Field(default=None, max_length=120)
    visible: bool = True
    locked: bool = False
    measurement: PlanDerivedMeasurement | None = Field(
        default=None, description="Resultado calculado pelo backend; valores do cliente são ignorados."
    )

    @model_validator(mode="after")
    def validate_length(self) -> "PlanLine":
        if self.start == self.end:
            raise ValueError("A linha precisa ter comprimento maior que zero")
        return self


class PlanAngle(BaseModel):
    id: UUID
    type: Literal["ANGLE"]
    start: PlanPoint
    vertex: PlanPoint
    end: PlanPoint
    label: str | None = Field(default=None, max_length=120)
    visible: bool = True
    locked: bool = False
    measurement: PlanDerivedMeasurement | None = Field(
        default=None, description="Resultado calculado pelo backend; valores do cliente são ignorados."
    )

    @model_validator(mode="after")
    def validate_sides(self) -> "PlanAngle":
        if self.start == self.vertex or self.end == self.vertex:
            raise ValueError("Os lados do ângulo precisam ter comprimento maior que zero")
        return self


class PlanCircle(BaseModel):
    id: UUID
    type: Literal["CIRCLE"]
    center: PlanPoint
    edge: PlanPoint
    label: str | None = Field(default=None, max_length=120)
    visible: bool = True
    locked: bool = False
    measurement: PlanDerivedMeasurement | None = Field(
        default=None, description="Resultado calculado pelo backend; valores do cliente são ignorados."
    )

    @model_validator(mode="after")
    def validate_radius(self) -> "PlanCircle":
        if self.center == self.edge:
            raise ValueError("O raio precisa ter comprimento maior que zero")
        return self


class PlanTplo(BaseModel):
    id: UUID
    type: Literal["TPLO"]
    center: PlanPoint
    edge: PlanPoint
    rotation_degrees: float = Field(ge=-180, le=180)
    label: str | None = Field(default=None, max_length=120)
    visible: bool = True
    locked: bool = False
    measurement: PlanDerivedMeasurement | None = Field(
        default=None, description="Resultado calculado pelo backend; valores do cliente são ignorados."
    )
    fragment: PlanFragment | None = Field(
        default=None, description="Contorno do fragmento proximal no sistema normalizado da imagem."
    )
    simulation: PlanTploSimulation | None = Field(
        default=None, description="Transformação geométrica calculada pelo backend."
    )

    @model_validator(mode="after")
    def validate_radius(self) -> "PlanTplo":
        if self.center == self.edge:
            raise ValueError("O raio TPLO precisa ter comprimento maior que zero")
        return self


class PlanImplantTransform(BaseModel):
    status: Literal["CALCULATED", "IMAGE_DIMENSIONS_REQUIRED"] = "IMAGE_DIMENSIONS_REQUIRED"
    coordinate_space: Literal["IMAGE_PIXELS"] = "IMAGE_PIXELS"
    affine_matrix: list[list[float]] = Field(default_factory=list)


class PlanImplant(BaseModel):
    """Placement of an approved, tenant-scoped catalog asset in source-image coordinates."""

    id: UUID
    type: Literal["IMPLANT"]
    catalog_item_id: UUID
    position: PlanPoint
    rotation_degrees: float = Field(default=0, ge=-180, le=180)
    scale: float = Field(default=1, gt=0, le=100)
    opacity: float = Field(default=1, ge=0, le=1)
    variant: str | None = Field(default=None, max_length=120)
    view: str | None = Field(default=None, max_length=120)
    label: str | None = Field(default=None, max_length=120)
    visible: bool = True
    locked: bool = False
    transform: PlanImplantTransform | None = Field(
        default=None, description="Transformação afim recalculada pelo backend para a imagem original."
    )


PlanObject = Annotated[
    PlanLine | PlanAngle | PlanCircle | PlanTplo | PlanImplant,
    Field(discriminator="type"),
]


class PlanViewport(BaseModel):
    """Presentation state for reopening the editor; geometry remains image-relative."""

    zoom: float = Field(default=1, ge=0.1, le=20)
    pan_x: float = Field(
        default=0, ge=-10, le=10, description="Deslocamento horizontal em larguras da imagem."
    )
    pan_y: float = Field(
        default=0, ge=-10, le=10, description="Deslocamento vertical em alturas da imagem."
    )


class PlanImageRegion(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> "PlanImageRegion":
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("A região da imagem deve estar contida no quadro original")
        return self


class PlanImageTransformResult(BaseModel):
    status: Literal["CALCULATED", "IMAGE_DIMENSIONS_REQUIRED"]
    crop_box_px: list[int] = Field(default_factory=list)
    output_size_px: list[int] = Field(default_factory=list)
    affine_matrix: list[list[float]] = Field(default_factory=list)


class PlanImageTransform(BaseModel):
    crop: PlanImageRegion | None = None
    rotation_degrees: float = Field(
        default=0,
        ge=-180,
        le=180,
        description="Rotação global anti-horária, em graus, aplicada após o recorte.",
    )
    result: PlanImageTransformResult | None = Field(
        default=None, description="Transformação da imagem recalculada pelo backend."
    )


class TploPlanMetadata(BaseModel):
    """Clinical inputs, including laterality and radiographic projection for the plan image."""

    laterality: Literal["LEFT", "RIGHT"] = Field(description="Lado clínico selecionado para a imagem")
    projection: Literal["MEDIOLATERAL", "CRANIOCAUDAL", "UNKNOWN"] = Field(
        default="UNKNOWN",
        description="Incidência radiográfica da imagem usada no planejamento",
    )
    image_quality: Literal["ACCEPTABLE", "LIMITED", "REJECTED"] = "LIMITED"
    eligibility: Literal["PENDING", "ELIGIBLE", "INELIGIBLE"] = "PENDING"
    eligibility_reasons: list[str] = Field(default_factory=list, max_length=10)
    current_slope_degrees: float | None = Field(default=None, ge=0, le=90)
    target_slope_degrees: float | None = Field(default=None, ge=0, le=90)
    blade_diameter_mm: float | None = Field(default=None, gt=0, le=100)
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


class TploRadiographicQuality(BaseModel):
    """Image quality observations recorded by the clinician for a TPLO view."""

    true_lateral: Literal["PASS", "FAIL", "NOT_ASSESSED"] = "NOT_ASSESSED"
    femoral_condyles_superimposed: Literal["PASS", "FAIL", "NOT_ASSESSED"] = "NOT_ASSESSED"
    stifle_and_tarsus_included: Literal["PASS", "FAIL", "NOT_ASSESSED"] = "NOT_ASSESSED"
    tibial_axis_centered: Literal["PASS", "FAIL", "NOT_ASSESSED"] = "NOT_ASSESSED"
    tibial_plateau_visible: Literal["PASS", "FAIL", "NOT_ASSESSED"] = "NOT_ASSESSED"
    notes: str | None = Field(default=None, max_length=2_000)

    @property
    def acceptable_for_planning(self) -> bool:
        return all(
            getattr(self, name) == "PASS"
            for name in (
                "true_lateral",
                "femoral_condyles_superimposed",
                "stifle_and_tarsus_included",
                "tibial_axis_centered",
                "tibial_plateau_visible",
            )
        )


class TploLandmarks(BaseModel):
    method: Literal[
        "MEDIAL_CONDYLE_CRANIAL_CRUCIATE_FULL_AXIS_V1",
        "CONVENTIONAL_FULL_MECHANICAL_AXIS_V1",
    ] = Field(
        default="MEDIAL_CONDYLE_CRANIAL_CRUCIATE_FULL_AXIS_V1",
        description=(
            "Método do artigo Today's Veterinary Practice: cranioproximal medial plateau "
            "junto à inserção do CrCL, caudoproximal do côndilo medial e eixo mecânico completo."
        ),
    )
    plateau_cranial: PlanPoint
    plateau_caudal: PlanPoint
    intercondylar_midpoint: PlanPoint
    talus_center: PlanPoint


class TploAdditionalMeasurementInput(BaseModel):
    """User placed named landmarks and an independent reference measurement."""

    landmarks: dict[str, PlanPoint] = Field(default_factory=dict, max_length=40)
    reference_values: dict[str, float] = Field(default_factory=dict, max_length=50)


class TploClinicalMeasurement(BaseModel):
    method: Literal[
        "MEDIAL_CONDYLE_CRANIAL_CRUCIATE_FULL_AXIS_V1",
        "CONVENTIONAL_FULL_MECHANICAL_AXIS_V1",
    ]
    status: Literal["CALCULATED", "LANDMARKS_REQUIRED", "IMAGE_DIMENSIONS_REQUIRED"]
    tpa_degrees: float | None = Field(default=None, ge=0, le=90)
    plateau_length_mm: float | None = Field(default=None, gt=0)
    tibial_axis_length_mm: float | None = Field(default=None, gt=0)
    calibration_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reference_tpa_degrees: float | None = Field(default=None, ge=0, le=90)
    tpa_absolute_error_degrees: float | None = Field(default=None, ge=0, le=90)
    tpa_max_absolute_error_degrees: float | None = Field(default=None, gt=0, le=90)
    acceptance: Literal["PASS", "FAIL", "NOT_ASSESSED", "NOT_CONFIGURED"] | None = None
    clinical_protocol_version: str | None = None
    clinically_validated: Literal[False] = False


class TploCorrectionPlan(BaseModel):
    status: Literal[
        "CALCULATED",
        "LANDMARKS_REQUIRED",
        "BLADE_DIAMETER_REQUIRED",
        "ROTATION_TABLE_NOT_CONFIGURED",
        "EXACT_TABLE_MATCH_REQUIRED",
        "TARGET_SLOPE_MISMATCH",
        "TARGET_SLOPE_REQUIRED",
    ]
    preoperative_tpa_degrees: float | None = Field(default=None, ge=0, le=90)
    current_slope_degrees: float | None = Field(default=None, ge=0, le=90)
    target_slope_degrees: float | None = Field(default=None, ge=0, le=90)
    blade_diameter_mm: float | None = Field(default=None, gt=0)
    rotation_mm: float | None = Field(default=None, gt=0)
    table_version: str | None = None
    table_source: str | None = None
    table_entries_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    acceptance: Literal["PASS", "NOT_ASSESSED"] = "NOT_ASSESSED"
    clinically_validated: Literal[False] = False


class TploClinicalValidation(BaseModel):
    status: Literal["DRAFT", "READY_FOR_REVIEW", "APPROVED", "REJECTED"] = "DRAFT"
    orientation_confirmed: bool = False
    image_quality_confirmed: bool = False
    calibration_confirmed: bool = False
    anatomical_references_confirmed: bool = False
    required_measurements: list[str] = Field(default_factory=list, max_length=50)
    reviewer_notes: str | None = Field(default=None, max_length=2_000)
    rejection_reason: str | None = Field(default=None, max_length=2_000)
    audit: list["TploClinicalReviewAudit"] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_state(self) -> "TploClinicalValidation":
        if self.status == "REJECTED" and not (self.rejection_reason or "").strip():
            raise ValueError("rejection_reason é obrigatório quando a validação é rejeitada")
        if self.status == "READY_FOR_REVIEW" and not all(
            (
                self.orientation_confirmed,
                self.image_quality_confirmed,
                self.calibration_confirmed,
                self.anatomical_references_confirmed,
            )
        ):
            raise ValueError("Todos os itens do checklist devem estar confirmados para revisão")
        return self


class TploClinicalReviewAudit(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    actor_id: UUID
    reviewed_at: datetime
    protocol_version: str
    measurement_method: str | None = None
    calibration_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    rotation_table_version: str | None = None
    clinical_protocol_source: str | None = None


class PlanDocument(BaseModel):
    schema_version: Literal[1] = 1
    viewport: PlanViewport = Field(default_factory=PlanViewport)
    image_transform: PlanImageTransform = Field(default_factory=PlanImageTransform)
    calibration: PlanCalibration | None = None
    tplo: TploPlanMetadata | None = None
    radiographic_quality: TploRadiographicQuality | None = None
    tplo_landmarks: TploLandmarks | None = None
    additional_measurements_input: TploAdditionalMeasurementInput = Field(
        default_factory=TploAdditionalMeasurementInput
    )
    additional_measurements: list[dict[str, object]] = Field(default_factory=list)
    tplo_measurement: TploClinicalMeasurement | None = None
    tplo_correction: TploCorrectionPlan | None = None
    clinical_validation: TploClinicalValidation | None = None
    objects: list[PlanObject] = Field(default_factory=list, max_length=500)


class SaveImagePlanRequest(BaseModel):
    base_revision: int = Field(ge=0)
    document: PlanDocument


class ReviewImagePlanRequest(BaseModel):
    """Command for the server-owned clinical review transition.

    Geometry is intentionally absent from this payload. The reviewer decides on the
    persisted candidate that was submitted for review, preventing the decision call
    from silently changing measurements or the TPLO simulation.
    """

    base_revision: int = Field(ge=1)
    status: Literal["READY_FOR_REVIEW", "APPROVED", "REJECTED"]
    orientation_confirmed: bool | None = None
    image_quality_confirmed: bool | None = None
    calibration_confirmed: bool | None = None
    anatomical_references_confirmed: bool | None = None
    required_measurements: list[str] | None = Field(default=None, max_length=50)
    reviewer_notes: str | None = Field(default=None, max_length=2_000)
    rejection_reason: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_rejection(self) -> "ReviewImagePlanRequest":
        if self.status == "REJECTED" and not (self.rejection_reason or "").strip():
            raise ValueError("rejection_reason é obrigatório quando a validação é rejeitada")
        return self


class ImagePlanResponse(BaseModel):
    image_id: UUID
    revision: int
    document: PlanDocument
    updated_at: datetime | None


class ValidateImagePlanRequest(BaseModel):
    base_revision: int | None = Field(default=None, ge=0)


class PlanValidationIssueResponse(BaseModel):
    code: str
    message: str
    field: str | None = None


class ImagePlanValidationResponse(BaseModel):
    image_id: UUID
    plan_revision: int
    status: Literal["READY_FOR_CLINICAL_REVIEW", "INCOMPLETE"]
    checks: dict[str, Literal["PASS", "FAIL", "NOT_APPLICABLE", "PENDING", "NOT_CHECKED"]]
    blocking_errors: list[PlanValidationIssueResponse]
    warnings: list[PlanValidationIssueResponse]
    validated_at: datetime


class FinalizeImagePlanRequest(BaseModel):
    base_revision: int = Field(ge=1)


class FinalizedReportFileResponse(BaseModel):
    format: Literal["PNG", "PDF"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    download_url: str
    expires_at: datetime


class FinalizedImagePlanResponse(BaseModel):
    image_id: UUID
    version: int = Field(ge=1)
    plan_revision: int = Field(ge=1)
    snapshot: dict[str, object]
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_template_version: str
    finalized_by: UUID
    finalized_at: datetime
    reports: list[FinalizedReportFileResponse]


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, object] = Field(
        default_factory=dict,
        description=(
            "Campos dependem de code. REQUEST_VALIDATION_ERROR: errors[], cada item com field e type. "
            "CASE_VALIDATION_ERROR: field opcional. IMAGE_UPLOAD_OBJECT_INVALID: upload_id e reason. "
            "IMAGE_UPLOAD_DUPLICATE: existing_image_id opcional, se a sessão confirmada for visível."
        ),
    )
    trace_id: str | None = None


class TploRotationTableResponse(BaseModel):
    configured: bool
    table_version: str | None
    source: str | None
    source_url: str | None = None
    source_asset_url: str | None = None
    target_slope_degrees: float | None = None
    entries_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    query: dict[str, float] = Field(default_factory=dict)
    match_count: int = Field(ge=0)
    entries: list[dict[str, str | int | float]]
    recommendation_enabled: Literal[False] = False


class TploClinicalProtocolResponse(BaseModel):
    configured: bool
    protocol_version: str | None = None
    source: str | None = None
    tpa_max_absolute_error_degrees: float | None = Field(default=None, gt=0, le=90)
    measurements: list[dict[str, object]] = Field(default_factory=list)
    acceptance_enabled: bool = False
    clinically_validated: Literal[False] = False


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
