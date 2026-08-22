# Techlan Monitor

Кастомная интеграция для [Home Assistant](https://www.home-assistant.io) · версия **1.0.0**.

![icon](custom_components/techlan_monitor/brand/icon.png)

| | |
|---|---|
| Домен | `techlan_monitor` |
| Версия | 1.0.0 |
| Тип | custom integration |

## Описание

Мониторинг серверов и устройств techlan.su.

## Возможности

- Бинарные датчики (движение, контакты и т.п.)
- Кнопки и действия
- Сенсоры и мониторинг состояния

## Установка

1. Скопируйте папку `custom_components/{domain}/` в каталог `custom_components/` конфигурации Home Assistant.
2. Перезапустите Home Assistant.
3. Настройки → Устройства и службы → Добавить интеграцию → **{mname}**.

> Установка через HACS: добавьте репозиторий `https://github.com/bezuglyy/{repo}` как Custom repository (категория Integration).

## Лицензия

MIT
