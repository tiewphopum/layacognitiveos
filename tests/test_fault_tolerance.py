
import time
import random
from typing import List

from layaos.core import log
from layaos.core.clock import BeatClock

def test_fault_tolerance_random_exceptions():
    log.setup("WARNING")
    clk = BeatClock(hz=50, name="faulty")
    ticks: List[int] = []

    def on_tick(ts: float, i: int):
        ticks.append(i)
        # inject fault 5% of the time
        if random.random() < 0.05:
            raise RuntimeError("injected fault")

    clk.start(on_tick)
    time.sleep(0.5)  # ~25 ticks expected
    clk.stop()

    # Clock should continue despite exceptions (BeatClock catches and logs, keeps running)
    assert len(ticks) >= 10
