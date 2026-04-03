import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.source import Source
from app.services.article_service import hash_url


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "analysis" / "topic_golden_cases.json"


def load_golden_cases() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text())


async def create_source(
    db_session: AsyncSession,
    *,
    slug: str,
    name: str,
    category: str = "general",
    config: dict | None = None,
) -> Source:
    source = Source(
        name=name,
        slug=slug,
        base_url=f"https://{slug}.example.com",
        rss_feeds=[],
        scraper_type="rss",
        category=category,
        is_active=True,
        scrape_interval_minutes=60,
        rate_limit_rpm=10,
        has_paywall=False,
        config=config,
        last_scraped_at=None,
    )
    db_session.add(source)
    await db_session.flush()
    return source


async def create_article(
    db_session: AsyncSession,
    *,
    source: Source,
    title: str,
    url: str,
    source_category: str,
    summary: str,
    published_at: datetime | None,
    created_at: datetime,
    category: str | None = None,
    image_url: str | None = None,
    content_snippet: str | None = None,
    content_text: str | None = None,
    language: str = "en",
) -> Article:
    article = Article(
        source_id=source.id,
        title=title,
        url=url,
        url_hash=hash_url(url),
        summary=summary,
        content_snippet=content_snippet,
        content_text=content_text,
        author=None,
        published_at=published_at,
        scraped_at=created_at,
        image_url=image_url,
        category=category,
        tags=["energy", "markets"] if source_category == "finance" else ["sports"],
        language=language,
        source_category=source_category,
        raw_metadata=None,
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(article)
    await db_session.flush()
    await db_session.refresh(article)
    return article


async def seed_case(db_session: AsyncSession, case: dict) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    sources: dict[str, Source] = {}

    for source_payload in case.get("sources", []):
        sources[source_payload["slug"]] = await create_source(
            db_session,
            slug=source_payload["slug"],
            name=source_payload["name"],
            category=source_payload.get("category", "general"),
            config=source_payload.get("config"),
        )

    for article_payload in case.get("articles", []):
        published_minutes_ago = article_payload.get("published_minutes_ago")
        created_minutes_ago = article_payload.get("created_minutes_ago", published_minutes_ago or 0)
        published_at = None if published_minutes_ago is None else now - timedelta(minutes=published_minutes_ago)
        created_at = now - timedelta(minutes=created_minutes_ago)
        await create_article(
            db_session,
            source=sources[article_payload["source_slug"]],
            title=article_payload["title"],
            url=article_payload["url"],
            source_category=article_payload["source_category"],
            summary=article_payload["summary"],
            published_at=published_at,
            created_at=created_at,
            category=article_payload.get("category"),
            image_url=article_payload.get("image_url"),
            content_snippet=article_payload.get("content_snippet"),
            content_text=article_payload.get("content_text"),
            language=article_payload.get("language", "en"),
        )

    await db_session.commit()


def flatten_topics(payload: dict) -> list[dict]:
    return [topic for group in payload["groups"] for topic in group["topics"]]


def rejection_breakdown(payload: dict) -> dict[str, int]:
    return {
        item["reason"]: item["count"]
        for item in payload.get("debug", {}).get("rejection_breakdown", [])
    }


def video_review_breakdown(payload: dict) -> dict[str, int]:
    return {
        item["reason"]: item["count"]
        for item in payload.get("debug", {}).get("video_review_breakdown", [])
    }


def assert_story_subtype_effect(topic: dict, effect: dict) -> None:
    if "format_hint_equals" in effect:
        assert topic["video_prompt_parts"]["format_hint"] == effect["format_hint_equals"]
    if "story_angle_contains" in effect:
        assert effect["story_angle_contains"] in topic["video_prompt_parts"]["story_angle"]
    for value in effect.get("story_angle_not_contains", []):
        assert value not in topic["video_prompt_parts"]["story_angle"]
    for value in effect.get("video_prompt_contains", []):
        assert value in topic["video_prompt_en"]
    for value in effect.get("video_prompt_not_contains", []):
        assert value not in topic["video_prompt_en"]
    for value in effect.get("scene_sequence_contains", []):
        assert any(value in scene for scene in topic["video_prompt_parts"]["scene_sequence"])
    for value in effect.get("scene_sequence_not_contains", []):
        assert all(value not in scene for scene in topic["video_prompt_parts"]["scene_sequence"])
    if "summary_contains" in effect:
        assert effect["summary_contains"] in topic["summary_tr"]
    for value in effect.get("summary_not_contains", []):
        assert value not in topic["summary_tr"]
    for value in effect.get("key_data_not_contains", []):
        assert value not in topic["video_content"]["key_data"]


def assert_golden_case(payload: dict, case: dict) -> None:
    expected = case["expected"]
    topics = flatten_topics(payload)

    assert len(topics) == expected["topic_count"]

    if "aggregation_types" in expected:
        assert [topic["aggregation_type"] for topic in topics] == expected["aggregation_types"]
    if "quality_statuses" in expected:
        assert [topic["quality_status"] for topic in topics] == expected["quality_statuses"]
    if "video_quality_statuses" in expected:
        assert [topic["video_quality_status"] for topic in topics] == expected["video_quality_statuses"]
    if "story_languages" in expected:
        assert [topic["story_language"] for topic in topics] == expected["story_languages"]
    if "editorial_types" in expected:
        assert [topic["editorial_type"] for topic in topics] == expected["editorial_types"]
    if expected.get("quality_score_descending"):
        assert [topic["quality_score"] for topic in topics] == sorted(
            [topic["quality_score"] for topic in topics],
            reverse=True,
        )
    for score_expectation in expected.get("quality_scores", []):
        topic = topics[score_expectation.get("topic_index", 0)]
        if "min" in score_expectation:
            assert topic["quality_score"] >= score_expectation["min"]
        if "max" in score_expectation:
            assert topic["quality_score"] <= score_expectation["max"]

    for index, headline_fragment in enumerate(expected.get("headline_order", [])):
        assert headline_fragment in topics[index]["headline_tr"]

    for headline_fragment in expected.get("must_contain_headlines", []):
        assert any(headline_fragment in topic["headline_tr"] for topic in topics)

    for headline_fragment in expected.get("must_not_contain_topics", []):
        assert all(headline_fragment not in topic["headline_tr"] for topic in topics)

    if "rejected_articles" in expected:
        assert payload["debug"]["rejected_articles"] == expected["rejected_articles"]
    if "rejected_unique_candidates" in expected:
        assert payload["debug"]["rejected_unique_candidates"] == expected["rejected_unique_candidates"]
    if "dropped_unique_articles" in expected:
        assert payload["debug"]["dropped_unique_articles"] == expected["dropped_unique_articles"]

    actual_breakdown = rejection_breakdown(payload)
    for reason, count in expected.get("rejection_breakdown", {}).items():
        assert actual_breakdown.get(reason, 0) == count

    actual_input_breakdown = {
        item["reason"]: item["count"]
        for item in payload.get("totals", {}).get("input_rejection_breakdown", [])
    }
    for reason, count in expected.get("input_rejection_breakdown", {}).items():
        assert actual_input_breakdown.get(reason, 0) == count

    actual_video_breakdown = video_review_breakdown(payload)
    for reason, count in expected.get("video_review_breakdown", {}).items():
        assert actual_video_breakdown.get(reason, 0) == count

    for field in (
        "video_publishable_topics_generated",
        "video_review_topics_generated",
        "video_rejected_topics_generated",
    ):
        if field in expected:
            assert payload["debug"][field] == expected[field]

    for effect in expected.get("story_subtype_effects", []):
        assert_story_subtype_effect(topics[effect.get("topic_index", 0)], effect)

    for expectation in expected.get("video_reason_expectations", []):
        topic = topics[expectation.get("topic_index", 0)]
        reasons = topic["video_review_reasons"]
        for reason in expectation.get("contains", []):
            assert reason in reasons
        for reason in expectation.get("not_contains", []):
            assert reason not in reasons
