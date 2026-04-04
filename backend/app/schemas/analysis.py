import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ContentCategory = Literal[
    "world",
    "politics",
    "business",
    "economy",
    "technology",
    "sports",
    "culture",
    "arts",
    "science",
    "environment",
    "health",
    "opinion",
    "analysis",
    "general",
]
StrategyDomain = Literal[
    "world",
    "politics",
    "business",
    "economy",
    "technology",
    "sports",
    "culture",
    "arts",
    "science",
    "environment",
    "health",
    "opinion",
    "analysis",
    "general",
    "crime_legal",
    "diplomacy",
]
PrimaryOutput = Literal["vertical_video", "carousel"]
VoiceoverMode = Literal["native", "hybrid", "text_only"]
HookStyle = Literal["urgent", "authority", "curiosity", "human", "explainer", "analysis"]
Pacing = Literal["fast", "balanced", "measured"]
VisualPolicy = Literal[
    "real_asset_first",
    "data_card",
    "demo_explainer",
    "scoreboard",
    "human_centered",
    "quote_visual",
    "symbolic_reconstruction",
    "restrained_drama",
]
ClaimPolicy = Literal[
    "standard_fact_voice",
    "attributed_claims",
    "analysis_attribution",
    "medical_caution",
    "opinion_attribution",
]
SensitivityLevel = Literal["low", "medium", "high"]
StoryFamily = Literal[
    "result_update",
    "profile_feature",
    "preview_watchlist",
    "schedule_listing",
    "betting_pick",
    "conflict_breaking",
    "disaster_update",
    "legal_case",
    "court_ruling",
    "consumer_impact",
    "institutional_review",
    "obituary_profile",
    "culture_controversy",
    "commentary_recap",
    "policy_shift",
    "social_trend",
    "opinion_editorial",
    "rescue_operation",
    "general_update",
]
PlanningStatus = Literal["produce", "review", "carousel_only", "skip"]
EditorialIntent = Literal["break", "explain", "profile", "memorial", "debate", "guide", "warning", "watchlist"]
LayoutFamily = Literal[
    "scoreboard_stack",
    "hero_detail_stack",
    "panel_listing_stack",
    "map_casualty_stack",
    "document_context_stack",
    "quote_context_stack",
    "price_impact_stack",
    "timeline_stack",
    "memorial_profile_stack",
    "reaction_split_stack",
    "rescue_sequence_stack",
    "generic_story_stack",
]
RiskFlag = Literal[
    "conflict_or_casualty",
    "legal_allegation",
    "election_process",
    "medical_claim",
    "minor_involved",
    "opinion_content",
    "gambling_content",
    "hate_speech_context",
    "obituary_sensitive",
    "speculative_claim",
]
EvidenceLevel = Literal["full_text", "summary_only", "headline_only"]
UncertaintyLevel = Literal["confirmed", "mixed", "speculative"]
SceneGoal = Literal["hook", "setup", "main_fact", "context", "impact", "reaction", "close"]
VisualType = Literal["action_photo", "portrait", "scoreboard", "map", "document", "quote_card", "data_card", "timeline", "symbolic"]
SafeVoiceRule = Literal["fact_voice", "attributed", "opinion_labeled"]
VideoMasterFormat = Literal["16:9", "9:16"]


class VideoPromptParts(BaseModel):
    format_hint: str = ""
    story_angle: str
    visual_brief: str
    motion_treatment: str = ""
    transition_style: str = ""
    scene_sequence: list[str] = Field(default_factory=list)
    tone: str
    design_keywords: list[str] = Field(default_factory=list)
    must_include: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    duration_seconds: int


class VideoContent(BaseModel):
    """Viewer-facing video content — what actually appears on screen."""
    headline: str
    narrative: list[str] = Field(default_factory=list)
    key_figures: list[str] = Field(default_factory=list)
    key_data: str = ""
    source_line: str = ""
    duration_seconds: int = 32


