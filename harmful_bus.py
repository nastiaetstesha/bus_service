import json
import argparse
import trio
from trio_websocket import open_websocket_url


async def main(url: str):
    async with open_websocket_url(url) as ws:
        await ws.send_message("not a json")
        resp = await ws.get_message()
        print("Response:", resp)

        bad_no_busid = {
            "lat": 55.75,
            "lng": 37.61,
            "route": "132",
        }
        await ws.send_message(json.dumps(bad_no_busid))
        resp = await ws.get_message()
        print("Response:", resp)

        bad_no_lat = {
            "busId": "test-bad",
            "lng": 37.61,
            "route": "132",
        }
        await ws.send_message(json.dumps(bad_no_lat))
        resp = await ws.get_message()
        print("Response:", resp)

        good = {
            "busId": "test-good",
            "lat": 55.751244,
            "lng": 37.618423,
            "route": "132",
        }
        await ws.send_message(json.dumps(good))

        with trio.move_on_after(1):
            resp = await ws.get_message()
            print("Response:", resp)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--server",
        default="ws://127.0.0.1:8080",
        help="ws сервер, куда шлём «сломанный» автобус",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    trio.run(main, args.server)
