"""Кнопки для Techlan Monitor.

- HAOS: reboot core / restart haos
- Серверы: reboot server

Каждая кнопка перезагрузки требует включённого предохранителя
(switch «Разрешить перезагрузку», см. ``switch.py``). Иначе выставляется
Repair и поднимается ``HomeAssistantError`` — случайной перезагрузки нет.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PLATFORM
from homeassistant.core import HomeAssistant, HomeAssistantError
from homeassistant.helpers import issue_registry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._shared.shared_entities import build_device_info

from .const import (
    DOMAIN,
    HAOS_BUTTONS,
    SERVER_BUTTONS,
)
from .coordinator import TechlanDataCoordinator


def _require_reboot_armed(coordinator: TechlanDataCoordinator, target_id: str) -> None:
    """Raise unless the reboot interlock for ``target_id`` is armed."""
    if coordinator.is_reboot_armed(target_id):
        return
    issue_registry.async_create_issue(
        coordinator.hass,
        DOMAIN,
        f"reboot_not_confirmed_{target_id}",
        is_fixable=False,
        severity=issue_registry.IssueSeverity.WARNING,
        translation_key="reboot_not_confirmed",
        translation_placeholders={"target": target_id},
    )
    raise HomeAssistantError(
        f"Перезагрузка {target_id} не подтверждена: включите switch "
        "«Разрешить перезагрузку» и повторите в течение окна подтверждения."
    )


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
        self._attr_device_info = build_device_info(
            identifiers={(DOMAIN, "haos")},
            name=coordinator.haos_hostname or "Home Assistant OS",
            model="HAOS",
            sw_version=coordinator.haos_version or None,
        )

    async def async_press(self) -> None:
        """Нажатие кнопки."""
        _require_reboot_armed(self.coordinator, "haos")
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
            raise
        finally:
            # One-shot: consume the interlock after a press attempt.
            self.coordinator.disarm_reboot("haos")


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
        self._attr_device_info = build_device_info(
            identifiers={(DOMAIN, server_id)},
            name=config.get(CONF_NAME, hostname),
            model=config.get(CONF_PLATFORM, "linux").capitalize(),
            manufacturer="Techlan",
            via_device_id=self.coordinator.haos_device_id,
            via_device=(DOMAIN, "haos"),
        )

    async def async_press(self) -> None:
        """Нажатие кнопки: перезагрузка сервера (подтверждённая)."""
        _require_reboot_armed(self.coordinator, self._server_id)
        try:
            await self.coordinator.async_reboot_server(self._server_id)
        finally:
            # One-shot: consume the interlock after a press attempt.
            self.coordinator.disarm_reboot(self._server_id)
