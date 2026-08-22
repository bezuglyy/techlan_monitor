"""Инициализация интеграции Techlan Monitor."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue

from .const import DOMAIN, PLATFORMS
from .coordinator import TechlanDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Настройка интеграции через config entry."""
    _LOGGER.info("Setting up Techlan Monitor (version %s)", entry.version)

    coordinator = TechlanDataCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Загрузка платформ
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Регистрация серверов в device registry
    _register_devices(hass, entry, coordinator)

    # Остановка coordinator при выключении HA
    async def _async_stop(_event: Any) -> None:
        await coordinator.async_shutdown()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузка интеграции."""
    _LOGGER.info("Unloading Techlan Monitor")
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator:
            await coordinator.async_shutdown()
    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Обновление options (вызывается после OptionsFlow)."""
    _LOGGER.info("Options updated for Techlan Monitor, reloading...")
    await hass.config_entries.async_reload(entry.entry_id)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Миграция config entry при обновлении версии."""
    _LOGGER.debug("Migrating from version %s", entry.version)
    if entry.version == 1:
        # Пока миграций нет
        pass
    entry.version = 1
    return True


def _register_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: TechlanDataCoordinator,
) -> None:
    """Регистрация HAOS device и устройств серверов в device registry."""
    dev_reg = dr.async_get(hass)

    # HAOS device
    haos_name = coordinator.haos_hostname or "Home Assistant OS"
    haos_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "haos")},
        name=haos_name,
        model="HAOS",
        manufacturer="Techlan",
        sw_version=coordinator.haos_version or "",
    )
    coordinator.haos_device_id = haos_device.id

    # Серверные устройства
    for server_id, server_info in coordinator.server_configs.items():
        hostname = server_info.get("hostname") or server_info.get("host", server_id)
        platform = server_info.get("platform", "linux")
        dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, server_id)},
            name=server_info.get("name", hostname),
            model=platform.capitalize(),
            manufacturer="Techlan",
            sw_version="",
            via_device=(DOMAIN, "haos"),
        )
