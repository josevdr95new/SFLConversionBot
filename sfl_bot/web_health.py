import logging
from aiohttp import web
from .config import configure_logging

logger = configure_logging()

async def handle_ping(request: web.Request) -> web.Response:
    return web.Response(text="🏓 pong\nBot status: operational")

async def start_web_server(port: int = 8000) -> tuple[web.AppRunner, web.TCPSite]:
    app = web.Application()
    app.router.add_get('/ping', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=port)
    await site.start()
    logger.info(f"Web server started on port {port}")
    return runner, site