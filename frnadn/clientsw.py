"""
Which software / network is behind an FRN station – shown as the station's avatar.

FRN clients send their band/channel, a free description and the client type
(crosslink, gateway, PC only). Crosslinks and gateways usually name what they
connect to ("DMR TG 262", "SvxLink Minden", "Zello Kanal …"). The first match wins;
without a match the client type decides.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# key, label, pattern (searched in band, description and name)
KINDS: List[Tuple[str, str, str]] = [
    ("dmr", "DMR", r"\bdmr\b|brandmeister|\btgif\b|freedmr|hblink|\bbm\s?\d{3,}|\btg\s?\d{3,}"),
    ("zello", "Zello", r"zello"),
    ("svxlink", "SvxLink", r"svx"),
    ("echolink", "EchoLink", r"echo\s?link|\becholink\b"),
    ("allstar", "AllStar", r"allstar|\basl\b|hamvoip"),
    ("c4fm", "C4FM / YSF", r"\bysf\b|c4fm|wires[- ]?x|\bfusion\b"),
    ("dstar", "D-STAR", r"d-?star|\bdplus\b|\bdextra\b|\bref\d{3}\b|\bxlx\d"),
    ("m17", "M17", r"\bm17\b"),
    ("teamspeak", "TeamSpeak / Mumble", r"teamspeak|\bts3\b|mumble"),
]
GENERIC = {0: ("crosslink", "Crosslink"), 1: ("gateway", "Gateway (radio)"), 2: ("pc", "PC / app")}
LABELS: Dict[str, str] = {k: label for k, label, _ in KINDS}
LABELS.update({k: label for k, label in GENERIC.values()})
LABELS["parrot"] = "Parrot / echo test"
KEYS = tuple(LABELS)
_COMPILED = [(k, re.compile(p, re.I)) for k, _, p in KINDS]


def detect(band: str = "", descr: str = "", name: str = "", client: Any = None, parrot: bool = False) -> str:
    if parrot:
        return "parrot"
    text = " ".join(str(x or "") for x in (band, descr, name))
    for key, rx in _COMPILED:
        if rx.search(text):
            return key
    # the band text is more reliable than the stored client type
    b = str(band or "").strip().lower()
    if b in ("pc only", "pc-only", "pconly"):
        return "pc"
    if b.startswith("crosslink"):
        return "crosslink"
    if client is None or client == "":
        client = 2 if not b else 1
    try:
        return GENERIC.get(int(client), GENERIC[2])[0]
    except (TypeError, ValueError):
        return "pc"
