"""Local HTTP + WebSocket server the UI talks to (127.0.0.1 only)."""

from __future__ import annotations

import asyncio
import logging

from aiohttp import WSMsgType, web

from phonelink.cast.manager import CastManager
from phonelink.paths import UI_DIR

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 47321


def build_app(manager: CastManager) -> web.Application:
    app = web.Application()
    routes = web.RouteTableDef()

    @routes.get("/")
    async def index(_request: web.Request) -> web.FileResponse:
        return web.FileResponse(UI_DIR / "index.html", headers={"Cache-Control": "no-store"})

    @routes.get("/api/state")
    async def state(_request: web.Request) -> web.Response:
        return web.json_response(manager.snapshot())

    @routes.post("/api/cast/start")
    async def cast_start(request: web.Request) -> web.Response:
        body = await request.json() if request.can_read_body else {}
        return web.json_response(await asyncio.to_thread(manager.start, body.get("device")))

    @routes.post("/api/cast/stop")
    async def cast_stop(_request: web.Request) -> web.Response:
        return web.json_response(await asyncio.to_thread(manager.stop))

    @routes.get("/ws")
    async def media(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(max_msg_size=0, compress=False)
        await ws.prepare(request)
        loop = asyncio.get_running_loop()
        # Latest-wins for video when a viewer falls behind: a bounded queue,
        # dropped back to the next keyframe rather than growing latency.
        queue: asyncio.Queue = asyncio.Queue(maxsize=240)

        def push(message) -> None:
            def put() -> None:
                if queue.full():
                    # Keep state/config text; the player resyncs at the next keyframe.
                    kept = [m for m in (queue.get_nowait() for _ in range(queue.qsize())) if isinstance(m, str)]
                    for m in kept:
                        queue.put_nowait(m)
                queue.put_nowait(message)

            loop.call_soon_threadsafe(put)

        manager.add_listener(push)

        async def sender() -> None:
            while True:
                message = await queue.get()
                if isinstance(message, str):
                    await ws.send_str(message)
                else:
                    await ws.send_bytes(message)

        task = asyncio.create_task(sender())
        try:
            async for msg in ws:
                if msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            manager.remove_listener(push)
            task.cancel()
        return ws

    app.add_routes(routes)
    app.router.add_static("/ui/", UI_DIR, show_index=False)
    return app


def serve_forever(manager: CastManager, ready=None) -> None:
    """Run the server on the calling thread (its own event loop)."""

    async def main() -> None:
        runner = web.AppRunner(build_app(manager), access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, HOST, PORT)
        await site.start()
        if ready is not None:
            ready.set()
        await asyncio.Event().wait()

    asyncio.run(main())
