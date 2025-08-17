# src/core/buffer.py
from __future__ import annotations
import collections
from typing import Deque, Optional, Any

class RingBuffer:
    def __init__(self, capacity: int = 256):
        self.cap = capacity
        self.buf: Deque[Any] = collections.deque(maxlen=capacity)

    def push(self, item: Any):
        self.buf.append(item)  # ล้นแล้วดันหัวทิ้งอัตโนมัติ

    def pop(self) -> Optional[Any]:
        return self.buf.popleft() if self.buf else None

    def peek(self) -> Optional[Any]:
        return self.buf[0] if self.buf else None

    def __len__(self): return len(self.buf)