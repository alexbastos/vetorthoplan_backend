class CaseValidationError(ValueError):
    """Raised when a clinical case violates a domain invariant."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field

