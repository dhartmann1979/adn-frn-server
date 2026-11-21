import importlib
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture
def app_mod(tmp_path, monkeypatch):
    """A fresh frnadn.app with its own data directory and a free FRN port."""
    monkeypatch.setenv("FRNADN_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("FRNADN_DEMO", "1")
    monkeypatch.setenv("FRNADN_FRN_JAR", str(tmp_path / "jar" / "FRN_Server.jar"))
    monkeypatch.delenv("FRNADN_FRN_HOME", raising=False)
    monkeypatch.delenv("FRNADN_FRN_DIRECT", raising=False)
    import frnadn.app as A
    importlib.reload(A)
    A.ctx = A.Ctx()
    A.ctx.settings.update({"frn.port": free_port(), "frn.address": "127.0.0.1", "frn.owner_email": "owner@example.org",
                           "frn.standalone": True, "frn.allow_lan": True}, "test")
    return A
