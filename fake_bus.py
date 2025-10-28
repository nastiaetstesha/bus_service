import json
import argparse
from pathlib import Path
import trio
from trio_websocket import open_websocket_url


def load_points(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    coords = data["coordinates"]  # [[lat, lng], ...]
    return [{"lat": float(lat), "lng": float(lng)} for lat, lng in coords]


async def main(url: str, route_file: Path, bus_id: str, route: str, period: float, step_skip: int, loop: bool):
    points = load_points(route_file)
    assert points, "Маршрут пуст"

    async with open_websocket_url(url) as ws:
        idx = 0
        while True:
            p = points[idx]
            msg = {
                "busId": bus_id,
                "lat": round(p["lat"], 6),
                "lng": round(p["lng"], 6),
                "route": route,
            }
            await ws.send_message(json.dumps(msg, ensure_ascii=False))
            await trio.sleep(period)

            idx += step_skip
            if idx >= len(points):
                if loop:
                    idx = 0
                else:
                    break


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Имитатор автобуса 156 (ws клиент)")
    ap.add_argument("--url", default="ws://127.0.0.1:8080", help="ws адрес сервера (только ws, не wss)")
    ap.add_argument("--route-file", default="156.json", type=Path, help="файл с coordinates")
    ap.add_argument("--bus-id", default="156-0", help="идентификатор автобуса")
    ap.add_argument("--route", default="156", help="номер маршрута")
    ap.add_argument("--period", type=float, default=0.3, help="пауза между точками, сек")
    ap.add_argument("--step-skip", type=int, default=1, help="брать каждую N-ю точку")
    ap.add_argument("--no-loop", action="store_true", help="не зацикливать маршрут")
    args = ap.parse_args()

    trio.run(
        main,
        args.url, args.route_file, args.bus_id, args.route,
        args.period, args.step_skip, not args.no_loop
    )
