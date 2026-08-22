"""Сенсоры для Techlan Monitor.

Два типа:
1. HAOS сенсоры (данные из Supervisor API)
2. Серверные сенсоры (данные с удалённых агентов)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    HAOS_SENSORS,
    SERVER_SENSORS,
    ATTR_CPU_CORES,
    ATTR_CPU_USAGE,
    ATTR_MEM_TOTAL,
    ATTR_MEM_USED,
    ATTR_MEM_FREE,
    ATTR_MEM_PCT,
    ATTR_UPTIME,
    ATTR_DISKS,
    ATTR_DOCKER,
    ATTR_SERVICES,
    ATTR_PORTS,
    ATTR_LOAD,
    ATTR_OS,
    ATTR_KERNEL,
    CONF_HOST,
    CONF_NAME,
    CONF_PLATFORM,
    UNIT_PCT,
    UNIT_BYTES,
)
from .coordinator import TechlanDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка сенсоров."""
    coordinator: TechlanDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []

    # HAOS сенсоры
    for sensor_key, description in HAOS_SENSORS.items():
        entities.append(TechlanHaosSensor(coordinator, entry, sensor_key, description))

    # Серверные сенсоры
    for server_id in coordinator.server_configs:
        config = coordinator.server_configs[server_id]
        for sensor_key, description in SERVER_SENSORS.items():
            entities.append(
                TechlanServerSensor(
                    coordinator, entry, server_id, config, sensor_key, description
                )
            )

    async_add_entities(entities)


class BaseTechlanSensor(CoordinatorEntity[TechlanDataCoordinator], SensorEntity):
    """Базовый сенсор Techlan Monitor."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: TechlanDataCoordinator,
        entry: ConfigEntry,
        sensor_key: str,
        description: SensorEntityDescription,
    ) -> None:
        """Инициализация."""
        super().__init__(coordinator)
        self.entity_description = description
        self._sensor_key = sensor_key
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{sensor_key}"
        self._attr_should_poll = False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Обновление от координатора."""
        self._update_state()
        self.async_write_ha_state()

    def _get_value(self) -> Any:
        """Получить значение — переопределяется в наследниках."""
        return None


