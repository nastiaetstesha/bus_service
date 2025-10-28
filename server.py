# import json
# import trio
# from trio_websocket import serve_websocket, WebSocketRequest, ConnectionClosed


# def _compact_json(dct) -> str:
#     return json.dumps(dct, ensure_ascii=False, separators=(",", ":"))


# async def ws_handler(request: WebSocketRequest):
#     ws = await request.accept()
#     addr = f"{request.remote[0]}:{request.remote[1]}"
#     print(f"[server] client connected: {addr}")
#     try:
#         while True:
#             raw = await ws.get_message()
#             try:
#                 data = json.loads(raw)
#             except json.JSONDecodeError:
#                 # Если прислали не-JSON — игнорируем
#                 continue
#             print(_compact_json(data))
#     except ConnectionClosed:
#         print(f"[server] client disconnected: {addr}")


# async def main():
#     host, port = "127.0.0.1", 8080
#     print(f"[server] listening on ws://{host}:{port}")
#     await serve_websocket(ws_handler, host, port, ssl_context=None)


# if __name__ == "__main__":
#     trio.run(main)
import json
import trio
from trio_websocket import serve_websocket, WebSocketRequest, ConnectionClosed


def _compact_json(dct) -> str:
    return json.dumps(dct, ensure_ascii=False, separators=(",", ":"))


async def ws_handler(request: WebSocketRequest):
    ws = await request.accept()

    # request.remote -> Endpoint(host='127.0.0.1', port=xxxxx)
    try:
        remote = getattr(request, "remote", None)
        if remote is not None:
            addr = f"{remote.host}:{remote.port}"
        else:
            addr = "<unknown>"
    except Exception:
        addr = "<unknown>"

    print(f"[server] client connected: {addr}")
    try:
        while True:
            raw = await ws.get_message()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            print(_compact_json(data))
    except ConnectionClosed:
        print(f"[server] client disconnected: {addr}")

async def main():
    host, port = "127.0.0.1", 8080
    print(f"[server] listening on ws://{host}:{port}")
    await serve_websocket(ws_handler, host, port, ssl_context=None)

if __name__ == "__main__":
    trio.run(main)
