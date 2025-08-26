from __future__ import annotations
from typing import TYPE_CHECKING
from yarl import URL

from constants import SETTINGS_PATH, PriorityMode
from utils import json_load, json_save

if TYPE_CHECKING:
    from main import ParsedArgs # Assuming ParsedArgs is in main.py

# This is the default structure for the settings file.
DEFAULT_SETTINGS = {
    "priority": [],
    "exclude": set(),
    "priority_mode": PriorityMode.PRIORITY_ONLY,
    "autostart_tray": False,
    "tray_notifications": True,
    "connection_quality": 1,
    "proxy": URL(),
    "language": "English",
}

class Settings:
    def __init__(self, args: "ParsedArgs"):
        self._args = args
        self._dirty = False
        self._data = json_load(SETTINGS_PATH, DEFAULT_SETTINGS)

    def _get(self, key: str, default: any = None) -> any:
        return self._data.get(key, default)

    def _set(self, key: str, value: any) -> None:
        if self._data.get(key) != value:
            self._data[key] = value
            self._dirty = True

    @property
    def priority(self) -> list[str]:
        return self._get("priority", [])

    @property
    def exclude(self) -> set[str]:
        return self._get("exclude", set())

    @property
    def priority_mode(self) -> PriorityMode:
        return self._get("priority_mode", PriorityMode.PRIORITY_ONLY)
    
    @priority_mode.setter
    def priority_mode(self, value: PriorityMode) -> None:
        self._set("priority_mode", value)

    @property
    def autostart_tray(self) -> bool:
        return self._get("autostart_tray", False)

    @autostart_tray.setter
    def autostart_tray(self, value: bool) -> None:
        self._set("autostart_tray", value)

    @property
    def tray_notifications(self) -> bool:
        return self._get("tray_notifications", True)

    @tray_notifications.setter
    def tray_notifications(self, value: bool) -> None:
        self._set("tray_notifications", value)

    @property
    def connection_quality(self) -> int:
        return self._get("connection_quality", 1)

    @connection_quality.setter
    def connection_quality(self, value: int) -> None:
        self._set("connection_quality", value)

    @property
    def proxy(self) -> URL:
        return self._get("proxy", URL())

    @proxy.setter
    def proxy(self, value: URL) -> None:
        self._set("proxy", value)

    @property
    def language(self) -> str:
        return self._get("language", "English")

    @language.setter
    def language(self, value: str) -> None:
        self._set("language", value)

    # These properties are derived from command-line arguments
    @property
    def logging_level(self) -> int:
        return self._args.logging_level

    @property
    def log(self) -> bool:
        return self._args.log

    @property
    def tray(self) -> bool:
        return self._args.tray

    @property
    def dump(self) -> bool:
        return self._args.dump

    @property
    def debug_ws(self) -> int:
        return self._args.debug_ws

    @property
    def debug_gql(self) -> int:
        return self._args.debug_gql

    def save(self, *, force: bool = False) -> None:
        if self._dirty or force:
            json_save(SETTINGS_PATH, self._data, sort=True)
            self._dirty = False