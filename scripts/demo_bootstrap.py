import os
from layaos.core import log
from layaos.core.metrics import start_exporter, inc_counter, observe_hist
import time
import random

def main():
    log.setup()
    start_exporter(interval_sec=float(os.getenv("METRICS_INTERVAL", "5")),
                   json_mode=(os.getenv("LOG_JSON", "0") == "1"))

    # เดโม่โยน metrics สักหน่อย
    for _ in range(10):
        inc_counter("event_rate", topic="demo")
        observe_hist("latency_ms", random.uniform(5, 30), stage="demo")
        time.sleep(0.5)

if __name__ == "__main__":
    main()