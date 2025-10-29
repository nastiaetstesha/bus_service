import json
import random
import argparse
from pathlib import Path
from typing import List, Dict, Any
import trio
from trio_websocket import open_websocket_url, ConnectionClosed
from itertools import cycle

from load_routes import load_routes


def route_points(route: Dict[str, Any]) -> List[Dict[str, float]]:
    """Приводим координаты к списку словарей {lat, lng}."""
    pts = route["coordinates"]
    return [{"lat": float(lat), "lng": float(lng)} for lat, lng in pts]



async def run_bus(url: str, bus_id: str, route_name: str,
                  points: List[Dict[str, float]],
                  period: float = 0.3, step_skip: int = 1):

    await trio.sleep(random.uniform(0, 0.5))

    def iter_points():
        pts = points[::step_skip] if step_skip > 1 else points
        if len(pts) == 1:
            pts = pts * 2
        return cycle(pts)

    while True:
        try:
            async with open_websocket_url(url) as ws:
                for p in iter_points():
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



async def main(url: str, routes_dir: str, max_routes: int,
               period: float, step_skip: int, shuffle: bool):
    routes = list(load_routes(routes_dir))
    if shuffle:
        random.shuffle(routes)
    if max_routes > 0:
        routes = routes[:max_routes]

    async with trio.open_nursery() as nursery:
        for r in routes:
            name = str(r["name"])
            pts = route_points(r)
            bus_id = f"{name}-0"
            nursery.start_soon(run_bus, url, bus_id, name, pts, period, step_skip)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Имитатор: автобусы по всем маршрутам")
    ap.add_argument("--url", default="ws://127.0.0.1:8080",
                    help="адрес WS сервера (ws, не wss)")
    ap.add_argument("--routes-dir", default="routes",
                    help="папка с JSON-маршрутами")
    ap.add_argument("--max-routes", type=int, default=50,
                    help="сколько маршрутов запускать (0 = все)")
    ap.add_argument("--period", type=float, default=0.3,
                    help="задержка между точками, сек")
    ap.add_argument("--step-skip", type=int, default=1,
                    help="брать каждую N-ю точку маршрута")
    ap.add_argument("--shuffle", action="store_true",
                    help="перемешать порядок маршрутов")
    args = ap.parse_args()

    trio.run(
        main,
        args.url,
        args.routes_dir,
        args.max_routes,
        args.period,
        args.step_skip,
        args.shuffle,
    )
