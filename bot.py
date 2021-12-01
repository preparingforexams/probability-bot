import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from enum import Enum, auto
from tempfile import TemporaryFile
from threading import Thread, Lock
from typing import Optional, List, Tuple, Dict, IO, Callable

import matplotlib.pyplot as plot
import requests
import sentry_sdk
from requests.exceptions import HTTPError

_ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")
_API_KEY = os.getenv("TELEGRAM_API_KEY")
_DUMP_LOCATION = os.getenv("DATA_PATH")
_IS_GOLDEN_FIVE_MODE = bool(os.getenv("TRY_GOLDEN_FIVE", "false"))
_SLEEP_TIME = float(os.getenv("SLEEP_TIME", "5"))

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


def _send_message(chat_id: int, text: str, reply_to_message_id: Optional[int] = None) -> dict:
    return _get_actual_body(requests.post(
        _build_url("sendMessage"),
        json={
            "text": text,
            "chat_id": chat_id,
            "reply_to_message_id": reply_to_message_id,
        },
        timeout=10,
    ))


def _send_dice(
    chat_id: int,
    emoji: str = "🎰",
    reply_to_message_id: Optional[int] = None,
) -> dict:
    return _get_actual_body(requests.post(
        _build_url("sendDice"),
        json={
            "chat_id": chat_id,
            "emoji": emoji,
            "reply_to_message_id": reply_to_message_id,
        },
        timeout=10,
    ))


def _send_image(
    chat_id: int,
    image_file: IO[bytes],
    caption: str,
    reply_to_message_id: Optional[int],
) -> dict:
    return _get_actual_body(requests.post(
        _build_url("sendPhoto"),
        files={
            "photo": image_file,
        },
        data={
            "caption": caption,
            "chat_id": chat_id,
            "reply_to_message_id": reply_to_message_id,
        },
        timeout=10,
    ))


def _send_existing_image(
    chat_id: int,
    file_id: str,
    reply_to_message_id: Optional[int],
) -> dict:
    return _get_actual_body(requests.post(
        _build_url("sendPhoto"),
        json={
            "chat_id": chat_id,
            "reply_to_message_id": reply_to_message_id,
            "photo": file_id,
        },
        timeout=10,
    ))


def _send_lemon_meme(message: dict):
    chat_id = message['chat']['id']
    message_id = message['message_id']
    file_id = "AgACAgIAAxkBAAOaYaevigmUAzZZ_K5CLEL2j4Gs2FkAAhe1MRsINDlJ0YwxQwvAN1wBAAMCAAN4AAMiBA"
    _send_existing_image(chat_id, file_id, reply_to_message_id=message_id)


