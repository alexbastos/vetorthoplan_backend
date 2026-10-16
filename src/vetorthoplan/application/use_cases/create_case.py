import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256

from vetorthoplan.application.context import TenantContext
from vetorthoplan.application.ports import CaseRepository, Clock, IdGenerator
from vetorthoplan.domain.cases import BiologicalSex, Case


@dataclass(frozen=True, slots=True)
class CreateCaseCommand:
    title: str
    animal_name: str
    species: str
    breed: str | None = None
    sex: BiologicalSex | None = None
    birth_date: date | None = None
    approximate_age_months: int | None = None
    weight_kg: Decimal | None = None
    clinical_notes: str | None = None


class CreateCase:
    def __init__(self, repository: CaseRepository, id_generator: IdGenerator, clock: Clock) -> None:
        self._repository = repository
        self._id_generator = id_generator
        self._clock = clock

    async def execute(
        self,
        command: CreateCaseCommand,
        context: TenantContext,
        *,
        idempotency_key: str | None = None,
    ) -> Case:
        case = Case.create(
            case_id=self._id_generator.new(),
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            title=command.title,
            animal_name=command.animal_name,
            species=command.species,
            breed=command.breed,
            sex=command.sex,
            birth_date=command.birth_date,
            approximate_age_months=command.approximate_age_months,
            weight_kg=command.weight_kg,
            clinical_notes=command.clinical_notes,
            now=self._clock.now(),
        )
        if idempotency_key is None:
            return await self._repository.add(case)

        request_body = {
            field: str(value) if value is not None else None
            for field, value in asdict(command).items()
        }
        request_hash = sha256(
            json.dumps(request_body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        key_hash = sha256(idempotency_key.encode()).hexdigest()
        return await self._repository.add_idempotently(
            case,
            key_hash=key_hash,
            request_hash=request_hash,
        )

