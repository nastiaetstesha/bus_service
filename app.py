import json
import math
import random
import time
import trio
from dataclasses import dataclass
from typing import Optional
from trio_websocket import serve_websocket, ConnectionClosed, WebSocketRequest


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

    bounds: Optional[Bounds] = Bounds(
        south_lat=55.70, north_lat=55.80,
        west_lng=37.55, east_lng=37.65
    )

    async with trio.open_nursery() as nursery:
        async def receiver():
            nonlocal bounds
            try:
                while True:
                    msg = await ws.get_message()
                    try:
                        data = json.loads(msg)
                    except json.JSONDecodeError:
                        continue

                    if data.get("msgType") == "newBounds":
                        d = data.get("data") or {}
                        try:
                            bounds = Bounds(
                                south_lat=float(d["south_lat"]),
                                north_lat=float(d["north_lat"]),
                                west_lng=float(d["west_lng"]),
                                east_lng=float(d["east_lng"]),
                            )
                            print(f"[WS] newBounds: {bounds}")
                        except (KeyError, ValueError, TypeError):
                            pass
                    else:

                        pass
            except ConnectionClosed:
                print("[WS] Client disconnected (receiver)")

        async def sender():
            try:
                while True:
                    if bounds:
                        payload = make_buses(bounds, n=25)
                        await ws.send_message(json.dumps(payload, ensure_ascii=False))
                    await trio.sleep(0.5)
            except ConnectionClosed:
                print("[WS] Client disconnected (sender)")

        nursery.start_soon(receiver)
        nursery.start_soon(sender)


async def main():
    host = "127.0.0.1"
    port = 8000
    print(f"[WS] Serving on ws://{host}:{port}/ws")
    await serve_websocket(ws_handler, host, port, ssl_context=None)

if __name__ == "__main__":
    trio.run(main)
