import logging
import time

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramEntityTooLarge
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message, ReplyParameters

from . import texts
from .config import Config
from .downloader import Downloader, VideoInfo, job_directory
from .errors import UserFacingError
from .ratelimit import RateLimiter
from .urls import extract_urls, pick_supported_url

log = logging.getLogger(__name__)

_CAPTION_LIMIT = 200

router = Router()
# В группах бот иначе реагировал бы на каждое сообщение со ссылкой.
router.message.filter(F.chat.type == ChatType.PRIVATE)


class StatusMessage:
    """Одно статус-сообщение, которое редактируется по ходу обработки."""

    def __init__(self, message: Message) -> None:
        self._message = message
        self._text = message.text

    @classmethod
    async def send(cls, reply_to: Message, text: str) -> "StatusMessage":
        return cls(await reply_to.reply(text))

    async def set(self, text: str) -> None:
        if text == self._text:
            return
        try:
            await self._message.edit_text(text)
            self._text = text
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                log.warning("Failed to update status: %s", e)
        except TelegramAPIError as e:
            # Например, пользователь заблокировал бота — обработку это не должно ронять.
            log.warning("Failed to update status: %s", e)


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_start(message: Message, config: Config) -> None:
    await message.answer(texts.START.format(max_mb=config.max_file_size_mb))


@router.message(F.text | F.caption)
async def on_text(
    message: Message,
    bot: Bot,
    config: Config,
    downloader: Downloader,
    limiter: RateLimiter,
) -> None:
    text = message.text or message.caption or ""
    urls = extract_urls(text, message.entities or message.caption_entities)
    if not urls:
        await message.reply(texts.NOT_A_LINK)
        return
    url = pick_supported_url(urls)
    if url is None:
        await message.reply(texts.UNSUPPORTED)
        return

    user_id = message.from_user.id if message.from_user else message.chat.id
    denied = limiter.try_acquire(user_id)
    if denied:
        if denied.already_active:
            await message.reply(texts.ALREADY_ACTIVE)
        else:
            await message.reply(texts.RATE_LIMITED.format(seconds=denied.retry_after_sec))
        return

    try:
        if len(urls) > 1:
            await message.answer(texts.MULTIPLE_LINKS)
        await process_link(message, url, bot, config, downloader)
    finally:
        limiter.release(user_id)


@router.message()
async def on_other(message: Message) -> None:
    await message.reply(texts.NOT_TEXT)


async def process_link(message: Message, url: str, bot: Bot, config: Config, downloader: Downloader) -> None:
    log.info("Job start: user=%s url=%s", message.chat.id, url)
    status = await StatusMessage.send(message, texts.ACCEPTED)
    try:
        if downloader.is_busy:
            await status.set(texts.QUEUED)
        async with downloader.slot:
            # Время ожидания в очереди в таймаут не входит.
            deadline = time.time() + config.download_timeout_sec
            await status.set(texts.PROBING)
            info = await downloader.probe(url, deadline)
            check_limits(info, config)

            await status.set(texts.DOWNLOADING)
            with job_directory(config.temp_dir) as job_dir:
                path = await downloader.download(url, job_dir, deadline)
                if path.stat().st_size > config.max_file_size_bytes:
                    raise UserFacingError(texts.TOO_BIG_UNKNOWN.format(max_mb=config.max_file_size_mb))
                await status.set(texts.UPLOADING)
                await send_video(message, path, info, bot, config)
        await status.set(texts.DONE)
        log.info("Job done: user=%s url=%s", message.chat.id, url)
    except UserFacingError as e:
        log.info("Job rejected: user=%s url=%s reason=%r", message.chat.id, url, str(e))
        await status.set(str(e))
    except Exception:
        log.exception("Job failed: user=%s url=%s", message.chat.id, url)
        await status.set(texts.UNKNOWN_ERROR)


def check_limits(info: VideoInfo, config: Config) -> None:
    if info.is_live:
        raise UserFacingError(texts.LIVE)
    if info.duration and info.duration > config.max_duration_sec:
        raise UserFacingError(
            texts.TOO_LONG.format(
                duration=texts.format_duration(info.duration),
                max_duration=texts.format_duration(config.max_duration_sec),
            )
        )
    if info.size and info.size > config.max_file_size_bytes:
        raise UserFacingError(
            texts.TOO_BIG.format(
                size_mb=round(info.size / 1024 / 1024),
                max_mb=config.max_file_size_mb,
            )
        )


async def send_video(message: Message, path, info: VideoInfo, bot: Bot, config: Config) -> None:
    caption = info.title
    if len(caption) > _CAPTION_LIMIT:
        caption = caption[: _CAPTION_LIMIT - 1] + "…"
    try:
        await bot.send_video(
            chat_id=message.chat.id,
            video=FSInputFile(path, filename=f"video{path.suffix}"),
            caption=caption or None,
            parse_mode=None,
            duration=info.duration,
            width=info.width,
            height=info.height,
            supports_streaming=True,
            reply_parameters=ReplyParameters(message_id=message.message_id, allow_sending_without_reply=True),
            request_timeout=config.upload_timeout_sec,
        )
    except TelegramEntityTooLarge:
        raise UserFacingError(texts.TOO_BIG_UNKNOWN.format(max_mb=config.max_file_size_mb)) from None
    except TelegramAPIError as e:
        log.warning("Failed to send video: %s", e)
        raise UserFacingError(texts.SEND_FAILED) from None
