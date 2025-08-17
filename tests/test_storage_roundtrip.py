
import json
import time
from pathlib import Path

from layaos.core import log
from layaos.core.contracts import DetectionEvent, CellStat
from layaos.adapters.storage import AsyncStorage

def test_storage_roundtrip(tmp_path: Path):
    log.setup("WARNING")
    st = AsyncStorage(tmp_path.as_posix(), max_queue=64, prefix="det")
    st.start()

    # enqueue 10 detection events
    for i in range(10):
        det = DetectionEvent(ts=time.time(), cam_id="cam0", any_motion=(i%2==0), motion_ratio=0.1*i,
                             cells=[CellStat(idx=0, ratio=0.01*i)])
        st.put_json("det", det)

    # wait for the worker to flush
    st.q.join()
    st.stop()

    files = sorted((tmp_path / "det").glob("det-*.json"))
    assert len(files) == 10

    # spot check schema
    sample = json.loads(files[0].read_text(encoding="utf-8"))
    assert "cam_id" in sample and "any_motion" in sample and "motion_ratio" in sample
