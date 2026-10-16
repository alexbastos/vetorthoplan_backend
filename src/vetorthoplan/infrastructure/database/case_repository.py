from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.application.errors import IdempotencyKeyConflictError
from vetorthoplan.application.ports import CaseCursor, CasePage
from vetorthoplan.domain.cases import BiologicalSex, Case, CaseStatus
from vetorthoplan.infrastructure.database.models import CaseIdempotencyModel, CaseModel


class SqlAlchemyCaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, case: Case) -> Case:
        model = CaseModel(
            id=case.id,
            tenant_id=case.tenant_id,
            title=case.title,
            animal_name=case.animal_name,
            species=case.species,
            breed=case.breed,
            sex=case.sex.value if case.sex else None,
            birth_date=case.birth_date,
            approximate_age_months=case.approximate_age_months,
            weight_kg=case.weight_kg,
            clinical_notes=case.clinical_notes,
            status=case.status.value,
            created_by=case.created_by,
            created_at=case.created_at,
            updated_at=case.updated_at,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def add_idempotently(
        self,
        case: Case,
        *,
        key_hash: str,
        request_hash: str,
    ) -> Case:
        record_id = case.id
        statement = (
            pg_insert(CaseIdempotencyModel)
            .values(
                id=record_id,
                tenant_id=case.tenant_id,
                actor_id=case.created_by,
                operation="CREATE_CASE",
                key_hash=key_hash,
                request_hash=request_hash,
                resource_id=case.id,
                created_at=case.created_at,
            )
            .on_conflict_do_nothing(constraint="uq_case_idempotency_scope")
        )
        result = await self._session.execute(statement)
        if result.rowcount == 0:
            existing = await self._session.scalar(
                select(CaseIdempotencyModel).where(
                    CaseIdempotencyModel.tenant_id == case.tenant_id,
                    CaseIdempotencyModel.actor_id == case.created_by,
                    CaseIdempotencyModel.operation == "CREATE_CASE",
                    CaseIdempotencyModel.key_hash == key_hash,
                )
            )
            if existing is None:
                raise RuntimeError("Não foi possível recuperar a chave de idempotência.")
            if existing.request_hash != request_hash:
                raise IdempotencyKeyConflictError
            existing_case = await self.get_by_id(case.tenant_id, existing.resource_id)
            if existing_case is None:
                raise RuntimeError("O caso associado à chave de idempotência não existe.")
            return existing_case

        return await self.add(case)

    async def get_by_id(self, tenant_id: UUID, case_id: UUID) -> Case | None:
        statement = select(CaseModel).where(
            CaseModel.tenant_id == tenant_id,
            CaseModel.id == case_id,
        )
        model = await self._session.scalar(statement)
        return self._to_domain(model) if model else None

    async def list_by_tenant(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        cursor: CaseCursor | None,
        status: CaseStatus | None,
        search: str | None,
    ) -> CasePage:
        filters = [CaseModel.tenant_id == tenant_id]
        search_filter = None

        if status is not None:
            filters.append(CaseModel.status == status.value)

        if search is not None:
            escaped_search = self._escape_like(search)
            pattern = f"%{escaped_search}%"
            search_filter = or_(
                CaseModel.title.ilike(pattern, escape="\\"),
                CaseModel.animal_name.ilike(pattern, escape="\\"),
                CaseModel.species.ilike(pattern, escape="\\"),
                CaseModel.breed.ilike(pattern, escape="\\"),
            )
            filters.append(search_filter)

        count_filters = [CaseModel.tenant_id == tenant_id]
        if search_filter is not None:
            count_filters.append(search_filter)
        count_rows = await self._session.execute(
            select(CaseModel.status, func.count())
            .where(*count_filters)
            .group_by(CaseModel.status)
        )
        status_counts = {case_status: 0 for case_status in CaseStatus}
        status_counts.update(
            {CaseStatus(raw_status): count for raw_status, count in count_rows.all()}
        )

        statement = select(CaseModel).where(*filters)
        if cursor is not None:
            statement = statement.where(
                or_(
                    CaseModel.created_at < cursor.created_at,
                    and_(
                        CaseModel.created_at == cursor.created_at,
                        CaseModel.id < cursor.case_id,
                    ),
                )
            )

        statement = statement.order_by(CaseModel.created_at.desc(), CaseModel.id.desc()).limit(
            limit + 1
        )
        models = list((await self._session.scalars(statement)).all())
        has_next_page = len(models) > limit
        page_models = models[:limit]
        items = tuple(self._to_domain(model) for model in page_models)

        next_cursor = None
        if has_next_page and page_models:
            last_model = page_models[-1]
            next_cursor = CaseCursor(created_at=last_model.created_at, case_id=last_model.id)

        return CasePage(items=items, next_cursor=next_cursor, status_counts=status_counts)

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @staticmethod
    def _to_domain(model: CaseModel) -> Case:
        return Case(
            id=model.id,
            tenant_id=model.tenant_id,
            title=model.title,
            animal_name=model.animal_name,
            species=model.species,
            breed=model.breed,
            sex=BiologicalSex(model.sex) if model.sex else None,
            birth_date=model.birth_date,
            approximate_age_months=model.approximate_age_months,
            weight_kg=model.weight_kg,
            clinical_notes=model.clinical_notes,
            status=CaseStatus(model.status),
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
