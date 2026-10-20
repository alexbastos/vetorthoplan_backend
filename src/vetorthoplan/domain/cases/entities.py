from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from vetorthoplan.domain.cases.errors import CaseValidationError


class CaseStatus(StrEnum):
    """Ciclo de vida do caso clínico.

    DRAFT é atribuído na criação. IN_PLANNING e ARCHIVED são rótulos literais.
    READY ainda não tem transição de negócio definida e não significa conclusão clínica.
    """

    DRAFT = "DRAFT"
    IN_PLANNING = "IN_PLANNING"
    READY = "READY"
    ARCHIVED = "ARCHIVED"


class BiologicalSex(StrEnum):
    FEMALE = "FEMALE"
    MALE = "MALE"
    UNKNOWN = "UNKNOWN"


class AgeSource(StrEnum):
    DECLARED = "DECLARED"
    BIRTH_DATE = "BIRTH_DATE"


@dataclass(frozen=True, slots=True)
class Case:
    id: UUID
    tenant_id: UUID
    title: str
    animal_name: str
    species: str
    breed: str | None
    sex: BiologicalSex | None
    birth_date: date | None
    approximate_age_months: int | None
    age_source: AgeSource | None
    age_reference_date: date | None
    weight_kg: Decimal | None
    clinical_notes: str | None
    status: CaseStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        case_id: UUID,
        tenant_id: UUID,
        actor_id: UUID,
        title: str,
        animal_name: str,
        species: str,
        breed: str | None = None,
        sex: BiologicalSex | None = None,
        birth_date: date | None = None,
        approximate_age_months: int | None = None,
        age_source: AgeSource | None = None,
        age_reference_date: date | None = None,
        weight_kg: Decimal | None = None,
        clinical_notes: str | None = None,
        now: datetime | None = None,
    ) -> Case:
        normalized_title = cls._required_text(title, field="title", max_length=200)
        normalized_animal_name = cls._required_text(
            animal_name,
            field="animal_name",
            max_length=120,
        )
        normalized_species = cls._required_text(species, field="species", max_length=80)
        normalized_breed = cls._optional_text(breed, field="breed", max_length=120)
        normalized_notes = cls._optional_text(
            clinical_notes,
            field="clinical_notes",
            max_length=4_000,
        )

        timestamp = now or datetime.now(UTC)
        if timestamp.tzinfo is None:
            raise CaseValidationError("O relógio deve produzir horário com timezone.")

        if sex is None:
            raise CaseValidationError("sex é obrigatório.", field="sex")

        today = timestamp.date()
        if birth_date is not None and birth_date > today:
            raise CaseValidationError("birth_date não pode estar no futuro.", field="birth_date")

        if approximate_age_months is not None and approximate_age_months < 0:
            raise CaseValidationError(
                "approximate_age_months deve ser maior ou igual a zero.",
                field="approximate_age_months",
            )

        if approximate_age_months is not None and approximate_age_months > 600:
            raise CaseValidationError(
                "approximate_age_months deve ser menor ou igual a 600.",
                field="approximate_age_months",
            )

        reference_date = timestamp.date()
        if birth_date is not None:
            calculated_age = cls._months_completed(birth_date, reference_date)
            if calculated_age > 600:
                raise CaseValidationError(
                    "A idade calculada deve ser menor ou igual a 600 meses.",
                    field="approximate_age_months",
                )
            if approximate_age_months is not None and approximate_age_months != calculated_age:
                raise CaseValidationError(
                    "A idade informada não corresponde à data de nascimento na data de criação do caso.",
                    field="approximate_age_months",
                )
            approximate_age_months = calculated_age
            age_source = AgeSource.BIRTH_DATE
        elif approximate_age_months is not None:
            age_source = AgeSource.DECLARED
        else:
            age_source = None
        age_reference_date = reference_date if age_source is not None else None

        if weight_kg is not None and weight_kg <= 0:
            raise CaseValidationError("weight_kg deve ser maior que zero.", field="weight_kg")

        if weight_kg is not None and weight_kg > Decimal("99999.99"):
            raise CaseValidationError(
                "weight_kg deve ser menor ou igual a 99999.99.",
                field="weight_kg",
            )

        return cls(
            id=case_id,
            tenant_id=tenant_id,
            title=normalized_title,
            animal_name=normalized_animal_name,
            species=normalized_species,
            breed=normalized_breed,
            sex=sex,
            birth_date=birth_date,
            approximate_age_months=approximate_age_months,
            age_source=age_source,
            age_reference_date=age_reference_date,
            weight_kg=weight_kg,
            clinical_notes=normalized_notes,
            status=CaseStatus.DRAFT,
            created_by=actor_id,
            created_at=timestamp,
            updated_at=timestamp,
        )

    @staticmethod
    def _months_completed(birth_date: date, reference_date: date) -> int:
        months = (reference_date.year - birth_date.year) * 12 + reference_date.month - birth_date.month
        anniversary_day = min(birth_date.day, monthrange(reference_date.year, reference_date.month)[1])
        if reference_date.day < anniversary_day:
            months -= 1
        return months

    @staticmethod
    def _required_text(value: str, *, field: str, max_length: int) -> str:
        normalized = value.strip()
        if not normalized:
            raise CaseValidationError(f"{field} é obrigatório.", field=field)
        if len(normalized) > max_length:
            raise CaseValidationError(
                f"{field} deve possuir no máximo {max_length} caracteres.",
                field=field,
            )
        return normalized

    @staticmethod
    def _optional_text(value: str | None, *, field: str, max_length: int) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > max_length:
            raise CaseValidationError(
                f"{field} deve possuir no máximo {max_length} caracteres.",
                field=field,
            )
        return normalized
