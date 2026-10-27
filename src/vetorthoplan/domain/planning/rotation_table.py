from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TploRotationTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=300)
    entries: list[dict[str, str | int | float]] = Field(min_length=1, max_length=5_000)
    source_url: str | None = Field(default=None, max_length=1000)
    source_asset_url: str | None = Field(default=None, max_length=1000)
    target_slope_degrees: float | None = Field(default=None, gt=0, lt=90)
    entries_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


def parse_rotation_table(
    version: str | None,
    source: str | None,
    raw_entries: str | None,
) -> TploRotationTable | None:
    values = (version, source, raw_entries)
    if not any(value is not None and value.strip() for value in values):
        return None
    if any(value is None or not value.strip() for value in values):
        raise ValueError("Versão, fonte e conteúdo da tabela TPLO devem ser configurados juntos")

    try:
        payload: Any = json.loads(raw_entries or "")
    except json.JSONDecodeError as exc:
        raise ValueError("JSON da tabela TPLO inválido") from exc

    if not isinstance(payload, list) or not payload or len(payload) > 5_000:
        raise ValueError("A tabela TPLO deve conter de 1 a 5000 linhas")
    for index, row in enumerate(payload):
        if not isinstance(row, dict) or not row:
            raise ValueError(f"Linha {index} da tabela TPLO deve ser um objeto não vazio")
        for key, value in row.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"Nome de coluna inválido na linha {index} da tabela TPLO")
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise ValueError(f"Valor inválido na coluna {key} da linha {index} da tabela TPLO")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"Valor numérico não finito na coluna {key} da tabela TPLO")

        for field in ("tpa_degrees", "blade_diameter_mm", "rotation_mm"):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"A linha {index} precisa conter um valor numérico em {field}")
            if not math.isfinite(value):
                raise ValueError(f"Valor não finito em {field} na linha {index} da tabela TPLO")
        if not 0 <= row["tpa_degrees"] <= 90:
            raise ValueError(f"TPA fora do intervalo permitido na linha {index} da tabela TPLO")
        if row["blade_diameter_mm"] <= 0 or row["rotation_mm"] <= 0:
            raise ValueError(f"Diâmetro e rotação devem ser positivos na linha {index} da tabela TPLO")

    combinations = {(row["tpa_degrees"], row["blade_diameter_mm"]) for row in payload}
    if len(combinations) != len(payload):
        raise ValueError("A tabela TPLO contém combinações repetidas de TPA e diâmetro")

    canonical_entries = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    entries_sha256 = hashlib.sha256(canonical_entries.encode("utf-8")).hexdigest()
    return TploRotationTable(
        version=version,
        source=source,
        entries=payload,
        entries_sha256=entries_sha256,
    )


def matches_numeric_filter(value: object, expected: float) -> bool:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return False
    try:
        actual_decimal = Decimal(str(value))
        expected_decimal = Decimal(str(expected))
    except InvalidOperation:
        return False
    return actual_decimal.is_finite() and actual_decimal == expected_decimal
