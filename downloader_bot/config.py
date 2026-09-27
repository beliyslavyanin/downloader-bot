import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Лимит обычного Bot API; больше — только через Local Bot API Server.
TELEGRAM_BOT_API_LIMIT_MB = 50


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    bot_token: str
    max_concurrent_downloads: int
    max_file_size_mb: int
    max_duration_sec: int
    max_video_height: int
    download_timeout_sec: int
    upload_timeout_sec: int
    rate_limit_per_user_per_min: int
    max_active_tasks_per_user: int
    temp_dir: Path
    cookies_file: Path | None

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} должно быть целым числом, получено {raw!r}") from None
    if value < 1:
        raise ConfigError(f"{name} должно быть больше нуля, получено {value}")
    return value


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError("Не задана переменная окружения BOT_TOKEN")

    temp_dir = os.getenv("TEMP_DIR", "").strip()
    cookies_file = os.getenv("COOKIES_FILE", "").strip()
    if cookies_file and not Path(cookies_file).is_file():
        raise ConfigError(f"COOKIES_FILE: файл не найден: {cookies_file}")
    return Config(
        bot_token=token,
        max_concurrent_downloads=_int_env("MAX_CONCURRENT_DOWNLOADS", 3),
        max_file_size_mb=_int_env("MAX_FILE_SIZE_MB", TELEGRAM_BOT_API_LIMIT_MB),
        max_duration_sec=_int_env("MAX_DURATION_SEC", 3600),
        max_video_height=_int_env("MAX_VIDEO_HEIGHT", 720),
        download_timeout_sec=_int_env("DOWNLOAD_TIMEOUT_SEC", 300),
        upload_timeout_sec=_int_env("UPLOAD_TIMEOUT_SEC", 300),
        rate_limit_per_user_per_min=_int_env("RATE_LIMIT_PER_USER_PER_MIN", 5),
        max_active_tasks_per_user=_int_env("MAX_ACTIVE_TASKS_PER_USER", 1),
        temp_dir=Path(temp_dir) if temp_dir else Path(tempfile.gettempdir()) / "downloader-bot",
        cookies_file=Path(cookies_file) if cookies_file else None,
    )
