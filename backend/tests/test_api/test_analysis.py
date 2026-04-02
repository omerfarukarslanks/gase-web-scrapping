from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.source import Source
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

    response = await client.get("/api/v1/analysis/topic-briefs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_status"] == "degraded"
    assert len(payload["groups"]) == 1
    topic = payload["groups"][0]["topics"][0]
    assert topic["aggregation_type"] == "shared"
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
    assert topic["source_count"] == 1
    assert topic["article_count"] == 1
    assert len(topic["representative_articles"]) == 1


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
    )
    await db_session.commit()

    async def fake_analyze_cluster(self, cluster, visual_assets=None):
        return [
            {
                "article_ids": [str(shared_first.id), str(shared_second.id)],
                "headline_tr": "Rafineri aksakligi petrolu yukseltti",
                "summary_tr": "Rafineri aksakligi petrol fiyatlarini yukari itti.",
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
    assert topics[1]["aggregation_type"] == "unique"
    assert payload["debug"]["shared_topics_generated"] >= 1
    assert payload["debug"]["unique_topics_generated"] >= 1
