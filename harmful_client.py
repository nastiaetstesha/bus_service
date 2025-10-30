import json
import trio
from trio_websocket import open_websocket_url


async def main():
    url = "ws://127.0.0.1:8000/ws"
    async with open_websocket_url(url) as ws:
        await ws.send_message("not a json")
        print("sent: not a json")
        print("response:", await ws.get_message())

        await ws.send_message(json.dumps({"hello": "world"}))
        print("sent: no msgType")
        print("response:", await ws.get_message())

        await ws.send_message(json.dumps({"msgType": "Ping"}))
        print("sent: bad msgType")
        print("response:", await ws.get_message())

        good = {
            "msgType": "newBounds",
            "data": {
                "south_lat": 55.7,
                "north_lat": 55.8,
                "west_lng": 37.5,
                "east_lng": 37.7,
            },
        }
        await ws.send_message(json.dumps(good))
        print("sent: good bounds")

        print("buses:", await ws.get_message())


if __name__ == "__main__":
    trio.run(main)
