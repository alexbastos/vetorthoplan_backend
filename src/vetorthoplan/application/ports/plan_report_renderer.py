from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

REPORT_TEMPLATE_VERSION = "TPLO_FINAL_REPORT_V2"


@dataclass(frozen=True, slots=True)
class RenderedPlanReports:
    png: bytes
    pdf: bytes


class PlanReportRenderer(Protocol):
    def render(
        self,
        *,
        preview_png: bytes,
        snapshot: dict[str, Any],
        case_id: UUID,
        image_id: UUID,
        plan_revision: int,
        finalization_version: int,
        finalized_by: UUID,
        finalized_at: str,
    ) -> RenderedPlanReports: ...
