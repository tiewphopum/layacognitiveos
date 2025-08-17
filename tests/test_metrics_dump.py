# tests/test_metrics_dump.py
from layaos.core import log
from layaos.core.bus import InProcEventBus
from layaos.core.clock import BeatClock
from layaos.core.contracts import Event
import time

def main():
    log.setup("INFO")
    bus = InProcEventBus(); bus.start()

    def c1(ev): pass
    bus.subscribe("a.b", c1)

    clk = BeatClock(hz=5.0, name="clock.fast")
    def on_tick(ts, i):
        bus.publish(Event("a.b", {"i": i, "ts": ts}))
        if i >= 10:
            clk.stop()

    clk.start(on_tick)
    time.sleep(3.0)
    bus.stop()

def test_step1():
    main()
    print("Hello from print()")
    assert True