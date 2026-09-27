import pytest

from downloader_bot import texts
from downloader_bot.errors import humanize_ytdlp_error


@pytest.mark.parametrize(
    "message, expected",
    [
        ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", texts.ERR_PRIVATE),
        ("ERROR: [youtube] abc: Video unavailable. This video has been removed by the uploader", texts.ERR_REMOVED),
        ("ERROR: [youtube] abc: The uploader has not made this video available in your country", texts.ERR_GEO),
        ("ERROR: [youtube] abc: Sign in to confirm your age. Use --cookies-from-browser", texts.ERR_AGE),
        ("ERROR: [youtube] abc: Sign in to confirm you're not a bot. Use --cookies", texts.ERR_BOT_CHECK),
        ("ERROR: Unsupported URL: https://t.me/somechannel", texts.ERR_UNSUPPORTED_LINK),
        ("ERROR: [twitter] 1: No video could be found in this tweet", texts.ERR_NO_VIDEO),
        ("ERROR: [Instagram] abc: There is no video in this post", texts.ERR_NO_VIDEO),
        (
            "ERROR: [Instagram] abc: The webpage request was redirected to the login page. You have exceeded "
            "the rate-limit for accessing posts anonymously. Use --cookies-from-browser or --cookies",
            texts.ERR_LOGIN,
        ),
        ("ERROR: Unable to download webpage: HTTP Error 429: Too Many Requests", texts.ERR_THROTTLED),
        ("ERROR: Unable to download webpage: <urlopen error timed out>", texts.ERR_NETWORK),
        ("ERROR: something completely new", texts.ERR_GENERIC),
    ],
)
def test_humanize(message, expected):
    assert humanize_ytdlp_error(message) == expected
