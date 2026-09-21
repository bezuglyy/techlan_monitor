"""DataUpdateCoordinator для Techlan Monitor.

Собирает данные из двух источников:
1. Supervisor API (данные HAOS)
2. HTTP-агенты на удалённых серверах
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AGENT_INSTALLED,
    CONF_PLATFORM,
    CONF_PORT,
    CONF_REBOOT_CONFIRM_SECONDS,
    CONF_SERVERS,
    CONF_TOKEN,
    CONF_USE_HTTPS,
    CONF_VERIFY_TLS,
    DEFAULT_AGENT_PORT,
    DEFAULT_REBOOT_CONFIRM_SECONDS,
    DOMAIN,
    HTTP_TIMEOUT,
    PLATFORM_LINUX,
    PLATFORM_WINDOWS,
)

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=30)


class TechlanDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Координатор данных Techlan Monitor."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Инициализация."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
            always_update=False,
        )

        self._entry_id = entry.entry_id
        self.session = async_get_clientsession(hass)
        self.server_configs: dict[str, dict[str, Any]] = {}
        self.haos_hostname: str = ""
        self.haos_version: str = ""
        self.haos_device_id: str | None = None
        self._haos_failures = 0
        self._haos_issue_active = False
        # Предохранители перезагрузки: ключ → monotonic-время истечения.
        self._reboot_armed: dict[str, float] = {}

        # Загружаем конфигурацию серверов из options
        self._load_config(entry)

    def _load_config(self, entry: ConfigEntry) -> None:
        """Загрузка конфигурации серверов."""
        self.entry = entry
        self.server_configs = dict(entry.options.get(CONF_SERVERS, {}))
        try:
            self.reboot_confirm_seconds = max(
                5,
                int(
                    entry.options.get(
                        CONF_REBOOT_CONFIRM_SECONDS, DEFAULT_REBOOT_CONFIRM_SECONDS
                    )
                ),
            )
        except (TypeError, ValueError):
            self.reboot_confirm_seconds = DEFAULT_REBOOT_CONFIRM_SECONDS
        _LOGGER.debug(
            "Loaded %d server configs: %s",
            len(self.server_configs),
            list(self.server_configs.keys()),
        )

    # ─── Предохранитель перезагрузки (двухшаговое подтверждение) ──────

    def arm_reboot(self, key: str) -> None:
        """Arm the reboot interlock for a limited time window."""
        self._reboot_armed[key] = time.monotonic() + self.reboot_confirm_seconds
        self.async_update_listeners()

    def disarm_reboot(self, key: str) -> None:
        """Disarm the reboot interlock immediately."""
        self._reboot_armed.pop(key, None)
        self.async_update_listeners()

    def is_reboot_armed(self, key: str) -> bool:
        """Return True while the interlock window is still open."""
        until = self._reboot_armed.get(key)
        if not until:
            return False
        if time.monotonic() >= until:
            self._reboot_armed.pop(key, None)
            return False
        return True

    def reboot_armed_remaining(self, key: str) -> int:
        """Seconds left in the interlock window (0 when disarmed)."""
        until = self._reboot_armed.get(key)
        if not until:
            return 0
        remaining = int(until - time.monotonic())
        if remaining <= 0:
            self._reboot_armed.pop(key, None)
            return 0
        return remaining

    async def _async_update_data(self) -> dict[str, Any]:
        """Обновление всех данных."""
        data: dict[str, Any] = {
            "haos": {},
            "servers": {},
            "errors": [],
        }

        # 1. Supervisor API (HAOS)
        try:
            haos_data = await self._fetch_haos_data()
            data["haos"] = haos_data
            self.haos_hostname = haos_data.get("hostname", "")
            self.haos_version = haos_data.get("version", "")
            self._note_haos(ok=True, error="")
        except Exception as err:
            msg = f"HAOS fetch failed: {err}"
            _LOGGER.warning(msg)
            data["errors"].append(msg)
            self._note_haos(ok=False, error=str(err))
            # Используем последние известные данные
            if self.data:
                data["haos"] = self.data.get("haos", {})

        # 2. Серверные агенты
        # Читаем конфиг из entry options (обновляется через OptionsFlow)
        server_configs = dict(self.entry.options.get(CONF_SERVERS, {}))
        tasks = {}
        for server_id, config in server_configs.items():
            tasks[server_id] = self._fetch_server_data(server_id, config)

        if tasks:
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for server_id, result in zip(tasks, results):
                if isinstance(result, Exception):
                    msg = f"Server {server_id} failed: {result}"
                    _LOGGER.warning(msg)
                    data["errors"].append(msg)
                    # Используем последние данные если есть
                    if self.data and "servers" in self.data:
                        data["servers"][server_id] = self.data["servers"].get(
                            server_id, {"online": False}
                        )
                    else:
                        data["servers"][server_id] = {"online": False}
                else:
                    data["servers"][server_id] = result

        return data

    # ─── Repairs (issues) ─────────────────────────────────────────────

    @property
    def _haos_issue_id(self) -> str:
        return f"haos_unreachable_{self._entry_id}"

    def _note_haos(self, *, ok: bool, error: str) -> None:
        """Raise/clear a Repair when the Supervisor API stays unreachable."""
        if ok:
            self._haos_failures = 0
            if self._haos_issue_active:
                async_delete_issue(self.hass, DOMAIN, self._haos_issue_id)
                self._haos_issue_active = False
            return
        self._haos_failures += 1
        if self._haos_failures >= 2 and not self._haos_issue_active:
            async_create_issue(
                self.hass,
                DOMAIN,
                self._haos_issue_id,
                is_fixable=False,
                severity=IssueSeverity.WARNING,
                translation_key="haos_unreachable",
                translation_placeholders={"error": error},
            )
            self._haos_issue_active = True

    # ─── Supervisor API ───────────────────────────────────────────────

    async def _fetch_haos_data(self) -> dict[str, Any]:
        """Получение данных о HAOS через Supervisor API."""
        try:
            token = self._get_supervisor_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            # Информация о хосте
            async with self.session.get(
                "http://supervisor/host/info",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            ) as resp:
                host_info = await resp.json()
                host_data = host_info.get("data", {})

            # Информация о системе
            async with self.session.get(
                "http://supervisor/info",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            ) as resp:
                sys_info = await resp.json()
                sys_data = sys_info.get("data", {})

            # Информация о супервизоре
            async with self.session.get(
                "http://supervisor/supervisor/info",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            ) as resp:
                sup_info = await resp.json()
                sup_data = sup_info.get("data", {})

            # Метрики CPU/память/диск
            async with self.session.get(
                "http://supervisor/host/info",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            ) as resp:
                host_detail = await resp.json()
                hd = host_detail.get("data", {})

            # Парсим информацию
            cpu_usage = host_data.get("cpu_percent", 0) or 0
            memory_data = host_data.get("memory", {})
            memory_usage = memory_data.get("percent", 0) if memory_data else 0
            disk_data = host_data.get("disk", {})
            disk_usage = disk_data.get("percent", 0) if disk_data else 0
            cpu_temp = host_data.get("cpu_temperature", 0) or 0
            cpu_freq = host_data.get("cpu_frequency", 0) or 0

            # Uptime из host data
            uptime_sec = host_data.get("uptime", 0) or 0

            # Load average
            load = host_data.get("load", [0, 0, 0])

            return {
                "hostname": host_data.get("hostname", "haos"),
                "version": sup_data.get("version", ""),
                "os": sys_data.get("operating_system", ""),
                "agent_version": sup_data.get("version", ""),
                "cpu_usage": float(cpu_usage),
                "cpu_temp": float(cpu_temp),
                "cpu_freq": float(cpu_freq),
                "memory_usage": float(memory_usage),
                "disk_usage": float(disk_usage),
                "uptime_sec": int(uptime_sec),
                "load": load,
                "type": "haos",
            }

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Supervisor API error: {err}") from err
        except (KeyError, ValueError, TypeError) as err:
            raise UpdateFailed(f"Supervisor API parse error: {err}") from err

    def _get_supervisor_token(self) -> str:
        """Получение Supervisor API токена."""
        token = ""
        # Method 1: hassio integration
        try:
            if hasattr(self.hass.auth, "async_get_supervisor_token"):
                token = self.hass.auth.async_get_supervisor_token()
        except Exception:
            pass
        # Method 2: hassio data
        if not token:
            try:
                token = self.hass.data.get("hassio", {}).get("token", "")
            except Exception:
                pass
        # Method 3: environment variable
        if not token:
            token = os.environ.get("SUPERVISOR_TOKEN", "")
        return token

    # ─── Серверные агенты ────────────────────────────────────────────

    async def _fetch_server_data(
        self, server_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Получение данных с удалённого сервера через HTTP-агент."""
        host = config.get(CONF_HOST, "")
        port = config.get(CONF_PORT, DEFAULT_AGENT_PORT)
        token = config.get(CONF_TOKEN, "")
        use_https = bool(config.get(CONF_USE_HTTPS, False))
        verify_tls = bool(config.get(CONF_VERIFY_TLS, True))

        scheme = "https" if use_https else "http"
        url = f"{scheme}://{host}:{port}/api/v1/metrics"
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # ssl=False disables certificate verification (self-signed agents);
        # it is only meaningful for HTTPS.
        ssl_param = False if (use_https and not verify_tls) else None

        try:
            async with self.session.get(
                url,
                headers=headers,
                ssl=ssl_param,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    return {"online": False, "error": f"HTTP {resp.status}"}

                metrics = await resp.json()
                return {"online": True, **metrics}

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            return {"online": False, "error": str(err)}

    # ─── Управление ──────────────────────────────────────────────────

    async def async_reboot_server(self, server_id: str) -> bool:
        """Перезагрузка сервера через агента."""
        config = self.server_configs.get(server_id)
        if not config:
            return False

        host = config.get(CONF_HOST, "")
        port = config.get(CONF_PORT, DEFAULT_AGENT_PORT)
        token = config.get(CONF_TOKEN, "")
        use_https = bool(config.get(CONF_USE_HTTPS, False))
        verify_tls = bool(config.get(CONF_VERIFY_TLS, True))

        scheme = "https" if use_https else "http"
        url = f"{scheme}://{host}:{port}/api/v1/reboot"
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        ssl_param = False if (use_https and not verify_tls) else None

        try:
            async with self.session.post(
                url,
                headers=headers,
                ssl=ssl_param,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001 - reboot is fire-and-forget
            return False

    async def async_reload_config(self, entry: ConfigEntry | None = None) -> None:
        """Перезагрузка конфигурации."""
        if entry:
            self._load_config(entry)
        await self.async_refresh()

    async def async_shutdown(self) -> None:
        """Остановка координатора."""
        pass  # cleanup если нужно
