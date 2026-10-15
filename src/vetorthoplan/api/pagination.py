from base64 import b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from datetime import datetime
from uuid import UUID

from vetorthoplan.application.ports import CaseCursor


class InvalidCursorError(ValueError):
    """Raised when an opaque pagination cursor cannot be decoded."""


def encode_case_cursor(cursor: CaseCursor | None) -> str | None:
    if cursor is None:
        return None
    payload = f"{cursor.created_at.isoformat()}|{cursor.case_id}".encode()
    return urlsafe_b64encode(payload).decode().rstrip("=")


def decode_case_cursor(value: str | None) -> CaseCursor | None:
    if value is None:
        return None

    try:
        padding = "=" * (-len(value) % 4)
        payload = b64decode(value + padding, altchars=b"-_", validate=True).decode()
        created_at_text, case_id_text = payload.split("|", maxsplit=1)
        created_at = datetime.fromisoformat(created_at_text)
        case_id = UUID(case_id_text)
    except (Base64Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidCursorError("Cursor de paginação inválido.") from exc

    if created_at.tzinfo is None:
        raise InvalidCursorError("Cursor de paginação inválido.")

    return CaseCursor(created_at=created_at, case_id=case_id)
