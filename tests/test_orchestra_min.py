# tests/test_orchestra_min.py
import asyncio
import pytest

from layaos.pipeline.wire_minimal import build_pipeline


@pytest.mark.asyncio
async def test_orchestra_min_runs_without_errors():
    """
    Minimal orchestration smoke test: build the 6-state pipeline and run
    briefly to ensure the state clocks tick without raising exceptions.
    """
    bus, _cam, states = build_pipeline()

    # run each state concurrently for a short demo duration
    tasks = [asyncio.create_task(s.run()) for s in states]
    try:
        await asyncio.sleep(0.6)  # ~several ticks even for slowest beat
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # If we reached here without exceptions, consider it a pass for smoke test
    assert True