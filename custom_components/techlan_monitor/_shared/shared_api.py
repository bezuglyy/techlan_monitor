"""Общий WebSocket-клиент ServerSkif через прокси ARM (канонический источник).

Копируется в ``techlan_ops/_shared/shared_api.py`` и
``techlan_sensor/_shared/shared_api.py`` скриптом ``tools/sync-ha-shared.py``.
Не редактировать копии вручную.

Слой не зависит от Home Assistant, поэтому его чистые функции и логика
соединения покрываются unit-тестами (``tools/tests/test_unit_shared.py``)
без HA-окружения.

Реализация — **одно постоянное соединение на интеграцию**:

* reader-поток непрерывно читает все кадры и складывает разобранные JSON в
  ограниченную очередь (``deque(maxlen=MAX_PENDING)``). Это снимает
  TCP-backpressure от незапрошенных широковещательных событий ServerSkif —
  раньше поток событий не вычитывался, поэтому соединение делали
  короткоживущим «на одну операцию»;
* запросы/ответы сериализуются ``threading.Lock`` (на одной сессии ServerSkif
  нельзя вести два диалога одновременно);
* реконнект с экспоненциальным backoff; keepalive-пинг при простое;
* общий дедлайн ожидания ответа (не даёт зависнуть на «полуживом» сокете);
* ``async_shutdown()`` корректно закрывает соединение и останавливает reader
  (вызывается из ``async_unload_entry`` интеграций);
* определяемая ошибка ``TechlanApiError`` для транспортных сбоев и
  ``TechlanCommandError`` для неподтверждённых команд.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from collections import deque
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

import websocket

try:  # пакетный импорт (Home Assistant)
    from .shared_const import RELAY_TIME_UNIT_SECONDS
except ImportError:  # модуль загружается как top-level (stdlib-тесты)
    from shared_const import RELAY_TIME_UNIT_SECONDS  # type: ignore[no-redef]

_LOGGER = logging.getLogger(__name__)


class TechlanApiError(Exception):
    """Raised when ARM/ServerSkif cannot answer."""


class TechlanCommandError(TechlanApiError):
    """Raised when a control command is not confirmed by the section state."""


class CannotConnectError(Exception):
    """Raised when the ARM connection settings cannot be validated."""


def websocket_url(base_url: str, ws_path: str = "/skif-ws") -> str:
    """Convert the configured HTTP ARM URL to its WebSocket proxy URL."""
    parsed = urlparse(base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "/" + ws_path.lstrip("/"), "", "", ""))


def url_is_valid(base_url: str, ws_path: str = "/skif-ws") -> bool:
    """Return True when the ARM base URL and WebSocket path look usable."""
    parsed = urlparse(str(base_url or "").rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    return str(ws_path or "").startswith("/")


def mask_secret(value: Any) -> str:
    """Mask a secret for diagnostics without revealing its length/content."""
    if value in (None, ""):
        return ""
    return "***"


def mask_url(url: str) -> str:
    """Strip URL userinfo (credentials), keeping scheme/host/port/path.

    Diagnostics must not leak embedded credentials. Internal host names/IPs
    are kept on purpose so the dump stays useful.
    """
    try:
        parsed = urlparse(str(url or ""))
    except ValueError:
        return "***"
    if not parsed.scheme or not parsed.netloc:
        return str(url or "")
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


def decode_messages(raw: Any) -> list[dict[str, Any]]:
    """Decode a ServerSkif frame that may contain several concatenated JSON objects."""
    if raw is None:
        return []
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    text = str(raw)
    decoder = json.JSONDecoder()
    messages: list[dict[str, Any]] = []
    offset = 0
    length = len(text)
    while offset < length:
        while offset < length and text[offset] not in "[{":
            offset += 1
        if offset >= length:
            break
        try:
            message, next_offset = decoder.raw_decode(text, offset)
        except json.JSONDecodeError:
            offset += 1
            continue
        if isinstance(message, dict):
            messages.append(message)
        offset = next_offset
    return messages


def parse_loop_keys(selected_loops: list[str] | None) -> set[tuple[int, int, int]]:
    """Parse ``['pku:part:sh', ...]`` into a set of integer tuples."""
    result: set[tuple[int, int, int]] = set()
    for item in selected_loops or []:
        parts = str(item).split(":")
        if len(parts) != 3:
            continue
        try:
            result.add(tuple(int(value) for value in parts))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
    return result


def loop_key(pku: int, part: int, sh: int) -> str:
    """Canonical ``pku:part:sh`` loop key used in config options."""
    return f"{int(pku)}:{int(part)}:{int(sh)}"


def state_confirms(code: Any, target: frozenset[int]) -> bool:
    """Return True when a raw state code is among the confirmation targets."""
    try:
        return int(code) in target
    except (TypeError, ValueError):
        return False


def format_loop_label(pku: int, part: int, sh: int, description: str | None) -> str:
    """Human-readable label for the HA loop selector."""
    return (
        f"ПКУ {pku} · раздел {part} · "
        f"ШС {int(sh) >> 8}/{int(sh) & 0xFF} — "
        f"{description or 'Без названия'}"
    )


# --- реле (управляемые выходы) ----------------------------------------------


def relay_key(pku: int, rl: int) -> str:
    """Canonical ``pku:rl`` relay key used in config options."""
    return f"{int(pku)}:{int(rl)}"


def parse_relay_keys(selected_relays: list[str] | None) -> set[tuple[int, int]]:
    """Parse ``['pku:rl', ...]`` into a set of ``(pku, rl)`` tuples."""
    result: set[tuple[int, int]] = set()
    for item in selected_relays or []:
        parts = str(item).split(":")
        if len(parts) != 2:
            continue
        try:
            result.add((int(parts[0]), int(parts[1])))
        except (TypeError, ValueError):
            continue
    return result


def decode_relay(rl: int) -> tuple[int, int]:
    """Split a relay id into ``(device, relay_number)`` (``rl = dev<<8 | num``)."""
    value = int(rl)
    return value >> 8, value & 0xFF


def format_relay_label(pku: int, rl: int, description: str | None) -> str:
    """Human-readable label for the HA relay selector."""
    device, number = decode_relay(rl)
    return (
        f"ПКУ {pku} · прибор {device} · реле {number} — {description or 'Без названия'}"
    )


def relay_time_units(seconds: float) -> int:
    """Convert seconds into protocol ``time`` units (1 unit = 0.125 c)."""
    units = float(seconds) / RELAY_TIME_UNIT_SECONDS
    return max(0, int(round(units)))


def _default_transport(url: str, timeout: float) -> Any:
    """Create a websocket-client connection (overridable for tests)."""
    return websocket.create_connection(
        url,
        timeout=timeout,
        http_proxy_host=None,
        http_proxy_port=None,
    )


class PersistentTechlanClient:
    """Persistent, serialised ServerSkif WebSocket client.

    Reads only a snapshot by default; subclasses add integration operations
    using ``request_sync`` (caller holds the request lock) and
    ``async_request`` (takes the lock for a single round-trip).
    """

    OPEN_TIMEOUT: float = 8.0
    # Общий бюджет ожидания одного ответа после успешного подключения.
    READ_BUDGET: float = 10.0
    # Максимум необработанных сообщений в буфере (защита от роста памяти
    # на незапрошенных широковещательных событиях ServerSkif).
    MAX_PENDING: int = 2000
    RECONNECT_MIN: float = 1.0
    RECONNECT_MAX: float = 30.0
    READER_TICK: float = 1.0

    def __init__(
        self,
        base_url: str,
        arm_id: str,
        password: str,
        ws_path: str = "/skif-ws",
        *,
        command_timeout: float = 30.0,
        keepalive: float = 25.0,
        transport_factory: Callable[[str, float], Any] | None = None,
    ) -> None:
        self._url = websocket_url(base_url, ws_path)
        self._arm_id = arm_id
        self._password = password
        self._command_timeout = float(command_timeout)
        self._keepalive = float(keepalive)
        self._factory = transport_factory or _default_transport
        # Сериализация request/response (один диалог на сессию).
        self._lock = threading.RLock()
        self._conn_lock = threading.Lock()
        self._pending: deque[dict[str, Any]] = deque(maxlen=self.MAX_PENDING)
        self._cond = threading.Condition()
        self._ws: Any = None
        self._authed = False
        self._stop = threading.Event()
        self._backoff = self.RECONNECT_MIN
        self._stats: dict[str, int] = {
            "connects": 0,
            "reconnects": 0,
            "messages": 0,
            "dropped": 0,
            "errors": 0,
            "timeouts": 0,
        }

    # --- introspection --------------------------------------------------------

    @property
    def command_timeout(self) -> float:
        return self._command_timeout

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    @property
    def connected(self) -> bool:
        return self._ws is not None and self._authed

    # --- connection lifecycle -------------------------------------------------

    def _ensure_connected(self) -> None:
        """Guarantee a live, authenticated connection (with backoff)."""
        with self._conn_lock:
            if self._stop.is_set():
                raise TechlanApiError("ARM client is shutting down")
            if self._ws is not None and self._authed:
                return
            deadline = time.monotonic() + self.OPEN_TIMEOUT * 3
            attempt = 0
            last_error: Exception | None = None
            while not self._stop.is_set():
                attempt += 1
                try:
                    ws = self._factory(self._url, self.OPEN_TIMEOUT)
                except Exception as exc:  # noqa: BLE001 - normalise transport errors
                    last_error = exc
                    self._stats["errors"] += 1
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(min(self._backoff, self.RECONNECT_MAX))
                    self._backoff = min(self._backoff * 2, self.RECONNECT_MAX)
                    continue

                self._pending.clear()
                self._ws = ws
                self._authed = False
                self._start_reader(ws)
                try:
                    self._send_raw(
                        ws,
                        {"funct": "armId", "id": self._arm_id, "pwd": self._password},
                    )
                    message = self._wait_for(
                        "armId", deadline=time.monotonic() + self.READ_BUDGET
                    )
                    if message.get("ret") is not True:
                        raise TechlanApiError("ServerSkif ARM authentication failed")
                except TechlanApiError as exc:
                    last_error = exc
                    self._teardown_ws(ws)
                    if time.monotonic() >= deadline or self._stop.is_set():
                        break
                    time.sleep(min(self._backoff, self.RECONNECT_MAX))
                    self._backoff = min(self._backoff * 2, self.RECONNECT_MAX)
                    continue

                self._authed = True
                self._stats["connects"] += 1
                if attempt > 1:
                    self._stats["reconnects"] += 1
                self._backoff = self.RECONNECT_MIN
                return

            self._teardown_ws(self._ws)
            raise TechlanApiError(f"ARM connection failed: {last_error}")

    def _start_reader(self, ws: Any) -> None:
        thread = threading.Thread(
            target=self._read_loop,
            args=(ws,),
            name="techlan-ws-reader",
            daemon=True,
        )
        thread.start()

    def _read_loop(self, ws: Any) -> None:
        try:
            ws.settimeout(self.READER_TICK)
        except Exception:  # noqa: BLE001 - fake transports may not support it
            pass
        last = time.monotonic()
        while not self._stop.is_set() and self._ws is ws:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                if self._keepalive > 0 and (time.monotonic() - last) >= self._keepalive:
                    try:
                        ws.ping()
                        last = time.monotonic()
                    except Exception:  # noqa: BLE001 - ping is best-effort
                        break
                continue
            except Exception:  # noqa: BLE001 - socket closed/aborted
                break
            last = time.monotonic()
            messages = decode_messages(raw)
            with self._cond:
                for message in messages:
                    if len(self._pending) == self.MAX_PENDING:
                        self._stats["dropped"] += 1
                    self._pending.append(message)
                if messages:
                    self._stats["messages"] += len(messages)
                    self._cond.notify_all()
        # Reader ended: if this is still the current connection, mark it down so
        # the next request reconnects (guard by identity to ignore stale readers).
        if self._ws is ws:
            self._authed = False
        with self._cond:
            self._cond.notify_all()

    def _teardown_ws(self, ws: Any) -> None:
        if self._ws is ws:
            self._ws = None
            self._authed = False
        if ws is None:
            return
        try:
            ws.close()
        except Exception:  # noqa: BLE001 - close must never mask errors
            pass

    # --- low-level helpers ----------------------------------------------------

    def _send_raw(self, ws: Any, payload: dict[str, Any]) -> None:
        ws.send(json.dumps(payload, ensure_ascii=False))

    def _take_matching(
        self, funct: str, pku: int | None, sh: int | None
    ) -> dict[str, Any] | None:
        for index, message in enumerate(self._pending):
            if message.get("funct") != funct:
                continue
            if pku is not None and int(message.get("pku", -1)) != pku:
                continue
            if sh is not None and int(message.get("sh", -1)) != sh:
                continue
            del self._pending[index]
            return message
        return None

    def _wait_for(
        self,
        funct: str,
        pku: int | None = None,
        sh: int | None = None,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        if deadline is None:
            deadline = time.monotonic() + self.READ_BUDGET
        with self._cond:
            while True:
                message = self._take_matching(funct, pku, sh)
                if message is not None:
                    return message
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._stats["timeouts"] += 1
                    raise TechlanApiError(f"Timeout waiting for {funct}")
                self._cond.wait(timeout=min(remaining, 0.5))

    def _wait_for_pku(self, funct: str, pku: int) -> dict[str, Any]:
        return self._wait_for(funct, pku=pku)

    # --- request/response -----------------------------------------------------

    def request_sync(
        self,
        funct: str,
        *,
        pku: int | None = None,
        sh: int | None = None,
        extra: dict[str, Any] | None = None,
        timeout: float | None = None,
        teardown_on_timeout: bool = True,
    ) -> dict[str, Any]:
        """Send one request and await its answer (caller holds ``self._lock``)."""
        ws = self._ws
        payload: dict[str, Any] = {"funct": funct}
        if pku is not None:
            payload["pku"] = int(pku)
        if extra:
            payload.update(extra)
        try:
            self._send_raw(ws, payload)
        except Exception as exc:  # noqa: BLE001 - normalise transport errors
            self._stats["errors"] += 1
            self._teardown_ws(ws)
            raise TechlanApiError(str(exc)) from exc
        try:
            return self._wait_for(
                funct,
                pku=pku,
                sh=sh,
                deadline=time.monotonic() + (timeout or self.READ_BUDGET),
            )
        except TechlanApiError:
            # A missing answer may simply mean the frame is unsupported
            # (best-effort reads); only drop the connection when asked to.
            if teardown_on_timeout:
                self._teardown_ws(ws)
            raise

    async def async_request(
        self,
        funct: str,
        *,
        pku: int | None = None,
        sh: int | None = None,
        extra: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Serialised single round-trip (keeps the connection alive)."""
        return await asyncio.to_thread(
            self._request_locked, funct, pku, sh, extra, timeout
        )

    def _request_locked(
        self,
        funct: str,
        pku: int | None,
        sh: int | None,
        extra: dict[str, Any] | None,
        timeout: float | None,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_connected()
            return self.request_sync(
                funct, pku=pku, sh=sh, extra=extra, timeout=timeout
            )

    async def async_run(self, func: Callable[..., Any], *args: Any) -> Any:
        """Run a multi-request operation while holding the request lock."""
        return await asyncio.to_thread(self._run_locked, func, *args)

    def _run_locked(self, func: Callable[..., Any], *args: Any) -> Any:
        with self._lock:
            self._ensure_connected()
            return func(*args)

    def send_command_sync(
        self, payload: dict[str, Any], *, authenticate_user: bool = True
    ) -> None:
        """Send a control command (``userId`` + command) on the live session."""
        ws = self._ws
        try:
            if authenticate_user:
                # ServerSkif expects operator auth immediately before the
                # command, on the same session («одним пакетом»).
                self._send_raw(ws, {"funct": "userId", "pwd": self._password})
            self._send_raw(ws, payload)
        except Exception as exc:  # noqa: BLE001 - normalise transport errors
            self._stats["errors"] += 1
            self._teardown_ws(ws)
            raise TechlanApiError(str(exc)) from exc

    async def async_send_command(
        self, payload: dict[str, Any], *, authenticate_user: bool = True
    ) -> None:
        await asyncio.to_thread(self._send_command_locked, payload, authenticate_user)

    def _send_command_locked(
        self, payload: dict[str, Any], authenticate_user: bool
    ) -> None:
        with self._lock:
            self._ensure_connected()
            self.send_command_sync(payload, authenticate_user=authenticate_user)

    # --- shutdown -------------------------------------------------------------

    async def async_shutdown(self) -> None:
        """Close the persistent connection and stop the reader thread."""
        self._stop.set()
        await asyncio.to_thread(self._shutdown_sync)

    def _shutdown_sync(self) -> None:
        ws = self._ws
        self._ws = None
        self._authed = False
        if ws is not None:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass
        with self._cond:
            self._cond.notify_all()


# --- pure extraction helpers (shared, unit-tested) ---------------------------


def extract_temperature(message: dict[str, Any]) -> float | None:
    """Extract a direct temperature only when ServerSkif labels it as °C."""
    value = message.get("temperature")
    if value is None:
        value = message.get("val")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if message.get("temperature") is not None else None
    text = str(value or "")
    if "°c" not in text.lower() and "град" not in text.lower():
        return None
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", text)
    return float(match.group(0).replace(",", ".")) if match else None


def extract_humidity(message: dict[str, Any]) -> float | None:
    """Extract a direct humidity value only when ServerSkif labels it as percent."""
    value = message.get("humidity")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(message.get("val") or "")
    if "%" not in text and "влаж" not in text.lower():
        return None
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", text)
    return float(match.group(0).replace(",", ".")) if match else None
