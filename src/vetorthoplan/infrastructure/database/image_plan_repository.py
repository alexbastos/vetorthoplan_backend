from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.domain.planning import ImagePlan
from vetorthoplan.infrastructure.database.models import ImagePlanModel


class SqlAlchemyImagePlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: UUID, image_id: UUID) -> ImagePlan | None:
        model = await self._session.scalar(
            select(ImagePlanModel).where(
                ImagePlanModel.tenant_id == tenant_id,
                ImagePlanModel.image_id == image_id,
            )
        )
        return self._to_domain(model) if model else None

    async def add(self, plan: ImagePlan) -> ImagePlan:
        self._session.add(
            ImagePlanModel(
                id=plan.id,
                tenant_id=plan.tenant_id,
                case_id=plan.case_id,
                image_id=plan.image_id,
                revision=plan.revision,
                document=plan.document,
                created_by=plan.created_by,
                created_at=plan.created_at,
                updated_at=plan.updated_at,
            )
        )
        await self._session.flush()
        return plan

    async def save(self, plan: ImagePlan, expected_revision: int) -> ImagePlan | None:
        result = await self._session.execute(
            update(ImagePlanModel)
            .where(
                ImagePlanModel.tenant_id == plan.tenant_id,
                ImagePlanModel.image_id == plan.image_id,
                ImagePlanModel.revision == expected_revision,
            )
            .values(
                revision=plan.revision,
                document=plan.document,
                updated_at=plan.updated_at,
            )
        )
        await self._session.flush()
        return plan if result.rowcount == 1 else None

    @staticmethod
    def _to_domain(model: ImagePlanModel) -> ImagePlan:
        return ImagePlan(
            id=model.id,
            tenant_id=model.tenant_id,
            case_id=model.case_id,
            image_id=model.image_id,
            revision=model.revision,
            document=dict(model.document),
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
