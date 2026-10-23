from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.errors import (
    ImageNotFoundError,
    ImageNotReadyError,
    PlanRevisionConflictError,
)
from vetorthoplan.application.ports import (
    Clock,
    IdGenerator,
    ImagePlanRepository,
    ImageUploadRepository,
)
from vetorthoplan.domain.imaging import ImageUploadStatus
from vetorthoplan.domain.planning import ImagePlan


@dataclass(frozen=True, slots=True)
class ImagePlanView:
    image_id: UUID
    revision: int
    document: dict[str, object]
    updated_at: datetime | None


class GetImagePlan:
    def __init__(self, plans: ImagePlanRepository, images: ImageUploadRepository) -> None:
        self._plans = plans
        self._images = images

    async def execute(self, image_id: UUID, context: TenantContext) -> ImagePlanView:
        image = await self._images.get_by_image_id(context.tenant_id, image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        if image.status != ImageUploadStatus.READY:
            raise ImageNotReadyError(image_id)
        plan = await self._plans.get(context.tenant_id, image_id)
        if plan is None:
            return ImagePlanView(
                image_id=image_id,
                revision=0,
                document={"schema_version": 1, "calibration": None, "tplo": None, "objects": []},
                updated_at=None,
            )
        return ImagePlanView(image_id, plan.revision, plan.document, plan.updated_at)


class SaveImagePlan:
    def __init__(
        self,
        *,
        plans: ImagePlanRepository,
        images: ImageUploadRepository,
        id_generator: IdGenerator,
        clock: Clock,
    ) -> None:
        self._plans = plans
        self._images = images
        self._id_generator = id_generator
        self._clock = clock

    async def execute(
        self,
        image_id: UUID,
        base_revision: int,
        document: dict[str, object],
        context: TenantContext,
    ) -> ImagePlanView:
        lock_case = getattr(self._images, "lock_case_for_image", None)
        if lock_case is not None and not await lock_case(context.tenant_id, image_id):
            raise ImageNotFoundError(image_id)
        image = await self._images.get_by_image_id(context.tenant_id, image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        if image.status != ImageUploadStatus.READY:
            raise ImageNotReadyError(image_id)
        current = await self._plans.get(context.tenant_id, image_id)
        if current is None:
            if base_revision != 0:
                raise PlanRevisionConflictError(0)
            saved = await self._plans.add(
                ImagePlan.create(
                    plan_id=self._id_generator.new(),
                    tenant_id=context.tenant_id,
                    case_id=image.case_id,
                    image_id=image.image_id,
                    document=document,
                    actor_id=context.actor_id,
                    now=self._clock.now(),
                )
            )
            if saved is None:
                latest = await self._plans.get(context.tenant_id, image_id)
                raise PlanRevisionConflictError(latest.revision if latest else 0)
        else:
            if current.revision != base_revision:
                raise PlanRevisionConflictError(current.revision)
            saved = await self._plans.save(
                current.revise(document, self._clock.now()),
                expected_revision=base_revision,
            )
            if saved is None:
                latest = await self._plans.get(context.tenant_id, image_id)
                raise PlanRevisionConflictError(latest.revision if latest else 0)
        return ImagePlanView(saved.image_id, saved.revision, saved.document, saved.updated_at)
