from typing import Protocol

from vetorthoplan.domain.planning.rotation_table import TploRotationTable


class TploRotationTableRepository(Protocol):
    async def get_active(self) -> TploRotationTable | None: ...
