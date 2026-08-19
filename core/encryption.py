"""
Encrypt/decrypt sensitive fields (e.g. Cluster.encrypted_token) at rest.

Per the assignment, implementing a full secret-management system (Vault,
KMS, etc.) is out of scope, but "encryption at rest" specifically is
called out as a best practice we should apply even in the exercise - so
tokens are never stored in plaintext in the database, never logged, and
never serialized back in API responses (see clusters/serializers.py).

In production, swap FIELD_ENCRYPTION_KEY for a key pulled from a real
secret manager (e.g. mounted from a Kubernetes Secret backed by a KMS
provider) rather than a plain env var.
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    key = settings.FIELD_ENCRYPTION_KEY
    if not key:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY is not set. Generate one with:\n"
            "  python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"\n"
            "and set it in your environment / .env file."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_value(raw_value: str) -> str:
    if raw_value is None:
        return raw_value
    token = _get_fernet().encrypt(raw_value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_value(encrypted_value: str) -> str:
    if not encrypted_value:
        return encrypted_value
    try:
        return _get_fernet().decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(
            "Could not decrypt stored value - FIELD_ENCRYPTION_KEY may have "
            "changed since this record was written."
        ) from exc
