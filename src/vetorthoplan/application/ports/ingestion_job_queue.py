from datetime import datetime
from typing import Protocol
from uuid import UUID

from vetorthoplan.domain.jobs import IngestionJob


class IngestionJobQueue(Protocol):
    async def enqueue(self, job: IngestionJob) -> IngestionJob:
        """Persiste o job ou devolve o job já agendado para o mesmo upload."""
        ...

    async def get_by_id(self, tenant_id: UUID, job_id: UUID) -> IngestionJob | None: ...

    async def lock_by_id(self, tenant_id: UUID, job_id: UUID) -> IngestionJob | None: ...

    async def get_by_image_id(self, tenant_id: UUID, image_id: UUID) -> IngestionJob | None: ...

    async def lock_by_image_id(self, tenant_id: UUID, image_id: UUID) -> IngestionJob | None: ...

    async def list_for_case(self, tenant_id: UUID, case_id: UUID) -> list[IngestionJob]: ...

    async def claim_next(self, now: datetime) -> IngestionJob | None:
        """Reserva atomicamente o job mais antigo para este worker."""
        ...

    async def save(self, job: IngestionJob) -> IngestionJob: ...
