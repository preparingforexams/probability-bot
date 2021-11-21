import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from enum import Enum, auto
from threading import Thread, Lock
from typing import Optional, List, Tuple, Dict

import requests
import sentry_sdk
from requests.exceptions import HTTPError

_API_KEY = os.getenv("TELEGRAM_API_KEY")
_DUMP_LOCATION = os.getenv("DATA_PATH")

_LOG = logging.getLogger("bot")


class Slot(Enum):
    BAR = auto()
    GRAPE = auto()
    LEMON = auto()
    SEVEN = auto()

    def __str__(self):
        return self.name

    @classmethod
    def by_name(cls, name: str):
        for slot in cls:
            if slot.name == name:
                return slot

        raise ValueError(f"Unknown slot: {name}")


_SLOT_MACHINE_VALUES: Dict[int, Tuple[Slot, Slot, Slot]] = {
    1: (Slot.BAR, Slot.BAR, Slot.BAR),
    2: (Slot.GRAPE, Slot.BAR, Slot.BAR),
    3: (Slot.LEMON, Slot.BAR, Slot.BAR),
    4: (Slot.SEVEN, Slot.BAR, Slot.BAR),
    5: (Slot.BAR, Slot.GRAPE, Slot.BAR),
    6: (Slot.GRAPE, Slot.GRAPE, Slot.BAR),
    7: (Slot.LEMON, Slot.GRAPE, Slot.BAR),
    8: (Slot.SEVEN, Slot.GRAPE, Slot.BAR),
    9: (Slot.BAR, Slot.LEMON, Slot.BAR),
    10: (Slot.GRAPE, Slot.LEMON, Slot.BAR),
    11: (Slot.LEMON, Slot.LEMON, Slot.BAR),
    12: (Slot.SEVEN, Slot.LEMON, Slot.BAR),
    13: (Slot.BAR, Slot.SEVEN, Slot.BAR),
    14: (Slot.GRAPE, Slot.SEVEN, Slot.BAR),
    15: (Slot.LEMON, Slot.SEVEN, Slot.BAR),
    16: (Slot.SEVEN, Slot.SEVEN, Slot.BAR),
    17: (Slot.BAR, Slot.BAR, Slot.GRAPE),
    18: (Slot.GRAPE, Slot.BAR, Slot.GRAPE),
    19: (Slot.LEMON, Slot.BAR, Slot.GRAPE),
    20: (Slot.SEVEN, Slot.BAR, Slot.GRAPE),
    21: (Slot.BAR, Slot.GRAPE, Slot.GRAPE),
    22: (Slot.GRAPE, Slot.GRAPE, Slot.GRAPE),
    23: (Slot.LEMON, Slot.GRAPE, Slot.GRAPE),
    24: (Slot.SEVEN, Slot.GRAPE, Slot.GRAPE),
    25: (Slot.BAR, Slot.LEMON, Slot.GRAPE),
    26: (Slot.GRAPE, Slot.LEMON, Slot.GRAPE),
    27: (Slot.LEMON, Slot.LEMON, Slot.GRAPE),
    28: (Slot.SEVEN, Slot.LEMON, Slot.GRAPE),
    29: (Slot.BAR, Slot.SEVEN, Slot.GRAPE),
    30: (Slot.GRAPE, Slot.SEVEN, Slot.GRAPE),
    31: (Slot.LEMON, Slot.SEVEN, Slot.GRAPE),
    32: (Slot.SEVEN, Slot.SEVEN, Slot.GRAPE),
    33: (Slot.BAR, Slot.BAR, Slot.LEMON),
    34: (Slot.GRAPE, Slot.BAR, Slot.LEMON),
    35: (Slot.LEMON, Slot.BAR, Slot.LEMON),
    36: (Slot.SEVEN, Slot.BAR, Slot.LEMON),
    37: (Slot.BAR, Slot.GRAPE, Slot.LEMON),
    38: (Slot.GRAPE, Slot.GRAPE, Slot.LEMON),
    39: (Slot.LEMON, Slot.GRAPE, Slot.LEMON),
    40: (Slot.SEVEN, Slot.GRAPE, Slot.LEMON),
    41: (Slot.BAR, Slot.LEMON, Slot.LEMON),
    42: (Slot.GRAPE, Slot.LEMON, Slot.LEMON),
    43: (Slot.LEMON, Slot.LEMON, Slot.LEMON),
    44: (Slot.SEVEN, Slot.LEMON, Slot.LEMON),
    45: (Slot.BAR, Slot.SEVEN, Slot.LEMON),
    46: (Slot.GRAPE, Slot.SEVEN, Slot.LEMON),
    47: (Slot.LEMON, Slot.SEVEN, Slot.LEMON),
    48: (Slot.SEVEN, Slot.SEVEN, Slot.LEMON),
    49: (Slot.BAR, Slot.BAR, Slot.SEVEN),
    50: (Slot.GRAPE, Slot.BAR, Slot.SEVEN),
    51: (Slot.LEMON, Slot.BAR, Slot.SEVEN),
    52: (Slot.SEVEN, Slot.BAR, Slot.SEVEN),
    53: (Slot.BAR, Slot.GRAPE, Slot.SEVEN),
    54: (Slot.GRAPE, Slot.GRAPE, Slot.SEVEN),
    55: (Slot.LEMON, Slot.GRAPE, Slot.SEVEN),
    56: (Slot.SEVEN, Slot.GRAPE, Slot.SEVEN),
    57: (Slot.BAR, Slot.LEMON, Slot.SEVEN),
    58: (Slot.GRAPE, Slot.LEMON, Slot.SEVEN),
    59: (Slot.LEMON, Slot.LEMON, Slot.SEVEN),
    60: (Slot.SEVEN, Slot.LEMON, Slot.SEVEN),
    61: (Slot.BAR, Slot.SEVEN, Slot.SEVEN),
    62: (Slot.GRAPE, Slot.SEVEN, Slot.SEVEN),
    63: (Slot.LEMON, Slot.SEVEN, Slot.SEVEN),
    64: (Slot.SEVEN, Slot.SEVEN, Slot.SEVEN),
}


