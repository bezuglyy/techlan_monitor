"""Общие константы интеграций Techlan ARM/ОПС (канонический источник).

Копируется в ``techlan_ops/_shared/shared_const.py`` и
``techlan_sensor/_shared/shared_const.py`` скриптом ``tools/sync-ha-shared.py``.
Не редактировать копии вручную.
"""

from __future__ import annotations

from typing import Final

# --- Ключи конфигурации config entry / options ---
CONF_BASE_URL: Final = "base_url"
CONF_ARM_ID: Final = "arm_id"
CONF_PASSWORD: Final = "password"
CONF_WS_PATH: Final = "ws_path"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_SELECTED_LOOPS: Final = "selected_loops"
CONF_TEMPERATURE_LOOPS: Final = "temperature_loops"
CONF_TEMPERATURE_SCALE: Final = "temperature_scale"
CONF_TEMPERATURE_OFFSET: Final = "temperature_offset"
CONF_HUMIDITY_LOOPS: Final = "humidity_loops"
CONF_HUMIDITY_SCALE: Final = "humidity_scale"
CONF_HUMIDITY_OFFSET: Final = "humidity_offset"
CONF_TEMPERATURE_ALARM_LOW: Final = "temperature_alarm_low"
CONF_TEMPERATURE_ALARM_HIGH: Final = "temperature_alarm_high"
CONF_COMMAND_TIMEOUT: Final = "command_timeout"
CONFIRM: Final = "confirm"

ATTR_PKU: Final = "pku"

# --- Значения по умолчанию ---
DEFAULT_BASE_URL: Final = "http://192.168.100.111:18081"
DEFAULT_ARM_ID: Final = "techlan"
DEFAULT_WS_PATH: Final = "/skif-ws"
DEFAULT_SCAN_INTERVAL: Final = 30
DEFAULT_TEMPERATURE_SCALE: Final = 1.0
DEFAULT_TEMPERATURE_OFFSET: Final = 0.0
DEFAULT_HUMIDITY_SCALE: Final = 1.0
DEFAULT_HUMIDITY_OFFSET: Final = 0.0
# Широкие пороги: тревога по вычисленной температуре включается, когда
# пользователь сужает диапазон через number-сущности.
DEFAULT_TEMPERATURE_ALARM_LOW: Final = -50.0
DEFAULT_TEMPERATURE_ALARM_HIGH: Final = 100.0
# Сколько секунд ждать подтверждение команды взятия/снятия по состоянию.
DEFAULT_COMMAND_TIMEOUT: Final = 30

# --- Состояния разделов ---

# Коды, при которых раздел считается взятым (24) или в переходе (23).
ARMED_CODES: Final = frozenset({23, 24})
# Коды, при которых раздел считается снятым.
DISARMED_CODES: Final = frozenset({109, 117, 119})
# Целевые коды подтверждения команды (без учёта переходных 23/117).
ARM_CONFIRM_CODES: Final = frozenset({24})
DISARM_CONFIRM_CODES: Final = frozenset({109})

# ServerSkif event/state codes that should be surfaced as active alarms.
# The ARM web client treats these as alarm or operationally important states.
ALARM_STATE_CODES: Final = frozenset(
    {
        3,
        18,
        27,
        33,
        37,
        40,
        44,
        45,
        58,
        79,
        118,
        137,
        138,
        139,
        141,
        143,
        144,
        145,
        146,
        147,
        149,
        150,
        151,
        157,
        159,
        160,
        161,
        162,
        214,
        216,
        220,
        221,
        250,
        252,
    }
)

# Код «температура ниже заданного значения» (климатическая тревога прибора).
TEMPERATURE_ALARM_CODE: Final = 206

STATE_NAMES: Final = {
    1: "Норма сети 220 В",
    7: "Исполнительное устройство включено вручную",
    8: "Исполнительное устройство выключено вручную",
    9: "Устройство дистанционного пуска активировано",
    10: "Устройство дистанционного пуска в норме",
    23: "Идёт взятие",
    24: "Взят",
    35: "Технологический ШС в норме",
    36: "Технологический ШС нарушен",
    47: "ДПЛС в норме",
    80: "Датчик затопления в норме",
    83: "Термометр в норме",
    91: "Канал связи в норме",
    109: "Снят",
    117: "Снят и в норме",
    119: "Снят и нарушен",
    123: "Выход (реле) в норме",
    127: "Связь с реле восстановлена",
    136: "Напряжение питания в норме",
    152: "Корпус закрыт",
    158: "Внутренняя зона в норме",
    188: "Связь с ШС в норме",
    191: "ДПЛС1 в норме",
    195: "Токопотребление в норме",
    197: "Зарядное устройство в норме",
    199: "Источник питания в норме",
    201: "ДПЛС2 в норме",
    206: "Температура ниже заданного значения",
    218: "RS-485 в норме",
}
