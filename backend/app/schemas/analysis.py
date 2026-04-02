import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    master_format: Literal["16:9"]
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


class TopicBrief(BaseModel):
    topic_id: str
    category: str
    aggregation_type: Literal["shared", "unique"]
    quality_status: Literal["publishable", "review"] = "publishable"
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    review_reasons: list[str] = Field(default_factory=list)
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
    remotion_storyboard: RemotionStoryboard


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
    rejected_unique_candidates: int = 0
    dropped_unique_articles: int = 0
    source_breakdown: list[AnalysisSourceDebug] = Field(default_factory=list)
    cluster_previews: list[AnalysisClusterDebug] = Field(default_factory=list)
    rejection_breakdown: list[AnalysisRejectionDebug] = Field(default_factory=list)
    review_breakdown: list[AnalysisReviewDebug] = Field(default_factory=list)
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
    feedback_count: int = 0
    feedback_coverage_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    score_distribution: list[TopicQualityScoreBand] = Field(default_factory=list)
    rejection_breakdown: list[AnalysisRejectionDebug] = Field(default_factory=list)
    review_breakdown: list[AnalysisReviewDebug] = Field(default_factory=list)
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
    source_count: int
    article_count: int
    sources: list[str] = Field(default_factory=list)
    source_slugs: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)
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
