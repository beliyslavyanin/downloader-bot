from aiogram.types import MessageEntity

from downloader_bot.urls import detect_platform, extract_urls, normalize_url, pick_supported_url


def test_extract_from_entities_with_utf16_offsets():
    text = "😀 глянь youtu.be/abc"
    offset = len("😀 глянь ".encode("utf-16-le")) // 2
    entity = MessageEntity(type="url", offset=offset, length=len("youtu.be/abc"))
    assert extract_urls(text, [entity]) == ["youtu.be/abc"]


def test_extract_text_link():
    entity = MessageEntity(type="text_link", offset=0, length=3, url="https://x.com/a/status/1")
    assert extract_urls("тут", [entity]) == ["https://x.com/a/status/1"]


def test_extract_fallback_regex():
    assert extract_urls("see https://vk.com/video1_2 ok", None) == ["https://vk.com/video1_2"]


def test_no_urls():
    assert extract_urls("привет", None) == []


def test_normalize():
    assert normalize_url("youtu.be/abc") == "https://youtu.be/abc"
    assert normalize_url("ftp://youtube.com/x") is None
    assert normalize_url("file:///etc/passwd") is None
    assert normalize_url("https://" + "a" * 3000) is None


def test_detect_platform():
    assert detect_platform("https://www.youtube.com/watch?v=1") == "YouTube"
    assert detect_platform("https://m.youtube.com/watch?v=1") == "YouTube"
    assert detect_platform("https://vm.tiktok.com/abc") == "TikTok"
    assert detect_platform("https://www.instagram.com/reel/abc/") == "Instagram"
    assert detect_platform("https://twitter.com/a/status/1") == "X"
    assert detect_platform("https://t.me/channel/123") == "Telegram"
    assert detect_platform("https://vkvideo.ru/video-1_2") == "VK"
    assert detect_platform("https://evil-youtube.com/x") is None
    assert detect_platform("https://youtube.com.evil.org/x") is None
    assert detect_platform("https://example.com") is None


def test_pick_first_supported():
    assert pick_supported_url(["https://example.com", "tiktok.com/@a/video/1"]) == "https://tiktok.com/@a/video/1"
    assert pick_supported_url(["https://example.com"]) is None
