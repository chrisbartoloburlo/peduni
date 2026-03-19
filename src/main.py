import asyncio
import logging
import os

import uvicorn
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from .config import settings
from .db import init_db
from .handlers.documents import handle_document
from .handlers.onboarding import start, settings
from .handlers.queries import handle_text
from .web import web_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    await init_db()
    logger.info("Database initialised")

    # Telegram bot
    bot = ApplicationBuilder().token(settings.telegram_token).build()
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CommandHandler("settings", settings))
    bot.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_document))
    bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    await bot.initialize()
    await bot.start()
    await bot.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram bot polling started")

    # FastAPI (OAuth callback)
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(web_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    logger.info("Starting web server on :8000")
    await server.serve()

    # Graceful shutdown
    await bot.updater.stop()
    await bot.stop()
    await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
