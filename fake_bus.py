import json
import random
import argparse
from pathlib import Path
from typing import List, Dict, Any
import trio
from trio_websocket import open_websocket_url, ConnectionClosed
from itertools import cycle, islice

from load_routes import load_routes
from functools import partial


def route_points(route: Dict[str, Any]) -> List[Dict[str, float]]:
    """Приводим координаты к списку словарей {lat, lng}."""
    pts = route["coordinates"]
    return [{"lat": float(lat), "lng": float(lng)} for lat, lng in pts]

def generate_bus_id(route_id: str, bus_index: int) -> str:
    return f"{route_id}-{bus_index}"


def build_iterator(points: List[Dict[str, float]], step_skip: int, start_offset: int):
    """Бесконечный итератор по точкам с шагом и стартовым сдвигом."""
    if step_skip < 1:
        step_skip = 1
    base = points[::step_skip] if step_skip > 1 else points
    # если осталась 1 точка — дублируем, чтобы маркер не «застыл»
    if len(base) == 1:
        base = base * 2
    cyc = cycle(base)
    # равномерный сдвиг старта по маршруту
    start_offset = start_offset % len(base)
    return islice(cyc, start_offset, None)


async def run_bus(
    url: str,
    bus_id: str,
    route_name: str,
    points: List[Dict[str, float]],
    *,
    period: float = 0.3,
    step_skip: int = 1,
    start_offset: int = 0,
):
    """Один автобус: отдельное ws-подключение + бесконечная отправка координат."""
    await trio.sleep(random.uniform(0, 0.5))
    while True:
        try:
            async with open_websocket_url(url) as ws:
                it = build_iterator(points, step_skip, start_offset)
                for p in it:
                    msg = {
                        "busId": bus_id,
                        "lat": round(p["lat"], 6),
                        "lng": round(p["lng"], 6),
                        "route": route_name,
                    }
                    await ws.send_message(json.dumps(msg, ensure_ascii=False))
                    await trio.sleep(period)
        except (ConnectionClosed, OSError):
            await trio.sleep(0.3)


async def main(
    url: str,
    routes_dir: str,
    max_routes: int,
    period: float,
    step_skip: int,
    shuffle: bool,
    buses_per_route: int,
):
    routes = list(load_routes(routes_dir))
    if shuffle:
        random.shuffle(routes)
    if max_routes > 0:
        routes = routes[:max_routes]

    async with trio.open_nursery() as nursery:
        for r in routes:
            route_name = str(r["name"])
            pts = route_points(r)

            for i in range(buses_per_route):
                bus_id = generate_bus_id(route_name, i)
                start_offset = (len(pts) * i) // max(1, buses_per_route)

                nursery.start_soon(
                    partial(
                        run_bus,
                        url,
                        bus_id,
                        route_name,
                        pts,
                        period=period,
                        step_skip=step_skip,
                        start_offset=start_offset,
                    )
                )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Имитатор автобусов по всем маршрутам")
    ap.add_argument("--url", default="ws://127.0.0.1:8080", help="адрес WS сервера (ws, не wss)")
    ap.add_argument("--routes-dir", default="routes", help="папка с JSON-маршрутами")
    ap.add_argument("--max-routes", type=int, default=50, help="сколько маршрутов запускать (0 = все)")
    ap.add_argument("--period", type=float, default=0.3, help="задержка между точками, сек")
    ap.add_argument("--step-skip", type=int, default=1, help="брать каждую N-ю точку маршрута")
    ap.add_argument("--shuffle", action="store_true", help="перемешать порядок маршрутов")
    ap.add_argument("--buses-per-route", type=int, default=3, help="сколько автобусов на каждый маршрут")
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
    )