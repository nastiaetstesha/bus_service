import json
import logging
from dataclasses import dataclass, asdict

import trio
from trio_websocket import serve_websocket, ConnectionClosed


logger = logging.getLogger("server")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
)


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
        return asdict(self)


@dataclass
class WindowBounds:
    south_lat: float = 0.0
    north_lat: float = 0.0
    west_lng: float = 0.0
    east_lng: float = 0.0

    @classmethod
    def from_json(cls, payload: dict) -> "WindowBounds":
        return cls(
            south_lat=float(payload["south_lat"]),
            north_lat=float(payload["north_lat"]),
            west_lng=float(payload["west_lng"]),
            east_lng=float(payload["east_lng"]),
        )

    def update(self, south_lat: float, north_lat: float, west_lng: float, east_lng: float):

        self.south_lat = float(south_lat)
        self.north_lat = float(north_lat)
        self.west_lng = float(west_lng)
        self.east_lng = float(east_lng)

    def is_inside(self, lat: float, lng: float) -> bool:
        return (
            self.south_lat <= lat <= self.north_lat
            and self.west_lng <= lng <= self.east_lng
        )


ALL_BUSES: dict[str, Bus] = {}


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


# обработчики


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


async def listen_browser(ws, bounds: WindowBounds):
    """Слушаем браузер и обновляем его окно."""
    while True:
        raw = await ws.get_message()
        payload = json.loads(raw)

        if payload.get("msgType") == "newBounds":
            data = payload["data"]
            logger.debug(json.dumps(payload, ensure_ascii=False))
            bounds.update(
                data["south_lat"],
                data["north_lat"],
                data["west_lng"],
                data["east_lng"],
            )
        else:
            logger.debug("browser msg: %s", payload)


async def talk_to_browser(ws, bounds: WindowBounds):
    """Раз в секунду шлём браузеру автобусы в текущем окне."""
    while True:
        await send_buses(ws, bounds)
        await trio.sleep(1)


async def handle_browser(request):
    ws = await request.accept()
    logger.info("browser connected")

    bounds = WindowBounds()

    try:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(listen_browser, ws, bounds)
            nursery.start_soon(talk_to_browser, ws, bounds)
    except ConnectionClosed:
        logger.info("browser disconnected")


async def main():
    logging.getLogger("trio_websocket").setLevel(logging.WARNING)
    logging.getLogger("wsproto").setLevel(logging.WARNING)

    async with trio.open_nursery() as nursery:
        # 8080 — сюда шлёт fake_bus.py
        nursery.start_soon(
            serve_websocket, handle_bus, "127.0.0.1", 8080, None
        )
        # 8000 — сюда подключается браузер
        nursery.start_soon(
            serve_websocket, handle_browser, "127.0.0.1", 8000, None
        )


if __name__ == "__main__":
    trio.run(main)
