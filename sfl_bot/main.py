import os
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from sfl_bot.config import configure_logging
from sfl_bot.handlers import Handlers

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

def main() -> None:
    try:
        application = setup_application()
        logger.info("Starting bot...")
        application.run_polling()
    except Exception as e:
        logger.critical(f"Error starting bot: {e}")
        raise

if __name__ == "__main__":
    main()