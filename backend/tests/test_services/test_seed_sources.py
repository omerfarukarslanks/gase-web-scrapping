from scripts.seed_sources import SOURCE_DISCOVERY_OVERRIDES, build_source_payload


def test_build_source_payload_deep_merges_analysis_rules(monkeypatch) -> None:
    source_data = {
        "name": "Demo Source",
        "slug": "demo-source",
        "base_url": "https://demo.example.com",
        "rss_feeds": [],
        "category": "general",
        "has_paywall": False,
        "config": {
            "detail_policy": "metadata_only",
            "analysis_rules": {
                "reject_url_substrings": ["/subscriptions"],
                "reject_title_terms": ["subscriptions"],
            },
        },
    }

    monkeypatch.setitem(
        SOURCE_DISCOVERY_OVERRIDES,
        "demo-source",
        {
            "scraper_type": "rss",
            "config": {
                "discovery_priority": ["rss"],
                "analysis_rules": {
                    "force_story_subtype_by_title_terms": {
                        "schedule": ["schedule"],
                    }
                },
            },
        },
    )

    payload = build_source_payload(source_data)

    assert payload["config"]["detail_policy"] == "metadata_only"
    assert payload["config"]["discovery_priority"] == ["rss"]
    assert payload["config"]["analysis_rules"]["reject_url_substrings"] == ["/subscriptions"]
    assert payload["config"]["analysis_rules"]["reject_title_terms"] == ["subscriptions"]
    assert payload["config"]["analysis_rules"]["force_story_subtype_by_title_terms"]["schedule"] == ["schedule"]


def test_build_source_payload_rollout_sources_include_analysis_rules() -> None:
    bloomberg = build_source_payload(
        {
            "name": "Bloomberg",
            "slug": "bloomberg",
            "base_url": "https://www.bloomberg.com",
            "rss_feeds": [],
            "category": "finance",
            "has_paywall": True,
        }
    )
    cbssports = build_source_payload(
        {
            "name": "CBS Sports",
            "slug": "cbssports",
            "base_url": "https://www.cbssports.com",
            "rss_feeds": [],
            "category": "sports",
            "has_paywall": False,
        }
    )
    abcnews = build_source_payload(
        {
            "name": "ABC News",
            "slug": "abcnews",
            "base_url": "https://abcnews.go.com",
            "rss_feeds": [],
            "category": "general",
            "has_paywall": False,
        }
    )
    skysports = build_source_payload(
        {
            "name": "Sky Sports",
            "slug": "skysports",
            "base_url": "https://www.skysports.com",
            "rss_feeds": [],
            "category": "sports",
            "has_paywall": False,
        }
    )
    ft = build_source_payload(
        {
            "name": "Financial Times",
            "slug": "ft",
            "base_url": "https://www.ft.com",
            "rss_feeds": [],
            "category": "finance",
            "has_paywall": True,
        }
    )
    espncricinfo = build_source_payload(
        {
            "name": "ESPN Cricinfo",
            "slug": "espncricinfo",
            "base_url": "https://www.espncricinfo.com",
            "rss_feeds": [],
            "category": "sports",
            "has_paywall": False,
        }
    )
    reuters = build_source_payload(
        {
            "name": "Reuters",
            "slug": "reuters",
            "base_url": "https://www.reuters.com",
            "rss_feeds": [],
            "category": "general",
            "has_paywall": False,
        }
    )
    apnews = build_source_payload(
        {
            "name": "AP News",
            "slug": "apnews",
            "base_url": "https://apnews.com",
            "rss_feeds": [],
            "category": "general",
            "has_paywall": False,
        }
    )

    assert "analysis_rules" in bloomberg["config"]
    assert "analysis_rules" in cbssports["config"]
    assert abcnews["config"]["analysis_rules"]["reject_url_substrings"] == ["/video/", "/videos/", "/gma3/", "/538/"]
    assert "/live/" in apnews["config"]["exclude_url_substrings"]
    assert skysports["config"]["analysis_rules"]["reject_url_substrings"] == [
        "/watch/",
        "/video/",
        "/videos/",
        "/transfer-centre/",
        "/live-blog/",
    ]
    assert espncricinfo["is_active"] is False
    assert ft["config"]["analysis_rules"]["reject_url_substrings"] == ["/stream/", "/myft/", "/podcasts", "/video/"]
    assert ft["is_active"] is False
    assert reuters["config"]["analysis_rules"]["reject_url_substrings"] == ["/graphics/", "/pictures/", "/fact-check/"]
    assert reuters["is_active"] is False
    assert bloomberg["is_active"] is False
