
import threading
import time

from layaos.core import log
from layaos.core.bus import InProcEventBus
from layaos.core.clock import BeatClock

def test_graceful_shutdown():
    log.setup("WARNING")
    bus = InProcEventBus()
    bus.start()
    clk = BeatClock(hz=20, name="grace")

    ran = {"count": 0}
    def on_tick(ts, i):
        ran["count"] += 1
        bus.publish(("noop", {"i": i}))  # raw tuple is allowed by bus

    clk.start(on_tick)
    time.sleep(0.2)
    clk.stop()
    bus.stop()

    # join should have returned promptly (BeatClock.stop and bus.stop do join with timeout)
    assert ran["count"] > 0
