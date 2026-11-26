"""SHA512-CRYPT (``$6$``) for the mailboxes – the hash Dovecot checks, made from the dashboard password.

The dashboard keeps its own scrypt hash. Dovecot cannot read scrypt, so whenever the plain password passes through the dashboard
(login, new user, new password) the same password is also stored as SHA512-CRYPT in ``users.mail_hash``. The mail server only
ever sees that hash (``/etc/dovecot/n8mail-users``). Python 3.13 has no ``crypt`` module any more – this is the reference
algorithm (Ulrich Drepper, "Unix crypt using SHA-256 and SHA-512"), checked against ``openssl passwd -6`` in the tests.
"""
from __future__ import annotations

import hashlib
import secrets

_ALPHA = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_ORDER = [(0, 21, 42), (22, 43, 1), (44, 2, 23), (3, 24, 45), (25, 46, 4), (47, 5, 26), (6, 27, 48), (28, 49, 7), (50, 8, 29),
          (9, 30, 51), (31, 52, 10), (53, 11, 32), (12, 33, 54), (34, 55, 13), (56, 14, 35), (15, 36, 57), (37, 58, 16),
          (59, 17, 38), (18, 39, 60), (40, 61, 19), (62, 20, 41)]


def _b64(b2: int, b1: int, b0: int, n: int) -> str:
    w = (b2 << 16) | (b1 << 8) | b0
    out = []
    for _ in range(n):
        out.append(_ALPHA[w & 0x3F])
        w >>= 6
    return "".join(out)


def sha512_crypt(password: str, salt: str = "", rounds: int = 5000) -> str:
    p = password.encode("utf-8")
    salt = (salt or "".join(secrets.choice(_ALPHA) for _ in range(16)))[:16]
    s = salt.encode("ascii")
    rounds = max(1000, min(999_999_999, int(rounds)))
    b = hashlib.sha512(p + s + p).digest()
    a = hashlib.sha512(p + s)
    for i in range(len(p) // 64):
        a.update(b)
    a.update(b[:len(p) % 64])
    n = len(p)
    while n:
        a.update(b if n & 1 else p)
        n >>= 1
    a = a.digest()
    dp = hashlib.sha512(p * len(p)).digest()
    pp = (dp * (len(p) // 64 + 1))[:len(p)]
    ds = hashlib.sha512(s * (16 + a[0])).digest()
    ss = (ds * (len(s) // 64 + 1))[:len(s)]
    c = a
    for i in range(rounds):
        h = hashlib.sha512()
        h.update(pp if i & 1 else c)
        if i % 3:
            h.update(ss)
        if i % 7:
            h.update(pp)
        h.update(c if i & 1 else pp)
        c = h.digest()
    enc = "".join(_b64(c[x], c[y], c[z], 4) for x, y, z in _ORDER) + _b64(0, 0, c[63], 2)
    prefix = "$6$" + (f"rounds={rounds}$" if rounds != 5000 else "")
    return f"{prefix}{salt}${enc}"


def mail_hash(password: str) -> str:
    """Hash for Dovecot: ``{SHA512-CRYPT}$6$rounds=…``."""
    return "{SHA512-CRYPT}" + sha512_crypt(password, rounds=100_000)


def verify(password: str, stored: str) -> bool:
    h = stored[len("{SHA512-CRYPT}"):] if stored.startswith("{SHA512-CRYPT}") else stored
    parts = h.split("$")
    if len(parts) < 4 or parts[1] != "6":
        return False
    rounds, salt = 5000, parts[2]
    if salt.startswith("rounds="):
        rounds, salt = int(salt[7:]), parts[3]
    return secrets.compare_digest(sha512_crypt(password, salt, rounds), h)
