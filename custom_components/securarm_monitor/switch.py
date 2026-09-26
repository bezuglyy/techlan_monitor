"""Предохранители перезагрузки для Techlan Monitor.

Чтобы кнопка reboot не срабатывала с одного нажатия, перед ней нужно
включить switch «Разрешить перезагрузку». Предохранитель автоматически
снимается через окно подтверждения (``reboot_confirm_seconds``) или вручную.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PLATFORM
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._shared.shared_entities import build_device_info
from .const import (
    DOMAIN,
    HAOS_ARMED_KEY,
    HAOS_SWITCHES,
    SERVER_ARMED_KEY,
    SERVER_SWITCHES,
)
from .coordinator import TechlanDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка предохранителей."""
    coordinator: TechlanDataCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = []
    for key, description in HAOS_SWITCHES.items():
        entities.append(
            TechlanRebootInterlock(coordinator, entry, "haos", key, description)
        )
    for server_id, config in coordinator.server_configs.items():
        for key, description in SERVER_SWITCHES.items():
            entities.append(
                TechlanRebootInterlock(
                    coordinator, entry, server_id, key, description, config
                )
            )
    async_add_entities(entities)


class TechlanRebootInterlock(CoordinatorEntity[TechlanDataCoordinator], SwitchEntity):
    """Arm/disarm the reboot confirmation window for one target."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: TechlanDataCoordinator,
        entry: ConfigEntry,
        target_id: str,
        switch_key: str,
        description: SwitchEntityDescription,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._target_id = target_id
        self._switch_key = switch_key
        self._config = config or {}
        self._attr_unique_id = f"{entry.entry_id}_{target_id}_{switch_key}"
        if target_id == "haos":
            self._attr_device_info = build_device_info(
                identifiers={(DOMAIN, "haos")},
                name=coordinator.haos_hostname or "Home Assistant OS",
                model="HAOS",
                sw_version=coordinator.haos_version or None,
            )
        else:
            hostname = self._config.get(CONF_HOST, "unknown")
            self._attr_device_info = build_device_info(
                identifiers={(DOMAIN, target_id)},
                name=self._config.get(CONF_NAME, hostname),
                model=self._config.get(CONF_PLATFORM, "linux").capitalize(),
                manufacturer="Techlan",
                via_device_id=coordinator.haos_device_id,
                via_device=(DOMAIN, "haos"),
            )

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_reboot_armed(self._target_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "target": self._target_id,
            "remaining_seconds": self.coordinator.reboot_armed_remaining(
                self._target_id
            ),
            "window_seconds": self.coordinator.reboot_confirm_seconds,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.arm_reboot(self._target_id)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.disarm_reboot(self._target_id)
        self.async_write_ha_state()
