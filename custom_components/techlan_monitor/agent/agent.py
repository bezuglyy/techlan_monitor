#!/usr/bin/env python3
"""techlan-agent: кросс-платформенный агент мониторинга серверов.

Работает на Linux (/proc, docker, ss) и Windows (wmic, systeminfo).
HTTP-сервер на порту 9100 (или AGENT_PORT).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from functools import wraps
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

AGENT_VERSION = "1.0.0"
AGENT_PORT = int(os.environ.get("AGENT_PORT", "9100"))
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "")

IS_WINDOWS = sys.platform == "win32"


# ─── helpers ──────────────────────────────────────────────────────────


def run(cmd: list[str], timeout: int = 10) -> str:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=IS_WINDOWS,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def read_file(path: str) -> str:
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return ""


def int_or(v: str, default: int = 0) -> int:
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


def float_or(v: str, default: float = 0.0) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


# ─── Linux collectors ─────────────────────────────────────────────────


def linux_hostname() -> str:
    return run(["hostname"])


def linux_uptime() -> dict:
    raw = read_file("/proc/uptime").split()[0] if read_file("/proc/uptime") else "0"
    sec = float_or(raw)
    return {"uptime_sec": sec, "uptime_str": _format_uptime(sec)}


def _format_uptime(sec: float) -> str:
    d = int(sec // 86400)
    h = int((sec % 86400) // 3600)
    m = int((sec % 3600) // 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts) or "0m"


def linux_load() -> list[str]:
    return read_file("/proc/loadavg").split()[:3] or ["0", "0", "0"]


def linux_cpu() -> dict:
    cores = int_or(run(["nproc"]), os.cpu_count() or 0)
    # parse /proc/stat for usage %
    idle_line = (
        read_file("/proc/stat").split("\n")[0] if read_file("/proc/stat") else ""
    )
    parts = idle_line.split()
    if len(parts) >= 5:
        user, nice, sys_idle, idle, iowait = (
            int_or(parts[1]),
            int_or(parts[2]),
            int_or(parts[3]),
            int_or(parts[4]),
            int_or(parts[5]),
        )
        total = user + nice + sys_idle + idle + iowait
        usage = round((total - idle) / total * 100, 1) if total > 0 else 0.0
    else:
        # fall back to top
        top_out = run(["top", "-bn1"], timeout=5)
        usage = 0.0
        for line in top_out.split("\n"):
            if "%Cpu(s)" in line:
                parts = line.split()
                if len(parts) > 1:
                    idle_str = parts[7] if len(parts) > 7 else parts[1]
                    try:
                        idle_pct = float(idle_str.replace(",", "."))
                        usage = round(100.0 - idle_pct, 1)
                    except ValueError:
                        usage = 0.0
    return {"cores": cores, "usage": usage}


def linux_memory() -> dict:
    meminfo = read_file("/proc/meminfo")
    vals = {}
    for line in meminfo.split("\n"):
        parts = line.split(":")
        if len(parts) == 2:
            key = parts[0].strip()
            val_str = parts[1].strip().split()[0]
            vals[key] = int_or(val_str) * 1024  # kB → bytes
    total = vals.get("MemTotal", 0)
    avail = vals.get("MemAvailable", vals.get("MemFree", 0))
    used = max(total - avail, 0)
    pct = round(used / total * 100, 1) if total > 0 else 0.0
    return {"total": total, "used": used, "free": avail, "pct": pct}


def linux_disk() -> list[dict]:
    out = run(
        ["df", "-B1", "--exclude-type=tmpfs", "--exclude-type=devtmpfs"], timeout=5
    )
    disks = []
    for line in out.split("\n")[1:]:
        parts = line.split()
        if len(parts) >= 6:
            try:
                disks.append(
                    {
                        "mount": parts[5],
                        "total": int(parts[1]),
                        "used": int(parts[2]),
                        "free": int(parts[3]),
                        "pct": parts[4].replace("%", ""),
                    }
                )
            except (ValueError, IndexError):
                pass
    return disks


def linux_docker() -> dict:
    out = run(
        ["docker", "ps", "--format", "{{.Names}}|{{.Status}}|{{.Image}}"], timeout=10
    )
    containers = []
    for line in out.split("\n"):
        if "|" in line:
            parts = line.split("|", 2)
            containers.append(
                {
                    "name": parts[0],
                    "status": parts[1],
                    "image": parts[2] if len(parts) > 2 else "",
                }
            )
    return {"containers": containers}


def linux_services() -> list[dict]:
    out = run(
        ["systemctl", "list-units", "--type=service", "--no-pager", "--no-legend"],
        timeout=10,
    )
    services = []
    for line in out.split("\n"):
        parts = line.split()
        if len(parts) >= 3:
            services.append({"name": parts[0], "active": parts[1], "sub": parts[2]})
    return services


def linux_ports() -> int:
    out = run(["ss", "-tln"], timeout=5)
    return max(len(out.split("\n")) - 1, 0) if out else 0


def linux_os() -> str:
    os_release = read_file("/etc/os-release")
    for line in os_release.split("\n"):
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return platform.platform()


def linux_kernel() -> str:
    return platform.release()


def collect_linux() -> dict:
    load = linux_load()
    mem = linux_memory()
    disk = linux_disk()
    return {
        "hostname": linux_hostname(),
        "platform": "linux",
        **linux_uptime(),
        "load": ",".join(load) if isinstance(load, list) else load,
        "cpu": linux_cpu(),
        "memory": mem,
        "disks": disk,
        "docker": linux_docker(),
        "services": linux_services(),
        "ports": linux_ports(),
        "os": linux_os(),
        "kernel": linux_kernel(),
    }


# ─── Windows collectors ───────────────────────────────────────────────


def win_hostname() -> str:
    return platform.node()


def win_uptime() -> dict:
    # wmic os get lastbootuptime
    out = run(["wmic", "os", "get", "lastbootuptime"], timeout=5)
    for line in out.split("\n"):
        line = line.strip()
        if line and line != "LastBootUpTime" and not line.startswith("20"):
            continue
        if line.startswith("20"):
            # Parse YYYYMMDDHHMMSS...
            try:
                import datetime

                boot = datetime.datetime.strptime(line[:14], "%Y%m%d%H%M%S")
                now = datetime.datetime.utcnow()
                sec = int((now - boot).total_seconds())
                return {
                    "uptime_sec": max(sec, 0),
                    "uptime_str": _format_uptime(max(sec, 0)),
                }
            except Exception:
                pass
    return {"uptime_sec": 0, "uptime_str": "0m"}


def win_load() -> str:
    # Windows doesn't have load average, return cpu usage as load
    cpu = win_cpu()
    return f"{cpu['usage']},0,0"


def win_cpu() -> dict:
    out = run(["wmic", "cpu", "get", "loadpercentage"], timeout=5)
    for line in out.split("\n"):
        try:
            pct = float(line.strip())
            return {"cores": os.cpu_count() or 0, "usage": pct}
        except ValueError:
            continue
    # fallback: systeminfo
    out2 = run(["systeminfo"], timeout=10)
    for line in out2.split("\n"):
        if "Processor" in line and "%" in line:
            try:
                pct = float(line.split("%")[0].split()[-1])
                return {"cores": os.cpu_count() or 0, "usage": pct}
            except (ValueError, IndexError):
                pass
    return {"cores": os.cpu_count() or 0, "usage": 0.0}


def win_memory() -> dict:
    out = run(["wmic", "computersystem", "get", "totalphysicalmemory"], timeout=5)
    total = 0
    for line in out.split("\n"):
        try:
            total = int(line.strip())
            break
        except ValueError:
            continue
    out2 = run(["wmic", "os", "get", "freephysicalmemory"], timeout=5)
    free = 0
    for line in out2.split("\n"):
        try:
            free = int(line.strip()) * 1024  # kB → bytes
            break
        except ValueError:
            continue
    used = max(total - free, 0)
    pct = round(used / total * 100, 1) if total > 0 else 0.0
    return {"total": total, "used": used, "free": free, "pct": pct}


def win_disk() -> list[dict]:
    out = run(["wmic", "logicaldisk", "get", "deviceid,size,freespace"], timeout=5)
    disks = []
    for line in out.split("\n")[1:]:
        parts = line.split()
        if len(parts) >= 3:
            try:
                device = parts[0]
                free = int(parts[1])
                total = int(parts[2])
                used = max(total - free, 0)
                pct = round(used / total * 100, 1) if total > 0 else 0.0
                disks.append(
                    {
                        "mount": device,
                        "total": total,
                        "used": used,
                        "free": free,
                        "pct": str(pct),
                    }
                )
            except (ValueError, IndexError):
                pass
    return disks


def win_docker() -> dict:
    out = run(
        ["docker", "ps", "--format", "{{.Names}}|{{.Status}}|{{.Image}}"], timeout=15
    )
    containers = []
    for line in out.split("\n"):
        if "|" in line:
            parts = line.split("|", 2)
            containers.append(
                {
                    "name": parts[0],
                    "status": parts[1],
                    "image": parts[2] if len(parts) > 2 else "",
                }
            )
    return {"containers": containers}


def win_services() -> list[dict]:
    out = run(["wmic", "service", "get", "name,state", "/format:csv"], timeout=10)
    services = []
    for line in out.split("\n")[2:]:
        parts = line.split(",")
        if len(parts) >= 3:
            name = parts[-2].strip()
            state = parts[-1].strip().lower()
            if name:
                services.append(
                    {
                        "name": name,
                        "active": "running" if state == "running" else "inactive",
                        "sub": state,
                    }
                )
    return services


def win_ports() -> int:
    out = run(["netstat", "-an"], timeout=5)
    count = 0
    for line in out.split("\n"):
        if "LISTENING" in line.upper() or "LISTEN" in line.upper():
            count += 1
    return count


def win_os() -> str:
    return platform.platform()


def win_kernel() -> str:
    return platform.version()


def collect_windows() -> dict:
    mem = win_memory()
    disk = win_disk()
    cpu = win_cpu()
    return {
        "hostname": win_hostname(),
        "platform": "windows",
        **win_uptime(),
        "load": win_load(),
        "cpu": cpu,
        "memory": mem,
        "disks": disk,
        "docker": win_docker(),
        "services": win_services(),
        "ports": win_ports(),
        "os": win_os(),
        "kernel": win_kernel(),
    }


# ─── HTTP server ──────────────────────────────────────────────────────


def check_token(handler: BaseHTTPRequestHandler) -> bool:
    if not AGENT_TOKEN:
        return True
    token = handler.headers.get("Authorization", "").replace("Bearer ", "")
    if token == AGENT_TOKEN:
        return True
    handler.send_response(401)
    handler.end_headers()
    handler.wfile.write(b'{"error":"unauthorized"}')
    return False


class AgentHandler(BaseHTTPRequestHandler):
    server_version = f"TechlanAgent/{AGENT_VERSION}"

    def do_GET(self) -> None:
        if not check_token(self):
            return
        parsed = urlparse(self.path)
        match parsed.path:
            case "/api/v1/health":
                self._json(
                    {
                        "ok": True,
                        "version": AGENT_VERSION,
                        "hostname": platform.node(),
                        "platform": sys.platform,
                    }
                )
            case "/api/v1/metrics":
                data = collect_linux() if not IS_WINDOWS else collect_windows()
                self._json(data)
            case "/api/v1/services":
                svc = linux_services() if not IS_WINDOWS else win_services()
                self._json({"services": svc})
            case "/api/v1/docker":
                dkr = linux_docker() if not IS_WINDOWS else win_docker()
                self._json(dkr)
            case _:
                self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        if not check_token(self):
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/v1/reboot":
            self._json({"ok": True, "message": "rebooting..."})
            if IS_WINDOWS:
                os.system("shutdown /r /t 3")
            else:
                os.system("reboot")
        else:
            self._json({"error": "not found"}, 404)

    def _json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass  # silent


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", AGENT_PORT), AgentHandler)
    print(
        f"[techlan-agent v{AGENT_VERSION}] listening on :{AGENT_PORT} (platform={sys.platform})"
    )

    def shutdown(sig, frame):
        print("[techlan-agent] shutting down...")
        server.shutdown()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
