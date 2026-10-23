class ImagingValidationError(ValueError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class ImageDisplayNameValidationError(ImagingValidationError):
    """Invalid user-facing image name."""
