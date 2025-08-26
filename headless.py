from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Coroutine, TypeVar

if TYPE_CHECKING:
    from twitch import Twitch
    from inventory import TimedDrop, DropsCampaign
    from utils import Game
    from gui import LoginData, ChannelList, InventoryOverview


_T = TypeVar("_T")

class LoginData:
    username: str
    password: str
    token: str

class MockLogin:
    async def ask_login(self) -> LoginData:
        raise NotImplementedError("Login is not supported in headless mode")

    async def ask_enter_code(self, page_url, user_code):
        print(f"Please go to {page_url} and enter the code: {user_code}")

    def update(self, status: str, user_id: int | None):
        print(f"Login status: {status}, user_id: {user_id}")
    
    def clear(self, *args, **kwargs):
        pass

class MockTray:
    def change_icon(self, state: str): pass
    def notify(self, *args, **kwargs): pass

class MockStatus:
    def update(self, text: str):
        logger.info(f"Status: {text}")

class MockChannels:
    def display(self, channel, *, add: bool = False): pass
    def remove(self, channel): pass
    def clear(self) -> None: pass
    def clear_watching(self) -> None: pass
    def get_selection(self) -> Any: return None
    def set_watching(self, channel) -> None: pass

class MockProgress:
    # This is the key to fixing the stall and getting real progress.
    def minute_almost_done(self) -> bool:
        # Returning True forces the reliable GQL fallback in the original
        # twitch.py's _watch_loop to run, fetching real progress.
        return True
    def stop_timer(self): pass
    def display(self, drop: "TimedDrop" | None, *, countdown: bool = True, subone: bool = False): pass
    def is_counting(self) -> bool: return False

class MockInventory:
    async def add_campaign(self, campaign: "DropsCampaign") -> None: pass
    def clear(self) -> None: pass
    def update_drop(self, drop: "TimedDrop") -> None: pass

class MockWebsocketStatus:
    def update(self, *args: Any, **kwargs: Any) -> None: pass
    def remove(self, *args: Any, **kwargs: Any) -> None: pass

logger = logging.getLogger("TwitchDrops")

class HeadlessGUIManager:
    def __init__(self, twitch: "Twitch"):
        self._twitch = twitch
        self._close_requested = asyncio.Event()
        self.login = MockLogin()
        self.tray = MockTray()
        self.status = MockStatus()
        self.channels: ChannelList = MockChannels()
        self.progress = MockProgress()
        self.inv: InventoryOverview = MockInventory()
        self.websockets = MockWebsocketStatus()

    def print(self, message: str):
        print(message)

    def start(self): pass
    def stop(self): pass
    def close_window(self): pass

    async def coro_unless_closed(self, coro: Coroutine[Any, Any, _T]) -> _T:
        request_task = asyncio.create_task(coro)
        close_task = asyncio.create_task(self._close_requested.wait())
        done, pending = await asyncio.wait([request_task, close_task], return_when=asyncio.FIRST_COMPLETED)
        for task in pending: task.cancel()
        if request_task in done:
            return request_task.result()
        else:
            from exceptions import ExitRequest
            raise ExitRequest()

    @property
    def close_requested(self) -> bool:
        return self._close_requested.is_set()

    def prevent_close(self):
        self._close_requested.clear()

    async def wait_until_closed(self):
        await self._close_requested.wait()

    def close(self, *args: Any):
        self._close_requested.set()
        self._twitch.close()
        return 0

    def display_drop(self, drop: "TimedDrop", *, countdown: bool = True, subone: bool = False): pass
    def clear_drop(self): pass
    def set_games(self, games: set["Game"]) -> None: pass
    def save(self, *, force: bool = False) -> None: pass