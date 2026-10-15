from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class IngestionJobStatus(StrEnum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class IngestionJob:
    id: UUID
    tenant_id: UUID
    case_id: UUID
    image_id: UUID
    upload_id: UUID
    status: IngestionJobStatus
    attempts: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None

    @classmethod
    def schedule(
        cls,
        *,
        job_id: UUID,
        tenant_id: UUID,
        case_id: UUID,
        image_id: UUID,
        upload_id: UUID,
        scheduled_at: datetime,
    ) -> IngestionJob:
        if scheduled_at.tzinfo is None:
            raise ValueError("scheduled_at deve conter timezone.")
        return cls(
            id=job_id,
            tenant_id=tenant_id,
            case_id=case_id,
            image_id=image_id,
            upload_id=upload_id,
            status=IngestionJobStatus.QUEUED,
            attempts=0,
            created_at=scheduled_at,
            updated_at=scheduled_at,
        )

    def start(self, *, started_at: datetime) -> IngestionJob:
        self._require_timezone(started_at)
        if self.status == IngestionJobStatus.PROCESSING:
            return self
        if self.status != IngestionJobStatus.QUEUED:
            raise ValueError("Somente jobs enfileirados podem iniciar.")
        return replace(
            self,
            status=IngestionJobStatus.PROCESSING,
            attempts=self.attempts + 1,
            started_at=started_at,
            updated_at=started_at,
            error_code=None,
        )

    def succeed(self, *, finished_at: datetime) -> IngestionJob:
        return self._finish(IngestionJobStatus.SUCCEEDED, finished_at, None)

    def reject(self, *, finished_at: datetime, error_code: str) -> IngestionJob:
        return self._finish(IngestionJobStatus.REJECTED, finished_at, error_code)

    def fail(self, *, finished_at: datetime, error_code: str) -> IngestionJob:
        return self._finish(IngestionJobStatus.FAILED, finished_at, error_code)

    def _finish(
        self,
        status: IngestionJobStatus,
        finished_at: datetime,
        error_code: str | None,
    ) -> IngestionJob:
        self._require_timezone(finished_at)
        if self.status != IngestionJobStatus.PROCESSING:
            raise ValueError("Somente jobs em processamento podem ser finalizados.")
        if error_code is not None and (not error_code or len(error_code) > 64):
            raise ValueError("error_code inválido.")
        return replace(
            self,
            status=status,
            finished_at=finished_at,
            updated_at=finished_at,
            error_code=error_code,
        )

    @staticmethod
    def _require_timezone(value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError("Datas do job devem conter timezone.")
