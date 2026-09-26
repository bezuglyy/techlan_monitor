"""Инициализация интеграции Techlan Monitor.

Мониторинг HAOS и удалённых серверов (агент :9100). Кнопки перезагрузки
защищены предохранителем (switch) и сервисами с ``confirm: true``.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, HomeAssistantError, ServiceCall
from homeassistant.helpers import issue_registry

from .const import (
    CONF_AGENT_INSTALLED,
    CONF_REBOOT_CONFIRM_SECONDS,
    CONF_SERVERS,
    CONF_TOKEN,
    CONF_USE_HTTPS,
    CONF_VERIFY_TLS,
    CONFIG_MINOR_VERSION,
    DEFAULT_REBOOT_CONFIRM_SECONDS,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import TechlanDataCoordinator
from ._shared.shared_entities import async_get_or_create_device

_LOGGER = logging.getLogger(__name__)

# Дефолты, добавляемые миграцией (для существующих установок).
_MIGRATION_SERVER_DEFAULTS: dict[str, Any] = {
    CONF_USE_HTTPS: False,
    CONF_VERIFY_TLS: True,
}


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register integration services once."""
    _register_services(hass)
    return True


def _get_coordinator(hass: HomeAssistant) -> TechlanDataCoordinator:
    for coordinator in hass.data.get(DOMAIN, {}).values():
        return coordinator
    raise HomeAssistantError("Интеграция Techlan Monitor ещё не загружена")


def _register_services(hass: HomeAssistant) -> None:
    """Register confirmed power management services."""
    if hass.services.has_service(DOMAIN, "reboot_server"):
        return

    server_schema = vol.Schema(
        {
            vol.Required("server_id"): str,
            vol.Required("confirm", default=False): vol.Coerce(bool),
        }
    )
    confirm_schema = vol.Schema(
        {vol.Required("confirm", default=False): vol.Coerce(bool)}
    )

    async def handle_reboot_server(call: ServiceCall) -> None:
        if not call.data["confirm"]:
            raise HomeAssistantError("Для перезагрузки требуется confirm: true")
        coordinator = _get_coordinator(hass)
        server_id = call.data["server_id"]
        if server_id not in coordinator.server_configs:
            raise HomeAssistantError(f"Сервер {server_id} не найден")
        ok = await coordinator.async_reboot_server(server_id)
        if not ok:
            raise HomeAssistantError(
                f"Агент сервера {server_id} не подтвердил перезагрузку"
            )
        coordinator.disarm_reboot(server_id)

    async def handle_restart_haos(call: ServiceCall) -> None:
        if not call.data["confirm"]:
            raise HomeAssistantError("Для перезагрузки требуется confirm: true")
        coordinator = _get_coordinator(hass)
        await _supervisor_post(coordinator, "host/reboot")

    async def handle_reboot_core(call: ServiceCall) -> None:
        if not call.data["confirm"]:
            raise HomeAssistantError("Для перезагрузки требуется confirm: true")
        coordinator = _get_coordinator(hass)
        await _supervisor_post(coordinator, "core/reboot")

    hass.services.async_register(
        DOMAIN, "reboot_server", handle_reboot_server, server_schema
    )
    hass.services.async_register(
        DOMAIN, "restart_haos", handle_restart_haos, confirm_schema
    )
    hass.services.async_register(
        DOMAIN, "reboot_core", handle_reboot_core, confirm_schema
    )


async def _supervisor_post(coordinator: TechlanDataCoordinator, path: str) -> None:
    """POST a Supervisor action with the local token."""
    token = coordinator._get_supervisor_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    async with coordinator.session.post(
        f"http://supervisor/{path}",
        headers=headers,
        timeout=coordinator.session._default_timeout,
    ) as resp:
        resp.raise_for_status()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Настройка интеграции через config entry."""
    _LOGGER.info("Setting up Techlan Monitor (version %s)", entry.version)

    coordinator = TechlanDataCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Регистрация устройств ДО платформ, чтобы via_device_id был доступен
    # дочерним сущностям при их создании.
    _register_devices(hass, entry, coordinator)
    _sync_token_issues(hass, entry, coordinator)

    # Загрузка платформ
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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
    """Миграция config entry при обновлении версии схемы."""
    if entry.version > 1:
        return False
    if entry.version == 1 and entry.minor_version < CONFIG_MINOR_VERSION:
        options = dict(entry.options)
        servers = dict(options.get(CONF_SERVERS, {}) or {})
        for server_id, info in servers.items():
            merged = dict(info)
            for key, default in _MIGRATION_SERVER_DEFAULTS.items():
                merged.setdefault(key, default)
            servers[server_id] = merged
        options[CONF_SERVERS] = servers
        options.setdefault(CONF_REBOOT_CONFIRM_SECONDS, DEFAULT_REBOOT_CONFIRM_SECONDS)
        hass.config_entries.async_update_entry(
            entry, options=options, minor_version=CONFIG_MINOR_VERSION
        )
        _LOGGER.info(
            "Techlan Monitor migrated to minor version %s", CONFIG_MINOR_VERSION
        )
    return True


def _sync_token_issues(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: TechlanDataCoordinator,
) -> None:
    """Raise a Repair for installed agents without a token (fail-closed)."""
    for server_id, info in coordinator.server_configs.items():
        issue_id = f"agent_token_missing_{server_id}"
        has_token = bool(str(info.get(CONF_TOKEN, "") or "").strip())
        installed = bool(info.get(CONF_AGENT_INSTALLED))
        if installed and not has_token:
            issue_registry.async_create_issue(
                hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=issue_registry.IssueSeverity.WARNING,
                translation_key="agent_token_missing",
                translation_placeholders={
                    "server_id": server_id,
                    "host": str(info.get("host", "")),
                },
            )
        else:
            issue_registry.async_delete_issue(hass, DOMAIN, issue_id)


def _register_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: TechlanDataCoordinator,
) -> None:
    """Регистрация HAOS device и устройств серверов в device registry."""
    # HAOS device (родительское)
    haos_name = coordinator.haos_hostname or "Home Assistant OS"
    haos_device = async_get_or_create_device(
        hass,
        entry,
        {(DOMAIN, "haos")},
        name=haos_name,
        model="HAOS",
        manufacturer="Techlan",
        sw_version=coordinator.haos_version or None,
        configuration_url=_haos_url(hass),
    )
    coordinator.haos_device_id = haos_device.id

    # Серверные устройства (дети) — version-aware ссылка на родителя
    for server_id, server_info in coordinator.server_configs.items():
        hostname = server_info.get("hostname") or server_info.get("host", server_id)
        platform = server_info.get("platform", "linux")
        async_get_or_create_device(
            hass,
            entry,
            {(DOMAIN, server_id)},
            name=server_info.get("name", hostname),
            model=platform.capitalize(),
            manufacturer="Techlan",
            via_device_id=haos_device.id,
            via_device=(DOMAIN, "haos"),
        )


def _haos_url(hass: HomeAssistant) -> str | None:
    """URL Home Assistant для DeviceInfo.configuration_url (если известен)."""
    return hass.config.external_url or hass.config.internal_url or None
