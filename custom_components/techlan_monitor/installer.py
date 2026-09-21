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
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Версия устанавливаемого агента (артефакт agent/agent.py должен совпадать).
AGENT_VERSION = "1.2.1"
# Общий таймаут установки (SSH + запись файлов + запуск службы).
INSTALL_TIMEOUT = 120

LINUX_TOKEN_FILE = "/opt/techlan-agent/agent.token"
WINDOWS_TOKEN_FILE = r"C:\ProgramData\TechlanAgent\agent.token"

# Полноценный агент поставляется в пакете: agent/agent.py — единый артефакт.
AGENT_SOURCE = Path(__file__).resolve().parent / "agent" / "agent.py"


def _agent_code() -> str:
    """Исходник агента для установки (единый артефакт ``agent/agent.py``)."""
    try:
        return AGENT_SOURCE.read_text(encoding="utf-8")
    except OSError as err:  # pragma: no cover - защита поставки
        raise RuntimeError(f"agent source not found: {AGENT_SOURCE}") from err



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
            await handle.write(_agent_code())
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

    script_b64 = base64.b64encode(_agent_code().encode()).decode()
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