class TechlanHaosSensor(BaseTechlanSensor):
    """Сенсор HAOS из Supervisor API."""

    _attr_translation_key = "haos"

    def __init__(
        self,
        coordinator: TechlanDataCoordinator,
        entry: ConfigEntry,
        sensor_key: str,
        description: SensorEntityDescription,
    ) -> None:
        """Инициализация."""
        super().__init__(coordinator, entry, sensor_key, description)
        self._attr_unique_id = f"{entry.entry_id}_{sensor_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "haos")},
        )

    @property
    def native_value(self) -> Any:
        """Текущее значение сенсора."""
        return self._get_value()

    def _get_value(self) -> Any:
        """Получить значение из данных HAOS."""
        data = self.coordinator.data
        if not data:
            return None
        haos = data.get("haos", {})

        value_map = {
            "haos_cpu_usage": lambda d: d.get("cpu_usage"),
            "haos_memory_usage": lambda d: d.get("memory_usage"),
            "haos_disk_usage": lambda d: d.get("disk_usage"),
            "haos_uptime": lambda d: self._format_uptime(d.get("uptime_sec", 0)),
            "haos_cpu_temp": lambda d: d.get("cpu_temp"),
            "haos_cpu_freq": lambda d: d.get("cpu_freq"),
            "haos_load_1m": lambda d: (
                str(d.get("load", [0, 0, 0])[0])
                if isinstance(d.get("load"), list)
                else d.get("load")
            ),
            "haos_load_5m": lambda d: (
                str(d.get("load", [0, 0, 0])[1])
                if isinstance(d.get("load"), list)
                else d.get("load")
            ),
            "haos_load_15m": lambda d: (
                str(d.get("load", [0, 0, 0])[2])
                if isinstance(d.get("load"), list)
                else d.get("load")
            ),
            "haos_hostname": lambda d: d.get("hostname", ""),
            "haos_os": lambda d: d.get("os", ""),
            "haos_agent_version": lambda d: d.get("agent_version", ""),
        }

        getter = value_map.get(self._sensor_key)
        if getter:
            return getter(haos)
        return None

    @staticmethod
    def _format_uptime(sec: int) -> str:
        """Форматирование uptime."""
        days = sec // 86400
        hours = (sec % 86400) // 3600
        minutes = (sec % 3600) // 60
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts) if parts else "0m"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Дополнительные атрибуты."""
        data = self.coordinator.data
        if not data:
            return None
        haos = data.get("haos", {})

        attrs: dict[str, Any] = {}
        if cpu := haos.get("cpu_usage"):
            attrs[ATTR_CPU_USAGE] = cpu
        if mem := haos.get("memory_usage"):
            attrs[ATTR_MEM_PCT] = mem
        if disk := haos.get("disk_usage"):
            attrs["disk_usage"] = disk
        return attrs or None


class TechlanServerSensor(BaseTechlanSensor):
    """Сенсор удалённого сервера."""

    _attr_translation_key = "server"

    def __init__(
        self,
        coordinator: TechlanDataCoordinator,
        entry: ConfigEntry,
        server_id: str,
        config: dict[str, Any],
        sensor_key: str,
        description: SensorEntityDescription,
    ) -> None:
        """Инициализация."""
        super().__init__(coordinator, entry, sensor_key, description)
        self._server_id = server_id
        self._server_config = config
        hostname = config.get(CONF_HOST, "unknown")
        self._attr_unique_id = f"{entry.entry_id}_{server_id}_{sensor_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, server_id)},
            name=config.get(CONF_NAME, hostname),
            model=config.get(CONF_PLATFORM, "linux").capitalize(),
            manufacturer="Techlan",
            via_device=(DOMAIN, "haos"),
        )

    @property
    def native_value(self) -> Any:
        """Текущее значение сенсора."""
        return self._get_value()

    def _get_value(self) -> Any:
        """Получить значение из данных сервера."""
        data = self.coordinator.data
        if not data:
            return None
        server = data.get("servers", {}).get(self._server_id, {})
        if not server.get("online"):
            return None

        value_map: dict[str, Callable[[dict], Any]] = {
            "cpu_usage": lambda d: (
                d.get("cpu", {}).get("usage")
                if isinstance(d.get("cpu"), dict)
                else None
            ),
            "memory_pct": lambda d: (
                d.get("memory", {}).get("pct")
                if isinstance(d.get("memory"), dict)
                else None
            ),
            "memory_total": lambda d: (
                d.get("memory", {}).get("total")
                if isinstance(d.get("memory"), dict)
                else None
            ),
            "memory_used": lambda d: (
                d.get("memory", {}).get("used")
                if isinstance(d.get("memory"), dict)
                else None
            ),
            "memory_free": lambda d: (
                d.get("memory", {}).get("free")
                if isinstance(d.get("memory"), dict)
                else None
            ),
            "uptime": lambda d: d.get("uptime_str", ""),
            "load": lambda d: d.get("load", ""),
            "hostname": lambda d: d.get("hostname", ""),
        }

        getter = value_map.get(self._sensor_key)
        if getter:
            return getter(server)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Дополнительные атрибуты."""
        data = self.coordinator.data
        if not data:
            return None
        server = data.get("servers", {}).get(self._server_id, {})
        if not server.get("online"):
            return {"online": False}

        attrs: dict[str, Any] = {"online": True}

        # CPU
        if cpu := server.get("cpu", {}):
            if isinstance(cpu, dict):
                if cores := cpu.get("cores"):
                    attrs[ATTR_CPU_CORES] = cores
                if usage := cpu.get("usage"):
                    attrs[ATTR_CPU_USAGE] = usage

        # Memory
        if mem := server.get("memory", {}):
            if isinstance(mem, dict):
                if total := mem.get("total"):
                    attrs[ATTR_MEM_TOTAL] = total
                if used := mem.get("used"):
                    attrs[ATTR_MEM_USED] = used
                if free := mem.get("free"):
                    attrs[ATTR_MEM_FREE] = free

        # Disks
        if disks := server.get("disks"):
            attrs[ATTR_DISKS] = disks

        # Docker
        if docker := server.get("docker", {}):
            containers = docker.get("containers", [])
            attrs[ATTR_DOCKER] = len(containers)

        # Services
        if services := server.get("services"):
            active = [s for s in services if s.get("active") == "running"]
            attrs[ATTR_SERVICES] = len(active)

        # Ports
        if ports := server.get("ports"):
            attrs[ATTR_PORTS] = ports

        # Load
        if load := server.get("load"):
            attrs[ATTR_LOAD] = load

        # OS
        if os_name := server.get("os"):
            attrs[ATTR_OS] = os_name
        if kernel := server.get("kernel"):
            attrs[ATTR_KERNEL] = kernel

        # Uptime
        if uptime_sec := server.get("uptime_sec"):
            attrs[ATTR_UPTIME] = uptime_sec

        # Platform
        attrs["platform"] = server.get("platform", "unknown")

        # Ошибки
        if error := server.get("error"):
            attrs["error"] = error

        return attrs if len(attrs) > 1 else None
