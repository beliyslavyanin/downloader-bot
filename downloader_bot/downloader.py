import asyncio
import logging
import shutil
import tempfile
import time
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import texts, worker
from .config import Config
from .errors import UserFacingError, humanize_ytdlp_error

log = logging.getLogger(__name__)

_JOB_DIR_PREFIX = "job-"
# Воркер сам прерывается по deadline; внешний таймаут чуть больше, чтобы он успел
# остановиться до удаления временной директории. Срабатывает, только если воркер завис.
_WORKER_GRACE_SEC = 30


@dataclass(frozen=True)
class VideoInfo:
    title: str
    duration: int | None
    width: int | None
    height: int | None
    is_live: bool
    size: int | None


class Downloader:
    """Семафор + пул процессов для yt-dlp.

    yt-dlp блокирующий и местами CPU-bound (парсинг, мерж через ffmpeg), поэтому
    работает в отдельных процессах, а не в event loop и не в потоках (GIL).
    Семафор ограничивает число одновременных задач на всю VPS и позволяет
    сказать пользователю, что он в очереди.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrent_downloads)
        self._pool = self._new_pool()

    def _new_pool(self) -> ProcessPoolExecutor:
        return ProcessPoolExecutor(max_workers=self._config.max_concurrent_downloads)

    @property
    def is_busy(self) -> bool:
        return self._semaphore.locked()

    @property
    def _cookies(self) -> str | None:
        return str(self._config.cookies_file) if self._config.cookies_file else None

    @property
    def slot(self) -> asyncio.Semaphore:
        return self._semaphore

    async def probe(self, url: str, deadline: float) -> VideoInfo:
        data = await self._run(deadline, worker.probe, url, self._config.max_video_height, self._cookies)
        return VideoInfo(**data)

    async def download(self, url: str, out_dir: Path, deadline: float) -> Path:
        path = await self._run(
            deadline,
            worker.download,
            url,
            str(out_dir),
            self._config.max_video_height,
            self._config.max_file_size_bytes,
            deadline,
            self._cookies,
        )
        return Path(path)

    async def _run(self, deadline: float, fn, *args):
        remaining = deadline - time.time()
        if remaining <= 0:
            raise UserFacingError(texts.TIMEOUT)

        pool = self._pool
        future = asyncio.get_running_loop().run_in_executor(pool, fn, *args)
        try:
            return await asyncio.wait_for(future, remaining + _WORKER_GRACE_SEC)
        except (TimeoutError, worker.DeadlineExceeded):
            log.info("Timeout: %s%r", fn.__name__, args[:1])
            raise UserFacingError(texts.TIMEOUT) from None
        except worker.YtdlpFailure as e:
            log.info("yt-dlp failed for %s: %s", args[0], e)
            raise UserFacingError(humanize_ytdlp_error(str(e))) from None
        except worker.NothingDownloaded:
            raise UserFacingError(texts.TOO_BIG_UNKNOWN.format(max_mb=self._config.max_file_size_mb)) from None
        except BrokenProcessPool:
            # Воркер упал (OOM и т.п.) — пул больше не принимает задачи, пересоздаём.
            log.exception("Process pool is broken, restarting")
            if self._pool is pool:
                pool.shutdown(wait=False, cancel_futures=True)
                self._pool = self._new_pool()
            raise UserFacingError(texts.UNKNOWN_ERROR) from None

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


@contextmanager
def job_directory(base: Path) -> Iterator[Path]:
    """Уникальная временная директория задачи, удаляется в любом случае."""
    path = Path(tempfile.mkdtemp(prefix=_JOB_DIR_PREFIX, dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
        if path.exists():
            log.warning("Failed to remove temp dir %s", path)


def cleanup_stale_jobs(base: Path) -> None:
    """Удаляет директории задач, оставшиеся после падения процесса."""
    for path in base.glob(_JOB_DIR_PREFIX + "*"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            log.info("Removed stale temp dir %s", path)
