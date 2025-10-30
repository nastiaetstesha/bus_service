import json
import logging
import trio
from trio_websocket import serve_websocket, ConnectionClosed, WebSocketRequest


logger = logging.getLogger("server")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s:%(name)s:%(message)s",
)

logging.getLogger("trio_websocket").setLevel(logging.WARNING)
logging.getLogger("wsproto").setLevel(logging.WARNING)


buses: dict[str, dict] = {}


def jdump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def remote_addr(request: WebSocketRequest) -> str:
    """
    Возвращаем адрес клиента так, чтобы он НИКОГДА не ронял сервер.
    В trio_websocket тут может быть Endpoint, tuple или вообще None.
    """
    r = getattr(request, "remote", None)
    if r is None:
        return "unknown"

    # бывает, что это tuple вида ('127.0.0.1', 55555)
    if isinstance(r, tuple) and len(r) == 2:
        return f"{r[0]}:{r[1]}"

    return str(r)



# ----- обработчик автобусов (8080) 
async def handle_bus(request: WebSocketRequest):
    addr = remote_addr(request)
    logger.info("[8080] bus connected %s path=%s", addr, request.path)
    try:
        ws = await request.accept()
        while True:
            msg = await ws.get_message()
            data = json.loads(msg)
            buses[data["busId"]] = data
    except ConnectionClosed:
        logger.info("[8080] bus disconnected %s", addr)



#  слушатель браузера 
async def listen_browser(ws):
    while True:
        try:
            msg = await ws.get_message()
        except ConnectionClosed:
            break

        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            logger.debug("got non-json from browser: %r", msg)
            continue

        if data.get("msgType") == "newBounds":
            logger.debug(json.dumps(data, ensure_ascii=False))
        else:
            logger.debug("browser msg: %s", data)



#  отправитель в браузер 
async def talk_to_browser(ws):
    while True:
        snapshot = {
            "msgType": "Buses",
            "buses": list(buses.values()),
        }
        try:
            await ws.send_message(json.dumps(snapshot, ensure_ascii=False))
        except ConnectionClosed:
            break
        await trio.sleep(1)



# -- обработчик браузера (8000)
async def handle_browser(request):
    ws = await request.accept()
    async with trio.open_nursery() as nursery:
        nursery.start_soon(listen_browser, ws)
        nursery.start_soon(talk_to_browser, ws)

# async def handle_browser(request: WebSocketRequest):
#     addr = remote_addr(request)
#     logger.info("[8000] browser connected %s path=%s", addr, request.path)

#     # if request.path != "/ws":
#     #     logger.warning("browser connected to unexpected path %s", request.path)

#     ws = await request.accept()

#     async with trio.open_nursery() as nursery:
#         nursery.start_soon(listen_browser, ws)
#         nursery.start_soon(talk_to_browser, ws)

#     logger.info("[8000] browser disconnected %s", addr)


#  ---- запуск двух серверов 
async def run_server(handler, host: str, port: int):
    logger.info("listening on ws://%s:%s", host, port)
    await serve_websocket(handler, host, port, ssl_context=None)


async def main():
    async with trio.open_nursery() as nursery:
        nursery.start_soon(run_server, handle_bus, "127.0.0.1", 8080)
        nursery.start_soon(run_server, handle_browser, "127.0.0.1", 8000)


if __name__ == "__main__":
    try:
        trio.run(main)
    except KeyboardInterrupt:
        logger.info("stopped by user")

