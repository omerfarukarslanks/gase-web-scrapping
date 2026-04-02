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


class TopicBrief(BaseModel):
    topic_id: str
    category: str
    aggregation_type: Literal["shared", "unique"]
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


class AnalysisDebug(BaseModel):
    fetched_articles: int = 0
    prepared_articles: int = 0
    candidate_clusters: int = 0
    multi_source_clusters: int = 0
    single_source_clusters: int = 0
    shared_topics_generated: int = 0
    unique_topics_generated: int = 0
    dropped_unique_articles: int = 0
    source_breakdown: list[AnalysisSourceDebug] = Field(default_factory=list)
    cluster_previews: list[AnalysisClusterDebug] = Field(default_factory=list)
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
