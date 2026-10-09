import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet():
    key = os.environ.get('STUDIO_TOKEN_KEY', '')
    if len(key) < 16:
        return None
    raw = hashlib.sha256(('studio-gh-token:' + key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def available() -> bool:
    return _fernet() is not None


def encrypt(value: str) -> str:
    f = _fernet()
    if f is None:
        raise RuntimeError('key missing')
    return f.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    f = _fernet()
    if f is None or not value:
        return ''
    try:
        return f.decrypt(value.encode()).decode()
    except InvalidToken:
        return ''
