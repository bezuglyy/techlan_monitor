"""DataUpdateCoordinator для Techlan Monitor.

Собирает данные из двух источников:
1. Supervisor API (данные HAOS)
2. HTTP-агенты на удалённых серверах
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AGENT_INSTALLED,
    CONF_PLATFORM,
    CONF_PORT,
    CONF_SERVERS,
    CONF_TOKEN,
    DEFAULT_AGENT_PORT,
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

        # Загружаем конфигурацию серверов из options
        self._load_config(entry)

    def _load_config(self, entry: ConfigEntry) -> None:
        """Загрузка конфигурации серверов."""
        self.entry = entry
        self.server_configs = dict(entry.options.get(CONF_SERVERS, {}))
        _LOGGER.debug(
            "Loaded %d server configs: %s",
            len(self.server_configs),
            list(self.server_configs.keys()),
        )

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
        except Exception as err:
            msg = f"HAOS fetch failed: {err}"
            _LOGGER.warning(msg)
            data["errors"].append(msg)
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
        platform = config.get(CONF_PLATFORM, PLATFORM_LINUX)

        url = f"http://{host}:{port}/api/v1/metrics"
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            async with self.session.get(
                url,
                headers=headers,
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

        url = f"http://{host}:{port}/api/v1/reboot"
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            async with self.session.post(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def async_reload_config(self, entry: ConfigEntry | None = None) -> None:
        """Перезагрузка конфигурации."""
        if entry:
            self._load_config(entry)
        await self.async_refresh()

    async def async_shutdown(self) -> None:
        """Остановка координатора."""
        pass  # cleanup если нужно
