import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Set
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

LOCAL_TIMEZONE = ZoneInfo("America/Edmonton")
BANNED_STICKER_IDS = {
    1461152152243142756,
    1461253269824471141,
}
REPLACEMENT_STICKER_ID = 1461235460943642656
ALLOWED_CHANNEL_IDS: set[int] = set()


def _parse_target_user_ids(raw: str) -> Set[int]:
    ids: Set[int] = set()
    if not raw:
        return ids

    for part in raw.replace(",", " ").split():
        try:
            ids.add(int(part))
        except ValueError:
            continue

    return ids


def _parse_optional_int(raw: Optional[str]) -> Optional[int]:
    if raw is None or raw.strip() == "":
        return None
    return int(raw)


def _parse_interval_seconds(raw: Optional[str], default: int = 300) -> int:
    if raw is None or raw.strip() == "":
        return default

    interval = int(raw)
    if interval < 10:
        raise ValueError("URL_MONITOR_INTERVAL_SECONDS must be at least 10 seconds")
    return interval


def _parse_positive_int(raw: Optional[str], default: int) -> int:
    if raw is None or raw.strip() == "":
        return default

    value = int(raw)
    if value <= 0:
        raise ValueError("Expected a positive integer value")
    return value


@dataclass(frozen=True)
class MonitorConfig:
    url: Optional[str]
    channel_id: Optional[int]
    interval_seconds: int
    timeout_seconds: int
    state_file: Path
    mention: str
    bedroom_filter: str

    @property
    def enabled(self) -> bool:
        return bool(self.url)


def load_monitor_config() -> MonitorConfig:
    return MonitorConfig(
        url=os.getenv("URL_MONITOR_URL"),
        channel_id=_parse_optional_int(os.getenv("URL_MONITOR_CHANNEL_ID")),
        interval_seconds=_parse_interval_seconds(os.getenv("URL_MONITOR_INTERVAL_SECONDS")),
        timeout_seconds=_parse_positive_int(os.getenv("URL_MONITOR_TIMEOUT_SECONDS"), default=30),
        state_file=Path(os.getenv("URL_MONITOR_STATE_FILE", "url_monitor_state.json")),
        mention=os.getenv("URL_MONITOR_MENTION", "").strip(),
        bedroom_filter=os.getenv("URL_MONITOR_BEDROOM_FILTER", "2").strip(),
    )


TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_USER_IDS = _parse_target_user_ids(os.getenv("TARGET_USER_IDS", ""))
MONITOR_CONFIG = load_monitor_config()