def _build_url(method: str) -> str:
    return f"https://api.telegram.org/bot{_API_KEY}/{method}"


def _get_actual_body(response: requests.Response):
    response.raise_for_status()
    body = response.json()
    if body.get("ok"):
        return body["result"]
    raise ValueError(f"Body was not ok! {body}")


def _send_message(chat_id: int, text: str, reply_to_message_id: Optional[int]) -> dict:
    return _get_actual_body(requests.post(
        _build_url("sendMessage"),
        json={
            "text": text,
            "chat_id": chat_id,
            "reply_to_message_id": reply_to_message_id,
        },
        timeout=10,
    ))


def _send_dice(chat_id: int, emoji: str = "🎰") -> dict:
    return _get_actual_body(requests.post(
        _build_url("sendDice"),
        json={
            "chat_id": chat_id,
            "emoji": emoji,
        },
        timeout=10,
    ))


@dataclass
class History:
    _lock: Lock
    test_count: int
    _occurrences_by_value: List[int]
    occurrences_by_slot: Dict[Slot, int]

    def __init__(self):
        self._lock = Lock()
        self.test_count = 0
        self._occurrences_by_value = [0 for _ in range(64)]
        self.occurrences_by_slot = {slot: 0 for slot in Slot}

    def add_test(self, value: int):
        with self._lock:
            self.test_count += 1
            self._occurrences_by_value[value - 1] += 1
            slots = _SLOT_MACHINE_VALUES[value]
            for slot in slots:
                self.occurrences_by_slot[slot] += 1

    def get_occurrence_by_value(self, value: int) -> int:
        return self._occurrences_by_value[value - 1]

    def get_top_values(self, n: int = 10) -> List[int]:
        sorted_values = sorted(range(1, 65), key=self.get_occurrence_by_value, reverse=True)
        return sorted_values[:n]

    def load(self, serialized: str):
        values = json.loads(serialized)
        self.test_count = values["count"]
        self._occurrences_by_value = values["occurrences_by_value"]
        self.occurrences_by_slot = {
            Slot.by_name(slot): value
            for slot, value in values["occurrences_by_slot"].items()
        }

    def serialize(self) -> str:
        with self._lock:
            values = dict(
                count=self.test_count,
                occurrences_by_value=self._occurrences_by_value,
                occurrences_by_slot={
                    str(slot): value
                    for slot, value in self.occurrences_by_slot.items()
                }
            )
            return json.dumps(values)


