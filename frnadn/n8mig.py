"""N8 migration package – encrypted transfer of a whole installation to the HobbyRadioPortal (standard library only).

The same file is part of HBlink4-FreeRadioID (dashboard/n8mig.py) and the HobbyRadioPortal (portal/n8mig.py); a test
in the portal checks that both copies are identical.

Umzugscode (one-time migration code), shown once on the old server:

    <prefix>_<id>.<secret>        e.g.  hb4m_3f9c21ab.Q2xk…   (id: 8 hex, secret: 32 url-safe characters)

The old server stores only SHA-256(secret). The new server sends the whole code as ``Authorization: Bearer``; the
package is encrypted with a key derived from the secret, so it stays confidential even over plain HTTP.

File format (encrypt-then-MAC):

    b"N8MIG1\\n" | salt (16) | nonce (16) | ciphertext | tag (32)
    enc_key, mac_key = scrypt(secret, salt, n=2^14, r=8, p=1, 64 bytes) split in two
    ciphertext       = plaintext XOR keystream, keystream block i (1 MiB) = SHAKE-256(enc_key | nonce | i (8 bytes BE))
    tag              = HMAC-SHA-256(mac_key, header | ciphertext)

Decryption writes to the target and deletes it again if the tag does not match – nothing unchecked is used.
"""
import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path

MAGIC = b"N8MIG1\n"
CHUNK = 1 << 20
CODE_RE = re.compile(r"^([a-z0-9]{2,8})_([0-9a-f]{8})\.([A-Za-z0-9_-]{32})$")


class MigrationError(Exception):
    pass


def new_code(prefix: str):
    """Returns (code, id, sha256 of the secret). Only the hash is stored."""
    cid, secret = secrets.token_hex(4), secrets.token_urlsafe(24)[:32]
    while len(secret) < 32:
        secret += secrets.token_urlsafe(8)
    secret = secret[:32]
    return f"{prefix}_{cid}.{secret}", cid, hashlib.sha256(secret.encode()).hexdigest()


def parse_code(code: str):
    """Returns (prefix, id, secret) or raises MigrationError."""
    m = CODE_RE.match((code or "").strip())
    if not m:
        raise MigrationError("Ungültiger Umzugscode.")
    return m.group(1), m.group(2), m.group(3)


def secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _keys(secret: str, salt: bytes):
    k = hashlib.scrypt(secret.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=64, maxmem=64 * 1024 * 1024)
    return k[:32], k[32:]


def _xor(data: bytes, enc: bytes, nonce: bytes, i: int) -> bytes:
    ks = hashlib.shake_256(enc + nonce + i.to_bytes(8, "big")).digest(len(data))
    return (int.from_bytes(data, "big") ^ int.from_bytes(ks, "big")).to_bytes(len(data), "big")


def encrypt_file(src, dst, secret: str) -> None:
    salt, nonce = os.urandom(16), os.urandom(16)
    enc, mac = _keys(secret, salt)
    header = MAGIC + salt + nonce
    h = hmac.new(mac, header, hashlib.sha256)
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        os.chmod(dst, 0o600)
        fo.write(header)
        i = 0
        while True:
            block = fi.read(CHUNK)
            if not block:
                break
            c = _xor(block, enc, nonce, i)
            h.update(c)
            fo.write(c)
            i += 1
        fo.write(h.digest())


def decrypt_file(src, dst, secret: str) -> None:
    src, dst = Path(src), Path(dst)
    size = src.stat().st_size
    if size < len(MAGIC) + 32 + 32:
        raise MigrationError("Umzugspaket zu kurz oder leer.")
    with open(src, "rb") as fi:
        header = fi.read(len(MAGIC) + 32)
        if not header.startswith(MAGIC):
            raise MigrationError("Kein N8-Umzugspaket.")
        salt, nonce = header[len(MAGIC):len(MAGIC) + 16], header[len(MAGIC) + 16:]
        enc, mac = _keys(secret, salt)
        h = hmac.new(mac, header, hashlib.sha256)
        left = size - len(header) - 32
        try:
            with open(dst, "wb") as fo:
                os.chmod(dst, 0o600)
                i = 0
                while left > 0:
                    c = fi.read(min(CHUNK, left))
                    if not c:
                        raise MigrationError("Umzugspaket unvollständig.")
                    left -= len(c)
                    h.update(c)
                    fo.write(_xor(c, enc, nonce, i))
                    i += 1
            if not hmac.compare_digest(h.digest(), fi.read(32)):
                raise MigrationError("Umzugscode passt nicht zum Paket oder das Paket ist beschädigt.")
        except BaseException:
            dst.unlink(missing_ok=True)
            raise
