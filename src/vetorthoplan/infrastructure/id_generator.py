from uuid import UUID, uuid4


class UuidGenerator:
    def new(self) -> UUID:
        return uuid4()

