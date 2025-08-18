import asyncio
import time
import pytest

from layaos.core.bus import EventBus
from layaos.core.contracts import Event
from layaos.core import log


@pytest.mark.asyncio
async def test_backpressure_resilience():
    """
    เน้น 'ความทน' ภายใต้โหลด: ระบบยัง consume ได้บ้างระหว่าง overload
    - ไม่บังคับต้องมี metric drops (เพราะแต่ละอิมพลีเมนต์ต่างกัน)
    - เพียงตรวจว่า under stress ยังรับ event ได้ > 0 ภายในเวลาที่กำหนด
    """
    log.setup("WARNING")

    # พยายามตั้ง queue เล็ก ถ้า constructor ไม่รับ maxlen ก็ใช้ค่า default ได้
    try:
        bus = EventBus(maxlen=64)  # type: ignore[arg-type]
    except TypeError:  # fallback
        bus = EventBus()           # type: ignore[call-arg]

    bus.start()

    topic = "overload.test"
    recv = 0

    def consumer(ev: Event):
        nonlocal recv
        # หน่วงให้ consumer ช้าหน่อย (จำลอง backpressure)
        time.sleep(0.005)
        recv += 1

    bus.subscribe(topic, consumer)

    # โหม publish เร็ว ๆ จำนวนมาก
    N = 4000
    for i in range(N):
        bus.publish(Event(topic, {"i": i}))
        # publisher เร็ว (แทบไม่หน่วง) เพื่อกดโหลด
        if i % 100 == 0:
            await asyncio.sleep(0)  # ให้โอกาส loop อื่นทำงาน

    # รอให้ consumer ได้ประมวลผลบางส่วน แต่ไม่รอจนหมด
    t0 = time.time()
    while time.time() - t0 < 2.0 and recv == 0:
        await asyncio.sleep(0.01)

    bus.stop()

    # ภายใต้ overload ยังต้อง consume ได้บ้าง
    assert recv > 0, "Expected to consume some events under overload"