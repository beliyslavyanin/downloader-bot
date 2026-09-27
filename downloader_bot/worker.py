"""Код, который выполняется в дочерних процессах ProcessPoolExecutor.

Модуль намеренно не импортирует aiogram и остальные части бота: воркеры
стартуют через spawn/forkserver и импортируют только то, что нужно yt-dlp.
Все исключения, выходящие наружу, должны быть простыми и pickle-совместимыми.
"""

import logging
import os
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError

log = logging.getLogger(__name__)

# Таймаут отдельной сетевой операции. Общий таймаут задачи — через deadline.
_SOCKET_TIMEOUT_SEC = 30
_TEMP_SUFFIXES = (".part", ".ytdl", ".temp", ".tmp")


class YtdlpFailure(Exception):
    """yt-dlp не смог обработать ссылку; аргумент — исходный текст ошибки."""


class DeadlineExceeded(Exception):
    """Истёк общий таймаут задачи."""


class NothingDownloaded(Exception):
    """yt-dlp завершился без файла — так он пропускает видео больше max_filesize."""


class _DeadlineCancel(DownloadCancelled):
    msg = "Deadline exceeded"


class _Logger:
    # Ошибки yt-dlp всё равно пробрасываются исключением и логируются в основном
    # процессе, поэтому здесь их не дублируем.
    def debug(self, msg: str) -> None:
        log.debug(msg)

    def info(self, msg: str) -> None:
        log.debug(msg)

    def warning(self, msg: str) -> None:
        log.warning(msg)

    def error(self, msg: str) -> None:
        log.debug(msg)


# Качество задаётся сортировкой, а не фильтром [height<=N]: у вертикальных видео
# (Reels, Shorts, TikTok) высота 1280+, и фильтр отсекал все форматы с известным
# разрешением, оставляя форматы без метаданных — часто исходник на сотню мегабайт.
# "res" в yt-dlp — меньшая сторона кадра. h264 в mp4 Telegram проигрывает inline везде.
def _format_sort(max_height: int) -> list[str]:
    return [f"res:{max_height}", "vcodec:h264", "ext:mp4:m4a"]


_FORMAT = "bv*+ba/b"

# Запасной вариант, если лучший формат не влез в лимит размера: пониже разрешение
# и самый низкий битрейт. Не "самый маленький файл" — иначе YouTube отдаст 144p.
# Форматы без битрейта исключаем: при сортировке "+br" yt-dlp ставит их первыми,
# а у Instagram это как раз тяжёлые исходники.
_FALLBACK_FORMAT = "bv*[tbr>0]+ba/b[tbr>0]"
_FALLBACK_SORT = ["res:480", "vcodec:h264", "+br", "ext:mp4:m4a"]


def _options(
    max_height: int, format: str = _FORMAT, format_sort: list[str] | None = None, **extra: Any
) -> dict[str, Any]:
    return {
        "format": format,
        "format_sort": format_sort or _format_sort(max_height),
        "merge_output_format": "mp4",
        # Одна ссылка — одно видео: у плейлистов и постов с несколькими видео берём первое.
        "noplaylist": True,
        "playlist_items": "1",
        "socket_timeout": _SOCKET_TIMEOUT_SEC,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 2,
        "quiet": True,
        "noprogress": True,
        "cachedir": False,
        "logger": _Logger(),
        **extra,
    }


@contextmanager
def _cookie_copy(cookies_file: str | None) -> Iterator[dict[str, Any]]:
    """Опции yt-dlp с временной копией файла cookies.

    yt-dlp при закрытии перезаписывает cookiefile, а воркеров несколько — без
    копии параллельные задачи портили бы общий файл одновременной записью.
    """
    if not cookies_file:
        yield {}
        return
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="cookies-")
    os.close(fd)
    try:
        shutil.copyfile(cookies_file, path)
        yield {"cookiefile": path}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _first_entry(info: dict[str, Any] | None) -> dict[str, Any] | None:
    while info and info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        info = entries[0] if entries else None
    return info


def estimate_size(info: dict[str, Any]) -> int | None:
    """Оценка размера итогового файла по метаданным; None — если оценить нельзя."""
    duration = info.get("duration")
    total = 0.0
    for fmt in info.get("requested_formats") or [info]:
        size = fmt.get("filesize") or fmt.get("filesize_approx")
        if not size:
            tbr = fmt.get("tbr")  # кбит/с
            if not (tbr and duration):
                return None
            size = tbr * 1000 / 8 * duration
        total += size
    return int(total)


def probe(url: str, max_height: int, cookies_file: str | None = None) -> dict[str, Any]:
    """Метаданные без скачивания: то, что нужно для проверки лимитов и отправки."""
    try:
        with _cookie_copy(cookies_file) as cookie_opts, yt_dlp.YoutubeDL(_options(max_height, **cookie_opts)) as ydl:
            info = _first_entry(ydl.extract_info(url, download=False))
    except DownloadError as e:
        raise YtdlpFailure(str(e)) from None
    if info is None:
        raise YtdlpFailure("No video formats found")

    duration = info.get("duration")
    return {
        "title": info.get("title") or "",
        "duration": int(duration) if duration else None,
        "width": info.get("width"),
        "height": info.get("height"),
        "is_live": bool(info.get("is_live")) or info.get("live_status") == "is_live",
        "size": estimate_size(info),
    }


def download(
    url: str,
    out_dir: str,
    max_height: int,
    max_filesize: int,
    deadline: float,
    cookies_file: str | None = None,
) -> str:
    """Скачивает видео в out_dir, возвращает путь к файлу.

    deadline — абсолютное время (time.time()). Воркер прерывает себя сам через
    хуки yt-dlp: задачу, уже запущенную в ProcessPoolExecutor, снаружи не отменить.
    """

    def check_deadline(_: dict[str, Any]) -> None:
        if time.time() > deadline:
            raise _DeadlineCancel()

    # Не у всех площадок в метаданных есть размер (Instagram не отдаёт даже
    # длительность), поэтому до скачивания лимит не проверить. Превышение yt-dlp
    # видит по Content-Length и прерывает закачку сразу — тогда пробуем формат полегче.
    for format, format_sort in ((_FORMAT, _format_sort(max_height)), (_FALLBACK_FORMAT, _FALLBACK_SORT)):
        try:
            with _cookie_copy(cookies_file) as cookie_opts:
                opts = _options(
                    max_height,
                    format,
                    format_sort,
                    outtmpl=os.path.join(out_dir, "video.%(ext)s"),
                    max_filesize=max_filesize,
                    progress_hooks=[check_deadline],
                    postprocessor_hooks=[check_deadline],
                    **cookie_opts,
                )
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
        except (DownloadError, DownloadCancelled) as e:
            if time.time() > deadline:
                raise DeadlineExceeded() from None
            raise YtdlpFailure(str(e)) from None

        # Итоговый файл — ровно "video.<ext>". Промежуточные дорожки называются
        # "video.f<id>.<ext>" и остаются, если прервалась вторая из них.
        for entry in os.scandir(out_dir):
            if entry.is_file() and entry.name.count(".") == 1 and not entry.name.endswith(_TEMP_SUFFIXES):
                return entry.path
        _clear_dir(out_dir)
    raise NothingDownloaded()


def _clear_dir(path: str) -> None:
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            shutil.rmtree(entry.path, ignore_errors=True)
        else:
            try:
                os.remove(entry.path)
            except OSError:
                pass
