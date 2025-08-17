# src/core/dispatcher.py
from __future__ import annotations
from typing import Callable, Dict
from .contracts import Event

Handler = Callable[[Event], None]

class Dispatcher:
    def __init__(self):
        self.routes: Dict[str, Handler] = {}  # topic exact match

    def register(self, topic: str, handler: Handler):
        self.routes[topic] = handler

    def handle(self, ev: Event):
        h = self.routes.get(ev.topic)
        if h: h(ev)