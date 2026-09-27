import os

from downloader_bot.worker import _cookie_copy, estimate_size


def test_estimate_merged_formats():
    info = {"duration": 10, "requested_formats": [{"filesize": 1000}, {"filesize_approx": 500}]}
    assert estimate_size(info) == 1500


def test_estimate_from_bitrate():
    assert estimate_size({"duration": 8, "tbr": 1000}) == 1_000_000


def test_estimate_unknown():
    assert estimate_size({"duration": None}) is None


def test_cookie_copy_none():
    with _cookie_copy(None) as opts:
        assert opts == {}


def test_cookie_copy_uses_temp_copy_and_cleans_up(tmp_path):
    original = tmp_path / "cookies.txt"
    original.write_text("# Netscape HTTP Cookie File\n")
    with _cookie_copy(str(original)) as opts:
        copy = opts["cookiefile"]
        assert copy != str(original)
        with open(copy, "w") as f:
            f.write("overwritten")
    assert not os.path.exists(copy)
    assert original.read_text() == "# Netscape HTTP Cookie File\n"
