from __future__ import annotations

import json
import asyncio
import logging
from time import time
from contextlib import suppress
from typing import Any, Literal, TYPE_CHECKING

import aiohttp

from translate import _
from exceptions import MinerException, WebsocketClosed
from constants import PING_INTERVAL, PING_TIMEOUT, MAX_WEBSOCKETS, WS_TOPICS_LIMIT
from utils import (
    CHARS_ASCII,
    task_wrapper,
    create_nonce,
    json_minify,
    format_traceback,
    AwaitableValue,
    ExponentialBackoff,
)

if TYPE_CHECKING:
    from collections import abc
    from twitch import Twitch
    from gui import WebsocketStatus
    from constants import JsonType, WebsocketTopic


WSMsgType = aiohttp.WSMsgType
logger = logging.getLogger("TwitchDrops")
ws_logger = logging.getLogger("TwitchDrops.websocket")


class Websocket:
    def __init__(self, pool: "WebsocketPool", index: int):
        self._pool: "WebsocketPool" = pool
        self._twitch: "Twitch" = pool._twitch
        self._ws_gui: "WebsocketStatus" = self._twitch.gui.websockets
        self._state_lock = asyncio.Lock()
        self._idx: int = index
        self._ws: AwaitableValue[aiohttp.ClientWebSocketResponse] = AwaitableValue()
        self._closed = asyncio.Event()
        self._reconnect_requested = asyncio.Event()
        self._topics_changed = asyncio.Event()
        self._next_ping: float = time()
        self._max_pong: float = self._next_ping + PING_TIMEOUT.total_seconds()
        self._handle_task: asyncio.Task[None] | None = None
        self.topics: dict[str, WebsocketTopic] = {}
        self._submitted: set[WebsocketTopic] = set()
        self.set_status(_("gui", "websocket", "disconnected"))

    def set_status(self, status: str | None = None, refresh_topics: bool = False):
        self._twitch.gui.websockets.update(
            self._idx, status=status, topics=(len(self.topics) if refresh_topics else None)
        )

    def request_reconnect(self):
        self._next_ping = time()
        self._reconnect_requested.set()

    async def start(self):
        async with self._state_lock:
            if self._handle_task is None or self._handle_task.done():
                self._handle_task = asyncio.create_task(self._handle())
            await self._ws.wait()

    async def stop(self, *, remove: bool = False):
        async with self._state_lock:
            if self._closed.is_set(): return
            self._closed.set()
            if ws := self._ws.get_with_default(None):
                await ws.close()
            if self._handle_task:
                with suppress(asyncio.TimeoutError, asyncio.CancelledError):
                    await asyncio.wait_for(self._handle_task, timeout=2)
            if remove:
                self._twitch.gui.websockets.remove(self._idx)

    async def _backoff_connect(self, ws_url: str, **kwargs) -> abc.AsyncGenerator[aiohttp.ClientWebSocketResponse, None]:
        session = await self._twitch.get_session()
        proxy = self._twitch.settings.proxy if self._twitch.settings.proxy else None
        backoff = ExponentialBackoff(**kwargs)
        for delay in backoff:
            try:
                async with session.ws_connect(ws_url, proxy=proxy) as websocket:
                    yield websocket
                    backoff.reset()
            except (aiohttp.ClientError, asyncio.TimeoutError):
                await asyncio.sleep(delay)
            except RuntimeError:
                break

    @task_wrapper(critical=True)
    async def _handle(self):
        self.set_status(_("gui", "websocket", "initializing"))
        await self._twitch.wait_until_login()
        self._closed.clear()
        async for websocket in self._backoff_connect("wss://pubsub-edge.twitch.tv/v1", maximum=180):
            self._ws.set(websocket)
            self._reconnect_requested.clear()
            self._topics_changed.set()
            self.set_status(_("gui", "websocket", "connected"))
            try:
                while not self._reconnect_requested.is_set():
                    await self._handle_ping()
                    await self._handle_topics()
                    await self._handle_recv()
            except WebsocketClosed as exc:
                if self._closed.is_set():
                    break
            finally:
                self._ws.clear()
                self._submitted.clear()
        self.set_status(_("gui", "websocket", "disconnected"))

    async def _handle_ping(self):
        now = time()
        if now >= self._next_ping:
            self._next_ping = now + PING_INTERVAL.total_seconds()
            self._max_pong = now + PING_TIMEOUT.total_seconds()
            await self.send({"type": "PING"})
        elif now >= self._max_pong:
            self.request_reconnect()

    async def _handle_topics(self):
        if not self._topics_changed.is_set(): return
        self._topics_changed.clear()
        self.set_status(refresh_topics=True)
        auth_state = await self._twitch.get_auth()
        current = set(self.topics.values())
        if removed := self._submitted.difference(current):
            await self.send({"type": "UNLISTEN", "data": {"topics": [str(t) for t in removed], "auth_token": auth_state.access_token}})
            self._submitted.difference_update(removed)
        if added := current.difference(self._submitted):
            await self.send({"type": "LISTEN", "data": {"topics": [str(t) for t in added], "auth_token": auth_state.access_token}})
            self._submitted.update(added)

    async def _handle_recv(self):
        ws = await self._ws.get()
        try:
            raw_message = await ws.receive(timeout=1.0)
            if raw_message.type is WSMsgType.TEXT:
                message = json.loads(raw_message.data)
                if message.get("type") == "MESSAGE":
                    if topic := self.topics.get(message["data"]["topic"]):
                        asyncio.create_task(topic(json.loads(message["data"]["message"])))
                elif message.get("type") == "PONG":
                    self._max_pong = self._next_ping
                elif message.get("type") == "RECONNECT":
                    self.request_reconnect()
            elif raw_message.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.CLOSING, WSMsgType.ERROR):
                raise WebsocketClosed(received=True)
        except asyncio.TimeoutError:
            pass

    async def send(self, message: JsonType):
        ws = await self._ws.get()
        if message["type"] != "PING":
            message["nonce"] = create_nonce(CHARS_ASCII, 30)
        await ws.send_json(message, dumps=json_minify)

