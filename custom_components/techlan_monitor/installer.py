"""SSH-установщик techlan-agent на удалённые серверы.

Поддерживает Linux (asyncssh) и Windows (PowerShell через asyncssh).
Установщик **генерирует случайный токен** и передаёт его агенту (файл
``agent.token`` + переменная окружения), возвращая токен вызывающему, чтобы
интеграция сохранила его в options для запросов.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Версия устанавливаемого агента (артефакт agent/agent.py должен совпадать).
AGENT_VERSION = "1.2.0"
# Общий таймаут установки (SSH + запись файлов + запуск службы).
INSTALL_TIMEOUT = 120

LINUX_TOKEN_FILE = "/opt/techlan-agent/agent.token"
WINDOWS_TOKEN_FILE = r"C:\ProgramData\TechlanAgent\agent.token"

# Текст скрипта агента для установки
AGENT_SCRIPT = """#!/usr/bin/env python3
# Этот файл будет заменён на полноценный agent.py
# Устанавливается через SSH agent installer

import json, os, platform, subprocess, sys, time

VERSION = "1.2.0"
PORT = int(os.environ.get("AGENT_PORT", "9100"))

def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except: return ""

IS_WIN = sys.platform == "win32"

def collect():
    if IS_WIN:
        hostname = platform.node()
        cpu = run(["wmic", "cpu", "get", "loadpercentage"], 5).split("\\n")[1].strip() or "0"
        mem = run(["wmic", "computersystem", "get", "totalphysicalmemory"], 5).split("\\n")[1].strip() or "0"
        return {"hostname":hostname,"platform":"windows","cpu_usage":float(cpu),"memory_total":int(mem)}
    else:
        hostname = run(["hostname"])
        cpu = run(["nproc"], 5) or str(os.cpu_count() or 0)
        load = read_file("/proc/loadavg").split()[:3] or ["0","0","0"]
        return {"hostname":hostname,"platform":"linux","cpu_cores":int(cpu),"load":",".join(load)}

def read_file(path):
    try:
        with open(path) as f: return f.read().strip()
    except: return ""

from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if "/health" in self.path:
            self._json({"ok":True,"version":VERSION,"hostname":platform.node(),"platform":sys.platform})
        elif "/metrics" in self.path:
            self._json(collect())
        else:
            self._json({"error":"not found"},404)
    def _json(self,d,status=200):
        b=json.dumps(d).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.end_headers()
        self.wfile.write(b)
    def log_message(self,f,*a): pass

def main():
    s = HTTPServer(("0.0.0.0",PORT), H)
    print(f"[techlan-agent v{VERSION}] :{PORT}")
    try: s.serve_forever()
    except: s.shutdown()

if __name__ == "__main__":
    main()
"""


def generate_token() -> str:
    """Generate a URL-safe agent token."""
    return secrets.token_urlsafe(32)


async def install_agent(
    hass: Any,
    host: str,
    username: str,
    password: str,
    port: int = 9100,
    platform: str = "linux",
    token: str | None = None,
) -> str | None:
    """Install the agent and return its token (``None`` on failure)."""
    try:
        import asyncssh
    except ImportError:
        _LOGGER.error("asyncssh not installed. Install with: pip install asyncssh")
        return None

    agent_token = token or generate_token()
    _LOGGER.info(
        "Installing techlan-agent on %s@%s (platform=%s)", username, host, platform
    )

    try:
        async with asyncssh.connect(
            host=host,
            username=username,
            password=password,
            known_hosts=None,
            connect_timeout=15,
        ) as conn:
            if platform == "linux":
                ok = await asyncio.wait_for(
                    _install_linux(conn, port, agent_token), timeout=INSTALL_TIMEOUT
                )
            else:
                ok = await asyncio.wait_for(
                    _install_windows(conn, port, agent_token), timeout=INSTALL_TIMEOUT
                )
        return agent_token if ok else None
    except asyncio.TimeoutError:
        _LOGGER.error("Agent install timed out for %s after %ss", host, INSTALL_TIMEOUT)
        return None
    except asyncssh.Error as err:
        _LOGGER.error("SSH connection failed for %s: %s", host, err)
        return None
    except Exception as err:
        _LOGGER.exception("Agent install failed for %s: %s", host, err)
        return None


async def _install_linux(conn: Any, port: int, token: str) -> bool:
    """Установка агента на Linux."""
    await conn.run("mkdir -p /opt/techlan-agent", check=False)

    # Запись agent.py
    async with conn.start_sftp_client() as sftp:
        async with sftp.open("/opt/techlan-agent/agent.py", "w") as handle:
            await handle.write(AGENT_SCRIPT)
        # Запись токена (точка доверия агента).
        async with sftp.open(LINUX_TOKEN_FILE, "w") as handle:
            await handle.write(token)

    # Права на файл токена: читает только владелец (служба запускается под nobody).
    await conn.run(
        f"chown nobody:nogroup {LINUX_TOKEN_FILE} 2>/dev/null || "
        f"chown nobody {LINUX_TOKEN_FILE} 2>/dev/null || true",
        check=False,
    )
    await conn.run(f"chmod 600 {LINUX_TOKEN_FILE}", check=False)

    service = f"""[Unit]
