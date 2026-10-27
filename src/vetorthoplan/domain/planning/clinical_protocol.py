from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClinicalMeasurementDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,49}$")
    label: str = Field(min_length=1, max_length=120)
    kind: Literal["DISTANCE", "ANGLE"]
    landmarks: list[str] = Field(min_length=2, max_length=3)
    unit: Literal["mm", "degrees"]
    max_absolute_error: float = Field(gt=0, le=1000)

    @model_validator(mode="after")
    def validate_definition(self) -> ClinicalMeasurementDefinition:
        expected_count = 2 if self.kind == "DISTANCE" else 3
        expected_unit = "mm" if self.kind == "DISTANCE" else "degrees"
        if len(self.landmarks) != expected_count:
            raise ValueError(f"{self.kind} exige {expected_count} marcos")
        if len(set(self.landmarks)) != len(self.landmarks):
            raise ValueError("Os marcos de uma medida precisam ser distintos")
        if self.unit != expected_unit:
            raise ValueError(f"{self.kind} exige unidade {expected_unit}")
        return self


class TploClinicalProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=300)
    measurements: list[ClinicalMeasurementDefinition] = Field(max_length=50)
    tpa_max_absolute_error_degrees: float | None = Field(default=None, gt=0, le=90)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> TploClinicalProtocol:
        ids = [measurement.id for measurement in self.measurements]
        if len(ids) != len(set(ids)):
            raise ValueError("IDs de medidas precisam ser únicos")
        reserved = {"TPA", "PLATEAU_AXIS", "TIBIAL_AXIS"}
        if reserved.intersection(ids):
            raise ValueError("IDs de medidas não podem substituir medidas clínicas existentes")
        return self


def parse_clinical_protocol(raw: str | None) -> TploClinicalProtocol | None:
    if raw is None or not raw.strip():
        return None
    return TploClinicalProtocol.model_validate(json.loads(raw))
