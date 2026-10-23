from uuid import UUID


class IdempotencyKeyConflictError(ValueError):
    """An idempotency key was reused for a different request."""


class CaseNotFoundError(LookupError):
    """Raised when a case is not visible in the active tenant."""

    def __init__(self, case_id: UUID) -> None:
        super().__init__("Caso clínico não encontrado.")
        self.case_id = case_id


class CaseDeletionConflictError(ValueError):
    def __init__(self, case_id: UUID, reason: str) -> None:
        super().__init__("Não é possível excluir o caso enquanto houver upload ou processamento ativo.")
        self.case_id = case_id
        self.reason = reason


class ImageUploadLimitExceededError(ValueError):
    def __init__(self, case_id: UUID, limit: int) -> None:
        super().__init__(f"O caso atingiu o limite de {limit} uploads de imagem.")
        self.case_id = case_id
        self.limit = limit


class ImageUploadDuplicateError(ValueError):
    def __init__(self, existing_image_id: UUID | None = None) -> None:
        super().__init__("Este arquivo já foi adicionado a este caso.")
        self.existing_image_id = existing_image_id


class ImageUploadIdempotencyConflictError(ValueError):
    def __init__(self) -> None:
        super().__init__("A chave de idempotência da sessão já foi usada com outros metadados.")


class ImageUploadNotFoundError(LookupError):
    def __init__(self, upload_id: UUID) -> None:
        super().__init__("Sessão de upload não encontrada.")
        self.upload_id = upload_id


class ImageUploadExpiredError(ValueError):
    def __init__(self, upload_id: UUID) -> None:
        super().__init__("A sessão expirou antes do envio do arquivo.")
        self.upload_id = upload_id


class ImageUploadCancelledError(ValueError):
    def __init__(self, upload_id: UUID) -> None:
        super().__init__("A sessão de upload foi cancelada.")
        self.upload_id = upload_id


class ImageUploadSessionNotPendingError(ValueError):
    def __init__(self, upload_id: UUID) -> None:
        super().__init__("A sessão idempotente já avançou; não será emitida outra URL de upload.")
        self.upload_id = upload_id


class ImageUploadCancellationConflictError(ValueError):
    def __init__(self, upload_id: UUID) -> None:
        super().__init__("Somente sessões de upload pendentes podem ser canceladas.")
        self.upload_id = upload_id


class ImageUploadObjectInvalidError(ValueError):
    def __init__(self, upload_id: UUID, reason: str) -> None:
        messages = {
            "object_not_found": "O arquivo ainda não está disponível no storage.",
            "uploaded_before_session": "O arquivo armazenado é anterior à sessão informada.",
            "size_mismatch": "O tamanho armazenado não corresponde ao declarado.",
            "media_type_mismatch": "O tipo armazenado não corresponde ao declarado.",
            "checksum_mismatch": "O checksum armazenado não corresponde ao declarado.",
            "upload_id_mismatch": "O arquivo não pertence à sessão informada.",
        }
        super().__init__(messages[reason])
        self.upload_id = upload_id
        self.reason = reason


class ImageNotFoundError(LookupError):
    def __init__(self, image_id: UUID) -> None:
        super().__init__("Imagem não encontrada.")
        self.image_id = image_id


class ImageDeletionConflictError(ValueError):
    def __init__(self, image_id: UUID) -> None:
        super().__init__(
            "Não é possível excluir durante upload ativo ou job QUEUED/PROCESSING."
        )
        self.image_id = image_id


class ImagePreviewUnavailableError(ValueError):
    def __init__(self, image_id: UUID) -> None:
        super().__init__("A prévia da imagem ainda não está disponível.")
        self.image_id = image_id


class ImageNotReadyError(ValueError):
    def __init__(self, image_id: UUID) -> None:
        super().__init__("A imagem precisa estar pronta antes do planejamento.")
        self.image_id = image_id


class PlanRevisionConflictError(ValueError):
    def __init__(self, current_revision: int) -> None:
        super().__init__("O plano foi alterado em outra sessão.")
        self.current_revision = current_revision


class IngestionJobNotFoundError(LookupError):
    def __init__(self, job_id: UUID) -> None:
        super().__init__("Job de ingestão não encontrado.")
        self.job_id = job_id


class IngestionJobRetryNotAllowedError(ValueError):
    def __init__(self, job_id: UUID) -> None:
        super().__init__("Somente jobs FAILED podem ser reenfileirados manualmente.")
        self.job_id = job_id


class ImageContentRejectedError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
