from pathlib import Path
from bs4 import BeautifulSoup

from instavault.parser import (
    parse_export_header,
    parse_media_cards,
    parse_social_connections,
    normalize_timestamp,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_normalize_timestamp():
    assert normalize_timestamp("Aug 20, 2026 8:33 am") == "2026-08-20 08:33:00"
    assert normalize_timestamp("Aug 25, 2026 1:11 pm") == "2026-08-25 13:11:00"
    assert normalize_timestamp(None) is None


def test_parse_followers_fixture():
    content = (FIXTURES_DIR / "followers_fixture.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "lxml")

    header = parse_export_header(soup)
    assert header["account_username"] == "testuser"
    assert header["generated_at"] == "2026-08-27T14:33Z"
    assert header["date_range_start"] == "2026-08-10T14:25Z"
    assert header["date_range_end"] == "2026-08-27T13:27Z"

    followers = parse_social_connections(soup, default_type="follower")
    assert len(followers) == 2
    assert followers[0]["username"] == "alice"
    assert followers[0]["connected_at"] == "2026-08-25 13:11:00"
    assert followers[1]["username"] == "bob"
    assert followers[1]["connected_at"] == "2026-08-22 02:52:00"


def test_parse_following_fixture():
    content = (FIXTURES_DIR / "following_fixture.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "lxml")

    following = parse_social_connections(soup, default_type="following")
    assert len(following) == 1
    assert following[0]["username"] == "charlie"
    assert following[0]["connected_at"] == "2026-09-23 06:34:00"


def test_parse_videos_fixture():
    content = (FIXTURES_DIR / "videos_fixture.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "lxml")

    header = parse_export_header(soup)
    assert header["account_username"] == "testuser"

    videos = parse_media_cards(soup)
    assert len(videos) == 1
    v = videos[0]
    assert v["url"] == "https://www.instagram.com/reel/TEST12345/"
    assert "Reviewing a great smartphone!" in v["caption"]
    assert v["owner_username"] == "getpeid"
    assert v["owner_name"] == "Carl Pei"
    assert v["owner_url"] == "http://nothing.tech"
    assert v["timestamp"] == "2026-08-20 08:33:00"
    assert "tech" in v["hashtags"]
    assert "gadgets" in v["hashtags"]