class WebsocketPool:
    def __init__(self, twitch: Twitch):
        self._twitch: Twitch = twitch
        self._running = asyncio.Event()
        self.websockets: list[Websocket] = []

    async def start(self):
        self._running.set()
        await asyncio.gather(*(ws.start() for ws in self.websockets))

    async def stop(self, *, clear_topics: bool = False):
        self._running.clear()
        await asyncio.gather(*(ws.stop(remove=clear_topics) for ws in self.websockets))

    # FIX #1: This method is now async
    async def add_topics(self, topics: abc.Iterable[WebsocketTopic]):
        topics_set = set(topics)
        topics_set.difference_update(*(ws.topics.values() for ws in self.websockets))
        if not topics_set: return
        for i in range(MAX_WEBSOCKETS):
            if i < len(self.websockets):
                ws = self.websockets[i]
            else:
                ws = Websocket(self, i)
                if self._running.is_set():
                    # FIX #2: We now await the start call
                    await ws.start()
                self.websockets.append(ws)
            
            while topics_set and len(ws.topics) < WS_TOPICS_LIMIT:
                topic = topics_set.pop()
                ws.topics[str(topic)] = topic
            ws._topics_changed.set()
            if not topics_set: return
        raise MinerException("Maximum topics limit has been reached")

    def remove_topics(self, topics: list[str]):
        topics_set = set(topics)
        for ws in self.websockets:
            if existing := topics_set.intersection(ws.topics.keys()):
                topics_set.difference_update(existing)
                for topic in existing:
                    del ws.topics[topic]
                ws._topics_changed.set()
        
        recycled_topics = []
        while self.websockets and sum(len(ws.topics) for ws in self.websockets) <= (len(self.websockets) - 1) * WS_TOPICS_LIMIT:
            ws = self.websockets.pop()
            recycled_topics.extend(ws.topics.values())
            asyncio.create_task(ws.stop(remove=True))
        if recycled_topics:
            asyncio.create_task(self.add_topics(recycled_topics))