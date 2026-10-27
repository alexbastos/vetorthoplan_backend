import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vetorthoplan.domain.planning.rotation_table import TploRotationTable
from vetorthoplan.infrastructure.database.models import TploRotationTableModel


class SqlAlchemyTploRotationTableRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self) -> TploRotationTable | None:
        model = await self._session.scalar(
            select(TploRotationTableModel).where(TploRotationTableModel.is_active.is_(True))
        )
        if model is None:
            return None
        canonical_entries = json.dumps(
            model.entries,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        digest = hashlib.sha256(canonical_entries.encode("utf-8")).hexdigest()
        if digest != model.entries_sha256:
            raise ValueError("O hash da tabela de rotação TPLO persistida não confere")
        return TploRotationTable(
            version=model.table_version,
            source=model.source,
            entries=model.entries,
            source_url=model.source_url,
            source_asset_url=model.source_asset_url,
            target_slope_degrees=float(model.target_slope_degrees),
            entries_sha256=digest,
        )