class VideoPlanScene(BaseModel):
    scene_id: str
    purpose: Literal["hook", "explain", "detail", "context", "comparison", "takeaway", "close"]
    duration_seconds: int
    layout_hint: Literal["headline", "split", "stat", "timeline", "quote", "comparison", "minimal", "full-bleed"]
    headline: str
    body: str = ""
    voiceover: str = ""
    supporting_points: list[str] = Field(default_factory=list)
    key_figures: list[str] = Field(default_factory=list)
    key_data: str = ""
    visual_direction: str = ""
    motion_direction: str = ""
    transition_from_previous: str = ""
    source_line: str = ""
    asset_ids: list[str] = Field(default_factory=list)


class VideoPlan(BaseModel):
    title: str
    audience_mode: Literal["sound_off_first"]
    master_format: VideoMasterFormat
    duration_seconds: int
    pacing_hint: str
    source_visibility: Literal["none", "subtle", "contextual"]
    scenes: list[VideoPlanScene] = Field(default_factory=list)


class RemotionStat(BaseModel):
    label: str
    value: str


class RemotionScene(BaseModel):
    scene_type: Literal["hook", "story", "detail", "outro", "hero", "stat-grid", "timeline", "style-board", "impact"]
    duration_seconds: int = 0
    layout_hint: str = ""
    kicker: str
    headline: str
    body: str
    voiceover: str = ""
    source_line: str = ""
    asset_ids: list[str] = Field(default_factory=list)
    visual_elements: list[str] = Field(default_factory=list)
    bullet_points: list[str] = Field(default_factory=list)
    stats: list[RemotionStat] = Field(default_factory=list)
    chips: list[str] = Field(default_factory=list)


class RemotionStoryboard(BaseModel):
    visual_thesis: str
    scenes: list[RemotionScene] = Field(default_factory=list)


class TopicRepresentativeArticle(BaseModel):
    id: uuid.UUID
    title: str
    url: str
    source_name: str | None = None
    source_slug: str | None = None
    published_at: datetime | None = None
    image_url: str | None = None


class VisualAsset(BaseModel):
    asset_id: str
    url: str
    kind: Literal["article_image", "og_image"]
    source_article_id: uuid.UUID
    source_name: str | None = None
    alt_text: str = ""


FeedbackLabel = Literal["approved", "wrong", "boring", "malformed"]


class TopicLatestFeedback(BaseModel):
    label: FeedbackLabel
    note: str | None = None
    updated_at: datetime


class PlanningDebugAngleScore(BaseModel):
    angle_type: str
    quality_status: Literal["publishable", "review", "reject"]
    quality_score: int = Field(default=100, ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)


class PlanningDebug(BaseModel):
    primary_angle_type: str
    alternate_angle_type: str | None = None
    alternate_video_plan_summary: str = ""
    angle_scores: list[PlanningDebugAngleScore] = Field(default_factory=list)


class ContentStrategy(BaseModel):
    primary_category: ContentCategory = "general"
    secondary_categories: list[ContentCategory] = Field(default_factory=list)
    strategy_domain: StrategyDomain = "general"
    primary_output: PrimaryOutput = "vertical_video"
    secondary_outputs: list[PrimaryOutput] = Field(default_factory=lambda: ["carousel"])
    viewer_language: str = "en"
    voiceover_mode: VoiceoverMode = "hybrid"
    hook_style: HookStyle = "urgent"
    pacing: Pacing = "balanced"
    visual_policy: VisualPolicy = "real_asset_first"
    claim_policy: ClaimPolicy = "standard_fact_voice"
    sensitivity_level: SensitivityLevel = "medium"
    human_review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)


class StoryFactPackV3(BaseModel):
    core_event: str = ""
    what_changed: str = ""
    why_now: str = ""
    key_entities: list[str] = Field(default_factory=list)
    key_numbers: list[str] = Field(default_factory=list)
    key_locations: list[str] = Field(default_factory=list)
    time_reference: str = ""
    source_attribution: str = ""
    evidence_level: EvidenceLevel = "full_text"
    uncertainty_level: UncertaintyLevel = "confirmed"


