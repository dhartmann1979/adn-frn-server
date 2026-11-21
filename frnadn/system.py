"""System information and control of the services (systemctl via sudo)."""
from __future__ import annotations

import asyncio
import os
import platform
import shutil
import socket
import time
from pathlib import Path
from typing import Any, Dict, List



def _sudo() -> List[str]:
    return [] if os.geteuid() == 0 else ["sudo", "-n"]


async def run(cmd: List[str], timeout: float = 20) -> Dict[str, Any]:
    try:
        p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(p.communicate(), timeout)
        return {"rc": p.returncode, "out": out.decode("utf-8", "replace")}
    except FileNotFoundError:
        return {"rc": 127, "out": f"{cmd[0]}: not found"}
    except asyncio.TimeoutError:
        try:
            p.kill()
        except Exception:
            pass
        return {"rc": 124, "out": "timeout"}


class System:
    """Host information and power control (the FRN server is controlled in frn/javasrv.py)."""

    def __init__(self, demo: bool = False):
        self.demo = demo
        self.started = time.time()

    async def journal(self, lines: int = 300, unit: str = "frnadn") -> str:
        if self.demo:
            return "(demo mode)"
        r = await run(["journalctl", "-u", f"{unit}.service", "-n", str(min(int(lines), 3000)), "--no-pager", "-o", "short-iso"], 20)
        return r["out"]

    async def power(self, action: str) -> Dict[str, Any]:
        if action not in ("reboot", "poweroff"):
            raise ValueError("unknown action")
        if self.demo:
            return {"rc": 0, "out": ""}
        return await run([*_sudo(), "systemctl", action], 30)

    def info(self) -> Dict[str, Any]:
        def read(p: str, default: str = "") -> str:
            try:
                return Path(p).read_text().strip().strip("\x00")
            except Exception:
                return default
        mem = {}
        for line in read("/proc/meminfo").splitlines():
            k, _, v = line.partition(":")
            if k in ("MemTotal", "MemAvailable"):
                mem[k] = int(v.split()[0]) * 1024
        try:
            up = float(read("/proc/uptime", "0").split()[0])
        except ValueError:
            up = 0.0
        du = shutil.disk_usage("/")
        os_name = ""
        for line in read("/etc/os-release").splitlines():
            if line.startswith("PRETTY_NAME="):
                os_name = line.split("=", 1)[1].strip('"')
        ips = []
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            pass
        load = os.getloadavg() if hasattr(os, "getloadavg") else (0, 0, 0)
        info = {"hostname": socket.gethostname(), "model": read("/sys/devices/virtual/dmi/id/product_name") or platform.machine(),
                "os": os_name, "kernel": platform.release(), "python": platform.python_version(),
                "load": [round(x, 2) for x in load], "cpus": os.cpu_count(),
                "mem_total": mem.get("MemTotal"), "mem_available": mem.get("MemAvailable"),
                "disk_total": du.total, "disk_free": du.free, "uptime": up, "ips": ips}
        if self.demo:
            info.update({"hostname": "frn", "model": "KVM virtual machine", "os": "Debian GNU/Linux 13 (trixie)",
                         "ips": ["203.0.113.26"], "cpus": 2, "load": [0.08, 0.05, 0.01], "mem_total": 2 * 2 ** 30,
                         "mem_available": int(1.4 * 2 ** 30), "disk_total": 40 * 2 ** 30, "disk_free": 31 * 2 ** 30,
                         "uptime": 12 * 86400 + 5 * 3600})
        return info
