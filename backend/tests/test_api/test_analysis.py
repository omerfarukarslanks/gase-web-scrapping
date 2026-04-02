from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.source import Source
from app.models.topic_feedback import TopicFeedback
from app.schemas.analysis import VideoPromptParts
from app.services.article_service import hash_url
from app.services.remotion_storyboard_service import RemotionStoryboardService
from app.services.topic_analysis import (
    OllamaAnalysisError,
    PreparedArticle,
    build_candidate_clusters,
    build_contextual_prompt_parts,
    build_fallback_video_plan,
    build_remotion_storyboard_context,
    build_video_prompt_from_parts,
    coerce_video_plan,
    get_recent_articles_for_analysis,
    normalize_analysis_category,
    tokenize,
)
from app.services.visual_asset_service import (
    VisualAssetCandidate,
    VisualAssetResolver,
    extract_open_graph_image,
)


async def create_source(
    db_session: AsyncSession,
    *,
    slug: str,
    name: str,
    category: str = "general",
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
        config=None,
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
) -> Article:
    article = Article(
        source_id=source.id,
        title=title,
        url=url,
        url_hash=hash_url(url),
        summary=summary,
        content_snippet=None,
        author=None,
        published_at=published_at,
        scraped_at=created_at,
        image_url=image_url,
        category=category,
        tags=["energy", "markets"] if source_category == "finance" else ["sports"],
        language="en",
        source_category=source_category,
        raw_metadata=None,
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(article)
    await db_session.flush()
    await db_session.refresh(article)
    return article


def make_prepared_article(
    *,
    title: str,
    summary: str,
    source_name: str,
    source_slug: str,
    normalized_category: str = "business",
) -> PreparedArticle:
    timestamp = datetime.now(UTC).replace(tzinfo=None)
    article = Article(
        id=uuid4(),
        source_id=uuid4(),
        title=title,
        url=f"https://{source_slug}.example.com/{uuid4()}",
        url_hash=hash_url(f"https://{source_slug}.example.com/{uuid4()}"),
        summary=summary,
        content_snippet=None,
        author=None,
        published_at=timestamp,
        scraped_at=timestamp,
        image_url=None,
        category=normalized_category,
        tags=["energy", "markets"],
        language="en",
        source_category="finance",
        raw_metadata=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    return PreparedArticle(
        article=article,
        normalized_category=normalized_category,
        analysis_text=summary,
        timestamp=timestamp,
        source_name=source_name,
        source_slug=source_slug,
        tag_tokens={"energy", "markets"},
        title_tokens=tokenize(title),
        text_tokens=tokenize(summary, max_tokens=80),
    )


async def create_topic_feedback_record(
    db_session: AsyncSession,
    *,
    topic_id: str,
    feedback_label: str,
    headline_tr: str = "Sample headline",
    summary_tr: str = "Sample summary with enough words for tuning.",
    category: str = "general",
    aggregation_type: str = "shared",
    quality_status: str = "publishable",
    quality_score: float = 0.75,
    source_count: int = 2,
    article_count: int = 2,
    source_slugs: list[str] | None = None,
    review_reasons: list[str] | None = None,
    score_features: dict[str, bool] | None = None,
    note: str | None = None,
) -> TopicFeedback:
    record = TopicFeedback(
        topic_id=topic_id,
        feedback_label=feedback_label,
        note=note,
        headline_tr=headline_tr,
        summary_tr=summary_tr,
        category=category,
        aggregation_type=aggregation_type,
        quality_status=quality_status,
        quality_score=quality_score,
        source_count=source_count,
        article_count=article_count,
        source_slugs=source_slugs or ["reuters"],
        representative_article_ids=[str(uuid4())],
        review_reasons=review_reasons or [],
        score_features=score_features
        or {
            "shared_topic": aggregation_type == "shared",
            "unique_topic": aggregation_type == "unique",
            "source_count_ge_2": source_count >= 2,
            "source_count_ge_3": source_count >= 3,
            "has_visual_asset": True,
            "missing_visual_asset": False,
            "non_thin_summary": True,
            "thin_summary": False,
            "non_truncated_headline": True,
            "truncated_headline": False,
            "has_published_at": True,
            "missing_published_at": False,
            "article_count_ge_2": article_count >= 2,
            "degraded_generation": False,
            "review_status": quality_status == "review",
        },
    )
    db_session.add(record)
    await db_session.flush()
    await db_session.refresh(record)
    return record


@pytest.mark.asyncio
async def test_get_recent_articles_for_analysis_uses_published_at_and_created_at_fallback(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    source = await create_source(db_session, slug="reuters", name="Reuters", category="general")

    published_recent = await create_article(
        db_session,
        source=source,
        title="Recent published article",
        url="https://reuters.example.com/recent-published",
        source_category="general",
        summary="Recent article summary",
        published_at=now - timedelta(minutes=20),
        created_at=now - timedelta(minutes=20),
    )
    created_recent = await create_article(
        db_session,
        source=source,
        title="Recent created article",
        url="https://reuters.example.com/recent-created",
        source_category="general",
        summary="Created recently without published_at",
        published_at=None,
        created_at=now - timedelta(minutes=15),
    )
    old_published = await create_article(
        db_session,
        source=source,
        title="Old published article",
        url="https://reuters.example.com/old-published",
        source_category="general",
        summary="Published too early to be included",
        published_at=now - timedelta(hours=2),
        created_at=now - timedelta(minutes=5),
    )
    old_created = await create_article(
        db_session,
        source=source,
        title="Old created article",
        url="https://reuters.example.com/old-created",
        source_category="general",
        summary="Created too early to be included",
        published_at=None,
        created_at=now - timedelta(hours=2),
    )
    await db_session.commit()

    recent_articles = await get_recent_articles_for_analysis(db_session, window_end=now)
    recent_ids = {article.id for article in recent_articles}

    assert published_recent.id in recent_ids
    assert created_recent.id in recent_ids
    assert old_published.id not in recent_ids
    assert old_created.id not in recent_ids


@pytest.mark.asyncio
async def test_get_recent_articles_for_analysis_supports_custom_hours_window(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    source = await create_source(db_session, slug="bbc", name="BBC News", category="general")

    within_three_hours = await create_article(
        db_session,
        source=source,
        title="Launch coverage within three hours",
        url="https://bbc.example.com/launch-coverage",
        source_category="general",
        summary="A launch story published two hours ago.",
        published_at=now - timedelta(hours=2),
        created_at=now - timedelta(hours=2),
        category="general",
    )
    older_than_three_hours = await create_article(
        db_session,
        source=source,
        title="Coverage too old for three-hour window",
        url="https://bbc.example.com/older-coverage",
        source_category="general",
        summary="A story published four hours ago.",
        published_at=now - timedelta(hours=4),
        created_at=now - timedelta(hours=4),
        category="general",
    )
    await db_session.commit()

    recent_articles = await get_recent_articles_for_analysis(
        db_session,
        hours=3,
        window_end=now,
    )
    recent_ids = {article.id for article in recent_articles}

    assert within_three_hours.id in recent_ids
    assert older_than_three_hours.id not in recent_ids


@pytest.mark.asyncio
async def test_get_recent_articles_for_analysis_caps_articles_per_source(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    first_source = await create_source(db_session, slug="source-one", name="Source One", category="general")
    second_source = await create_source(db_session, slug="source-two", name="Source Two", category="general")

    for index in range(4):
        await create_article(
            db_session,
            source=first_source,
            title=f"Source One Story {index}",
            url=f"https://source-one.example.com/{index}",
            source_category="general",
            summary="A recent article from the first source.",
            published_at=now - timedelta(minutes=index + 1),
            created_at=now - timedelta(minutes=index + 1),
        )

    for index in range(2):
        await create_article(
            db_session,
            source=second_source,
            title=f"Source Two Story {index}",
            url=f"https://source-two.example.com/{index}",
            source_category="general",
            summary="A recent article from the second source.",
            published_at=now - timedelta(minutes=index + 1),
            created_at=now - timedelta(minutes=index + 1),
        )

    await db_session.commit()

    monkeypatch.setattr("app.services.topic_analysis.settings.ANALYSIS_MAX_ARTICLES_PER_SOURCE", 2)
    monkeypatch.setattr("app.services.topic_analysis.settings.ANALYSIS_MAX_ARTICLES_PER_RUN", 10)

    recent_articles = await get_recent_articles_for_analysis(db_session, window_end=now, hours=6)
    source_counts: dict[str, int] = {}
    for article in recent_articles:
        source_counts[str(article.source.slug)] = source_counts.get(str(article.source.slug), 0) + 1

    assert source_counts["source-one"] == 2
    assert source_counts["source-two"] == 2


def test_normalize_analysis_category_maps_values() -> None:
    assert normalize_analysis_category("Science and Technology", "general") == "technology"
    assert normalize_analysis_category("MoneyWatch", "general") == "business"
    assert normalize_analysis_category(None, "finance") == "business"
    assert normalize_analysis_category(None, "sports") == "sports"
    assert normalize_analysis_category("Unknown label", None) == "general"


def test_build_candidate_clusters_groups_related_titles() -> None:
    related_one = make_prepared_article(
        title="Oil prices jump after Texas refinery outage",
        summary="Global oil benchmarks rose after a refinery outage in Texas disrupted supply expectations.",
        source_name="Reuters",
        source_slug="reuters",
    )
    related_two = make_prepared_article(
        title="Texas refinery outage sends oil prices higher",
        summary="Markets reacted to a Texas refinery shutdown and traders pushed oil prices upward.",
        source_name="Bloomberg",
        source_slug="bloomberg",
    )
    unrelated = make_prepared_article(
        title="Apple unveils new chips at annual developer event",
        summary="Apple introduced a new chip family and highlighted AI features for developers.",
        source_name="WSJ",
        source_slug="wsj",
        normalized_category="technology",
    )

    clusters = build_candidate_clusters([related_one, related_two, unrelated])

    assert len(clusters) == 1
    assert {item.source_slug for item in clusters[0]} == {"reuters", "bloomberg"}


def test_build_contextual_prompt_parts_for_sports_uses_score_and_key_actor() -> None:
    first = make_prepared_article(
        title="Correa's 3-run blast powers the Astros past the Red Sox 6-4 for a sweep",
        summary="Carlos Correa hit a 3-run homer as the Astros beat the Red Sox 6-4 to complete the sweep.",
        source_name="AP News",
        source_slug="ap",
        normalized_category="sports",
    )
    second = make_prepared_article(
        title="Yahoo Sports: Correa Blast Powers Astros to 6-4 Win, Sweep Over Red Sox",
        summary="Yahoo Sports also highlighted Correa and the 6-4 Astros win over Boston in the sweep finale.",
        source_name="Yahoo Sports",
        source_slug="yahoo",
        normalized_category="sports",
    )

    prompt_parts = build_contextual_prompt_parts(
        [first, second],
        category="sports",
        headline="Correa's 3-run blast powers the Astros past the Red Sox 6-4 for a sweep",
        summary="Carlos Correa hit a 3-run homer as Houston beat Boston 6-4 and sealed the sweep.",
        key_points=[
            "Carlos Correa's 3-run homer changed the game.",
            "Houston beat Boston 6-4 to complete the sweep.",
        ],
        why_it_matters="Houston leaves the series with momentum after a convincing sweep.",
    )

    assert "sports moment" in prompt_parts.story_angle
    assert "6-4" in prompt_parts.story_angle
    assert "glossy score bugs" in prompt_parts.visual_brief
    assert prompt_parts.format_hint
    assert prompt_parts.motion_treatment
    assert prompt_parts.transition_style
    assert prompt_parts.design_keywords
    assert any("6-4" in item for item in prompt_parts.must_include)
    assert any("Correa" in item for item in prompt_parts.must_include)
    assert any("scoreboard" in scene.lower() for scene in prompt_parts.scene_sequence)
    assert 8 <= prompt_parts.duration_seconds <= 30


def test_build_contextual_prompt_parts_for_non_score_sports_story_avoids_fake_matchup() -> None:
    first = make_prepared_article(
        title="Arthur backs 'national treasure' Bashir to regain form",
        summary="Coach Mickey Arthur says Shoaib Bashir can play his way back into England contention.",
        source_name="BBC Sport",
        source_slug="bbc-sport",
        normalized_category="sports",
    )
    second = make_prepared_article(
        title="Arthur says Bashir can regain his England place",
        summary="A second report says Bashir has a fresh chance to rebuild momentum at Derbyshire.",
        source_name="Sky Sports",
        source_slug="sky-sport",
        normalized_category="sports",
    )

    prompt_parts = build_contextual_prompt_parts(
        [first, second],
        category="sports",
        headline="Arthur backs Bashir to regain form",
        summary="Coach Mickey Arthur says Shoaib Bashir can rebuild his case for England at Derbyshire.",
        key_points=["Bashir gets a fresh chance at Derbyshire."],
        why_it_matters="A short run of form could quickly affect Bashir's England chances.",
    )

    assert "arthur vs bashir" not in prompt_parts.story_angle.lower()
    assert "without forcing a matchup or scoreboard framing" in prompt_parts.story_angle.lower()
    assert all("scoreboard" not in scene.lower() for scene in prompt_parts.scene_sequence)
    assert "portrait" in prompt_parts.visual_brief.lower()


def test_build_contextual_prompt_parts_for_schedule_story_avoids_scoreboard_frame() -> None:
    first = make_prepared_article(
        title="MI IPL 2026 full schedule: Check dates, venues and home-away fixtures of Mumbai Indians",
        summary="Mumbai Indians open their 2026 campaign on March 29 at Wankhede against Kolkata Knight Riders.",
        source_name="Yahoo Sports",
        source_slug="yahoo-sports",
        normalized_category="sports",
    )
    second = make_prepared_article(
        title="Mumbai Indians confirm dates and venues for 2026 IPL fixtures",
        summary="The fixture list lays out dates, venues and home-away splits for Mumbai's campaign.",
        source_name="CBS Sports",
        source_slug="cbs-sports",
        normalized_category="sports",
    )

    prompt_parts = build_contextual_prompt_parts(
        [first, second],
        category="sports",
        headline=first.article.title,
        summary=first.article.summary or "",
        key_points=["Mumbai opens on March 29 at Wankhede.", "The schedule includes home-away splits."],
        why_it_matters="The fixture order shapes the early path of Mumbai's season.",
    )

    assert "schedule-driven sports update" in prompt_parts.story_angle.lower()
    assert "date and venue" in prompt_parts.story_angle.lower()
    assert all("scoreboard" not in scene.lower() for scene in prompt_parts.scene_sequence)
    assert "scoreboard" not in prompt_parts.visual_brief.lower()


def test_build_contextual_prompt_parts_for_business_non_market_story_avoids_terminal_frame() -> None:
    first = make_prepared_article(
        title="MPS turmoil could turn it from predator to prey",
        summary="A strategic rethink could leave the bank vulnerable to a takeover instead of expansion.",
        source_name="Financial Times",
        source_slug="ft",
        normalized_category="business",
    )
    second = make_prepared_article(
        title="Bank turmoil leaves MPS exposed to outside pressure",
        summary="A second report says the bank's instability is changing its options and bargaining power.",
        source_name="Reuters",
        source_slug="reuters",
        normalized_category="business",
    )

    prompt_parts = build_contextual_prompt_parts(
        [first, second],
        category="business",
        headline=first.article.title,
        summary=first.article.summary or "",
        key_points=["The bank's leverage is weakening."],
        why_it_matters="The next strategic decision could change who controls the bank.",
    )

    assert prompt_parts.format_hint == "Editorial business explainer with restrained motion graphics"
    assert "market narrative" not in prompt_parts.story_angle.lower()
    assert "market-terminal aesthetic" in prompt_parts.visual_brief.lower()


def test_build_video_prompt_from_parts_prefers_human_guidance_over_rigid_checklists() -> None:
    prompt = build_video_prompt_from_parts(
        VideoPromptParts(
            format_hint="Premium broadcast-meets-kinetic-typography sports short",
            story_angle="Turn Astros vs Red Sox into a premium, emotionally readable sports moment with Correa as the decisive figure.",
            visual_brief="Use stadium-light contrast, glossy score bugs, and crisp team-color energy.",
            motion_treatment="Use snap zooms and elastic scoreboard reveals.",
            transition_style="Use scoreboard wipes and bright light-streak cuts.",
            scene_sequence=[
                "Open on a bold scoreboard with the 6-4 result anchored in the center.",
                "Punch into Correa's decisive moment with player-led spotlight typography.",
                "Close on a sweep card that feels like the end of a highlight package.",
            ],
            tone="High-energy, premium, and emotionally clear",
            design_keywords=["broadcast polish", "score bug", "stadium glow"],
            must_include=["Astros vs Red Sox", "6-4", "Carlos Correa"],
            avoid=["Publisher logos", "Forced screenshots"],
            duration_seconds=30,
        ),
        category="sports",
    )

    assert "Possible sequence:" in prompt
    assert "Helpful story anchors:" in prompt
    assert "Do not force sources, logos, screenshots, or maps" in prompt
    assert "Must Include:" not in prompt


def test_coerce_video_plan_supports_single_scene_and_hides_source_line() -> None:
    first = make_prepared_article(
        title="Artemis II launch sends crew toward the moon",
        summary="NASA launched Artemis II on a mission that begins a new moon era.",
        source_name="BBC News",
        source_slug="bbc",
        normalized_category="science",
    )
    second = make_prepared_article(
        title="Artemis II begins crewed moon-era mission",
        summary="A second outlet also highlighted the start of the Artemis II mission.",
        source_name="CBS News",
        source_slug="cbs",
        normalized_category="science",
    )
    prompt_parts = build_contextual_prompt_parts(
        [first, second],
        category="science",
        headline="Artemis II begins a new moon-era mission",
        summary="Two outlets describe Artemis II as the start of a new crewed moon chapter.",
        key_points=["Artemis II launched successfully.", "The mission revives crewed moon ambitions."],
        why_it_matters="The mission reopens a major chapter in human spaceflight.",
    )

    video_plan = coerce_video_plan(
        {
            "title": "Artemis II begins a new moon-era mission",
            "duration_seconds": 22,
            "source_visibility": "none",
            "scenes": [
                {
                    "scene_id": "scene-1",
                    "purpose": "hook",
                    "duration_seconds": 22,
                    "layout_hint": "full-bleed",
                    "headline": "Artemis II is back on the launchpad",
                    "body": "A single, focused opener frames the mission for social viewers.",
                    "supporting_points": [],
                    "key_figures": ["Moon mission", "Crewed return"],
                    "key_data": "",
                    "visual_direction": "Show a clean launch silhouette with orbital glow.",
                    "motion_direction": "Use a slow dramatic push-in.",
                    "transition_from_previous": "Cold open",
                    "source_line": "BBC News and CBS News",
                }
            ],
        },
        [first, second],
        category="science",
        headline="Artemis II begins a new moon-era mission",
        summary="Two outlets describe Artemis II as the start of a new crewed moon chapter.",
        key_points=["Artemis II launched successfully.", "The mission revives crewed moon ambitions."],
        why_it_matters="The mission reopens a major chapter in human spaceflight.",
        prompt_parts=prompt_parts,
        visual_assets=[],
    )

    assert video_plan.duration_seconds == 22
    assert len(video_plan.scenes) == 1
    assert video_plan.scenes[0].duration_seconds == 22
    assert video_plan.scenes[0].source_line == ""


def test_coerce_video_plan_collapses_repetitive_short_sports_story_to_single_scene() -> None:
    first = make_prepared_article(
        title="Arthur backs Bashir to regain form",
        summary="Arthur says Bashir can rebuild his England case.",
        source_name="BBC Sport",
        source_slug="bbc-sport",
        normalized_category="sports",
    )
    second = make_prepared_article(
        title="Arthur backs Bashir to regain England form",
        summary="Another outlet repeats that Bashir can regain momentum.",
        source_name="Sky Sports",
        source_slug="sky-sport",
        normalized_category="sports",
    )
    prompt_parts = build_contextual_prompt_parts(
        [first, second],
        category="sports",
        headline="Arthur backs Bashir to regain form",
        summary="Arthur says Bashir can rebuild his England case at Derbyshire.",
        key_points=["Bashir gets a fresh chance at Derbyshire."],
        why_it_matters="A quick return to form could change Bashir's selection outlook.",
    )

    video_plan = coerce_video_plan(
        {
            "title": "Arthur backs Bashir to regain form",
            "duration_seconds": 18,
            "source_visibility": "none",
            "scenes": [
                {
                    "scene_id": "scene-1",
                    "purpose": "hook",
                    "duration_seconds": 9,
                    "layout_hint": "full-bleed",
                    "headline": "Arthur backs Bashir to regain form",
                    "body": "Arthur says Bashir can rebuild his England case at Derbyshire.",
                    "supporting_points": [],
                    "key_figures": ["Shoaib Bashir"],
                    "key_data": "",
                    "visual_direction": "Hero portrait",
                    "motion_direction": "Slow push",
                    "transition_from_previous": "Cold open",
                    "source_line": "",
                    "asset_ids": [],
                },
                {
                    "scene_id": "scene-2",
                    "purpose": "explain",
                    "duration_seconds": 9,
                    "layout_hint": "comparison",
                    "headline": "Arthur backs Bashir to regain form",
                    "body": "Arthur says Bashir can rebuild his England case at Derbyshire.",
                    "supporting_points": [],
                    "key_figures": ["Shoaib Bashir"],
                    "key_data": "",
                    "visual_direction": "Repeat hero portrait",
                    "motion_direction": "Slow push",
                    "transition_from_previous": "Soft wipe",
                    "source_line": "",
                    "asset_ids": [],
                },
            ],
        },
        [first, second],
        category="sports",
        headline="Arthur backs Bashir to regain form",
        summary="Arthur says Bashir can rebuild his England case at Derbyshire.",
        key_points=["Bashir gets a fresh chance at Derbyshire."],
        why_it_matters="A quick return to form could change Bashir's selection outlook.",
        prompt_parts=prompt_parts,
        visual_assets=[],
    )

    assert len(video_plan.scenes) == 1
    assert video_plan.duration_seconds == 12
    assert video_plan.scenes[0].layout_hint == "full-bleed"


def test_coerce_video_plan_clamps_long_multi_scene_plan_to_master_runtime() -> None:
    first = make_prepared_article(
        title="Oil prices jump after refinery outage",
        summary="Oil prices climbed after an outage raised short-term supply concerns.",
        source_name="Reuters",
        source_slug="reuters",
    )
    second = make_prepared_article(
        title="Refinery outage pushes crude higher",
        summary="Another report described the same outage lifting oil prices.",
        source_name="Bloomberg",
        source_slug="bloomberg",
    )
    prompt_parts = build_contextual_prompt_parts(
        [first, second],
        category="business",
        headline="Oil prices rise after refinery outage",
        summary="Two outlets say the outage pushed crude prices higher.",
        key_points=["Crude prices moved up.", "Supply concerns drove the reaction."],
        why_it_matters="Energy costs may stay elevated in the near term.",
    )

    video_plan = coerce_video_plan(
        {
            "title": "Oil prices rise after refinery outage",
            "duration_seconds": 70,
            "source_visibility": "subtle",
            "scenes": [
                {
                    "scene_id": f"scene-{index + 1}",
                    "purpose": purpose,
                    "duration_seconds": duration,
                    "layout_hint": layout,
                    "headline": headline,
                    "body": body,
                    "supporting_points": [],
                    "key_figures": [],
                    "key_data": "",
                    "visual_direction": "Clean market graphics",
                    "motion_direction": "Measured camera slides",
                    "transition_from_previous": "Smooth wipe",
                    "source_line": "Reuters and Bloomberg",
                    "asset_ids": [],
                }
                for index, (purpose, layout, duration, headline, body) in enumerate(
                    [
                        ("hook", "headline", 8, "Oil jolts higher", "Markets react immediately."),
                        ("explain", "split", 10, "What changed", "A refinery outage tightened expectations."),
                        ("detail", "stat", 12, "Why traders moved", "Supply concerns fed the move."),
                        ("context", "timeline", 12, "The short-term setup", "Energy desks now watch follow-through."),
                        ("comparison", "comparison", 14, "What markets are comparing", "Benchmarks and regional impacts diverge."),
                        ("close", "minimal", 14, "What to watch next", "Attention turns to near-term supply updates."),
                    ]
                )
            ],
        },
        [first, second],
        category="business",
        headline="Oil prices rise after refinery outage",
        summary="Two outlets say the outage pushed crude prices higher.",
        key_points=["Crude prices moved up.", "Supply concerns drove the reaction."],
        why_it_matters="Energy costs may stay elevated in the near term.",
        prompt_parts=prompt_parts,
        visual_assets=[],
    )

    assert video_plan.duration_seconds == 30
    assert len(video_plan.scenes) == 2
    assert sum(scene.duration_seconds for scene in video_plan.scenes) == 30
    assert all(scene.source_line == "Reuters and Bloomberg" for scene in video_plan.scenes)


def test_remotion_storyboard_service_builds_storyboard_from_human_prompt() -> None:
    first = make_prepared_article(
        title="Correa's 3-run blast powers the Astros past the Red Sox 6-4 for a sweep",
        summary="Carlos Correa hit a 3-run homer as the Astros beat the Red Sox 6-4 to complete the sweep.",
        source_name="AP News",
        source_slug="ap",
        normalized_category="sports",
    )
    second = make_prepared_article(
        title="Yahoo Sports: Correa Blast Powers Astros to 6-4 Win, Sweep Over Red Sox",
        summary="Yahoo Sports also highlighted Correa and the 6-4 Astros win over Boston in the sweep finale.",
        source_name="Yahoo Sports",
        source_slug="yahoo",
        normalized_category="sports",
    )

    prompt_parts = build_contextual_prompt_parts(
        [first, second],
        category="sports",
        headline="Correa's 3-run blast powers the Astros past the Red Sox 6-4 for a sweep",
        summary="Carlos Correa hit a 3-run homer as Houston beat Boston 6-4 and sealed the sweep.",
        key_points=[
            "Carlos Correa's 3-run homer changed the game.",
            "Houston beat Boston 6-4 to complete the sweep.",
        ],
        why_it_matters="Houston leaves the series with momentum after a convincing sweep.",
    )
    human_prompt = "Use Remotion best practices. Create a premium sports short with a scoreboard opener, a Correa spotlight, and a closing sweep takeaway."
    video_plan = build_fallback_video_plan(
        [first, second],
        category="sports",
        headline="Correa's 3-run blast powers the Astros past the Red Sox 6-4 for a sweep",
        summary="Carlos Correa hit a 3-run homer as Houston beat Boston 6-4 and sealed the sweep.",
        key_points=[
            "Carlos Correa's 3-run homer changed the game.",
            "Houston beat Boston 6-4 to complete the sweep.",
        ],
        why_it_matters="Houston leaves the series with momentum after a convincing sweep.",
        prompt_parts=prompt_parts,
        visual_assets=[],
    )
    context = build_remotion_storyboard_context(
        [first, second],
        category="sports",
        headline="Correa's 3-run blast powers the Astros past the Red Sox 6-4 for a sweep",
        summary="Carlos Correa hit a 3-run homer as Houston beat Boston 6-4 and sealed the sweep.",
        key_points=[
            "Carlos Correa's 3-run homer changed the game.",
            "Houston beat Boston 6-4 to complete the sweep.",
        ],
        why_it_matters="Houston leaves the series with momentum after a convincing sweep.",
        prompt_parts=prompt_parts,
        prompt_text=human_prompt,
        video_plan=video_plan,
        visual_assets=[],
    )

    storyboard = RemotionStoryboardService().build_storyboard(context)

    assert storyboard.visual_thesis
    assert len(storyboard.scenes) == 2
    assert storyboard.scenes[0].scene_type == "hook"
    assert storyboard.scenes[1].scene_type == "story"
    assert sum(scene.duration_seconds for scene in storyboard.scenes) == video_plan.duration_seconds


@pytest.mark.asyncio
async def test_visual_asset_resolver_prefers_article_images_and_uses_og_fallback(monkeypatch) -> None:
    resolver = VisualAssetResolver()

    async def fake_fetch_open_graph_image(self, client, page_url: str) -> str:
        if "fallback-story" in page_url:
            return "https://images.example.com/fallback-og.jpg"
        return ""

    monkeypatch.setattr(
        VisualAssetResolver,
        "_fetch_open_graph_image",
        fake_fetch_open_graph_image,
    )

    candidates = [
        VisualAssetCandidate(
            article_id=uuid4(),
            article_url="https://news.example.com/with-image",
            title="Story with a direct image",
            source_name="Example News",
            image_url="https://images.example.com/direct.jpg",
        ),
        VisualAssetCandidate(
            article_id=uuid4(),
            article_url="https://news.example.com/fallback-story",
            title="Story that needs OG fallback",
            source_name="Fallback News",
            image_url=None,
        ),
    ]

    assets = await resolver.resolve(candidates)

    assert len(assets) == 2
    assert assets[0].kind == "article_image"
    assert assets[0].url == "https://images.example.com/direct.jpg"
    assert assets[1].kind == "og_image"
    assert assets[1].url == "https://images.example.com/fallback-og.jpg"


def test_extract_open_graph_image_resolves_relative_urls() -> None:
    html = """
    <html>
      <head>
        <meta property="og:image" content="/images/story.jpg" />
      </head>
    </html>
    """

    image_url = extract_open_graph_image(html, page_url="https://example.com/news/story")

    assert image_url == "https://example.com/images/story.jpg"


@pytest.mark.asyncio
async def test_topic_briefs_endpoint_filters_and_returns_mocked_ollama_result(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    reuters = await create_source(db_session, slug="reuters", name="Reuters", category="finance")
    bloomberg = await create_source(db_session, slug="bloomberg", name="Bloomberg", category="finance")
    espn = await create_source(db_session, slug="espn", name="ESPN", category="sports")

    first = await create_article(
        db_session,
        source=reuters,
        title="Oil prices jump after Texas refinery outage",
        url="https://reuters.example.com/oil-prices-jump",
        source_category="finance",
        summary="Oil prices moved higher after a refinery outage in Texas tightened market expectations.",
        published_at=now - timedelta(minutes=25),
        created_at=now - timedelta(minutes=25),
        image_url="https://cdn.example.com/reuters-oil.jpg",
    )
    second = await create_article(
        db_session,
        source=bloomberg,
        title="Texas refinery outage sends crude higher",
        url="https://bloomberg.example.com/refinery-outage",
        source_category="finance",
        summary="Crude rose as a Texas refinery outage raised near-term supply concerns across markets.",
        published_at=now - timedelta(minutes=18),
        created_at=now - timedelta(minutes=18),
        image_url="https://cdn.example.com/bloomberg-oil.jpg",
    )
    await create_article(
        db_session,
        source=espn,
        title="Late goal sends club into cup semifinal",
        url="https://espn.example.com/cup-semifinal",
        source_category="sports",
        summary="A stoppage-time goal secured a semifinal place in a domestic cup match.",
        published_at=now - timedelta(minutes=10),
        created_at=now - timedelta(minutes=10),
        category="sports",
    )
    await db_session.commit()

    async def fake_analyze_cluster(self, cluster, visual_assets=None):
        return [
            {
                "article_ids": [str(first.id), str(second.id)],
                "headline_tr": "Petrol fiyatlari Teksas arizasi sonrasi yukseliste",
                "summary_tr": "Teksas'taki rafineri arizasi petrol arzina dair kaygilari artirdi. Iki buyuk kaynak, fiyatlardaki yukselisin ayni gelismeden beslendigini aktariyor.",
                "key_points_tr": [
                    "Rafineri arizasi arz beklentilerini sIkilastirdi.",
                    "Reuters ve Bloomberg fiyatlarda yukselis bildirdi.",
                ],
                "why_it_matters_tr": "Enerji maliyetleri ve piyasa oynakligi kisa vadede etkilenebilir.",
                "confidence": 0.91,
                "video_prompt_en": "Create a sharp news explainer about oil prices rising after a Texas refinery outage.",
                "video_prompt_parts": {
                    "format_hint": "Premium financial explainer",
                    "story_angle": "Oil markets react to a Texas refinery outage",
                    "visual_brief": "Show commodity charts, refinery visuals, and urgent newsroom graphics",
                    "motion_treatment": "Use smooth chart parallax and crisp data reveals",
                    "transition_style": "Use chart morphs and panel wipes",
                    "scene_sequence": [
                        "Open with a red breaking-news chart on crude prices",
                        "Cut to refinery visuals and a Texas map",
                        "Close with a market outlook graphic",
                    ],
                    "tone": "Urgent and factual",
                    "design_keywords": ["market UI", "chart glow"],
                    "must_include": ["Texas refinery outage", "oil price spike"],
                    "avoid": ["brand logos"],
                    "duration_seconds": 34,
                },
                "video_plan": {
                    "title": "Oil prices climb after the Texas refinery outage",
                    "duration_seconds": 34,
                    "pacing_hint": "measured escalation",
                    "source_visibility": "subtle",
                    "scenes": [
                        {
                            "scene_id": "scene-1",
                            "purpose": "hook",
                            "duration_seconds": 8,
                            "layout_hint": "headline",
                            "headline": "Oil reacts fast",
                            "body": "The outage puts immediate pressure on crude expectations.",
                            "supporting_points": [],
                            "key_figures": ["Texas refinery outage", "oil price spike"],
                            "key_data": "",
                            "visual_direction": "Open with bold commodity typography over a dark market field.",
                            "motion_direction": "Use a sharp zoom with chart glow.",
                            "transition_from_previous": "Cold open",
                            "source_line": "",
                            "asset_ids": ["asset-1"],
                        },
                        {
                            "scene_id": "scene-2",
                            "purpose": "explain",
                            "duration_seconds": 9,
                            "layout_hint": "split",
                            "headline": "Why the market moved",
                            "body": "Supply concerns tightened the near-term setup for traders.",
                            "supporting_points": [
                                "The outage changed supply expectations.",
                                "Traders repriced crude higher.",
                            ],
                            "key_figures": [],
                            "key_data": "",
                            "visual_direction": "Pair a refinery silhouette with clean market labels.",
                            "motion_direction": "Use lateral panel slides.",
                            "transition_from_previous": "Panel wipe",
                            "source_line": "",
                            "asset_ids": ["asset-2"],
                        },
                        {
                            "scene_id": "scene-3",
                            "purpose": "detail",
                            "duration_seconds": 8,
                            "layout_hint": "stat",
                            "headline": "The key market signal",
                            "body": "Short-term energy pricing turned more reactive.",
                            "supporting_points": [],
                            "key_figures": ["Near-term supply concern"],
                            "key_data": "Crude higher",
                            "visual_direction": "Use a premium data card with restrained glow.",
                            "motion_direction": "Reveal the figure with a crisp counter pop.",
                            "transition_from_previous": "Chart morph",
                            "source_line": "",
                            "asset_ids": [],
                        },
                        {
                            "scene_id": "scene-4",
                            "purpose": "takeaway",
                            "duration_seconds": 9,
                            "layout_hint": "minimal",
                            "headline": "What to watch next",
                            "body": "Markets now look for how long the outage may affect supply flows.",
                            "supporting_points": [],
                            "key_figures": [],
                            "key_data": "",
                            "visual_direction": "Finish on a calm outlook frame with restrained motion.",
                            "motion_direction": "Use a soft hold and fade.",
                            "transition_from_previous": "Soft dissolve",
                            "source_line": "",
                            "asset_ids": [],
                        },
                    ],
                },
            }
        ]

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        fake_analyze_cluster,
    )

    response = await client.get(
        "/api/v1/analysis/topic-briefs",
        params={"source_category": "finance", "category": "business", "limit_topics": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_status"] == "ok"
    assert len(payload["groups"]) == 1
    assert payload["groups"][0]["category"] == "business"
    assert len(payload["groups"][0]["topics"]) == 1
    topic = payload["groups"][0]["topics"][0]
    assert topic["aggregation_type"] == "shared"
    assert topic["source_count"] == 2
    assert topic["article_count"] == 2
    assert topic["sources"] == ["Bloomberg", "Reuters"] or topic["sources"] == ["Reuters", "Bloomberg"]
    assert topic["video_prompt_parts"]["duration_seconds"] == 30
    assert topic["video_prompt_parts"]["format_hint"] == "Premium financial explainer"
    assert "Use Remotion best practices." in topic["video_prompt_en"]
    assert "Look and feel:" in topic["video_prompt_en"]
    assert "Helpful story anchors:" in topic["video_prompt_en"]
    assert "Texas refinery outage" in topic["video_prompt_en"]
    assert topic["video_plan"]["duration_seconds"] == 30
    assert len(topic["video_plan"]["scenes"]) == 2
    assert topic["video_plan"]["scenes"][0]["purpose"] == "hook"
    assert topic["video_plan"]["scenes"][1]["purpose"] == "explain"
    assert len(topic["visual_assets"]) == 2
    assert topic["visual_assets"][0]["kind"] == "article_image"
    assert topic["video_plan"]["scenes"][0]["asset_ids"] == ["asset-1"]
    assert topic["remotion_storyboard"]["visual_thesis"]
    assert len(topic["remotion_storyboard"]["scenes"]) == 2
    assert topic["remotion_storyboard"]["scenes"][0]["scene_type"] == "hook"
    assert topic["remotion_storyboard"]["scenes"][1]["scene_type"] == "story"


@pytest.mark.asyncio
async def test_topic_briefs_endpoint_degrades_when_ollama_is_unavailable(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    guardian = await create_source(db_session, slug="guardian", name="The Guardian", category="general")
    bbc = await create_source(db_session, slug="bbc", name="BBC News", category="general")

    await create_article(
        db_session,
        source=guardian,
        title="Ceasefire talks resume after overnight strikes",
        url="https://guardian.example.com/ceasefire-talks",
        source_category="general",
        summary="Negotiators resumed talks after overnight strikes raised pressure on both sides.",
        published_at=now - timedelta(minutes=28),
        created_at=now - timedelta(minutes=28),
        category="world",
        image_url="https://cdn.example.com/guardian-ceasefire.jpg",
    )
    await create_article(
        db_session,
        source=bbc,
        title="Negotiators return to ceasefire talks following overnight strikes",
        url="https://bbc.example.com/ceasefire-talks",
        source_category="general",
        summary="Fresh strikes were followed by renewed ceasefire talks, according to officials and mediators.",
        published_at=now - timedelta(minutes=20),
        created_at=now - timedelta(minutes=20),
        category="world",
        image_url="https://cdn.example.com/bbc-ceasefire.jpg",
    )
    await db_session.commit()

    async def raise_ollama_error(self, cluster, visual_assets=None):
        raise OllamaAnalysisError("ollama unavailable")

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        raise_ollama_error,
    )

    response = await client.get("/api/v1/analysis/topic-briefs", params={"include_review": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_status"] == "degraded"
    assert len(payload["groups"]) == 1
    topic = payload["groups"][0]["topics"][0]
    assert topic["aggregation_type"] == "shared"
    assert topic["quality_status"] == "review"
    assert topic["source_count"] == 2
    assert "Use Remotion best practices." in topic["video_prompt_en"]
    assert "Create a " in topic["video_prompt_en"]
    assert "Do not force sources, logos, screenshots, or maps" in topic["video_prompt_en"]
    assert "BBC News" not in topic["summary_tr"]
    assert "The Guardian" not in topic["summary_tr"]
    assert topic["video_plan"]["source_visibility"] == "none"
    assert 1 <= len(topic["video_plan"]["scenes"]) <= 3
    assert topic["video_plan"]["duration_seconds"] <= 30
    assert all(scene["source_line"] == "" for scene in topic["video_plan"]["scenes"])
    assert len(topic["visual_assets"]) == 2
    assert topic["remotion_storyboard"]["visual_thesis"]
    assert len(topic["remotion_storyboard"]["scenes"]) == len(topic["video_plan"]["scenes"])


@pytest.mark.asyncio
async def test_topic_briefs_endpoint_returns_unique_topics_for_single_source_clusters(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    reuters = await create_source(db_session, slug="reuters", name="Reuters", category="general")

    first = await create_article(
        db_session,
        source=reuters,
        title="Court delays ruling in major antitrust case",
        url="https://reuters.example.com/antitrust-case-1",
        source_category="general",
        summary="A court delayed its ruling in a closely watched antitrust case.",
        published_at=now - timedelta(minutes=22),
        created_at=now - timedelta(minutes=22),
        category="business",
        image_url="https://cdn.example.com/reuters-antitrust-1.jpg",
    )
    second = await create_article(
        db_session,
        source=reuters,
        title="Major antitrust ruling delayed by court",
        url="https://reuters.example.com/antitrust-case-2",
        source_category="general",
        summary="The same antitrust case was delayed by the court, according to Reuters coverage.",
        published_at=now - timedelta(minutes=12),
        created_at=now - timedelta(minutes=12),
        category="business",
        image_url="https://cdn.example.com/reuters-antitrust-2.jpg",
    )
    await db_session.commit()

    async def fake_analyze_cluster(self, cluster, visual_assets=None):
        return [
            {
                "article_ids": [str(first.id), str(second.id)],
                "headline_tr": "Mahkeme kritik antitrust kararini erteledi",
                "summary_tr": "Tek kaynakta yer alan benzer iki yazi mahkeme kararinin ertelendigini aktariyor.",
                "key_points_tr": ["Karar ertelendi"],
                "why_it_matters_tr": "Dava takvimi degisti.",
                "confidence": 0.6,
                "video_prompt_en": "Create a short explainer about the delayed antitrust ruling.",
                "video_prompt_parts": {
                    "format_hint": "Editorial legal explainer",
                    "story_angle": "Delayed antitrust ruling",
                    "visual_brief": "Use courtroom visuals",
                    "motion_treatment": "Use deliberate card reveals",
                    "transition_style": "Use minimal wipe transitions",
                    "scene_sequence": ["Headline card", "Court sketch", "Timeline slide"],
                    "tone": "Factual",
                    "design_keywords": ["courtroom", "editorial type"],
                    "must_include": ["Delayed ruling"],
                    "avoid": ["logos"],
                    "duration_seconds": 30,
                },
            }
        ]

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        fake_analyze_cluster,
    )

    response = await client.get("/api/v1/analysis/topic-briefs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_status"] == "ok"
    assert len(payload["groups"]) == 1
    topic = payload["groups"][0]["topics"][0]
    assert topic["aggregation_type"] == "unique"
    assert topic["quality_status"] == "publishable"
    assert topic["source_count"] == 1
    assert topic["article_count"] == 2
    assert "Tek kaynak" not in topic["summary_tr"]
    assert "multiple sources" not in topic["video_prompt_en"].lower()


@pytest.mark.asyncio
async def test_topic_briefs_endpoint_debug_reports_single_source_cluster_reason(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    yahoo = await create_source(db_session, slug="yahoosports", name="Yahoo Sports", category="sports")

    await create_article(
        db_session,
        source=yahoo,
        title="Inter Milan defender remains under scrutiny after setback",
        url="https://sports.yahoo.com/inter-setback-1",
        source_category="sports",
        summary="Inter Milan defender remains in focus after another difficult outing.",
        published_at=now - timedelta(minutes=14),
        created_at=now - timedelta(minutes=14),
        category="sports",
        image_url="https://cdn.example.com/yahoo-inter-1.jpg",
    )
    await create_article(
        db_session,
        source=yahoo,
        title="Inter Milan defender faces fresh scrutiny after latest setback",
        url="https://sports.yahoo.com/inter-setback-2",
        source_category="sports",
        summary="Another report revisits the same defender and the latest setback for Inter Milan.",
        published_at=now - timedelta(minutes=10),
        created_at=now - timedelta(minutes=10),
        category="sports",
        image_url="https://cdn.example.com/yahoo-inter-2.jpg",
    )
    await db_session.commit()

    async def should_not_run(self, cluster, visual_assets=None):
        raise AssertionError("single-source clusters should not reach Ollama")

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        should_not_run,
    )

    response = await client.get("/api/v1/analysis/topic-briefs", params={"hours": 6, "debug": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_status"] == "ok"
    assert len(payload["groups"]) == 1
    assert payload["groups"][0]["topics"][0]["aggregation_type"] == "unique"
    assert payload["groups"][0]["topics"][0]["quality_status"] == "publishable"
    assert payload["debug"]["candidate_clusters"] >= 1
    assert payload["debug"]["single_source_clusters"] >= 1
    assert payload["debug"]["multi_source_clusters"] == 0
    assert payload["debug"]["unique_topics_generated"] >= 1
    assert any("unique" in note.lower() for note in payload["debug"]["notes"])


@pytest.mark.asyncio
async def test_topic_briefs_endpoint_returns_unique_topic_for_unclustered_single_article(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    ap = await create_source(db_session, slug="ap", name="AP News", category="general")

    await create_article(
        db_session,
        source=ap,
        title="Mayor announces flood cleanup fund after weekend damage",
        url="https://ap.example.com/flood-fund",
        source_category="general",
        summary="A mayor announced a cleanup fund after severe weekend flood damage.",
        published_at=now - timedelta(minutes=18),
        created_at=now - timedelta(minutes=18),
        category="general",
        image_url="https://cdn.example.com/ap-flood-fund.jpg",
    )
    await db_session.commit()

    async def should_not_run(self, cluster, visual_assets=None):
        raise AssertionError("unique single-article topics should not reach Ollama")

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        should_not_run,
    )

    response = await client.get("/api/v1/analysis/topic-briefs", params={"hours": 3})

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_status"] == "ok"
    assert len(payload["groups"]) == 1
    topic = payload["groups"][0]["topics"][0]
    assert topic["aggregation_type"] == "unique"
    assert topic["quality_status"] == "publishable"
    assert topic["source_count"] == 1
    assert topic["article_count"] == 1
    assert len(topic["representative_articles"]) == 1


@pytest.mark.asyncio
async def test_topic_briefs_endpoint_excludes_review_topics_by_default(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    ap = await create_source(db_session, slug="ap-review", name="AP Review", category="general")

    await create_article(
        db_session,
        source=ap,
        title="Mayor announces flood cleanup fund after weekend damage",
        url="https://ap-review.example.com/flood-fund",
        source_category="general",
        summary="A mayor announced a cleanup fund after severe weekend flood damage.",
        published_at=now - timedelta(minutes=18),
        created_at=now - timedelta(minutes=18),
        category="general",
    )
    await db_session.commit()

    async def should_not_run(self, cluster, visual_assets=None):
        raise AssertionError("single-source unique topics should not reach Ollama")

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        should_not_run,
    )

    response = await client.get("/api/v1/analysis/topic-briefs", params={"hours": 3, "debug": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["groups"] == []
    assert payload["debug"]["publishable_topics_generated"] == 0
    assert payload["debug"]["review_topics_generated"] == 1
    review_breakdown = {item["reason"]: item["count"] for item in payload["debug"]["review_breakdown"]}
    assert review_breakdown["single_source_topic"] >= 1
    assert review_breakdown["missing_visual_asset"] >= 1


@pytest.mark.asyncio
async def test_topic_briefs_endpoint_include_review_returns_review_topics_after_publishable_topics(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    ap = await create_source(db_session, slug="ap-publishable", name="AP Publishable", category="general")
    reuters = await create_source(db_session, slug="reuters-review", name="Reuters Review", category="general")

    await create_article(
        db_session,
        source=ap,
        title="City opens overnight cooling centers ahead of heatwave",
        url="https://ap-publishable.example.com/cooling-centers",
        source_category="general",
        summary="Officials opened overnight cooling centers ahead of a fast-moving heatwave.",
        published_at=now - timedelta(minutes=12),
        created_at=now - timedelta(minutes=12),
        category="general",
        image_url="https://cdn.example.com/ap-cooling-review-test.jpg",
    )
    await create_article(
        db_session,
        source=reuters,
        title="Mayor announces flood cleanup fund after weekend damage",
        url="https://reuters-review.example.com/flood-fund",
        source_category="general",
        summary="A mayor announced a cleanup fund after severe weekend flood damage.",
        published_at=now - timedelta(minutes=8),
        created_at=now - timedelta(minutes=8),
        category="general",
    )
    await db_session.commit()

    async def should_not_run(self, cluster, visual_assets=None):
        raise AssertionError("single-source unique topics should not reach Ollama")

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        should_not_run,
    )

    response = await client.get(
        "/api/v1/analysis/topic-briefs",
        params={"hours": 3, "include_review": True, "debug": True},
    )

    assert response.status_code == 200
    payload = response.json()
    topics = [topic for group in payload["groups"] for topic in group["topics"]]
    assert len(topics) == 2
    assert topics[0]["quality_status"] == "publishable"
    assert topics[1]["quality_status"] == "review"
    assert topics[0]["quality_score"] > topics[1]["quality_score"]
    assert payload["debug"]["publishable_topics_generated"] == 1
    assert payload["debug"]["review_topics_generated"] == 1


@pytest.mark.asyncio
async def test_topic_briefs_endpoint_filters_non_news_utility_pages_from_unique_topics(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    bloomberg = await create_source(db_session, slug="bloomberg", name="Bloomberg", category="finance")
    ap = await create_source(db_session, slug="ap", name="AP News", category="general")

    for title, url in [
        ("subscriptions", "https://www.bloomberg.com/subscriptions"),
        ("workwise", "https://www.bloomberg.com/workwise"),
        ("wealthscore financial health calculator", "https://www.bloomberg.com/wealthscore-financial-health-calculator"),
    ]:
        await create_article(
            db_session,
            source=bloomberg,
            title=title,
            url=url,
            source_category="finance",
            summary=title,
            published_at=now - timedelta(minutes=8),
            created_at=now - timedelta(minutes=8),
            category="business",
        )

    await create_article(
        db_session,
        source=ap,
        title="Mayor announces flood cleanup fund after weekend damage",
        url="https://ap.example.com/2026/04/02/flood-cleanup-fund",
        source_category="general",
        summary="A mayor announced a cleanup fund after severe weekend flood damage.",
        published_at=now - timedelta(minutes=6),
        created_at=now - timedelta(minutes=6),
        category="general",
        image_url="https://cdn.example.com/ap-cleanup-fund.jpg",
    )
    await db_session.commit()

    async def should_not_run(self, cluster, visual_assets=None):
        raise AssertionError("single-source unique topics should not reach Ollama")

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        should_not_run,
    )

    response = await client.get("/api/v1/analysis/topic-briefs", params={"hours": 3, "debug": True})

    assert response.status_code == 200
    payload = response.json()
    topics = [topic for group in payload["groups"] for topic in group["topics"]]
    assert len(topics) == 1
    assert topics[0]["headline_tr"] == "Mayor announces flood cleanup fund after weekend damage"
    assert topics[0]["quality_status"] == "publishable"
    assert topics[0]["quality_score"] > 0.7
    assert payload["debug"]["rejected_articles"] >= 3
    assert payload["debug"]["rejected_unique_candidates"] == 0
    rejection_breakdown = {item["reason"]: item["count"] for item in payload["debug"]["rejection_breakdown"]}
    assert rejection_breakdown["utility_or_hub_page"] >= 3


@pytest.mark.asyncio
async def test_topic_briefs_endpoint_rejects_old_year_evergreen_title_in_recent_window(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    bloomberg = await create_source(db_session, slug="bloomberg", name="Bloomberg", category="finance")

    await create_article(
        db_session,
        source=bloomberg,
        title="2020 China consumer outlook special report",
        url="https://www.bloomberg.com/articles/2020-china-consumer-outlook-special-report-123456",
        source_category="finance",
        summary="An old evergreen feature surfaced in a recent scrape.",
        published_at=now - timedelta(minutes=7),
        created_at=now - timedelta(minutes=7),
        category="business",
    )
    await db_session.commit()

    async def should_not_run(self, cluster, visual_assets=None):
        raise AssertionError("single-source unique topics should not reach Ollama")

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        should_not_run,
    )

    response = await client.get("/api/v1/analysis/topic-briefs", params={"hours": 3, "debug": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["groups"] == []
    rejection_breakdown = {item["reason"]: item["count"] for item in payload["debug"]["rejection_breakdown"]}
    assert rejection_breakdown["stale_or_evergreen"] >= 1


@pytest.mark.asyncio
async def test_topic_briefs_endpoint_decodes_html_entities_without_leaking_numeric_artifacts(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    sky = await create_source(db_session, slug="skysports", name="Sky Sports", category="sports")

    await create_article(
        db_session,
        source=sky,
        title="Wilder gunning for Usyk: 'It can and will happen'",
        url="https://www.skysports.com/boxing/news/2026/04/02/wilder-usyk-it-can-and-will-happen",
        source_category="sports",
        summary="Deontay Wilder believes he&#8217;s one victory away from challenging unified heavyweight champion Oleksandr Usyk.",
        published_at=now - timedelta(minutes=5),
        created_at=now - timedelta(minutes=5),
        category="sports",
        image_url="https://example.com/wilder.jpg",
    )
    await db_session.commit()

    async def should_not_run(self, cluster, visual_assets=None):
        raise AssertionError("single-source unique topics should not reach Ollama")

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        should_not_run,
    )

    response = await client.get("/api/v1/analysis/topic-briefs", params={"hours": 3, "debug": True})

    assert response.status_code == 200
    payload = response.json()
    topic = payload["groups"][0]["topics"][0]
    assert "8217" not in topic["summary_tr"]
    assert "8217" not in topic["video_content"]["key_data"]
    assert "he's one victory away" in topic["summary_tr"].lower()
    assert payload["debug"]["rejected_articles"] == 0


@pytest.mark.asyncio
async def test_topic_quality_report_endpoint_summarizes_publishable_review_and_rejections(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    guardian = await create_source(db_session, slug="guardian-report", name="The Guardian", category="general")
    bbc = await create_source(db_session, slug="bbc-report", name="BBC News", category="general")
    ap = await create_source(db_session, slug="ap-report", name="AP News", category="general")
    bloomberg = await create_source(db_session, slug="bloomberg-report", name="Bloomberg", category="finance")

    await create_article(
        db_session,
        source=guardian,
        title="Ceasefire talks resume after overnight strikes",
        url="https://guardian-report.example.com/ceasefire-talks",
        source_category="general",
        summary="Negotiators resumed talks after overnight strikes raised pressure on both sides.",
        published_at=now - timedelta(minutes=28),
        created_at=now - timedelta(minutes=28),
        category="world",
        image_url="https://cdn.example.com/guardian-report.jpg",
    )
    await create_article(
        db_session,
        source=bbc,
        title="Negotiators return to ceasefire talks following overnight strikes",
        url="https://bbc-report.example.com/ceasefire-talks",
        source_category="general",
        summary="Fresh strikes were followed by renewed ceasefire talks, according to officials and mediators.",
        published_at=now - timedelta(minutes=20),
        created_at=now - timedelta(minutes=20),
        category="world",
        image_url="https://cdn.example.com/bbc-report.jpg",
    )
    await create_article(
        db_session,
        source=ap,
        title="City opens overnight cooling centers ahead of heatwave",
        url="https://ap-report.example.com/cooling-centers",
        source_category="general",
        summary="Officials opened overnight cooling centers ahead of a fast-moving heatwave.",
        published_at=now - timedelta(minutes=12),
        created_at=now - timedelta(minutes=12),
        category="general",
        image_url="https://cdn.example.com/ap-report.jpg",
    )
    await create_article(
        db_session,
        source=bloomberg,
        title="subscriptions",
        url="https://www.bloomberg.com/subscriptions",
        source_category="finance",
        summary="subscriptions",
        published_at=now - timedelta(minutes=7),
        created_at=now - timedelta(minutes=7),
        category="business",
    )
    await db_session.commit()

    async def raise_ollama_error(self, cluster, visual_assets=None):
        raise OllamaAnalysisError("ollama unavailable")

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        raise_ollama_error,
    )

    response = await client.get("/api/v1/analysis/topic-quality-report", params={"hours": 3})

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_status"] == "degraded"
    assert payload["ollama_error"] == "ollama unavailable"
    assert payload["totals"]["publishable_topics"] == 1
    assert payload["totals"]["review_topics"] == 1
    assert payload["totals"]["rejected_articles"] == 1
    assert payload["totals"]["shared_topics"] == 1
    assert payload["totals"]["unique_topics"] == 1
    assert payload["totals"]["avg_quality_score"] > 0
    assert payload["totals"]["publishable_avg_quality_score"] > 0
    assert payload["totals"]["review_avg_quality_score"] > 0
    assert sum(item["count"] for item in payload["totals"]["score_distribution"]) == 2

    rejection_breakdown = {item["reason"]: item["count"] for item in payload["totals"]["rejection_breakdown"]}
    assert rejection_breakdown["utility_or_hub_page"] >= 1
    review_breakdown = {item["reason"]: item["count"] for item in payload["totals"]["review_breakdown"]}
    assert review_breakdown["degraded_generation"] >= 1

    sources = {item["source_slug"]: item for item in payload["sources"]}
    assert sources["guardian-report"]["review_contributions"] == 1
    assert sources["guardian-report"]["shared_contributions"] == 1
    assert sources["guardian-report"]["review_avg_quality_score"] > 0
    assert sources["bbc-report"]["review_contributions"] == 1
    assert sources["ap-report"]["publishable_contributions"] == 1
    assert sources["ap-report"]["unique_contributions"] == 1
    assert sources["ap-report"]["avg_quality_score"] > 0
    assert sources["bloomberg-report"]["rejected_article_count"] == 1
    assert sources["bloomberg-report"]["sample_rejections"][0]["reason"] == "utility_or_hub_page"
    assert sources["guardian-report"]["lowest_scoring_topics"][0]["quality_status"] == "review"
    assert payload["sources"][0]["source_slug"] == "bloomberg-report"
    assert payload["sources"][-1]["source_slug"] == "ap-report"
    assert payload["totals"]["feedback_count"] == 0
    assert payload["totals"]["feedback_coverage_percent"] == 0
    assert payload["totals"]["feedback_breakdown"] == []


@pytest.mark.asyncio
async def test_topic_briefs_endpoint_limit_topics_applies_to_final_shared_and_unique_pool(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    reuters = await create_source(db_session, slug="reuters", name="Reuters", category="finance")
    bloomberg = await create_source(db_session, slug="bloomberg", name="Bloomberg", category="finance")
    ap = await create_source(db_session, slug="ap", name="AP News", category="general")

    shared_first = await create_article(
        db_session,
        source=reuters,
        title="Oil rises after refinery disruption",
        url="https://reuters.example.com/oil-disruption",
        source_category="finance",
        summary="Oil prices rose after a refinery disruption tightened supply expectations.",
        published_at=now - timedelta(minutes=20),
        created_at=now - timedelta(minutes=20),
        category="business",
        image_url="https://cdn.example.com/reuters-oil-shared.jpg",
    )
    shared_second = await create_article(
        db_session,
        source=bloomberg,
        title="Refinery disruption lifts crude prices",
        url="https://bloomberg.example.com/oil-disruption",
        source_category="finance",
        summary="A second report said crude rose after refinery issues tightened supply outlook.",
        published_at=now - timedelta(minutes=17),
        created_at=now - timedelta(minutes=17),
        category="business",
        image_url="https://cdn.example.com/bloomberg-oil-shared.jpg",
    )
    await create_article(
        db_session,
        source=ap,
        title="City opens overnight cooling centers ahead of heatwave",
        url="https://ap.example.com/heatwave-centers",
        source_category="general",
        summary="Officials opened overnight cooling centers ahead of a fast-moving heatwave.",
        published_at=now - timedelta(minutes=12),
        created_at=now - timedelta(minutes=12),
        category="general",
        image_url="https://cdn.example.com/ap-cooling-centers.jpg",
    )
    await db_session.commit()

    async def fake_analyze_cluster(self, cluster, visual_assets=None):
        return [
            {
                "article_ids": [str(shared_first.id), str(shared_second.id)],
                "headline_tr": "Rafineri aksakligi petrolu yukseltti",
                "summary_tr": "Rafineri aksakligi petrol fiyatlarini yukari itti ve enerji piyasasinda kisa vadeli arz baskisi yaratti.",
                "key_points_tr": ["Petrol yukseliste"],
                "why_it_matters_tr": "Enerji piyasasi etkilenebilir.",
                "confidence": 0.9,
                "video_prompt_en": "Create a concise oil-market update.",
                "video_prompt_parts": {
                    "format_hint": "Premium financial explainer",
                    "story_angle": "Oil reacts to refinery disruption",
                    "visual_brief": "Use clean chart-led visuals",
                    "motion_treatment": "Use subtle chart motion",
                    "transition_style": "Use panel wipes",
                    "scene_sequence": ["Chart opener", "Brief impact panel"],
                    "tone": "Factual",
                    "design_keywords": ["market ui"],
                    "must_include": ["oil rise"],
                    "avoid": ["logos"],
                    "duration_seconds": 18,
                },
                "video_plan": {
                    "title": "Oil rises after refinery disruption",
                    "duration_seconds": 18,
                    "pacing_hint": "balanced",
                    "source_visibility": "none",
                    "scenes": [
                        {
                            "scene_id": "scene-1",
                            "purpose": "hook",
                            "duration_seconds": 10,
                            "layout_hint": "headline",
                            "headline": "Oil rises after refinery disruption",
                            "body": "Supply concerns quickly lifted crude prices.",
                            "supporting_points": [],
                            "key_figures": [],
                            "key_data": "",
                            "visual_direction": "",
                            "motion_direction": "",
                            "transition_from_previous": "Cold open",
                            "source_line": "",
                            "asset_ids": [],
                        }
                    ],
                },
            }
        ]

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        fake_analyze_cluster,
    )

    response = await client.get("/api/v1/analysis/topic-briefs", params={"hours": 3, "limit_topics": 2, "debug": True})

    assert response.status_code == 200
    payload = response.json()
    topics = [topic for group in payload["groups"] for topic in group["topics"]]
    assert len(topics) == 2
    assert topics[0]["aggregation_type"] == "shared"
    assert topics[0]["quality_status"] == "publishable"
    assert topics[1]["aggregation_type"] == "unique"
    assert topics[1]["quality_status"] == "publishable"
    assert topics[0]["quality_score"] > topics[1]["quality_score"]
    assert payload["debug"]["shared_topics_generated"] >= 1
    assert payload["debug"]["unique_topics_generated"] >= 1


@pytest.mark.asyncio
async def test_topic_briefs_endpoint_groups_sorted_by_highest_quality_score(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    reuters = await create_source(db_session, slug="reuters-groups", name="Reuters Groups", category="finance")
    bloomberg = await create_source(db_session, slug="bloomberg-groups", name="Bloomberg Groups", category="finance")
    ap = await create_source(db_session, slug="ap-groups", name="AP Groups", category="general")

    shared_first = await create_article(
        db_session,
        source=reuters,
        title="Oil rises after refinery disruption",
        url="https://reuters-groups.example.com/oil-disruption",
        source_category="finance",
        summary="Oil prices rose after a refinery disruption tightened supply expectations.",
        published_at=now - timedelta(minutes=20),
        created_at=now - timedelta(minutes=20),
        category="business",
        image_url="https://cdn.example.com/reuters-groups-oil.jpg",
    )
    shared_second = await create_article(
        db_session,
        source=bloomberg,
        title="Refinery disruption lifts crude prices",
        url="https://bloomberg-groups.example.com/oil-disruption",
        source_category="finance",
        summary="Crude rose after refinery issues tightened the supply outlook.",
        published_at=now - timedelta(minutes=18),
        created_at=now - timedelta(minutes=18),
        category="business",
        image_url="https://cdn.example.com/bloomberg-groups-oil.jpg",
    )
    await create_article(
        db_session,
        source=ap,
        title="City opens cooling centers before overnight heatwave",
        url="https://ap-groups.example.com/cooling-centers",
        source_category="general",
        summary="Officials opened cooling centers before an overnight heatwave.",
        published_at=now - timedelta(minutes=9),
        created_at=now - timedelta(minutes=9),
        category="general",
    )
    await db_session.commit()

    async def fake_analyze_cluster(self, cluster, visual_assets=None):
        return [
            {
                "article_ids": [str(shared_first.id), str(shared_second.id)],
                "headline_tr": "Rafineri aksakligi petrolu yukseltti",
                "summary_tr": "Rafineri aksakligi petrol fiyatlarini yukari itti ve enerji piyasasinda arz baskisi yaratti.",
                "key_points_tr": ["Petrol fiyatlari yukseliste."],
                "why_it_matters_tr": "Enerji piyasasi kisa vadede etkilenebilir.",
            }
        ]

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        fake_analyze_cluster,
    )

    response = await client.get(
        "/api/v1/analysis/topic-briefs",
        params={"hours": 3, "include_review": True, "debug": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["groups"][0]["category"] == "business"
    assert payload["groups"][1]["category"] == "general"
    assert payload["groups"][0]["topics"][0]["quality_score"] > payload["groups"][1]["topics"][0]["quality_score"]


@pytest.mark.asyncio
async def test_topic_feedback_endpoints_upsert_hydrate_and_delete(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    ap = await create_source(db_session, slug="ap-feedback", name="AP Feedback", category="general")

    await create_article(
        db_session,
        source=ap,
        title="City opens overnight cooling centers ahead of heatwave",
        url="https://ap-feedback.example.com/cooling-centers",
        source_category="general",
        summary="Officials opened overnight cooling centers ahead of a fast-moving heatwave.",
        published_at=now - timedelta(minutes=12),
        created_at=now - timedelta(minutes=12),
        category="general",
        image_url="https://cdn.example.com/ap-feedback-cooling.jpg",
    )
    await db_session.commit()

    async def should_not_run(self, cluster, visual_assets=None):
        raise AssertionError("single-source unique topics should not reach Ollama")

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        should_not_run,
    )

    initial_response = await client.get("/api/v1/analysis/topic-briefs", params={"hours": 3})
    assert initial_response.status_code == 200
    initial_topic = initial_response.json()["groups"][0]["topics"][0]
    assert initial_topic["latest_feedback"] is None

    payload = {
        "topic_id": initial_topic["topic_id"],
        "feedback_label": "approved",
        "note": "Looks ready for internal curation.",
        "topic_snapshot": {
            "headline_tr": initial_topic["headline_tr"],
            "summary_tr": initial_topic["summary_tr"],
            "category": initial_topic["category"],
            "aggregation_type": initial_topic["aggregation_type"],
            "quality_status": initial_topic["quality_status"],
            "quality_score": initial_topic["quality_score"],
            "source_count": initial_topic["source_count"],
            "article_count": initial_topic["article_count"],
            "sources": initial_topic["sources"],
            "source_slugs": [
                article["source_slug"]
                for article in initial_topic["representative_articles"]
                if article.get("source_slug")
            ],
            "review_reasons": initial_topic["review_reasons"],
            "representative_article_ids": [
                article["id"] for article in initial_topic["representative_articles"]
            ],
            "has_visual_asset": bool(initial_topic["visual_assets"]),
            "has_published_at": any(
                article.get("published_at") for article in initial_topic["representative_articles"]
            ),
        },
    }

    save_response = await client.put("/api/v1/analysis/topic-feedback", json=payload)
    assert save_response.status_code == 200
    assert save_response.json()["latest_feedback"]["label"] == "approved"

    payload["feedback_label"] = "wrong"
    payload["note"] = "The wording still feels misleading."
    overwrite_response = await client.put("/api/v1/analysis/topic-feedback", json=payload)
    assert overwrite_response.status_code == 200
    assert overwrite_response.json()["latest_feedback"]["label"] == "wrong"
    assert overwrite_response.json()["latest_feedback"]["note"] == "The wording still feels misleading."

    count_query = await db_session.execute(select(func.count()).select_from(TopicFeedback))
    assert count_query.scalar_one() == 1

    refreshed_response = await client.get("/api/v1/analysis/topic-briefs", params={"hours": 3})
    assert refreshed_response.status_code == 200
    refreshed_topic = refreshed_response.json()["groups"][0]["topics"][0]
    assert refreshed_topic["latest_feedback"]["label"] == "wrong"
    assert refreshed_topic["latest_feedback"]["note"] == "The wording still feels misleading."

    delete_response = await client.delete(f"/api/v1/analysis/topic-feedback/{initial_topic['topic_id']}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"topic_id": initial_topic["topic_id"], "deleted": True}

    final_response = await client.get("/api/v1/analysis/topic-briefs", params={"hours": 3})
    assert final_response.status_code == 200
    final_topic = final_response.json()["groups"][0]["topics"][0]
    assert final_topic["latest_feedback"] is None


@pytest.mark.asyncio
async def test_topic_quality_report_endpoint_includes_feedback_coverage(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    ap = await create_source(db_session, slug="ap-feedback-report", name="AP Feedback Report", category="general")
    reuters = await create_source(
        db_session, slug="reuters-feedback-report", name="Reuters Feedback Report", category="general"
    )

    await create_article(
        db_session,
        source=ap,
        title="City opens overnight cooling centers ahead of heatwave",
        url="https://ap-feedback-report.example.com/cooling-centers",
        source_category="general",
        summary="Officials opened overnight cooling centers ahead of a fast-moving heatwave.",
        published_at=now - timedelta(minutes=12),
        created_at=now - timedelta(minutes=12),
        category="general",
        image_url="https://cdn.example.com/ap-feedback-report-cooling.jpg",
    )
    await create_article(
        db_session,
        source=reuters,
        title="Mayor announces flood cleanup fund after weekend damage",
        url="https://reuters-feedback-report.example.com/flood-fund",
        source_category="general",
        summary="A mayor announced a cleanup fund after severe weekend flood damage.",
        published_at=now - timedelta(minutes=8),
        created_at=now - timedelta(minutes=8),
        category="general",
    )
    await db_session.commit()

    async def should_not_run(self, cluster, visual_assets=None):
        raise AssertionError("single-source unique topics should not reach Ollama")

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        should_not_run,
    )

    topics_response = await client.get(
        "/api/v1/analysis/topic-briefs",
        params={"hours": 3, "include_review": True},
    )
    assert topics_response.status_code == 200
    topics = [topic for group in topics_response.json()["groups"] for topic in group["topics"]]
    assert len(topics) == 2

    publishable_topic = next(topic for topic in topics if topic["quality_status"] == "publishable")
    feedback_payload = {
        "topic_id": publishable_topic["topic_id"],
        "feedback_label": "approved",
        "note": "Strong enough for internal publishing.",
        "topic_snapshot": {
            "headline_tr": publishable_topic["headline_tr"],
            "summary_tr": publishable_topic["summary_tr"],
            "category": publishable_topic["category"],
            "aggregation_type": publishable_topic["aggregation_type"],
            "quality_status": publishable_topic["quality_status"],
            "quality_score": publishable_topic["quality_score"],
            "source_count": publishable_topic["source_count"],
            "article_count": publishable_topic["article_count"],
            "sources": publishable_topic["sources"],
            "source_slugs": [
                article["source_slug"]
                for article in publishable_topic["representative_articles"]
                if article.get("source_slug")
            ],
            "review_reasons": publishable_topic["review_reasons"],
            "representative_article_ids": [
                article["id"] for article in publishable_topic["representative_articles"]
            ],
            "has_visual_asset": bool(publishable_topic["visual_assets"]),
            "has_published_at": any(
                article.get("published_at") for article in publishable_topic["representative_articles"]
            ),
        },
    }
    save_response = await client.put("/api/v1/analysis/topic-feedback", json=feedback_payload)
    assert save_response.status_code == 200

    report_response = await client.get("/api/v1/analysis/topic-quality-report", params={"hours": 3})
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["totals"]["feedback_count"] == 1
    assert report["totals"]["feedback_coverage_percent"] == 50.0
    assert report["totals"]["feedback_breakdown"] == [{"label": "approved", "count": 1}]


@pytest.mark.asyncio
async def test_topic_score_tuning_report_requires_minimum_feedback_thresholds(
    client,
    db_session: AsyncSession,
) -> None:
    for index in range(10):
        await create_topic_feedback_record(
            db_session,
            topic_id=f"under-threshold-{index}",
            feedback_label="approved" if index % 2 == 0 else "wrong",
            quality_score=0.7 if index % 2 == 0 else 0.35,
        )
    await db_session.commit()

    response = await client.get("/api/v1/analysis/topic-score-tuning-report", params={"days": 30})

    assert response.status_code == 200
    payload = response.json()
    assert payload["totals"]["feedback_count"] == 10
    assert payload["totals"]["eligible_for_recommendations"] is False
    assert payload["recommendations"] == []
    assert any("Not enough feedback yet" in note for note in payload["notes"])
    assert any("Thresholds:" in note for note in payload["notes"])


@pytest.mark.asyncio
async def test_topic_score_tuning_report_generates_recommendations_and_mismatch_samples(
    client,
    db_session: AsyncSession,
) -> None:
    for index in range(20):
        await create_topic_feedback_record(
            db_session,
            topic_id=f"approved-shared-{index}",
            feedback_label="approved",
            aggregation_type="shared",
            quality_status="publishable",
            quality_score=0.42 if index == 0 else 0.86,
            score_features={
                "shared_topic": True,
                "unique_topic": False,
                "source_count_ge_2": True,
                "source_count_ge_3": False,
                "has_visual_asset": True,
                "missing_visual_asset": False,
                "non_thin_summary": True,
                "thin_summary": False,
                "non_truncated_headline": True,
                "truncated_headline": False,
                "has_published_at": True,
                "missing_published_at": False,
                "article_count_ge_2": True,
                "degraded_generation": False,
                "review_status": False,
            },
        )

    for index in range(20):
        await create_topic_feedback_record(
            db_session,
            topic_id=f"negative-unique-{index}",
            feedback_label="wrong" if index % 2 == 0 else "boring",
            aggregation_type="unique",
            quality_status="review",
            quality_score=0.82 if index == 0 else 0.28,
            source_count=1,
            article_count=1,
            review_reasons=["single_source_topic"],
            score_features={
                "shared_topic": False,
                "unique_topic": True,
                "source_count_ge_2": False,
                "source_count_ge_3": False,
                "has_visual_asset": False,
                "missing_visual_asset": True,
                "non_thin_summary": False,
                "thin_summary": True,
                "non_truncated_headline": True,
                "truncated_headline": False,
                "has_published_at": True,
                "missing_published_at": False,
                "article_count_ge_2": False,
                "degraded_generation": False,
                "review_status": True,
            },
        )
    await db_session.commit()

    response = await client.get("/api/v1/analysis/topic-score-tuning-report", params={"days": 30})

    assert response.status_code == 200
    payload = response.json()
    assert payload["totals"]["feedback_count"] == 40
    assert payload["totals"]["approved_count"] == 20
    assert payload["totals"]["negative_count"] == 20
    assert payload["totals"]["eligible_for_recommendations"] is True

    recommendations = {item["feature"]: item for item in payload["recommendations"]}
    assert "shared_topic" in recommendations
    assert recommendations["shared_topic"]["delta"] == pytest.approx(0.03)
    assert recommendations["shared_topic"]["recommended_weight"] > recommendations["shared_topic"]["current_weight"]

    assert payload["calibration_summary"]["high_score_negative_count"] >= 1
    assert payload["calibration_summary"]["low_score_approved_count"] >= 1
    assert payload["mismatch_samples"]["high_score_negative"][0]["feedback_label"] in {"wrong", "boring"}
    assert payload["mismatch_samples"]["high_score_negative"][0]["quality_score"] >= 0.75
    assert payload["mismatch_samples"]["low_score_approved"][0]["feedback_label"] == "approved"
    assert payload["mismatch_samples"]["low_score_approved"][0]["quality_score"] <= 0.55
