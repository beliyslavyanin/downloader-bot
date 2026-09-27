from . import texts


class UserFacingError(Exception):
    """Ошибка, текст которой можно показать пользователю как есть."""


# Порядок важен: сообщения yt-dlp часто содержат несколько маркеров сразу
# (например, возрастное ограничение упоминает cookies), поэтому более
# специфичные шаблоны идут раньше общих.
_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("private video", "video is private", "this account is private", "is private"), texts.ERR_PRIVATE),
    (
        (
            "not available in your country",
            "not available from your location",
            "geo restrict",
            "geo-restrict",
            "blocked in your country",
            "not made this video available in your country",
        ),
        texts.ERR_GEO,
    ),
    (("confirm your age", "age-restricted", "age restricted", "inappropriate for some users"), texts.ERR_AGE),
    (("not a bot",), texts.ERR_BOT_CHECK),
    (("premieres in", "live event will begin", "this live event", "is_upcoming"), texts.ERR_NOT_STARTED),
    (
        (
            "video unavailable",
            "video is unavailable",
            "has been removed",
            "been deleted",
            "no longer available",
            "does not exist",
            "post is unavailable",
            "http error 404",
            "not found",
        ),
        texts.ERR_REMOVED,
    ),
    (
        ("login required", "log in", "login to", "sign in", "requires authentication", "cookies"),
        texts.ERR_LOGIN,
    ),
    (
        (
            "no video could be found",
            "no video formats found",
            "no media found",
            "there's no video",
            "there is no video",
            "requested format is not available",
        ),
        texts.ERR_NO_VIDEO,
    ),
    (("unsupported url",), texts.ERR_UNSUPPORTED_LINK),
    (("http error 429", "too many requests", "rate limit", "rate-limit"), texts.ERR_THROTTLED),
    (
        (
            "timed out",
            "timeout",
            "connection",
            "network is unreachable",
            "name resolution",
            "getaddrinfo",
            "remote end closed",
            "ssl",
        ),
        texts.ERR_NETWORK,
    ),
]


def humanize_ytdlp_error(message: str) -> str:
    lowered = message.lower()
    for markers, text in _PATTERNS:
        if any(marker in lowered for marker in markers):
            return text
    return texts.ERR_GENERIC
