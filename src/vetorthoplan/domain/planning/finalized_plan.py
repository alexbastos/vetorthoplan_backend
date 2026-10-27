from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class FinalizedPlan:
    id: UUID
    tenant_id: UUID
    case_id: UUID
    image_id: UUID
    version: int
    plan_revision: int
    snapshot: dict[str, object]
    snapshot_sha256: str
    report_template_version: str
    report_png_key: str
    report_png_sha256: str
    report_pdf_key: str
    report_pdf_sha256: str
    finalized_by: UUID
    finalized_at: datetime