class PlanningDecision(BaseModel):
    status: PlanningStatus = "produce"
    story_family: StoryFamily = "general_update"
    editorial_intent: EditorialIntent = "break"
    layout_family: LayoutFamily = "generic_story_stack"
    scene_count: int = Field(default=3, ge=1, le=6)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    reason: str = ""


class SceneBlueprint(BaseModel):
    goal: SceneGoal
    visual_type: VisualType
    must_include: list[str] = Field(default_factory=list)
    safe_voice_rule: SafeVoiceRule = "fact_voice"


class VerticalVideoBlueprint(BaseModel):
    target_duration_seconds: int = Field(default=15, ge=8, le=45)
    scene_blueprints: list[SceneBlueprint] = Field(default_factory=list)


class CarouselBlueprint(BaseModel):
    slide_count: int = Field(default=4, ge=2, le=8)
    cover_angle: str = ""
    slide_goals: list[str] = Field(default_factory=list)


class OutputBlueprint(BaseModel):
    vertical_video: VerticalVideoBlueprint | None = None
    carousel: CarouselBlueprint | None = None


class VerticalVideoSceneOutput(BaseModel):
    scene_id: str
    start_second: int = 0
    duration_seconds: int = 0
    headline: str
    body: str = ""
    voiceover: str = ""
    overlay_text: str = ""
    visual_direction: str = ""


class VerticalVideoOutput(BaseModel):
    aspect_ratio: Literal["9:16"] = "9:16"
    target_platforms: list[Literal["youtube_shorts", "instagram_reels", "tiktok"]] = Field(
        default_factory=lambda: ["youtube_shorts", "instagram_reels", "tiktok"]
    )
    duration_seconds: int = 30
    hook: str = ""
    title: str = ""
    tts_script: str = ""
    overlay_text: list[str] = Field(default_factory=list)
    scenes: list[VerticalVideoSceneOutput] = Field(default_factory=list)
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)


class CarouselCardOutput(BaseModel):
    title: str
    body: str = ""
    kicker: str = ""
    image_prompt: str = ""


class CarouselOutput(BaseModel):
    cover: CarouselCardOutput
    slides: list[CarouselCardOutput] = Field(default_factory=list)
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)


class ImagePromptOutput(BaseModel):
    usage: Literal["cover", "scene", "supporting"] = "supporting"
    prompt: str


class PlatformOutputs(BaseModel):
    vertical_video: VerticalVideoOutput | None = None
    carousel: CarouselOutput | None = None
    image_prompts: list[ImagePromptOutput] = Field(default_factory=list)


class TopicBrief(BaseModel):
    topic_id: str
    category: str
    secondary_categories: list[ContentCategory] = Field(default_factory=list)
    aggregation_type: Literal["shared", "unique"]
    story_language: str = "en"
    editorial_type: str = "report"
    quality_status: Literal["publishable", "review"] = "publishable"
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    review_reasons: list[str] = Field(default_factory=list)
    video_quality_status: Literal["publishable", "review", "reject"] = "publishable"
    video_quality_score: int = Field(default=100, ge=0, le=100)
    video_review_reasons: list[str] = Field(default_factory=list)
    latest_feedback: TopicLatestFeedback | None = None
    headline_tr: str
    summary_tr: str
    key_points_tr: list[str] = Field(default_factory=list)
    why_it_matters_tr: str
    confidence: float = Field(ge=0.0, le=1.0)
    source_count: int
    article_count: int
    sources: list[str] = Field(default_factory=list)
    representative_articles: list[TopicRepresentativeArticle] = Field(default_factory=list)
    visual_assets: list[VisualAsset] = Field(default_factory=list)
    video_prompt_en: str
    video_prompt_parts: VideoPromptParts
    video_plan: VideoPlan
    video_content: VideoContent | None = None
    strategy: ContentStrategy = Field(default_factory=ContentStrategy)
    platform_outputs: PlatformOutputs = Field(default_factory=PlatformOutputs)
    story_fact_pack: StoryFactPackV3 = Field(default_factory=StoryFactPackV3)
    planning_decision: PlanningDecision = Field(default_factory=PlanningDecision)
    output_blueprint: OutputBlueprint = Field(default_factory=OutputBlueprint)
    remotion_storyboard: RemotionStoryboard
    planning_debug: PlanningDebug | None = None