def _get_dump_file_path() -> str:
    folder = _DUMP_LOCATION or "data"
    if not os.path.exists(folder):
        os.mkdir(folder)
    return os.path.join(folder, "history.json")


def _try_load_history(history: History):
    file_path = _get_dump_file_path()
    if not os.path.isfile(file_path):
        _LOG.info("No history file found")
        return

    with open(file_path) as f:
        content = f.read()
        history.load(content)


def _dump_history(history: History):
    file_path = _get_dump_file_path()
    with open(file_path, 'w') as f:
        content = history.serialize()
        f.write(content)


def _build_summary(history: History) -> str:
    text = f"Handled {history.test_count} slot machine results.\n"

    for slot in Slot:
        text += f"\n{slot}: {history.occurrences_by_slot[slot]}"

    text += "\n" * 2

    text += "Top results:"
    for value in history.get_top_values():
        slots = _SLOT_MACHINE_VALUES[value]
        description = ", ".join(str(slot) for slot in slots)
        occurrence = history.get_occurrence_by_value(value)
        text += f"\n- {occurrence}x {description}"

    return text


def _handle_message(history: History, message: dict):
    dice: Optional[dict] = message.get("dice")
    text: Optional[str] = message.get("text")
    if dice:
        if dice["emoji"] != "🎰":
            _LOG.debug("Skipping non-slot-machine message")
            return

        history.add_test(dice["value"])
        # Is this a database?
        _dump_history(history)
    elif text:
        chat_id = message["chat"]["id"]
        if text.startswith("/summary"):
            summary = _build_summary(history)
            _send_message(chat_id, summary, message["message_id"])
        elif text.startswith("/stopspam"):
            _stop_spam()
        elif text.startswith("/spam"):
            _start_spam(chat_id, history)
            _send_message(
                chat_id,
                "Stop spamming with /stopspam",
                message["message_id"],
            )
    else:
        _LOG.debug("Skipping non-dice and non-text message")


def _handle_update(history: History, update: dict):
    message = update.get("message")

    if not message:
        _LOG.debug("Skipping non-message update")
        return

    _handle_message(history, message)


def _request_updates(last_update_id: Optional[int]) -> List[dict]:
    body: Optional[dict] = None
    if last_update_id:
        body = {
            "offset": last_update_id + 1,
            "timeout": 10,
        }
    return _get_actual_body(requests.post(
        _build_url("getUpdates"),
        json=body,
        timeout=15,
    ))


def _handle_updates():
    last_update_id: Optional[int] = None
    history = History()
    _try_load_history(history)
    while True:
        updates = _request_updates(last_update_id)
        try:
            for update in updates:
                _handle_update(history, update)
                last_update_id = update["update_id"]
        except Exception as e:
            _LOG.error("Could not handle update", exc_info=e)


is_spamming: bool = False
spammer: Optional[Thread] = None


def _spam(chat_id: int, history: Optional[History] = None):
    while is_spamming:
        try:
            message = _send_dice(chat_id)
        except HTTPError:
            _LOG.warning("Waiting because of rate limit")
            time.sleep(60)
            continue
        if history is not None:
            _handle_message(history, message)
        time.sleep(1)


def _start_spam(chat_id: int, history: History):
    global is_spamming, spammer
    if is_spamming or spammer is not None:
        return

    is_spamming = True
    spammer = Thread(name="spam", target=lambda: _spam(chat_id, history), daemon=True)
    spammer.start()


def _stop_spam():
    global is_spamming, spammer
    if is_spamming and spammer is not None:
        is_spamming = False
        time.sleep(0.2)
        spammer = None


def _setup_logging():
    logging.basicConfig()
    _LOG.level = logging.DEBUG


def _setup_sentry():
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        _LOG.warning("Sentry DSN not found")
        return

    sentry_sdk.init(
        dsn,

        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0
    )


def _log_arg_error():
    _LOG.error("Missing subcommand name (one of [handle-updates, spam])")


def main():
    _setup_logging()
    _setup_sentry()

    if not _API_KEY:
        _LOG.error("Missing API key")
        sys.exit(1)

    if not _DUMP_LOCATION:
        _LOG.warning("DATA_PATH is not set!")

    _handle_updates()


if __name__ == '__main__':
    main()
