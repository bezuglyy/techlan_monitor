"""Общий DataUpdateCoordinator для интеграций ARM/ОПС.

Копируется в ``techlan_ops/_shared/shared_coordinator.py`` и
``techlan_sensor/_shared/shared_coordinator.py`` скриптом
``tools/sync-ha-shared.py``. Не редактировать копии вручную.

Помимо опроса ServerSkif координатор:

* владеет постоянным WS-клиентом и закрывает его при выгрузке;
* хранит актуальные опции (`options`), чтобы number-сущности применялись
  без пересоздания интеграции;
* поднимает Repair (issue) при недоступности ARM-OPS/ServerSkif и убирает
  его после восстановления;
* (опционально) публикует события HA при смене состояния раздела/тревоге —
  для автоматизаций.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .shared_api import TechlanApiError
from .shared_const import ALARM_STATE_CODES

_LOGGER = logging.getLogger(__name__)


class TechlanBaseCoordinator(DataUpdateCoordinator[dict]):
    """Fetch a read-only ARM snapshot and mirror reachability into Repairs."""

    # Сколько подряд неудачных опросов до Repair (защита от флапов).
    FAILURE_THRESHOLD = 2

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        *,
        domain: str,
        client: Any,
        scan_interval: int,
        selected_loops: list[str] | None = None,
        selected_relays: list[str] | None = None,
        effective_options: dict[str, Any] | None = None,
        emit_events: bool = False,
    ) -> None:
        self.entry = entry
        self.client = client
        self.selected_loops = selected_loops
        self.selected_relays = selected_relays
        self.options = dict(effective_options or {})
        self.emit_events = emit_events
        # Заполняются интеграцией после регистрации родительского устройства.
        self.parent_device_id: str | None = None
        self.parent_identifier: tuple[str, str] = (domain, "arm")
        self.configuration_url: str = ""
        self._domain = domain
        self._failure_count = 0
        self._issue_active = False
        self._prev_states: dict[tuple[int, int], int] = {}
        self._prev_alarms: set[tuple[int, int, int]] = set()
        self._shutdown_done = False
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=domain,
            update_interval=timedelta(seconds=int(scan_interval)),
        )

    # --- runtime options ------------------------------------------------------

    def option(self, key: str, default: Any = None) -> Any:
        """Return a live option value (number entities update it in place)."""
        return self.options.get(key, default)

    def update_runtime_options(self, options: dict[str, Any]) -> None:
        """Refresh the in-memory option snapshot (no reload required)."""
        self.options = dict(options)

    # --- polling --------------------------------------------------------------

    async def _async_update_data(self) -> dict:
        try:
            # ``selected_relays`` поддерживает только клиент techlan_sensor;
            # остальные интеграции получают прежнюю сигнатуру вызова.
            extra: dict[str, Any] = {}
            if self.selected_relays is not None:
                extra["selected_relays"] = self.selected_relays
            snapshot = await self.client.async_fetch_snapshot(
                self.selected_loops, **extra
            )
        except TechlanApiError as exc:
            self._failure_count += 1
            if self._failure_count >= self.FAILURE_THRESHOLD:
                self._raise_issue(str(exc))
            raise UpdateFailed(str(exc)) from exc
        self._failure_count = 0
        self._clear_issue()
        if self.emit_events:
            self._emit_state_events(snapshot)
        return snapshot

    # --- HA events (for automations) -----------------------------------------

    def _emit_state_events(self, snapshot: dict) -> None:
        states: dict[tuple[int, int], int] = {}
        alarms: set[tuple[int, int, int]] = set()
        for pku, item in (snapshot.get("pkus") or {}).items():
            for part, details in (item.get("parts") or {}).items():
                try:
                    code = int(details.get("state_code", -1))
                except (TypeError, ValueError):
                    continue
                key = (int(pku), int(part))
                states[key] = code
                if code in ALARM_STATE_CODES:
                    alarms.add((int(pku), int(part), code))
        # First poll only establishes the baseline.
        if self._prev_states:
            for (pku, part), code in states.items():
                previous = self._prev_states.get((pku, part))
                if previous is None or previous == code:
                    continue
                self.hass.bus.async_fire(
                    f"{self._domain}_state_changed",
                    {
                        "pku": pku,
                        "part": part,
                        "from_code": previous,
                        "to_code": code,
                        "is_alarm": code in ALARM_STATE_CODES,
                    },
                )
        for pku, part, code in sorted(alarms - self._prev_alarms):
            self.hass.bus.async_fire(
                f"{self._domain}_alarm",
                {"pku": pku, "part": part, "state_code": code},
            )
        self._prev_states = states
        self._prev_alarms = alarms

    # --- Repairs (issues) -----------------------------------------------------

    @property
    def _issue_id(self) -> str:
        return f"arm_unreachable_{self.entry.entry_id}"

    def _raise_issue(self, error: str) -> None:
        if self._issue_active:
            return
        async_create_issue(
            self.hass,
            self._domain,
            self._issue_id,
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key="arm_unreachable",
            translation_placeholders={"error": error},
        )
        self._issue_active = True

    def _clear_issue(self) -> None:
        if not self._issue_active:
            return
        async_delete_issue(self.hass, self._domain, self._issue_id)
        self._issue_active = False

    # --- shutdown -------------------------------------------------------------

    async def async_shutdown(self) -> None:
        """Stop polling and close the persistent WebSocket connection."""
        if self._shutdown_done:
            return
        self._shutdown_done = True
        await super().async_shutdown()
        try:
            await self.client.async_shutdown()
        except Exception:  # noqa: BLE001 - shutdown must never raise
            _LOGGER.debug("Client shutdown failed", exc_info=True)
