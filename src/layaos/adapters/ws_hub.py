# src/layaos/adapters/ws_hub.py
from __future__ import annotations
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, Optional, Set

log = logging.getLogger(__name__)

try:
    import websockets  # type: ignore
except Exception:  # pragma: no cover
    websockets = None  # optional dependency

MessageHandler = Callable[[str, dict], Awaitable[None]]

@dataclass
class WSHubClientConfig:
    url: str = "ws://127.0.0.1:8765"
    reconnect_delay: float = 1.0

@dataclass
class WSHubClient:
    cfg: WSHubClientConfig
    _ws: Optional["websockets.WebSocketClientProtocol"] = None
    _subs: Dict[str, Set[MessageHandler]] = field(default_factory=dict)
    _task_recv: Optional[asyncio.Task] = None
    _closed: bool = False

    async def connect(self) -> None:
        if websockets is None:
            raise RuntimeError("websockets not installed. `pip install websockets`")
        while not self._closed:
            try:
                log.info("ws connect %s", self.cfg.url)
                self._ws = await websockets.connect(self.cfg.url)
                self._task_recv = asyncio.create_task(self._recv_loop())
                return
            except Exception as e:
                log.warning("ws connect failed: %s; retry in %.1fs", e, self.cfg.reconnect_delay)
                await asyncio.sleep(self.cfg.reconnect_delay)

    async def close(self) -> None:
        self._closed = True
        if self._task_recv:
            self._task_recv.cancel()
        if self._ws:
            await self._ws.close()

    async def publish(self, topic: str, payload: dict) -> None:
        if not self._ws:
            raise RuntimeError("ws not connected")
        msg = {"type": "pub", "topic": topic, "data": payload}
        await self._ws.send(json.dumps(msg))

    async def subscribe(self, topic: str, handler: MessageHandler) -> None:
        self._subs.setdefault(topic, set()).add(handler)
        # inform server (best-effort)
        if self._ws:
            await self._ws.send(json.dumps({"type": "sub", "topic": topic}))

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        ws = self._ws
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    topic = msg.get("topic", "")
                    data = msg.get("data", {})
                    for h in self._subs.get(topic, set()):
                        await h(topic, data)
                except Exception as e:
                    log.exception("ws recv err: %s", e)
        finally:
            self._ws = None
            if not self._closed:
                log.info("ws disconnected; will reconnect")
                await self.connect()