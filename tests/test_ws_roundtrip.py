
# tests/test_ws_roundtrip.py
import asyncio
import json
import pytest

websockets = pytest.importorskip("websockets")

@pytest.mark.asyncio
async def test_ws_roundtrip():
    from layaos.adapters.ws_hub import WSHubClient, WSHubClientConfig

    # เซิร์ฟเวอร์จำลองเล็ก ๆ
    async def echo_server(ws):
        subs = set()
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "sub":
                subs.add(msg["topic"])
            elif msg.get("type") == "pub":
                if msg["topic"] in subs:
                    await ws.send(json.dumps({"topic": msg["topic"], "data": msg["data"]}))

    async def server_main(stop_evt):
        async with websockets.serve(lambda ws: echo_server(ws), "127.0.0.1", 8765):
            await stop_evt.wait()

    stop_evt = asyncio.Event()
    srv = asyncio.create_task(server_main(stop_evt))
    await asyncio.sleep(0.1)

    received = {}

    async def on_msg(topic, data):
        received[topic] = data

    cli = WSHubClient(WSHubClientConfig(url="ws://127.0.0.1:8765"))
    await cli.connect()
    await cli.subscribe("demo", on_msg)
    await cli.publish("demo", {"x": 1})
    await asyncio.sleep(0.1)

    assert received.get("demo") == {"x": 1}

    await cli.close()
    stop_evt.set()
    await srv