@dataclass
class History:
    _lock: Lock
    test_count: int
    self_test_count: int
    occurrences_by_value: List[int]
    occurrences_by_slot: Dict[Slot, int]

    def __init__(self):
        self._lock = Lock()
        self.test_count = 0
        self.self_test_count = 0
        self.occurrences_by_value = [0 for _ in range(64)]
        self.occurrences_by_slot = {slot: 0 for slot in Slot}

    def add_test(self, value: int) -> Tuple[Slot, Slot, Slot]:
        with self._lock:
            self.test_count += 1
            self.occurrences_by_value[value - 1] += 1
            slots = _SLOT_MACHINE_VALUES[value]
            for slot in slots:
                self.occurrences_by_slot[slot] += 1
            return slots

    def get_occurrence_by_value(self, value: int) -> int:
        return self.occurrences_by_value[value - 1]

    def get_extreme_values(self, top: bool, n: int = 5) -> List[int]:
        sorted_values = sorted(range(1, 65), key=self.get_occurrence_by_value, reverse=top)
        return sorted_values[:n]

    def inc_self_tests(self):
        with self._lock:
            self.self_test_count += 1

    def load(self, serialized: str):
        values = json.loads(serialized)
        self.test_count = values["count"]
        self.self_test_count = values.get("self_test_count", 0)
        self.occurrences_by_value = values["occurrences_by_value"]
        self.occurrences_by_slot = {
            Slot.by_name(slot): value
            for slot, value in values["occurrences_by_slot"].items()
        }

    def serialize(self) -> str:
        with self._lock:
            values = dict(
                count=self.test_count,
                self_test_count=self.self_test_count,
                occurrences_by_value=self.occurrences_by_value,
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
    _LOG.info("Trying to load history...")
    file_path = _get_dump_file_path()
    if not os.path.isfile(file_path):
        _LOG.info("No history file found")
        return

    with open(file_path) as f:
        content = f.read()
        history.load(content)

    _LOG.info("Successfully loaded history")


def _dump_history(history: History):
    file_path = _get_dump_file_path()
    with open(file_path, 'w') as f:
        content = history.serialize()
        f.write(content)


def _create_plot(history: History, file: IO):
    fig, ax = plot.subplots()

    ax.hist(
        list(range(64)),
        weights=[history.occurrences_by_value],
        bins=64,
        linewidth=0.3,
        edgecolor="white",
    )

    plot.savefig(
        fname=file,
        format="png",
        bbox_inches="tight",
    )


def _build_summary(history: History) -> str:
    text = f"Handled {history.test_count} slot machine results,"
    text += f" more than {history.self_test_count} of which I triggered with my own two hands!"

    text += "\n"

    for slot in Slot:
        text += f"\n{slot}: {history.occurrences_by_slot[slot]}"

    text += "\n" * 2

    text += "Most common results:"
    for value in history.get_extreme_values(top=True):
        slots = _SLOT_MACHINE_VALUES[value]
        description = ", ".join(str(slot) for slot in slots)
        occurrence = history.get_occurrence_by_value(value)
        text += f"\n- {occurrence}x {description}"

    text += "\n" * 2

    text += "Least common results:"
    for value in history.get_extreme_values(top=False):
        slots = _SLOT_MACHINE_VALUES[value]
        description = ", ".join(str(slot) for slot in slots)
        occurrence = history.get_occurrence_by_value(value)
        text += f"\n- {occurrence}x {description}"

    return text


def _handle_message(history: History, message: dict) -> Optional[Tuple[Slot, Slot, Slot]]:
    dice: Optional[dict] = message.get("dice")
    text: Optional[str] = message.get("text")
    if dice:
        if dice["emoji"] != "🎰":
            _LOG.debug("Skipping non-slot-machine message")
            return

        result = history.add_test(dice["value"])
        # Is this a database?
        _dump_history(history)

        if result == (Slot.LEMON,) * 3:
            try:
                _send_lemon_meme(message)
            except Exception as e:
                _LOG.error("Could not send lemon meme", exc_info=e)

        return result
    elif text:
        chat_id = message["chat"]["id"]
        message_id = message["message_id"]
        if text.startswith("/summary"):
            with TemporaryFile("w+b") as f:
                summary = _build_summary(history)
                _create_plot(history, f)
                f.seek(0)
                _send_image(
                    chat_id,
                    image_file=f,
                    caption=summary,
                    reply_to_message_id=message_id,
                )
        elif text.startswith("/stopspam"):
            user_id: int = message["from"]["id"]
            if str(user_id) != _ADMIN_USER_ID:
                _LOG.info("Non-admin user tried to stop spam")
                _send_message(chat_id, "no u", message_id)
                return
            _stop_spam()
        elif text.startswith("/spam"):
            user_id: int = message["from"]["id"]
            if str(user_id) != _ADMIN_USER_ID:
                _LOG.info("Non-admin user tried to start spam")
                _send_message(chat_id, "nah.", message_id)
                return
            _start_spam(chat_id, history)
    else:
        _LOG.debug("Skipping non-dice and non-text message: %s", message)


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


def _try_send_dice(send_dice: Callable[[], dict]) -> Optional[dict]:
    while is_spamming:
        try:
            return send_dice()
        except HTTPError:
            _LOG.warning("Waiting because of rate limit")
            time.sleep(60)
    return None


class GoldStage(Enum):
    bowling = auto()
    dart = auto()
    football = auto()
    basketball = auto()
    won = auto()


@dataclass
class GoldResult:
    stage: GoldStage
    last_message_id: Optional[int]

    def __init__(self, stage: GoldStage, message: Optional[dict]):
        self.stage = stage
        self.last_message_id = message["message_id"] if message else None
        if stage in [GoldStage.football, GoldStage.basketball] and message:
            _LOG.warning("Failed %s with value %d", stage, message["dice"]["value"])


def _try_for_gold(chat_id: int, message_id: int) -> GoldResult:
    bowling = _try_send_dice(lambda: _send_dice(
        chat_id,
        emoji="🎳",
        reply_to_message_id=message_id,
    ))
    if bowling is None or bowling["dice"]["value"] != 6:
        return GoldResult(GoldStage.bowling, bowling)

    time.sleep(_SLEEP_TIME)

    dart = _try_send_dice(lambda: _send_dice(
        chat_id,
        emoji="🎯",
        reply_to_message_id=message_id,
    ))
    if dart is None or dart["dice"]["value"] != 6:
        return GoldResult(GoldStage.dart, dart)

    time.sleep(_SLEEP_TIME)

    football = _try_send_dice(lambda: _send_dice(
        chat_id,
        emoji="⚽",
        reply_to_message_id=message_id,
    ))
    if football is None or football["dice"]["value"] not in [3, 4, 5]:
        return GoldResult(GoldStage.football, football)

    time.sleep(_SLEEP_TIME)

    basketball = _try_send_dice(lambda: _send_dice(
        chat_id,
        emoji="🏀",
        reply_to_message_id=message_id,
    ))
    if basketball is None or basketball["dice"]["value"] not in [4, 5]:
        return GoldResult(GoldStage.basketball, basketball)

    return GoldResult(GoldStage.won, basketball)


def _spam(chat_id: int, history: History):
    while is_spamming:
        message = _try_send_dice(lambda: _send_dice(chat_id))
        if message is None:
            return
        history.inc_self_tests()
        _handle_message(history, message)
        # 1 bar, 22,43 fruits, 64 seven
        if _IS_GOLDEN_FIVE_MODE and message["dice"]["value"] in [64]:
            time.sleep(_SLEEP_TIME)
            gold_result = _try_for_gold(chat_id, message["message_id"])
            time.sleep(_SLEEP_TIME)
            if gold_result.stage == GoldStage.won:
                value = message["dice"]["value"]
                hashtags = []
                if value == 64:
                    hashtags.append("#gloriousFiveDeluxe")
                    hashtags.append("#suckItSteffen")
                else:
                    hashtags.append("#gloriousFive")

                if value not in [1, 64]:
                    hashtags.append("#notSoGlorious")
                    hashtags.append("#cheapVictory")
                    hashtags.append("#fuckFruitsButNotInASexualWay")

                _send_message(
                    chat_id,
                    f"Fuck yeah! {' '.join(hashtags)}",
                    gold_result.last_message_id,
                )
                return
            elif gold_result.last_message_id is None:
                _send_message(chat_id, "I got bored")
                return
            else:
                if gold_result.stage == GoldStage.bowling:
                    _send_message(chat_id, "#sad #fuckBowling", gold_result.last_message_id)
                elif gold_result.stage == GoldStage.dart:
                    _send_message(
                        chat_id,
                        "#sad #tooSoberForDarts",
                        gold_result.last_message_id,
                    )
                elif gold_result.stage == GoldStage.football:
                    _send_message(
                        chat_id,
                        "#sad #lionelMessiWhoDisIPreferLionelRichieAmirite #allNightLong",
                        gold_result.last_message_id,
                    )
                elif gold_result.stage == GoldStage.basketball:
                    _send_message(
                        chat_id,
                        "#sad #everythingButNet",
                        gold_result.last_message_id,
                    )

        time.sleep(_SLEEP_TIME)


def _start_spam(chat_id: int, history: History):
    global is_spamming, spammer
    if is_spamming or spammer is not None:
        return

    def _run():
        global is_spamming, spammer
        try:
            _spam(chat_id, history)
        except Exception as e:
            _LOG.error("Unexcpected exception", exc_info=e)
        finally:
            is_spamming = False
            spammer = None

    is_spamming = True
    # always wanted to use that operator
    (spammer := Thread(name="spam", target=_run, daemon=True)).start()


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
