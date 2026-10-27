from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.domain.planning.finalized_plan import FinalizedPlan
from vetorthoplan.infrastructure.database.models import FinalizedPlanModel


class SqlAlchemyFinalizedPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def latest(self, tenant_id: UUID, image_id: UUID) -> FinalizedPlan | None:
        model = await self._session.scalar(
            select(FinalizedPlanModel)
            .where(
                FinalizedPlanModel.tenant_id == tenant_id,
                FinalizedPlanModel.image_id == image_id,
            )
            .order_by(FinalizedPlanModel.version.desc())
            .limit(1)
        )
        return self._to_domain(model) if model is not None else None

    async def get_by_version(self, tenant_id: UUID, image_id: UUID, version: int) -> FinalizedPlan | None:
        model = await self._session.scalar(
            select(FinalizedPlanModel).where(
                FinalizedPlanModel.tenant_id == tenant_id,
                FinalizedPlanModel.image_id == image_id,
                FinalizedPlanModel.version == version,
            )
        )
        return self._to_domain(model) if model is not None else None

    async def add(self, finalized_plan: FinalizedPlan) -> bool:
        result = await self._session.execute(
            insert(FinalizedPlanModel)
            .values(
                id=finalized_plan.id,
                tenant_id=finalized_plan.tenant_id,
                case_id=finalized_plan.case_id,
                image_id=finalized_plan.image_id,
                version=finalized_plan.version,
                plan_revision=finalized_plan.plan_revision,
                snapshot=finalized_plan.snapshot,
                snapshot_sha256=finalized_plan.snapshot_sha256,
                report_template_version=finalized_plan.report_template_version,
                report_png_key=finalized_plan.report_png_key,
                report_png_sha256=finalized_plan.report_png_sha256,
                report_pdf_key=finalized_plan.report_pdf_key,
                report_pdf_sha256=finalized_plan.report_pdf_sha256,
                finalized_by=finalized_plan.finalized_by,
                finalized_at=finalized_plan.finalized_at,
            )
            .on_conflict_do_nothing(constraint="uq_finalized_plans_image")
        )
        await self._session.flush()
        return result.rowcount == 1

    async def list_for_image(self, tenant_id: UUID, image_id: UUID) -> list[FinalizedPlan]:
        models = await self._session.scalars(
            select(FinalizedPlanModel)
            .where(
                FinalizedPlanModel.tenant_id == tenant_id,
                FinalizedPlanModel.image_id == image_id,
            )
            .order_by(FinalizedPlanModel.version)
        )
        return [self._to_domain(model) for model in models]

    async def list_for_case(self, tenant_id: UUID, case_id: UUID) -> list[FinalizedPlan]:
        models = await self._session.scalars(
            select(FinalizedPlanModel)
            .where(
                FinalizedPlanModel.tenant_id == tenant_id,
                FinalizedPlanModel.case_id == case_id,
            )
            .order_by(FinalizedPlanModel.image_id, FinalizedPlanModel.version)
        )
        return [self._to_domain(model) for model in models]

    @staticmethod
    def _to_domain(model: FinalizedPlanModel) -> FinalizedPlan:
        return FinalizedPlan(
            id=model.id,
            tenant_id=model.tenant_id,
            case_id=model.case_id,
            image_id=model.image_id,
            version=model.version,
            plan_revision=model.plan_revision,
            snapshot=dict(model.snapshot),
            snapshot_sha256=model.snapshot_sha256,
            report_template_version=model.report_template_version,
            report_png_key=model.report_png_key,
            report_png_sha256=model.report_png_sha256,
            report_pdf_key=model.report_pdf_key,
            report_pdf_sha256=model.report_pdf_sha256,
            finalized_by=model.finalized_by,
            finalized_at=model.finalized_at,
        )
