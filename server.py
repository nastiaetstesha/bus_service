import json
import logging
import trio
from trio_websocket import serve_websocket, ConnectionClosed, WebSocketRequest
from dataclasses import dataclass, asdict


@dataclass
class Bus:
    busId: str
    lat: float
    lng: float
    route: str

    @classmethod
    def from_json(cls, payload: dict) -> "Bus":
        return cls(
            busId=payload["busId"],
            lat=float(payload["lat"]),
            lng=float(payload["lng"]),
            route=payload["route"],
        )

    def to_front(self) -> dict:
        # фронтенд ждёт словарь, поэтому обратно в dict
        return asdict(self)


@dataclass
class WindowBounds:
    south_lat: float
    north_lat: float
    west_lng: float
    east_lng: float

    @classmethod
    def from_json(cls, payload: dict) -> "WindowBounds":
        return cls(
            south_lat=float(payload["south_lat"]),
            north_lat=float(payload["north_lat"]),
            west_lng=float(payload["west_lng"]),
            east_lng=float(payload["east_lng"]),
        )

    def is_inside(self, lat: float, lng: float) -> bool:
        return (
            self.south_lat <= lat <= self.north_lat
            and self.west_lng <= lng <= self.east_lng
        )


logger = logging.getLogger("server")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s:%(name)s:%(message)s",
)

logging.getLogger("trio_websocket").setLevel(logging.WARNING)
logging.getLogger("wsproto").setLevel(logging.WARNING)


ALL_BUSES: dict[str, Bus] = {}

def is_inside(bounds: dict, lat: float, lng: float) -> bool:
    return (
        bounds["south_lat"] <= lat <= bounds["north_lat"]
        and bounds["west_lng"] <= lng <= bounds["east_lng"]
    )


def jdump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def remote_addr(request: WebSocketRequest) -> str:
    """
    Возвращаем адрес клиента так, чтобы он НИКОГДА не ронял сервер.
    В trio_websocket тут может быть Endpoint, tuple или вообще None.
    """
    r = getattr(request, "remote", None)
    if r is None:
        return "unknown"

    # бывает, что это tuple вида ('127.0.0.1', 55555)
    if isinstance(r, tuple) and len(r) == 2:
        return f"{r[0]}:{r[1]}"

    return str(r)



# ----- обработчик автобусов (8080) 
async def handle_bus(request):
    ws = await request.accept()
    logger.info("bus source connected")

    try:
        while True:
            raw = await ws.get_message()
            payload = json.loads(raw)
            bus = Bus.from_json(payload)
            ALL_BUSES[bus.busId] = bus
    except ConnectionClosed:
        logger.info("bus source disconnected")



#  слушатель браузера 
async def listen_browser(ws):
    while True:
        try:
            msg = await ws.get_message()
        except ConnectionClosed:
            break

        try:
            payload = json.loads(msg)
        except json.JSONDecodeError:
            logger.debug("browser sent non-json: %r", msg)
            continue

        if payload.get("msgType") == "newBounds":
            bounds = payload["data"]

            inside = [
                bus for bus in ALL_BUSES.values()
                if is_inside(bounds, bus["lat"], bus["lng"])
            ]
            logger.debug(json.dumps(payload, ensure_ascii=False))
            logger.debug("%s buses inside bounds", len(inside))
        else:
            logger.debug("browser msg: %s", payload)



#  отправитель в браузер 
async def talk_to_browser(ws):
    while True:
        snapshot = {
            "msgType": "Buses",
            "buses": list(ALL_BUSES.values()),
        }
        try:
            await ws.send_message(json.dumps(snapshot, ensure_ascii=False))
        except ConnectionClosed:
            break
        await trio.sleep(1)



# -- обработчик браузера (8000)
async def handle_browser(request):
    ws = await request.accept()
    logger.info("browser connected")

    try:
        while True:
            raw = await ws.get_message()
            payload = json.loads(raw)

            if payload.get("msgType") == "newBounds":
                bounds = WindowBounds.from_json(payload["data"])
                logger.debug(json.dumps(payload, ensure_ascii=False))
                await send_buses(ws, bounds)
            else:
                logger.debug("browser msg: %s", payload)

    except ConnectionClosed:
        logger.info("browser disconnected")


# async def handle_browser(request: WebSocketRequest):
#     addr = remote_addr(request)
#     logger.info("[8000] browser connected %s path=%s", addr, request.path)

#     # if request.path != "/ws":
#     #     logger.warning("browser connected to unexpected path %s", request.path)

#     ws = await request.accept()

#     async with trio.open_nursery() as nursery:
#         nursery.start_soon(listen_browser, ws)
#         nursery.start_soon(talk_to_browser, ws)

#     logger.info("[8000] browser disconnected %s", addr)


async def send_buses(ws, bounds: WindowBounds):
    visible = [
        bus.to_front()
        for bus in ALL_BUSES.values()
        if bounds.is_inside(bus.lat, bus.lng)
    ]
    msg = {
        "msgType": "Buses",
        "buses": visible,
    }
    await ws.send_message(json.dumps(msg, ensure_ascii=False))
    logger.debug("%s buses inside bounds", len(visible))


#  ---- запуск двух серверов 
async def main():
    async with trio.open_nursery() as nursery:
        # на 8080 будем слушать автобусы
        nursery.start_soon(
            serve_websocket, handle_bus, "127.0.0.1", 8080, None
        )
        # на 8000 — браузер
        nursery.start_soon(
            serve_websocket, handle_browser, "127.0.0.1", 8000, None
        )


if __name__ == "__main__":
    # чтобы trio-websocket не флудил
    logging.getLogger("trio_websocket").setLevel(logging.WARNING)
    logging.getLogger("wsproto").setLevel(logging.WARNING)

    trio.run(main)

