"""Кнопки для Techlan Monitor.

- HAOS: reboot core / restart haos
- Серверы: reboot server
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PLATFORM
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    HAOS_BUTTONS,
    SERVER_BUTTONS,
)
from .coordinator import TechlanDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка кнопок."""
    coordinator: TechlanDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[ButtonEntity] = []

    # HAOS кнопки
    for button_key, description in HAOS_BUTTONS.items():
        entities.append(TechlanHaosButton(coordinator, entry, button_key, description))

    # Серверные кнопки
    for server_id, config in coordinator.server_configs.items():
        for button_key, description in SERVER_BUTTONS.items():
            entities.append(
                TechlanServerButton(
                    coordinator, entry, server_id, config, button_key, description
                )
            )

    async_add_entities(entities)


class TechlanHaosButton(CoordinatorEntity[TechlanDataCoordinator], ButtonEntity):
    """Кнопка на HAOS (reboot core / restart haos)."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: TechlanDataCoordinator,
        entry: ConfigEntry,
        button_key: str,
        description: ButtonEntityDescription,
    ) -> None:
        """Инициализация."""
        super().__init__(coordinator)
        self.entity_description = description
        self._button_key = button_key
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{button_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "haos")},
        )

    async def async_press(self) -> None:
        """Нажатие кнопки."""
        try:
            token = self.coordinator._get_supervisor_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            if self._button_key == "reboot_core":
                # Перезагрузка HA Core через Supervisor API
                async with self.coordinator.session.post(
                    "http://supervisor/core/reboot",
                    headers=headers,
                    timeout=self.coordinator.session._default_timeout,
                ) as resp:
                    resp.raise_for_status()

            elif self._button_key == "restart_haos":
                # Перезагрузка всей HAOS
                async with self.coordinator.session.post(
                    "http://supervisor/host/reboot",
                    headers=headers,
                    timeout=self.coordinator.session._default_timeout,
                ) as resp:
                    resp.raise_for_status()

        except Exception as err:
            from homeassistant.helpers import issue_registry

            issue_registry.async_create_issue(
                self.hass,
                DOMAIN,
                f"{self._button_key}_failed",
                is_fixable=False,
                severity=issue_registry.IssueSeverity.ERROR,
                translation_key="button_failed",
                translation_placeholders={
                    "button": self._button_key,
                    "error": str(err),
                },
            )


class TechlanServerButton(CoordinatorEntity[TechlanDataCoordinator], ButtonEntity):
    """Кнопка на удалённом сервере (reboot)."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: TechlanDataCoordinator,
        entry: ConfigEntry,
        server_id: str,
        config: dict[str, Any],
        button_key: str,
        description: ButtonEntityDescription,
    ) -> None:
        """Инициализация."""
        super().__init__(coordinator)
        self.entity_description = description
        self._button_key = button_key
        self._server_id = server_id
        self._entry = entry
        hostname = config.get(CONF_HOST, "unknown")
        self._attr_unique_id = f"{entry.entry_id}_{server_id}_{button_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, server_id)},
            name=config.get(CONF_NAME, hostname),
            model=config.get(CONF_PLATFORM, "linux").capitalize(),
            manufacturer="Techlan",
            via_device=(DOMAIN, "haos"),
        )

    async def async_press(self) -> None:
        """Нажатие кнопки: перезагрузка сервера."""
        await self.coordinator.async_reboot_server(self._server_id)