Description=Techlan Monitor Agent
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/techlan-agent/agent.py
Environment=AGENT_PORT={port}
Environment=AGENT_TOKEN_FILE={LINUX_TOKEN_FILE}
Restart=always
RestartSec=5
User=nobody

[Install]
WantedBy=multi-user.target
"""
    async with conn.start_sftp_client() as sftp:
        async with sftp.open(
            "/etc/systemd/system/techlan-agent.service", "w"
        ) as handle:
            await handle.write(service)

    await conn.run("systemctl daemon-reload", check=False)
    await conn.run("systemctl enable techlan-agent", check=False)
    result = await conn.run("systemctl restart techlan-agent", check=False)

    if result.returncode == 0:
        _LOGGER.info("techlan-agent installed and started on Linux")
        return True
    _LOGGER.error("Failed to start techlan-agent: %s", result.stderr)
    return False


async def _install_windows(conn: Any, port: int, token: str) -> bool:
    """Установка агента на Windows (PowerShell)."""
    await conn.run(
        'powershell -Command "New-Item -ItemType Directory -Force '
        '-Path C:\\ProgramData\\TechlanAgent"',
        check=False,
    )

    import base64

    script_b64 = base64.b64encode(AGENT_SCRIPT.encode()).decode()
    await conn.run(
        "powershell -Command \"[System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('"
        + script_b64
        + "')) | Set-Content -Path 'C:\\ProgramData\\TechlanAgent\\agent.py' -Encoding UTF8\"",
        check=False,
    )
    token_b64 = base64.b64encode(token.encode()).decode()
    await conn.run(
        "powershell -Command \"[System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('"
        + token_b64
        + "')) | Set-Content -Path 'C:\\ProgramData\\TechlanAgent\\agent.token' -Encoding UTF8 -NoNewline\"",
        check=False,
    )

    task_xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
    </BootTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>python</Command>
      <Arguments>C:\\ProgramData\\TechlanAgent\\agent.py</Arguments>
    </Exec>
  </Actions>
</Task>"""
    task_b64 = base64.b64encode(task_xml.encode("utf-16-le")).decode()
    await conn.run(
        'powershell -Command "$xml = [System.Text.Encoding]::Unicode.GetString('
        "[System.Convert]::FromBase64String('" + task_b64 + "')); "
        "Register-ScheduledTask -TaskName 'TechlanAgent' -Xml $xml -Force\"",
        check=False,
    )

    result = await conn.run(
        "powershell -Command \"Start-ScheduledTask -TaskName 'TechlanAgent'\"",
        check=False,
    )

    if result.returncode == 0:
        _LOGGER.info("techlan-agent installed and started on Windows")
        return True
    _LOGGER.warning(
        "Agent scheduled task created but start may have failed: %s", result.stderr
    )
    return False
