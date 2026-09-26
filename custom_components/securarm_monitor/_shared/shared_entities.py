"""Общие помощники устройств (DeviceInfo) для интеграций ARM/ОПС.

Копируется в ``<integration>/_shared`` скриптом ``tools/sync-ha-shared.py``.
Не редактировать копии вручную.

``via_device`` в DeviceInfo устарел (удаляется в HA 2027.8) в пользу
``via_device_id``. Однако не все поддерживаемые версии HA принимают
``via_device_id`` в ``device_registry.async_get_or_create``. Поэтому здесь
один раз определяется поддерживаемый ключ и подставляется нужный:

* современный HA — ``via_device_id`` (id родительского устройства);
* старый HA — ``via_device`` (кортеж идентификаторов родителя).

Интеграции передают оба значения и не зависят от версии HA.
"""

from __future__ import annotations

import inspect
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr


def _supports_via_device_id() -> bool:
    """Return True if this HA version accepts ``via_device_id`` in the registry."""
    try:
        params = inspect.signature(dr.DeviceRegistry.async_get_or_create).parameters
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return False
    return "via_device_id" in params


VIA_DEVICE_ID_SUPPORTED: bool = _supports_via_device_id()


def configuration_url(base_url: str) -> str:
    """Return the web-АРМ URL for DeviceInfo.configuration_url."""
    return f"{str(base_url or '').rstrip('/')}/ohrana.htm"


def build_device_info(
    *,
    identifiers: set[tuple[str, str]],
    name: str,
    manufacturer: str = "Techlan",
    model: str | None = None,
    sw_version: str | None = None,
    configuration_url: str | None = None,
    via_device_id: str | None = None,
    via_device: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Build a DeviceInfo mapping with the HA-version-appropriate parent link."""
    info: dict[str, Any] = {
        "identifiers": set(identifiers),
        "name": name,
        "manufacturer": manufacturer,
    }
    if model:
        info["model"] = model
    if sw_version:
        info["sw_version"] = sw_version
    if configuration_url:
        info["configuration_url"] = configuration_url
    if VIA_DEVICE_ID_SUPPORTED and via_device_id:
        info["via_device_id"] = via_device_id
    elif via_device:
        info["via_device"] = tuple(via_device)
    return info


def async_get_or_create_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    identifiers: set[tuple[str, str]],
    *,
    name: str,
    manufacturer: str = "Techlan",
    model: str | None = None,
    sw_version: str | None = None,
    configuration_url: str | None = None,
    via_device_id: str | None = None,
    via_device: tuple[str, str] | None = None,
) -> Any:
    """Create/update a device in the registry (parent links version-aware)."""
    device_registry = dr.async_get(hass)
    kwargs: dict[str, Any] = {
        "config_entry_id": entry.entry_id,
        "identifiers": identifiers,
        "name": name,
        "manufacturer": manufacturer,
        "model": model,
        "sw_version": sw_version,
        "configuration_url": configuration_url,
    }
    if VIA_DEVICE_ID_SUPPORTED and via_device_id:
        kwargs["via_device_id"] = via_device_id
    elif via_device:
        kwargs["via_device"] = tuple(via_device)
    return device_registry.async_get_or_create(**kwargs)


def async_resolve_device_id(
    hass: HomeAssistant, identifiers: set[tuple[str, str]]
) -> str | None:
    """Return the device_id for existing identifiers, or None (fallback)."""
    device = dr.async_get(hass).async_get_device(identifiers=identifiers)
    return device.id if device else None
