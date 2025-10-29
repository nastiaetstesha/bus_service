import json
import logging
from functools import partial
import trio
from trio_websocket import serve_websocket, WebSocketRequest, ConnectionClosed

buses = {}


def jdump(d):
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


async def handle_bus(request: WebSocketRequest, logger: logging.Logger):
    ws = await request.accept()
    try:
        r = request.remote
        addr = f"{getattr(r, 'host', '?')}:{getattr(r, 'port', '?')}"
    except Exception:
        addr = "<unknown>"
    logger.info(f"[8080] connected {addr}")

    try:
        while True:
            raw = await ws.get_message()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.debug("[8080] non-JSON ignored")
                continue

            bus_id = data.get("busId")
            lat = data.get("lat")
            lng = data.get("lng")
            route = data.get("route")
            if not (bus_id and lat is not None and lng is not None and route):
                logger.debug("[8080] incomplete payload ignored: %s", data)
                continue

            buses[str(bus_id)] = {
                "busId": str(bus_id),
                "lat": float(lat),
                "lng": float(lng),
                "route": str(route),
            }
    except ConnectionClosed:
        logger.info(f"[8080] disconnected {addr}")


async def talk_to_browser(request: WebSocketRequest, logger: logging.Logger):
    if request.path not in ("/", "/ws"):
        await request.reject(404)
        return

    ws = await request.accept()

    try:
        r = request.remote
        addr = f"{getattr(r, 'host', '?')}:{getattr(r, 'port', '?')}"
    except Exception:
        addr = "<unknown>"

    logger.info(f"[8000] browser connected {addr}")

    try:
        while True:
            snapshot = {"msgType": "Buses", "buses": list(buses.values())}
            try:
                await ws.send_message(jdump(snapshot))
            except (ConnectionClosed, OSError):
                break
            await trio.sleep(1.0)
    finally:
        logger.info(f"[8000] browser disconnected {addr}")


async def run_server(handler, host, port):
    await serve_websocket(handler, host, port, ssl_context=None)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("bus_server")

    bus_handler = partial(handle_bus, logger=logger)
    browser_handler = partial(talk_to_browser, logger=logger)

    host = "127.0.0.1"
    logger.info(f"listening buses on ws://{host}:8080")
    logger.info(f"serving browser on ws://{host}:8000/ws")

    async with trio.open_nursery() as nursery:
        nursery.start_soon(run_server, bus_handler, host, 8080)
        nursery.start_soon(run_server, browser_handler, host, 8000)


if __name__ == "__main__":
    trio.run(main)
