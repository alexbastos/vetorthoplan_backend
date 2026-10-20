from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.infrastructure.database.models import (
    AuthOrganizationMappingModel,
    AuthSubjectMappingModel,
)


async def resolve_actor_id(session: AsyncSession, issuer: str, subject: str) -> UUID:
    statement = (
        insert(AuthSubjectMappingModel)
        .values(
            actor_id=uuid4(),
            issuer=issuer,
            subject=subject,
            created_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(constraint="uq_auth_subject_mappings_issuer_subject")
    )
    await session.execute(statement)
    mapping = await session.scalar(
        select(AuthSubjectMappingModel).where(
            AuthSubjectMappingModel.issuer == issuer,
            AuthSubjectMappingModel.subject == subject,
        )
    )
    if mapping is None:
        raise RuntimeError("Não foi possível resolver o mapeamento do usuário autenticado.")
    return mapping.actor_id


async def resolve_tenant_id(session: AsyncSession, issuer: str, organization_id: str) -> UUID:
    statement = (
        insert(AuthOrganizationMappingModel)
        .values(
            tenant_id=uuid4(),
            issuer=issuer,
            organization_id=organization_id,
            created_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(constraint="uq_auth_organization_mappings_issuer_organization")
    )
    await session.execute(statement)
    mapping = await session.scalar(
        select(AuthOrganizationMappingModel).where(
            AuthOrganizationMappingModel.issuer == issuer,
            AuthOrganizationMappingModel.organization_id == organization_id,
        )
    )
    if mapping is None:
        raise RuntimeError("Não foi possível resolver o mapeamento da organização autenticada.")
    return mapping.tenant_id
