import asyncio
import pytest

from layaos.core.bus import InProcEventBus

class DummyEvent:
    def __init__(self, topic, payload):
        self.topic = topic
        self.data = payload        # ✅ bus.publish(Event) คาด ev.data
        self.payload = payload     # (เผื่ออนาคต รองรับทั้งสองชื่อ)

@pytest.mark.asyncio
async def test_bus_publish_topic_and_event_dual_api():
    bus = InProcEventBus(maxlen=32)

    # โหมด 1: publish(topic, data)
    bus.publish("t.alpha", {"i": 1})
    bus.publish("t.alpha", {"i": 2})
    assert bus.queue_depth("t.alpha") == 2

    msg1 = await asyncio.wait_for(bus.consume("t.alpha"), timeout=2.0)
    msg2 = await asyncio.wait_for(bus.consume("t.alpha"), timeout=2.0)
    assert (msg1["i"], msg2["i"]) == (1, 2)
    assert bus.queue_depth("t.alpha") == 0

    # โหมด 2: publish(Event) -> ต้องใช้ ev.data
    bus.publish(DummyEvent("t.beta", {"ok": True, "n": 7}))
    got = await asyncio.wait_for(bus.consume("t.beta"), timeout=2.0)
    assert got == {"ok": True, "n": 7}

    # try_consume ตอนคิวว่าง → None
    assert await bus.try_consume("t.beta") is None

@pytest.mark.asyncio
async def test_bus_concurrent_producers_single_consumer():
    bus = InProcEventBus(maxlen=128)
    topic = "t.concurrent"
    N1, N2 = 25, 35

    async def producer(start, count):
        for k in range(count):
            bus.publish(topic, {"k": start + k})
            await asyncio.sleep(0)  # ปล่อยให้สลับ task

    async def consumer(expected_total, timeout_s=5.0):
        out = []
        deadline = asyncio.get_event_loop().time() + timeout_s
        while len(out) < expected_total:
            # ใช้ try_consume เพื่อตัดอาการค้าง
            msg = await bus.try_consume(topic)
            if msg is not None:
                out.append(msg["k"])
                continue
            if asyncio.get_event_loop().time() > deadline:
                break
            await asyncio.sleep(0.005)
        return out

    # รันพร้อมกัน 2 producer + 1 consumer (polling)
    consumed, *_ = await asyncio.gather(
        consumer(N1 + N2),
        producer(0, N1),
        producer(1000, N2),
    )

    assert len(consumed) == N1 + N2
    assert set(consumed) == set(list(range(0, N1)) + list(range(1000, 1000 + N2)))

@pytest.mark.asyncio
async def test_bus_queue_depth_and_empty_try_consume():
    bus = InProcEventBus(maxlen=8)
    assert bus.queue_depth("x") == 0

    bus.publish("x", {"a": 1})
    bus.publish("x", {"a": 2})
    assert bus.queue_depth("x") == 2

    # ดึง 1 ชิ้น แล้วลอง try_consume ที่ยังเหลือ
    one = await bus.consume("x")
    assert one["a"] == 1
    maybe = await bus.try_consume("x")
    assert maybe == {"a": 2}
    assert bus.queue_depth("x") == 0

    # ไม่มีของ → try_consume ต้องเป็น None
    assert await bus.try_consume("x") is None