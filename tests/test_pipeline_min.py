# tests/test_pipeline_min.py
from layaos.core import log
from layaos.core.bus import EventBus
from layaos.core.clock import BeatClock
from layaos.core.contracts import Event
from collections import Counter

def main():
    log.setup("DEBUG")
    bus = EventBus()
    bus.start()

    ev_count = Counter()

    # --- State2 ---
    def s2(ev):
        ev_count[ev.topic] += 1
        log.get("state2").info("got %s %s (count=%d)", ev.topic, ev.payload, ev_count[ev.topic])
        # ส่งต่อไป State3
        val = ev.payload["i"] * 2
        bus.publish(Event("state2.preproc", {"val": val, "ts": ev.payload["ts"]}))

    # --- State3 ---
    def s3(ev):
        ev_count[ev.topic] += 1
        log.get("state3").info("got %s %s (count=%d)", ev.topic, ev.payload, ev_count[ev.topic])
        if ev.payload["val"] % 4 == 0:
            log.get("state3").info("TRIGGER v=%s ts=%.3f", ev.payload["val"], ev.payload["ts"])

    bus.subscribe("state1.raw", s2)
    bus.subscribe("state2.preproc", s3)

    clk = BeatClock(hz=4.0)
    def tick(ts, i):
        bus.publish(Event("state1.raw", {"i": i, "ts": ts}))

    clk.start(tick)
    import time; time.sleep(3)
    clk.stop()
    bus.stop()

def test_step1():
    main()
    print("Hello from print()")
    assert True