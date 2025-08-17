# tests/test_camera_to_bus.py
import asyncio
import pytest
from layaos.core.bus import InProcEventBus
from layaos.synth.mock_camera import MockCamera, MockCamConfig
from layaos.adapters.storage import LocalEventStorage, StorageConfig

# ลบ @pytest.mark.asyncio ทิ้ง
def test_camera_to_bus():
    import asyncio
    async def _run():
        from layaos.core.bus import InProcEventBus
        from layaos.synth.mock_camera import MockCamera, MockCamConfig
        from layaos.adapters.storage import LocalEventStorage, StorageConfig

        bus = InProcEventBus(maxlen=128)
        cam = MockCamera(MockCamConfig(width=64, height=48, fps=8), bus=bus, topic_out="cam/0.frame")
        st = LocalEventStorage(StorageConfig(base_dir=".test-out"))
        n = 10

        async def consumer():
            c = 0
            while c < n:
                evt = await bus.consume("cam/0.frame")
                assert "frame" in evt
                st.save_json("cam/0.event", {"i": c})
                c += 1

        task_cam = asyncio.create_task(cam.run(n_frames=n))
        task_cons = asyncio.create_task(consumer())
        await asyncio.gather(task_cam, task_cons)

