# Techlan Monitor
![Release](https://img.shields.io/github/v/release/bezuglyy/techlan_monitor?label=Release&style=flat-square) ![HACS](https://img.shields.io/badge/HACS-Custom%20Repository-purple?style=flat-square) ![License](https://img.shields.io/github/license/bezuglyy/techlan_monitor?style=flat-square) ![HA](https://img.shields.io/badge/HA-2025.1%2B-2ea44f?style=flat-square)
Кастомная интеграция для [Home Assistant](https://www.home-assistant.io) · версия **1.2.0**.
![icon](custom_components/techlan_monitor/brand/icon.png)
| | |
|---|---|
| Домен | `techlan_monitor` |
| Версия | 1.2.0 |
| Тип | custom integration |
## Описание
Мониторинг серверов и устройств techlan.su.
### Возможности
- Бинарные датчики (движение, контакты и т.п.)
- Кнопки и действия
- Сенсоры и мониторинг состояния
### Изменения 1.2.0
- 🔒 **Агент теперь fail-closed:** без токена запрещены опасные операции (`/api/v1/reboot` → 403) и чтение метрик (503, кроме `/health`). Установщик сам генерирует токен и сохраняет его в настройках.
- 🛑 **Предохранитель перезагрузки:** кнопки `Reboot Server` / `Reboot HA Core` / `Restart HAOS` требуют включённого switch-предохранителя (авто-сброс 60 с); добавлены сервисы с `confirm: true`.
- Новый сенсор **Agent Version**, опции `use_https`/`verify_tls`.
- **Диагностика**, **Repairs**, enum-классы, миграция схемы; **фирменный брендинг** (светлая/тёмная тема).
### Установка
1. Скопируйте папку `custom_components/techlan_monitor/` в каталог `custom_components/` конфигурации Home Assistant.
2. Перезапустите Home Assistant.
3. Настройки → Устройства и службы → Добавить интеграцию → **Techlan Monitor**.
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
3. Settings → Devices & Services → Add Integration → **Techlan Monitor**.
> HACS: add `https://github.com/bezuglyy/techlan_monitor` as a Custom repository (category Integration).
---
**Автор / Author:**
![Bezuglyj E.N.](logo-bezuglyj.png)
## License / Лицензия
MIT