class TopicGroup(BaseModel):
    category: str
    topics: list[TopicBrief] = Field(default_factory=list)


class AnalysisSourceDebug(BaseModel):
    source_slug: str
    source_name: str
    article_count: int


class AnalysisClusterDebug(BaseModel):
    category: str
    article_count: int
    source_count: int
    sources: list[str] = Field(default_factory=list)
    sample_titles: list[str] = Field(default_factory=list)


class AnalysisRejectionDebug(BaseModel):
    reason: str
    count: int


class AnalysisReviewDebug(BaseModel):
    reason: str
    count: int


class AnalysisFeedbackDebug(BaseModel):
    label: FeedbackLabel
    count: int


class AnalysisDebug(BaseModel):
    fetched_articles: int = 0
    prepared_articles: int = 0
    rejected_articles: int = 0
    candidate_clusters: int = 0
    multi_source_clusters: int = 0
    single_source_clusters: int = 0
    shared_topics_generated: int = 0
    unique_topics_generated: int = 0
    publishable_topics_generated: int = 0
    review_topics_generated: int = 0
    video_publishable_topics_generated: int = 0
    video_review_topics_generated: int = 0
    video_rejected_topics_generated: int = 0
    rejected_unique_candidates: int = 0
    dropped_unique_articles: int = 0
    source_breakdown: list[AnalysisSourceDebug] = Field(default_factory=list)
    cluster_previews: list[AnalysisClusterDebug] = Field(default_factory=list)
    rejection_breakdown: list[AnalysisRejectionDebug] = Field(default_factory=list)
    review_breakdown: list[AnalysisReviewDebug] = Field(default_factory=list)
    video_review_breakdown: list[AnalysisReviewDebug] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    ollama_base_url: str | None = None
    ollama_error: str | None = None


class TopicBriefsResponse(BaseModel):
    analysis_status: Literal["ok", "degraded"]
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    groups: list[TopicGroup] = Field(default_factory=list)
    debug: AnalysisDebug | None = None


class TopicQualitySampleRejection(BaseModel):
    title: str
    reason: str


class TopicQualitySampleReviewTopic(BaseModel):
    headline: str
    reasons: list[str] = Field(default_factory=list)


class TopicQualityScoreBand(BaseModel):
    label: str
    count: int = 0


class TopicQualityScoredTopic(BaseModel):
    headline: str
    quality_status: Literal["publishable", "review"]
    quality_score: float = Field(ge=0.0, le=1.0)


class TopicQualityTotals(BaseModel):
    fetched_articles: int = 0
    prepared_articles: int = 0
    rejected_articles: int = 0
    candidate_clusters: int = 0
    publishable_topics: int = 0
    review_topics: int = 0
    rejected_topics: int = 0
    shared_topics: int = 0
    unique_topics: int = 0
    avg_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    publishable_avg_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    review_avg_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    video_publishable_topics: int = 0
    video_review_topics: int = 0
    video_rejected_topics: int = 0
    feedback_count: int = 0
    feedback_coverage_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    score_distribution: list[TopicQualityScoreBand] = Field(default_factory=list)
    rejection_breakdown: list[AnalysisRejectionDebug] = Field(default_factory=list)
    input_rejection_breakdown: list[AnalysisRejectionDebug] = Field(default_factory=list)
    review_breakdown: list[AnalysisReviewDebug] = Field(default_factory=list)
    video_review_breakdown: list[AnalysisReviewDebug] = Field(default_factory=list)
    feedback_breakdown: list[AnalysisFeedbackDebug] = Field(default_factory=list)


