"""Diagnostics support for Techlan Monitor (секреты маскируются)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PLATFORM,
    CONF_PORT,
    CONF_REBOOT_CONFIRM_SECONDS,
    CONF_SERVERS,
    CONF_USE_HTTPS,
    CONF_VERIFY_TLS,
    DEFAULT_REBOOT_CONFIRM_SECONDS,
    DOMAIN,
    VERSION,
)

# Секреты (token/password) в дамп не включаются вовсе — см. masked_servers.


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return masked diagnostics (server tokens/passwords are never dumped)."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    servers = entry.options.get(CONF_SERVERS, {}) or {}
    masked_servers = {
        server_id: {
            CONF_HOST: cfg.get(CONF_HOST),
            CONF_NAME: cfg.get(CONF_NAME),
            CONF_PLATFORM: cfg.get(CONF_PLATFORM),
            CONF_PORT: cfg.get(CONF_PORT),
            "agent_installed": bool(cfg.get("agent_installed")),
            "has_token": bool(cfg.get("token")),
            "has_ssh_password": bool(cfg.get("password")),
            "ssh_user": cfg.get("username", ""),
            CONF_USE_HTTPS: bool(cfg.get(CONF_USE_HTTPS, False)),
            CONF_VERIFY_TLS: bool(cfg.get(CONF_VERIFY_TLS, True)),
        }
        for server_id, cfg in servers.items()
    }
    data = getattr(coordinator, "data", None) or {}
    return {
        "entry": {
            "title": entry.title,
            "domain": DOMAIN,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "integration_version": VERSION,
        },
        "settings": {
            CONF_REBOOT_CONFIRM_SECONDS: entry.options.get(
                CONF_REBOOT_CONFIRM_SECONDS, DEFAULT_REBOOT_CONFIRM_SECONDS
            ),
        },
        "servers": masked_servers,
        "snapshot": {
            "haos": data.get("haos", {}),
            "server_ids": list((data.get("servers") or {}).keys()),
            "errors": data.get("errors", []),
        },
    }
