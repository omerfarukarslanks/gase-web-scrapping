from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.source import Source
from app.models.topic_feedback import TopicFeedback
from app.schemas.analysis import (
    ContentStrategy,
    PlanningDecision,
    RemotionStoryboard,
    TopicBrief,
    TopicRepresentativeArticle,
    VideoContent,
    VideoPlan,
    VideoPlanScene,
    VideoPromptParts,
    VisualAsset,
)
from app.services.article_service import hash_url
from app.services.remotion_storyboard_service import RemotionStoryboardService
from app.services.topic_analysis import (
    OllamaAnalysisError,
    OllamaTopicAnalyzer,
    PreparedArticle,
    build_candidate_clusters,
    build_contextual_prompt_parts,
    build_fallback_topic,
    build_prepared_articles,
    build_fallback_video_plan,
    build_remotion_storyboard_context,
    build_story_fact_pack,
    build_topic_from_llm_payload,
    build_video_prompt_from_parts,
    coerce_output_blueprint,
    coerce_planning_decision,
    coerce_story_fact_pack_v3,
    coerce_video_plan,
    evaluate_video_quality,
    get_recent_articles_for_analysis,
    infer_story_family,
    make_topic_analysis_entry,
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
    content_snippet: str | None = None,
    content_text: str | None = None,
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
    content_snippet: str | None = None,
    content_text: str | None = None,
    language: str = "en",
    editorial_type: str = "report",
) -> PreparedArticle:
    timestamp = datetime.now(UTC).replace(tzinfo=None)
    article = Article(
        id=uuid4(),
        source_id=uuid4(),
        title=title,
        url=f"https://{source_slug}.example.com/{uuid4()}",
        url_hash=hash_url(f"https://{source_slug}.example.com/{uuid4()}"),
        summary=summary,
        content_snippet=content_snippet,
        content_text=content_text,
        author=None,
        published_at=timestamp,
        scraped_at=timestamp,
        image_url=None,
        category=normalized_category,
        tags=["energy", "markets"],
        language=language,
        source_category="finance",
        raw_metadata=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    return PreparedArticle(
        article=article,
        normalized_category=normalized_category,
        cluster_text=content_snippet or summary,
        detail_text=content_text or content_snippet or summary,
        editorial_type=editorial_type,
        story_language=language,
        uncertainty_level="speculative" if editorial_type == "speculative" else "confirmed",
        timestamp=timestamp,
        source_name=source_name,
        source_slug=source_slug,
        tag_tokens={"energy", "markets"},
        title_tokens=tokenize(title),
        text_tokens=tokenize(content_snippet or summary, max_tokens=80),
    )


def make_video_validation_topic(
    cluster: list[PreparedArticle],
    *,
    headline_tr: str,
    summary_tr: str,
    why_it_matters_tr: str,
    key_points_tr: list[str],
    scene_specs: list[dict],
    category: str = "general",
    must_include: list[str] | None = None,
    video_prompt_en: str = "Use Remotion best practices.",
) -> TopicBrief:
    representative_articles = [
        TopicRepresentativeArticle(
            id=item.article.id,
            title=item.article.title,
            url=item.article.url,
            source_name=item.source_name,
            source_slug=item.source_slug,
            published_at=item.timestamp,
            image_url=item.article.image_url,
        )
        for item in cluster[:3]
    ]
    visual_assets = [
        VisualAsset(
            asset_id="asset-1",
            url=cluster[0].article.image_url or "https://cdn.example.com/video-quality.jpg",
            kind="article_image",
            source_article_id=cluster[0].article.id,
            source_name=cluster[0].source_name,
            alt_text=headline_tr,
        )
    ]
    scenes = [
        VideoPlanScene(
            scene_id=spec.get("scene_id", f"scene-{index + 1}"),
            purpose=spec.get("purpose", "hook"),
            duration_seconds=spec.get("duration_seconds", 8),
            layout_hint=spec.get("layout_hint", "headline"),
            headline=spec["headline"],
            body=spec.get("body", ""),
            supporting_points=spec.get("supporting_points", []),
            key_figures=spec.get("key_figures", []),
            key_data=spec.get("key_data", ""),
            visual_direction=spec.get("visual_direction", "Editorial framing"),
            motion_direction=spec.get("motion_direction", "Measured push-ins"),
            transition_from_previous=spec.get("transition_from_previous", "Cold open" if index == 0 else "Cut"),
            source_line=spec.get("source_line", ""),
            asset_ids=spec.get("asset_ids", ["asset-1"] if index == 0 else []),
        )
        for index, spec in enumerate(scene_specs)
    ]
    video_plan = VideoPlan(
        title=headline_tr,
        audience_mode="sound_off_first",
        master_format="16:9",
        duration_seconds=sum(scene.duration_seconds for scene in scenes),
        pacing_hint="balanced",
        source_visibility="none",
        scenes=scenes,
    )
    video_content = VideoContent(
        headline=headline_tr,
        narrative=[scene.body or scene.headline for scene in scenes if scene.body or scene.headline][:3],
        key_figures=[figure for scene in scenes for figure in scene.key_figures][:4],
        key_data=next((scene.key_data for scene in scenes if scene.key_data), ""),
        source_line="",
        duration_seconds=video_plan.duration_seconds,
    )
    return TopicBrief(
        topic_id=f"topic-{uuid4().hex[:8]}",
        category=category,
        aggregation_type="shared" if len({item.source_slug for item in cluster}) >= 2 else "unique",
        story_language=cluster[0].story_language if cluster else "en",
        editorial_type=cluster[0].editorial_type if cluster else "report",
        headline_tr=headline_tr,
        summary_tr=summary_tr,
        key_points_tr=key_points_tr,
        why_it_matters_tr=why_it_matters_tr,
        confidence=0.82,
        source_count=len({item.source_slug for item in cluster}),
        article_count=len(cluster),
        sources=[item.source_name for item in cluster],
        representative_articles=representative_articles,
        visual_assets=visual_assets,
        video_prompt_en=video_prompt_en,
        video_prompt_parts=VideoPromptParts(
            format_hint="Editorial short",
            story_angle=headline_tr,
            visual_brief="Use bold typography and one clear hero frame.",
            motion_treatment="Measured push-ins",
            transition_style="Editorial wipes",
            scene_sequence=[spec["headline"] for spec in scene_specs],
            tone="Urgent and factual",
            design_keywords=["editorial typography", "news texture"],
            must_include=must_include or [],
            avoid=["Generic filler footage"],
            duration_seconds=video_plan.duration_seconds,
        ),
        video_plan=video_plan,
        video_content=video_content,
        remotion_storyboard=RemotionStoryboard(visual_thesis=headline_tr, scenes=[]),
    )


@pytest.mark.asyncio
async def test_build_prepared_articles_prefers_content_text_for_detail_and_snippet_for_cluster(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    source = await create_source(db_session, slug="guardian", name="The Guardian", category="general")
    article = await create_article(
        db_session,
        source=source,
        title="City opens flood recovery fund after weekend storm",
        url="https://guardian.example.com/flood-recovery-fund",
        source_category="general",
        summary="Short RSS summary about the flood recovery fund.",
        content_snippet="Snippet says the city opened a recovery fund after weekend flood damage.",
        content_text=(
            "City officials opened a recovery fund after weekend flooding damaged roads and homes across the riverfront district. "
            "The mayor said bridge repairs will start immediately and displaced families can apply for emergency aid on Friday morning. "
            "Crews are also inspecting drainage systems after overnight storms."
        ),
        published_at=now - timedelta(minutes=10),
        created_at=now - timedelta(minutes=10),
    )
    await db_session.commit()

    result = await build_prepared_articles([article])

    assert len(result.prepared_articles) == 1
    prepared = result.prepared_articles[0]
    assert prepared.cluster_text == "Snippet says the city opened a recovery fund after weekend flood damage."
    assert "bridge repairs will start immediately" in prepared.detail_text
    assert prepared.detail_text != prepared.cluster_text


@pytest.mark.asyncio
async def test_build_prepared_articles_uses_content_text_lead_before_summary_for_cluster(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    source = await create_source(db_session, slug="apnews", name="AP News", category="general")
    article = await create_article(
        db_session,
        source=source,
        title="Heatwave forces overnight cooling plan",
        url="https://apnews.example.com/heatwave-cooling-plan",
        source_category="general",
        summary="Very short summary.",
        content_text=(
            "Officials opened overnight cooling centers ahead of a fast-moving heatwave expected to peak on Friday. "
            "Emergency crews are extending transit hours so elderly residents can reach shelters safely. "
            "The weather service warned temperatures could challenge early-season records."
        ),
        published_at=now - timedelta(minutes=8),
        created_at=now - timedelta(minutes=8),
    )
    await db_session.commit()

    result = await build_prepared_articles([article])

    prepared = result.prepared_articles[0]
    assert "overnight cooling centers" in prepared.cluster_text
    assert prepared.cluster_text != "Very short summary."
    assert "Emergency crews are extending transit hours" in prepared.detail_text


def test_build_fallback_topic_prefers_detail_text_over_rss_summary() -> None:
    prepared = make_prepared_article(
        title="City opens flood recovery fund after weekend storm",
        summary="Brief RSS stub.",
        content_text=(
            "City officials opened a recovery fund after weekend flooding damaged roads and homes across the riverfront district. "
            "The mayor said displaced families can apply for emergency aid on Friday morning."
        ),
        source_name="AP News",
        source_slug="apnews",
        normalized_category="general",
    )

    topic = build_fallback_topic([prepared], [], aggregation_type="unique")

    assert topic is not None
    assert "recovery fund" in topic.summary_tr.lower()
    assert "brief rss stub" not in topic.summary_tr.lower()


def test_ollama_prompt_payload_includes_detail_and_cluster_text() -> None:
    analyzer = OllamaTopicAnalyzer()
    prepared = make_prepared_article(
        title="Oil rises after refinery outage",
        summary="RSS summary",
        content_snippet="Cluster snippet about oil rising after the outage.",
        content_text=(
            "Oil prices moved higher after a refinery outage in Texas tightened near-term supply expectations. "
            "Traders pointed to diesel and gasoline inventories as the main pressure point."
        ),
        source_name="Reuters",
        source_slug="reuters",
    )

    prompt = analyzer._build_prompt([prepared], [])

    assert '"cluster_text": "Cluster snippet about oil rising after the outage."' in prompt
    assert '"detail_text": "Oil prices moved higher after a refinery outage in Texas tightened near-term supply expectations.' in prompt
    assert "Use detail_text as the main article context" in prompt
    assert '"analysis_text"' not in prompt


def test_build_story_fact_pack_infers_sports_domain_and_return_context() -> None:
    cluster = [
        make_prepared_article(
            title="Alexander Isak returns to training after 101-day absence",
            summary="Arne Slot says Alexander Isak is back in training after 101 days out with a broken leg.",
            content_text=(
                "Alexander Isak returned to first-team training after 101 days out with a broken leg. "
                "Arne Slot said the striker looks stronger physically but will not be ready to start against Manchester City. "
                "Liverpool also face PSG next week in the Champions League."
            ),
            source_name="Sky Sports",
            source_slug="skysports",
            normalized_category="sports",
        ),
        make_prepared_article(
            title="Slot says Isak could make the bench after long injury layoff",
            summary="Slot said Isak may be on the bench after returning to training.",
            content_text=(
                "Slot said Isak may be on the bench after returning to training, but Liverpool will manage his minutes carefully. "
                "Mohamed Salah is fit, while Alisson remains out."
            ),
            source_name="BBC Sport",
            source_slug="bbcsport",
            normalized_category="sports",
        ),
    ]

    fact_pack = build_story_fact_pack(
        cluster,
        category="sports",
        headline="Alexander Isak returns after 101 days out",
        summary="Isak has returned to training but is not ready to start against Manchester City.",
        key_points=["He broke his leg in December.", "He could still make the bench."],
    )

    assert fact_pack.story_domain == "sports"
    assert any("101" in fact for fact in fact_pack.numeric_facts)
    assert any("Alexander Isak" in actor for actor in fact_pack.actors)
    assert fact_pack.trigger_or_setup


def test_build_story_fact_pack_infers_diplomacy_domain() -> None:
    cluster = [
        make_prepared_article(
            title="China says peace talks between Afghanistan and Pakistan are advancing",
            summary="China says the talks are advancing after the two sides resumed conversations.",
            content_text=(
                "China's Foreign Ministry said peace talks between Afghanistan and Pakistan are advancing after the two sides resumed conversations in Urumqi. "
                "The talks follow weeks of fighting that killed hundreds and deepened tensions tied to the TTP."
            ),
            source_name="ABC News",
            source_slug="abcnews",
            normalized_category="general",
        ),
        make_prepared_article(
            title="Pakistan and Afghanistan return to talks under Chinese mediation",
            summary="Chinese mediation resumed after recent deadly fighting.",
            content_text=(
                "Chinese mediation resumed after recent deadly fighting, even as a suicide attack in Pakistan underscored the fragility of the process."
            ),
            source_name="AP News",
            source_slug="apnews",
            normalized_category="general",
        ),
    ]

    fact_pack = build_story_fact_pack(
        cluster,
        category="general",
        headline="China says peace talks are advancing",
        summary="China says Afghanistan and Pakistan are moving forward with talks in Urumqi.",
        key_points=["The talks resumed after weeks of fighting.", "TTP tensions remain central to the crisis."],
    )

    assert fact_pack.story_domain == "diplomacy"
    assert fact_pack.trigger_or_setup
    assert fact_pack.institution


def test_build_topic_from_llm_payload_selects_primary_angle_and_attaches_planning_debug() -> None:
    cluster = [
        make_prepared_article(
            title="Alexander Isak returns to training after 101-day absence",
            summary="Arne Slot says Alexander Isak is back in training after 101 days out with a broken leg.",
            content_text=(
                "Alexander Isak returned to first-team training after 101 days out with a broken leg. "
                "Arne Slot said the striker looks stronger physically but will not be ready to start against Manchester City. "
                "Liverpool also face PSG next week in the Champions League."
            ),
            source_name="Sky Sports",
            source_slug="skysports",
            normalized_category="sports",
        ),
        make_prepared_article(
            title="Slot says Isak could make the bench after long injury layoff",
            summary="Slot said Isak may be on the bench after returning to training.",
            content_text=(
                "Slot said Isak may be on the bench after returning to training, but Liverpool will manage his minutes carefully. "
                "Mohamed Salah is fit, while Alisson remains out."
            ),
            source_name="BBC Sport",
            source_slug="bbcsport",
            normalized_category="sports",
        ),
    ]
    cluster_lookup = {str(item.article.id): item for item in cluster}
    payload = {
        "article_ids": [str(item.article.id) for item in cluster],
        "fact_pack": {
            "core_event": "Alexander Isak is back in training after 101 days out.",
            "actors": ["Alexander Isak", "Arne Slot", "Liverpool"],
            "supporting_facts": [
                "He broke his leg and has returned to first-team training.",
                "Slot says he will not be ready to start against Manchester City.",
            ],
            "trigger_or_setup": "Liverpool face Manchester City before a Champions League trip to PSG.",
            "impact_or_next": "Isak could still make the bench as Liverpool enters a crucial stretch.",
            "evidence_points": [],
            "legal_consequence": "",
            "institution": "",
            "result_context": "Manchester City on Saturday, PSG on Wednesday.",
            "allegation_frame": "",
            "story_language": "en",
            "editorial_type": "report",
            "story_domain": "sports",
            "uncertainty_level": "confirmed",
        },
        "angle_plans": [
            {
                "angle_id": "news_update",
                "angle_type": "news_update",
                "title": "Isak returns after 101 days out",
                "hook": "Alexander Isak is back in training, but not ready to start yet.",
                "duration_seconds": 14,
                "tone": "Urgent and factual",
                "angle_rationale": "Focus on status, availability, and the immediate fixture.",
                "scenes": [
                    {
                        "id": "scene-1",
                        "start_second": 0,
                        "duration_seconds": 7,
                        "headline": "Isak is back in training",
                        "body": "Alexander Isak returned after 101 days out with a broken leg.",
                        "voiceover": "Isak is back after a 101-day layoff.",
                        "visual_direction": "Use a training-ground hero image.",
                        "motion_direction": "Restrained push-ins.",
                        "transition": "Cold open",
                    },
                    {
                        "id": "scene-2",
                        "start_second": 7,
                        "duration_seconds": 7,
                        "headline": "City comes too soon",
                        "body": "Arne Slot says he is not ready to start against Manchester City, but he could make the bench.",
                        "voiceover": "Slot says City comes too soon, though the bench is possible.",
                        "visual_direction": "Shift to a fixture-led split card.",
                        "motion_direction": "Editorial panel slide.",
                        "transition": "Panel wipe",
                    },
                ],
            },
            {
                "angle_id": "competition_context",
                "angle_type": "competition_context",
                "title": "Liverpool enters a crucial week with Isak back",
                "hook": "Isak's return gives Liverpool another option before Manchester City and PSG.",
                "duration_seconds": 16,
                "tone": "Measured and factual",
                "angle_rationale": "Frame the comeback around the upcoming run of games.",
                "scenes": [
                    {
                        "id": "scene-1",
                        "start_second": 0,
                        "duration_seconds": 8,
                        "headline": "Liverpool gets a timely boost",
                        "body": "Isak is back in training before Manchester City and PSG.",
                        "voiceover": "Liverpool gets another attacking option back at a key moment.",
                        "visual_direction": "Use a fixture-led opening frame.",
                        "motion_direction": "Measured push-in.",
                        "transition": "Cold open",
                    },
                    {
                        "id": "scene-2",
                        "start_second": 8,
                        "duration_seconds": 8,
                        "headline": "Minutes will be managed",
                        "body": "Slot says Liverpool will build his minutes carefully after the 101-day layoff.",
                        "voiceover": "Liverpool will manage his return carefully.",
                        "visual_direction": "Add a minutes-management info card.",
                        "motion_direction": "Clean editorial fade.",
                        "transition": "Soft wipe",
                    },
                ],
            },
        ],
    }

    topic = build_topic_from_llm_payload(cluster_lookup, payload, [], aggregation_type="shared")

    assert topic is not None
    assert topic.planning_debug is not None
    assert topic.planning_debug.primary_angle_type == "news_update"
    assert topic.planning_debug.alternate_angle_type == "competition_context"
    assert topic.video_plan.scenes[0].headline == "Isak is back in training"


def test_ollama_topic_payload_validator_accepts_planner_first_topics() -> None:
    analyzer = OllamaTopicAnalyzer()

    assert analyzer._topic_payload_is_valid(
        {
            "article_ids": ["abc-123"],
            "story_fact_pack": {"core_event": "A concrete update"},
            "planning_decision": {"status": "produce", "story_family": "general_update"},
            "strategy": {"primary_category": "general", "primary_output": "vertical_video"},
        }
    )


def test_build_topic_from_llm_payload_hydrates_planner_first_fields_and_applies_review_override() -> None:
    cluster = [
        make_prepared_article(
            title="Wisconsin mosque president detained by ICE after leaving home",
            summary="Supporters say Salah Sarsour was detained by ICE agents in Milwaukee.",
            content_text=(
                "Salah Sarsour, president of Wisconsin's largest mosque, was detained by ICE agents in Milwaukee. "
                "Supporters and attorneys say he was targeted for speech related to Israel and is being held in Indiana. "
                "Attorneys said he is a legal permanent resident and are seeking his release."
            ),
            source_name="PBS",
            source_slug="pbs",
            normalized_category="general",
        ),
        make_prepared_article(
            title="Supporters call for release after ICE detains Milwaukee mosque leader",
            summary="Attorneys said the detention raises immigration and speech concerns.",
            content_text=(
                "Attorneys said the detention raises immigration and speech concerns after ICE agents took Sarsour into custody. "
                "Supporters gathered in Milwaukee and local officials criticized the arrest."
            ),
            source_name="AP",
            source_slug="ap",
            normalized_category="general",
        ),
    ]
    cluster_lookup = {str(item.article.id): item for item in cluster}
    payload = {
        "article_ids": [str(item.article.id) for item in cluster],
        "story_fact_pack": {
            "core_event": "Salah Sarsour was detained by ICE agents in Milwaukee.",
            "what_changed": "Supporters are now demanding his release after the detention.",
            "why_now": "Attorneys say the case raises immigration and free-speech concerns.",
            "key_entities": ["Salah Sarsour", "ICE", "Islamic Society of Milwaukee"],
            "key_numbers": ["53", "30 years"],
            "key_locations": ["Milwaukee", "Indiana"],
            "time_reference": "Monday",
            "source_attribution": "Supporters and attorneys say",
            "evidence_level": "full_text",
            "uncertainty_level": "mixed",
        },
        "planning_decision": {
            "status": "produce",
            "story_family": "legal_case",
            "editorial_intent": "explain",
            "layout_family": "document_context_stack",
            "scene_count": 4,
            "risk_flags": [],
            "reason": "Model thinks this can publish directly.",
        },
        "strategy": {
            "primary_category": "politics",
            "secondary_categories": ["analysis"],
            "strategy_domain": "crime_legal",
            "primary_output": "carousel",
            "secondary_outputs": [],
            "viewer_language": "en",
            "voiceover_mode": "hybrid",
            "hook_style": "analysis",
            "pacing": "measured",
            "visual_policy": "quote_visual",
            "claim_policy": "attributed_claims",
            "sensitivity_level": "high",
            "human_review_required": False,
            "review_reasons": [],
        },
        "output_blueprint": {
            "vertical_video": {
                "target_duration_seconds": 12,
                "scene_blueprints": [
                    {
                        "goal": "hook",
                        "visual_type": "portrait",
                        "must_include": ["Salah Sarsour"],
                        "safe_voice_rule": "attributed",
                    }
                ],
            },
            "carousel": {
                "slide_count": 4,
                "cover_angle": "Detention case",
                "slide_goals": ["what happened", "supporters say", "legal posture", "what next"],
            },
        },
    }

    topic = build_topic_from_llm_payload(cluster_lookup, payload, [], aggregation_type="shared")

    assert topic is not None
    assert topic.category == "politics"
    assert topic.story_fact_pack.core_event == "Salah Sarsour was detained by ICE agents in Milwaukee."
    assert topic.story_fact_pack.uncertainty_level == "mixed"
    assert topic.planning_decision.story_family == "legal_case"
    assert topic.planning_decision.status == "review"
    assert "legal_allegation" in topic.planning_decision.risk_flags
    assert topic.strategy.primary_output == "carousel"
    assert topic.strategy.human_review_required is True
    assert topic.platform_outputs.vertical_video is None
    assert topic.platform_outputs.carousel is not None
    assert len(topic.platform_outputs.carousel.slides) == 4
    assert any("Milwaukee" in slide.body or "ICE" in slide.body for slide in topic.platform_outputs.carousel.slides)
    assert topic.output_blueprint.carousel is not None
    assert topic.output_blueprint.vertical_video is None
    assert topic.output_blueprint.carousel.slide_goals == [
        "what happened",
        "supporters say",
        "legal posture",
        "what next",
    ]


def test_coerce_story_fact_pack_v3_normalizes_lists_and_invalid_enums() -> None:
    cluster = [
        make_prepared_article(
            title="Rescue crews pull five survivors from rough seas off Puerto Rico",
            summary="Coast Guard crews rescued five people after vessels capsized off Puerto Rico.",
            content_text=(
                "The Coast Guard and Puerto Rico police rescued five people after two boats capsized in rough seas. "
                "All five survivors were treated for minor injuries after the nighttime operation."
            ),
            source_name="CBS News",
            source_slug="cbsnews",
            normalized_category="general",
        ),
        make_prepared_article(
            title="Night rescue saves five after capsized boats off Puerto Rico",
            summary="Five survivors were rescued after a nighttime operation off Puerto Rico.",
            content_text=(
                "Rescue crews saved five people in darkness and rough seas near Puerto Rico after a capsizing incident."
            ),
            source_name="AP",
            source_slug="ap",
            normalized_category="general",
        ),
    ]
    topic = make_video_validation_topic(
        cluster,
        category="general",
        headline_tr="Porto Riko aciklarinda gece yarisi kurtarma operasyonu",
        summary_tr="İki teknenin alabora olmasindan sonra bes kisi sag kurtarildi.",
        key_points_tr=["Sahil Guvenlik ve polis ekipleri ortak operasyon yuruttu."],
        why_it_matters_tr="Operasyon agir deniz sartlarinda tamamlandi ve tum kurtulanlar hastaneye ulasti.",
        scene_specs=[
            {
                "headline": "Bes kisi rough seas icinden kurtarildi",
                "body": "Kurtarma ekipleri gece karanliginda operasyon yuruttu.",
                "key_figures": ["5 survivors"],
            }
        ],
    )
    fact_pack = build_story_fact_pack(
        cluster,
        category=topic.category,
        headline=topic.headline_tr,
        summary=topic.summary_tr,
        key_points=topic.key_points_tr,
    )

    story_fact_pack = coerce_story_fact_pack_v3(
        {
            "core_event": "Five people were rescued after two boats capsized off Puerto Rico.",
            "what_changed": "The rescue operation concluded with all survivors brought ashore.",
            "key_entities": ["Coast Guard", "Puerto Rico police", "Coast Guard"],
            "key_numbers": ["5", "5", "2"],
            "key_locations": ["Puerto Rico", "Puerto Rico", "San Juan"],
            "evidence_level": "unsupported_value",
            "uncertainty_level": "not_a_level",
        },
        topic=topic,
        cluster=cluster,
        fact_pack=fact_pack,
    )

    assert story_fact_pack.core_event == "Five people were rescued after two boats capsized off Puerto Rico."
    assert story_fact_pack.key_entities == ["Coast Guard", "Puerto Rico police"]
    assert story_fact_pack.key_numbers == ["5", "2"]
    assert story_fact_pack.key_locations == ["Puerto Rico", "San Juan"]
    assert story_fact_pack.evidence_level in {"full_text", "summary_only", "headline_only"}
    assert story_fact_pack.evidence_level != "unsupported_value"
    assert story_fact_pack.uncertainty_level in {"confirmed", "mixed", "speculative"}
    assert story_fact_pack.uncertainty_level != "not_a_level"


def test_infer_story_family_classifies_coventry_style_match_as_result_update() -> None:
    cluster = [
        make_prepared_article(
            title="Coventry City 3-2 Derby County: Jack Rudoni at the double",
            summary="Jack Rudoni scored twice on his return from injury as Coventry beat Derby 3-2.",
            content_text=(
                "Coventry City beat Derby County 3-2 as Jack Rudoni scored twice after returning from injury. "
                "Frank Onyeka opened the scoring before Ben Brereton Diaz equalised. "
                "Rudoni then struck in the 68th and 80th minutes to secure the win."
            ),
            source_name="Sky Sports",
            source_slug="skysports",
            normalized_category="sports",
        ),
        make_prepared_article(
            title="Rudoni double sends Coventry closer to promotion",
            summary="Coventry moved closer to promotion with a 3-2 win over Derby.",
            content_text=(
                "Rudoni scored twice after coming off the bench and Coventry moved another step closer to promotion."
            ),
            source_name="BBC Sport",
            source_slug="bbcsport",
            normalized_category="sports",
        ),
    ]
    topic = make_video_validation_topic(
        cluster,
        category="sports",
        headline_tr="Coventry Derby'yi 3-2 gecti, Rudoni maci cevirdi",
        summary_tr="Jack Rudoni sakatlik donusunde cift golle Coventry'yi tasidi.",
        key_points_tr=[
            "Coventry Derby'yi 3-2 yendi.",
            "Rudoni 68 ve 80. dakikalarda gol atti.",
        ],
        why_it_matters_tr="Sonuc Coventry'nin yukselis yarisi icin dogrudan etki yaratti.",
        scene_specs=[
            {
                "headline": "Rudoni cift golle geri dondu",
                "body": "Coventry sakatlik donusu gelen oyuncusuyla maci kazandi.",
                "key_figures": ["3-2", "Rudoni"],
                "key_data": "3-2",
            }
        ],
    )
    fact_pack = build_story_fact_pack(
        cluster,
        category=topic.category,
        headline=topic.headline_tr,
        summary=topic.summary_tr,
        key_points=topic.key_points_tr,
    )

    assert infer_story_family(topic=topic, cluster=cluster, fact_pack=fact_pack) == "result_update"


def test_coerce_planning_decision_enforces_review_for_betting_pick_and_filters_invalid_values() -> None:
    cluster = [
        make_prepared_article(
            title="Weekend Lock: Yakhyaev vs Ribeiro to not start round two",
            summary="A betting pick says the UFC bout should end before round two.",
            content_text=(
                "Weekend Lock backs Abdul Rakhman Yakhyaev vs Brendson Ribeiro to not start round two at -300. "
                "The article says Yakhyaev is a fast starter and asks readers for their most confident betting lock."
            ),
            source_name="Yahoo Sports",
            source_slug="yahoosports",
            normalized_category="sports",
        ),
        make_prepared_article(
            title="UFC betting column backs early finish in Vegas",
            summary="A prediction column points to an early finish in the featured fight.",
            content_text=(
                "The prediction focuses on round props and method-of-victory odds for the matchup in Las Vegas."
            ),
            source_name="MMA Mania",
            source_slug="mmamania",
            normalized_category="sports",
        ),
    ]
    topic = make_video_validation_topic(
        cluster,
        category="sports",
        headline_tr="Haftanin bankosu: Yakhyaev-Ribeiro ikinci raundu gormez mi?",
        summary_tr="Yazi mazin erken bitecegini savunuyor ve okuyuculara kendi bahis kilidini soruyor.",
        key_points_tr=["Tahmin, macin ikinci raundu gormeyecegi yonunde."],
        why_it_matters_tr="Bahis odakli bu icerik daha temkinli paketlenmeli.",
        scene_specs=[
            {
                "headline": "Weekend Lock erken bitis ariyor",
                "body": "Yazi ikinci raund oncesi bitis bahsini one cikariyor.",
                "key_figures": ["-300"],
            }
        ],
    )
    fact_pack = build_story_fact_pack(
        cluster,
        category=topic.category,
        headline=topic.headline_tr,
        summary=topic.summary_tr,
        key_points=topic.key_points_tr,
    )

    decision = coerce_planning_decision(
        {
            "status": "produce",
            "story_family": "betting_pick",
            "layout_family": "totally_invalid_layout",
            "risk_flags": ["not_real", "gambling_content"],
            "reason": "Model tried to publish it directly.",
        },
        topic=topic,
        cluster=cluster,
        fact_pack=fact_pack,
    )

    assert decision.story_family == "betting_pick"
    assert decision.status == "review"
    assert decision.layout_family == "quote_context_stack"
    assert "gambling_content" in decision.risk_flags
    assert "not_real" not in decision.risk_flags


def test_coerce_output_blueprint_trims_vertical_blueprint_to_scene_count() -> None:
    decision = PlanningDecision(
        status="produce",
        story_family="result_update",
        editorial_intent="break",
        layout_family="scoreboard_stack",
        scene_count=2,
        risk_flags=[],
        reason="Result story.",
    )
    strategy = ContentStrategy(
        primary_category="sports",
        secondary_categories=[],
        strategy_domain="sports",
        primary_output="vertical_video",
        secondary_outputs=["carousel"],
        viewer_language="en",
        voiceover_mode="native",
        hook_style="urgent",
        pacing="fast",
        visual_policy="scoreboard",
        claim_policy="standard_fact_voice",
        sensitivity_level="low",
        human_review_required=False,
        review_reasons=[],
    )

    blueprint = coerce_output_blueprint(
        {
            "vertical_video": {
                "target_duration_seconds": 12,
                "scene_blueprints": [
                    {"goal": "hook", "visual_type": "scoreboard", "must_include": ["result"], "safe_voice_rule": "fact_voice"},
                    {"goal": "context", "visual_type": "action_photo", "must_include": ["turning point"], "safe_voice_rule": "fact_voice"},
                    {"goal": "impact", "visual_type": "data_card", "must_include": ["table"], "safe_voice_rule": "fact_voice"},
                ],
            },
            "carousel": {
                "slide_count": 4,
                "cover_angle": "match result",
                "slide_goals": ["what happened", "turning point", "table impact", "what next"],
            },
        },
        decision=decision,
        strategy=strategy,
    )

    assert blueprint.vertical_video is not None
    assert len(blueprint.vertical_video.scene_blueprints) == 2
    assert blueprint.vertical_video.target_duration_seconds == 12
    assert blueprint.carousel is not None
    assert blueprint.carousel.slide_goals == ["what happened", "turning point", "table impact", "what next"]


def test_build_topic_from_legacy_payload_hydrates_planner_defaults_for_rescue_story() -> None:
    cluster = [
        make_prepared_article(
            title="3 federal agents, 2 boaters rescued after vessels capsize off Puerto Rico",
            summary="Five people were rescued after two boats capsized off Puerto Rico.",
            content_text=(
                "The Coast Guard and Puerto Rico police rescued five people after two boats capsized in rough seas. "
                "A rescue swimmer was lowered from a helicopter and all survivors were treated for minor injuries."
            ),
            source_name="CBS News",
            source_slug="cbsnews",
            normalized_category="general",
        ),
        make_prepared_article(
            title="Night rescue saves five after capsized vessels off Puerto Rico",
            summary="A nighttime rescue operation saved five people in rough seas.",
            content_text=(
                "Rescue crews kept visual contact with all five people in the water before bringing them safely ashore."
            ),
            source_name="AP",
            source_slug="ap",
            normalized_category="general",
        ),
    ]
    cluster_lookup = {str(item.article.id): item for item in cluster}
    payload = {
        "article_ids": [str(item.article.id) for item in cluster],
        "headline_tr": "Porto Riko aciklarinda film gibi gece kurtarmasi",
        "summary_tr": "Alabora olan iki teknenin ardindan bes kisi dalgalar arasindan sag kurtarildi.",
        "key_points_tr": [
            "Kurtarma operasyonu Sahil Guvenlik ve polis helikopterleriyle yapildi.",
            "Tum kurtulanlar hafif yarali olarak kiyiya ulastirildi.",
        ],
        "why_it_matters_tr": "Agir hava kosullarinda tamamlanan operasyon zincirleme bir kurtarma hikayesine donustu.",
    }

    topic = build_topic_from_llm_payload(cluster_lookup, payload, [], aggregation_type="shared")

    assert topic is not None
    assert topic.story_fact_pack.core_event
    assert topic.planning_decision.story_family == "rescue_operation"
    assert topic.planning_decision.status == "produce"
    assert topic.planning_decision.layout_family == "rescue_sequence_stack"
    assert topic.strategy.primary_output == "vertical_video"
    assert topic.output_blueprint.vertical_video is not None
    assert topic.platform_outputs.vertical_video is not None


def test_evaluate_video_quality_rejects_cross_story_contamination() -> None:
    cluster = [
        make_prepared_article(
            title="Bosnia beats Italy on penalties to qualify for World Cup",
            summary="Bosnia beat Italy on penalties to qualify after a 1-1 draw.",
            content_text=(
                "Bosnia and Herzegovina beat Italy on penalties after a 1-1 draw to qualify for the World Cup. "
                "Supporters celebrated through the night in Zenica and Sarajevo."
            ),
            source_name="Al Jazeera",
            source_slug="aljazeera",
            normalized_category="sports",
        ),
        make_prepared_article(
            title="Bosnia reaches World Cup after dramatic shootout win over Italy",
            summary="A penalty shootout sent Bosnia back to the World Cup.",
            content_text=(
                "A dramatic penalty shootout sent Bosnia back to the World Cup and sparked huge celebrations across the country."
            ),
            source_name="AP News",
            source_slug="apnews",
            normalized_category="sports",
        ),
    ]
    topic = make_video_validation_topic(
        cluster,
        category="sports",
        headline_tr="Bosna Italya'yi penaltılarla eleyip Dunya Kupasi'na cıktı",
        summary_tr="Bosna penaltılarla Italya'yi eledi. Lamine Yamal taraftar tezahuratlarini kinadi.",
        key_points_tr=[
            "Bosna Italya'yi penaltılarla eledi.",
            "Lamine Yamal anti-Muslim chants sonrasinda tepki gosterdi.",
        ],
        why_it_matters_tr="Bu zafer Bosna'nin turnuva donusu icin tarihi bir gece oldu.",
        scene_specs=[
            {
                "headline": "Bosnia beats Italy on penalties",
                "body": "Bosnia reached the World Cup after a dramatic shootout win.",
                "key_figures": ["Bosnia", "Italy"],
            },
            {
                "headline": "Yamal condemns anti-Muslim chants",
                "body": "Spain's final hopes were also clouded by abuse at another match.",
                "key_figures": ["Yamal", "Spain"],
            },
        ],
        must_include=["Bosnia", "Italy", "Yamal"],
    )

    status, score, reasons = evaluate_video_quality(topic, cluster=cluster)

    assert status == "reject"
    assert score <= 60
    assert "cross_story_contamination" in reasons


def test_evaluate_video_quality_rejects_missing_allegation_framing_for_crime_story() -> None:
    cluster = [
        make_prepared_article(
            title="Gucci Mane kidnapped, robbed at gunpoint in Dallas, DOJ says",
            summary="Gucci Mane was allegedly kidnapped and robbed in Dallas, DOJ says.",
            content_text=(
                "Nine people were federally charged after prosecutors said Gucci Mane was lured to Dallas under the guise of a business meeting. "
                "According to a federal complaint, Pooh Shiesty allegedly forced him to sign paperwork at gunpoint. "
                "If convicted, the defendants could face up to life in federal prison."
            ),
            source_name="CBS News",
            source_slug="cbsnews",
            normalized_category="general",
        ),
        make_prepared_article(
            title="Federal complaint details Dallas studio ambush targeting Gucci Mane",
            summary="A federal complaint details the alleged ambush.",
            content_text=(
                "Authorities said the suspects planned the attack in advance and face kidnapping charges that could carry life sentences."
            ),
            source_name="AP News",
            source_slug="apnews",
            normalized_category="general",
        ),
    ]
    topic = make_video_validation_topic(
        cluster,
        category="general",
        headline_tr="Gucci Mane kidnapped in Dallas studio ambush",
        summary_tr="Gucci Mane was lured to a Dallas studio and forced to sign paperwork at gunpoint.",
        key_points_tr=["Nine people face federal charges in the case."],
        why_it_matters_tr="The case could end with life sentences for the defendants.",
        scene_specs=[
            {
                "headline": "Dallas studio ambush",
                "body": "Gucci Mane was lured to a studio meeting and forced to sign paperwork at gunpoint.",
                "key_figures": ["Gucci Mane", "Dallas"],
            },
            {
                "headline": "Nine people face charges",
                "body": "The defendants could face life in prison if convicted.",
                "key_figures": ["Gucci Mane", "Dallas"],
            },
        ],
        must_include=["Gucci Mane", "Dallas", "DOJ"],
    )
    fact_pack = build_story_fact_pack(
        cluster,
        category="general",
        headline=topic.headline_tr,
        summary=topic.summary_tr,
        key_points=topic.key_points_tr,
    )

    status, score, reasons = evaluate_video_quality(topic, cluster=cluster, fact_pack=fact_pack)

    assert status == "reject"
    assert score <= 80
    assert "missing_allegation_framing" in reasons


def test_evaluate_video_quality_rejects_broken_copy() -> None:
    cluster = [
        make_prepared_article(
            title="Phil Mickelson withdraws from Masters due to family health matter",
            summary="Phil Mickelson will miss the Masters because of a family health matter.",
            content_text=(
                "Phil Mickelson will miss the Masters because of an ongoing family health matter and expects to be out for an extended period."
            ),
            source_name="The Guardian",
            source_slug="guardian",
            normalized_category="sports",
        ),
        make_prepared_article(
            title="Mickelson says he will miss Augusta for extended period",
            summary="Mickelson says he will miss Augusta.",
            content_text=(
                "The three-time Masters champion said he will miss Augusta and remain away from competition for an extended period."
            ),
            source_name="AP News",
            source_slug="apnews",
            normalized_category="sports",
        ),
    ]
    topic = make_video_validation_topic(
        cluster,
        category="sports",
        headline_tr="Phil Mickelson Masters'tan aile sagligi nedeniyle cekildi",
        summary_tr="Three-time champion 'out for extended period''It is the most special week.",
        key_points_tr=["Phil Mickelson Masters'ta yer almayacak."],
        why_it_matters_tr="Augusta oncesi saha dısı en buyuk gelismelerden biri bu oldu.",
        scene_specs=[
            {
                "headline": "Phil Mickelson withdraws from Masters",
                "body": "Three-time champion 'out for extended period''It is the most special week.",
                "key_figures": ["Phil Mickelson", "Three"],
            }
        ],
        must_include=["Phil Mickelson", "Three"],
    )

    status, score, reasons = evaluate_video_quality(topic, cluster=cluster)

    assert status == "reject"
    assert score <= 65
    assert "broken_copy" in reasons


def test_evaluate_video_quality_marks_generic_why_and_missing_numeric_impact_review() -> None:
    cluster = [
        make_prepared_article(
            title="Mortgage rates surge as spring homebuying season slows",
            summary="Mortgage rates climbed and threatened to wash out the spring buying season.",
            content_text=(
                "The rate on a 30-year mortgage rose to 6.46% and buyers now face about $265 in extra monthly payments. "
                "That adds up to roughly $95,400 over the life of a 30-year loan."
            ),
            source_name="CBS News",
            source_slug="cbsnews",
            normalized_category="general",
        ),
        make_prepared_article(
            title="Higher bond yields push mortgage costs higher for homebuyers",
            summary="Higher yields pushed borrowing costs back up.",
            content_text=(
                "Borrowing costs jumped after Treasury yields climbed, making the average home loan noticeably more expensive for buyers."
            ),
            source_name="AP News",
            source_slug="apnews",
            normalized_category="general",
        ),
    ]
    topic = make_video_validation_topic(
        cluster,
        category="general",
        headline_tr="Mortgage faizleri yukseliyor, ev alicilarinin planlari bozuluyor",
        summary_tr="Mortgage rates are surging, foiling homebuyers' best-laid plans.",
        key_points_tr=["Mortgage rates are surging, foiling homebuyers' best-laid plans."],
        why_it_matters_tr="The next confirmed update will likely shape where the story goes next.",
        scene_specs=[
            {
                "headline": "Mortgage rates are surging",
                "body": "Borrowing costs are threatening to wash out the spring homebuying season.",
                "key_figures": ["Mortgage", "Surging"],
            },
            {
                "headline": "Mortgage rates are surging",
                "body": "The next confirmed update will likely shape where the story goes next.",
                "supporting_points": ["Mortgage rates are surging, foiling homebuyers' best-laid plans."],
                "key_figures": ["Mortgage", "Surging"],
            },
        ],
        must_include=["Mortgage", "Surging"],
    )

    status, score, reasons = evaluate_video_quality(topic, cluster=cluster)

    assert status == "review"
    assert score < 85
    assert "generic_why_it_matters" in reasons
    assert "missing_numeric_impact" in reasons


def test_evaluate_video_quality_flags_missing_institutional_context_review() -> None:
    cluster = [
        make_prepared_article(
            title="DOJ says Presidential Records Act is unconstitutional",
            summary="The Justice Department said the records law is unconstitutional.",
            content_text=(
                "The Justice Department's Office of Legal Counsel said the Presidential Records Act is unconstitutional and that President Trump does not need to comply with it. "
                "The law requires presidential records to go to the National Archives."
            ),
            source_name="CBS News",
            source_slug="cbsnews",
            normalized_category="general",
        ),
        make_prepared_article(
            title="OLC opinion says Trump does not need to follow records law",
            summary="An OLC opinion said Trump does not need to comply with the law.",
            content_text=(
                "The opinion binds the executive branch unless a court reaches a different conclusion."
            ),
            source_name="AP News",
            source_slug="apnews",
            normalized_category="general",
        ),
    ]
    topic = make_video_validation_topic(
        cluster,
        category="general",
        headline_tr="DOJ Baskanlik Kayitlari Yasasi'nin anayasaya aykiri oldugunu soyluyor",
        summary_tr="DOJ opinion says the records law is unconstitutional.",
        key_points_tr=["DOJ says Presidential Records Act is unconstitutional."],
        why_it_matters_tr="This could quickly reshape the political response around the case.",
        scene_specs=[
            {
                "headline": "DOJ opinion sparks fresh debate",
                "body": "A new legal opinion is drawing attention across Washington.",
                "key_figures": ["DOJ", "Office"],
            },
            {
                "headline": "What to watch next",
                "body": "Political reaction may follow quickly after the opinion.",
                "key_figures": ["DOJ", "Office"],
            },
        ],
        must_include=["DOJ", "Office"],
    )

    status, score, reasons = evaluate_video_quality(topic, cluster=cluster)

    assert status == "review"
    assert score < 85
    assert "missing_institutional_context" in reasons


def test_evaluate_video_quality_flags_missing_sports_result_context_review() -> None:
    cluster = [
        make_prepared_article(
            title="Bosnia beats Italy on penalties to qualify for World Cup",
            summary="Bosnia beat Italy on penalties to qualify for the World Cup.",
            content_text=(
                "Bosnia beat Italy on penalties after a 1-1 draw to qualify for the World Cup. "
                "Esmir Bajraktarevic scored the decisive spot kick."
            ),
            source_name="Al Jazeera",
            source_slug="aljazeera",
            normalized_category="sports",
        ),
        make_prepared_article(
            title="Bosnia reaches World Cup after shootout win over Italy",
            summary="Bosnia reached the World Cup after a shootout win over Italy.",
            content_text=(
                "Supporters in Zenica and Sarajevo celebrated after the dramatic shootout."
            ),
            source_name="AP News",
            source_slug="apnews",
            normalized_category="sports",
        ),
    ]
    topic = make_video_validation_topic(
        cluster,
        category="sports",
        headline_tr="Bosna'nin Italya karsisindaki tarihi gecesi",
        summary_tr="Bosna'nin tarihi gecesi ulke capinda buyuk cosku yaratti.",
        key_points_tr=["Bosna taraftarlari tarihi geceyi kutladi."],
        why_it_matters_tr="Bu galibiyet ulke capinda uzun sure konusulacak bir gece yaratti.",
        scene_specs=[
            {
                "headline": "Bosnia's historic night",
                "body": "The country erupted in celebration after a dramatic evening.",
                "key_figures": ["Bosnia", "Italy"],
            }
        ],
        must_include=["Bosnia", "Italy"],
    )

    status, score, reasons = evaluate_video_quality(topic, cluster=cluster)

    assert status == "review"
    assert score < 85
    assert "missing_sports_result_context" in reasons


def test_evaluate_video_quality_forces_speculative_story_to_review() -> None:
    cluster = [
        make_prepared_article(
            title="USC a possible landing spot for Audi Crooks",
            summary="Iowa State star Audi Crooks entered the transfer portal and could land at USC.",
            content_text=(
                "Iowa State star Audi Crooks entered the transfer portal for her final year. "
                "Some believe USC could be a landing spot because of the roster already in place."
            ),
            source_name="Yahoo Sports",
            source_slug="yahoosports",
            normalized_category="sports",
            editorial_type="speculative",
        )
    ]
    topic = make_video_validation_topic(
        cluster,
        category="sports",
        headline_tr="USC, Audi Crooks icin olasi duraklardan biri olabilir",
        summary_tr="Audi Crooks transfer portalina girdi ve USC olasi adreslerden biri olarak aniliyor.",
        key_points_tr=["Audi Crooks final sezonu oncesi transfer portalina girdi."],
        why_it_matters_tr="USC kadrosu olasi bir transfer icin dikkat ceken senaryolardan biri olarak goruluyor.",
        scene_specs=[
            {
                "headline": "Audi Crooks enters transfer portal",
                "body": "USC is one of the possible destinations being discussed for her final college season.",
                "key_figures": ["Audi Crooks", "USC"],
            }
        ],
        must_include=["Audi Crooks", "USC"],
    )

    status, score, reasons = evaluate_video_quality(topic, cluster=cluster)

    assert status == "review"
    assert score < 85
    assert "speculative_story" in reasons


def test_evaluate_video_quality_flags_mixed_language_copy_review() -> None:
    cluster = [
        make_prepared_article(
            title="Con la tabla de sumar pueden salir las cuentas",
            summary="El equipo maño empata en Leganes y sigue creciendo con David Navarro.",
            content_text=(
                "El Real Zaragoza empató 1-1 en Leganés y mantiene viva la pelea por la permanencia. "
                "El equipo de David Navarro sigue sumando en un tramo decisivo."
            ),
            source_name="Marca English",
            source_slug="marca",
            normalized_category="sports",
            language="es",
        )
    ]
    topic = make_video_validation_topic(
        cluster,
        category="sports",
        headline_tr="Con la tabla de sumar pueden salir las cuentas",
        summary_tr="El Zaragoza rescato un empate clave en Leganes.",
        key_points_tr=["Real Zaragoza took a key point in Leganes."],
        why_it_matters_tr="El punto mantiene al equipo vivo en la pelea por la permanencia.",
        scene_specs=[
            {
                "headline": "Con la tabla de sumar pueden salir las cuentas",
                "body": "Real Zaragoza took a key point in Leganes to stay alive in the relegation fight.",
                "key_figures": ["David Navarro", "Real Zaragoza"],
            }
        ],
        must_include=["David Navarro", "Real Zaragoza"],
    )

    status, score, reasons = evaluate_video_quality(topic, cluster=cluster)

    assert status == "review"
    assert score < 85
    assert "mixed_language_copy" in reasons


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
    video_quality_status: str = "publishable",
    video_quality_score: int = 88,
    source_count: int = 2,
    article_count: int = 2,
    source_slugs: list[str] | None = None,
    review_reasons: list[str] | None = None,
    video_review_reasons: list[str] | None = None,
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
        video_quality_status=video_quality_status,
        video_quality_score=video_quality_score,
        source_count=source_count,
        article_count=article_count,
        source_slugs=source_slugs or ["reuters"],
        representative_article_ids=[str(uuid4())],
        review_reasons=review_reasons or [],
        video_review_reasons=video_review_reasons or [],
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
    assert normalize_analysis_category("Entertainment", "general") == "culture"
    assert normalize_analysis_category(None, "finance") == "economy"
    assert normalize_analysis_category(None, "sports") == "sports"
    assert normalize_analysis_category("Unknown label", None) == "general"


def test_make_topic_analysis_entry_applies_health_strategy_review_guardrails() -> None:
    cluster = [
        make_prepared_article(
            title="Doctors flag dosing concerns after weight-loss treatment trend",
            summary="Doctors urged caution after a popular weight-loss treatment spread rapidly online.",
            source_name="Reuters",
            source_slug="reuters",
            normalized_category="health",
            content_text=(
                "Doctors urged caution after online videos encouraged patients to change dosage schedules without supervision. "
                "Hospitals said some patients arrived with severe side effects after following unverified medical advice."
            ),
        ),
        make_prepared_article(
            title="Hospitals warn viral dosage advice can trigger serious side effects",
            summary="Hospitals said patients should not adjust treatment plans without a clinician.",
            source_name="AP",
            source_slug="ap",
            normalized_category="health",
            content_text=(
                "Hospitals said patients should not adjust treatment plans without a clinician because symptoms can escalate quickly. "
                "Health officials said guidance must come from licensed professionals."
            ),
        ),
    ]
    topic = make_video_validation_topic(
        cluster,
        headline_tr="Doctors warn against viral dosage advice",
        summary_tr="Hospitals say patients should not change treatment dosage based on social posts.",
        why_it_matters_tr="Unverified medical advice can create immediate health risks and push hospitals into emergency response.",
        key_points_tr=[
            "Doctors say dosage changes need clinical supervision.",
            "Hospitals reported severe side effects after online advice spread.",
        ],
        category="health",
        scene_specs=[
            {
                "headline": "Doctors warn against viral dosage advice",
                "body": "Hospitals say patients should not change treatment plans without a clinician.",
                "key_figures": ["Doctors", "Hospitals"],
            },
            {
                "headline": "Unverified advice can trigger severe side effects",
                "body": "Health officials said dosage guidance must come from licensed professionals.",
                "key_figures": ["Health officials"],
            },
        ],
    )

    entry = make_topic_analysis_entry(topic, cluster=cluster)

    assert entry.topic.strategy.primary_category == "health"
    assert entry.topic.strategy.human_review_required is True
    assert entry.topic.video_plan.master_format == "16:9"
    assert entry.quality_status == "review"
    assert entry.video_quality_status in {"review", "reject"}
    assert "health_content_requires_review" in entry.topic.review_reasons


def test_make_topic_analysis_entry_marks_schedule_listing_as_carousel_only() -> None:
    cluster = [
        make_prepared_article(
            title='"Face the Nation with Margaret Brennan" guests for April 5, 2026',
            summary="This week's guests include Democratic Gov. Wes Moore of Maryland and Archbishop Timothy Broglio.",
            source_name="CBS News",
            source_slug="cbsnews",
            normalized_category="general",
            content_text=(
                "Here are the guests for Sunday, April 5, on CBS News' Face the Nation. "
                "Guests include Gov. Wes Moore and Archbishop Timothy Broglio. "
                "The program airs at 10:30 a.m. ET and streams at 12:30 p.m. ET."
            ),
        ),
        make_prepared_article(
            title="Sunday political show lineup features Wes Moore and Timothy Broglio",
            summary="The panel and guest list for Sunday morning are now set.",
            source_name="AP",
            source_slug="ap",
            normalized_category="general",
            content_text=(
                "The Sunday lineup is now set, with guests including Gov. Wes Moore and Archbishop Timothy Broglio. "
                "The show airs Sunday morning and will stream later in the day."
            ),
        ),
    ]
    topic = make_video_validation_topic(
        cluster,
        headline_tr="Face the Nation guests for April 5",
        summary_tr="Wes Moore and Timothy Broglio are among this week's guests on the CBS program.",
        why_it_matters_tr="The guest list previews the main institutional and political talking points for Sunday.",
        key_points_tr=[
            "Guests include Gov. Wes Moore and Archbishop Timothy Broglio.",
            "The program airs Sunday morning and streams later in the day.",
        ],
        category="general",
        scene_specs=[
            {
                "headline": "This week's guest lineup is set",
                "body": "CBS says the Sunday program will feature Gov. Wes Moore and Archbishop Timothy Broglio.",
            },
            {
                "headline": "The panel follows later in the program",
                "body": "The full show airs on Sunday and streams later in the day.",
            },
        ],
    )

    entry = make_topic_analysis_entry(topic, cluster=cluster)

    assert entry.topic.planning_decision.story_family == "schedule_listing"
    assert entry.topic.planning_decision.status == "carousel_only"
    assert entry.topic.strategy.primary_output == "carousel"
    assert entry.topic.video_plan.master_format == "16:9"
    assert entry.topic.output_blueprint.carousel is not None
    assert entry.topic.output_blueprint.vertical_video is None


def test_make_topic_analysis_entry_marks_conflict_breaking_for_review() -> None:
    cluster = [
        make_prepared_article(
            title="US fighter jet down in Iran as search continues for missing crew member",
            summary="Officials said one crew member was rescued while another remains missing.",
            source_name="ABC News",
            source_slug="abcnews",
            normalized_category="world",
            content_text=(
                "A U.S. fighter jet appears to have been shot down over Iranian territory, officials said. "
                "One crew member was rescued, while the status of another remains unknown. "
                "Rescue helicopters also came under incoming fire during the search."
            ),
        ),
        make_prepared_article(
            title="Officials say search continues after US warplane goes down over Iran",
            summary="The incident marks a dangerous new point in the conflict, officials said.",
            source_name="CBS News",
            source_slug="cbsnews",
            normalized_category="world",
            content_text=(
                "Officials said the aircraft was downed during the conflict and that rescue efforts are ongoing. "
                "The missing crew member has not yet been located."
            ),
        ),
    ]
    topic = make_video_validation_topic(
        cluster,
        headline_tr="US fighter jet goes down over Iran",
        summary_tr="Officials say one crew member was rescued and a search is still underway for another.",
        why_it_matters_tr="The incident marks a dangerous escalation point and remains an active search-and-rescue story.",
        key_points_tr=[
            "Officials say one crew member was rescued.",
            "The search for another crew member is still underway.",
        ],
        category="world",
        scene_specs=[
            {
                "headline": "US fighter jet goes down over Iran",
                "body": "Officials said one crew member was rescued while another remains missing.",
                "key_figures": ["Officials"],
            },
            {
                "headline": "Rescue effort continues under fire",
                "body": "Officials said helicopters involved in the search also took incoming fire.",
                "key_figures": ["Rescue crews"],
            },
        ],
    )

    entry = make_topic_analysis_entry(topic, cluster=cluster)

    assert entry.topic.planning_decision.story_family == "conflict_breaking"
    assert entry.topic.planning_decision.status == "review"
    assert "conflict_or_casualty" in entry.topic.planning_decision.risk_flags
    assert entry.topic.strategy.primary_output == "vertical_video"
    assert entry.topic.strategy.human_review_required is True
    assert entry.quality_status == "review"
    assert entry.topic.output_blueprint.vertical_video is not None
    assert entry.topic.platform_outputs.vertical_video is not None
    assert len(entry.topic.platform_outputs.vertical_video.scenes) == len(
        entry.topic.output_blueprint.vertical_video.scene_blueprints
    )
    assert entry.topic.platform_outputs.image_prompts


def test_make_topic_analysis_entry_skips_letters_style_roundups() -> None:
    cluster = [
        make_prepared_article(
            title="Fly me to the moon - or at least to Luton | Brief letters",
            summary="Readers react to moon travel, trains and mint sauce in a letters roundup.",
            source_name="The Guardian",
            source_slug="guardian",
            normalized_category="science",
            content_text=(
                "Artemis II has successfully taken off to begin its journey to the far side of the moon. "
                "Meanwhile, our grandson has been unable to travel by train from Manchester to Luton. "
                "Brief letters also discuss mint sauce and a wordsearch."
            ),
        ),
        make_prepared_article(
            title="Brief letters: Moon mission and train frustrations",
            summary="A short roundup of reader responses to recent stories.",
            source_name="AP",
            source_slug="ap",
            normalized_category="science",
            content_text=(
                "Brief letters react to the moon mission and unrelated daily-life topics. "
                "The roundup includes short responses from multiple readers."
            ),
        ),
    ]
    topic = make_video_validation_topic(
        cluster,
        headline_tr="Brief letters on moon travel and trains",
        summary_tr="A letters roundup reacts to recent stories with short reader submissions.",
        why_it_matters_tr="The content is a multi-topic letters format rather than a single concrete development.",
        key_points_tr=[
            "The roundup mixes moon-mission and train complaints.",
            "The format collects unrelated short reader responses.",
        ],
        category="science",
        scene_specs=[
            {
                "headline": "Readers weigh in on several topics",
                "body": "The roundup mixes the moon mission with travel complaints and other brief reactions.",
            },
        ],
    )

    entry = make_topic_analysis_entry(topic, cluster=cluster)

    assert entry.topic.planning_decision.status == "skip"
    assert entry.video_quality_status == "reject"


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
        return []

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
        return []

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
        return []

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
        return []

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
async def test_topic_briefs_endpoint_filters_video_rejects_and_only_shows_video_review_with_include_review(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    ap = await create_source(db_session, slug="ap-video-filter", name="AP Video Filter", category="general")
    reuters = await create_source(
        db_session,
        slug="reuters-video-filter",
        name="Reuters Video Filter",
        category="general",
    )
    bbc = await create_source(db_session, slug="bbc-video-filter", name="BBC Video Filter", category="general")

    await create_article(
        db_session,
        source=ap,
        title="City opens overnight cooling centers ahead of heatwave",
        url="https://ap-video-filter.example.com/cooling-centers",
        source_category="general",
        summary="Officials opened overnight cooling centers ahead of a fast-moving heatwave.",
        published_at=now - timedelta(minutes=16),
        created_at=now - timedelta(minutes=16),
        category="general",
        image_url="https://cdn.example.com/ap-video-filter-cooling.jpg",
    )
    await create_article(
        db_session,
        source=reuters,
        title="Mayor announces flood cleanup fund after weekend damage",
        url="https://reuters-video-filter.example.com/flood-fund",
        source_category="general",
        summary="A mayor announced a cleanup fund after severe weekend flood damage.",
        published_at=now - timedelta(minutes=12),
        created_at=now - timedelta(minutes=12),
        category="general",
        image_url="https://cdn.example.com/reuters-video-filter-flood.jpg",
    )
    await create_article(
        db_session,
        source=bbc,
        title="Transit agency says quote chain broke after signal outage",
        url="https://bbc-video-filter.example.com/signal-outage",
        source_category="general",
        summary="A transit agency said the quote chain broke after a signal outage hit morning service.",
        published_at=now - timedelta(minutes=8),
        created_at=now - timedelta(minutes=8),
        category="general",
        image_url="https://cdn.example.com/bbc-video-filter-transit.jpg",
    )
    await db_session.commit()

    async def should_not_run(self, cluster, visual_assets=None):
        return []

    def fake_evaluate_video_quality(topic, *, cluster):
        headline = topic.headline_tr.lower()
        if "flood cleanup fund" in headline:
            return ("review", 72, ("headline_only_support",))
        if "quote chain broke" in headline:
            return ("reject", 40, ("broken_copy",))
        return ("publishable", 94, ())

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        should_not_run,
    )
    monkeypatch.setattr(
        "app.services.topic_analysis.evaluate_video_quality",
        fake_evaluate_video_quality,
    )

    default_response = await client.get(
        "/api/v1/analysis/topic-briefs",
        params={"hours": 3, "debug": True},
    )

    assert default_response.status_code == 200
    default_payload = default_response.json()
    default_topics = [topic for group in default_payload["groups"] for topic in group["topics"]]
    assert len(default_topics) == 1
    assert default_topics[0]["video_quality_status"] == "publishable"
    assert default_payload["debug"]["video_publishable_topics_generated"] == 1
    assert default_payload["debug"]["video_review_topics_generated"] == 1
    assert default_payload["debug"]["video_rejected_topics_generated"] == 1

    review_response = await client.get(
        "/api/v1/analysis/topic-briefs",
        params={"hours": 3, "include_review": True, "debug": True},
    )

    assert review_response.status_code == 200
    review_payload = review_response.json()
    review_topics = [topic for group in review_payload["groups"] for topic in group["topics"]]
    assert len(review_topics) == 2
    assert [topic["video_quality_status"] for topic in review_topics] == ["publishable", "review"]
    assert all(topic["video_quality_status"] != "reject" for topic in review_topics)
    assert review_topics[1]["video_review_reasons"] == ["headline_only_support"]


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
        return []

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
        return []

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
        return []

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
    input_rejection_breakdown = {
        item["reason"]: item["count"] for item in payload["totals"]["input_rejection_breakdown"]
    }
    assert input_rejection_breakdown["utility_or_hub_page"] >= 1
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
async def test_topic_briefs_endpoint_exposes_planning_debug_only_in_debug_mode(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    sky = await create_source(db_session, slug="sky-angle", name="Sky Angle", category="sports")
    bbc = await create_source(db_session, slug="bbc-angle", name="BBC Angle", category="sports")

    first = await create_article(
        db_session,
        source=sky,
        title="Alexander Isak returns to training after 101-day absence",
        url="https://sky-angle.example.com/isak-return",
        source_category="sports",
        summary="Arne Slot says Alexander Isak is back in training after 101 days out with a broken leg.",
        published_at=now - timedelta(minutes=12),
        created_at=now - timedelta(minutes=12),
        category="sports",
        image_url="https://cdn.example.com/isak-angle.jpg",
        content_text=(
            "Alexander Isak returned to first-team training after 101 days out with a broken leg. "
            "Arne Slot said he will not be ready to start against Manchester City."
        ),
    )
    second = await create_article(
        db_session,
        source=bbc,
        title="Alexander Isak could make the bench after long layoff, Slot says",
        url="https://bbc-angle.example.com/isak-bench",
        source_category="sports",
        summary="Slot said Isak may be on the bench after returning to training.",
        published_at=now - timedelta(minutes=10),
        created_at=now - timedelta(minutes=10),
        category="sports",
        image_url="https://cdn.example.com/isak-angle-bench.jpg",
        content_text="Liverpool will manage his minutes carefully before trips to Manchester City and PSG.",
    )
    await db_session.commit()

    async def fake_analyze_cluster(self, cluster, visual_assets=None):
        return [
            {
                "article_ids": [str(first.id), str(second.id)],
                "fact_pack": {
                    "core_event": "Alexander Isak is back in training after 101 days out.",
                    "actors": ["Alexander Isak", "Arne Slot", "Liverpool"],
                    "supporting_facts": [
                        "He broke his leg and has returned to training.",
                        "He is not ready to start against Manchester City.",
                    ],
                    "trigger_or_setup": "Liverpool face Manchester City before a trip to PSG.",
                    "impact_or_next": "Isak could still make the bench as Liverpool enters a crucial week.",
                    "evidence_points": [],
                    "legal_consequence": "",
                    "institution": "",
                    "result_context": "Manchester City on Saturday, PSG next week.",
                    "allegation_frame": "",
                    "story_language": "en",
                    "editorial_type": "report",
                    "story_domain": "sports",
                    "uncertainty_level": "confirmed",
                },
                "angle_plans": [
                    {
                        "angle_id": "news_update",
                        "angle_type": "news_update",
                        "title": "Isak returns after 101 days out",
                        "hook": "Alexander Isak is back in training, but not ready to start yet.",
                        "duration_seconds": 14,
                        "tone": "Urgent and factual",
                        "angle_rationale": "Focus on the direct squad update.",
                        "scenes": [
                            {
                                "id": "scene-1",
                                "start_second": 0,
                                "duration_seconds": 7,
                                "headline": "Isak is back in training",
                                "body": "Alexander Isak returned after 101 days out with a broken leg.",
                                "voiceover": "Isak is back after a 101-day layoff.",
                                "visual_direction": "Use training imagery.",
                                "motion_direction": "Restrained push-in.",
                                "transition": "Cold open",
                            },
                            {
                                "id": "scene-2",
                                "start_second": 7,
                                "duration_seconds": 7,
                                "headline": "City comes too soon",
                                "body": "Arne Slot says he is not ready to start against Manchester City, but he could make the bench.",
                                "voiceover": "Slot says City comes too soon, though the bench is possible.",
                                "visual_direction": "Use fixture-led framing.",
                                "motion_direction": "Editorial wipe.",
                                "transition": "Panel wipe",
                            },
                        ],
                    },
                    {
                        "angle_id": "competition_context",
                        "angle_type": "competition_context",
                        "title": "Liverpool gets a timely boost",
                        "hook": "Isak returns before Manchester City and PSG.",
                        "duration_seconds": 15,
                        "tone": "Measured and factual",
                        "angle_rationale": "Frame the story through the upcoming fixtures.",
                        "scenes": [
                            {
                                "id": "scene-1",
                                "start_second": 0,
                                "duration_seconds": 8,
                                "headline": "Liverpool gets another option",
                                "body": "Isak is back in training before Manchester City and PSG.",
                                "voiceover": "Liverpool gets another attacking option back.",
                                "visual_direction": "Use a fixture timeline.",
                                "motion_direction": "Measured slide.",
                                "transition": "Cold open",
                            },
                            {
                                "id": "scene-2",
                                "start_second": 8,
                                "duration_seconds": 7,
                                "headline": "Minutes will be managed",
                                "body": "Liverpool will build his minutes carefully after the 101-day layoff.",
                                "voiceover": "His return will be managed carefully.",
                                "visual_direction": "Use a minutes card.",
                                "motion_direction": "Clean fade.",
                                "transition": "Soft wipe",
                            },
                        ],
                    },
                ],
            }
        ]

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        fake_analyze_cluster,
    )

    response = await client.get("/api/v1/analysis/topic-briefs", params={"hours": 3, "debug": True})
    assert response.status_code == 200
    payload = response.json()
    topic = payload["groups"][0]["topics"][0]
    assert "planning_debug" in topic
    assert topic["planning_debug"]["primary_angle_type"] == "news_update"
    assert topic["planning_debug"]["alternate_angle_type"] == "competition_context"

    response_without_debug = await client.get("/api/v1/analysis/topic-briefs", params={"hours": 3})
    assert response_without_debug.status_code == 200
    payload_without_debug = response_without_debug.json()
    topic_without_debug = payload_without_debug["groups"][0]["topics"][0]
    assert "planning_debug" not in topic_without_debug


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
        return []

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        should_not_run,
    )

    initial_response = await client.get("/api/v1/analysis/topic-briefs", params={"hours": 3})
    assert initial_response.status_code == 200
    initial_topic = initial_response.json()["groups"][0]["topics"][0]
    assert initial_topic.get("latest_feedback") is None

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
            "video_quality_status": initial_topic["video_quality_status"],
            "video_quality_score": initial_topic["video_quality_score"],
            "source_count": initial_topic["source_count"],
            "article_count": initial_topic["article_count"],
            "sources": initial_topic["sources"],
            "source_slugs": [
                article["source_slug"]
                for article in initial_topic["representative_articles"]
                if article.get("source_slug")
            ],
            "review_reasons": initial_topic["review_reasons"],
            "video_review_reasons": initial_topic["video_review_reasons"],
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
    assert final_topic.get("latest_feedback") is None


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
        return []

    def fake_evaluate_video_quality(topic, *, cluster):
        if "flood cleanup fund" in topic.headline_tr.lower():
            return ("review", 72, ("headline_only_support",))
        return ("publishable", 92, ())

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        should_not_run,
    )
    monkeypatch.setattr(
        "app.services.topic_analysis.evaluate_video_quality",
        fake_evaluate_video_quality,
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
            "video_quality_status": publishable_topic["video_quality_status"],
            "video_quality_score": publishable_topic["video_quality_score"],
            "source_count": publishable_topic["source_count"],
            "article_count": publishable_topic["article_count"],
            "sources": publishable_topic["sources"],
            "source_slugs": [
                article["source_slug"]
                for article in publishable_topic["representative_articles"]
                if article.get("source_slug")
            ],
            "review_reasons": publishable_topic["review_reasons"],
            "video_review_reasons": publishable_topic["video_review_reasons"],
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
    assert report["totals"]["video_publishable_topics"] == 1
    assert report["totals"]["video_review_topics"] == 1
    assert report["totals"]["video_rejected_topics"] == 0
    assert report["totals"]["video_review_breakdown"] == [
        {"reason": "headline_only_support", "count": 1}
    ]


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
