
# tests/conftest.py
import os
import logging
import pytest

from layaos.core import log
from layaos.core.metrics import start_exporter, stop_exporter

@pytest.fixture(scope="session", autouse=True)
def _bootstrap_logging_and_metrics():
    # Setup logging (reads LOG_LEVEL / LOG_JSON / .env if available)
    log.setup()

    # Start metrics exporter with short interval during tests
    interval = float(os.getenv("METRICS_INTERVAL_TEST", "1.0"))
    json_mode = (os.getenv("LOG_JSON", "0") == "1")
    start_exporter(interval_sec=interval, json_mode=json_mode,
                   logger=logging.getLogger("metrics"))
    yield
    stop_exporter()
