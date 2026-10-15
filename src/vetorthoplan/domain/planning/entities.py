from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ImagePlan:
    id: UUID
    tenant_id: UUID
    case_id: UUID
    image_id: UUID
    revision: int
    document: dict[str, object]
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        plan_id: UUID,
        tenant_id: UUID,
        case_id: UUID,
        image_id: UUID,
        document: dict[str, object],
        actor_id: UUID,
        now: datetime,
    ) -> "ImagePlan":
        return cls(
            id=plan_id,
            tenant_id=tenant_id,
            case_id=case_id,
            image_id=image_id,
            revision=1,
            document=dict(document),
            created_by=actor_id,
            created_at=now,
            updated_at=now,
        )

    def revise(self, document: dict[str, object], now: datetime) -> "ImagePlan":
        return replace(
            self,
            revision=self.revision + 1,
            document=dict(document),
            updated_at=now,
        )
