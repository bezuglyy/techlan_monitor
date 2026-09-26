"""Общие константы интеграций Techlan ARM/ОПС (канонический источник).

Копируется в ``securarm/_shared/shared_const.py`` и
``securarm_sensor/_shared/shared_const.py`` скриптом ``tools/sync-ha-shared.py``.
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
CONF_SELECTED_RELAYS: Final = "selected_relays"
CONF_SELECTED_READERS: Final = "selected_readers"
CONF_RELAY_TIME: Final = "relay_time"
CONF_RELAY_PROGRAM: Final = "relay_program"
CONFIRM: Final = "confirm"

ATTR_PKU: Final = "pku"
ATTR_RELAY: Final = "relay"
ATTR_READER: Final = "reader"

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

# --- Реле (управляемые выходы ServerSkif) -----------------------------------
#
# Реле адресуется парой (pku, rl), где rl = (device << 8) | relay_number.
# Протокол (канон — вендорский клиент arm-skif 2.16.0, WebSocket/script/armSkif/main.js):
#   getListDevices {pku}                  -> [dev, ...]
#   getListRelay   {pku, req: dev}        -> [rl, ...]
#   getRelayDescription {pku, req: [rl]}  -> [str, ...]
#   getRelayState  {pku, req: [rl]}       -> [1|2|3, ...]
#   controlRelay_Inv {pku, rl}            -> переключить реле
#   controlRelay {pku, rl, prog[, mask, delay, time]} -> задать программу
# Команда отправляется только вместе с пакетом userId (см. send_command_sync).

# Коды состояний реле (arrRelayState вендора; 0 = нет данных).
RELAY_STATE_UNKNOWN: Final = 0
RELAY_STATE_ON: Final = 1
RELAY_STATE_OFF: Final = 2
RELAY_STATE_BLINK: Final = 3

# Тексты состояний реле.
RELAY_STATE_NAMES: Final = {
    0: "Нет данных",
    1: "Включено",
    2: "Выключено",
    3: "Мигает",
}

# Коды программ (RL_* в вендоре).
RELAY_PROGRAM_RESET: Final = 0
RELAY_PROGRAM_ON: Final = 1
RELAY_PROGRAM_OFF: Final = 2
RELAY_PROGRAM_ON_TIME: Final = 3
RELAY_PROGRAM_OFF_TIME: Final = 4
RELAY_PROGRAM_BLINK_OFF: Final = 5
RELAY_PROGRAM_BLINK_ON: Final = 6
RELAY_PROGRAM_BLINK_OFF_TIME: Final = 7
RELAY_PROGRAM_BLINK_ON_TIME: Final = 8

# Человекочитаемое имя программы -> код RL_*.
RELAY_PROGRAMS: Final = {
    "reset": RELAY_PROGRAM_RESET,
    "on": RELAY_PROGRAM_ON,
    "off": RELAY_PROGRAM_OFF,
    "on_time": RELAY_PROGRAM_ON_TIME,
    "off_time": RELAY_PROGRAM_OFF_TIME,
    "blink_off": RELAY_PROGRAM_BLINK_OFF,
    "blink_on": RELAY_PROGRAM_BLINK_ON,
    "blink_off_time": RELAY_PROGRAM_BLINK_OFF_TIME,
    "blink_on_time": RELAY_PROGRAM_BLINK_ON_TIME,
}

# Программы, требующие параметр времени (секунды).
RELAY_TIME_PROGRAMS: Final = frozenset(
    {"on_time", "off_time", "blink_off_time", "blink_on_time"}
)

# Одна единица поля ``time`` в протоколе = 0.125 c (вендор: rlTime / 0.125).
RELAY_TIME_UNIT_SECONDS: Final = 0.125

# Программа по умолчанию и время по умолчанию для *_TIME.
DEFAULT_RELAY_PROGRAM: Final = "on"
DEFAULT_RELAY_TIME: Final = 3.0


# --- Считыватели (контроллеры доступа, напр. С2000-2) ------------------------
#
# Считыватель адресуется парой (pku, rd), где rd = (device << 8) | reader_number.
# Протокол (канон — вендорский arm-skif 2.16.0, Application_A.pdf Табл. А.4):
#   getListReader      {pku, req: dev}      -> [rd, ...]
#   getReaderDescription {pku, req: [rd]}   -> [str, ...]
#   getReaderState     {pku, req: [rd]}     -> [битовая маска, ...]
#   controlReader      {pku, rd, prog}      -> программа управления считывателем
#
# Зачем: у контроллеров ДОСТУПА (С2000-2) реле — это «замки», управляемые
# только логикой доступа (в РЭ только программы 3/4 «включить/выключить на
# время»), внешнее управление реле прибором не поддерживается. Правильный путь
# — управлять считывателем: РЭ прямо указывает, что режим «Доступ открыт»
# включается «по команде сетевого контроллера по интерфейсу RS-485».
# Команда отправляется только вместе с пакетом userId (см. async_send_command).

# Биты состояния считывателя (getReaderState).
READER_STATE_EXIT_LOCKED: Final = 1  # бит 0 — запрет выхода (по кнопке)
READER_STATE_ENTRY_LOCKED: Final = 2  # бит 1 — запрет входа
READER_STATE_FREE: Final = 4  # бит 2 — свободный проход

# Коды программ (RD_* в вендоре, Табл. А.4).
READER_PROGRAM_OPEN: Final = 0  # RD_OPEN — предоставление доступа (разово)
READER_PROGRAM_NORMAL: Final = 1  # RD_NORMAL — разрешение доступа (норма)
READER_PROGRAM_UNLOCK_READER: Final = 2  # RD_UNLOCK_RD — разблокировать считыватель
READER_PROGRAM_UNLOCK_BUTTON: Final = 3  # RD_UNLOCK_BTN — разблокировать кнопку «Выход»
READER_PROGRAM_LOCK: Final = 4  # RD_LOCK — запрет доступа
READER_PROGRAM_LOCK_READER: Final = 5  # RD_LOCK_RD — заблокировать считыватель
READER_PROGRAM_LOCK_BUTTON: Final = 6  # RD_LOCK_BTN — заблокировать кнопку «Выход»
READER_PROGRAM_FREE: Final = 7  # RD_UNLOCK — открытие свободного доступа

# Человекочитаемое имя программы -> код RD_*.
READER_PROGRAMS: Final = {
    "open": READER_PROGRAM_OPEN,
    "normal": READER_PROGRAM_NORMAL,
    "unlock_reader": READER_PROGRAM_UNLOCK_READER,
    "unlock_button": READER_PROGRAM_UNLOCK_BUTTON,
    "lock": READER_PROGRAM_LOCK,
    "lock_reader": READER_PROGRAM_LOCK_READER,
    "lock_button": READER_PROGRAM_LOCK_BUTTON,
    "free": READER_PROGRAM_FREE,
}

# Подписи программ (для select/справки).
READER_PROGRAM_NAMES: Final = {
    "open": "Предоставление доступа",
    "normal": "Разрешение доступа",
    "unlock_reader": "Разблокировать считыватель",
    "unlock_button": "Разблокировать кнопку «Выход»",
    "lock": "Запрет доступа",
    "lock_reader": "Заблокировать считыватель",
    "lock_button": "Заблокировать кнопку «Выход»",
    "free": "Открытие свободного доступа",
}

# Программа по умолчанию (моментальное открытие доступа).
DEFAULT_READER_PROGRAM: Final = "open"
