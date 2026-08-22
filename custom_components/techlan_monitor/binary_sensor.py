"""Binary sensor для Techlan Monitor.

- online/alive для каждого удалённого сервера
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PLATFORM,
    DOMAIN,
    SERVER_BINARY_SENSORS,
)
from .coordinator import TechlanDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка binary_sensor."""
    coordinator: TechlanDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[BinarySensorEntity] = []

    # alive для каждого сервера
    for server_id, config in coordinator.server_configs.items():
        for sensor_key, description in SERVER_BINARY_SENSORS.items():
            entities.append(
                TechlanServerBinarySensor(
                    coordinator, entry, server_id, config, sensor_key, description
                )
            )

    async_add_entities(entities)


class TechlanServerBinarySensor(
    CoordinatorEntity[TechlanDataCoordinator], BinarySensorEntity
):
    """Binary sensor: online/alive сервера."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: TechlanDataCoordinator,
        entry: ConfigEntry,
        server_id: str,
        config: dict[str, Any],
        sensor_key: str,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Инициализация."""
        super().__init__(coordinator)
        self.entity_description = description
        self._sensor_key = sensor_key
        self._server_id = server_id
        self._entry = entry
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
    def is_on(self) -> bool | None:
        """Состояние: online/offline."""
        data = self.coordinator.data
        if not data:
            return None
        server = data.get("servers", {}).get(self._server_id, {})
        return server.get("online", False)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Обновление от координатора."""
        self.async_write_ha_state()
