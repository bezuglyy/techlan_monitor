# techlan-agent — артефакт мониторинга

Автономный HTTP-агент для удалённых серверов (Linux/Windows), который
опрашивает интеграция `techlan_monitor`.

| Параметр | Значение |
|---|---|
| Версия | **1.2.0** (синхронизировать с `AGENT_VERSION` в `agent.py` и `installer.py`) |
| Порт | `AGENT_PORT` (по умолчанию 9100) |
| Токен | `AGENT_TOKEN` (env) → `AGENT_TOKEN_FILE` → `/opt/techlan-agent/agent.token` (Linux) / `C:\ProgramData\TechlanAgent\agent.token` (Windows) |
| Эндпоинты | `GET /api/v1/health`, `GET /api/v1/metrics`, `GET /api/v1/services`, `GET /api/v1/docker`, `POST /api/v1/reboot` |

## Безопасность (fail-closed)

- Команды ограничены фиксированным списком эндпоинтов; произвольное
  выполнение команд недоступно.
- `POST /api/v1/reboot` — единственное изменяющее действие. **Без
  настроенного `AGENT_TOKEN` оно всегда запрещено (403)**, даже если
  включён небезопасный режим чтения.
- Если токен не задан, читающие эндпоинты (`/metrics`, `/services`, `/docker`)
  по умолчанию тоже **запрещены** (`503`). Только явное
  `AGENT_ALLOW_INSECURE=1` разрешает их без токена (для совместимости со
  старыми агентами); в этом режиме reboot всё равно недоступен.
- `/api/v1/health` открыт всегда: отдаёт только версию/идентичность
  (`version`, `hostname`, `platform`, `auth`, `secure`) и нужен для
  обнаружения версии при миграции.
- Токен сравнивается постоянным по времени `secrets.compare_digest`.
- Установщик из HA (`installer.py`) **генерирует случайный токен**
  (`secrets.token_urlsafe(32)`), пишет его в файл `agent.token`
  (Linux: `chmod 600`, владелец `nobody`) и передаёт службе через
  `AGENT_TOKEN_FILE`; токен возвращается интеграции и сохраняется в options.
- Рекомендуется ограничить порт агента на межсетевом экране; при выносе за
  пределы доверенной сети — ставить агента за TLS-прокси (см. `use_https`/
  `verify_tls` в настройках сервера).

## Версия

`GET /api/v1/health` и `GET /api/v1/metrics` возвращают `version` /
`agent_version`; в HA есть диагностический сенсор «Agent Version» по каждому
серверу. Для обновления агента — переустановить его из Options
(«Установить агента»): новый токен выдаётся, если у сервера его ещё нет.

## Установка

Автоматически: `techlan_monitor` → Настройки → Options → «Установить агента»
(SSH, требуется пользователь/пароль). Скрипт установки — `installer.py`
(Linux: `/opt/techlan-agent/agent.py` + `agent.token` + systemd; Windows:
`C:\ProgramData\TechlanAgent` + Scheduled Task).
