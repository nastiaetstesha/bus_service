import json
import random
import logging
import argparse
from typing import List, Dict, Any
from itertools import cycle, islice
from functools import partial
import functools
import trio_websocket

import trio
from trio import ClosedResourceError
from trio_websocket import open_websocket_url, ConnectionClosed
from contextlib import suppress

from load_routes import load_routes


logger = logging.getLogger("fake_bus")


def relaunch_on_disconnect(delay: float = 0.3):
    def wrapper(func):
        @functools.wraps(func)
        async def inner(*args, **kwargs):
            while True:
                try:
                    await func(*args, **kwargs)
                except (
                    trio_websocket.ConnectionClosed,
                    trio_websocket.HandshakeError,
                    OSError,
                ) as e:
                    logger.warning("connection lost (%s), reconnect in %.1fs", e, delay)
                    await trio.sleep(delay)
                except trio.ClosedResourceError as e:
                    logger.info("resource closed: %s", e)
                    return
        return inner
    return wrapper



def setup_logging(verbosity: int):
    # -v → INFO, -vv → DEBUG
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
    )


# ------ утилиты маршрута 
def route_points(route: Dict[str, Any]) -> List[Dict[str, float]]:
    return [{"lat": float(lat), "lng": float(lng)} for lat, lng in route["coordinates"]]


def generate_bus_id(route_id: str, bus_index: int, emulator_id: str = "") -> str:
    base = f"{route_id}-{bus_index}"
    return f"{emulator_id}-{base}" if emulator_id else base


def build_iterator(points: List[Dict[str, float]], step_skip: int, start_offset: int):
    if step_skip < 1:
        step_skip = 1
    base = points[::step_skip] if step_skip > 1 else points
    if len(base) == 1:
        base = base * 2
    cyc = cycle(base)
    start_offset = start_offset % len(base)
    return islice(cyc, start_offset, None)


# ---------- один автобус: пишет в канал
async def run_bus(
    send_ch: trio.MemorySendChannel,
    bus_id: str,
    route_name: str,
    points: List[Dict[str, float]],
    *,
    period: float = 0.3,
    step_skip: int = 1,
    start_offset: int = 0,
):
    await trio.sleep(random.uniform(0, 0.5))
    it = build_iterator(points, step_skip, start_offset)
    try:
        for p in it:
            msg = {
                "busId": bus_id,
                "lat": round(p["lat"], 6),
                "lng": round(p["lng"], 6),
                "route": route_name,
            }
            await send_ch.send(msg)
            await trio.sleep(period)
    except ClosedResourceError:
        return


# ------ отправитель: один сокет на канал --------
# async def send_updates(url: str, recv_ch: trio.MemoryReceiveChannel):
#     while True:
#         try:
#             async with open_websocket_url(url) as ws:
#                 async with recv_ch:
#                     async for msg in recv_ch:
#                         await ws.send_message(json.dumps(msg, ensure_ascii=False))
#         except (ConnectionClosed, OSError) as e:
#             logger.warning("sender: %s, reconnecting…", e)
#             await trio.sleep(0.3)
@relaunch_on_disconnect(delay=0.3)
async def send_updates(url: str, recv_ch: trio.MemoryReceiveChannel):
    async with open_websocket_url(url) as ws:
        while True:
            # ждём сообщение от автобуса
            msg = await recv_ch.receive()
            # отправляем на сервер
            await ws.send_message(json.dumps(msg, ensure_ascii=False))



# --------- main ----
async def main(
    server: str,
    routes_number: int,
    buses_per_route: int,
    websockets_number: int,
    emulator_id: str,
    refresh_timeout: float,
    step_skip: int,
    shuffle: bool,
    channel_capacity: int,
    routes_dir: str,
):
    routes = list(load_routes(routes_dir))
    if shuffle:
        random.shuffle(routes)
    if routes_number > 0:
        routes = routes[:routes_number]

    logger.info(
        "starting emulator: server=%s, routes=%s, buses_per_route=%s, websockets=%s",
        server,
        len(routes),
        buses_per_route,
        websockets_number,
    )

    async with trio.open_nursery() as nursery:
        send_channels: list[trio.MemorySendChannel] = []
        for _ in range(max(1, websockets_number)):
            send_ch, recv_ch = trio.open_memory_channel(channel_capacity)
            send_channels.append(send_ch)
            nursery.start_soon(send_updates, server, recv_ch)

        for route in routes:
            route_name = str(route["name"])
            pts = route_points(route)

            for i in range(buses_per_route):
                bus_id = generate_bus_id(route_name, i, emulator_id=emulator_id)
                start_offset = (len(pts) * i) // max(1, buses_per_route)
                send_ch = random.choice(send_channels)

                nursery.start_soon(
                    partial(
                        run_bus,
                        send_ch,
                        bus_id,
                        route_name,
                        pts,
                        period=refresh_timeout,
                        step_skip=step_skip,
                        start_offset=start_offset,
                    )
                )



# -- cli 
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Имитатор движения автобусов для урока «Автобусы на карте»"
    )
    parser.add_argument(
        "--server",
        default="ws://127.0.0.1:8080",
        help="адрес ws-сервера (по умолчанию ws://127.0.0.1:8080)",
    )
    parser.add_argument(
        "--routes-dir",
        default="routes",
        help="папка с JSON маршрутами",
    )
    parser.add_argument(
        "--routes-number",
        type=int,
        default=50,
        help="сколько маршрутов запустить (0 = все)",
    )
    parser.add_argument(
        "--buses-per-route",
        type=int,
        default=5,
        help="сколько автобусов на каждый маршрут",
    )
    parser.add_argument(
        "--websockets-number",
        type=int,
        default=8,
        help="сколько одновременно держать ws-соединений",
    )
    parser.add_argument(
        "--emulator-id",
        default="",
        help="префикс к busId, чтобы различать несколько экземпляров имитатора",
    )
    parser.add_argument(
        "--refresh-timeout",
        type=float,
        default=0.25,
        help="пауза между отправками координат (сек)",
    )
    parser.add_argument(
        "--step-skip",
        type=int,
        default=2,
        help="брать каждую N-ю точку маршрута",
    )
    parser.add_argument(
        "--channel-capacity",
        type=int,
        default=2000,
        help="размер буфера канала на одно ws (чем больше автобусов, тем больше ставь)",
    )
    parser.add_argument(
        "-v",
        action="count",
        default=0,
        help="уровень подробности логов: -v (info), -vv (debug)",
    )
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="перемешать маршруты перед запуском",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.v)

    with suppress(KeyboardInterrupt):
        trio.run(
            main,
            args.server,
            args.routes_number,
            args.buses_per_route,
            args.websockets_number,
            args.emulator_id,
            args.refresh_timeout,
            args.step_skip,
            args.shuffle,
            args.channel_capacity,
            args.routes_dir,
        )
    logger.info("stopped by user")