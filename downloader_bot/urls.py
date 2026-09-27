import re
from collections.abc import Iterable
from urllib.parse import urlsplit

from aiogram.types import MessageEntity

# Домен → платформа. Поддомены (www., m., vm. и т.п.) матчатся автоматически.
SUPPORTED_DOMAINS = {
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "tiktok.com": "TikTok",
    "instagram.com": "Instagram",
    "x.com": "X",
    "twitter.com": "X",
    "vk.com": "VK",
    "vk.ru": "VK",
    "vkvideo.ru": "VK",
    "t.me": "Telegram",
    "telegram.me": "Telegram",
}

_MAX_URL_LENGTH = 2048
_FALLBACK_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def extract_urls(text: str, entities: Iterable[MessageEntity] | None) -> list[str]:
    """Ссылки из сообщения в порядке появления.

    Telegram сам размечает ссылки (в т.ч. без схемы, вида "youtu.be/xxx") и скрытые
    ссылки под текстом — берём их из entities, а regex оставляем как запасной вариант.
    """
    urls: list[str] = []
    for entity in entities or ():
        if entity.type == "url":
            urls.append(entity.extract_from(text))
        elif entity.type == "text_link" and entity.url:
            urls.append(entity.url)
    if not urls:
        urls = _FALLBACK_URL_RE.findall(text)
    return [u.strip() for u in urls if u.strip()]


def normalize_url(raw: str) -> str | None:
    """Добавляет схему, проверяет формат. None — если это не http(s)-ссылка."""
    url = raw.strip()
    if len(url) > _MAX_URL_LENGTH:
        return None
    if "://" not in url:
        url = "https://" + url
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    return url


def detect_platform(url: str) -> str | None:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower().rstrip(".")
    for domain, platform in SUPPORTED_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return platform
    return None


def pick_supported_url(urls: list[str]) -> str | None:
    """Первая ссылка на поддерживаемую площадку (уже нормализованная)."""
    for raw in urls:
        url = normalize_url(raw)
        if url and detect_platform(url):
            return url
    return None
