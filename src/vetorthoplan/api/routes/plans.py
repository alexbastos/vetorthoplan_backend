from uuid import UUID

from fastapi import APIRouter

from vetorthoplan.api.dependencies import (
    GetImagePlanDependency,
    SaveImagePlanDependency,
    TenantContextDependency,
)
from vetorthoplan.api.schemas import (
    ErrorResponse,
    ImagePlanResponse,
    SaveImagePlanRequest,
)

router = APIRouter(prefix="/api/v1")


@router.get(
    "/images/{image_id}/plan",
    response_model=ImagePlanResponse,
    tags=["Planning"],
    responses={404: {"model": ErrorResponse}},
)
async def get_image_plan(
    image_id: UUID,
    context: TenantContextDependency,
    use_case: GetImagePlanDependency,
) -> ImagePlanResponse:
    plan = await use_case.execute(image_id, context)
    return ImagePlanResponse(**{
        field: getattr(plan, field) for field in ImagePlanResponse.model_fields
    })


@router.put(
    "/images/{image_id}/plan",
    response_model=ImagePlanResponse,
    tags=["Planning"],
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def save_image_plan(
    image_id: UUID,
    payload: SaveImagePlanRequest,
    context: TenantContextDependency,
    use_case: SaveImagePlanDependency,
) -> ImagePlanResponse:
    plan = await use_case.execute(
        image_id,
        payload.base_revision,
        payload.document.model_dump(mode="json"),
        context,
    )
    return ImagePlanResponse(**{
        field: getattr(plan, field) for field in ImagePlanResponse.model_fields
    })
