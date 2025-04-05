import os
import logging
import asyncio
from aiohttp import web
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from sfl_bot.config import configure_logging
from sfl_bot.handlers import Handlers
from sfl_bot.web_health import start_web_server  # Servidor web separado

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
    web_runner, web_site = await start_web_server()  # Inicia servidor web desde web_health.py
    
    try:
        logger.info("Starting bot...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()  # Modo polling (alternativa a webhooks)
        
        # Mantener la ejecución activa
        while True:
            await asyncio.sleep(3600)
            
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
        await web_site.stop()          # Detener servidor web
        await web_runner.cleanup()     # Limpiar recursos
        await application.stop()       # Detener bot de Telegram
        await application.shutdown()   # Apagado final

if __name__ == "__main__":
    asyncio.run(main())