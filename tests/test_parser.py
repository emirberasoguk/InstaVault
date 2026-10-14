from pathlib import Path
from bs4 import BeautifulSoup

from instavault.parser import (
    parse_export_header,
    parse_media_cards,
    parse_social_connections,
    parse_advertisers,
    parse_off_meta,
    parse_recent_searches,
    parse_interactions,
    parse_deleted_content,
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


def test_parse_advertisers_fixture():
    content = (FIXTURES_DIR / "advertisers_fixture.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "lxml")
    advs = parse_advertisers(soup)
    assert len(advs) == 3
    adv_dict = {a["advertiser_name"]: a["has_data_sharing"] for a in advs}
    assert "Acme Corporation" in adv_dict
    assert adv_dict["Acme Corporation"] is False
    assert "Beta Brand" in adv_dict
    assert adv_dict["Beta Brand"] is True
    assert "Gamma Store" in adv_dict
    assert adv_dict["Gamma Store"] is True


def test_parse_off_meta_fixture():
    content = (FIXTURES_DIR / "off_meta_fixture.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "lxml")
    events = parse_off_meta(soup)
    assert len(events) == 2
    assert events[0]["company_name"] == "Spotify AB"
    assert events[0]["event_name"] == "PAGE_VIEW"
    assert events[0]["timestamp"] == "2026-08-15 08:41:00"
    assert events[1]["company_name"] == "Spotify AB"
    assert events[1]["event_name"] == "SEARCH"
    assert events[1]["timestamp"] == "2026-08-16 21:15:00"


def test_parse_searches_fixture():
    content = (FIXTURES_DIR / "searches_fixture.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "lxml")
    searches = parse_recent_searches(soup)
    assert len(searches) == 2
    assert searches[0]["search_query"] == "nothing phone"
    assert searches[0]["searched_at"] == "2026-09-15 14:30:00"
    assert searches[1]["search_query"] == "python async"
    assert searches[1]["searched_at"] == "2026-09-14 11:20:00"


def test_parse_interactions_fixture():
    content = (FIXTURES_DIR / "interactions_fixture.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "lxml")
    interactions = parse_interactions(soup, default_type="post_like")
    assert len(interactions) == 2
    assert interactions[0]["interaction_type"] == "post_like"
    assert interactions[0]["target_username"] == "techinsider"
    assert interactions[0]["target_url"] == "https://www.instagram.com/p/CXYZ12345/"
    assert interactions[0]["timestamp"] == "2026-09-17 04:33:00"

    assert interactions[1]["interaction_type"] == "post_like"
    assert interactions[1]["target_username"] == "devuser"
    assert interactions[1]["timestamp"] == "2026-09-16 03:29:00"


def test_parse_deleted_content_fixture():
    content = (FIXTURES_DIR / "deleted_content_fixture.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "lxml")
    deleted = parse_deleted_content(soup)
    assert len(deleted) == 2
    assert deleted[0]["content_type"] == "reel"
    assert deleted[0]["caption"] == "Throwback summer video #vacation"
    assert deleted[0]["deleted_at"] == "2026-09-16 12:21:00"

    assert deleted[1]["content_type"] == "story"
    assert deleted[1]["caption"] is None
    assert deleted[1]["deleted_at"] == "2026-08-30 01:24:00"
