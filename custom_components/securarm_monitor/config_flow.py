"""Config and Options Flow для Techlan Monitor."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .installer import install_agent
from .const import (
    CONF_AGENT_INSTALLED,
    CONF_PLATFORM,
    CONF_PORT,
    CONF_REBOOT_CONFIRM_SECONDS,
    CONF_SERVERS,
    CONF_TOKEN,
    CONF_USE_HTTPS,
    CONF_VERIFY_TLS,
    CONFIG_MINOR_VERSION,
    DEFAULT_AGENT_PORT,
    DEFAULT_REBOOT_CONFIRM_SECONDS,
    DOMAIN,
    PLATFORM_LINUX,
    PLATFORM_WINDOWS,
)

_LOGGER = logging.getLogger(__name__)


class TechlanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow для Techlan Monitor."""

    VERSION = 1
    MINOR_VERSION = CONFIG_MINOR_VERSION

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Первый шаг — создание интеграции."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="SecurARM Monitor", data={})

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> TechlanOptionsFlow:
        """Вернуть OptionsFlow."""
        return TechlanOptionsFlow()


class TechlanOptionsFlow(OptionsFlow):
    """Options flow для управления серверами."""

    _server_id: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Главное меню управления серверами."""
        servers = self._get_servers()

        menu_options = ["add_server"]
        if servers:
            menu_options.append("remove_server")
            menu_options.append("list_servers")
        menu_options.append("install_agent")
        menu_options.append("settings")

        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Общие настройки (окно подтверждения перезагрузки)."""
        servers = self._get_servers()
        if user_input is not None:
            seconds = int(
                user_input.get(
                    CONF_REBOOT_CONFIRM_SECONDS, DEFAULT_REBOOT_CONFIRM_SECONDS
                )
            )
            return self.async_create_entry(
                title="",
                data={
                    CONF_SERVERS: servers,
                    CONF_REBOOT_CONFIRM_SECONDS: max(5, seconds),
                },
            )
        current = self.config_entry.options.get(
            CONF_REBOOT_CONFIRM_SECONDS, DEFAULT_REBOOT_CONFIRM_SECONDS
        )
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_REBOOT_CONFIRM_SECONDS, default=int(current)
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=3600)),
                }
            ),
        )

    async def async_step_add_server(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Добавить сервер."""
        if user_input is not None:
            host = user_input[CONF_HOST]
            name = user_input.get(CONF_NAME, host)
            platform = user_input.get(CONF_PLATFORM, PLATFORM_LINUX)
            port = user_input.get(CONF_PORT, DEFAULT_AGENT_PORT)
            token = user_input.get(CONF_TOKEN, "")
            ssh_user = user_input.get(CONF_USERNAME, "")
            ssh_pass = user_input.get(CONF_PASSWORD, "")

            server_id = f"server_{host.replace('.', '_')}"
            servers = self._get_servers()
            servers[server_id] = {
                CONF_HOST: host,
                CONF_NAME: name,
                CONF_PLATFORM: platform,
                CONF_PORT: port,
                CONF_TOKEN: token,
                CONF_USERNAME: ssh_user,
                CONF_PASSWORD: ssh_pass,
                CONF_AGENT_INSTALLED: False,
                CONF_USE_HTTPS: bool(user_input.get(CONF_USE_HTTPS, False)),
                CONF_VERIFY_TLS: bool(user_input.get(CONF_VERIFY_TLS, True)),
            }

            return self._save_and_finish(servers)

        return self.async_show_form(
            step_id="add_server",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Optional(CONF_NAME): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Optional(CONF_PLATFORM, default=PLATFORM_LINUX): vol.In(
                        [PLATFORM_LINUX, PLATFORM_WINDOWS]
                    ),
                    vol.Optional(CONF_PORT, default=DEFAULT_AGENT_PORT): vol.All(
                        vol.Coerce(int), vol.Range(min=1024, max=65535)
                    ),
                    vol.Optional(CONF_TOKEN, default=""): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(CONF_USERNAME, default=""): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Optional(CONF_PASSWORD, default=""): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(CONF_USE_HTTPS, default=False): bool,
                    vol.Optional(CONF_VERIFY_TLS, default=True): bool,
                }
            ),
        )

    async def async_step_remove_server(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Удалить сервер."""
        servers = self._get_servers()

        if user_input is not None:
            server_id = user_input.get("server_id")
            if server_id and server_id in servers:
                servers.pop(server_id)
            return self._save_and_finish(servers)

        return self.async_show_form(
            step_id="remove_server",
            data_schema=vol.Schema(
                {
                    vol.Required("server_id"): vol.In(list(servers.keys())),
                }
            ),
        )

    async def async_step_list_servers(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Список серверов."""
        servers = self._get_servers()
        lines = []
        for sid, info in servers.items():
            host = info.get(CONF_HOST, "?")
            name = info.get(CONF_NAME, host)
            platform = info.get(CONF_PLATFORM, "?")
            installed = "✅" if info.get(CONF_AGENT_INSTALLED) else "❌"
            lines.append(
                f"• **{name}** ({sid}) — {host} [{platform}] Agent:{installed}"
            )

        text = "\n".join(lines) if lines else "Нет добавленных серверов."

        return self.async_show_form(
            step_id="list_servers",
            data_schema=vol.Schema({}),
            description_placeholders={"servers": text},
        )

    async def async_step_install_agent(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Установка агента на сервер (SSH)."""
        servers = self._get_servers()
        uninstalled = {
            sid: info
            for sid, info in servers.items()
            if not info.get(CONF_AGENT_INSTALLED)
        }

        if not uninstalled:
            return self.async_abort(reason="all_agents_installed")

        if user_input is not None:
            if not user_input.get("confirm"):
                return self.async_abort(reason="install_not_confirmed")
            server_id = user_input["server_id"]
            info = servers.get(server_id)
            if info:
                token = await self._install_agent_via_ssh(info)
                if token:
                    info[CONF_AGENT_INSTALLED] = True
                    info[CONF_TOKEN] = token
                    servers[server_id] = info
                    return self._save_and_finish(servers)
                return self.async_abort(reason="install_failed")

        return self.async_show_form(
            step_id="install_agent",
            data_schema=vol.Schema(
                {
                    vol.Required("server_id"): vol.In(list(uninstalled.keys())),
                    vol.Required("confirm", default=False): bool,
                }
            ),
        )

    async def _install_agent_via_ssh(self, info: dict[str, Any]) -> str | None:
        """Установка агента через SSH; возвращает выданный токен."""
        host = info.get(CONF_HOST, "")
        ssh_user = info.get(CONF_USERNAME, "root")
        ssh_pass = info.get(CONF_PASSWORD, "")
        platform = info.get(CONF_PLATFORM, PLATFORM_LINUX)
        port = info.get(CONF_PORT, DEFAULT_AGENT_PORT)

        if not host or not ssh_user:
            _LOGGER.error("SSH credentials not configured for %s", host)
            return None

        try:
            return await install_agent(
                self.hass,
                host=host,
                username=ssh_user,
                password=ssh_pass,
                port=port,
                platform=platform,
                token=info.get(CONF_TOKEN) or None,
            )
        except Exception as err:
            _LOGGER.exception("Agent install failed for %s: %s", host, err)
            return None

    # ─── helpers ──────────────────────────────────────────────────────

    def _get_servers(self) -> dict[str, dict[str, Any]]:
        """Получить словарь серверов из options."""
        return dict(self.config_entry.options.get(CONF_SERVERS, {}))

    def _save_and_finish(self, servers: dict[str, Any]) -> FlowResult:
        """Сохранить options (сохраняя общие скаляры) и завершить."""
        data: dict[str, Any] = {CONF_SERVERS: servers}
        if CONF_REBOOT_CONFIRM_SECONDS in self.config_entry.options:
            data[CONF_REBOOT_CONFIRM_SECONDS] = self.config_entry.options[
                CONF_REBOOT_CONFIRM_SECONDS
            ]
        return self.async_create_entry(title="", data=data)
