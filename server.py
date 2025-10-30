import json
import logging
import argparse
from dataclasses import dataclass, asdict
from contextlib import suppress

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


async def run_server(bus_port: int, browser_port: int):
    async with trio.open_nursery() as nursery:
        nursery.start_soon(
            serve_websocket, handle_bus, "127.0.0.1", bus_port, None
        )
        nursery.start_soon(
            serve_websocket, handle_browser, "127.0.0.1", browser_port, None
        )
        logger.info("listening on ws://127.0.0.1:%s (buses)", bus_port)
        logger.info("listening on ws://127.0.0.1:%s (browser)", browser_port)


# async def main():
#     logging.getLogger("trio_websocket").setLevel(logging.WARNING)
#     logging.getLogger("wsproto").setLevel(logging.WARNING)

#     async with trio.open_nursery() as nursery:
#         # 8080 — сюда шлёт fake_bus.py
#         nursery.start_soon(
#             serve_websocket, handle_bus, "127.0.0.1", 8080, None
#         )
#         # 8000 — сюда подключается браузер
#         nursery.start_soon(
#             serve_websocket, handle_browser, "127.0.0.1", 8000, None
#         )


def setup_logging(verbosity: int):
    # 0 — WARNING, 1 — INFO, 2+ — DEBUG
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
    )

    logging.getLogger("trio_websocket").setLevel(logging.WARNING)
    logging.getLogger("wsproto").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сервер для урока «Автобусы на карте»"
    )
    parser.add_argument(
        "--bus-port",
        type=int,
        default=8080,
        help="порт, на который шлёт имитатор автобусов (default: 8080)",
    )
    parser.add_argument(
        "--browser-port",
        type=int,
        default=8000,
        help="порт, на который подключается браузер (default: 8000)",
    )
    parser.add_argument(
        "-v",
        action="count",
        default=0,
        help="уровень логирования: -v (INFO), -vv (DEBUG)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.v)

    with suppress(KeyboardInterrupt):
        trio.run(run_server, args.bus_port, args.browser_port)

    logger.info("stopped by user")