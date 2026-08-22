"""Константы интеграции techlan_monitor."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.button import ButtonEntityDescription
from homeassistant.helpers.entity import EntityCategory, EntityDescription

DOMAIN: Final = "techlan_monitor"
VERSION: Final = "1.0.0"

# Платформы
PLATFORMS: Final[list[str]] = ["sensor", "binary_sensor", "button"]

# Порты
DEFAULT_AGENT_PORT: Final = 9100
CONF_PORT: Final = "agent_port"

# Параметры конфигурации
CONF_SERVERS: Final = "servers"
CONF_HOST: Final = "host"
CONF_NAME: Final = "name"
CONF_PLATFORM: Final = "platform"  # "linux" или "windows"
CONF_TOKEN: Final = "token"
CONF_SSH_USER: Final = "ssh_user"
CONF_SSH_PASS: Final = "ssh_pass"
CONF_AGENT_INSTALLED: Final = "agent_installed"

# Типы платформ
PLATFORM_LINUX: Final = "linux"
PLATFORM_WINDOWS: Final = "windows"

# Иконки
ICON_MEMORY: Final = "mdi:memory"
ICON_CPU: Final = "mdi:cpu-64-bit"
ICON_DISK: Final = "mdi:harddisk"
ICON_UPTIME: Final = "mdi:clock-outline"
ICON_LOAD: Final = "mdi:chart-bell-curve"
ICON_DOCKER: Final = "mdi:docker"
ICON_SERVICE: Final = "mdi:checkbox-marked-circle-outline"
ICON_PORT: Final = "mdi:lan"
ICON_SERVER: Final = "mdi:server"
ICON_HOSTNAME: Final = "mdi:tag-text-outline"
ICON_OS: Final = "mdi:information-outline"
ICON_KERNEL: Final = "mdi:chip"

# Атрибуты
ATTR_CPU_CORES: Final = "cores"
ATTR_CPU_USAGE: Final = "cpu_usage"
ATTR_MEM_TOTAL: Final = "memory_total"
ATTR_MEM_USED: Final = "memory_used"
ATTR_MEM_FREE: Final = "memory_free"
ATTR_MEM_PCT: Final = "memory_pct"
ATTR_UPTIME: Final = "uptime_sec"
ATTR_DISKS: Final = "disks"
ATTR_DOCKER: Final = "docker_containers"
ATTR_SERVICES: Final = "active_services"
ATTR_PORTS: Final = "listening_ports"
ATTR_LOAD: Final = "load"
ATTR_OS: Final = "os"
ATTR_KERNEL: Final = "kernel"

# Единицы измерения
UNIT_PCT: Final = "%"
UNIT_BYTES: Final = "B"
UNIT_CORES: Final = "cores"
UNIT_PORTS: Final = "ports"

# --- HAOS сенсоры (локальный Supervisor API) ---

HAOS_SENSORS: Final[dict[str, SensorEntityDescription]] = {
    "haos_cpu_usage": SensorEntityDescription(
        key="haos_cpu_usage",
        name="HAOS CPU Usage",
        native_unit_of_measurement=UNIT_PCT,
        suggested_unit_of_measurement=UNIT_PCT,
        suggested_display_precision=1,
        icon=ICON_CPU,
    ),
    "haos_memory_usage": SensorEntityDescription(
        key="haos_memory_usage",
        name="HAOS Memory Usage",
        native_unit_of_measurement=UNIT_PCT,
        suggested_unit_of_measurement=UNIT_PCT,
        suggested_display_precision=1,
        icon=ICON_MEMORY,
    ),
    "haos_disk_usage": SensorEntityDescription(
        key="haos_disk_usage",
        name="HAOS Disk Usage",
        native_unit_of_measurement=UNIT_PCT,
        suggested_unit_of_measurement=UNIT_PCT,
        suggested_display_precision=1,
        icon=ICON_DISK,
    ),
    "haos_uptime": SensorEntityDescription(
        key="haos_uptime",
        name="HAOS Uptime",
        icon=ICON_UPTIME,
    ),
    "haos_cpu_temp": SensorEntityDescription(
        key="haos_cpu_temp",
        name="HAOS CPU Temperature",
        native_unit_of_measurement="°C",
        suggested_unit_of_measurement="°C",
        suggested_display_precision=1,
        device_class="temperature",
        icon=ICON_CPU,
    ),
    "haos_cpu_freq": SensorEntityDescription(
        key="haos_cpu_freq",
        name="HAOS CPU Frequency",
        native_unit_of_measurement="MHz",
        suggested_unit_of_measurement="MHz",
        icon=ICON_CPU,
    ),
    "haos_load_1m": SensorEntityDescription(
        key="haos_load_1m",
        name="HAOS Load 1m",
        icon=ICON_LOAD,
    ),
    "haos_load_5m": SensorEntityDescription(
        key="haos_load_5m",
        name="HAOS Load 5m",
        icon=ICON_LOAD,
    ),
    "haos_load_15m": SensorEntityDescription(
        key="haos_load_15m",
        name="HAOS Load 15m",
        icon=ICON_LOAD,
    ),
    "haos_hostname": SensorEntityDescription(
        key="haos_hostname",
        name="HAOS Hostname",
        icon=ICON_HOSTNAME,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "haos_os": SensorEntityDescription(
        key="haos_os",
        name="HAOS Version",
        icon=ICON_OS,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "haos_agent_version": SensorEntityDescription(
        key="haos_agent_version",
        name="HAOS Agent Version",
        icon=ICON_HOSTNAME,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}

# --- Серверные сенсоры (удалённые агенты) ---

SERVER_SENSORS: Final[dict[str, SensorEntityDescription]] = {
    "cpu_usage": SensorEntityDescription(
        key="cpu_usage",
        name="CPU Usage",
        native_unit_of_measurement=UNIT_PCT,
        suggested_unit_of_measurement=UNIT_PCT,
        suggested_display_precision=1,
        icon=ICON_CPU,
    ),
    "memory_pct": SensorEntityDescription(
        key="memory_pct",
        name="Memory Usage",
        native_unit_of_measurement=UNIT_PCT,
        suggested_unit_of_measurement=UNIT_PCT,
        suggested_display_precision=1,
        icon=ICON_MEMORY,
    ),
    "memory_total": SensorEntityDescription(
        key="memory_total",
        name="Memory Total",
        native_unit_of_measurement=UNIT_BYTES,
        suggested_unit_of_measurement=UNIT_BYTES,
        device_class="data_size",
        icon=ICON_MEMORY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "memory_used": SensorEntityDescription(
        key="memory_used",
        name="Memory Used",
        native_unit_of_measurement=UNIT_BYTES,
        suggested_unit_of_measurement=UNIT_BYTES,
        device_class="data_size",
        icon=ICON_MEMORY,
    ),
    "memory_free": SensorEntityDescription(
        key="memory_free",
        name="Memory Free",
        native_unit_of_measurement=UNIT_BYTES,
        suggested_unit_of_measurement=UNIT_BYTES,
        device_class="data_size",
        icon=ICON_MEMORY,
    ),
    "uptime": SensorEntityDescription(
        key="uptime",
        name="Uptime",
        icon=ICON_UPTIME,
    ),
    "load": SensorEntityDescription(
        key="load",
        name="Load Average",
        icon=ICON_LOAD,
    ),
    "hostname": SensorEntityDescription(
        key="hostname",
        name="Hostname",
        icon=ICON_HOSTNAME,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}

# --- Серверные Binary Sensor ---

SERVER_BINARY_SENSORS: Final[dict[str, BinarySensorEntityDescription]] = {
    "alive": BinarySensorEntityDescription(
        key="alive",
        name="Server Online",
        device_class="connectivity",
        icon=ICON_SERVER,
    ),
}

# --- Серверные Button ---

SERVER_BUTTONS: Final[dict[str, ButtonEntityDescription]] = {
    "reboot": ButtonEntityDescription(
        key="reboot",
        name="Reboot Server",
        icon="mdi:restart",
        entity_category=EntityCategory.CONFIG,
    ),
}

# --- HAOS кнопки ---

HAOS_BUTTONS: Final[dict[str, ButtonEntityDescription]] = {
    "reboot_core": ButtonEntityDescription(
        key="reboot_core",
        name="Reboot HA Core",
        icon="mdi:home-restart",
        entity_category=EntityCategory.CONFIG,
    ),
    "restart_haos": ButtonEntityDescription(
        key="restart_haos",
        name="Restart HAOS",
        icon="mdi:restart",
        entity_category=EntityCategory.CONFIG,
    ),
}

# Максимальное время ожидания HTTP-запроса к агенту (сек)
HTTP_TIMEOUT: Final = 15
