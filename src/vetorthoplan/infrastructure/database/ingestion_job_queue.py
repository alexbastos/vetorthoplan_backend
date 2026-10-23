from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.domain.jobs import IngestionJob, IngestionJobStatus
from vetorthoplan.infrastructure.database.models import IngestionJobModel


class SqlAlchemyIngestionJobQueue:
    """Fila durável no PostgreSQL, deduplicada pelo upload de origem."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, job: IngestionJob) -> IngestionJob:
        statement = (
            insert(IngestionJobModel)
            .values(
                id=job.id,
                tenant_id=job.tenant_id,
                case_id=job.case_id,
                image_id=job.image_id,
                upload_id=job.upload_id,
                status=job.status.value,
                attempts=job.attempts,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
            .on_conflict_do_nothing(index_elements=[IngestionJobModel.upload_id])
            .returning(IngestionJobModel)
        )
        model = await self._session.scalar(statement)
        if model is None:
            model = await self._session.scalar(
                select(IngestionJobModel).where(
                    IngestionJobModel.tenant_id == job.tenant_id,
                    IngestionJobModel.upload_id == job.upload_id,
                )
            )
        if model is None:  # pragma: no cover - proteção contra inconsistência transacional
            raise RuntimeError("Não foi possível recuperar o job de ingestão agendado.")
        await self._session.flush()
        return self._to_domain(model)

    async def get_by_id(self, tenant_id: UUID, job_id: UUID) -> IngestionJob | None:
        statement = select(IngestionJobModel).where(
            IngestionJobModel.tenant_id == tenant_id,
            IngestionJobModel.id == job_id,
        )
        model = await self._session.scalar(statement)
        return self._to_domain(model) if model else None

    async def lock_by_id(self, tenant_id: UUID, job_id: UUID) -> IngestionJob | None:
        model = await self._session.scalar(
            select(IngestionJobModel)
            .where(
                IngestionJobModel.tenant_id == tenant_id,
                IngestionJobModel.id == job_id,
            )
            .with_for_update()
        )
        return self._to_domain(model) if model else None

    async def get_by_image_id(self, tenant_id: UUID, image_id: UUID) -> IngestionJob | None:
        statement = select(IngestionJobModel).where(
            IngestionJobModel.tenant_id == tenant_id,
            IngestionJobModel.image_id == image_id,
        )
        model = await self._session.scalar(statement)
        return self._to_domain(model) if model else None

    async def lock_by_image_id(self, tenant_id: UUID, image_id: UUID) -> IngestionJob | None:
        model = await self._session.scalar(
            select(IngestionJobModel)
            .where(
                IngestionJobModel.tenant_id == tenant_id,
                IngestionJobModel.image_id == image_id,
            )
            .with_for_update()
        )
        return self._to_domain(model) if model else None

    async def list_for_case(self, tenant_id: UUID, case_id: UUID) -> list[IngestionJob]:
        models = (await self._session.scalars(
            select(IngestionJobModel).where(
                IngestionJobModel.tenant_id == tenant_id,
                IngestionJobModel.case_id == case_id,
            ).with_for_update()
        )).all()
        return [self._to_domain(model) for model in models]

    async def claim_next(self, now: datetime) -> IngestionJob | None:
        statement = (
            select(IngestionJobModel)
            .where(IngestionJobModel.status == IngestionJobStatus.QUEUED.value)
            .order_by(IngestionJobModel.created_at, IngestionJobModel.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        model = await self._session.scalar(statement)
        if model is None:
            return None
        job = self._to_domain(model).start(started_at=now)
        model.status = job.status.value
        model.attempts = job.attempts
        model.started_at = job.started_at
        model.updated_at = job.updated_at
        model.error_code = None
        await self._session.flush()
        return job

    async def save(self, job: IngestionJob) -> IngestionJob:
        statement = (
            update(IngestionJobModel)
            .where(
                IngestionJobModel.tenant_id == job.tenant_id,
                IngestionJobModel.id == job.id,
            )
            .values(
                status=job.status.value,
                attempts=job.attempts,
                updated_at=job.updated_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                error_code=job.error_code,
            )
        )
        await self._session.execute(statement)
        await self._session.flush()
        return job

    @staticmethod
    def _to_domain(model: IngestionJobModel) -> IngestionJob:
        return IngestionJob(
            id=model.id,
            tenant_id=model.tenant_id,
            case_id=model.case_id,
            image_id=model.image_id,
            upload_id=model.upload_id,
            status=IngestionJobStatus(model.status),
            attempts=model.attempts,
            created_at=model.created_at,
            updated_at=model.updated_at,
            started_at=model.started_at,
            finished_at=model.finished_at,
            error_code=model.error_code,
        )
