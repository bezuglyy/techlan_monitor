# SecurARM Monitor
![Release](https://img.shields.io/github/v/release/bezuglyy/techlan_monitor?label=Release&style=flat-square) ![HACS](https://img.shields.io/badge/HACS-Custom%20Repository-purple?style=flat-square) ![License](https://img.shields.io/github/license/bezuglyy/techlan_monitor?style=flat-square) ![HA](https://img.shields.io/badge/HA-2025.1%2B-2ea44f?style=flat-square)
Кастомная интеграция для [Home Assistant](https://www.home-assistant.io) · версия **1.2.5**.
![icon](custom_components/techlan_monitor/brand/icon.png)
| | |
|---|---|
| Домен | `techlan_monitor` |
| Версия | 1.2.5 |
| Тип | custom integration |
## Описание
Мониторинг серверов и устройств techlan.su.
### Возможности
- Бинарные датчики (движение, контакты и т.п.)
- Кнопки и действия
- Сенсоры и мониторинг состояния
### Изменения 1.2.5
- 🖼️ **Фирменный знак SecurARM** (щит с шестернёй и замком, логотип автора) в `brand/` — icon/logo + тёмные варианты и `@2x`.
### Изменения 1.2.4
- 🏷️ **Переименование в SecurARM:** отображаемое имя интеграции — **SecurARM Monitor**, логотипы/иконки обновлены (`brand/`, вордмарк **SECURARM**).
- ⚠️ Домен `techlan_monitor`, `unique_id` и все `entity_id` **не изменены**; имя агента на хостах (`TechlanAgent`) также не менялось.
### Изменения 1.2.0
- 🔒 **Агент теперь fail-closed:** без токена запрещены опасные операции (`/api/v1/reboot` → 403) и чтение метрик (503, кроме `/health`). Установщик сам генерирует токен и сохраняет его в настройках.
- 🛑 **Предохранитель перезагрузки:** кнопки `Reboot Server` / `Reboot HA Core` / `Restart HAOS` требуют включённого switch-предохранителя (авто-сброс 60 с); добавлены сервисы с `confirm: true`.
- Новый сенсор **Agent Version**, опции `use_https`/`verify_tls`.
- **Диагностика**, **Repairs**, enum-классы, миграция схемы; **фирменный брендинг** (светлая/тёмная тема).
### Изменения 1.2.1
- 🐞 **Исправлен разбор Supervisor API (HA 2026.x):** раньше код читал несуществующие поля (`cpu_percent`, `memory.percent`, `disk.percent`) → CPU/память/диск/uptime показывали `0`. Теперь: диск — из `disk_used/disk_total`, uptime — из `boot_timestamp`, а сенсоры переименованы по реальным полям: **Core Version**, **Supervisor Version**, **Agent Version**, **Kernel**, **OS**, **Hostname**.
- ❌ Удалены недоступные сенсоры HAOS (CPU/память/температура/частота/load) — Supervisor API их не отдаёт (раньше показывали ложный `0`).

### Изменения 1.2.2
- 🔒 **Исправлен установщик агента:** раньше по SSH ставился **урезанный inline-скрипт-заглушка** вместо полноценного `agent/agent.py` → агент не проверял токен (метрики и `POST /api/v1/reboot` были открыты). Теперь установщик разворачивает **реальный агент** из пакета (`agent/agent.py`, версия агента `1.2.1`).
- ✅ Проверено: без токена `/api/v1/metrics` → **401**, `POST /api/v1/reboot` → **401**; с Bearer-токеном метрики отдаются (200).

### Изменения 1.2.3
- ⚡ **Убраны блокирующие вызовы в event loop** (HA предупреждал `Detected blocking call ... inside the event loop`): `import asyncssh` и чтение `agent/agent.py` перенесены на этап загрузки модуля (HA импортирует интеграции в executor), `from .installer import install_agent` — на уровень модуля `config_flow`.

### Установка
1. Скопируйте папку `custom_components/techlan_monitor/` в каталог `custom_components/` конфигурации Home Assistant.
2. Перезапустите Home Assistant.
3. Настройки → Устройства и службы → Добавить интеграцию → **SecurARM Monitor**.
> Установка через HACS: добавьте репозиторий `https://github.com/bezuglyy/techlan_monitor` как Custom repository (категория Integration).
---
## Description
Monitoring of techlan.su servers and devices.
### Features
- Binary sensors (motion, contacts, etc.)
- Buttons and actions
- Sensors and state monitoring
### Installation
1. Copy the `custom_components/techlan_monitor/` folder into the `custom_components/` directory of your Home Assistant configuration.
2. Restart Home Assistant.
3. Settings → Devices & Services → Add Integration → **SecurARM Monitor**.
> HACS: add `https://github.com/bezuglyy/techlan_monitor` as a Custom repository (category Integration).
---
**Автор / Author:**
![Bezuglyj E.N.](logo-bezuglyj.png)
## License / Лицензия
MIT
