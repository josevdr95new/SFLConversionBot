import os
import logging
import asyncio
import signal
import sys
from aiohttp import web
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from sfl_bot.config import configure_logging
from sfl_bot.handlers import Handlers
from sfl_bot.web_health import start_web_server

logger = configure_logging()

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
    
    shutdown_event = asyncio.Event()
    
    def signal_handler():
        logger.info("Received shutdown signal")
        shutdown_event.set()
    
    # Manejo de señales multiplataforma
    if sys.platform == "win32":
        signal.signal(signal.SIGINT, lambda s, f: shutdown_event.set())
    else:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

    try:
        logger.info("Starting bot...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        logger.info("Bot is now running. Press Ctrl+C to stop.")
        await shutdown_event.wait()

    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
    finally:
        logger.info("Starting graceful shutdown...")
        try:
            # 1. Detener polling
            if application.updater.running:
                await application.updater.stop()
            
            # 2. Detener servidor web
            await web_site.stop()
            await web_runner.cleanup()
            
            # 3. Apagar aplicación
            await application.stop()
            await application.shutdown()
            
            # 4. Cerrar cliente HTTP
            await application.bot.shutdown()
            
        except Exception as shutdown_error:
            logger.error(f"Error during shutdown: {shutdown_error}", exc_info=True)
        finally:
            logger.info("Shutdown completed")

if __name__ == "__main__":
    asyncio.run(main())