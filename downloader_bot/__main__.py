import asyncio
import logging
import shutil
import sys

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from .config import TELEGRAM_BOT_API_LIMIT_MB, ConfigError, load_config
from .downloader import Downloader, cleanup_stale_jobs
from .handlers import router
from .ratelimit import RateLimiter

log = logging.getLogger("downloader_bot")


async def run() -> None:
    config = load_config()
    if config.max_file_size_mb > TELEGRAM_BOT_API_LIMIT_MB:
        log.warning(
            "MAX_FILE_SIZE_MB=%s exceeds the Bot API limit of %s MB; sending will fail without Local Bot API Server",
            config.max_file_size_mb,
            TELEGRAM_BOT_API_LIMIT_MB,
        )
    if shutil.which("ffmpeg") is None:
        log.warning("ffmpeg not found: videos with separate audio/video streams can't be merged")

    config.temp_dir.mkdir(parents=True, exist_ok=True)
    cleanup_stale_jobs(config.temp_dir)

    downloader = Downloader(config)
    limiter = RateLimiter(
        per_minute=config.rate_limit_per_user_per_min,
        max_active=config.max_active_tasks_per_user,
    )
    bot = Bot(config.bot_token)
    dp = Dispatcher(config=config, downloader=downloader, limiter=limiter)
    dp.include_router(router)

    log.info("Bot started")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        downloader.shutdown()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    load_dotenv()
    try:
        asyncio.run(run())
    except ConfigError as e:
        log.error("Configuration error: %s", e)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
