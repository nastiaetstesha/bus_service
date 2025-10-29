import json
import random
import argparse
from typing import List, Dict, Any
from itertools import cycle, islice
from functools import partial

import trio
from trio import ClosedResourceError
from trio_websocket import open_websocket_url, ConnectionClosed

from load_routes import load_routes


# ------ утилиты маршрута 
def route_points(route: Dict[str, Any]) -> List[Dict[str, float]]:
    return [{"lat": float(lat), "lng": float(lng)} for lat, lng in route["coordinates"]]


def generate_bus_id(route_id: str, bus_index: int) -> str:
    return f"{route_id}-{bus_index}"


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
    await trio.sleep(random.uniform(0, 0.5))  # рассинхронизируем старт
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
async def send_updates(url: str, recv_ch: trio.MemoryReceiveChannel):
    while True:
        try:
            async with open_websocket_url(url) as ws:
                async with recv_ch:
                    async for msg in recv_ch:
                        await ws.send_message(json.dumps(msg, ensure_ascii=False))
        except (ConnectionClosed, OSError):
            await trio.sleep(0.3)


# --------- main ----
async def main(
    url: str,
    routes_dir: str,
    max_routes: int,
    period: float,
    step_skip: int,
    shuffle: bool,
    buses_per_route: int,
    num_sockets: int,
    channel_capacity: int,
):
    routes = list(load_routes(routes_dir))
    if shuffle:
        random.shuffle(routes)
    if max_routes > 0:
        routes = routes[:max_routes]

    send_channels: list[trio.MemorySendChannel] = []
    async with trio.open_nursery() as nursery:
        for _ in range(max(1, num_sockets)):
            send_ch, recv_ch = trio.open_memory_channel(channel_capacity)
            send_channels.append(send_ch)
            nursery.start_soon(send_updates, url, recv_ch)

        for route in routes:
            route_name = str(route["name"])
            pts = route_points(route)

            for i in range(buses_per_route):
                bus_id = generate_bus_id(route_name, i)
                start_offset = (len(pts) * i) // max(1, buses_per_route)
                send_ch = random.choice(send_channels)

                nursery.start_soon(
                    partial(
                        run_bus,
                        send_ch,
                        bus_id,
                        route_name,
                        pts,
                        period=period,
                        step_skip=step_skip,
                        start_offset=start_offset,
                    )
                )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Имитатор автобусов c каналами Trio")
    ap.add_argument("--url", default="ws://127.0.0.1:8080", help="адрес WS сервера (ws, не wss)")
    ap.add_argument("--routes-dir", default="routes", help="папка с JSON-маршрутами")
    ap.add_argument("--max-routes", type=int, default=200, help="сколько маршрутов запускать (0 = все)")
    ap.add_argument("--period", type=float, default=0.25, help="задержка между точками, сек")
    ap.add_argument("--step-skip", type=int, default=2, help="брать каждую N-ю точку маршрута")
    ap.add_argument("--shuffle", action="store_true", help="перемешать порядок маршрутов")
    ap.add_argument("--buses-per-route", type=int, default=5, help="сколько автобусов на каждый маршрут")
    ap.add_argument("--num-sockets", type=int, default=8, help="сколько WS-соединений открыть")
    ap.add_argument("--channel-capacity", type=int, default=2000, help="буфер канала на одно соединение")
    args = ap.parse_args()

    trio.run(
        main,
        args.url,
        args.routes_dir,
        args.max_routes,
        args.period,
        args.step_skip,
        args.shuffle,
        args.buses_per_route,
        args.num_sockets,
        args.channel_capacity,
    )
