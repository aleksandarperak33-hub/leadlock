"""
Encryption utilities for sensitive data (CRM API keys, tokens, etc.).
Uses Fernet symmetric encryption with the configured ENCRYPTION_KEY.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _get_fernet():
    """Get a Fernet cipher using the configured encryption key."""
    from cryptography.fernet import Fernet
    from src.config import get_settings
    settings = get_settings()

    key = settings.encryption_key
    if not key:
        logger.warning("ENCRYPTION_KEY not configured — storing values as-is")
        return None

    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a string value. Returns the encrypted token as a string.
    Falls back to storing plaintext if encryption key is not configured.
    """
    if not plaintext:
        return plaintext

    fernet = _get_fernet()
    if fernet is None:
        return plaintext

    try:
        return fernet.encrypt(plaintext.encode()).decode()
    except Exception as e:
        logger.error("Encryption failed: %s", str(e))
        return plaintext


def decrypt_value(encrypted: str) -> Optional[str]:
    """
    Decrypt a string value. Returns the plaintext string.
    Falls back to returning the value as-is if decryption fails
    (handles legacy unencrypted values).
    """
    if not encrypted:
        return encrypted

    fernet = _get_fernet()
    if fernet is None:
        return encrypted

    try:
        return fernet.decrypt(encrypted.encode()).decode()
    except Exception:
        # Value may be legacy plaintext — return as-is
        return encrypted
