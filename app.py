import json
import math
import random
import time
import trio
from dataclasses import dataclass
from typing import Optional
from trio_websocket import serve_websocket, ConnectionClosed, WebSocketRequest
from pathlib import Path


ROUTE_FILE = Path("156.json")
BUS_ID = "156A"
ROUTE_NAME = "156"

PERIOD = 0.3
STEP_SKIP = 1 


@dataclass
class Bounds:
    south_lat: float
    north_lat: float
    west_lng: float
    east_lng: float

    def random_point(self):
        lat = random.uniform(self.south_lat, self.north_lat)
        lng = random.uniform(self.west_lng, self.east_lng)
        return lat, lng


def load_route():
    data = json.loads(ROUTE_FILE.read_text(encoding="utf-8"))
    coords = data["coordinates"]      # [[lat, lng], ...]
    points = [{"lat": float(lat), "lng": float(lng)} for lat, lng in coords]
    return points


def make_buses(bounds: Bounds, n=20):
    """Собираем список автобусов, который ждёт фронт:
    {
      "msgType": "Buses",
      "buses": [{"busId": "...", "lat": 55.75, "lng": 37.6, "route": "120"}, ...]
    }
    """
    buses = []
    for i in range(n):
        lat, lng = bounds.random_point()
        bus_id = f"{random.randint(100, 999)}{random.choice('абвгдежз')}{random.choice('абвгдежз')}"
        route = random.choice(["120", "670к", "904", "М10", "М3", "34", "12", "271"])
        buses.append({
            "busId": bus_id,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "route": route,
        })
    return {"msgType": "Buses", "buses": buses}


async def ws_handler(request: WebSocketRequest):
    if request.path != "/ws":
        await request.reject(404)
        return

    ws = await request.accept()
    print("[WS] Client connected")

    points = load_route()
    idx = 0

    try:
        while True:
            p = points[idx]
            payload = {
                "msgType": "Buses",
                "buses": [{
                    "busId": BUS_ID,
                    "lat": round(p["lat"], 6),
                    "lng": round(p["lng"], 6),
                    "route": ROUTE_NAME,
                }]
            }
            await ws.send_message(json.dumps(payload, ensure_ascii=False))

            idx = (idx + STEP_SKIP) % len(points)

            await trio.sleep(PERIOD)
    except Exception as e:
        print(f"[WS] disconnected: {e}")


async def main():
    host, port = "127.0.0.1", 8000
    print(f"[WS] serving on ws://{host}:{port}/ws")
    await serve_websocket(ws_handler, host, port, ssl_context=None)

if __name__ == "__main__":
    trio.run(main)
