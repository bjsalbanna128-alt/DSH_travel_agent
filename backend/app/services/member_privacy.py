"""Normalize, encrypt and mask member contact data before database writes."""

import base64
import binascii
import hmac
import re
import secrets
import unicodedata

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException

from app.config import settings

KEY_VERSION = b"\x01"


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def normalize_phone(value: str) -> str:
    phone = re.sub(r"[\s()\-]+", "", _normalize(value))
    if not re.fullmatch(r"\+?[0-9]{3,18}", phone):
        raise HTTPException(422, "请输入有效的电话号码。")
    return phone


def normalize_document(value: str) -> str:
    number = re.sub(r"[\s\-]+", "", _normalize(value)).upper()
    if not re.fullmatch(r"[A-Z0-9]{1,40}", number):
        raise HTTPException(422, "证件号码须由字母和数字组成，请输入完整号码。")
    return number


def mask_number(value: str) -> str:
    if len(value) <= 6:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


def mask_name(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "*" * (len(value) - 1)


class MemberPrivacy:
    def __init__(self):
        try:
            master = base64.b64decode(settings.pii_encryption_key.get_secret_value(), altchars=b"-_", validate=True)
        except (binascii.Error, ValueError):
            master = b""
        if len(master) < 32:
            raise HTTPException(503, "敏感资料保存暂不可用。")
        self._cipher = AESGCM(self._derive(master, b"encryption"))
        self._digest_key = self._derive(master, b"document-deduplication")

    @staticmethod
    def _derive(master: bytes, purpose: bytes) -> bytes:
        return HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None,
            info=b"travel-agent/membership/v1/" + purpose,
        ).derive(master)

    def encrypt(self, value: str, *, context: bytes) -> bytes:
        nonce = secrets.token_bytes(12)
        return KEY_VERSION + nonce + self._cipher.encrypt(nonce, value.encode(), KEY_VERSION + context)

    def decrypt(self, envelope: bytes, *, context: bytes) -> str:
        if envelope[:1] != KEY_VERSION or len(envelope) < 29:
            raise ValueError("Invalid member encryption envelope")
        nonce = envelope[1:13]
        return self._cipher.decrypt(nonce, envelope[13:], KEY_VERSION + context).decode()

    def document_digest(self, kind: str, number: str) -> str:
        return hmac.digest(self._digest_key, f"{kind}\0{number}".encode(), "sha256").hex()
