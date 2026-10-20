from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from vetorthoplan.domain.cases import BiologicalSex, Case, CaseStatus, CaseValidationError

CASE_ID = UUID("00000000-0000-4000-8000-000000000010")
TENANT_ID = UUID("00000000-0000-4000-8000-000000000011")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000012")
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def test_create_case_normalizes_text_and_starts_as_draft() -> None:
    case = Case.create(
        case_id=CASE_ID,
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        title="  Planejamento TPLO  ",
        animal_name="  Paciente sintético  ",
        species="  Canina  ",
        breed="  Labrador  ",
        sex=BiologicalSex.UNKNOWN,
        weight_kg=Decimal("31.40"),
        now=NOW,
    )

    assert case.title == "Planejamento TPLO"
    assert case.animal_name == "Paciente sintético"
    assert case.species == "Canina"
    assert case.breed == "Labrador"
    assert case.status is CaseStatus.DRAFT
    assert case.tenant_id == TENANT_ID
    assert case.created_by == ACTOR_ID
    assert case.created_at == NOW


def test_create_case_accepts_coherent_birth_date_and_age() -> None:
    case = Case.create(
        case_id=CASE_ID,
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        title="TPLO",
        animal_name="Paciente sintético",
        species="Canina",
        sex=BiologicalSex.UNKNOWN,
        birth_date=date(2020, 9, 15),
        approximate_age_months=72,
        now=NOW,
    )
    assert case.approximate_age_months == 72
    assert case.age_source.value == "BIRTH_DATE"
    assert case.age_reference_date == NOW.date()


def test_create_case_rejects_incoherent_birth_date_and_age() -> None:
    with pytest.raises(CaseValidationError, match="não corresponde") as error:
        Case.create(
            case_id=CASE_ID,
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            title="TPLO",
            animal_name="Paciente sintético",
            species="Canina",
            sex=BiologicalSex.UNKNOWN,
            birth_date=date(2020, 9, 15),
            approximate_age_months=71,
            now=NOW,
        )
    assert error.value.field == "approximate_age_months"


def test_create_case_rejects_non_positive_weight() -> None:
    with pytest.raises(CaseValidationError, match="maior que zero"):
        Case.create(
            case_id=CASE_ID,
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            title="TPLO",
            animal_name="Paciente sintético",
            species="Canina",
            sex=BiologicalSex.UNKNOWN,
            weight_kg=Decimal("0"),
            now=NOW,
        )


def test_create_case_uses_injected_clock_to_reject_future_birth_date() -> None:
    with pytest.raises(CaseValidationError, match="futuro"):
        Case.create(
            case_id=CASE_ID,
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            title="TPLO",
            animal_name="Paciente sintético",
            species="Canina",
            sex=BiologicalSex.UNKNOWN,
            birth_date=date(2026, 9, 16),
            now=NOW,
        )
