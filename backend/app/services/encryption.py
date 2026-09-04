from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _get_fernet() -> Fernet:
    if not settings.SMTP_ENCRYPTION_KEY:
        raise RuntimeError("SMTP_ENCRYPTION_KEY is not configured")

    try:
        return Fernet(settings.SMTP_ENCRYPTION_KEY.encode())
    except ValueError as exc:
        raise RuntimeError("SMTP_ENCRYPTION_KEY is invalid") from exc


def encrypt_smtp_password(password: str) -> str:
    return _get_fernet().encrypt(password.encode()).decode()


def decrypt_smtp_password(encrypted_password: str) -> str:
    try:
        return _get_fernet().decrypt(
            encrypted_password.encode()
        ).decode()
    except InvalidToken as exc:
        raise RuntimeError("Unable to decrypt SMTP password") from exc