class TopicQualitySourceReport(BaseModel):
    source_slug: str
    source_name: str
    article_count: int = 0
    prepared_article_count: int = 0
    rejected_article_count: int = 0
    topic_contributions: int = 0
    publishable_contributions: int = 0
    review_contributions: int = 0
    shared_contributions: int = 0
    unique_contributions: int = 0
    avg_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    publishable_avg_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    review_avg_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    rejection_breakdown: list[AnalysisRejectionDebug] = Field(default_factory=list)
    review_breakdown: list[AnalysisReviewDebug] = Field(default_factory=list)
    sample_rejections: list[TopicQualitySampleRejection] = Field(default_factory=list)
    sample_review_topics: list[TopicQualitySampleReviewTopic] = Field(default_factory=list)
    lowest_scoring_topics: list[TopicQualityScoredTopic] = Field(default_factory=list)


class TopicQualityReportResponse(BaseModel):
    analysis_status: Literal["ok", "degraded"]
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    totals: TopicQualityTotals
    sources: list[TopicQualitySourceReport] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    ollama_error: str | None = None


class TopicFeedbackSnapshotInput(BaseModel):
    headline_tr: str
    summary_tr: str
    category: str
    aggregation_type: Literal["shared", "unique"]
    quality_status: Literal["publishable", "review"]
    quality_score: float = Field(ge=0.0, le=1.0)
    video_quality_status: Literal["publishable", "review", "reject"]
    video_quality_score: int = Field(ge=0, le=100)
    source_count: int
    article_count: int
    sources: list[str] = Field(default_factory=list)
    source_slugs: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)
    video_review_reasons: list[str] = Field(default_factory=list)
    representative_article_ids: list[uuid.UUID] = Field(default_factory=list)
    has_visual_asset: bool = False
    has_published_at: bool = False


class TopicFeedbackUpsertRequest(BaseModel):
    topic_id: str
    feedback_label: FeedbackLabel
    note: str | None = None
    topic_snapshot: TopicFeedbackSnapshotInput


class TopicFeedbackResponse(BaseModel):
    topic_id: str
    latest_feedback: TopicLatestFeedback


class TopicFeedbackDeleteResponse(BaseModel):
    topic_id: str
    deleted: bool


class TopicScoreWeightRecommendation(BaseModel):
    feature: str
    current_weight: float
    recommended_weight: float
    delta: float
    active_count: int
    inactive_count: int
    approval_rate_when_active: float = Field(ge=0.0, le=1.0)
    approval_rate_when_inactive: float = Field(ge=0.0, le=1.0)
    lift: float


class TopicScoreTuningSample(BaseModel):
    topic_id: str
    headline_tr: str
    feedback_label: FeedbackLabel
    quality_status: Literal["publishable", "review"]
    quality_score: float = Field(ge=0.0, le=1.0)


class TopicScoreTuningTotals(BaseModel):
    feedback_count: int = 0
    approved_count: int = 0
    negative_count: int = 0
    eligible_for_recommendations: bool = False
    feedback_breakdown: list[AnalysisFeedbackDebug] = Field(default_factory=list)


class TopicScoreTuningCalibrationSummary(BaseModel):
    high_score_negative_count: int = 0
    low_score_approved_count: int = 0


class TopicScoreTuningMismatchSamples(BaseModel):
    high_score_negative: list[TopicScoreTuningSample] = Field(default_factory=list)
    low_score_approved: list[TopicScoreTuningSample] = Field(default_factory=list)


class TopicScoreTuningReportResponse(BaseModel):
    generated_at: datetime
    days: int
    source_category: str | None = None
    category: str | None = None
    totals: TopicScoreTuningTotals
    current_weights: dict[str, float] = Field(default_factory=dict)
    recommendations: list[TopicScoreWeightRecommendation] = Field(default_factory=list)
    calibration_summary: TopicScoreTuningCalibrationSummary
    mismatch_samples: TopicScoreTuningMismatchSamples
    notes: list[str] = Field(default_factory=list)
