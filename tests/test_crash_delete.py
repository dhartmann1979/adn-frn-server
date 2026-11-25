"""💥 Abstürze bereinigen: einzelne und alle Befunde samt Protokoll löschen (n8_admin.N8Admin.crash_delete)."""
import json
import time

from frnadn.n8_admin import N8Admin


def make(tmp_path, n=3):
    d = tmp_path / "crash"
    d.mkdir()
    ids = [f"20261125-2100{i:02d}-frnadn" for i in range(n)]
    with open(tmp_path / "crashes.jsonl", "w") as f:
        for i, cid in enumerate(ids):
            f.write(json.dumps({"id": cid, "time": time.time() - 100 + i, "unit": "frnadn.service", "kind": "crash",
                                "service": "Dashboard", "reason": "x", "log": cid + ".log"}) + "\n")
            (d / f"{cid}.log").write_text("log")
    (d / "fault-frnadn.service.log").write_text("faulthandler")
    return ids


def test_delete_one_and_all(tmp_path):
    ids = make(tmp_path)
    a = N8Admin(tmp_path)
    assert a.crashes()["total"] == 3
    r = a.crash_delete([ids[1], "../etc/passwd"])
    assert r["deleted"] == 1 and r["total"] == 2 and ids[1] not in [e["id"] for e in r["items"]]
    assert not (tmp_path / "crash" / f"{ids[1]}.log").exists() and (tmp_path / "crash" / f"{ids[0]}.log").exists()
    a.crash_ack(all_=True)
    r = a.crash_delete(all_=True)
    assert r["total"] == 0 and r["unacked"] == 0 and r["deleted"] == 2
    assert not list((tmp_path / "crash").glob("2026*.log")) and not (tmp_path / "crash" / "ack.json").exists()
    assert (tmp_path / "crash" / "fault-frnadn.service.log").exists()      # faulthandler file stays
    # new records after cleaning are counted again
    with open(tmp_path / "crashes.jsonl", "a") as f:
        f.write(json.dumps({"id": "20261125-220000-frnadn", "time": time.time(), "unit": "frnadn.service"}) + "\n")
    assert a.crashes()["unacked"] == 1


def test_delete_without_records(tmp_path):
    assert N8Admin(tmp_path).crash_delete(all_=True)["total"] == 0
