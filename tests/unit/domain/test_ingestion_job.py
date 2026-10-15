from datetime import UTC, datetime
from uuid import UUID

import pytest

from vetorthoplan.domain.jobs import IngestionJob, IngestionJobStatus


def test_schedule_ingestion_job_starts_queued() -> None:
    scheduled_at = datetime(2026, 9, 17, 14, 0, tzinfo=UTC)

    job = IngestionJob.schedule(
        job_id=UUID("00000000-0000-4000-8000-000000000301"),
        tenant_id=UUID("00000000-0000-4000-8000-000000000302"),
        case_id=UUID("00000000-0000-4000-8000-000000000303"),
        image_id=UUID("00000000-0000-4000-8000-000000000304"),
        upload_id=UUID("00000000-0000-4000-8000-000000000305"),
        scheduled_at=scheduled_at,
    )

    assert job.status == IngestionJobStatus.QUEUED
    assert job.attempts == 0
    assert job.created_at == scheduled_at
    assert job.updated_at == scheduled_at


def test_schedule_ingestion_job_requires_timezone() -> None:
    with pytest.raises(ValueError, match="timezone"):
        IngestionJob.schedule(
            job_id=UUID("00000000-0000-4000-8000-000000000301"),
            tenant_id=UUID("00000000-0000-4000-8000-000000000302"),
            case_id=UUID("00000000-0000-4000-8000-000000000303"),
            image_id=UUID("00000000-0000-4000-8000-000000000304"),
            upload_id=UUID("00000000-0000-4000-8000-000000000305"),
            scheduled_at=datetime(2026, 9, 17, 14, 0),
        )
