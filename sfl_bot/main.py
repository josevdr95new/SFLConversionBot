import os
import logging
import asyncio
from aiohttp import web
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from sfl_bot.config import configure_logging
from sfl_bot.handlers import Handlers

logger = configure_logging()

async def handle_ping(request: web.Request) -> web.Response:
    return web.Response(text="🏓 pong\nBot status: operational")

async def start_web_server(port: int = 8000):
    app = web.Application()
    app.router.add_get('/ping', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=port)
    await site.start()
    logger.info(f"Web server started on port {port}")
    return runner, site

def setup_application() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("Token not found. Configure TELEGRAM_BOT_TOKEN in .env")
        raise ValueError("Telegram token not provided")

    bot = Handlers()
    application = Application.builder().token(token).post_shutdown(bot.shutdown).build()
    
    application.add_handlers([
        CommandHandler("start", bot.handle_start),
        CommandHandler("help", bot.handle_help),
        CommandHandler("status", bot.handle_status),
        MessageHandler(filters.COMMAND & ~filters.Regex(r"^/(start|help|status)$"), bot.handle_item)
    ])
    
    application.add_error_handler(bot.error_handler)
    return application

async def main() -> None:
    application = setup_application()
    web_runner, web_site = await start_web_server()
    
    try:
        logger.info("Starting bot...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()  # Si usas webhooks, cambia esto
        
        # Mantener la ejecución indefinidamente
        while True:
            await asyncio.sleep(3600)
            
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
        await web_site.stop()
        await web_runner.cleanup()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    asyncio.run(main())