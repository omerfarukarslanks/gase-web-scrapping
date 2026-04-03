from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.article import Article
from app.models.source import Source
from app.models.topic_feedback import TopicFeedback
from app.schemas.analysis import (
    AnalysisFeedbackDebug,
    AnalysisClusterDebug,
    AnalysisDebug,
    AnalysisRejectionDebug,
    AnalysisReviewDebug,
    AnalysisSourceDebug,
    PlanningDebug,
    PlanningDebugAngleScore,
    RemotionStat,
    TopicBrief,
    TopicBriefsResponse,
    TopicFeedbackDeleteResponse,
    TopicFeedbackResponse,
    TopicFeedbackSnapshotInput,
    TopicFeedbackUpsertRequest,
    TopicGroup,
    TopicLatestFeedback,
    TopicQualityReportResponse,
    TopicQualityScoreBand,
    TopicQualityScoredTopic,
    TopicQualitySampleRejection,
    TopicQualitySampleReviewTopic,
    TopicQualitySourceReport,
    TopicQualityTotals,
    TopicRepresentativeArticle,
    TopicScoreTuningCalibrationSummary,
    TopicScoreTuningMismatchSamples,
    TopicScoreTuningReportResponse,
    TopicScoreTuningSample,
    TopicScoreTuningTotals,
    TopicScoreWeightRecommendation,
    VisualAsset,
    VideoPlan,
    VideoPlanScene,
    VideoContent,
    VideoPromptParts,
)
from app.services.remotion_storyboard_service import (
    RemotionStoryboardContext,
    RemotionStoryboardService,
)
from app.services.article_visibility import apply_article_visibility_filters
from app.services.visual_asset_service import VisualAssetCandidate, VisualAssetResolver
from app.scrapers.utils.deduplication import normalize_title, titles_are_similar

logger = logging.getLogger(__name__)

VALID_SOURCE_CATEGORIES = {"general", "finance", "sports"}
VALID_CONTENT_CATEGORIES = {
    "world",
    "politics",
    "business",
    "technology",
    "sports",
    "entertainment",
    "science",
    "health",
    "opinion",
    "general",
}
SOURCE_TO_CONTENT_CATEGORY = {
    "general": "general",
    "finance": "business",
    "sports": "sports",
}
CATEGORY_KEYWORDS = {
    "world": {"world", "international", "global", "foreign", "us news", "europe", "middle east"},
    "politics": {
        "politics",
        "political",
        "election",
        "elections",
        "government",
        "white house",
        "congress",
        "parliament",
        "policy",
        "senate",
    },
    "business": {"business", "economy", "economic", "markets", "market", "finance", "money", "moneywatch", "wealth"},
    "technology": {"technology", "tech", "ai", "artificial intelligence", "science and technology"},
    "sports": {"sports", "sport", "soccer", "nba", "nfl", "tennis", "golf", "f1", "cricket"},
    "entertainment": {"entertainment", "culture", "arts", "lifestyle", "film", "tv", "music"},
    "science": {"science", "environment", "climate", "space", "green"},
    "health": {"health", "medical", "medicine", "wellness"},
    "opinion": {"opinion", "analysis", "editorial", "leaders", "comment"},
}
STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "at",
    "from",
    "by",
    "with",
    "after",
    "before",
    "amid",
    "into",
    "over",
    "under",
    "new",
    "latest",
    "live",
    "says",
    "say",
    "as",
    "is",
    "are",
    "be",
    "that",
    "this",
    "it",
}
ROLE_PREFIXES = ("coach ", "manager ", "captain ", "sir ", "mr ", "mrs ", "ms ")
WORD_RE = re.compile(r"[a-z0-9']+")
SCORE_RE = re.compile(r"\b\d{1,3}\s*-\s*\d{1,3}\b")
NUMERIC_PHRASE_RE = re.compile(r"\b\d[\w.-]*(?:\s+[A-Za-z][\w'-]*){0,3}\b")
HTML_ENTITY_RE = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]+);")
TRAILING_CONNECTOR_RE = re.compile(
    r"(?:\b(?:vs|to|and|or|with|from|after|before|for|on|at|in|by|around|amid|against)\.?|\()\s*$",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
PROPER_NOUN_RE = re.compile(
    r"\b(?:[A-Z]{2,}|[A-Z][a-z]+)(?:['’]s)?(?:\s+(?:[A-Z]{2,}|[A-Z][a-z]+)(?:['’]s)?){0,3}\b"
)
GENERIC_PROMPT_MARKERS = (
    "breaking news recap focused on",
    "use newsroom-style graphics",
    "template-friendly motion graphics",
    "show key evidence from coverage by",
    "forward-looking recap",
    "clean impact board",
)
VALID_VIDEO_PLAN_PURPOSES = {"hook", "explain", "detail", "context", "comparison", "takeaway", "close"}
VALID_VIDEO_PLAN_LAYOUTS = {"headline", "split", "stat", "timeline", "quote", "comparison", "minimal", "full-bleed"}
VALID_VIDEO_PLAN_SOURCE_VISIBILITY = {"none", "subtle", "contextual"}
SOURCE_REFERENCE_PATTERNS = (
    re.compile(r"\b\d+\s*farkli kaynagin[^.?!]*[.?!]?", re.IGNORECASE),
    re.compile(r"\bbirden fazla kaynagin[^.?!]*[.?!]?", re.IGNORECASE),
    re.compile(r"\btek kaynakta[^.?!]*[.?!]?", re.IGNORECASE),
    re.compile(r"\biki buyuk kaynak[^.?!]*[.?!]?", re.IGNORECASE),
    re.compile(r"\b(?:multiple|several|two|three)\s+sources?[^.?!]*[.?!]?", re.IGNORECASE),
)
COMPARISON_SIGNAL_RE = re.compile(
    r"\b(vs\.?|versus|head[- ]to[- ]head|compared with|comparison|beat|beats|beating|defeat|defeats|defeated|edge past|outperform|underperform|higher than|lower than)\b",
    re.IGNORECASE,
)
NEWSLIKE_URL_RE = re.compile(r"/(?:\d{4}/\d{2}/\d{2}|content/[a-f0-9-]{8,}|articles?/[\w-]{12,}|\d{8}-[\w-]{12,})")
TITLE_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){2,}$")
MARKET_SIGNAL_RE = re.compile(
    r"\b(stock|stocks|share|shares|bond|bonds|yield|yields|oil|crude|price|prices|markets?|investors?|equities|treasury|tariff|inflation|earnings|forecast|profit|loss|revenue|currency|currencies|fx|dollar|euro)\b",
    re.IGNORECASE,
)
SPORTS_SCHEDULE_SIGNAL_RE = re.compile(
    r"\b(schedule|fixtures?|dates?|venues?|home-away|calendar|draw|round[- ]robin)\b",
    re.IGNORECASE,
)
SPORTS_ODDS_SIGNAL_RE = re.compile(
    r"\b(odds|prediction|predictions|spread|line|betting|favorite|favourite|picks|model)\b",
    re.IGNORECASE,
)
SPORTS_ADMIN_SIGNAL_RE = re.compile(
    r"\b(president|commissioner|director|athletic director|ad\b|resigns?|rule|policy|conference championship|federation)\b",
    re.IGNORECASE,
)
NON_NEWS_URL_SEGMENTS = {
    "subscription",
    "subscriptions",
    "account",
    "accounts",
    "settings",
    "newsletter",
    "newsletters",
    "gift-guide",
    "gift-guides",
    "guide",
    "guides",
    "calculator",
    "calculators",
    "workwise",
    "sponsored",
    "sponsored-contents",
    "replay",
    "video",
    "videos",
    "watch",
    "liveblog",
    "live-blog",
    "topic",
    "topics",
    "tag",
    "tags",
    "author",
    "authors",
    "search",
    "news-alerts-settings",
}
NON_NEWS_URL_HINTS = {
    "subscription",
    "calculator",
    "gift-guide",
    "gift-guides",
    "newsletter",
    "settings",
    "sponsored",
    "replay",
    "video",
    "videos",
    "workwise",
    "topic",
    "topics",
    "tag",
    "tags",
    "author",
    "authors",
}
UTILITY_TITLE_TERMS = {
    "subscriptions",
    "subscription",
    "workwise",
    "gift guide",
    "gift guides",
    "calculator",
    "calculators",
    "latest newscast",
    "closed-captioned newscast",
    "sponsored contents",
    "news alerts settings",
    "promo code",
    "bonus bets",
}
SINGLE_WORD_SECTION_TERMS = {
    "subscriptions",
    "workwise",
    "lifestyle",
    "opinion",
    "videos",
    "video",
    "podcasts",
}
GENERIC_ENTITY_TOKENS = {
    "check",
    "latest",
    "jet",
    "news",
    "world",
    "general",
    "duration",
    "home",
    "guide",
    "president",
    "political",
    "reaction",
    "watch",
    "next",
    "night",
    "historic",
}
VALID_REJECTION_REASONS = {
    "non_news_url",
    "utility_or_hub_page",
    "stale_or_evergreen",
    "broken_title",
    "html_artifact",
    "low_signal_unique",
    "template_mismatch",
}
VALID_REVIEW_REASONS = {
    "single_source_topic",
    "missing_visual_asset",
    "thin_summary",
    "truncated_headline",
    "degraded_generation",
}
VALID_VIDEO_REVIEW_REASONS = {
    "cross_story_contamination",
    "broken_copy",
    "unsupported_claim",
    "generic_why_it_matters",
    "headline_only_support",
    "weak_scene_progression",
    "low_information_anchors",
    "missing_numeric_impact",
    "missing_institutional_context",
    "missing_sports_result_context",
    "speculative_story",
    "mixed_language_copy",
    "generic_asset_only",
    "missing_domain_fact_pack",
    "missing_allegation_framing",
    "missing_legal_consequence",
    "missing_crime_setup",
}
HARD_VIDEO_REJECT_REASONS = {
    "cross_story_contamination",
    "broken_copy",
    "unsupported_claim",
    "missing_allegation_framing",
}
VALID_FEEDBACK_LABELS = {"approved", "wrong", "boring", "malformed"}
QUALITY_SCORE_WEIGHTS: dict[str, float] = {
    "base": 0.35,
    "shared_topic": 0.20,
    "unique_topic": 0.08,
    "source_count_ge_2": 0.12,
    "source_count_ge_3": 0.05,
    "has_visual_asset": 0.10,
    "missing_visual_asset": -0.08,
    "non_thin_summary": 0.10,
    "thin_summary": -0.10,
    "non_truncated_headline": 0.08,
    "truncated_headline": -0.12,
    "has_published_at": 0.05,
    "missing_published_at": -0.08,
    "article_count_ge_2": 0.05,
    "degraded_generation": -0.12,
    "review_status": -0.05,
}
QUALITY_SCORE_FEATURES = tuple(feature for feature in QUALITY_SCORE_WEIGHTS if feature != "base")
VIDEO_QUALITY_DEDUCTIONS: dict[str, int] = {
    "cross_story_contamination": 40,
    "broken_copy": 35,
    "unsupported_claim": 30,
    "generic_why_it_matters": 12,
    "headline_only_support": 15,
    "weak_scene_progression": 12,
    "low_information_anchors": 8,
    "missing_numeric_impact": 15,
    "missing_institutional_context": 15,
    "missing_sports_result_context": 15,
    "speculative_story": 12,
    "mixed_language_copy": 20,
    "generic_asset_only": 10,
    "missing_domain_fact_pack": 18,
    "missing_allegation_framing": 20,
    "missing_legal_consequence": 14,
    "missing_crime_setup": 14,
}
SAFE_ANGLE_TYPES_BY_DOMAIN: dict[str, tuple[str, str]] = {
    "sports": ("news_update", "competition_context"),
    "crime_justice": ("breaking_case", "case_explainer"),
    "diplomacy": ("breaking_diplomacy", "regional_context"),
    "business": ("breaking_business", "impact_explainer"),
    "science": ("breakthrough", "practical_significance"),
    "general": ("breaking_update", "context_explainer"),
    "policy": ("breaking_update", "context_explainer"),
}
ANGLE_PRIORITY_BY_DOMAIN: dict[str, tuple[str, ...]] = {
    "sports": ("news_update", "competition_context"),
    "crime_justice": ("breaking_case", "case_explainer"),
    "diplomacy": ("breaking_diplomacy", "regional_context"),
    "business": ("breaking_business", "impact_explainer"),
    "science": ("breakthrough", "practical_significance"),
    "general": ("breaking_update", "context_explainer"),
    "policy": ("breaking_update", "context_explainer"),
}
ANGLE_LABELS: dict[str, str] = {
    "news_update": "straight sports update",
    "competition_context": "competition-context sports update",
    "breaking_case": "breaking case explainer",
    "case_explainer": "case explainer",
    "breaking_diplomacy": "breaking diplomacy update",
    "regional_context": "regional-context diplomacy explainer",
    "breaking_business": "breaking business update",
    "impact_explainer": "impact-focused business explainer",
    "breakthrough": "science breakthrough update",
    "practical_significance": "practical-significance science explainer",
    "breaking_update": "breaking update",
    "context_explainer": "context explainer",
}
TUNING_MIN_FEEDBACK = 40
TUNING_MIN_APPROVED = 15
TUNING_MIN_NEGATIVE = 15
TUNING_MIN_FEATURE_SUPPORT = 10
HIGH_SCORE_NEGATIVE_THRESHOLD = 0.75
LOW_SCORE_APPROVED_THRESHOLD = 0.55
TEXT_NORMALIZATION_TRANSLATION = str.maketrans(
    {
        "\xa0": " ",
        "\u200b": " ",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
    }
)
CLUSTER_TEXT_CHAR_LIMIT = 420
VIDEO_GENERIC_WHY_MARKERS = (
    "the next confirmed update will likely shape where the story goes next",
    "the result can shape the momentum heading into the next game",
    "the move could influence near-term market expectations",
    "the development could shape the next phase of research or missions",
    "the next product or policy response could quickly shift the story",
    "the next official response will shape how the situation develops",
    "the next official response will determine the immediate political impact",
)
DETAIL_TEXT_STOP_MARKERS = (
    "recommended stories",
    "related stories",
    "related keywords",
    "more from",
    "read more",
    "continue reading",
    "also in the show",
    "from the show",
    "issued on:",
    "reading time",
    "to display this content from youtube",
    "advertising related keywords",
)
LOW_INFORMATION_ANCHOR_TOKENS = {
    "office",
    "surging",
    "three",
    "latest",
    "general",
    "story",
    "update",
    "point",
    "week",
    "rates",
    "mortgage",
    "possible landing spot",
    "women's basketball superstar",
    "show",
    "tariffs",
    "trump's",
}
BUSINESS_NUMERIC_HINTS = (
    "mortgage",
    "rate",
    "rates",
    "yield",
    "sales",
    "price",
    "prices",
    "cost",
    "costs",
    "$",
    "%",
    "forecast",
    "inflation",
)
INSTITUTIONAL_CONTEXT_HINTS = (
    "department",
    "ministry",
    "office",
    "court",
    "law",
    "legal",
    "archives",
    "president",
    "government",
    "agency",
    "comply",
)
CRIME_JUSTICE_HINTS = (
    "doj",
    "department of justice",
    "fbi",
    "federal",
    "charged",
    "charges",
    "prosecutor",
    "prosecutors",
    "complaint",
    "police",
    "authorities",
    "kidnapp",
    "robbed",
    "gunpoint",
    "prison",
    "sentence",
)
CRIME_SETUP_HINTS = (
    "luring",
    "lured",
    "under the guise",
    "meeting",
    "setup",
    "ambush",
    "takeover",
    "forced",
    "gunpoint",
)
LEGAL_CONSEQUENCE_HINTS = (
    "charged",
    "charge",
    "faces",
    "federal prison",
    "life in prison",
    "life sentence",
    "up to life",
    "convicted",
    "sentence",
)
DIPLOMACY_HINTS = (
    "peace talks",
    "talks",
    "mediation",
    "mediating",
    "mediator",
    "foreign ministry",
    "foreign minister",
    "resumed conversations",
    "resumed talks",
    "delegation",
    "consultation process",
    "consensus",
    "ceasefire",
)
DIPLOMACY_TRIGGER_HINTS = (
    "after weeks of fighting",
    "deadly fighting",
    "killed hundreds",
    "open war",
    "air strikes",
    "suicide bomber",
    "conflict",
    "ttp",
)
SPORTS_AVAILABILITY_HINTS = (
    "available",
    "bench",
    "not ready to start",
    "fit enough to start",
    "returned to training",
    "returned to first-team training",
    "fit for the game",
    "sidelined",
    "out for",
)
SPORTS_FIXTURE_HINTS = (
    "quarter-final",
    "semifinal",
    "final",
    "fixture",
    "fixtures",
    "fa cup",
    "champions league",
    "premier league",
    "psg",
    "manchester city",
    "etihad",
)
SCIENCE_HINTS = (
    "study",
    "researchers",
    "scientists",
    "trial",
    "peer-reviewed",
    "experiment",
    "discovery",
    "observed",
)
GENERAL_BREAKING_HINTS = (
    "officials said",
    "authorities said",
    "announced",
    "update",
    "developing",
)
SPORTS_RESULT_HINTS = (
    "won",
    "win",
    "beat",
    "defeat",
    "qualified",
    "qualification",
    "shootout",
    "penalty",
    "goal",
    "final",
    "champion",
    "victory",
)
EDITORIAL_TYPES = {
    "report",
    "analysis",
    "speculative",
    "teaser_roundup",
    "segment_teaser",
    "related_links_page",
    "live_blog",
    "video_page",
}
INELIGIBLE_EDITORIAL_TYPES = {
    "teaser_roundup",
    "segment_teaser",
    "related_links_page",
    "live_blog",
    "video_page",
}
SPECULATIVE_EDITORIAL_TYPES = {"speculative"}
SPECULATIVE_MARKERS = (
    "possible landing spot",
    "could land",
    "could join",
    "could be headed",
    "linked with",
    "linked to",
    "expected to",
    "believe she could",
    "possible destination",
    "potential landing spot",
    "rumor",
    "rumour",
)
ANALYSIS_MARKERS = (
    "analysis",
    "explainer",
    "what remains",
    "what to know",
    "how it works",
    "why it matters",
    "opinion",
    "editorial",
)
SEGMENT_TEASER_MARKERS = (
    "also in the show",
    "from the show",
    "issued on:",
    "reading time",
    "to display this content from youtube",
)
RELATED_LINK_MARKERS = (
    "recommended stories",
    "related stories",
    "related keywords",
    "list of 4 items",
    "list of 3 items",
    "list 1 of",
    "list 2 of",
)
TEASER_ROUNDUP_MARKERS = (
    "top stories",
    "latest newscast",
    "watch the latest",
    "morning roundup",
    "evening roundup",
    "roundup",
)
VIDEO_PAGE_MARKERS = (
    "/video/",
    "/videos/",
    "/watch/",
    "video player",
)
LIVE_BLOG_MARKERS = (
    "/live-blog/",
    "/liveblog/",
    "/live/",
    "live updates",
)
GENERIC_ASSET_MARKERS = (
    "social_share",
    "share_generic",
    "share_genric",
    "generic",
    "og_thumbnail",
    "/share/",
)
LANGUAGE_HINT_WORDS: dict[str, tuple[str, ...]] = {
    "en": ("the", "and", "with", "after", "from", "said", "will", "could", "mortgage", "rates", "point", "stay", "fight", "join"),
    "es": ("el", "la", "los", "las", "con", "pero", "equipo", "empata", "continua", "mano", "navarro"),
    "fr": ("le", "la", "les", "avec", "dans", "mais", "show", "france"),
    "tr": ("ve", "bir", "ile", "icin", "gibi", "olan", "haber"),
}
LANGUAGE_CONFIDENCE_THRESHOLD = 2
BROKEN_COPY_PATTERNS = (
    re.compile(r"['\"]{2,}"),
    re.compile(r"[a-z]['\"]{1}[A-Z]"),
    re.compile(r"\b[A-Z][a-z]{0,2}\.$"),
    re.compile(r"[.,;:!?]{2,}"),
)
SENTENCE_PROTECTED_ABBREVIATIONS = (
    "vs.",
    "mr.",
    "mrs.",
    "ms.",
    "dr.",
    "prof.",
    "sr.",
    "jr.",
    "st.",
    "u.s.",
    "u.k.",
)


class OllamaAnalysisError(RuntimeError):
    """Raised when Ollama analysis fails."""


@dataclass(slots=True)
class PreparedArticle:
    article: Article
    normalized_category: str
    cluster_text: str
    detail_text: str
    editorial_type: str
    story_language: str
    uncertainty_level: str
    timestamp: datetime
    source_name: str
    source_slug: str
    tag_tokens: set[str] = field(default_factory=set)
    title_tokens: set[str] = field(default_factory=set)
    text_tokens: set[str] = field(default_factory=set)


@dataclass(slots=True)
class StoryFactPack:
    core_event: str = ""
    primary_event: str = ""
    supporting_fact: str = ""
    supporting_facts: tuple[str, ...] = ()
    trigger_or_setup: str = ""
    impact_or_next: str = ""
    impact_fact: str = ""
    evidence_points: tuple[str, ...] = ()
    numeric_facts: tuple[str, ...] = ()
    actors: tuple[str, ...] = ()
    institution: str = ""
    result_context: str = ""
    legal_consequence: str = ""
    allegation_frame: str = ""
    story_domain: str = "general"
    uncertainty_level: str = "confirmed"
    story_language: str = "en"
    editorial_type: str = "report"


@dataclass(slots=True)
class TopicPlanningSelection:
    primary_topic: TopicBrief
    alternate_topic: TopicBrief | None = None
    planning_debug: PlanningDebug | None = None


@dataclass(slots=True)
class AnalysisRejection:
    reason: str
    stage: str
    title: str
    url: str
    source_slug: str
    source_name: str


@dataclass(slots=True)
class PreparedArticlesResult:
    prepared_articles: list[PreparedArticle]
    rejections: list[AnalysisRejection] = field(default_factory=list)


@dataclass(slots=True)
class TopicAnalysisEntry:
    topic: TopicBrief
    quality_status: str
    quality_score: float
    score_features: dict[str, bool] = field(default_factory=dict)
    review_reasons: tuple[str, ...] = ()
    video_quality_status: str = "publishable"
    video_quality_score: int = 100
    video_review_reasons: tuple[str, ...] = ()
    source_slugs: tuple[str, ...] = ()
    source_names: tuple[str, ...] = ()
    degraded_generation: bool = False


@dataclass(slots=True)
class TopicAnalysisRunResult:
    analysis_status: str
    window_start: datetime
    window_end: datetime
    articles: list[Article]
    prepared_articles: list[PreparedArticle]
    candidate_clusters: list[list[PreparedArticle]]
    rejections: list[AnalysisRejection]
    topic_entries: list[TopicAnalysisEntry]
    notes: list[str] = field(default_factory=list)
    ollama_error: str | None = None
    shared_topics_generated: int = 0
    unique_topics_generated: int = 0
    rejected_unique_candidates: int = 0
    total_unique_candidate_articles: int = 0


@dataclass(slots=True)
class SourceAnalysisRules:
    reject_url_substrings: tuple[str, ...] = ()
    reject_url_patterns: tuple[re.Pattern[str], ...] = ()
    reject_title_terms: tuple[str, ...] = ()
    reject_title_patterns: tuple[re.Pattern[str], ...] = ()
    evergreen_title_terms: tuple[str, ...] = ()
    force_story_subtype_by_title_terms: dict[str, tuple[str, ...]] = field(default_factory=dict)
    force_story_subtype_by_url_terms: dict[str, tuple[str, ...]] = field(default_factory=dict)
    allow_unique_without_published_at: bool = False


VALID_STORY_SUBTYPES_BY_CATEGORY = {
    "sports": {"matchup", "schedule", "odds", "admin", "update"},
    "business": {"market", "general"},
}
QUALITY_SCORE_BANDS = (
    ("0.90-1.00", 0.90, 1.01),
    ("0.75-0.89", 0.75, 0.90),
    ("0.60-0.74", 0.60, 0.75),
    ("0.40-0.59", 0.40, 0.60),
    ("0.00-0.39", 0.00, 0.40),
)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def compact_text(value: str | None) -> str:
    if value is None:
        return ""
    normalized = html.unescape(str(value)).translate(TEXT_NORMALIZATION_TRANSLATION)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
    normalized = re.sub(r"\.{4,}", "...", normalized)
    return normalized


def truncate_viewer_text(value: str, limit: int = 500) -> str:
    compacted = compact_text(value)
    if len(compacted) <= limit:
        return compacted
    trimmed = compacted[:limit].rstrip(",;:.!?'\"")
    if " " in trimmed:
        trimmed = trimmed.rsplit(" ", 1)[0]
    return compact_text(trimmed)


def trim_words(value: str, max_words: int) -> str:
    words = compact_text(value).split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(",;:.") + "..."


def trim_viewer_words(value: str, max_words: int) -> str:
    words = compact_text(value).split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(",;:.!?")


def split_sentences(value: str) -> list[str]:
    compacted = compact_text(value)
    if not compacted:
        return []
    protected = compacted
    placeholder_map: dict[str, str] = {}
    for index, abbreviation in enumerate(SENTENCE_PROTECTED_ABBREVIATIONS):
        placeholder = f"__abbr_{index}__"
        pattern = re.compile(rf"\b{re.escape(abbreviation)}", re.IGNORECASE)
        def _replace_abbreviation(match: re.Match[str], *, token: str = placeholder) -> str:
            placeholder_map[token] = match.group(0)
            return token

        protected = pattern.sub(_replace_abbreviation, protected)

    parts = re.split(r"(?<=[.!?])\s+", protected)
    restored = []
    for part in parts:
        normalized = part
        for placeholder, original in placeholder_map.items():
            normalized = normalized.replace(placeholder, original)
        normalized = compact_text(normalized)
        if normalized:
            restored.append(normalized)
    return restored


def remove_source_labels(value: str, source_names: list[str]) -> str:
    cleaned = compact_text(value).replace("|", ". ").replace("•", ". ")
    for source_name in sorted({name for name in source_names if compact_text(name)}, key=len, reverse=True):
        escaped = re.escape(source_name)
        cleaned = re.sub(rf"(^|[.;]\s*){escaped}\s*:\s*", r"\1", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"\baccording to\s+{escaped}\b[:,]?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"\b{escaped}\b[:,]?\s*", "", cleaned, flags=re.IGNORECASE)
    for pattern in SOURCE_REFERENCE_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"\s+[|/]\s+", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    return compact_text(cleaned)


def fix_concatenated_words(value: str) -> str:
    """Fix words concatenated without space, e.g. 'satelliteThe' → 'satellite. The'."""
    # Pattern: lowercase letter immediately followed by uppercase letter (camelCase boundary)
    # e.g. "satelliteThe", "indicatorA", "launchNASA"
    value = re.sub(r"([a-z])([A-Z])", r"\1. \2", value)
    # Pattern: period/comma immediately followed by letter without space
    # e.g. ".The" → ". The", ",according" → ", according"
    value = re.sub(r"([.,;:!?])([A-Za-z])", r"\1 \2", value)
    return value


def clean_viewer_text(
    value: str | None,
    *,
    source_names: list[str] | None = None,
    max_sentences: int = 3,
    max_chars: int = 2000,
) -> str:
    cleaned = remove_source_labels(value or "", source_names or [])
    if not cleaned:
        return ""
    cleaned = fix_concatenated_words(cleaned)
    sentences = dedupe_preserve_order(split_sentences(cleaned))
    if not sentences:
        sentences = [cleaned]
    merged = " ".join(sentences[:max_sentences])
    return truncate_viewer_text(compact_text(merged), max_chars)


def clean_viewer_points(
    values: list[str],
    *,
    source_names: list[str] | None = None,
    max_items: int = 2,
    max_chars: int = 2000,
) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        normalized = clean_viewer_text(
            value,
            source_names=source_names,
            max_sentences=3,
            max_chars=max_chars,
        )
        if normalized:
            cleaned.append(normalized)
    return dedupe_preserve_order(cleaned)[:max_items]


def text_similarity(left: str, right: str) -> float:
    left_clean = compact_text(left)
    right_clean = compact_text(right)
    if not left_clean or not right_clean:
        return 0.0
    return max(
        SequenceMatcher(None, left_clean.lower(), right_clean.lower()).ratio(),
        jaccard_similarity(tokenize(left_clean, max_tokens=50), tokenize(right_clean, max_tokens=50)),
    )


def strip_detail_boilerplate(value: str | None) -> str:
    cleaned = compact_text(value)
    if not cleaned:
        return ""

    lowered = cleaned.lower()
    cutoffs = [lowered.find(marker) for marker in DETAIL_TEXT_STOP_MARKERS if marker in lowered]
    if cutoffs:
        cleaned = cleaned[: min(index for index in cutoffs if index >= 0)]

    cleaned = re.sub(r"list of \d+ items[^.?!]*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"list \d+ of \d+[^.?!]*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"-\s*list \d+ of \d+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bissued on:\s*[^.?!]*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bfrom the show\b[^.?!]*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\breading time\s*\d+\s*min[^.?!]*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\badvertising related keywords\b.*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bto display this content from youtube\b[^.?!]*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:one of your browser extensions|you may need to disable it)[^.?!]*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bby:\s*$", " ", cleaned, flags=re.IGNORECASE)
    return compact_text(cleaned)


def detect_text_language(text: str, *, fallback: str = "en") -> str:
    normalized = compact_text(text).lower()
    if not normalized:
        return fallback

    token_counts: dict[str, int] = {}
    for language, hints in LANGUAGE_HINT_WORDS.items():
        token_counts[language] = sum(len(re.findall(rf"\b{re.escape(hint)}\b", normalized)) for hint in hints)

    if any(character in normalized for character in "ñáéíóúü"):
        token_counts["es"] += 2
    if any(character in normalized for character in "çğıöşü"):
        token_counts["tr"] += 2
    if any(character in normalized for character in "àâçéèêëîïôûùüÿœæ"):
        token_counts["fr"] += 1

    best_language, best_score = max(token_counts.items(), key=lambda item: item[1], default=(fallback, 0))
    if best_score < LANGUAGE_CONFIDENCE_THRESHOLD:
        return fallback
    return best_language


def contains_text_marker(value: str, marker: str) -> bool:
    normalized_value = compact_text(value).lower()
    normalized_marker = compact_text(marker).lower()
    if not normalized_value or not normalized_marker:
        return False
    return bool(re.search(rf"(?<!\w){re.escape(normalized_marker)}(?!\w)", normalized_value))


def dominant_story_language(cluster: list[PreparedArticle] | list[Article], *, fallback: str = "en") -> str:
    scores: dict[str, int] = defaultdict(int)
    for item in cluster:
        if isinstance(item, PreparedArticle):
            article = item.article
            text = " ".join([item.detail_text, item.cluster_text, article.title, article.summary or ""])
            language_hint = compact_text(item.story_language) or compact_text(article.language)
        else:
            article = item
            text = " ".join([article.content_text or "", article.content_snippet or "", article.summary or "", article.title])
            language_hint = compact_text(article.language)
        detected = detect_text_language(text, fallback=language_hint or fallback)
        scores[detected] += 2
        if language_hint:
            scores[language_hint] += 1
    if not scores:
        return fallback
    return max(scores.items(), key=lambda item: item[1])[0]


def classify_editorial_type(article: Article, *, detail_text: str) -> str:
    title = compact_text(article.title).lower()
    url = compact_text(article.url).lower()
    combined = compact_text(" ".join([article.title, article.summary or "", detail_text])).lower()

    if any(marker in url or marker in combined for marker in LIVE_BLOG_MARKERS):
        return "live_blog"
    if any(marker in url or marker in combined for marker in VIDEO_PAGE_MARKERS):
        return "video_page"
    if any(contains_text_marker(combined, marker) for marker in RELATED_LINK_MARKERS):
        return "related_links_page"
    if any(contains_text_marker(combined, marker) for marker in SEGMENT_TEASER_MARKERS):
        return "segment_teaser"
    if any(contains_text_marker(title, marker) or contains_text_marker(combined, marker) for marker in TEASER_ROUNDUP_MARKERS):
        return "teaser_roundup"
    if any(contains_text_marker(title, marker) or contains_text_marker(combined, marker) for marker in SPECULATIVE_MARKERS):
        return "speculative"
    if compact_text(article.category).lower() == "opinion" or any(marker in title for marker in ANALYSIS_MARKERS):
        return "analysis"
    return "report"


def classify_uncertainty_level(editorial_type: str) -> str:
    return "speculative" if editorial_type in SPECULATIVE_EDITORIAL_TYPES else "confirmed"


def informative_anchor(value: str, *, headline: str = "") -> str:
    candidate = compact_text(value).strip(".,;:!?")
    if not candidate:
        return ""
    lowered = candidate.lower()
    if lowered in LOW_INFORMATION_ANCHOR_TOKENS:
        return ""
    if text_similarity(candidate, headline) >= 0.96:
        return ""
    if " " not in candidate:
        if candidate.isupper():
            return candidate
        if not candidate[:1].isupper():
            return ""
        if len(candidate) < 4:
            return ""
        if lowered in GENERIC_ENTITY_TOKENS:
            return ""
    return candidate


def filter_informative_anchors(
    values: list[str],
    *,
    headline: str = "",
    max_items: int = 5,
) -> list[str]:
    anchors: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = informative_anchor(value, headline=headline)
        if not candidate:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        anchors.append(candidate)
        if len(anchors) >= max_items:
            break
    return anchors


def text_contains_hint(text: str, hint: str) -> bool:
    normalized = compact_text(text).lower()
    if not normalized or not hint:
        return False
    lowered_hint = hint.lower()
    if lowered_hint in {"$", "%"}:
        return lowered_hint in normalized
    return bool(re.search(rf"\b{re.escape(lowered_hint)}\b", normalized))


def text_contains_any_hint(text: str, hints: Iterable[str]) -> bool:
    return any(text_contains_hint(text, hint) for hint in hints)


def is_generic_why_line(value: str) -> bool:
    normalized = compact_text(value).lower()
    if not normalized:
        return True
    return any(marker in normalized for marker in VIDEO_GENERIC_WHY_MARKERS)


def build_why_it_matters_line(
    category: str,
    *,
    headline: str = "",
    summary: str = "",
    key_points: list[str] | None = None,
    cluster: list[PreparedArticle] | None = None,
) -> str:
    key_points = key_points or []
    cluster = cluster or []
    source_names = unique_source_names(cluster)

    candidate_sentences = dedupe_preserve_order(
        [
            clean_viewer_text(point, source_names=source_names, max_sentences=2, max_chars=2000)
            for point in key_points
        ]
        + [
            clean_viewer_text(summary, source_names=source_names, max_sentences=3, max_chars=2000),
        ]
        + [
            clean_viewer_text(
                sentence,
                source_names=source_names,
                max_sentences=3,
                max_chars=2000,
            )
            for item in cluster[:3]
            for sentence in split_sentences(item.detail_text)
        ]
    )

    best_candidate = ""
    best_score = float("-inf")
    lowered_category = compact_text(category).lower()
    for candidate in candidate_sentences:
        normalized = compact_text(candidate)
        if not normalized:
            continue
        if is_generic_why_line(normalized):
            continue
        if looks_broken_title(normalized) or has_html_artifact(normalized):
            continue

        similarity_penalty = text_similarity(normalized, headline) * 0.55
        token_count = len(tokenize(normalized, max_tokens=40))
        keyword_bonus = 0.0
        lower_candidate = normalized.lower()
        if lowered_category == "business" and text_contains_any_hint(lower_candidate, BUSINESS_NUMERIC_HINTS):
            keyword_bonus += 0.25
        if lowered_category in {"world", "politics", "general"} and any(
            text_contains_hint(lower_candidate, token) for token in INSTITUTIONAL_CONTEXT_HINTS
        ):
            keyword_bonus += 0.22
        if lowered_category == "sports" and (extract_score([normalized]) or text_contains_any_hint(lower_candidate, SPORTS_RESULT_HINTS)):
            keyword_bonus += 0.24
        if extract_numeric_phrase([normalized]) or extract_score([normalized]):
            keyword_bonus += 0.18
        if text_contains_any_hint(lower_candidate, ("means", "would", "could", "will", "after", "because", "so")):
            keyword_bonus += 0.1

        score = min(token_count / 16.0, 0.3) + keyword_bonus - similarity_penalty
        if score > best_score and similarity_penalty < 0.68:
            best_candidate = normalized
            best_score = score

    if best_candidate:
        return truncate_viewer_text(best_candidate, 2000)

    fallback_candidates = dedupe_preserve_order(
        clean_viewer_points(key_points, source_names=source_names, max_items=2, max_chars=2000)
        + [clean_viewer_text(summary, source_names=source_names, max_sentences=2, max_chars=2000)]
    )
    for candidate in fallback_candidates:
        if candidate and text_similarity(candidate, headline) < 0.88:
            return truncate_viewer_text(candidate, 2000)

    return truncate_viewer_text(
        clean_viewer_text(summary, source_names=source_names, max_sentences=2, max_chars=2000)
        or trim_viewer_words(headline, 100),
        2000,
    )


def make_rejection(
    reason: str,
    *,
    stage: str,
    title: str,
    url: str,
    source_slug: str,
    source_name: str,
) -> AnalysisRejection:
    normalized_reason = reason if reason in VALID_REJECTION_REASONS else "low_signal_unique"
    return AnalysisRejection(
        reason=normalized_reason,
        stage=stage,
        title=compact_text(title),
        url=compact_text(url),
        source_slug=compact_text(source_slug) or "unknown",
        source_name=compact_text(source_name) or "Unknown Source",
    )


def normalize_rule_terms(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    normalized = [compact_text(str(item)).lower() for item in value if compact_text(str(item))]
    return tuple(dict.fromkeys(normalized))


def normalize_rule_patterns(value: Any) -> tuple[re.Pattern[str], ...]:
    if not isinstance(value, list):
        return ()
    patterns: list[re.Pattern[str]] = []
    for item in value:
        pattern_text = compact_text(str(item))
        if not pattern_text:
            continue
        try:
            patterns.append(re.compile(pattern_text, re.IGNORECASE))
        except re.error:
            continue
    return tuple(patterns)


def normalize_forced_subtype_terms(value: Any) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, tuple[str, ...]] = {}
    valid_subtypes = {subtype for subtypes in VALID_STORY_SUBTYPES_BY_CATEGORY.values() for subtype in subtypes}
    for subtype, terms in value.items():
        normalized_subtype = compact_text(str(subtype)).lower()
        if normalized_subtype not in valid_subtypes:
            continue
        normalized_terms = normalize_rule_terms(terms)
        if normalized_terms:
            normalized[normalized_subtype] = normalized_terms
    return normalized


def parse_source_analysis_rules(source: Source | None) -> SourceAnalysisRules:
    config = source.config if source and isinstance(source.config, dict) else {}
    raw_rules = config.get("analysis_rules")
    if not isinstance(raw_rules, dict):
        return SourceAnalysisRules()

    return SourceAnalysisRules(
        reject_url_substrings=normalize_rule_terms(raw_rules.get("reject_url_substrings")),
        reject_url_patterns=normalize_rule_patterns(raw_rules.get("reject_url_regexes")),
        reject_title_terms=normalize_rule_terms(raw_rules.get("reject_title_terms")),
        reject_title_patterns=normalize_rule_patterns(raw_rules.get("reject_title_regexes")),
        evergreen_title_terms=normalize_rule_terms(raw_rules.get("evergreen_title_terms")),
        force_story_subtype_by_title_terms=normalize_forced_subtype_terms(
            raw_rules.get("force_story_subtype_by_title_terms")
        ),
        force_story_subtype_by_url_terms=normalize_forced_subtype_terms(
            raw_rules.get("force_story_subtype_by_url_terms")
        ),
        allow_unique_without_published_at=bool(raw_rules.get("allow_unique_without_published_at", False)),
    )


def cluster_analysis_rules(cluster: list[PreparedArticle]) -> SourceAnalysisRules:
    if not cluster:
        return SourceAnalysisRules()
    source_slugs = {item.source_slug for item in cluster}
    if len(source_slugs) != 1:
        return SourceAnalysisRules()
    article_source = cluster[0].article.source if hasattr(cluster[0].article, "source") else None
    return parse_source_analysis_rules(article_source)


def match_rule_terms(value: str, terms: tuple[str, ...]) -> bool:
    lowered = compact_text(value).lower()
    return any(term in lowered for term in terms)


def match_rule_patterns(value: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(value) for pattern in patterns)


def forced_story_subtype(
    *,
    category: str,
    headline: str,
    url: str,
    rules: SourceAnalysisRules | None,
) -> str | None:
    if not rules:
        return None
    allowed_subtypes = VALID_STORY_SUBTYPES_BY_CATEGORY.get(category, {"general"})
    lowered_headline = compact_text(headline)
    lowered_url = compact_text(url)

    for subtype, terms in rules.force_story_subtype_by_title_terms.items():
        if subtype in allowed_subtypes and match_rule_terms(lowered_headline, terms):
            return subtype
    for subtype, terms in rules.force_story_subtype_by_url_terms.items():
        if subtype in allowed_subtypes and match_rule_terms(lowered_url, terms):
            return subtype
    return None


def has_html_artifact(value: str | None) -> bool:
    compacted = compact_text(value)
    return bool(HTML_ENTITY_RE.search(value or "") or re.search(r"\b(?:nbsp|quot|amp|8217|8220|8221)\b", compacted))


def looks_like_slug_title(value: str) -> bool:
    compacted = compact_text(value)
    return bool(compacted and TITLE_SLUG_RE.fullmatch(compacted.lower()))


def has_unbalanced_punctuation(value: str) -> bool:
    compacted = compact_text(value)
    if not compacted:
        return False
    single_quotes = compacted.count("'")
    return (
        compacted.count("(") != compacted.count(")")
        or compacted.count('"') % 2 == 1
        or (compacted.endswith("'") and single_quotes == 1)
    )


def looks_broken_title(value: str) -> bool:
    compacted = compact_text(value)
    lowered = compacted.lower()
    if not compacted:
        return True
    if len(compacted) < 8 or looks_like_slug_title(compacted):
        return True
    if compacted.endswith("..."):
        truncated_root = compacted[:-3].strip()
        if len(compacted.split()) <= 4 or TRAILING_CONNECTOR_RE.search(truncated_root):
            return True
    if TRAILING_CONNECTOR_RE.search(compacted):
        return True
    if re.search(r"['\"][A-Z]\.?$", compacted):
        return True
    if has_unbalanced_punctuation(compacted):
        return True
    if len(compacted.split()) == 1 and lowered in SINGLE_WORD_SECTION_TERMS:
        return True
    return False


def is_utility_title(value: str) -> bool:
    lowered = compact_text(value).lower()
    return any(term == lowered or term in lowered for term in UTILITY_TITLE_TERMS)


def extract_title_years(value: str) -> list[int]:
    return [int(match.group(0)) for match in YEAR_RE.finditer(compact_text(value))]


def has_stale_year_signal(title: str, timestamp: datetime) -> bool:
    years = extract_title_years(title)
    if not years:
        return False
    return any(year <= timestamp.year - 2 for year in years)


def path_segments(url: str) -> list[str]:
    path = urlparse(url).path.strip("/").lower()
    if not path:
        return []
    return [segment for segment in path.split("/") if segment]


def last_path_segment(url: str) -> str:
    segments = path_segments(url)
    return segments[-1] if segments else ""


def url_has_non_news_segment(url: str) -> bool:
    segments = path_segments(url)
    return any(
        segment in NON_NEWS_URL_SEGMENTS
        or any(re.search(rf"(?:^|[-_]){re.escape(hint)}(?:$|[-_])", segment) for hint in NON_NEWS_URL_HINTS)
        for segment in segments
    )


def looks_news_like_url(url: str) -> bool:
    compacted = compact_text(url)
    if not compacted or url_has_non_news_segment(compacted):
        return False
    if NEWSLIKE_URL_RE.search(compacted):
        return True
    last_segment = last_path_segment(compacted)
    if not last_segment:
        return False
    if "." in last_segment:
        last_segment = last_segment.rsplit(".", 1)[0]
    if len(last_segment) >= 8 and "-" in last_segment:
        return True
    return bool(re.search(r"[a-z]{4,}[-_][a-z0-9-]{4,}", last_segment))


def has_minimum_story_signal(title: str, summary: str) -> bool:
    clean_title = compact_text(title)
    clean_summary = compact_text(summary)
    combined_tokens = tokenize(f"{clean_title} {clean_summary}", max_tokens=80)
    return len(clean_title.split()) >= 3 and len(combined_tokens) >= 5 and len(clean_summary.split()) >= 6


def infer_story_subtype(
    *,
    category: str,
    headline: str,
    url: str = "",
    summary: str,
    key_points: list[str],
    comparison_story: bool,
    rules: SourceAnalysisRules | None = None,
) -> str:
    forced_subtype = forced_story_subtype(
        category=category,
        headline=headline,
        url=url,
        rules=rules,
    )
    if forced_subtype:
        return forced_subtype

    combined = compact_text(" ".join([headline, summary, *key_points]))
    if category == "sports":
        if SPORTS_ODDS_SIGNAL_RE.search(combined):
            return "odds"
        if SPORTS_SCHEDULE_SIGNAL_RE.search(combined):
            return "schedule"
        if SPORTS_ADMIN_SIGNAL_RE.search(combined):
            return "admin"
        if comparison_story:
            return "matchup"
        return "update"
    if category == "business":
        if MARKET_SIGNAL_RE.search(combined):
            return "market"
        return "general"
    return "general"


def editorial_type_rejection_reason(editorial_type: str) -> str | None:
    if editorial_type in INELIGIBLE_EDITORIAL_TYPES:
        return "utility_or_hub_page"
    return None


def article_eligibility_reason(
    article: Article,
    *,
    timestamp: datetime,
    detail_text: str,
    editorial_type: str,
    rules: SourceAnalysisRules | None = None,
) -> str | None:
    raw_title = article.title or ""
    raw_summary = detail_text
    clean_title = compact_text(raw_title)
    clean_summary = compact_text(raw_summary)
    source_rules = rules or SourceAnalysisRules()

    editorial_rejection = editorial_type_rejection_reason(editorial_type)
    if editorial_rejection:
        return editorial_rejection
    if url_has_non_news_segment(article.url):
        last_segment = last_path_segment(article.url)
        if last_segment in {"video", "videos", "watch"}:
            return "non_news_url"
        return "utility_or_hub_page"
    if match_rule_terms(article.url, source_rules.reject_url_substrings) or match_rule_patterns(article.url, source_rules.reject_url_patterns):
        return "utility_or_hub_page"
    if match_rule_terms(clean_title, source_rules.reject_title_terms) or match_rule_patterns(clean_title, source_rules.reject_title_patterns):
        return "utility_or_hub_page"
    if is_utility_title(clean_title):
        return "utility_or_hub_page"
    if looks_broken_title(clean_title):
        return "broken_title"
    if match_rule_terms(clean_title, source_rules.evergreen_title_terms):
        return "stale_or_evergreen"
    if has_stale_year_signal(clean_title, timestamp):
        return "stale_or_evergreen"
    if has_html_artifact(raw_title) and looks_broken_title(clean_title):
        return "html_artifact"
    if (
        not article.published_at
        and not source_rules.allow_unique_without_published_at
        and (not looks_news_like_url(article.url) or not has_minimum_story_signal(clean_title, clean_summary or clean_title))
    ):
        return "stale_or_evergreen"
    return None


def unique_candidate_rejection_reason(cluster: list[PreparedArticle]) -> str | None:
    if not cluster:
        return "low_signal_unique"

    representative = cluster[0].article
    titles = [compact_text(item.article.title) for item in cluster if compact_text(item.article.title)]
    summaries = [compact_text(item.detail_text) or compact_text(item.cluster_text) for item in cluster]
    headline = min(titles, key=len) if titles else compact_text(representative.title)
    summary = " ".join([value for value in summaries if value][:2]) or headline
    category = cluster[0].normalized_category
    source_rules = cluster_analysis_rules(cluster)

    if not looks_news_like_url(representative.url):
        return "non_news_url"
    if match_rule_terms(representative.url, source_rules.reject_url_substrings) or match_rule_patterns(representative.url, source_rules.reject_url_patterns):
        return "utility_or_hub_page"
    if match_rule_terms(headline, source_rules.reject_title_terms) or match_rule_patterns(headline, source_rules.reject_title_patterns):
        return "utility_or_hub_page"
    if is_utility_title(headline):
        return "utility_or_hub_page"
    if looks_broken_title(headline):
        return "broken_title"
    if match_rule_terms(headline, source_rules.evergreen_title_terms):
        return "stale_or_evergreen"
    if has_stale_year_signal(headline, cluster[0].timestamp):
        return "stale_or_evergreen"
    if not representative.published_at and not source_rules.allow_unique_without_published_at:
        return "stale_or_evergreen"
    if any(has_html_artifact(item.article.title) or has_html_artifact(item.article.summary) for item in cluster) and not has_minimum_story_signal(headline, summary):
        return "html_artifact"
    if not has_minimum_story_signal(headline, summary):
        return "low_signal_unique"

    subtype = infer_story_subtype(
        category=category,
        headline=headline,
        url=representative.url,
        summary=summary,
        key_points=titles[:2],
        comparison_story=is_comparison_story(
            category=category,
            headline=headline,
            summary=summary,
            key_points=titles[:2],
            score=extract_score([headline, summary, *titles[:2]]),
        ),
        rules=source_rules,
    )
    if category == "sports" and subtype == "matchup" and not extract_score([headline, summary, *titles[:2]]) and not COMPARISON_SIGNAL_RE.search(summary):
        return "template_mismatch"
    return None


def topic_render_rejection_reason(
    *,
    aggregation_type: str,
    headline: str,
    summary: str,
    key_points: list[str],
) -> str | None:
    clean_headline = compact_text(headline)
    clean_summary = compact_text(summary)
    if looks_broken_title(clean_headline):
        return "broken_title"
    if has_html_artifact(headline) or has_html_artifact(summary):
        return "html_artifact"
    if aggregation_type == "unique" and not has_minimum_story_signal(clean_headline, clean_summary or " ".join(key_points)):
        return "low_signal_unique"
    return None


def is_truncated_headline(value: str) -> bool:
    return compact_text(value).endswith("...")


def has_thin_summary(value: str) -> bool:
    cleaned = compact_text(value)
    summary_tokens = tokenize(cleaned, max_tokens=80)
    return len(cleaned) < 45 or len(summary_tokens) < 8


def evaluate_topic_quality(
    topic: TopicBrief,
    *,
    degraded_generation: bool = False,
) -> tuple[str, tuple[str, ...]]:
    review_reasons: list[str] = []
    representative = topic.representative_articles[0] if topic.representative_articles else None
    headline_truncated = is_truncated_headline(topic.headline_tr)
    missing_visual_asset = not topic.visual_assets
    thin_summary = has_thin_summary(topic.summary_tr)

    if topic.aggregation_type == "unique" and topic.source_count == 1:
        strong_unique_publishable = (
            representative is not None
            and representative.published_at is not None
            and not headline_truncated
            and not missing_visual_asset
            and not thin_summary
        )
        if not strong_unique_publishable:
            review_reasons.append("single_source_topic")

    if headline_truncated:
        review_reasons.append("truncated_headline")
    if missing_visual_asset:
        review_reasons.append("missing_visual_asset")
    if thin_summary:
        review_reasons.append("thin_summary")
    if degraded_generation:
        review_reasons.append("degraded_generation")

    deduped_reasons = tuple(
        reason
        for reason in dict.fromkeys(review_reasons)
        if reason in VALID_REVIEW_REASONS
    )
    return ("review", deduped_reasons) if deduped_reasons else ("publishable", ())


def round_quality_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def topic_score_features(
    topic: TopicBrief,
    *,
    quality_status: str,
    degraded_generation: bool = False,
) -> dict[str, bool]:
    representative = topic.representative_articles[0] if topic.representative_articles else None
    headline_truncated = is_truncated_headline(topic.headline_tr)
    missing_visual_asset = not topic.visual_assets
    thin_summary = has_thin_summary(topic.summary_tr)

    return {
        "shared_topic": topic.aggregation_type == "shared",
        "unique_topic": topic.aggregation_type == "unique",
        "source_count_ge_2": topic.source_count >= 2,
        "source_count_ge_3": topic.source_count >= 3,
        "has_visual_asset": not missing_visual_asset,
        "missing_visual_asset": missing_visual_asset,
        "non_thin_summary": not thin_summary,
        "thin_summary": thin_summary,
        "non_truncated_headline": not headline_truncated,
        "truncated_headline": headline_truncated,
        "has_published_at": representative is not None and representative.published_at is not None,
        "missing_published_at": representative is None or representative.published_at is None,
        "article_count_ge_2": topic.article_count >= 2,
        "degraded_generation": degraded_generation,
        "review_status": quality_status == "review",
    }


def calculate_topic_quality_score(
    score_features: dict[str, bool],
) -> float:
    score = QUALITY_SCORE_WEIGHTS["base"]
    for feature in QUALITY_SCORE_FEATURES:
        if score_features.get(feature):
            score += QUALITY_SCORE_WEIGHTS[feature]
    return round_quality_score(score)


def average_quality_score(values: list[float]) -> float:
    if not values:
        return 0.0
    return round_quality_score(sum(values) / len(values))


def build_score_distribution(values: list[float]) -> list[TopicQualityScoreBand]:
    return [
        TopicQualityScoreBand(
            label=label,
            count=sum(1 for value in values if lower_bound <= value < upper_bound),
        )
        for label, lower_bound, upper_bound in QUALITY_SCORE_BANDS
    ]


def normalize_score_features(raw_features: dict[str, Any] | None) -> dict[str, bool]:
    raw_features = raw_features or {}
    return {
        feature: bool(raw_features.get(feature, False))
        for feature in QUALITY_SCORE_FEATURES
    }


def topic_feedback_score_features(snapshot: TopicFeedbackSnapshotInput) -> dict[str, bool]:
    headline_truncated = is_truncated_headline(snapshot.headline_tr)
    thin_summary = has_thin_summary(snapshot.summary_tr)
    degraded_generation = "degraded_generation" in snapshot.review_reasons

    return normalize_score_features(
        {
            "shared_topic": snapshot.aggregation_type == "shared",
            "unique_topic": snapshot.aggregation_type == "unique",
            "source_count_ge_2": snapshot.source_count >= 2,
            "source_count_ge_3": snapshot.source_count >= 3,
            "has_visual_asset": snapshot.has_visual_asset,
            "missing_visual_asset": not snapshot.has_visual_asset,
            "non_thin_summary": not thin_summary,
            "thin_summary": thin_summary,
            "non_truncated_headline": not headline_truncated,
            "truncated_headline": headline_truncated,
            "has_published_at": snapshot.has_published_at,
            "missing_published_at": not snapshot.has_published_at,
            "article_count_ge_2": snapshot.article_count >= 2,
            "degraded_generation": degraded_generation,
            "review_status": snapshot.quality_status == "review",
        }
    )


def topic_video_output_texts(topic: TopicBrief) -> list[str]:
    scene_texts = [
        value
        for scene in topic.video_plan.scenes
        for value in [scene.headline, scene.body, *scene.supporting_points]
        if compact_text(value)
    ]
    narrative = topic.video_content.narrative if topic.video_content else []
    return [
        topic.headline_tr,
        topic.summary_tr,
        topic.why_it_matters_tr,
        *topic.key_points_tr,
        *scene_texts,
        *narrative,
    ]


def topic_video_english_texts(topic: TopicBrief) -> list[str]:
    scene_texts = [
        value
        for scene in topic.video_plan.scenes
        for value in [scene.headline, scene.body, *scene.supporting_points]
        if compact_text(value)
    ]
    narrative = topic.video_content.narrative if topic.video_content else []
    return scene_texts + narrative + [topic.video_plan.title]


def has_broken_copy(topic: TopicBrief) -> bool:
    values = topic_video_output_texts(topic)
    for value in values:
        normalized = compact_text(value)
        if not normalized:
            continue
        if has_html_artifact(normalized):
            return True
        for pattern in BROKEN_COPY_PATTERNS:
            if pattern.search(normalized):
                return True
        if "..." in normalized:
            return True
    return False


def has_mixed_language_copy(topic: TopicBrief) -> bool:
    visible_values = [
        topic.headline_tr,
        topic.summary_tr,
        topic.why_it_matters_tr,
        *topic.key_points_tr,
        *[
            value
            for scene in topic.video_plan.scenes
            for value in [scene.headline, scene.body, *scene.supporting_points]
        ],
    ]
    detected_languages: list[str] = []
    for value in visible_values:
        compacted = compact_text(value)
        if not compacted:
            continue
        detected = detect_text_language(compacted, fallback=topic.story_language)
        if detected:
            detected_languages.append(detected)
    distinct_languages = {language for language in detected_languages if language}
    if not distinct_languages:
        return False
    dominant = max(
        ((language, detected_languages.count(language)) for language in distinct_languages),
        key=lambda item: item[1],
    )[0]
    return dominant != topic.story_language or len(distinct_languages) > 1


def has_generic_asset_only(topic: TopicBrief) -> bool:
    if not topic.visual_assets:
        return False
    if any(asset.kind == "article_image" for asset in topic.visual_assets):
        return False
    return any(any(marker in asset.url.lower() for marker in GENERIC_ASSET_MARKERS) for asset in topic.visual_assets)


def topic_output_corpus(topic: TopicBrief) -> str:
    return compact_text(" ".join(topic_video_output_texts(topic))).lower()


def resolve_story_fact_pack(
    topic: TopicBrief,
    cluster: list[PreparedArticle],
    fact_pack: StoryFactPack | None = None,
) -> StoryFactPack:
    if fact_pack is not None:
        return fact_pack
    return build_story_fact_pack(
        cluster,
        category=topic.category,
        headline=topic.headline_tr,
        summary=topic.summary_tr,
        key_points=topic.key_points_tr,
    )


def contains_legal_attribution(
    topic: TopicBrief,
    cluster: list[PreparedArticle],
    fact_pack: StoryFactPack | None = None,
) -> bool:
    resolved_fact_pack = resolve_story_fact_pack(topic, cluster, fact_pack)
    if resolved_fact_pack.story_domain != "crime_justice":
        return True
    detail_corpus = compact_text(" ".join(item.detail_text for item in cluster)).lower()
    if not resolved_fact_pack.allegation_frame and not text_contains_any_hint(detail_corpus, CRIME_JUSTICE_HINTS):
        return True
    output_corpus = topic_output_corpus(topic)
    expected_markers = (
        ("savcilara gore", "federal sikayete gore", "doj'ye gore", "yetkililere gore")
        if resolved_fact_pack.story_language == "tr"
        else ("according to prosecutors", "according to the federal complaint", "doj says", "authorities say")
    )
    if resolved_fact_pack.allegation_frame and compact_text(resolved_fact_pack.allegation_frame).lower() in output_corpus:
        return True
    return text_contains_any_hint(output_corpus, expected_markers)


def has_crime_support(topic: TopicBrief, fact_pack: StoryFactPack) -> bool:
    output_corpus = topic_output_corpus(topic)
    has_actor = any(output_mentions_fact(output_corpus, actor) for actor in fact_pack.actors[:3]) or text_contains_any_hint(
        output_corpus,
        ("charged", "charges", "sanik", "saniklar", "accused"),
    )
    has_setup = output_mentions_fact(output_corpus, fact_pack.trigger_or_setup or fact_pack.supporting_fact)
    has_legal = output_mentions_fact(output_corpus, fact_pack.legal_consequence) or text_contains_any_hint(
        output_corpus,
        LEGAL_CONSEQUENCE_HINTS,
    )
    return has_actor and has_setup and has_legal


def has_sports_support(topic: TopicBrief, fact_pack: StoryFactPack) -> bool:
    output_corpus = topic_output_corpus(topic)
    has_actor = any(output_mentions_fact(output_corpus, actor) for actor in fact_pack.actors[:2])
    has_status = any(
        output_mentions_fact(output_corpus, value)
        for value in (fact_pack.core_event, fact_pack.supporting_fact, fact_pack.trigger_or_setup)
        if compact_text(value)
    ) or text_contains_any_hint(output_corpus, SPORTS_AVAILABILITY_HINTS)
    has_context = any(
        output_mentions_fact(output_corpus, value)
        for value in (fact_pack.impact_or_next, fact_pack.result_context)
        if compact_text(value)
    ) or text_contains_any_hint(output_corpus, SPORTS_FIXTURE_HINTS + SPORTS_RESULT_HINTS)
    return has_actor and has_status and has_context


def has_business_support(topic: TopicBrief, fact_pack: StoryFactPack) -> bool:
    output_corpus = topic_output_corpus(topic)
    has_metric = bool(fact_pack.numeric_facts) and any(output_mentions_fact(output_corpus, value) for value in fact_pack.numeric_facts[:2])
    has_impact = output_mentions_fact(output_corpus, fact_pack.impact_or_next or fact_pack.impact_fact)
    return has_metric or has_impact


def has_diplomacy_support(topic: TopicBrief, fact_pack: StoryFactPack) -> bool:
    output_corpus = topic_output_corpus(topic)
    has_institution = output_mentions_fact(output_corpus, fact_pack.institution) or text_contains_any_hint(output_corpus, DIPLOMACY_HINTS)
    has_development = any(
        output_mentions_fact(output_corpus, value)
        for value in (fact_pack.core_event, fact_pack.supporting_fact)
        if compact_text(value)
    )
    has_trigger = any(
        output_mentions_fact(output_corpus, value)
        for value in (fact_pack.trigger_or_setup, fact_pack.impact_or_next)
        if compact_text(value)
    ) or text_contains_any_hint(output_corpus, DIPLOMACY_TRIGGER_HINTS)
    return has_institution and has_development and has_trigger


def has_general_support(topic: TopicBrief, fact_pack: StoryFactPack) -> bool:
    output_corpus = topic_output_corpus(topic)
    has_core = output_mentions_fact(output_corpus, fact_pack.core_event or fact_pack.primary_event)
    has_support = any(
        output_mentions_fact(output_corpus, value)
        for value in (fact_pack.supporting_fact, fact_pack.impact_or_next, fact_pack.result_context)
        if compact_text(value)
    )
    return has_core and has_support


def has_missing_domain_fact_pack(
    topic: TopicBrief,
    cluster: list[PreparedArticle],
    fact_pack: StoryFactPack | None = None,
) -> bool:
    fact_pack = resolve_story_fact_pack(topic, cluster, fact_pack)
    detail_corpus = compact_text(" ".join(item.detail_text for item in cluster)).lower()
    if not fact_pack.primary_event:
        return True
    if fact_pack.story_domain == "crime_justice":
        return not has_crime_support(topic, fact_pack)
    if fact_pack.story_domain == "diplomacy":
        return not has_diplomacy_support(topic, fact_pack)
    if fact_pack.supporting_fact and text_similarity(fact_pack.supporting_fact, topic.headline_tr) < 0.72:
        return False
    if topic.category == "business":
        metric_heavy_business = bool(extract_score([detail_corpus]) or extract_numeric_phrase([detail_corpus])) or text_contains_any_hint(
            detail_corpus,
            BUSINESS_NUMERIC_HINTS,
        )
        if metric_heavy_business:
            return not fact_pack.numeric_facts and not fact_pack.impact_fact
        return not (fact_pack.supporting_fact or fact_pack.impact_fact or fact_pack.actors or fact_pack.institution)
    if topic.category == "sports":
        sports_status_story = text_contains_any_hint(detail_corpus, SPORTS_AVAILABILITY_HINTS) or bool(fact_pack.trigger_or_setup)
        if sports_status_story:
            return not has_sports_support(topic, fact_pack)
        result_driven_sports = bool(extract_score([detail_corpus])) or text_contains_any_hint(
            detail_corpus,
            SPORTS_RESULT_HINTS,
        )
        if fact_pack.editorial_type in SPECULATIVE_EDITORIAL_TYPES:
            return not (fact_pack.supporting_fact and fact_pack.actors)
        if result_driven_sports:
            supporting_fact = compact_text(fact_pack.supporting_fact).lower()
            return not (
                fact_pack.result_context
                or (
                    supporting_fact
                    and (
                        bool(extract_score([supporting_fact]))
                        or text_contains_any_hint(supporting_fact, SPORTS_RESULT_HINTS)
                    )
                )
            )
        return not (fact_pack.supporting_fact or fact_pack.actors or fact_pack.impact_fact)
    if topic.category in {"world", "politics", "general"}:
        institutional_story = text_contains_any_hint(detail_corpus, INSTITUTIONAL_CONTEXT_HINTS)
        if institutional_story:
            return not fact_pack.institution and not fact_pack.impact_fact
        return not (fact_pack.supporting_fact or fact_pack.impact_fact or fact_pack.actors)
    return not fact_pack.supporting_fact


def has_speculative_story(topic: TopicBrief, cluster: list[PreparedArticle]) -> bool:
    fact_pack = build_story_fact_pack(
        cluster,
        category=topic.category,
        headline=topic.headline_tr,
        summary=topic.summary_tr,
        key_points=topic.key_points_tr,
    )
    return fact_pack.editorial_type in SPECULATIVE_EDITORIAL_TYPES


def has_cross_story_contamination(topic: TopicBrief, cluster: list[PreparedArticle]) -> bool:
    values = topic_video_output_texts(topic)
    detail_corpus = compact_text(
        " ".join(
            compact_text(value)
            for item in cluster
            for value in (item.detail_text, item.cluster_text, item.article.title, item.article.summary)
            if compact_text(value)
        )
    )
    detail_names = {
        normalize_prompt_entity(name).lower()
        for name in extract_named_phrases([detail_corpus], ignore=set(unique_source_names(cluster)), max_items=20)
        if normalize_prompt_entity(name).lower() not in GENERIC_ENTITY_TOKENS
        and normalize_prompt_entity(name).lower() not in LOW_INFORMATION_ANCHOR_TOKENS
    }
    headline_names = {
        normalize_prompt_entity(name).lower()
        for name in extract_named_phrases([topic.headline_tr], ignore=set(unique_source_names(cluster)), max_items=6)
        if normalize_prompt_entity(name).lower() not in GENERIC_ENTITY_TOKENS
        and normalize_prompt_entity(name).lower() not in LOW_INFORMATION_ANCHOR_TOKENS
    }
    for value in values:
        normalized = compact_text(value)
        lowered = normalized.lower()
        if not normalized:
            continue
        if any(marker in lowered for marker in DETAIL_TEXT_STOP_MARKERS):
            return True
        if re.search(r"list of \d+ items|list \d+ of \d+", lowered):
            return True

    if len(topic.key_points_tr) >= 2:
        for point in topic.key_points_tr[1:]:
            point_names = {
                normalize_prompt_entity(name).lower()
                for name in extract_named_phrases([point], ignore=set(unique_source_names(cluster)), max_items=4)
                if normalize_prompt_entity(name).lower() not in GENERIC_ENTITY_TOKENS
                and normalize_prompt_entity(name).lower() not in LOW_INFORMATION_ANCHOR_TOKENS
            }
            unknown_point_names = [name for name in point_names if name and name not in detail_names]
            if (
                unknown_point_names
                and text_similarity(point, topic.headline_tr) < 0.55
                and text_similarity(point, detail_corpus) < 0.25
            ):
                return True
            if point_names and headline_names and point_names.isdisjoint(headline_names) and text_similarity(point, topic.headline_tr) < 0.12:
                return True

    for scene in topic.video_plan.scenes[1:]:
        scene_text = compact_text(" ".join([scene.headline, scene.body, *scene.supporting_points]))
        if not scene_text:
            continue
        scene_names = {
            normalize_prompt_entity(name).lower()
            for name in extract_named_phrases([scene_text], ignore=set(unique_source_names(cluster)), max_items=6)
            if normalize_prompt_entity(name).lower() not in GENERIC_ENTITY_TOKENS
            and normalize_prompt_entity(name).lower() not in LOW_INFORMATION_ANCHOR_TOKENS
        }
        unknown_scene_names = [name for name in scene_names if name and name not in detail_names]
        if (
            unknown_scene_names
            and text_similarity(scene_text, topic.headline_tr) < 0.55
            and text_similarity(scene_text, detail_corpus) < 0.25
        ):
            return True
    return False


def has_unsupported_claim(topic: TopicBrief, cluster: list[PreparedArticle]) -> bool:
    detail_corpus = compact_text(
        " ".join(
            compact_text(value)
            for item in cluster
            for value in (
                item.detail_text,
                item.cluster_text,
                item.article.title,
                item.article.summary,
            )
            if compact_text(value)
        )
    )
    output_values = topic_video_english_texts(topic)

    detail_numeric = {
        compact_text(match.group(0)).lower()
        for match in NUMERIC_PHRASE_RE.finditer(detail_corpus)
    }
    output_numeric = {
        compact_text(match.group(0)).lower()
        for value in output_values
        for match in NUMERIC_PHRASE_RE.finditer(value)
    }
    unknown_numeric = [
        value
        for value in output_numeric
        if not value.startswith("point ")
        and not any(value == detail or value in detail or detail in value for detail in detail_numeric)
    ]
    return bool(unknown_numeric)


def has_headline_only_support(topic: TopicBrief) -> bool:
    if len(topic.video_plan.scenes) < 2:
        return False
    second_scene = topic.video_plan.scenes[1]
    candidate_text = compact_text(" ".join([second_scene.headline, second_scene.body, *second_scene.supporting_points]))
    if not candidate_text:
        return True
    return text_similarity(candidate_text, topic.headline_tr) >= 0.72


def has_low_information_anchors(topic: TopicBrief) -> bool:
    raw_anchors = dedupe_preserve_order(
        [figure for scene in topic.video_plan.scenes for figure in scene.key_figures]
        + (topic.video_content.key_figures if topic.video_content else [])
        + topic.video_prompt_parts.must_include
    )
    if len(raw_anchors) < 2:
        return False
    informative = filter_informative_anchors(raw_anchors, headline=topic.headline_tr, max_items=len(raw_anchors))
    return len(informative) <= max(1, len(raw_anchors) // 2)


def has_missing_numeric_impact(topic: TopicBrief, cluster: list[PreparedArticle]) -> bool:
    detail_corpus = compact_text(" ".join(item.detail_text for item in cluster))
    output_corpus = compact_text(" ".join(topic_video_english_texts(topic) + [topic.why_it_matters_tr]))
    story_is_numeric = topic.category == "business" or text_contains_any_hint(detail_corpus, BUSINESS_NUMERIC_HINTS)
    if not story_is_numeric:
        return False
    has_detail_numeric = bool(extract_score([detail_corpus]) or extract_numeric_phrase([detail_corpus]))
    has_output_numeric = bool(extract_score([output_corpus]) or extract_numeric_phrase([output_corpus]))
    return has_detail_numeric and not has_output_numeric


def has_missing_institutional_context(topic: TopicBrief, cluster: list[PreparedArticle]) -> bool:
    detail_corpus = compact_text(" ".join(item.detail_text for item in cluster)).lower()
    output_corpus = compact_text(" ".join(topic_video_english_texts(topic) + [topic.why_it_matters_tr])).lower()
    story_is_institutional = topic.category in {"world", "politics", "general"} and text_contains_any_hint(
        detail_corpus,
        INSTITUTIONAL_CONTEXT_HINTS,
    )
    if not story_is_institutional:
        return False
    institution_markers = ("department", "office", "archives", "agency", "government")
    consequence_markers = ("comply", "president", "court", "executive", "binds")
    has_detail_context = text_contains_any_hint(detail_corpus, institution_markers) and text_contains_any_hint(
        detail_corpus,
        consequence_markers,
    )
    has_output_context = text_contains_any_hint(output_corpus, institution_markers) and text_contains_any_hint(
        output_corpus,
        consequence_markers,
    )
    return has_detail_context and not has_output_context


def has_missing_sports_result_context(topic: TopicBrief, cluster: list[PreparedArticle]) -> bool:
    if topic.category != "sports":
        return False
    detail_corpus = compact_text(" ".join(item.detail_text for item in cluster)).lower()
    output_corpus = compact_text(" ".join(topic_video_english_texts(topic) + [topic.why_it_matters_tr])).lower()
    has_detail_result = bool(extract_score([detail_corpus])) or text_contains_any_hint(detail_corpus, SPORTS_RESULT_HINTS)
    has_output_result = bool(extract_score([output_corpus])) or text_contains_any_hint(output_corpus, SPORTS_RESULT_HINTS)
    return has_detail_result and not has_output_result


def evaluate_video_quality(
    topic: TopicBrief,
    *,
    cluster: list[PreparedArticle],
    fact_pack: StoryFactPack | None = None,
) -> tuple[str, int, tuple[str, ...]]:
    reasons: list[str] = []
    why_line = compact_text(topic.why_it_matters_tr)
    resolved_fact_pack = resolve_story_fact_pack(topic, cluster, fact_pack)

    if has_cross_story_contamination(topic, cluster):
        reasons.append("cross_story_contamination")
    if has_broken_copy(topic):
        reasons.append("broken_copy")
    if has_unsupported_claim(topic, cluster):
        reasons.append("unsupported_claim")
    if is_generic_why_line(why_line):
        reasons.append("generic_why_it_matters")
    if has_headline_only_support(topic):
        reasons.append("headline_only_support")
    if len(topic.video_plan.scenes) >= 2 and scene_progression_score(topic.video_plan.scenes) < 0.42:
        reasons.append("weak_scene_progression")
    if has_low_information_anchors(topic):
        reasons.append("low_information_anchors")
    if has_speculative_story(topic, cluster):
        reasons.append("speculative_story")
    if has_mixed_language_copy(topic):
        reasons.append("mixed_language_copy")
    if has_generic_asset_only(topic):
        reasons.append("generic_asset_only")
    if has_missing_domain_fact_pack(topic, cluster, resolved_fact_pack):
        reasons.append("missing_domain_fact_pack")
    if has_missing_numeric_impact(topic, cluster):
        reasons.append("missing_numeric_impact")
    if has_missing_institutional_context(topic, cluster):
        reasons.append("missing_institutional_context")
    if has_missing_sports_result_context(topic, cluster):
        reasons.append("missing_sports_result_context")
    if resolved_fact_pack.story_domain == "crime_justice":
        output_corpus = topic_output_corpus(topic)
        if not contains_legal_attribution(topic, cluster, resolved_fact_pack):
            reasons.append("missing_allegation_framing")
        if resolved_fact_pack.trigger_or_setup and not output_mentions_fact(output_corpus, resolved_fact_pack.trigger_or_setup):
            reasons.append("missing_crime_setup")
        if resolved_fact_pack.legal_consequence and not (
            output_mentions_fact(output_corpus, resolved_fact_pack.legal_consequence)
            or text_contains_any_hint(output_corpus, LEGAL_CONSEQUENCE_HINTS)
        ):
            reasons.append("missing_legal_consequence")

    deduped_reasons = tuple(
        reason
        for reason in dict.fromkeys(reasons)
        if reason in VALID_VIDEO_REVIEW_REASONS
    )
    score = max(
        0,
        min(
            100,
            100 - sum(VIDEO_QUALITY_DEDUCTIONS.get(reason, 0) for reason in deduped_reasons),
        ),
    )
    if any(reason in HARD_VIDEO_REJECT_REASONS for reason in deduped_reasons):
        return "reject", score, deduped_reasons
    review_floor_reasons = {
        "generic_why_it_matters",
        "headline_only_support",
        "weak_scene_progression",
        "speculative_story",
        "mixed_language_copy",
        "generic_asset_only",
        "missing_domain_fact_pack",
        "missing_numeric_impact",
        "missing_institutional_context",
        "missing_sports_result_context",
        "missing_allegation_framing",
        "missing_legal_consequence",
        "missing_crime_setup",
    }
    if any(reason in review_floor_reasons for reason in deduped_reasons) and score >= 85:
        score = 84
    if score >= 85:
        return "publishable", score, deduped_reasons
    if score >= 55:
        return "review", score, deduped_reasons
    return "reject", score, deduped_reasons


def effective_prompt_visibility_status(entry: TopicAnalysisEntry) -> str:
    if entry.video_quality_status == "reject":
        return "reject"
    if entry.quality_status == "review" or entry.video_quality_status == "review":
        return "review"
    return "publishable"


def build_latest_feedback(record: TopicFeedback) -> TopicLatestFeedback:
    return TopicLatestFeedback(
        label=record.feedback_label,
        note=record.note,
        updated_at=record.updated_at,
    )


def feedback_breakdown(records: list[TopicFeedback]) -> list[AnalysisFeedbackDebug]:
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        counts[record.feedback_label] += 1
    return [
        AnalysisFeedbackDebug(label=label, count=count)
        for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if label in VALID_FEEDBACK_LABELS
    ]


def feedback_coverage_percent(*, feedback_count: int, topic_count: int) -> float:
    if topic_count <= 0:
        return 0.0
    return round(min(100.0, max(0.0, (feedback_count / topic_count) * 100.0)), 2)


async def get_topic_feedback_records(
    db: AsyncSession,
    topic_ids: list[str],
) -> dict[str, TopicFeedback]:
    unique_ids = [topic_id for topic_id in dict.fromkeys(topic_ids) if compact_text(topic_id)]
    if not unique_ids:
        return {}
    rows = await db.execute(
        select(TopicFeedback).where(TopicFeedback.topic_id.in_(unique_ids))
    )
    return {record.topic_id: record for record in rows.scalars().all()}


async def hydrate_topics_with_feedback(
    db: AsyncSession,
    topics: list[TopicBrief],
) -> tuple[list[TopicBrief], dict[str, TopicFeedback]]:
    feedback_map = await get_topic_feedback_records(db, [topic.topic_id for topic in topics])
    hydrated_topics = [
        topic.model_copy(
            update={
                "latest_feedback": build_latest_feedback(feedback_map[topic.topic_id])
                if topic.topic_id in feedback_map
                else None
            }
        )
        for topic in topics
    ]
    return hydrated_topics, feedback_map


def approved_feedback(record: TopicFeedback) -> bool:
    return record.feedback_label == "approved"


def negative_feedback(record: TopicFeedback) -> bool:
    return record.feedback_label in {"wrong", "boring", "malformed"}


def tuning_weight_delta(lift: float) -> float:
    if lift >= 0.20:
        return 0.03
    if lift >= 0.10:
        return 0.02
    if lift <= -0.20:
        return -0.03
    if lift <= -0.10:
        return -0.02
    return 0.0


def classify_story_complexity(summary: str, key_points: list[str]) -> str:
    summary_len = len(compact_text(summary))
    point_count = len([point for point in key_points if compact_text(point)])
    if point_count <= 1 and summary_len <= 120:
        return "short"
    if point_count <= 3 and summary_len <= 220:
        return "medium"
    return "complex"


def suggest_scene_count(
    summary: str,
    key_points: list[str],
    *,
    category: str = "general",
    comparison_story: bool = False,
    duration_seconds: int = 0,
) -> int:
    complexity = classify_story_complexity(summary, key_points)
    if category == "sports" and not comparison_story:
        if complexity == "short":
            return 1
        if complexity == "medium" and len(dedupe_preserve_order(key_points)) <= 2:
            return 1
    if complexity == "short":
        base = 1
    elif complexity == "medium":
        base = 2
    else:
        base = 3

    # Clamp scene count by duration so short videos don't get too many scenes
    if duration_seconds > 0:
        if duration_seconds <= 12:
            return min(base, 2)
        if duration_seconds <= 20:
            return min(base, 3)
        return min(base, 4)

    return base


def tokenize(value: str, *, max_tokens: int = 40) -> set[str]:
    tokens = [
        token
        for token in WORD_RE.findall(value.lower())
        if len(token) > 2 and token not in STOPWORDS
    ]
    return set(tokens[:max_tokens])


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def clamp_confidence(value: Any, default: float = 0.65) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    return max(0.0, min(1.0, numeric))


def truncate_text(value: str, limit: int = 160) -> str:
    compacted = compact_text(value)
    if len(compacted) <= limit:
        return compacted
    return f"{compacted[: max(0, limit - 3)].rstrip()}..."


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = compact_text(value)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def extract_lead_sentences(
    value: str | None,
    *,
    title: str = "",
    max_sentences: int = 3,
    max_chars: int = CLUSTER_TEXT_CHAR_LIMIT,
) -> str:
    cleaned = compact_text(value)
    if not cleaned:
        return ""

    normalized_title = normalize_title(title)
    selected: list[str] = []
    for sentence in split_sentences(cleaned):
        normalized_sentence = compact_text(sentence)
        if not normalized_sentence:
            continue
        if normalized_title and SequenceMatcher(
            None,
            normalize_title(normalized_sentence),
            normalized_title,
        ).ratio() >= 0.94:
            continue
        if selected and SequenceMatcher(None, selected[-1].lower(), normalized_sentence.lower()).ratio() >= 0.92:
            continue

        candidate = " ".join([*selected, normalized_sentence]).strip()
        if len(candidate) > max_chars and selected:
            break
        if len(candidate) > max_chars:
            selected.append(truncate_text(normalized_sentence, max_chars))
            break

        selected.append(normalized_sentence)
        if len(selected) >= max_sentences:
            break

    if not selected:
        return truncate_text(cleaned, max_chars)
    return truncate_text(" ".join(selected), max_chars)


def build_detail_text(article: Article) -> str:
    content_text = strip_detail_boilerplate(article.content_text)
    if content_text:
        detail = extract_lead_sentences(
            content_text,
            title=article.title,
            max_sentences=5,
            max_chars=settings.ANALYSIS_TEXT_CHAR_LIMIT,
        )
        return detail or truncate_text(content_text, settings.ANALYSIS_TEXT_CHAR_LIMIT)

    content_snippet = strip_detail_boilerplate(article.content_snippet)
    if content_snippet:
        return truncate_text(content_snippet, settings.ANALYSIS_TEXT_CHAR_LIMIT)

    summary = strip_detail_boilerplate(article.summary)
    if summary:
        return truncate_text(summary, settings.ANALYSIS_TEXT_CHAR_LIMIT)

    return compact_text(article.title)


def build_cluster_text(article: Article) -> str:
    content_snippet = strip_detail_boilerplate(article.content_snippet)
    if content_snippet:
        return truncate_text(content_snippet, CLUSTER_TEXT_CHAR_LIMIT)

    content_text = strip_detail_boilerplate(article.content_text)
    if content_text:
        lead = extract_lead_sentences(
            content_text,
            title=article.title,
            max_sentences=3,
            max_chars=CLUSTER_TEXT_CHAR_LIMIT,
        )
        if lead:
            return lead

    summary = strip_detail_boilerplate(article.summary)
    if summary:
        return truncate_text(summary, CLUSTER_TEXT_CHAR_LIMIT)

    return truncate_text(compact_text(article.title), CLUSTER_TEXT_CHAR_LIMIT)


def extract_score(values: list[str]) -> str:
    for value in values:
        match = SCORE_RE.search(value)
        if match:
            return match.group(0).replace(" ", "")
    return ""


def extract_numeric_phrase(values: list[str], *, exclude: set[str] | None = None) -> str:
    excluded = {item.lower() for item in (exclude or set())}
    for value in values:
        for match in NUMERIC_PHRASE_RE.finditer(value):
            candidate = compact_text(match.group(0))
            if not candidate or candidate.lower() in excluded:
                continue
            if re.fullmatch(r"\d{3,5}", candidate):
                continue
            return candidate
    return ""


def extract_named_phrases(values: list[str], *, ignore: set[str] | None = None, max_items: int = 6) -> list[str]:
    ignored = {compact_text(item).lower() for item in (ignore or set())}
    ignored.update(
        {
            "ap news",
            "bbc news",
            "cbs news",
            "yahoo sports",
            "reuters",
            "bloomberg",
            "the guardian",
            "news",
            "breaking news",
            "english",
            "turkish",
        }
    )
    phrases: list[str] = []
    seen: set[str] = set()
    for value in values:
        compacted_value = compact_text(value)
        for match in PROPER_NOUN_RE.finditer(value):
            candidate = compact_text(match.group(0))
            if not candidate:
                continue
            lowered = candidate.lower()
            if lowered in ignored or lowered in STOPWORDS or lowered in seen:
                continue
            if len(candidate) < 3:
                continue
            if " " not in candidate and not candidate.isupper():
                if lowered in GENERIC_ENTITY_TOKENS:
                    continue
                if compacted_value.startswith(f"{candidate} ") and sum(
                    1 for text in values if re.search(rf"\b{re.escape(candidate)}\b", compact_text(text))
                ) < 2:
                    continue
            seen.add(lowered)
            phrases.append(candidate)
            if len(phrases) >= max_items:
                return phrases
    return phrases


def looks_generic_prompt_component(value: str) -> bool:
    normalized = compact_text(value).lower()
    if not normalized:
        return True
    return any(marker in normalized for marker in GENERIC_PROMPT_MARKERS)


def looks_underspecified_human_prompt(value: str) -> bool:
    normalized = compact_text(value).lower()
    if not normalized:
        return True
    if len(normalized) < 180:
        return True
    if any(marker in normalized for marker in GENERIC_PROMPT_MARKERS):
        return True
    structure_markers = ("visual style:", "motion language:", "transitions:", "scene beats:")
    return sum(marker in normalized for marker in structure_markers) < 2


def truncate_for_prompt(value: str, limit: int = 1000) -> str:
    compacted = compact_text(value)
    if len(compacted) <= limit:
        return compacted
    return f"{compacted[: max(0, limit - 3)].rstrip()}..."


def build_prompt_entities(
    cluster: list[PreparedArticle],
    *,
    headline: str,
    summary: str,
    key_points: list[str],
) -> dict[str, Any]:
    values = [headline, summary, *key_points]
    sources = unique_source_names(cluster)
    score = extract_score(values)
    names = extract_named_phrases(values, ignore=set(sources), max_items=5)
    numeric_phrase = extract_numeric_phrase(values, exclude={score} if score else set())
    matchup = " vs ".join(names[:2]) if len(names) >= 2 else ""
    focus_entity = names[2] if len(names) >= 3 else (names[0] if names else "")

    return {
        "sources": sources,
        "score": score,
        "names": names,
        "numeric_phrase": numeric_phrase,
        "matchup": matchup,
        "focus_entity": focus_entity,
        "top_key_point": truncate_for_prompt(key_points[0]) if key_points else "",
        "supporting_key_points": [truncate_for_prompt(point) for point in key_points[1:3]],
    }


def extract_numeric_phrases(values: list[str], *, max_items: int = 4) -> list[str]:
    phrases: list[str] = []
    seen: set[str] = set()
    for value in values:
        compacted_value = compact_text(value)
        if not compacted_value:
            continue
        score = extract_score([compacted_value])
        if score:
            normalized_score = score.replace(" ", "")
            if normalized_score.lower() not in seen:
                seen.add(normalized_score.lower())
                phrases.append(normalized_score)
        for match in re.finditer(
            r"(\$\d[\d,]*(?:\.\d+)?(?:\s*(?:per month|monthly|lifetime))?|\d+(?:\.\d+)?%|\+\$\d[\d,]*(?:\.\d+)?|\d+(?:\.\d+)?\s*(?:points|rebounds|assists|seed|sales|days?|weeks?|months?|years?|hours?|minutes?|million|billion|sterling|pounds?))",
            compacted_value,
            flags=re.IGNORECASE,
        ):
            candidate = compact_text(match.group(0))
            lowered = candidate.lower()
            if not candidate or lowered in seen:
                continue
            seen.add(lowered)
            phrases.append(candidate)
            if len(phrases) >= max_items:
                return phrases
    return phrases


def choose_supporting_fact(
    sentences: list[str],
    *,
    headline: str,
    category: str,
) -> str:
    best_candidate = ""
    best_score = float("-inf")
    for sentence in sentences:
        candidate = clean_viewer_text(sentence, max_sentences=2, max_chars=2000)
        if not candidate or is_generic_why_line(candidate):
            continue
        if text_similarity(candidate, headline) >= 0.84:
            continue
        score = len(tokenize(candidate, max_tokens=30)) / 12.0
        lowered = candidate.lower()
        if category == "business" and text_contains_any_hint(lowered, BUSINESS_NUMERIC_HINTS):
            score += 0.5
        if category in {"world", "politics", "general", "business"} and text_contains_any_hint(lowered, INSTITUTIONAL_CONTEXT_HINTS):
            score += 0.25
        if category == "sports" and (extract_score([candidate]) or text_contains_any_hint(lowered, SPORTS_RESULT_HINTS)):
            score += 0.45
        if extract_numeric_phrases([candidate]):
            score += 0.35
        if text_contains_any_hint(lowered, ("because", "after", "means", "would", "could", "will")):
            score += 0.12
        if score > best_score:
            best_candidate = candidate
            best_score = score
    return best_candidate


def choose_impact_fact(
    sentences: list[str],
    *,
    headline: str,
    summary: str,
    key_points: list[str],
    category: str,
    cluster: list[PreparedArticle],
) -> str:
    candidate = build_why_it_matters_line(
        category,
        headline=headline,
        summary=summary,
        key_points=key_points,
        cluster=cluster,
    )
    if candidate and text_similarity(candidate, headline) < 0.9:
        return candidate
    return choose_supporting_fact(sentences, headline=headline, category=category)


def select_institution_from_values(values: list[str]) -> str:
    for value in values:
        compacted_value = compact_text(value)
        if not compacted_value:
            continue
        named_phrases = extract_named_phrases([compacted_value], max_items=4)
        for phrase in named_phrases:
            lowered = phrase.lower()
            if text_contains_any_hint(lowered, INSTITUTIONAL_CONTEXT_HINTS):
                return phrase
        lowered_value = compacted_value.lower()
        for hint in INSTITUTIONAL_CONTEXT_HINTS:
            if text_contains_hint(lowered_value, hint):
                return hint.title()
    return ""


def choose_sentence_by_hints(
    sentences: list[str],
    *,
    hints: tuple[str, ...],
    max_chars: int = 2000,
) -> str:
    for sentence in sentences:
        candidate = clean_viewer_text(sentence, max_sentences=2, max_chars=max_chars)
        if candidate and text_contains_any_hint(candidate.lower(), hints):
            return candidate
    return ""


def choose_trigger_or_setup(
    sentences: list[str],
    *,
    category: str,
    story_domain: str,
) -> str:
    if story_domain == "crime_justice":
        candidate = choose_sentence_by_hints(sentences, hints=CRIME_SETUP_HINTS)
        if candidate:
            return candidate
    if story_domain == "diplomacy":
        candidate = choose_sentence_by_hints(sentences, hints=DIPLOMACY_TRIGGER_HINTS)
        if candidate:
            return candidate
    if category == "sports":
        candidate = choose_sentence_by_hints(
            sentences,
            hints=SPORTS_AVAILABILITY_HINTS + SPORTS_FIXTURE_HINTS,
        )
        if candidate:
            return candidate
    return ""


def choose_evidence_points(
    sentences: list[str],
    *,
    story_domain: str,
) -> tuple[str, ...]:
    if story_domain != "crime_justice":
        return ()
    evidence_hints = (
        "surveillance",
        "cell data",
        "social media",
        "fingerprint",
        "complaint",
        "electronic monitoring",
        "license plate",
        "records",
        "data",
    )
    points: list[str] = []
    for sentence in sentences:
        candidate = clean_viewer_text(sentence, max_sentences=2, max_chars=2000)
        if candidate and text_contains_any_hint(candidate.lower(), evidence_hints):
            points.append(candidate)
        if len(points) >= 3:
            break
    return tuple(dedupe_preserve_order(points))


def choose_legal_consequence(
    sentences: list[str],
    *,
    story_domain: str,
) -> str:
    if story_domain != "crime_justice":
        return ""
    return choose_sentence_by_hints(sentences, hints=LEGAL_CONSEQUENCE_HINTS, max_chars=2000)


def choose_allegation_frame(
    *,
    story_language: str,
    story_domain: str,
    values: list[str],
) -> str:
    corpus = compact_text(" ".join(values)).lower()
    if story_domain != "crime_justice":
        return ""
    if text_contains_any_hint(corpus, ("prosecutor", "prosecutors")):
        return "Savcilara gore" if story_language == "tr" else "According to prosecutors"
    if text_contains_any_hint(corpus, ("complaint", "criminal complaint", "federal complaint")):
        return "Federal sikayete gore" if story_language == "tr" else "According to the federal complaint"
    if text_contains_any_hint(corpus, ("doj", "department of justice")):
        return "DOJ'ye gore" if story_language == "tr" else "DOJ says"
    if text_contains_any_hint(corpus, ("police", "authorities")):
        return "Yetkililere gore" if story_language == "tr" else "Authorities say"
    return ""


def infer_story_domain(
    cluster: list[PreparedArticle],
    *,
    category: str,
    values: list[str],
) -> str:
    detail_corpus = compact_text(" ".join(item.detail_text for item in cluster)).lower()
    combined = compact_text(" ".join(values + [detail_corpus])).lower()
    if category == "sports":
        return "sports"
    if category == "business":
        return "business"
    if category == "general" and text_contains_any_hint(combined, BUSINESS_NUMERIC_HINTS):
        return "business"
    if category == "science" or text_contains_any_hint(combined, SCIENCE_HINTS):
        return "science"
    if text_contains_any_hint(combined, CRIME_JUSTICE_HINTS):
        return "crime_justice"
    if text_contains_any_hint(combined, DIPLOMACY_HINTS):
        return "diplomacy"
    if category == "politics":
        return "policy"
    if category in {"world", "general"} and text_contains_any_hint(combined, INSTITUTIONAL_CONTEXT_HINTS):
        return "policy"
    if category in {"world", "general"} and text_contains_any_hint(combined, GENERAL_BREAKING_HINTS):
        return "general"
    return "general"


def build_story_fact_pack(
    cluster: list[PreparedArticle],
    *,
    category: str,
    headline: str,
    summary: str,
    key_points: list[str],
) -> StoryFactPack:
    values = [headline, summary, *key_points]
    detail_sentences = [
        sentence
        for item in cluster
        for sentence in split_sentences(item.detail_text)
        if compact_text(sentence)
    ]
    prompt_entities = build_prompt_entities(
        cluster,
        headline=headline,
        summary=summary,
        key_points=key_points,
    )
    story_language = dominant_story_language(cluster)
    story_domain = infer_story_domain(cluster, category=category, values=values)
    numeric_facts = tuple(extract_numeric_phrases(values + [item.detail_text for item in cluster]))
    actors = tuple(filter_informative_anchors(prompt_entities["names"], headline=headline, max_items=5))
    institution = select_institution_from_values(values + [item.detail_text for item in cluster[:2]])
    result_context = ""
    if category == "sports":
        for sentence in detail_sentences:
            lowered = sentence.lower()
            if extract_score([sentence]) or text_contains_any_hint(lowered, SPORTS_RESULT_HINTS):
                result_context = clean_viewer_text(sentence, max_sentences=2, max_chars=2000)
                break
    primary_event = clean_viewer_text(headline, max_sentences=2, max_chars=2000) or clean_viewer_text(summary, max_sentences=2, max_chars=2000)
    supporting_fact = choose_supporting_fact(detail_sentences + values, headline=headline, category=category)
    supporting_facts = tuple(
        dedupe_preserve_order(
            [
                candidate
                for candidate in [
                    supporting_fact,
                    *[
                        choose_supporting_fact(
                            [sentence],
                            headline=headline,
                            category=category,
                        )
                        for sentence in detail_sentences[:5]
                    ],
                ]
                if candidate and text_similarity(candidate, headline) < 0.9
            ]
        )[:3]
    )
    impact_fact = choose_impact_fact(
        detail_sentences + values,
        headline=headline,
        summary=summary,
        key_points=key_points,
        category=category,
        cluster=cluster,
    )
    trigger_or_setup = choose_trigger_or_setup(
        detail_sentences,
        category=category,
        story_domain=story_domain,
    )
    evidence_points = choose_evidence_points(detail_sentences, story_domain=story_domain)
    legal_consequence = choose_legal_consequence(detail_sentences, story_domain=story_domain)
    cluster_editorial_type = "report"
    for editorial_type in ("segment_teaser", "related_links_page", "video_page", "live_blog", "teaser_roundup", "speculative", "analysis"):
        if any(item.editorial_type == editorial_type for item in cluster):
            cluster_editorial_type = editorial_type
            break
    allegation_frame = choose_allegation_frame(
        story_language=story_language,
        story_domain=story_domain,
        values=values + [item.detail_text for item in cluster],
    )
    return StoryFactPack(
        core_event=primary_event,
        primary_event=primary_event,
        supporting_fact=supporting_fact,
        supporting_facts=supporting_facts,
        trigger_or_setup=trigger_or_setup,
        impact_or_next=impact_fact,
        impact_fact=impact_fact,
        evidence_points=evidence_points,
        numeric_facts=numeric_facts,
        actors=actors,
        institution=institution,
        result_context=result_context,
        legal_consequence=legal_consequence,
        allegation_frame=allegation_frame,
        story_domain=story_domain,
        uncertainty_level="speculative" if cluster_editorial_type in SPECULATIVE_EDITORIAL_TYPES else "confirmed",
        story_language=story_language,
        editorial_type=cluster_editorial_type,
    )


def is_comparison_story(
    *,
    category: str,
    headline: str,
    summary: str,
    key_points: list[str],
    score: str = "",
) -> bool:
    values = [headline, summary, *key_points]
    combined = compact_text(" ".join(values))
    if score:
        return True
    if COMPARISON_SIGNAL_RE.search(combined):
        return True
    if category == "business":
        return any(token in combined.lower() for token in ("spread", "gap", "relative to", "versus"))
    return False


def normalize_prompt_entity(name: str) -> str:
    return re.sub(r"['’]s$", "", compact_text(name)).strip()


def select_sports_matchup_and_focus(names: list[str], *, allow_matchup: bool) -> tuple[str, str]:
    normalized_names = [normalize_prompt_entity(name) for name in names if normalize_prompt_entity(name)]
    person_candidates = [name for name in normalized_names if " " in name]
    person_keys = {name.lower() for name in person_candidates}
    team_candidates = [name for name in normalized_names if name.lower() not in person_keys]
    non_titled_people = [
        name
        for name in person_candidates
        if not any(name.lower().startswith(prefix) for prefix in ROLE_PREFIXES)
    ]

    matchup = ""
    if allow_matchup and len(team_candidates) >= 2:
        matchup = " vs ".join(team_candidates[:2])

    focus_entity = (
        non_titled_people[-1]
        if non_titled_people
        else (person_candidates[0] if person_candidates else (team_candidates[0] if team_candidates else ""))
    )
    return matchup, focus_entity


def suggest_duration_seconds(category: str, key_points: list[str], summary: str) -> int:
    summary_len = len(compact_text(summary))
    point_count = len([point for point in key_points if compact_text(point)])
    complexity = classify_story_complexity(summary, key_points)

    if complexity == "short":
        base_by_category = {
            "sports": 9,
            "business": 10,
            "science": 11,
            "technology": 10,
            "world": 11,
            "politics": 11,
            "general": 10,
        }
        base = base_by_category.get(category, 10)
        suggested = base + (1 if summary_len > 85 else 0) + (1 if point_count else 0)
        return max(8, min(15, suggested))

    if complexity == "medium":
        base_by_category = {
            "sports": 16,
            "business": 18,
            "science": 20,
            "technology": 17,
            "world": 19,
            "politics": 20,
            "general": 17,
        }
        base = base_by_category.get(category, 17)
        suggested = base + (1 if summary_len > 170 else 0) + (1 if point_count >= 3 else 0)
        return max(15, min(24, suggested))

    base_by_category = {
        "sports": 22,
        "business": 23,
        "science": 27,
        "technology": 22,
        "world": 25,
        "politics": 26,
        "general": 22,
    }
    base = base_by_category.get(category, 22)
    suggested = base + (1 if summary_len > 260 else 0)
    return max(20, min(30, suggested))


def normalize_analysis_category(article_category: str | None, source_category: str | None) -> str:
    raw_value = compact_text(article_category).lower()
    if raw_value:
        if raw_value in VALID_CONTENT_CATEGORIES:
            return raw_value

        normalized = re.sub(r"[^a-z0-9]+", " ", raw_value).strip()
        if normalized in VALID_CONTENT_CATEGORIES:
            return normalized

        for category, keywords in CATEGORY_KEYWORDS.items():
            if normalized in keywords:
                return category
            if any(keyword in normalized for keyword in keywords):
                return category

    normalized_source = compact_text(source_category).lower()
    if normalized_source in SOURCE_TO_CONTENT_CATEGORY:
        return SOURCE_TO_CONTENT_CATEGORY[normalized_source]

    return "general"


def get_article_timestamp(article: Article) -> datetime:
    return article.published_at or article.created_at


async def get_recent_articles_for_analysis(
    db: AsyncSession,
    *,
    source_category: str | None = None,
    hours: int = 1,
    window_end: datetime | None = None,
) -> list[Article]:
    effective_end = window_end or utcnow()
    window_start = effective_end - timedelta(hours=hours)
    timestamp_expr = func.coalesce(Article.published_at, Article.created_at).label("analysis_timestamp")
    source_rank = func.row_number().over(
        partition_by=Article.source_id,
        order_by=timestamp_expr.desc(),
    ).label("source_rank")

    ranked_articles = (
        select(
            Article.id.label("article_id"),
            timestamp_expr,
            source_rank,
        )
        .join(Source)
        .where(timestamp_expr >= window_start)
    )
    ranked_articles = apply_article_visibility_filters(ranked_articles)

    if source_category:
        ranked_articles = ranked_articles.where(Article.source_category == source_category)

    ranked_subquery = ranked_articles.subquery()

    query = (
        select(Article)
        .join(ranked_subquery, Article.id == ranked_subquery.c.article_id)
        .options(selectinload(Article.source))
        .where(ranked_subquery.c.source_rank <= settings.ANALYSIS_MAX_ARTICLES_PER_SOURCE)
        .order_by(ranked_subquery.c.analysis_timestamp.desc())
        .limit(settings.ANALYSIS_MAX_ARTICLES_PER_RUN)
    )

    result = await db.execute(query)
    return list(result.scalars().all())


async def build_prepared_articles(
    articles: list[Article],
    *,
    category_filter: str | None = None,
) -> PreparedArticlesResult:
    prepared = await asyncio.gather(
        *[
            _build_prepared_article(
                article,
                category_filter=category_filter,
            )
            for article in articles
        ]
    )

    prepared_articles: list[PreparedArticle] = []
    rejections: list[AnalysisRejection] = []
    for item in prepared:
        if isinstance(item, PreparedArticle):
            prepared_articles.append(item)
        elif isinstance(item, AnalysisRejection):
            rejections.append(item)

    return PreparedArticlesResult(
        prepared_articles=prepared_articles,
        rejections=rejections,
    )


async def _build_prepared_article(
    article: Article,
    *,
    category_filter: str | None,
) -> PreparedArticle | AnalysisRejection | None:
    normalized_category = normalize_analysis_category(article.category, article.source_category)
    if category_filter and normalized_category != category_filter:
        return None

    timestamp = get_article_timestamp(article)
    source_rules = parse_source_analysis_rules(article.source if hasattr(article, "source") else None)
    detail_text = build_detail_text(article)
    cluster_text = build_cluster_text(article)
    story_language = detect_text_language(
        " ".join([detail_text, cluster_text, article.title, article.summary or ""]),
        fallback=compact_text(article.language) or "en",
    )
    editorial_type = classify_editorial_type(article, detail_text=detail_text)
    rejection_reason = article_eligibility_reason(
        article,
        timestamp=timestamp,
        detail_text=detail_text,
        editorial_type=editorial_type,
        rules=source_rules,
    )
    if rejection_reason:
        return make_rejection(
            rejection_reason,
            stage="article",
            title=article.title,
            url=article.url,
            source_slug=article.source.slug if article.source else "unknown",
            source_name=article.source.name if article.source else "Unknown Source",
        )

    source_name = article.source.name if article.source else "Unknown Source"
    source_slug = article.source.slug if article.source else "unknown"

    return PreparedArticle(
        article=article,
        normalized_category=normalized_category,
        cluster_text=cluster_text,
        detail_text=detail_text,
        editorial_type=editorial_type,
        story_language=story_language,
        uncertainty_level=classify_uncertainty_level(editorial_type),
        timestamp=timestamp,
        source_name=source_name,
        source_slug=source_slug,
        tag_tokens={compact_text(str(tag)).lower() for tag in (article.tags or []) if compact_text(str(tag))},
        title_tokens=tokenize(article.title),
        text_tokens=tokenize(cluster_text, max_tokens=80),
    )


def articles_are_candidate_match(left: PreparedArticle, right: PreparedArticle) -> bool:
    if left.normalized_category != right.normalized_category:
        return False

    title_jaccard = jaccard_similarity(left.title_tokens, right.title_tokens)
    tag_jaccard = jaccard_similarity(left.tag_tokens, right.tag_tokens)
    text_jaccard = jaccard_similarity(left.text_tokens, right.text_tokens)
    title_ratio = SequenceMatcher(
        None,
        normalize_title(left.article.title),
        normalize_title(right.article.title),
    ).ratio()
    shared_title_terms = len(left.title_tokens & right.title_tokens)

    if titles_are_similar(left.article.title, right.article.title, threshold=0.72):
        return True
    if title_ratio >= 0.82:
        return True
    if title_jaccard >= 0.45:
        return True
    if shared_title_terms >= 2 and (text_jaccard >= 0.16 or tag_jaccard >= 0.25):
        return True

    weighted_score = (title_jaccard * 0.55) + (title_ratio * 0.25) + (tag_jaccard * 0.10) + (text_jaccard * 0.10)
    return shared_title_terms >= 2 and weighted_score >= 0.36


def build_candidate_clusters(prepared_articles: list[PreparedArticle]) -> list[list[PreparedArticle]]:
    clustered: list[list[PreparedArticle]] = []
    articles_by_category: dict[str, list[PreparedArticle]] = defaultdict(list)

    for article in prepared_articles:
        articles_by_category[article.normalized_category].append(article)

    for articles in articles_by_category.values():
        if len(articles) < 2:
            continue

        parent = list(range(len(articles)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left_index: int, right_index: int) -> None:
            left_root = find(left_index)
            right_root = find(right_index)
            if left_root != right_root:
                parent[right_root] = left_root

        for left_index in range(len(articles)):
            for right_index in range(left_index + 1, len(articles)):
                if articles_are_candidate_match(articles[left_index], articles[right_index]):
                    union(left_index, right_index)

        grouped: dict[int, list[PreparedArticle]] = defaultdict(list)
        for index, article in enumerate(articles):
            grouped[find(index)].append(article)

        for cluster in grouped.values():
            if len(cluster) > 1:
                clustered.append(sorted(cluster, key=lambda item: item.timestamp, reverse=True))

    return clustered


def build_visual_asset_candidates(cluster: list[PreparedArticle]) -> list[VisualAssetCandidate]:
    candidates: list[VisualAssetCandidate] = []
    seen_sources: set[str] = set()
    for item in cluster:
        if item.source_slug in seen_sources:
            continue
        seen_sources.add(item.source_slug)
        candidates.append(
            VisualAssetCandidate(
                article_id=item.article.id,
                article_url=item.article.url,
                title=item.article.title,
                source_name=item.source_name,
                image_url=item.article.image_url,
            )
        )
        if len(candidates) >= settings.VISUAL_ASSET_MAX_PER_TOPIC:
            break
    return candidates


async def resolve_visual_assets_for_cluster(
    cluster: list[PreparedArticle],
    resolver: VisualAssetResolver,
) -> list[VisualAsset]:
    candidates = build_visual_asset_candidates(cluster)
    if not candidates:
        return []
    return await resolver.resolve(candidates)


class OllamaTopicAnalyzer:
    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_MODEL

    async def analyze_cluster(
        self,
        cluster: list[PreparedArticle],
        visual_assets: list[VisualAsset] | None = None,
    ) -> list[dict[str, Any]]:
        visual_assets = visual_assets or []
        raw_response = await self._request_generation(self._build_prompt(cluster, visual_assets))
        try:
            parsed = self._parse_json(raw_response)
        except OllamaAnalysisError:
            repair_response = await self._request_generation(
                self._build_repair_prompt(raw_response, cluster, visual_assets)
            )
            parsed = self._parse_json(repair_response)

        topics = self._extract_valid_topics(parsed)
        if topics:
            return topics

        repair_response = await self._request_generation(
            self._build_repair_prompt(raw_response, cluster, visual_assets)
        )
        repaired_topics = self._extract_valid_topics(self._parse_json(repair_response))
        if repaired_topics:
            return repaired_topics
        raise OllamaAnalysisError("Ollama response did not contain a valid topics list")

    async def _request_generation(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=5.0)) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise OllamaAnalysisError(str(exc)) from exc
        body = response.json()
        return compact_text(body.get("response"))

    def _topic_payload_is_valid(self, topic: dict[str, Any]) -> bool:
        if not isinstance(topic, dict):
            return False
        has_article_ids = isinstance(topic.get("article_ids"), list)
        has_new_shape = isinstance(topic.get("fact_pack"), dict) and isinstance(topic.get("angle_plans"), list)
        has_legacy_shape = bool(topic.get("headline_tr")) or isinstance(topic.get("video_plan"), dict)
        return has_article_ids and (has_new_shape or has_legacy_shape)

    def _extract_valid_topics(self, parsed: dict[str, Any]) -> list[dict[str, Any]]:
        topics = parsed.get("topics", [])
        if not isinstance(topics, list):
            return []
        return [topic for topic in topics if self._topic_payload_is_valid(topic)]

    def _build_prompt(self, cluster: list[PreparedArticle], visual_assets: list[VisualAsset]) -> str:
        fallback_fact_pack = build_story_fact_pack(
            cluster,
            category=cluster[0].normalized_category if cluster else "general",
            headline=cluster[0].article.title if cluster else "",
            summary=cluster[0].detail_text if cluster else "",
            key_points=[item.article.title for item in cluster[:2]],
        )
        story_language = fallback_fact_pack.story_language
        editorial_type = fallback_fact_pack.editorial_type
        story_domain = fallback_fact_pack.story_domain
        safe_angle_types = SAFE_ANGLE_TYPES_BY_DOMAIN.get(story_domain, SAFE_ANGLE_TYPES_BY_DOMAIN["general"])
        articles_payload = [
            {
                "article_id": str(item.article.id),
                "source_name": item.source_name,
                "source_slug": item.source_slug,
                "story_language": item.story_language,
                "editorial_type": item.editorial_type,
                "published_at": item.timestamp.isoformat(),
                "category": item.normalized_category,
                "title": item.article.title,
                "image_url": item.article.image_url,
                "tags": sorted(item.tag_tokens),
                "cluster_text": item.cluster_text[: CLUSTER_TEXT_CHAR_LIMIT],
                "detail_text": item.detail_text[: settings.ANALYSIS_TEXT_CHAR_LIMIT],
            }
            for item in cluster
        ]
        assets_payload = [
            {
                "asset_id": asset.asset_id,
                "kind": asset.kind,
                "source_name": asset.source_name,
                "alt_text": asset.alt_text,
            }
            for asset in visual_assets
        ]

        schema = {
            "topics": [
                {
                    "article_ids": ["uuid"],
                    "confidence": 0.84,
                    "fact_pack": {
                        "core_event": "Short statement of the concrete event in the dominant story language",
                        "actors": ["Named actor", "Institution"],
                        "supporting_facts": ["Supporting fact 1", "Supporting fact 2"],
                        "trigger_or_setup": "Setup, trigger, or availability context in the dominant story language",
                        "impact_or_next": "Impact, practical consequence, or next step in the dominant story language",
                        "evidence_points": ["Evidence or proof point 1"],
                        "legal_consequence": "Legal consequence if stated in the source, otherwise empty string",
                        "institution": "Main institution, mediator, or governing body",
                        "result_context": "Result, fixture, or concrete sports context if applicable",
                        "allegation_frame": "Attribution phrase like 'According to prosecutors' or empty string",
                        "story_language": story_language,
                        "editorial_type": editorial_type,
                        "story_domain": story_domain,
                        "uncertainty_level": "confirmed",
                    },
                    "social_media_content": {
                        "news_summary": "Kısa ve öz haber özeti",
                        "platforms": {
                            "instagram_reels": {
                                "hook_text": "Bunu daha önce duymadınız!",
                                "body_text": "Haberin can alıcı detayı burada...",
                                "call_to_action": "Takipte kalın."
                            },
                            "ai_image_prompt": "Cinematic shot of [Haber Konusu], highly detailed, 8k, realistic lighting..."
                        }
                    },
                    "angle_plans": [
                        {
                            "angle_id": safe_angle_types[0],
                            "angle_type": safe_angle_types[0],
                            "title": "Viewer-facing short title in the dominant story language",
                            "hook": "Short opening hook in the dominant story language",
                            "duration_seconds": 16,
                            "tone": "Urgent, clear, and factual",
                            "angle_rationale": "One English sentence explaining why this angle is useful",
                            "scenes": [
                                {
                                    "id": "scene-1",
                                    "start_second": 0,
                                    "duration_seconds": 6,
                                    "headline": "Short viewer-facing scene headline in the dominant story language (max 6 words)",
                                    "body": "Optional short on-screen supporting text (max 10 words). Can be empty.",
                                    "voiceover": "Complete, natural spoken news anchor sentence. Must be highly informative and conversational. At least 15 words.",
                                    "visual_direction": "English production note for visuals",
                                    "motion_direction": "English production note for motion",
                                    "transition": "English transition note",
                                }
                            ],
                        },
                    ],
                    "headline_tr": "Optional legacy compatibility headline in the dominant story language",
                    "summary_tr": "Optional legacy compatibility summary in the dominant story language",
                    "key_points_tr": ["Optional legacy key point"],
                    "why_it_matters_tr": "Optional legacy implication line in the dominant story language",
                    "confidence": 0.84,
                }
            ]
        }

        return (
            "You are analyzing news coverage gathered in the last hour from multiple publishers.\n"
            "Group only articles that describe the same concrete event or development.\n"
            "If the candidate cluster actually contains different stories, split it into separate topics.\n"
            "Do not include groups backed by fewer than two unique sources.\n"
            "You are the lead video director and scriptwriter. Rely entirely on the full detail_text to build the story narrative and scene flow.\n"
            "Never use teaser, roundup, related-links, replay, show, segment, or video-page copy as the main story.\n"
            "Use detail_text as the main article context when extracting facts and planning angles.\n"
            "Use cluster_text only as a short comparison aid; do not let it override detail_text.\n"
            f"The dominant story language for this cluster is {story_language}. All viewer-facing copy must stay in that language.\n"
            "Do not mix languages inside viewer-facing copy.\n"
            "Preserve uncertainty. If the coverage is speculative or allegation-based, keep words like could, alleged, according to prosecutors, DOJ says, complaint says, linked, or expected rather than rewriting them as certainty.\n\n"
            "EDITORIAL ROLE:\n"
            "- Sen profesyonel bir sosyal medya içerik üreticisi ve haber editörüsün.\n"
            "- Haber metinlerini analiz et, en çarpıcı noktaları belirle ve bunları YouTube Shorts/Instagram formatına (kanca, gelişme, çağrı) dönüştür.\n"
            "- JSON formatı dışında açıklama yapma. Görsel betimlemeleri (image prompts) fotorealistik ve dramatik detaylarla süsle.\n"
            "- Extract a compact fact pack first.\n"
            "- Then produce ONE safe, highly engaging editorial angle for the story.\n"
            f"- The expected safe angle type for this domain is: {safe_angle_types[0]}.\n"
            "- Do not use freeform personas like sports commentator, historian, or financial analyst.\n"
            "- Do not invent outside comparisons, historical analogies, or unsupported consequences.\n\n"
            "FACT EXTRACTION RULES:\n"
            "- core_event should capture the main concrete development.\n"
            "- supporting_facts must contain distinct factual beats, not headline restatements.\n"
            "- trigger_or_setup should explain how the story developed, resumed, or why availability changed.\n"
            "- impact_or_next should explain what changes next or why the story matters now.\n"
            "- evidence_points should only be included when the detail_text actually mentions proof, records, surveillance, monitoring, complaint details, or similar concrete evidence.\n"
            "- legal_consequence should only be populated when the article states charges, sentencing risk, or formal legal exposure.\n"
            "- allegation_frame must be populated for crime/legal stories when needed.\n\n"
            "ANGLE PLANNING RULES:\n"
            "- Each angle must be a Remotion-friendly YouTube short plan.\n"
            "- Each angle should use 2 to 4 scenes unless the story is extremely short.\n"
            "- Each scene must add a new concrete fact, consequence, or setup detail.\n"
            "- Every scene headline and body must be complete sentences or clean fragments. No ellipses. No visibly truncated copy.\n"
            "- voiceover MUST be written as a natural, engaging news anchor script. It should sound human, authoritative, and conversational. Do NOT use robotic or repetitive phrasing.\n"
            "- visual_direction, motion_direction, and transition must be in English production language.\n"
            "- Viewer-facing scene copy must remain in the dominant story language.\n"
            "- For sports return or fitness stories, include player status, availability, and fixture context.\n"
            "- For diplomacy stories, include mediator or institution, the development, and the trigger or contradiction on the ground.\n"
            "- For crime/legal stories, preserve allegation framing and include charges or legal exposure when stated.\n\n"
            f"Cluster editorial type: {editorial_type}. Story domain: {story_domain}.\n"
            "Return JSON only. Follow this shape exactly:\n"
            f"{json.dumps(schema, ensure_ascii=True)}\n"
            "If no shared story exists, return {\"topics\": []}.\n"
            f"Available assets:\n{json.dumps(assets_payload, ensure_ascii=True)}\n"
            f"Articles:\n{json.dumps(articles_payload, ensure_ascii=True)}"
        )

    def _build_repair_prompt(
        self,
        raw_response: str,
        cluster: list[PreparedArticle],
        visual_assets: list[VisualAsset],
    ) -> str:
        return (
            "Repair the previous JSON response.\n"
            "Return JSON only.\n"
            "Keep the same stories and article_ids.\n"
            "Ensure each topic contains article_ids plus either the legacy fields or the new fact_pack + angle_plans fields.\n"
            "Do not use ellipses. Do not leave incomplete sentences. Preserve allegation framing where needed.\n"
            f"Expected article ids: {[str(item.article.id) for item in cluster]}\n"
            f"Available assets: {json.dumps([{'asset_id': asset.asset_id, 'kind': asset.kind} for asset in visual_assets], ensure_ascii=True)}\n"
            f"Previous response:\n{raw_response}"
        )

    def _parse_json(self, value: str) -> dict[str, Any]:
        if not value:
            raise OllamaAnalysisError("Empty Ollama response")

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            start = value.find("{")
            end = value.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise OllamaAnalysisError("Ollama response is not valid JSON") from None
            try:
                return json.loads(value[start : end + 1])
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive path
                raise OllamaAnalysisError("Failed to parse Ollama JSON payload") from exc


def build_contextual_prompt_parts(
    cluster: list[PreparedArticle],
    *,
    category: str,
    headline: str,
    summary: str,
    key_points: list[str],
    why_it_matters: str,
) -> VideoPromptParts:
    fact_pack = build_story_fact_pack(
        cluster,
        category=category,
        headline=headline,
        summary=summary,
        key_points=key_points,
    )
    entities = build_prompt_entities(
        cluster,
        headline=headline,
        summary=summary,
        key_points=key_points,
    )
    sources = entities["sources"]
    representative_titles = [truncate_for_prompt(item.article.title) for item in cluster[:3]]
    score = entities["score"]
    matchup = entities["matchup"]
    focus_entity = entities["focus_entity"]
    numeric_phrase = entities["numeric_phrase"]
    top_key_point = entities["top_key_point"] or truncate_for_prompt(summary)
    supporting_key_points = entities["supporting_key_points"]
    focus_names = list(fact_pack.actors) or entities["names"]
    source_rules = cluster_analysis_rules(cluster)
    representative_url = cluster[0].article.url if cluster else ""
    comparison_story = is_comparison_story(
        category=category,
        headline=headline,
        summary=summary,
        key_points=key_points,
        score=score,
    )
    story_subtype = infer_story_subtype(
        category=category,
        headline=headline,
        url=representative_url,
        summary=summary,
        key_points=key_points,
        comparison_story=comparison_story,
        rules=source_rules,
    )
    duration_seconds = suggest_duration_seconds(category, key_points, summary)
    if category == "sports":
        sports_matchup, sports_focus = select_sports_matchup_and_focus(
            focus_names,
            allow_matchup=story_subtype == "matchup",
        )
        matchup = sports_matchup or matchup
        focus_entity = sports_focus or focus_entity

    format_hint: str
    story_angle: str
    visual_brief: str
    motion_treatment: str
    transition_style: str
    scene_sequence: list[str]
    tone: str
    design_keywords: list[str]
    must_include: list[str]

    if category == "sports":
        if story_subtype == "matchup":
            format_hint = "Premium broadcast-meets-kinetic-typography sports short"
            story_angle = (
                f"Turn {matchup or truncate_for_prompt(headline)} into a sharp, emotionally readable sports moment"
                f"{f' with the {score} result visible throughout' if score else (f' with {fact_pack.result_context}' if fact_pack.result_context else '')}"
                f"{f' and {focus_entity} framed as the decisive figure' if focus_entity else ''}."
            )
            visual_brief = (
                "Use stadium-light contrast, glossy score bugs, team-color energy, and a decisive-play spotlight. "
                "Let the visuals feel premium and fast, not like a generic sports bulletin."
            )
            motion_treatment = (
                "Use snap zooms, scoreboard flips, elastic stat reveals, and fast but readable kinetic typography."
            )
            transition_style = "Scoreboard wipes, light-streak cuts, lens-flare flashes, and energetic vertical pushes."
            scene_sequence = [
                f"Open on a bold scoreboard lockup for {matchup or truncate_for_prompt(headline)}"
                f"{f' with {score} anchored in the center' if score else ''}.",
                f"Punch into the decisive moment with a player-led spotlight"
                f"{f' on {focus_entity}' if focus_entity else ''} and short on-screen language around: {truncate_for_prompt(top_key_point)}.",
                "Finish on a momentum-rich result card that feels like the final beat of a highlight package, not a newsroom recap.",
            ]
            design_keywords = ["broadcast polish", "kinetic typography", "score bug", "stadium glow", "snap zooms"]
        else:
            format_hint = "Premium social-first sports update"
            focal_phrase = focus_entity or truncate_for_prompt(headline)
            if story_subtype == "schedule":
                story_angle = (
                    f"Turn {truncate_for_prompt(headline)} into a clear schedule-driven sports update centered on {focal_phrase}, "
                    "using date and venue information without forcing a matchup recap."
                )
            elif story_subtype == "odds":
                story_angle = (
                    f"Explain {truncate_for_prompt(headline)} as a betting-and-expectations sports update centered on {focal_phrase}, "
                    "without pretending a game result already happened."
                )
            elif story_subtype == "admin":
                story_angle = (
                    f"Tell {truncate_for_prompt(headline)} as an off-field sports development centered on {focal_phrase}, "
                    "with editorial clarity and consequence, not game-highlight energy."
                )
            else:
                story_angle = (
                    f"Tell {truncate_for_prompt(headline)} as a short, human sports update"
                    f"{f' centered on {focus_entity}' if focus_entity else ''}, without forcing a matchup or scoreboard framing."
                )
            if fact_pack.uncertainty_level == "speculative":
                story_angle = (
                    f"Treat {truncate_for_prompt(headline)} as a speculative sports update, keeping all on-screen language clearly uncertain"
                    f"{f' and centered on {focus_entity}' if focus_entity else ''}."
                )
            visual_brief = (
                "Use a strong athlete or coach portrait, editorial sports typography, subtle stadium texture, and one clean hero-image-led composition. "
                "It should feel fast and premium, but calmer and more personal than a match recap."
            )
            motion_treatment = (
                "Use restrained push-ins, portrait parallax, short emphasis reveals, and crisp headline timing."
            )
            transition_style = "Soft light wipes, subtle punch-ins, and clean editorial fades."
            scene_sequence = [
                f"Open on a strong portrait or training visual with the headline {truncate_for_prompt(headline)}.",
                f"Add one short support beat that explains the update clearly: {truncate_for_prompt(fact_pack.supporting_fact or top_key_point)}.",
                "Only add a final beat if it introduces genuinely new context, otherwise let the first image and headline carry the story.",
            ]
            design_keywords = ["editorial sports", "hero portrait", "clean typography", "subtle stadium texture", "calm motion"]
        must_include = dedupe_preserve_order(
            ([matchup] if matchup else [])
            + ([score] if score else [])
            + ([focus_entity] if focus_entity else [])
            + list(fact_pack.numeric_facts[:2])
            + representative_titles[:2]
        )
        tone = "High-energy, premium, and emotionally clear"
    elif category == "business":
        if story_subtype == "market":
            format_hint = "Editorial financial explainer with premium motion graphics"
            story_angle = (
                f"Frame {truncate_for_prompt(headline)} as a crisp market narrative with one clear trigger and one clear consequence"
                f"{f', centering {numeric_phrase or (fact_pack.numeric_facts[0] if fact_pack.numeric_facts else '')} as the most visible data point' if (numeric_phrase or fact_pack.numeric_facts) else ''}."
            )
            visual_brief = (
                "Use elegant dark-finance UI panels, glowing charts, restrained glass surfaces, and clean directional arrows. "
                "It should feel closer to a premium Bloomberg-style promo than a static market card."
            )
            motion_treatment = "Smooth value-counting, layered chart parallax, sliding data panes, and restrained camera drift."
            transition_style = "Glass panel wipes, soft chart morphs, ticker pulls, and clean numeric snap-ins."
            scene_sequence = [
                "Open with a single commanding market card that states the move and the tension immediately.",
                f"Show the trigger and the reaction as a clear visual chain, led by: {truncate_for_prompt(fact_pack.supporting_fact or top_key_point)}.",
                f"Close on a poised outlook board hinting at what traders or observers watch next: {truncate_for_prompt(fact_pack.impact_fact or why_it_matters)}.",
            ]
            design_keywords = ["glassmorphism", "market UI", "chart glow", "directional arrows", "editorial finance"]
            tone = "Analytical, premium, and composed"
        else:
            format_hint = "Editorial business explainer with restrained motion graphics"
            story_angle = (
                f"Explain {truncate_for_prompt(headline)} as a direct business update focused on the main actor, the immediate development, "
                "and the most relevant practical implication."
            )
            visual_brief = (
                "Use clean editorial panels, restrained data callouts, and modern newsroom typography. "
                "Keep it premium and informative without forcing a market-terminal aesthetic."
            )
            motion_treatment = "Use restrained panel motion, subtle text emphasis, and clear sequencing over flashy chart choreography."
            transition_style = "Editorial panel slides, crisp fades, and minimal stat reveals."
            scene_sequence = [
                "Open with the key business development in one clean headline panel.",
                f"Add the clearest supporting detail with a labeled explainer card: {truncate_for_prompt(fact_pack.supporting_fact or top_key_point)}.",
                f"Close on the practical implication or next decision to watch: {truncate_for_prompt(fact_pack.impact_fact or why_it_matters)}.",
            ]
            design_keywords = ["editorial business", "clean panels", "newsroom typography", "restrained motion", "clear labels"]
            tone = "Clear, premium, and informative"
        must_include = dedupe_preserve_order(
            focus_names[:2]
            + list(fact_pack.numeric_facts[:2])
            + ([numeric_phrase] if numeric_phrase and story_subtype == "market" else [])
            + representative_titles[:2]
        )
    elif category == "science":
        format_hint = "Cinematic editorial science explainer"
        story_angle = (
            f"Treat {truncate_for_prompt(headline)} as a milestone story with wonder, clarity, and technical confidence."
        )
        visual_brief = (
            "Use high-contrast editorial science graphics, orbital rings, precision labels, and a minimal sense of awe. "
            "Avoid cheesy sci-fi; keep it elegant and grounded."
        )
        motion_treatment = "Slow orbital drift, layered depth, subtle scale pulls, and clean milestone reveals."
        transition_style = "Soft ring tunnels, luminous fades, and precise timeline morphs."
        scene_sequence = [
            "Open with the mission or breakthrough name, its current status, and a single bold milestone card.",
            f"Walk through the milestone sequence with technical labels and the clearest supporting fact: {top_key_point}.",
            f"Close with why the development matters next for research, missions, or public impact, using short takeaway panels.",
        ]
        design_keywords = ["orbital graphics", "editorial science", "precision labels", "soft glow", "timeline cards"]
        must_include = dedupe_preserve_order(focus_names[:3] + representative_titles[:2])
        tone = "Elegant, factual, and forward-looking"
    elif category == "entertainment":
        format_hint = "Pop-culture and entertainment news short"
        story_angle = (
            f"Deliver {truncate_for_prompt(headline)} as an engaging, fast-paced entertainment update."
        )
        visual_brief = (
            "Use vibrant colors, dynamic portrait cutouts, and glossy typography. It should feel like a premium magazine or pop-culture show."
        )
        motion_treatment = "Smooth parallax, bouncy text reveals, and energetic transitions."
        transition_style = "Light leaks, smooth wipes, and fast punch-ins."
        scene_sequence = [
            "Open with a vibrant hero portrait stating the main news.",
            f"Add context or the latest development: {truncate_for_prompt(fact_pack.supporting_fact or top_key_point)}.",
            f"Close with the reaction or what's next: {truncate_for_prompt(fact_pack.impact_fact or why_it_matters)}.",
        ]
        design_keywords = ["pop-culture", "magazine style", "vibrant", "glossy"]
        must_include = dedupe_preserve_order(focus_names[:2] + representative_titles[:2])
        tone = "Engaging, conversational, and energetic"
    elif category in {"world", "politics", "general"}:
        format_hint = "Editorial breaking-news short with strong typography"
        story_angle = (
            f"Deliver {truncate_for_prompt(headline)} as an editorial news short that feels urgent, human, and visually disciplined."
        )
        visual_brief = (
            "Use bold typography, cropped documentary-style framing, editorial color fields, and scene cards that make the event readable without relying on logos or source screenshots."
        )
        motion_treatment = "Measured push-ins, kinetic headline swaps, subtle tilt, and crisp card choreography."
        transition_style = "Editorial wipes, iris reveals, typography pushes, and restrained whip transitions."
        scene_sequence = [
            "Open with the main development and the most important actor or location in one bold headline panel.",
            f"Lay out the event sequence in two or three factual cards, anchored by: {truncate_for_prompt(fact_pack.supporting_fact or top_key_point)}.",
            f"Close with the immediate implication and what to watch next, staying human and clear: {truncate_for_prompt(fact_pack.impact_fact or why_it_matters)}.",
        ]
        design_keywords = ["editorial typography", "news texture", "headline cards", "measured motion", "documentary framing"]
        must_include = dedupe_preserve_order(
            focus_names[:3]
            + ([fact_pack.institution] if fact_pack.institution else [])
            + supporting_key_points[:1]
            + representative_titles[:2]
        )
        tone = "Urgent, human, and highly legible"
    else:
        format_hint = "Modern motion-graphics explainer"
        story_angle = (
            f"Explain {truncate_for_prompt(headline)} with a clean headline-led structure, one supporting detail panel, "
            "and a sharp closing implication."
        )
        visual_brief = (
            "Use labeled motion-graphics panels, visible facts, and minimal filler. Every scene should introduce a new "
            "piece of information rather than reusing the same layout."
        )
        motion_treatment = "Subtle depth, smart kinetic text, calm panel choreography, and clean emphasis reveals."
        transition_style = "Shape wipes, panel slides, and soft scale transitions."
        scene_sequence = [
            "Open with the headline and one bold evidence strip.",
            f"Show the strongest supporting detail with a labelled panel: {top_key_point}.",
            f"Close with why it matters and the next thing to watch, based on {truncate_for_prompt(why_it_matters)}.",
        ]
        design_keywords = ["clean motion graphics", "bold labels", "subtle depth", "panel choreography"]
        must_include = dedupe_preserve_order(focus_names[:2] + representative_titles[:2])
        tone = "Factual, composed, and easy to scan"

    avoid = [
        "Publisher logos",
        "Watermarks",
        "Mandatory source screenshots unless visually essential",
        "Generic filler footage unrelated to the story",
        "Claims not supported by the summary",
    ]

    fallback_must_include = filter_informative_anchors(representative_titles[:3], headline=headline, max_items=3)

    return VideoPromptParts(
        format_hint=format_hint,
        story_angle=story_angle,
        visual_brief=visual_brief,
        motion_treatment=motion_treatment,
        transition_style=transition_style,
        scene_sequence=scene_sequence[:4],
        tone=tone,
        design_keywords=design_keywords[:6],
        must_include=filter_informative_anchors(must_include, headline=headline, max_items=5) or fallback_must_include,
        avoid=avoid,
        duration_seconds=duration_seconds,
    )


def build_fallback_prompt_parts(
    cluster: list[PreparedArticle],
    *,
    category: str,
    headline: str,
    summary: str,
    key_points: list[str],
    why_it_matters: str,
) -> VideoPromptParts:
    return build_contextual_prompt_parts(
        cluster,
        category=category,
        headline=headline,
        summary=summary,
        key_points=key_points,
        why_it_matters=why_it_matters,
    )


def build_video_prompt_from_parts(parts: VideoPromptParts, *, category: str) -> str:
    scenes = "\n".join(f"{index + 1}. {scene}" for index, scene in enumerate(parts.scene_sequence))
    keywords = ", ".join(parts.design_keywords)
    story_anchors = ", ".join(parts.must_include)
    avoid = ", ".join(parts.avoid[:4])
    return (
        "Use Remotion best practices.\n"
        f"Create a {parts.duration_seconds}-second {parts.format_hint.lower()} for this {category} story.\n\n"
        f"Core idea:\n{parts.story_angle}\n\n"
        f"Look and feel:\n{parts.visual_brief}\n\n"
        f"Motion language:\n{parts.motion_treatment}\n\n"
        f"Transitions:\n{parts.transition_style}\n\n"
        f"Tone:\n{parts.tone}\n\n"
        f"Possible sequence:\n{scenes}\n\n"
        f"Design keywords to lean on: {keywords}\n"
        f"Helpful story anchors: {story_anchors}\n"
        f"If something feels forced or too literal, avoid: {avoid}.\n\n"
        "A single-scene execution is completely valid if it communicates the story cleanly.\n"
        "Keep the runtime lean and social-first; do not stretch a small update into a long explainer.\n"
        "Do not feel obligated to show every fact as a literal object on screen. "
        "If the strongest execution is built from typography, abstract motion graphics, UI-style panels, gradients, light, texture, or symbolic animation, follow that idea.\n"
        "Do not force sources, logos, screenshots, or maps unless they genuinely improve the video.\n"
        "Prioritize a visually coherent, human, pleasing piece over a rigid checklist."
    ).strip()


def clamp_video_duration(value: int, default: int = 30) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = default
    return max(8, min(30, numeric))


def infer_pacing_hint(duration_seconds: int, scene_count: int) -> str:
    if duration_seconds <= 14 or scene_count >= 3:
        return "fast"
    if duration_seconds >= 24:
        return "measured"
    return "balanced"


def default_layout_for_scene(
    *,
    category: str,
    purpose: str,
    key_data: str = "",
    key_figures: list[str] | None = None,
    comparison_story: bool = False,
    has_visual_assets: bool = False,
) -> str:
    figures = key_figures or []
    if purpose == "hook":
        if has_visual_assets or category in {"sports", "science"}:
            return "full-bleed"
        return "headline"
    if purpose == "comparison":
        return "comparison" if comparison_story else "split"
    if purpose == "context":
        return "timeline"
    if purpose == "detail":
        if key_data:
            return "stat"
        return "split"
    if purpose == "takeaway":
        return "minimal"
    if purpose == "close":
        return "minimal"
    if purpose == "explain":
        if category in {"world", "politics", "science"}:
            return "timeline"
        if category == "sports" and comparison_story and len(figures) >= 2:
            return "comparison"
        if key_data:
            return "stat"
        return "split"
    return "headline"


def allocate_scene_durations(total_duration: int, scene_count: int, requested: list[int] | None = None) -> list[int]:
    total_duration = clamp_video_duration(total_duration)
    if scene_count <= 0:
        return []
    if scene_count == 1:
        return [total_duration]

    minimum = 2
    base = [minimum] * scene_count
    remaining = max(0, total_duration - (minimum * scene_count))
    weights = requested or [1] * scene_count
    clean_weights = [max(1, int(weight)) for weight in weights[:scene_count]]
    if len(clean_weights) < scene_count:
        clean_weights.extend([1] * (scene_count - len(clean_weights)))
    total_weight = sum(clean_weights)
    raw_shares = [(remaining * weight) / total_weight for weight in clean_weights]
    extra = [int(share) for share in raw_shares]
    result = [base_value + extra_value for base_value, extra_value in zip(base, extra, strict=False)]
    remainder = remaining - sum(extra)
    fractional_order = sorted(
        range(scene_count),
        key=lambda index: raw_shares[index] - int(raw_shares[index]),
        reverse=True,
    )
    for index in fractional_order[:remainder]:
        result[index] += 1
    return result


def scene_text_signature(scene: VideoPlanScene) -> str:
    return compact_text(
        " ".join(
            [
                scene.headline,
                scene.body,
                *scene.supporting_points,
                scene.key_data,
                *scene.key_figures,
            ]
        )
    )


def scene_similarity(left: VideoPlanScene, right: VideoPlanScene) -> float:
    left_signature = scene_text_signature(left)
    right_signature = scene_text_signature(right)
    if not left_signature or not right_signature:
        return 0.0
    return max(
        SequenceMatcher(None, left_signature.lower(), right_signature.lower()).ratio(),
        jaccard_similarity(tokenize(left_signature, max_tokens=60), tokenize(right_signature, max_tokens=60)),
    )


def scene_progression_score(scenes: list[VideoPlanScene]) -> float:
    if len(scenes) <= 1:
        return 1.0
    scores: list[float] = []
    for index in range(1, len(scenes)):
        similarity = max(scene_similarity(scenes[index], previous) for previous in scenes[:index])
        novelty_bonus = 0.0
        if scenes[index].key_data and scenes[index].key_data != scenes[index - 1].key_data:
            novelty_bonus += 0.15
        if scenes[index].supporting_points:
            novelty_bonus += 0.1
        if scenes[index].layout_hint != scenes[index - 1].layout_hint:
            novelty_bonus += 0.05
        scores.append(max(0.0, 1.0 - similarity) + novelty_bonus)
    return sum(scores) / len(scores)


def normalize_scene_layout_hint(
    scene: VideoPlanScene,
    *,
    index: int,
    category: str,
    comparison_story: bool,
    visual_assets: list[VisualAsset],
) -> str:
    if index == 0 and visual_assets and scene.layout_hint in {"headline", "minimal", "split"}:
        return "full-bleed"
    if scene.layout_hint == "comparison" and not comparison_story:
        if category == "sports":
            return "split"
        return "headline"
    return scene.layout_hint


def enforce_scene_guardrails(
    scenes: list[VideoPlanScene],
    *,
    category: str,
    summary: str,
    key_points: list[str],
    visual_assets: list[VisualAsset],
    comparison_story: bool,
) -> list[VideoPlanScene]:
    if not scenes:
        return []

    preferred_scene_count = suggest_scene_count(
        summary,
        key_points,
        category=category,
        comparison_story=comparison_story,
    )
    adjusted: list[VideoPlanScene] = []
    for index, scene in enumerate(scenes):
        normalized_layout = normalize_scene_layout_hint(
            scene,
            index=index,
            category=category,
            comparison_story=comparison_story,
            visual_assets=visual_assets,
        )
        normalized_scene = scene.model_copy(
            update={
                "layout_hint": normalized_layout,
                "asset_ids": scene.asset_ids
                or default_asset_ids_for_scene(
                    index=index,
                    scene_count=len(scenes),
                    layout_hint=normalized_layout,
                    visual_assets=visual_assets,
                ),
            }
        )
        if adjusted and scene_similarity(normalized_scene, adjusted[-1]) >= 0.72:
            continue
        adjusted.append(normalized_scene)

    if not adjusted:
        adjusted = [scenes[0]]

    if len(adjusted) > 1:
        progression = scene_progression_score(adjusted)
        if preferred_scene_count == 1 or progression < 0.42:
            first_scene = adjusted[0].model_copy(
                update={
                    "layout_hint": normalize_scene_layout_hint(
                        adjusted[0],
                        index=0,
                        category=category,
                        comparison_story=comparison_story,
                        visual_assets=visual_assets,
                    ),
                    "body": adjusted[0].body
                    or adjusted[1].body
                    or summary,
                    "supporting_points": dedupe_preserve_order(
                        adjusted[0].supporting_points + adjusted[1].supporting_points
                    )[:2],
                    "asset_ids": adjusted[0].asset_ids
                    or default_asset_ids_for_scene(
                        index=0,
                        scene_count=1,
                        layout_hint=adjusted[0].layout_hint,
                        visual_assets=visual_assets,
                    ),
                }
            )
            return [first_scene]

    return adjusted[: max(1, min(4, preferred_scene_count if len(adjusted) > preferred_scene_count else len(adjusted)))]


def default_asset_ids_for_scene(
    *,
    index: int,
    scene_count: int,
    layout_hint: str,
    visual_assets: list[VisualAsset],
) -> list[str]:
    if not visual_assets:
        return []
    if scene_count == 1:
        return [visual_assets[0].asset_id]
    if index == 0:
        return [visual_assets[0].asset_id]
    if layout_hint == "split" and len(visual_assets) > 1:
        return [visual_assets[1].asset_id]
    if scene_count == 2 and index == 1 and len(visual_assets) > 1:
        return [visual_assets[1].asset_id]
    return []


def build_fallback_video_plan(
    cluster: list[PreparedArticle],
    *,
    category: str,
    headline: str,
    summary: str,
    key_points: list[str],
    why_it_matters: str,
    prompt_parts: VideoPromptParts,
    visual_assets: list[VisualAsset],
) -> VideoPlan:
    fact_pack = build_story_fact_pack(
        cluster,
        category=category,
        headline=headline,
        summary=summary,
        key_points=key_points,
    )
    entities = build_prompt_entities(
        cluster,
        headline=headline,
        summary=summary,
        key_points=key_points,
    )
    source_names = unique_source_names(cluster)
    clean_headline = trim_viewer_words(
            clean_viewer_text(headline, source_names=source_names, max_sentences=2, max_chars=2000) or headline,
            100,
    )
    clean_summary = clean_viewer_text(summary, source_names=source_names, max_sentences=3, max_chars=2000)
    clean_points = clean_viewer_points(key_points, source_names=source_names, max_items=2, max_chars=2000)
    clean_why_candidate = clean_viewer_text(
        why_it_matters,
        source_names=source_names,
        max_sentences=2,
        max_chars=2000,
    )
    clean_why = (
        clean_why_candidate
        if clean_why_candidate and not is_generic_why_line(clean_why_candidate)
        else build_why_it_matters_line(
            category,
            headline=clean_headline,
            summary=clean_summary or summary,
            key_points=clean_points,
            cluster=cluster,
        )
    )
    source_rules = cluster_analysis_rules(cluster)
    representative_url = cluster[0].article.url if cluster else ""
    key_figures = filter_informative_anchors(list(fact_pack.actors) or entities["names"], headline=clean_headline, max_items=4)
    key_data = (
        entities["score"]
        or (fact_pack.numeric_facts[0] if fact_pack.numeric_facts else "")
        or entities["numeric_phrase"]
        or ""
    )
    comparison_story = is_comparison_story(
        category=category,
        headline=clean_headline,
        summary=clean_summary or summary,
        key_points=clean_points,
        score=entities["score"],
    )
    story_subtype = infer_story_subtype(
        category=category,
        headline=clean_headline,
        url=representative_url,
        summary=clean_summary or summary,
        key_points=clean_points,
        comparison_story=comparison_story,
        rules=source_rules,
    )
    comparison_story = story_subtype == "matchup"
    duration_seconds = clamp_video_duration(prompt_parts.duration_seconds)
    scene_count = suggest_scene_count(
        clean_summary or summary,
        clean_points,
        category=category,
        comparison_story=comparison_story,
        duration_seconds=duration_seconds,
    )
    scene_durations = allocate_scene_durations(
        duration_seconds,
        scene_count,
        [4, 3, 2][:scene_count],
    )

    scenes: list[VideoPlanScene] = []

    hook_layout = default_layout_for_scene(
        category=category,
        purpose="hook",
        key_data=key_data,
        key_figures=key_figures,
        comparison_story=comparison_story,
        has_visual_assets=bool(visual_assets),
    )
    scenes.append(
        VideoPlanScene(
            scene_id="scene-1",
            purpose="hook",
            duration_seconds=scene_durations[0],
            layout_hint=hook_layout,
            headline=clean_headline,
            body=clean_summary or fact_pack.primary_event,
            voiceover=clean_summary or fact_pack.primary_event,
            supporting_points=[],
            key_figures=key_figures[:3],
            key_data=key_data,
            visual_direction=truncate_text(prompt_parts.visual_brief, 300),
            motion_direction=truncate_text(prompt_parts.motion_treatment, 300),
            transition_from_previous="Cold open",
            source_line="",
            asset_ids=default_asset_ids_for_scene(
                index=0,
                scene_count=scene_count,
                layout_hint=hook_layout,
                visual_assets=visual_assets,
            ),
        )
    )

    explain_candidate = next(
        (
            candidate
            for candidate in [fact_pack.supporting_fact, *clean_points, clean_why]
            if candidate and text_similarity(candidate, clean_headline) < 0.72
        ),
        "",
    )

    if scene_count >= 2 and explain_candidate:
        explain_layout = default_layout_for_scene(
            category=category,
            purpose="explain",
            key_data=key_data,
            key_figures=key_figures,
            comparison_story=comparison_story,
            has_visual_assets=bool(visual_assets),
        )
        explain_headline = trim_viewer_words(explain_candidate, 100)
        explain_body = (
            fact_pack.result_context
            if fact_pack.result_context and text_similarity(fact_pack.result_context, explain_headline) < 0.88
            else (
                clean_points[1]
                if len(clean_points) > 1 and text_similarity(clean_points[1], explain_headline) < 0.88
                else (clean_why if text_similarity(clean_why, clean_summary) < 0.88 else "")
            )
        )
        scenes.append(
            VideoPlanScene(
                scene_id="scene-2",
                purpose="explain",
                duration_seconds=scene_durations[1],
                layout_hint=explain_layout,
                headline=trim_viewer_words(explain_candidate, 100),
                body=explain_body,
                voiceover=explain_body or explain_candidate,
                supporting_points=clean_points[:2],
                key_figures=key_figures[:3],
                key_data=key_data if explain_layout == "stat" else "",
                visual_direction=truncate_text(prompt_parts.visual_brief, 300),
                motion_direction=truncate_text(prompt_parts.motion_treatment, 300),
                transition_from_previous=truncate_text(prompt_parts.transition_style, 200),
                source_line="",
                asset_ids=default_asset_ids_for_scene(
                    index=1,
                    scene_count=scene_count,
                    layout_hint=explain_layout,
                    visual_assets=visual_assets,
                ),
            )
        )

    impact_candidate = fact_pack.impact_fact or clean_why
    if scene_count >= 3 and impact_candidate and text_similarity(impact_candidate, clean_headline) < 0.72:
        takeaway_layout = default_layout_for_scene(
            category=category,
            purpose="takeaway",
            key_data="",
            key_figures=key_figures,
            comparison_story=comparison_story,
            has_visual_assets=bool(visual_assets),
        )
        scenes.append(
            VideoPlanScene(
                scene_id="scene-3",
                purpose="takeaway",
                duration_seconds=scene_durations[2],
                layout_hint=takeaway_layout,
                headline=trim_viewer_words(impact_candidate, 100),
                body=impact_candidate,
                voiceover=impact_candidate,
                supporting_points=[],
                key_figures=key_figures[:2],
                key_data="",
                visual_direction=truncate_text(prompt_parts.visual_brief, 300),
                motion_direction=truncate_text(prompt_parts.motion_treatment, 300),
                transition_from_previous=truncate_text(prompt_parts.transition_style, 200),
                source_line="",
                asset_ids=default_asset_ids_for_scene(
                    index=2,
                    scene_count=scene_count,
                    layout_hint=takeaway_layout,
                    visual_assets=visual_assets,
                ),
            )
        )

    scenes = enforce_scene_guardrails(
        scenes,
        category=category,
        summary=clean_summary or summary,
        key_points=clean_points,
        visual_assets=visual_assets,
        comparison_story=comparison_story,
    )
    duration_seconds = clamp_video_duration(
        min(duration_seconds, 12)
        if category == "sports" and not comparison_story and len(scenes) == 1
        else duration_seconds
    )
    scene_durations = allocate_scene_durations(duration_seconds, len(scenes), [scene.duration_seconds for scene in scenes])
    normalized_scenes = [
        scene.model_copy(update={"duration_seconds": scene_durations[index]})
        for index, scene in enumerate(scenes)
    ]

    return VideoPlan(
        title=truncate_viewer_text(clean_headline, 2000),
        audience_mode="sound_off_first",
        master_format="16:9",
        duration_seconds=duration_seconds,
        pacing_hint=infer_pacing_hint(duration_seconds, len(normalized_scenes)),
        source_visibility="none",
        scenes=normalized_scenes,
    )


def coerce_video_plan(
    data: dict[str, Any] | None,
    cluster: list[PreparedArticle],
    *,
    category: str,
    headline: str,
    summary: str,
    key_points: list[str],
    why_it_matters: str,
    prompt_parts: VideoPromptParts,
    visual_assets: list[VisualAsset],
) -> VideoPlan:
    fallback = build_fallback_video_plan(
        cluster,
        category=category,
        headline=headline,
        summary=summary,
        key_points=key_points,
        why_it_matters=why_it_matters,
        prompt_parts=prompt_parts,
        visual_assets=visual_assets,
    )
    if not isinstance(data, dict):
        return fallback

    raw_scenes = data.get("scenes")
    if not isinstance(raw_scenes, list):
        return fallback

    scene_candidates: list[VideoPlanScene] = []
    source_names = unique_source_names(cluster)
    valid_asset_ids = {asset.asset_id for asset in visual_assets}
    source_rules = cluster_analysis_rules(cluster)
    representative_url = cluster[0].article.url if cluster else ""
    comparison_story = is_comparison_story(
        category=category,
        headline=headline,
        summary=summary,
        key_points=key_points,
        score=extract_score([headline, summary, *key_points]),
    )
    comparison_story = (
        infer_story_subtype(
            category=category,
            headline=headline,
            url=representative_url,
            summary=summary,
            key_points=key_points,
            comparison_story=comparison_story,
            rules=source_rules,
        )
        == "matchup"
    )

    for index, item in enumerate(raw_scenes[:4]):
        if not isinstance(item, dict):
            continue
        purpose = compact_text(str(item.get("purpose", ""))).lower()
        layout_hint = compact_text(str(item.get("layout_hint", ""))).lower()
        headline_value = trim_viewer_words(
            clean_viewer_text(
                str(item.get("headline", "")),
                source_names=source_names,
                max_sentences=2,
                max_chars=2000,
            ),
            100,
        )
        if purpose not in VALID_VIDEO_PLAN_PURPOSES or layout_hint not in VALID_VIDEO_PLAN_LAYOUTS or not headline_value:
            continue
        supporting_points = clean_viewer_points(
            coerce_list(item.get("supporting_points")),
            source_names=source_names,
            max_items=2,
            max_chars=2000,
        )
        body_value = clean_viewer_text(
            str(item.get("body", "")),
            source_names=source_names,
            max_sentences=4,
            max_chars=2000,
        )
        voiceover_value = clean_viewer_text(
            str(item.get("voiceover", "")),
            source_names=source_names,
            max_sentences=4,
            max_chars=2000,
        )
        raw_asset_ids = coerce_list(item.get("asset_ids"))
        asset_ids = [asset_id for asset_id in raw_asset_ids if asset_id in valid_asset_ids][:2]
        scene_candidates.append(
            VideoPlanScene(
                scene_id=compact_text(str(item.get("scene_id", ""))) or f"scene-{index + 1}",
                purpose=purpose,
                duration_seconds=max(1, int(item.get("duration_seconds", 1) or 1)),
                layout_hint=layout_hint,
                headline=headline_value,
                body=body_value,
                voiceover=voiceover_value or body_value or headline_value,
                supporting_points=supporting_points,
                key_figures=filter_informative_anchors(
                    coerce_list(item.get("key_figures")),
                    headline=headline_value,
                    max_items=4,
                ),
                key_data=compact_text(str(item.get("key_data", ""))),
                visual_direction=compact_text(str(item.get("visual_direction", ""))),
                motion_direction=compact_text(str(item.get("motion_direction", ""))),
                transition_from_previous=compact_text(str(item.get("transition_from_previous", ""))),
                source_line=compact_text(str(item.get("source_line", ""))),
                asset_ids=asset_ids,
            )
        )

    if not scene_candidates:
        return fallback

    scene_candidates = enforce_scene_guardrails(
        scene_candidates,
        category=category,
        summary=summary,
        key_points=key_points,
        visual_assets=visual_assets,
        comparison_story=comparison_story,
    )

    requested_total = data.get("duration_seconds")
    if requested_total is None:
        requested_total = sum(scene.duration_seconds for scene in scene_candidates)
    total_duration = clamp_video_duration(int(requested_total or fallback.duration_seconds), fallback.duration_seconds)
    if category == "sports" and not comparison_story and len(scene_candidates) == 1:
        total_duration = min(total_duration, 12)
    normalized_durations = allocate_scene_durations(
        total_duration,
        len(scene_candidates),
        [scene.duration_seconds for scene in scene_candidates],
    )

    source_visibility = compact_text(str(data.get("source_visibility", ""))).lower()
    if source_visibility not in VALID_VIDEO_PLAN_SOURCE_VISIBILITY:
        source_visibility = fallback.source_visibility

    normalized_scenes: list[VideoPlanScene] = []
    for index, scene in enumerate(scene_candidates):
        normalized_scenes.append(
            VideoPlanScene(
                scene_id=scene.scene_id or f"scene-{index + 1}",
                purpose=scene.purpose,
                duration_seconds=normalized_durations[index],
                layout_hint=scene.layout_hint,
                headline=scene.headline,
                body=scene.body,
                voiceover=getattr(scene, "voiceover", scene.body),
                supporting_points=scene.supporting_points[:2],
                key_figures=scene.key_figures[:4],
                key_data=scene.key_data,
                visual_direction=scene.visual_direction,
                motion_direction=scene.motion_direction,
                transition_from_previous=scene.transition_from_previous,
                source_line=scene.source_line if source_visibility != "none" else "",
                asset_ids=scene.asset_ids
                or default_asset_ids_for_scene(
                    index=index,
                    scene_count=len(scene_candidates),
                    layout_hint=scene.layout_hint,
                    visual_assets=visual_assets,
                ),
            )
        )

    pacing_hint = compact_text(str(data.get("pacing_hint", ""))) or infer_pacing_hint(total_duration, len(normalized_scenes))
    title = compact_text(str(data.get("title", ""))) or fallback.title

    return VideoPlan(
        title=title,
        audience_mode="sound_off_first",
        master_format="16:9",
        duration_seconds=total_duration,
        pacing_hint=pacing_hint,
        source_visibility=source_visibility,
        scenes=normalized_scenes,
    )


def build_video_content_from_plan(
    plan: VideoPlan,
    cluster: list[PreparedArticle] | None = None,
    *,
    summary: str = "",
    key_points: list[str] | None = None,
    why_it_matters: str = "",
) -> VideoContent:
    source_names = unique_source_names(cluster) if cluster else []

    # --- narrative: prefer article detail_text over scene bodies ---
    article_sentences: list[str] = []
    if cluster:
        for item in cluster[:3]:
            detail = compact_text(item.detail_text)
            if detail:
                sentence = clean_viewer_text(detail, source_names=source_names, max_sentences=2, max_chars=2000)
                if sentence:
                    article_sentences.append(sentence)

    scene_sentences = [
        clean_viewer_text(scene.body or scene.headline, max_sentences=2, max_chars=2000)
        for scene in plan.scenes
        if compact_text(scene.body or scene.headline)
    ]

    # Build narrative: opening from summary/detail, middle from key_points/scenes, closing from why_it_matters
    raw_narrative: list[str] = []
    opening = clean_viewer_text(summary, source_names=source_names, max_sentences=2, max_chars=2000) if summary else ""
    if opening:
        raw_narrative.append(opening)
    elif article_sentences:
        raw_narrative.append(article_sentences[0])
    elif scene_sentences:
        raw_narrative.append(scene_sentences[0])

    middle_candidates = (key_points or []) + article_sentences[1:] + scene_sentences
    for candidate in middle_candidates:
        cleaned = clean_viewer_text(candidate, source_names=source_names, max_sentences=2, max_chars=2000)
        if cleaned and cleaned not in raw_narrative:
            raw_narrative.append(cleaned)
            break

    closing = clean_viewer_text(why_it_matters, source_names=source_names, max_sentences=2, max_chars=2000) if why_it_matters else ""
    if closing and closing not in raw_narrative:
        raw_narrative.append(closing)

    narrative = dedupe_preserve_order(raw_narrative)[:3]
    if not narrative:
        narrative = dedupe_preserve_order(scene_sentences)[:3]

    # --- key_figures: combine scene figures with article-derived entities ---
    scene_figures = dedupe_preserve_order([figure for scene in plan.scenes for figure in scene.key_figures])
    if cluster:
        entities = build_prompt_entities(
            cluster,
            headline=plan.title,
            summary=summary,
            key_points=key_points or [],
        )
        all_figures = dedupe_preserve_order(scene_figures + entities["names"])
    else:
        all_figures = scene_figures
    key_figures = filter_informative_anchors(all_figures, headline=plan.title, max_items=4)

    key_data = next((compact_text(scene.key_data) for scene in plan.scenes if compact_text(scene.key_data)), "")

    # --- source_line: build from actual sources ---
    if source_names:
        source_line = f"{len(source_names)} {'source' if len(source_names) == 1 else 'sources'} · {', '.join(source_names[:3])}"
    else:
        source_line = ""

    return VideoContent(
        headline=plan.title,
        narrative=narrative,
        key_figures=key_figures,
        key_data=key_data,
        source_line=source_line,
        duration_seconds=plan.duration_seconds,
    )


def make_storyboard_stat(label: str, value: str) -> RemotionStat:
    return RemotionStat(label=truncate_text(label, 24), value=truncate_text(value, 24))


def build_remotion_storyboard_context(
    cluster: list[PreparedArticle],
    *,
    category: str,
    headline: str,
    summary: str,
    key_points: list[str],
    why_it_matters: str,
    prompt_parts: VideoPromptParts,
    prompt_text: str,
    video_plan: VideoPlan,
    visual_assets: list[VisualAsset],
) -> RemotionStoryboardContext:
    entities = build_prompt_entities(
        cluster,
        headline=headline,
        summary=summary,
        key_points=key_points,
    )
    sources = unique_source_names(cluster)
    representative_titles = [truncate_text(item.article.title, 140) for item in cluster[:4]]
    facts = dedupe_preserve_order(
        ([entities["score"]] if entities["score"] else [])
        + entities["names"][:3]
        + [truncate_text(item, 80) for item in prompt_parts.must_include[:3]]
    )[:5]

    stats: list[RemotionStat] = [make_storyboard_stat("Runtime", f"{video_plan.duration_seconds}s")]
    if video_plan.scenes:
        stats.append(make_storyboard_stat("Scenes", str(len(video_plan.scenes))))
    stats.append(make_storyboard_stat("Pacing", video_plan.pacing_hint))
    stats.append(make_storyboard_stat("Format", video_plan.master_format))

    return RemotionStoryboardContext(
        category=category,
        headline=headline,
        summary=summary,
        key_points=key_points,
        why_it_matters=why_it_matters,
        prompt_text=prompt_text,
        prompt_parts=prompt_parts,
        sources=sources,
        representative_titles=representative_titles,
        facts=facts,
        style_cues=[
            truncate_text(prompt_parts.format_hint, 200),
            truncate_text(prompt_parts.visual_brief, 300),
            truncate_text(prompt_parts.motion_treatment, 300),
            truncate_text(prompt_parts.transition_style, 200),
        ],
        stats=stats[:4],
        article_count=len(cluster),
        video_plan=video_plan,
        video_content=build_video_content_from_plan(
            video_plan,
            cluster,
            summary=summary,
            key_points=key_points,
            why_it_matters=why_it_matters,
        ),
        visual_assets=visual_assets,
    )


def prepared_summary_candidate(item: PreparedArticle) -> str:
    return compact_text(item.detail_text) or compact_text(item.cluster_text) or compact_text(item.article.title)


def prepared_key_point_candidate(item: PreparedArticle) -> str:
    title = compact_text(item.article.title)
    if title and not looks_broken_title(title):
        return title

    detail_line = extract_lead_sentences(
        item.detail_text or item.cluster_text,
        title=item.article.title,
        max_sentences=1,
        max_chars=96,
    )
    return detail_line or title or compact_text(item.cluster_text) or compact_text(item.article.title)


def build_fallback_topic(
    cluster: list[PreparedArticle],
    visual_assets: list[VisualAsset],
    *,
    aggregation_type: str = "shared",
) -> TopicBrief | None:
    unique_sources = unique_source_names(cluster)
    if not cluster:
        return None
    if aggregation_type == "shared" and len(unique_sources) < settings.ANALYSIS_MIN_SHARED_SOURCES:
        return None

    representative = cluster[0]
    category = representative.normalized_category
    source_names = unique_sources
    fact_pack = build_story_fact_pack(
        cluster,
        category=category,
        headline=representative.article.title,
        summary=prepared_summary_candidate(representative),
        key_points=[item.article.title for item in cluster[:2]],
    )

    # Pick the shortest, most direct title as headline
    titles = [item.article.title for item in cluster if item.article.title]
    headline_tr = clean_viewer_text(min(titles, key=len) if titles else representative.article.title, source_names=source_names, max_sentences=2, max_chars=2000)
    headline_tr = trim_viewer_words(headline_tr or representative.article.title, 100)

    cleaned_summaries = dedupe_preserve_order(
        [
            clean_viewer_text(
                prepared_summary_candidate(item),
                source_names=source_names,
                max_sentences=3,
                max_chars=2000,
            )
            for item in cluster[:3]
        ]
    )
    summary_tr = " ".join(cleaned_summaries[:2]) or headline_tr
    if has_thin_summary(summary_tr):
        raw_summary_candidates = dedupe_preserve_order(
            [
                    truncate_text(compact_text(prepared_summary_candidate(item)), 200)
                for item in cluster[:3]
                if compact_text(prepared_summary_candidate(item))
            ]
        )
        for candidate in raw_summary_candidates:
            if len(tokenize(candidate, max_tokens=80)) >= 6:
                summary_tr = candidate
                break

    key_points_tr = clean_viewer_points(
        [prepared_key_point_candidate(item) for item in cluster[:3]],
        source_names=source_names,
        max_items=2,
        max_chars=2000,
    )
    why_it_matters_tr = build_why_it_matters_line(
        category,
        headline=headline_tr,
        summary=summary_tr,
        key_points=key_points_tr,
        cluster=cluster,
    )

    prompt_parts = build_fallback_prompt_parts(
        cluster,
        category=category,
        headline=headline_tr,
        summary=summary_tr,
        key_points=key_points_tr,
        why_it_matters=why_it_matters_tr,
    )
    human_prompt_en = build_video_prompt_from_parts(prompt_parts, category=category)
    video_plan = build_fallback_video_plan(
        cluster,
        category=category,
        headline=headline_tr,
        summary=summary_tr,
        key_points=key_points_tr,
        why_it_matters=why_it_matters_tr,
        prompt_parts=prompt_parts,
        visual_assets=visual_assets,
    )
    video_content = build_video_content_from_plan(
        video_plan,
        cluster,
        summary=summary_tr,
        key_points=key_points_tr,
        why_it_matters=why_it_matters_tr,
    )

    # Enrich fallback narrative with diverse source titles when narrative is weak
    if len(video_content.narrative) < 2 and len(cluster) >= 2:
        seen_sources: set[str] = set()
        title_narrative: list[str] = []
        for item in cluster:
            if item.source_slug not in seen_sources:
                seen_sources.add(item.source_slug)
                cleaned_title = clean_viewer_text(
                    item.article.title,
                    source_names=source_names,
                    max_sentences=1,
                    max_chars=120,
                )
                if cleaned_title and cleaned_title not in title_narrative:
                    title_narrative.append(cleaned_title)
            if len(title_narrative) >= 3:
                break
        if len(title_narrative) > len(video_content.narrative):
            video_content.narrative = title_narrative[:3]

    remotion_context = build_remotion_storyboard_context(
        cluster,
        category=category,
        headline=headline_tr,
        summary=summary_tr,
        key_points=key_points_tr,
        why_it_matters=why_it_matters_tr,
        prompt_parts=prompt_parts,
        prompt_text=human_prompt_en,
        video_plan=video_plan,
        visual_assets=visual_assets,
    )
    remotion_storyboard = RemotionStoryboardService().build_storyboard(remotion_context)

    if topic_render_rejection_reason(
        aggregation_type=aggregation_type,
        headline=headline_tr,
        summary=summary_tr,
        key_points=key_points_tr,
    ):
        return None

    topic = TopicBrief(
        topic_id=build_topic_id(cluster),
        category=category,
        aggregation_type=aggregation_type,
        story_language=fact_pack.story_language,
        editorial_type=fact_pack.editorial_type,
        headline_tr=headline_tr,
        summary_tr=summary_tr,
        key_points_tr=key_points_tr,
        why_it_matters_tr=why_it_matters_tr,
        confidence=0.45,
        source_count=len(unique_sources),
        article_count=len(cluster),
        sources=unique_sources,
        representative_articles=build_representative_articles(cluster),
        visual_assets=visual_assets,
        video_prompt_en=human_prompt_en,
        video_prompt_parts=prompt_parts,
        video_plan=video_plan,
        video_content=video_content,
        remotion_storyboard=remotion_storyboard,
    )
    if topic_render_rejection_reason(
        aggregation_type=aggregation_type,
        headline=topic.headline_tr,
        summary=topic.summary_tr,
        key_points=topic.key_points_tr,
    ):
        return None
    return topic


def build_topic_id(cluster: list[PreparedArticle]) -> str:
    article_ids = "|".join(sorted(str(item.article.id) for item in cluster))
    return hashlib.sha1(article_ids.encode()).hexdigest()[:16]


def cluster_source_count(cluster: list[PreparedArticle]) -> int:
    return len({item.source_slug for item in cluster})


def is_shared_cluster(cluster: list[PreparedArticle]) -> bool:
    return cluster_source_count(cluster) >= settings.ANALYSIS_MIN_SHARED_SOURCES


def unique_source_names(cluster: list[PreparedArticle]) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for item in cluster:
        if item.source_slug not in seen:
            seen.add(item.source_slug)
            names.append(item.source_name)
    return names


def unique_source_slugs(cluster: list[PreparedArticle]) -> list[str]:
    seen: set[str] = set()
    slugs: list[str] = []
    for item in cluster:
        if item.source_slug not in seen:
            seen.add(item.source_slug)
            slugs.append(item.source_slug)
    return slugs


def partition_clusters(
    prepared_articles: list[PreparedArticle],
    candidate_clusters: list[list[PreparedArticle]],
) -> tuple[list[list[PreparedArticle]], list[list[PreparedArticle]], list[list[PreparedArticle]]]:
    clustered_article_ids = {
        str(item.article.id)
        for cluster in candidate_clusters
        for item in cluster
    }
    shared_clusters = [cluster for cluster in candidate_clusters if is_shared_cluster(cluster)]
    unique_clusters = [cluster for cluster in candidate_clusters if not is_shared_cluster(cluster)]
    singleton_clusters = [
        [article]
        for article in prepared_articles
        if str(article.article.id) not in clustered_article_ids
    ]
    return shared_clusters, unique_clusters, singleton_clusters


def build_representative_articles(cluster: list[PreparedArticle]) -> list[TopicRepresentativeArticle]:
    representatives: list[TopicRepresentativeArticle] = []
    seen_sources: set[str] = set()
    for item in cluster:
        if item.source_slug in seen_sources:
            continue
        seen_sources.add(item.source_slug)
        representatives.append(
            TopicRepresentativeArticle(
                id=item.article.id,
                title=item.article.title,
                url=item.article.url,
                source_name=item.source_name,
                source_slug=item.source_slug,
                published_at=item.timestamp,
                image_url=item.article.image_url,
            )
        )
        if len(representatives) >= 3:
            break
    return representatives


def build_analysis_debug(
    *,
    articles: list[Article],
    prepared_articles: list[PreparedArticle],
    candidate_clusters: list[list[PreparedArticle]],
    topic_entries: list[TopicAnalysisEntry] | None = None,
    rejections: list[AnalysisRejection] | None = None,
    notes: list[str] | None = None,
    ollama_error: str | None = None,
    shared_topics_generated: int = 0,
    unique_topics_generated: int = 0,
    rejected_unique_candidates: int = 0,
    dropped_unique_articles: int = 0,
) -> AnalysisDebug:
    source_counter: dict[tuple[str, str], int] = defaultdict(int)
    for article in articles:
        source = article.source
        source_counter[(source.slug if source else "unknown", source.name if source else "Unknown Source")] += 1

    source_breakdown = [
        AnalysisSourceDebug(
            source_slug=source_slug,
            source_name=source_name,
            article_count=count,
        )
        for (source_slug, source_name), count in sorted(
            source_counter.items(),
            key=lambda item: (-item[1], item[0][0]),
        )[:10]
    ]

    cluster_previews = [
        AnalysisClusterDebug(
            category=cluster[0].normalized_category if cluster else "general",
            article_count=len(cluster),
            source_count=len({item.source_slug for item in cluster}),
            sources=unique_source_names(cluster),
            sample_titles=[truncate_text(item.article.title, 96) for item in cluster[:3]],
        )
        for cluster in candidate_clusters[:8]
    ]

    single_source_clusters = sum(1 for cluster in candidate_clusters if not is_shared_cluster(cluster))
    multi_source_clusters = len(candidate_clusters) - single_source_clusters
    rejection_counts: dict[str, int] = defaultdict(int)
    for rejection in rejections or []:
        rejection_counts[rejection.reason] += 1
    review_counts: dict[str, int] = defaultdict(int)
    video_review_counts: dict[str, int] = defaultdict(int)
    for entry in topic_entries or []:
        for reason in entry.review_reasons:
            review_counts[reason] += 1
        for reason in entry.video_review_reasons:
            video_review_counts[reason] += 1

    publishable_topics_generated = sum(
        1 for entry in (topic_entries or []) if entry.quality_status == "publishable"
    )
    review_topics_generated = sum(
        1 for entry in (topic_entries or []) if entry.quality_status == "review"
    )
    video_publishable_topics_generated = sum(
        1 for entry in (topic_entries or []) if entry.video_quality_status == "publishable"
    )
    video_review_topics_generated = sum(
        1 for entry in (topic_entries or []) if entry.video_quality_status == "review"
    )
    video_rejected_topics_generated = sum(
        1 for entry in (topic_entries or []) if entry.video_quality_status == "reject"
    )

    return AnalysisDebug(
        fetched_articles=len(articles),
        prepared_articles=len(prepared_articles),
        rejected_articles=sum(1 for rejection in (rejections or []) if rejection.stage == "article"),
        candidate_clusters=len(candidate_clusters),
        multi_source_clusters=multi_source_clusters,
        single_source_clusters=single_source_clusters,
        shared_topics_generated=shared_topics_generated,
        unique_topics_generated=unique_topics_generated,
        publishable_topics_generated=publishable_topics_generated,
        review_topics_generated=review_topics_generated,
        video_publishable_topics_generated=video_publishable_topics_generated,
        video_review_topics_generated=video_review_topics_generated,
        video_rejected_topics_generated=video_rejected_topics_generated,
        rejected_unique_candidates=rejected_unique_candidates,
        dropped_unique_articles=dropped_unique_articles,
        source_breakdown=source_breakdown,
        cluster_previews=cluster_previews,
        rejection_breakdown=[
            AnalysisRejectionDebug(reason=reason, count=count)
            for reason, count in sorted(rejection_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        review_breakdown=[
            AnalysisReviewDebug(reason=reason, count=count)
            for reason, count in sorted(review_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        video_review_breakdown=[
            AnalysisReviewDebug(reason=reason, count=count)
            for reason, count in sorted(video_review_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        notes=notes or [],
        ollama_base_url=settings.OLLAMA_BASE_URL,
        ollama_error=ollama_error,
    )


def coerce_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [compact_text(str(item)) for item in value if compact_text(str(item))]
    if isinstance(value, str) and compact_text(value):
        return [compact_text(value)]
    return []


def coerce_prompt_parts(
    data: dict[str, Any] | None,
    cluster: list[PreparedArticle],
    *,
    category: str,
    headline: str,
    summary: str,
    key_points: list[str],
    why_it_matters: str,
) -> VideoPromptParts:
    fallback = build_fallback_prompt_parts(
        cluster,
        category=category,
        headline=headline,
        summary=summary,
        key_points=key_points,
        why_it_matters=why_it_matters,
    )
    if not isinstance(data, dict):
        return fallback

    scene_sequence = coerce_list(data.get("scene_sequence")) or fallback.scene_sequence
    design_keywords = coerce_list(data.get("design_keywords")) or fallback.design_keywords
    must_include = coerce_list(data.get("must_include")) or fallback.must_include
    avoid = coerce_list(data.get("avoid")) or fallback.avoid

    try:
        duration_seconds = int(data.get("duration_seconds", fallback.duration_seconds))
    except (TypeError, ValueError):
        duration_seconds = fallback.duration_seconds

    story_angle = compact_text(str(data.get("story_angle") or fallback.story_angle))
    format_hint = compact_text(str(data.get("format_hint") or fallback.format_hint))
    visual_brief = compact_text(str(data.get("visual_brief") or fallback.visual_brief))
    motion_treatment = compact_text(str(data.get("motion_treatment") or fallback.motion_treatment))
    transition_style = compact_text(str(data.get("transition_style") or fallback.transition_style))
    tone = compact_text(str(data.get("tone") or fallback.tone))

    return VideoPromptParts(
        format_hint=format_hint or fallback.format_hint,
        story_angle=fallback.story_angle if looks_generic_prompt_component(story_angle) else story_angle,
        visual_brief=fallback.visual_brief if looks_generic_prompt_component(visual_brief) else visual_brief,
        motion_treatment=motion_treatment or fallback.motion_treatment,
        transition_style=transition_style or fallback.transition_style,
        scene_sequence=scene_sequence[:4] if len(scene_sequence) >= 2 else fallback.scene_sequence,
        tone=tone or fallback.tone,
        design_keywords=design_keywords[:6] or fallback.design_keywords,
        must_include=must_include[:5],
        avoid=avoid[:5],
        duration_seconds=max(8, min(30, duration_seconds)),
    )


def coerce_story_fact_pack(
    data: dict[str, Any] | None,
    cluster: list[PreparedArticle],
    *,
    category: str,
    headline: str,
    summary: str,
    key_points: list[str],
) -> StoryFactPack:
    fallback = build_story_fact_pack(
        cluster,
        category=category,
        headline=headline,
        summary=summary,
        key_points=key_points,
    )
    if not isinstance(data, dict):
        return fallback

    def _coerce_text(key: str, fallback_value: str) -> str:
        return compact_text(str(data.get(key) or fallback_value))

    def _coerce_tuple(key: str, fallback_values: tuple[str, ...], *, max_items: int = 4) -> tuple[str, ...]:
        values = tuple(coerce_list(data.get(key)))[:max_items]
        return values or fallback_values

    story_domain = compact_text(str(data.get("story_domain") or fallback.story_domain)).lower() or fallback.story_domain
    if story_domain not in SAFE_ANGLE_TYPES_BY_DOMAIN:
        story_domain = fallback.story_domain

    return StoryFactPack(
        core_event=_coerce_text("core_event", fallback.core_event or fallback.primary_event),
        primary_event=_coerce_text("core_event", fallback.primary_event),
        supporting_fact=_coerce_text("supporting_facts", fallback.supporting_fact)
        if isinstance(data.get("supporting_facts"), str)
        else fallback.supporting_fact,
        supporting_facts=_coerce_tuple("supporting_facts", fallback.supporting_facts, max_items=4),
        trigger_or_setup=_coerce_text("trigger_or_setup", fallback.trigger_or_setup),
        impact_or_next=_coerce_text("impact_or_next", fallback.impact_or_next or fallback.impact_fact),
        impact_fact=_coerce_text("impact_or_next", fallback.impact_fact),
        evidence_points=_coerce_tuple("evidence_points", fallback.evidence_points, max_items=3),
        numeric_facts=_coerce_tuple("numeric_facts", fallback.numeric_facts, max_items=4),
        actors=_coerce_tuple("actors", fallback.actors, max_items=5),
        institution=_coerce_text("institution", fallback.institution),
        result_context=_coerce_text("result_context", fallback.result_context),
        legal_consequence=_coerce_text("legal_consequence", fallback.legal_consequence),
        allegation_frame=_coerce_text("allegation_frame", fallback.allegation_frame),
        story_domain=story_domain,
        uncertainty_level=_coerce_text("uncertainty_level", fallback.uncertainty_level) or fallback.uncertainty_level,
        story_language=_coerce_text("story_language", fallback.story_language) or fallback.story_language,
        editorial_type=_coerce_text("editorial_type", fallback.editorial_type) or fallback.editorial_type,
    )


def coerce_angle_plan_scenes(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    scenes: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        headline = compact_text(str(item.get("headline", "")))
        body = compact_text(str(item.get("body", "")))
        voiceover = compact_text(str(item.get("voiceover", "")))
        if not headline and not body:
            continue
        try:
            start_second = max(0, int(item.get("start_second", 0) or 0))
        except (TypeError, ValueError):
            start_second = 0
        try:
            duration_seconds = max(2, int(item.get("duration_seconds", 4) or 4))
        except (TypeError, ValueError):
            duration_seconds = 4
        scenes.append(
            {
                "id": compact_text(str(item.get("id", ""))) or f"scene-{index + 1}",
                "start_second": start_second,
                "duration_seconds": duration_seconds,
                "headline": headline,
                "body": body,
                "voiceover": voiceover,
                "visual_direction": compact_text(str(item.get("visual_direction", ""))),
                "motion_direction": compact_text(str(item.get("motion_direction", ""))),
                "transition": compact_text(str(item.get("transition", ""))),
            }
        )
    return scenes[:4]


def coerce_angle_plans(
    data: Any,
    *,
    story_domain: str,
) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    allowed_types = SAFE_ANGLE_TYPES_BY_DOMAIN.get(story_domain, SAFE_ANGLE_TYPES_BY_DOMAIN["general"])
    normalized: list[dict[str, Any]] = []
    seen_types: set[str] = set()
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        angle_type = compact_text(str(item.get("angle_type", ""))).lower() or allowed_types[min(index, len(allowed_types) - 1)]
        if angle_type not in allowed_types or angle_type in seen_types:
            continue
        scenes = coerce_angle_plan_scenes(item.get("scenes"))
        if not scenes:
            continue
        seen_types.add(angle_type)
        normalized.append(
            {
                "angle_id": compact_text(str(item.get("angle_id", ""))) or angle_type,
                "angle_type": angle_type,
                "title": compact_text(str(item.get("title", ""))),
                "hook": compact_text(str(item.get("hook", ""))),
                "duration_seconds": max(
                    8,
                    min(
                        30,
                        int(item.get("duration_seconds", sum(scene["duration_seconds"] for scene in scenes)) or 12),
                    ),
                ),
                "tone": compact_text(str(item.get("tone", ""))),
                "angle_rationale": compact_text(str(item.get("angle_rationale", ""))),
                "scenes": scenes,
            }
        )
    return normalized[:2]


def angle_scene_texts(angle_plan: dict[str, Any]) -> list[str]:
    return [
        compact_text(value)
        for scene in angle_plan.get("scenes", [])
        for value in (scene.get("headline"), scene.get("body"), scene.get("voiceover"))
        if compact_text(value)
    ]


def angle_signature(angle_plan: dict[str, Any]) -> str:
    values = [angle_plan.get("title"), angle_plan.get("hook"), *angle_scene_texts(angle_plan)]
    return compact_text(" ".join(str(value) for value in values if compact_text(str(value)))).lower()


def angle_plans_are_distinct(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if compact_text(str(left.get("angle_type"))) != compact_text(str(right.get("angle_type"))):
        signature_similarity = text_similarity(angle_signature(left), angle_signature(right))
        return signature_similarity < 0.82
    return False


def summarize_angle_plan(angle_plan: dict[str, Any]) -> str:
    scene_heads = [compact_text(str(scene.get("headline", ""))) for scene in angle_plan.get("scenes", []) if compact_text(str(scene.get("headline", "")))]
    summary_bits = [compact_text(str(angle_plan.get("title", "")))] + scene_heads[:2]
    return " | ".join(bit for bit in summary_bits if bit)


def angle_priority_index(*, story_domain: str, angle_type: str) -> int:
    priorities = ANGLE_PRIORITY_BY_DOMAIN.get(story_domain, ANGLE_PRIORITY_BY_DOMAIN["general"])
    try:
        return priorities.index(angle_type)
    except ValueError:
        return len(priorities)


def output_mentions_fact(output_corpus: str, fact: str) -> bool:
    normalized_fact = compact_text(fact).lower()
    if not normalized_fact:
        return False
    if normalized_fact in output_corpus:
        return True
    key_tokens = [token for token in tokenize(normalized_fact, max_tokens=12) if len(token) >= 4 and token not in STOPWORDS]
    if not key_tokens:
        return False
    token_hits = sum(1 for token in key_tokens if re.search(rf"\b{re.escape(token)}\b", output_corpus))
    return token_hits >= max(1, min(2, len(key_tokens)))


def infer_angle_prompt_format_hint(*, story_domain: str, angle_type: str) -> str:
    label = ANGLE_LABELS.get(angle_type, "editorial explainer")
    if story_domain == "sports":
        return f"Premium social-first {label}"
    if story_domain == "crime_justice":
        return f"Editorial breaking-news {label}"
    if story_domain == "diplomacy":
        return f"Global affairs {label}"
    if story_domain == "business":
        return f"Premium business {label}"
    if story_domain == "science":
        return f"Science explainer {label}"
    return f"Editorial {label}"


def build_prompt_parts_from_angle_plan(
    angle_plan: dict[str, Any],
    *,
    cluster: list[PreparedArticle],
    category: str,
    headline: str,
    summary: str,
    key_points: list[str],
    why_it_matters: str,
    fact_pack: StoryFactPack,
) -> VideoPromptParts:
    fallback = build_fallback_prompt_parts(
        cluster,
        category=category,
        headline=headline,
        summary=summary,
        key_points=key_points,
        why_it_matters=why_it_matters,
    )
    scenes = angle_plan.get("scenes", [])
    visual_brief = compact_text(" ".join(scene.get("visual_direction", "") for scene in scenes if compact_text(scene.get("visual_direction", ""))))
    motion_treatment = compact_text(" ".join(scene.get("motion_direction", "") for scene in scenes if compact_text(scene.get("motion_direction", ""))))
    transition_style = compact_text(" ".join(scene.get("transition", "") for scene in scenes if compact_text(scene.get("transition", ""))))
    must_include = filter_informative_anchors(
        dedupe_preserve_order(
            list(fact_pack.actors[:3])
            + ([fact_pack.institution] if fact_pack.institution else [])
            + list(fact_pack.numeric_facts[:2])
        ),
        headline=headline,
        max_items=5,
    )
    return VideoPromptParts(
        format_hint=infer_angle_prompt_format_hint(
            story_domain=fact_pack.story_domain,
            angle_type=str(angle_plan.get("angle_type", "")),
        ),
        story_angle=compact_text(str(angle_plan.get("hook", ""))) or fallback.story_angle,
        visual_brief=visual_brief or fallback.visual_brief,
        motion_treatment=motion_treatment or fallback.motion_treatment,
        transition_style=transition_style or fallback.transition_style,
        scene_sequence=[compact_text(str(scene.get("headline", ""))) for scene in scenes if compact_text(str(scene.get("headline", "")))] or fallback.scene_sequence,
        tone=compact_text(str(angle_plan.get("tone", ""))) or fallback.tone,
        design_keywords=fallback.design_keywords,
        must_include=must_include or fallback.must_include,
        avoid=fallback.avoid,
        duration_seconds=max(8, min(30, int(angle_plan.get("duration_seconds", fallback.duration_seconds) or fallback.duration_seconds))),
    )


def derive_topic_copy_from_angle_plan(
    angle_plan: dict[str, Any],
    *,
    cluster: list[PreparedArticle],
    fact_pack: StoryFactPack,
    fallback_topic: TopicBrief,
) -> tuple[str, str, list[str], str]:
    source_names = unique_source_names(cluster)
    scenes = angle_plan.get("scenes", [])
    headline_candidate = (
        compact_text(str(angle_plan.get("title", "")))
        or compact_text(str(angle_plan.get("hook", "")))
        or compact_text(str(scenes[0].get("headline", "")) if scenes else "")
        or fact_pack.core_event
        or fallback_topic.headline_tr
    )
    headline = clean_viewer_text(headline_candidate, source_names=source_names, max_sentences=2, max_chars=2000) or fallback_topic.headline_tr
    headline = trim_viewer_words(headline, 100)

    summary_candidates = [
        compact_text(str(angle_plan.get("hook", ""))),
        *[compact_text(str(scene.get("body", ""))) for scene in scenes[:2]],
        fact_pack.core_event,
        fact_pack.trigger_or_setup,
    ]
    summary_lines = [
        clean_viewer_text(value, source_names=source_names, max_sentences=3, max_chars=2000)
        for value in summary_candidates
        if compact_text(value)
    ]
    summary = " ".join(dedupe_preserve_order([line for line in summary_lines if line])[:2]) or fallback_topic.summary_tr

    key_point_candidates = list(fact_pack.supporting_facts) + [
        fact_pack.trigger_or_setup,
        fact_pack.impact_or_next,
        fact_pack.result_context,
        fact_pack.legal_consequence,
    ]
    key_points = clean_viewer_points(
        key_point_candidates,
        source_names=source_names,
        max_items=3,
        max_chars=2000,
    ) or fallback_topic.key_points_tr

    why_candidate = ""
    for candidate in (
        fact_pack.impact_or_next,
        fact_pack.legal_consequence,
        fact_pack.result_context,
        compact_text(str(scenes[-1].get("body", ""))) if scenes else "",
        fallback_topic.why_it_matters_tr,
    ):
        cleaned = clean_viewer_text(candidate, source_names=source_names, max_sentences=2, max_chars=2000)
        if cleaned and text_similarity(cleaned, headline) < 0.9:
            why_candidate = cleaned
            break
    return headline, summary, key_points, why_candidate or fallback_topic.why_it_matters_tr


def infer_scene_purpose(
    *,
    index: int,
    scene_count: int,
    scene_text: str,
    fact_pack: StoryFactPack,
) -> str:
    lowered = compact_text(scene_text).lower()
    if index == 0:
        return "hook"
    if index == scene_count - 1 and (
        output_mentions_fact(lowered, fact_pack.impact_or_next)
        or output_mentions_fact(lowered, fact_pack.legal_consequence)
    ):
        return "takeaway"
    if output_mentions_fact(lowered, fact_pack.result_context):
        return "context"
    if index >= 2:
        return "detail"
    return "explain"


def infer_scene_layout_hint(*, index: int, scene_count: int, scene_text: str) -> str:
    if index == 0:
        return "full-bleed"
    if scene_count == 2 and index == 1:
        return "split"
    if len(compact_text(scene_text)) <= 48:
        return "headline"
    return "split"


def build_video_plan_data_from_angle_plan(
    angle_plan: dict[str, Any],
    *,
    fact_pack: StoryFactPack,
) -> dict[str, Any]:
    scenes = angle_plan.get("scenes", [])
    video_plan_scenes: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes):
        scene_text = " ".join(
            compact_text(str(value))
            for value in (scene.get("headline"), scene.get("body"), scene.get("voiceover"))
            if compact_text(str(value))
        )
        video_plan_scenes.append(
            {
                "scene_id": compact_text(str(scene.get("id", ""))) or f"scene-{index + 1}",
                "purpose": infer_scene_purpose(
                    index=index,
                    scene_count=len(scenes),
                    scene_text=scene_text,
                    fact_pack=fact_pack,
                ),
                "duration_seconds": max(2, int(scene.get("duration_seconds", 4) or 4)),
                "layout_hint": infer_scene_layout_hint(index=index, scene_count=len(scenes), scene_text=scene_text),
                "headline": compact_text(str(scene.get("headline", ""))),
                "body": compact_text(str(scene.get("body", ""))),
                "supporting_points": [],
                "key_figures": list(fact_pack.actors[:4]),
                "key_data": next((fact for fact in fact_pack.numeric_facts if output_mentions_fact(scene_text.lower(), fact)), ""),
                "visual_direction": compact_text(str(scene.get("visual_direction", ""))),
                "motion_direction": compact_text(str(scene.get("motion_direction", ""))),
                "transition_from_previous": compact_text(str(scene.get("transition", ""))) or ("Cold open" if index == 0 else "Cut"),
                "source_line": "",
                "asset_ids": [],
            }
        )
    return {
        "title": compact_text(str(angle_plan.get("title", ""))),
        "duration_seconds": max(8, min(30, int(angle_plan.get("duration_seconds", 12) or 12))),
        "pacing_hint": compact_text(str(angle_plan.get("tone", ""))) or infer_pacing_hint(
            max(8, min(30, int(angle_plan.get("duration_seconds", 12) or 12))),
            max(1, len(video_plan_scenes)),
        ),
        "source_visibility": "none",
        "scenes": video_plan_scenes,
    }


def build_topic_from_angle_plan_payload(
    cluster: list[PreparedArticle],
    angle_plan: dict[str, Any],
    fact_pack: StoryFactPack,
    visual_assets: list[VisualAsset],
    *,
    aggregation_type: str,
) -> TopicBrief | None:
    fallback_topic = build_fallback_topic(cluster, visual_assets, aggregation_type=aggregation_type)
    if fallback_topic is None:
        return None
    category = cluster[0].normalized_category
    headline_tr, summary_tr, key_points_tr, why_it_matters_tr = derive_topic_copy_from_angle_plan(
        angle_plan,
        cluster=cluster,
        fact_pack=fact_pack,
        fallback_topic=fallback_topic,
    )
    prompt_parts = build_prompt_parts_from_angle_plan(
        angle_plan,
        cluster=cluster,
        category=category,
        headline=headline_tr,
        summary=summary_tr,
        key_points=key_points_tr,
        why_it_matters=why_it_matters_tr,
        fact_pack=fact_pack,
    )
    video_prompt_en = build_video_prompt_from_parts(prompt_parts, category=category)
    video_plan = coerce_video_plan(
        build_video_plan_data_from_angle_plan(angle_plan, fact_pack=fact_pack),
        cluster,
        category=category,
        headline=headline_tr,
        summary=summary_tr,
        key_points=key_points_tr,
        why_it_matters=why_it_matters_tr,
        prompt_parts=prompt_parts,
        visual_assets=visual_assets,
    )
    video_content = build_video_content_from_plan(
        video_plan,
        cluster,
        summary=summary_tr,
        key_points=key_points_tr,
        why_it_matters=why_it_matters_tr,
    )
    remotion_context = build_remotion_storyboard_context(
        cluster,
        category=category,
        headline=headline_tr,
        summary=summary_tr,
        key_points=key_points_tr,
        why_it_matters=why_it_matters_tr,
        prompt_parts=prompt_parts,
        prompt_text=video_prompt_en,
        video_plan=video_plan,
        visual_assets=visual_assets,
    )
    remotion_storyboard = RemotionStoryboardService().build_storyboard(remotion_context)
    return TopicBrief(
        topic_id=build_topic_id(cluster),
        category=category,
        aggregation_type=aggregation_type,
        story_language=fact_pack.story_language,
        editorial_type=fact_pack.editorial_type,
        headline_tr=headline_tr,
        summary_tr=summary_tr,
        key_points_tr=key_points_tr[:4],
        why_it_matters_tr=why_it_matters_tr,
        confidence=0.78,
        source_count=len(unique_source_names(cluster)),
        article_count=len(cluster),
        sources=unique_source_names(cluster),
        representative_articles=build_representative_articles(cluster),
        visual_assets=visual_assets,
        video_prompt_en=video_prompt_en,
        video_prompt_parts=prompt_parts,
        video_plan=video_plan,
        video_content=video_content,
        remotion_storyboard=remotion_storyboard,
    )


def select_topic_from_angle_plans(
    cluster: list[PreparedArticle],
    angle_plans: list[dict[str, Any]],
    fact_pack: StoryFactPack,
    visual_assets: list[VisualAsset],
    *,
    aggregation_type: str,
) -> TopicPlanningSelection | None:
    candidates: list[tuple[dict[str, Any], TopicBrief, str, int, tuple[str, ...]]] = []
    for angle_plan in angle_plans:
        topic = build_topic_from_angle_plan_payload(
            cluster,
            angle_plan,
            fact_pack,
            visual_assets,
            aggregation_type=aggregation_type,
        )
        if topic is None:
            continue
        status, score, reasons = evaluate_video_quality(topic, cluster=cluster, fact_pack=fact_pack)
        candidates.append((angle_plan, topic, status, score, reasons))

    if not candidates:
        return None

    status_priority = {"publishable": 2, "review": 1, "reject": 0}
    sorted_candidates = sorted(
        candidates,
        key=lambda item: (
            status_priority.get(item[2], 0),
            item[3],
            -angle_priority_index(
                story_domain=fact_pack.story_domain,
                angle_type=str(item[0].get("angle_type", "")),
            ),
        ),
        reverse=True,
    )
    primary_angle, primary_topic, _, _, _ = sorted_candidates[0]
    alternate_topic: TopicBrief | None = None
    alternate_summary = ""
    alternate_angle_type: str | None = None
    if len(sorted_candidates) > 1 and angle_plans_are_distinct(sorted_candidates[0][0], sorted_candidates[1][0]):
        alternate_angle, alternate_topic_candidate, _, _, _ = sorted_candidates[1]
        alternate_topic = alternate_topic_candidate
        alternate_summary = summarize_angle_plan(alternate_angle)
        alternate_angle_type = compact_text(str(alternate_angle.get("angle_type", ""))) or None

    planning_debug = PlanningDebug(
        primary_angle_type=compact_text(str(primary_angle.get("angle_type", ""))) or "primary",
        alternate_angle_type=alternate_angle_type,
        alternate_video_plan_summary=alternate_summary,
        angle_scores=[
            PlanningDebugAngleScore(
                angle_type=compact_text(str(angle_plan.get("angle_type", ""))) or "unknown",
                quality_status=status,
                quality_score=score,
                reasons=list(reasons),
            )
            for angle_plan, _topic, status, score, reasons in sorted_candidates
        ],
    )
    return TopicPlanningSelection(
        primary_topic=primary_topic.model_copy(update={"planning_debug": planning_debug}),
        alternate_topic=alternate_topic,
        planning_debug=planning_debug,
    )


def build_topic_from_llm_payload(
    cluster_lookup: dict[str, PreparedArticle],
    payload: dict[str, Any],
    visual_assets: list[VisualAsset],
    *,
    aggregation_type: str = "shared",
) -> TopicBrief | None:
    article_ids = [str(item) for item in payload.get("article_ids", []) if str(item) in cluster_lookup]
    if not article_ids:
        return None

    unique_ids: list[str] = []
    seen_ids: set[str] = set()
    for article_id in article_ids:
        if article_id not in seen_ids:
            seen_ids.add(article_id)
            unique_ids.append(article_id)

    cluster = sorted(
        [cluster_lookup[article_id] for article_id in unique_ids],
        key=lambda item: item.timestamp,
        reverse=True,
    )
    unique_sources = unique_source_names(cluster)
    if aggregation_type == "shared" and len(unique_sources) < settings.ANALYSIS_MIN_SHARED_SOURCES:
        return None

    fallback_topic = build_fallback_topic(cluster, visual_assets, aggregation_type=aggregation_type)
    headline_tr = clean_viewer_text(str(payload.get("headline_tr", "")), source_names=unique_sources, max_sentences=2, max_chars=2000) or cluster[0].article.title
    headline_tr = trim_viewer_words(headline_tr, 100)
    summary_tr = clean_viewer_text(str(payload.get("summary_tr", "")), source_names=unique_sources, max_sentences=4, max_chars=2000) or (
        fallback_topic.summary_tr if fallback_topic else cluster[0].article.title
    )
    key_points_tr = clean_viewer_points(
        coerce_list(payload.get("key_points_tr")),
        source_names=unique_sources,
        max_items=2,
        max_chars=2000,
    ) or clean_viewer_points(
        [item.article.title for item in cluster[:3]],
        source_names=unique_sources,
        max_items=2,
        max_chars=2000,
    )
    why_candidate = clean_viewer_text(
        str(payload.get("why_it_matters_tr", "")),
        source_names=unique_sources,
        max_sentences=2,
        max_chars=2000,
    )
    why_it_matters_tr = (
        why_candidate
        if why_candidate and not is_generic_why_line(why_candidate)
        else build_why_it_matters_line(
            cluster[0].normalized_category,
            headline=headline_tr,
            summary=summary_tr,
            key_points=key_points_tr,
            cluster=cluster,
        )
    )
    category = cluster[0].normalized_category
    fact_pack = build_story_fact_pack(
        cluster,
        category=category,
        headline=headline_tr,
        summary=summary_tr,
        key_points=key_points_tr,
    )
    if isinstance(payload.get("fact_pack"), dict) or isinstance(payload.get("angle_plans"), list):
        llm_fact_pack = coerce_story_fact_pack(
            payload.get("fact_pack"),
            cluster,
            category=category,
            headline=headline_tr,
            summary=summary_tr,
            key_points=key_points_tr,
        )
        angle_plans = coerce_angle_plans(
            payload.get("angle_plans"),
            story_domain=llm_fact_pack.story_domain,
        )
        if angle_plans:
            selection = select_topic_from_angle_plans(
                cluster,
                angle_plans,
                llm_fact_pack,
                visual_assets,
                aggregation_type=aggregation_type,
            )
            if selection is not None:
                return selection.primary_topic
    prompt_parts = coerce_prompt_parts(
        payload.get("video_prompt_parts"),
        cluster,
        category=category,
        headline=headline_tr,
        summary=summary_tr,
        key_points=key_points_tr,
        why_it_matters=why_it_matters_tr,
    )
    generated_video_prompt = build_video_prompt_from_parts(prompt_parts, category=category)
    llm_video_prompt = compact_text(str(payload.get("video_prompt_en")))
    video_prompt_en = generated_video_prompt if looks_underspecified_human_prompt(llm_video_prompt) else llm_video_prompt or generated_video_prompt
    video_plan = coerce_video_plan(
        payload.get("video_plan"),
        cluster,
        category=category,
        headline=headline_tr,
        summary=summary_tr,
        key_points=key_points_tr,
        why_it_matters=why_it_matters_tr,
        prompt_parts=prompt_parts,
        visual_assets=visual_assets,
    )
    video_content = build_video_content_from_plan(
        video_plan,
        cluster,
        summary=summary_tr,
        key_points=key_points_tr,
        why_it_matters=why_it_matters_tr,
    )

    # Override video_content with LLM-extracted viewer-facing fields when available
    llm_narrative = [compact_text(s) for s in coerce_list(payload.get("video_narrative_en")) if compact_text(s)]
    llm_key_figures = [compact_text(s) for s in coerce_list(payload.get("video_key_figures")) if compact_text(s)]
    llm_key_data = compact_text(str(payload.get("video_key_data", "")))
    llm_video_headline = compact_text(str(payload.get("video_headline_en", "")))

    if llm_narrative:
        video_content.narrative = dedupe_preserve_order(llm_narrative)[:3]
    if llm_key_figures:
        video_content.key_figures = filter_informative_anchors(
            dedupe_preserve_order(llm_key_figures),
            headline=video_content.headline,
            max_items=4,
        )
    if llm_key_data:
        video_content.key_data = llm_key_data
    if llm_video_headline:
        video_content.headline = llm_video_headline

    social_media = payload.get("social_media_content") or {}
    if social_media:
        news_summary = compact_text(str(social_media.get("news_summary", "")))
        if news_summary:
            summary_tr = news_summary

        platforms = social_media.get("platforms") or {}
        ai_image_prompt = compact_text(str(platforms.get("ai_image_prompt", "")))
        if ai_image_prompt:
            video_prompt_en = f"{video_prompt_en}\n\nAI Image Prompt: {ai_image_prompt}"

        instagram_reels = platforms.get("instagram_reels") or {}
        if instagram_reels:
            hook = compact_text(str(instagram_reels.get("hook_text", "")))
            body = compact_text(str(instagram_reels.get("body_text", "")))
            cta = compact_text(str(instagram_reels.get("call_to_action", "")))
            reels_texts = [text for text in [hook, body, cta] if text]
            if reels_texts:
                video_content.narrative = reels_texts

                # Remotion Video Plan sahnelerini sosyal medya kurgusuyla senkronize ediyoruz
                if len(video_plan.scenes) > 0:
                    # Sahne 1: Kanca (Hook)
                    video_plan.scenes[0].headline = hook
                    video_plan.scenes[0].body = ""
                    video_plan.scenes[0].voiceover = hook
                    
                    # Sahne 2: Gelişme (Body)
                    if len(video_plan.scenes) > 1 and body:
                        video_plan.scenes[1].headline = body
                        video_plan.scenes[1].body = ""
                        video_plan.scenes[1].voiceover = body
                    elif body:
                        # Eğer 2. sahne yoksa dinamik olarak ekle
                        new_scene = video_plan.scenes[0].model_copy(update={"scene_id": "scene-2", "purpose": "explain", "headline": body, "voiceover": body})
                        video_plan.scenes.append(new_scene)
                        
                    # Sahne 3: Çağrı (Call to Action)
                    if len(video_plan.scenes) > 2 and cta:
                        video_plan.scenes[2].headline = cta
                        video_plan.scenes[2].body = ""
                        video_plan.scenes[2].voiceover = cta


    remotion_context = build_remotion_storyboard_context(
        cluster,
        category=category,
        headline=headline_tr,
        summary=summary_tr,
        key_points=key_points_tr,
        why_it_matters=why_it_matters_tr,
        prompt_parts=prompt_parts,
        prompt_text=video_prompt_en,
        video_plan=video_plan,
        visual_assets=visual_assets,
    )
    remotion_storyboard = RemotionStoryboardService().build_storyboard(remotion_context)

    return TopicBrief(
        topic_id=build_topic_id(cluster),
        category=category,
        aggregation_type=aggregation_type,
        story_language=fact_pack.story_language,
        editorial_type=fact_pack.editorial_type,
        headline_tr=headline_tr,
        summary_tr=summary_tr,
        key_points_tr=key_points_tr[:4],
        why_it_matters_tr=why_it_matters_tr,
        confidence=clamp_confidence(payload.get("confidence"), default=0.78),
        source_count=len(unique_sources),
        article_count=len(cluster),
        sources=unique_sources,
        representative_articles=build_representative_articles(cluster),
        visual_assets=visual_assets,
        video_prompt_en=video_prompt_en,
        video_prompt_parts=prompt_parts,
        video_plan=video_plan,
        video_content=video_content,
        remotion_storyboard=remotion_storyboard,
    )


def topic_sort_key(topic: TopicBrief) -> tuple[int, datetime, int, float, int]:
    latest_published_at = max(
        (article.published_at or datetime.min) for article in topic.representative_articles
    ) if topic.representative_articles else datetime.min
    return (
        1 if topic.aggregation_type == "shared" else 0,
        latest_published_at,
        topic.article_count,
        topic.confidence,
        topic.source_count,
    )


def sort_topics(topics: list[TopicBrief]) -> list[TopicBrief]:
    return sorted(
        topics,
        key=lambda topic: (topic.quality_score,) + topic_sort_key(topic),
        reverse=True,
    )


def make_topic_analysis_entry(
    topic: TopicBrief,
    *,
    cluster: list[PreparedArticle],
    degraded_generation: bool = False,
) -> TopicAnalysisEntry:
    quality_status, review_reasons = evaluate_topic_quality(
        topic,
        degraded_generation=degraded_generation,
    )
    score_features = topic_score_features(
        topic,
        quality_status=quality_status,
        degraded_generation=degraded_generation,
    )
    quality_score = calculate_topic_quality_score(score_features)
    video_quality_status, video_quality_score, video_review_reasons = evaluate_video_quality(
        topic,
        cluster=cluster,
    )
    seen_sources: set[str] = set()
    source_pairs: list[tuple[str, str]] = []
    for article in topic.representative_articles:
        slug = article.source_slug or "unknown"
        name = article.source_name or "Unknown Source"
        if slug in seen_sources:
            continue
        seen_sources.add(slug)
        source_pairs.append((slug, name))

    return TopicAnalysisEntry(
        topic=topic.model_copy(
            update={
                "quality_status": quality_status,
                "quality_score": quality_score,
                "review_reasons": list(review_reasons),
                "video_quality_status": video_quality_status,
                "video_quality_score": video_quality_score,
                "video_review_reasons": list(video_review_reasons),
            }
        ),
        quality_status=quality_status,
        quality_score=quality_score,
        score_features=score_features,
        review_reasons=review_reasons,
        video_quality_status=video_quality_status,
        video_quality_score=video_quality_score,
        video_review_reasons=video_review_reasons,
        source_slugs=tuple(slug for slug, _ in source_pairs),
        source_names=tuple(name for _, name in source_pairs),
        degraded_generation=degraded_generation,
    )


def sort_topic_entries(
    entries: list[TopicAnalysisEntry],
    *,
    include_review: bool,
) -> list[TopicAnalysisEntry]:
    filtered_entries = [
        entry
        for entry in entries
        if (
            effective_prompt_visibility_status(entry) != "reject"
            and (include_review or effective_prompt_visibility_status(entry) == "publishable")
        )
    ]
    return sorted(
        filtered_entries,
        key=lambda entry: (
            1 if effective_prompt_visibility_status(entry) == "publishable" else 0,
            entry.quality_score,
            entry.video_quality_score,
        ) + topic_sort_key(entry.topic),
        reverse=True,
    )


def build_topic_groups(topic_entries: list[TopicAnalysisEntry]) -> list[TopicGroup]:
    groups_by_category: dict[str, list[TopicAnalysisEntry]] = defaultdict(list)
    for entry in topic_entries:
        groups_by_category[entry.topic.category].append(entry)

    groups = [
        TopicGroup(category=group_category, topics=[entry.topic for entry in group_entries])
        for group_category, group_entries in groups_by_category.items()
    ]
    groups.sort(
        key=lambda group: (
            max((topic.quality_score for topic in group.topics), default=0.0),
            len(group.topics),
        ),
        reverse=True,
    )
    return groups


def build_topic_quality_totals(
    result: TopicAnalysisRunResult,
    *,
    feedback_records: dict[str, TopicFeedback] | None = None,
) -> TopicQualityTotals:
    rejection_counts: dict[str, int] = defaultdict(int)
    input_rejection_counts: dict[str, int] = defaultdict(int)
    review_counts: dict[str, int] = defaultdict(int)
    video_review_counts: dict[str, int] = defaultdict(int)
    feedback_items = list((feedback_records or {}).values())
    for rejection in result.rejections:
        rejection_counts[rejection.reason] += 1
        if rejection.stage == "article":
            input_rejection_counts[rejection.reason] += 1
    for entry in result.topic_entries:
        for reason in entry.review_reasons:
            review_counts[reason] += 1
        for reason in entry.video_review_reasons:
            video_review_counts[reason] += 1
    all_scores = [entry.quality_score for entry in result.topic_entries]
    publishable_scores = [entry.quality_score for entry in result.topic_entries if entry.quality_status == "publishable"]
    review_scores = [entry.quality_score for entry in result.topic_entries if entry.quality_status == "review"]

    return TopicQualityTotals(
        fetched_articles=len(result.articles),
        prepared_articles=len(result.prepared_articles),
        rejected_articles=sum(1 for rejection in result.rejections if rejection.stage == "article"),
        candidate_clusters=len(result.candidate_clusters),
        publishable_topics=sum(1 for entry in result.topic_entries if entry.quality_status == "publishable"),
        review_topics=sum(1 for entry in result.topic_entries if entry.quality_status == "review"),
        rejected_topics=sum(1 for rejection in result.rejections if rejection.stage != "article"),
        shared_topics=sum(1 for entry in result.topic_entries if entry.topic.aggregation_type == "shared"),
        unique_topics=sum(1 for entry in result.topic_entries if entry.topic.aggregation_type == "unique"),
        avg_quality_score=average_quality_score(all_scores),
        publishable_avg_quality_score=average_quality_score(publishable_scores),
        review_avg_quality_score=average_quality_score(review_scores),
        video_publishable_topics=sum(1 for entry in result.topic_entries if entry.video_quality_status == "publishable"),
        video_review_topics=sum(1 for entry in result.topic_entries if entry.video_quality_status == "review"),
        video_rejected_topics=sum(1 for entry in result.topic_entries if entry.video_quality_status == "reject"),
        feedback_count=len(feedback_items),
        feedback_coverage_percent=feedback_coverage_percent(
            feedback_count=len(feedback_items),
            topic_count=len(result.topic_entries),
        ),
        score_distribution=build_score_distribution(all_scores),
        rejection_breakdown=[
            AnalysisRejectionDebug(reason=reason, count=count)
            for reason, count in sorted(rejection_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        input_rejection_breakdown=[
            AnalysisRejectionDebug(reason=reason, count=count)
            for reason, count in sorted(input_rejection_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        review_breakdown=[
            AnalysisReviewDebug(reason=reason, count=count)
            for reason, count in sorted(review_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        video_review_breakdown=[
            AnalysisReviewDebug(reason=reason, count=count)
            for reason, count in sorted(video_review_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        feedback_breakdown=feedback_breakdown(feedback_items),
    )


def build_source_quality_reports(result: TopicAnalysisRunResult) -> list[TopicQualitySourceReport]:
    source_data: dict[tuple[str, str], dict[str, Any]] = {}

    def ensure_source(slug: str, name: str) -> dict[str, Any]:
        key = (slug, name)
        if key not in source_data:
            source_data[key] = {
                "article_count": 0,
                "prepared_article_count": 0,
                "rejected_article_count": 0,
                "topic_contributions": 0,
                "publishable_contributions": 0,
                "review_contributions": 0,
                "shared_contributions": 0,
                "unique_contributions": 0,
                "score_values": [],
                "publishable_score_values": [],
                "review_score_values": [],
                "rejection_counts": defaultdict(int),
                "review_counts": defaultdict(int),
                "sample_rejections": [],
                "sample_review_topics": [],
                "lowest_scoring_topics": [],
            }
        return source_data[key]

    for article in result.articles:
        source = article.source
        slug = source.slug if source else "unknown"
        name = source.name if source else "Unknown Source"
        ensure_source(slug, name)["article_count"] += 1

    for prepared in result.prepared_articles:
        ensure_source(prepared.source_slug, prepared.source_name)["prepared_article_count"] += 1

    for rejection in result.rejections:
        bucket = ensure_source(rejection.source_slug, rejection.source_name)
        if rejection.stage == "article":
            bucket["rejected_article_count"] += 1
        bucket["rejection_counts"][rejection.reason] += 1
        if len(bucket["sample_rejections"]) < 3:
            bucket["sample_rejections"].append(
                TopicQualitySampleRejection(title=rejection.title, reason=rejection.reason)
            )

    for entry in result.topic_entries:
        if entry.video_quality_status == "reject":
            continue
        source_pairs = list(zip(entry.source_slugs, entry.source_names))
        for slug, name in source_pairs:
            bucket = ensure_source(slug, name)
            bucket["topic_contributions"] += 1
            if entry.quality_status == "publishable":
                bucket["publishable_contributions"] += 1
                bucket["publishable_score_values"].append(entry.quality_score)
            else:
                bucket["review_contributions"] += 1
                bucket["review_score_values"].append(entry.quality_score)
            if entry.topic.aggregation_type == "shared":
                bucket["shared_contributions"] += 1
            else:
                bucket["unique_contributions"] += 1
            bucket["score_values"].append(entry.quality_score)
            for reason in entry.review_reasons:
                bucket["review_counts"][reason] += 1
            if entry.quality_status == "review" and len(bucket["sample_review_topics"]) < 3:
                bucket["sample_review_topics"].append(
                    TopicQualitySampleReviewTopic(
                        headline=entry.topic.headline_tr,
                        reasons=list(entry.review_reasons),
                    )
                )
            bucket["lowest_scoring_topics"].append(
                TopicQualityScoredTopic(
                    headline=entry.topic.headline_tr,
                    quality_status=entry.quality_status,
                    quality_score=entry.quality_score,
                )
            )

    reports = [
        TopicQualitySourceReport(
            source_slug=source_slug,
            source_name=source_name,
            article_count=bucket["article_count"],
            prepared_article_count=bucket["prepared_article_count"],
            rejected_article_count=bucket["rejected_article_count"],
            topic_contributions=bucket["topic_contributions"],
            publishable_contributions=bucket["publishable_contributions"],
            review_contributions=bucket["review_contributions"],
            shared_contributions=bucket["shared_contributions"],
            unique_contributions=bucket["unique_contributions"],
            avg_quality_score=average_quality_score(bucket["score_values"]),
            publishable_avg_quality_score=average_quality_score(bucket["publishable_score_values"]),
            review_avg_quality_score=average_quality_score(bucket["review_score_values"]),
            rejection_breakdown=[
                AnalysisRejectionDebug(reason=reason, count=count)
                for reason, count in sorted(bucket["rejection_counts"].items(), key=lambda item: (-item[1], item[0]))
            ],
            review_breakdown=[
                AnalysisReviewDebug(reason=reason, count=count)
                for reason, count in sorted(bucket["review_counts"].items(), key=lambda item: (-item[1], item[0]))
            ],
            sample_rejections=bucket["sample_rejections"],
            sample_review_topics=bucket["sample_review_topics"],
            lowest_scoring_topics=sorted(
                bucket["lowest_scoring_topics"],
                key=lambda item: (item.quality_score, item.headline.lower()),
            )[:3],
        )
        for (source_slug, source_name), bucket in source_data.items()
    ]
    return sorted(
        reports,
        key=lambda report: (
            report.rejected_article_count,
            report.review_contributions,
            -report.avg_quality_score,
            report.article_count,
            report.source_slug,
        ),
        reverse=True,
    )


def build_topic_briefs_response(
    result: TopicAnalysisRunResult,
    *,
    topics: list[TopicBrief],
    limit_topics: int,
    include_review: bool,
    include_debug: bool,
) -> TopicBriefsResponse:
    sorted_entries = sort_topic_entries(result.topic_entries, include_review=include_review)
    topic_lookup = {
        topic.topic_id: topic.model_copy(
            update={"planning_debug": topic.planning_debug if include_debug else None}
        )
        for topic in topics
    }
    limited_entries = sorted_entries[:limit_topics]
    returned_topics = [topic_lookup.get(entry.topic.topic_id, entry.topic) for entry in limited_entries]
    returned_unique_articles = sum(
        topic.article_count
        for topic in returned_topics
        if topic.aggregation_type == "unique"
    )
    dropped_unique_articles = max(0, result.total_unique_candidate_articles - returned_unique_articles)
    debug_notes = list(result.notes)
    combined_review_count = sum(1 for entry in result.topic_entries if effective_prompt_visibility_status(entry) == "review")
    video_rejected_count = sum(1 for entry in result.topic_entries if entry.video_quality_status == "reject")

    if not include_review and combined_review_count:
        debug_notes.append(
            f"{combined_review_count} topic(s) were flagged for review and excluded from the default response."
        )
    if video_rejected_count:
        debug_notes.append(
            f"{video_rejected_count} topic(s) were rejected by the video-quality validator before prompt listing."
        )
    if not limited_entries and combined_review_count and not include_review:
        debug_notes.append("Only review topics were produced for this window; pass include_review=true to inspect them.")
    if dropped_unique_articles:
        debug_notes.append(
            f"{dropped_unique_articles} unique article(s) were omitted from the final response after filtering and limit_topics={limit_topics}."
        )

    return TopicBriefsResponse(
        analysis_status=result.analysis_status,
        generated_at=result.window_end,
        window_start=result.window_start,
        window_end=result.window_end,
        groups=build_topic_groups(
            [
                entry
                if entry.topic.topic_id not in topic_lookup
                else TopicAnalysisEntry(
                    topic=topic_lookup[entry.topic.topic_id],
                    quality_status=entry.quality_status,
                    quality_score=entry.quality_score,
                    score_features=entry.score_features,
                    review_reasons=entry.review_reasons,
                    video_quality_status=entry.video_quality_status,
                    video_quality_score=entry.video_quality_score,
                    video_review_reasons=entry.video_review_reasons,
                    source_slugs=entry.source_slugs,
                    source_names=entry.source_names,
                    degraded_generation=entry.degraded_generation,
                )
                for entry in limited_entries
            ]
        ),
        debug=build_analysis_debug(
            articles=result.articles,
            prepared_articles=result.prepared_articles,
            candidate_clusters=result.candidate_clusters,
            topic_entries=result.topic_entries,
            rejections=result.rejections,
            notes=debug_notes,
            ollama_error=result.ollama_error,
            shared_topics_generated=result.shared_topics_generated,
            unique_topics_generated=result.unique_topics_generated,
            rejected_unique_candidates=result.rejected_unique_candidates,
            dropped_unique_articles=dropped_unique_articles,
        )
        if include_debug
        else None,
    )


def build_topic_quality_report_response(
    result: TopicAnalysisRunResult,
    *,
    feedback_records: dict[str, TopicFeedback] | None = None,
) -> TopicQualityReportResponse:
    return TopicQualityReportResponse(
        analysis_status=result.analysis_status,
        generated_at=result.window_end,
        window_start=result.window_start,
        window_end=result.window_end,
        totals=build_topic_quality_totals(result, feedback_records=feedback_records),
        sources=build_source_quality_reports(result),
        notes=list(result.notes),
        ollama_error=result.ollama_error,
    )


async def upsert_topic_feedback(
    db: AsyncSession,
    payload: TopicFeedbackUpsertRequest,
) -> TopicFeedbackResponse:
    snapshot = payload.topic_snapshot
    score_features = topic_feedback_score_features(snapshot)
    note = compact_text(payload.note) or None

    existing = await db.execute(
        select(TopicFeedback).where(TopicFeedback.topic_id == payload.topic_id)
    )
    record = existing.scalar_one_or_none()
    if record is None:
        record = TopicFeedback(topic_id=payload.topic_id, feedback_label=payload.feedback_label)
        db.add(record)

    record.feedback_label = payload.feedback_label
    record.note = note
    record.headline_tr = compact_text(snapshot.headline_tr)
    record.summary_tr = compact_text(snapshot.summary_tr)
    record.category = snapshot.category
    record.aggregation_type = snapshot.aggregation_type
    record.quality_status = snapshot.quality_status
    record.quality_score = round_quality_score(snapshot.quality_score)
    record.video_quality_status = snapshot.video_quality_status
    record.video_quality_score = max(0, min(100, int(snapshot.video_quality_score)))
    record.source_count = snapshot.source_count
    record.article_count = snapshot.article_count
    record.source_slugs = [compact_text(slug) for slug in snapshot.source_slugs if compact_text(slug)]
    record.representative_article_ids = [str(article_id) for article_id in snapshot.representative_article_ids]
    record.review_reasons = [reason for reason in snapshot.review_reasons if reason in VALID_REVIEW_REASONS]
    record.video_review_reasons = [
        reason for reason in snapshot.video_review_reasons if reason in VALID_VIDEO_REVIEW_REASONS
    ]
    record.score_features = score_features

    await db.flush()
    await db.refresh(record)
    return TopicFeedbackResponse(
        topic_id=payload.topic_id,
        latest_feedback=build_latest_feedback(record),
    )


async def delete_topic_feedback(
    db: AsyncSession,
    topic_id: str,
) -> TopicFeedbackDeleteResponse:
    existing = await db.execute(
        select(TopicFeedback).where(TopicFeedback.topic_id == topic_id)
    )
    record = existing.scalar_one_or_none()
    if record is not None:
        await db.delete(record)
        await db.flush()
    return TopicFeedbackDeleteResponse(topic_id=topic_id, deleted=record is not None)


def build_tuning_sample(record: TopicFeedback) -> TopicScoreTuningSample:
    return TopicScoreTuningSample(
        topic_id=record.topic_id,
        headline_tr=record.headline_tr,
        feedback_label=record.feedback_label,
        quality_status=record.quality_status,
        quality_score=round_quality_score(record.quality_score),
    )


async def generate_topic_score_tuning_report(
    db: AsyncSession,
    *,
    days: int = 30,
    source_category: str | None = None,
    category: str | None = None,
) -> TopicScoreTuningReportResponse:
    generated_at = utcnow()
    cutoff = generated_at - timedelta(days=days)

    feedback_query = select(TopicFeedback).where(TopicFeedback.updated_at >= cutoff)
    if category:
        feedback_query = feedback_query.where(TopicFeedback.category == category)
    feedback_rows = await db.execute(feedback_query)
    feedback_records = [record for record in feedback_rows.scalars().all() if record.feedback_label in VALID_FEEDBACK_LABELS]

    if source_category:
        source_rows = await db.execute(select(Source.slug, Source.category))
        source_category_map = {
            compact_text(slug): compact_text(record_category)
            for slug, record_category in source_rows.all()
        }
        feedback_records = [
            record
            for record in feedback_records
            if any(source_category_map.get(compact_text(slug)) == source_category for slug in (record.source_slugs or []))
        ]

    approved_records = [record for record in feedback_records if approved_feedback(record)]
    negative_records = [record for record in feedback_records if negative_feedback(record)]
    eligible = (
        len(feedback_records) >= TUNING_MIN_FEEDBACK
        and len(approved_records) >= TUNING_MIN_APPROVED
        and len(negative_records) >= TUNING_MIN_NEGATIVE
    )

    recommendations: list[TopicScoreWeightRecommendation] = []
    notes: list[str] = []
    if not eligible:
        notes.append(
            "Not enough feedback yet for reliable weight recommendations."
        )
        notes.append(
            f"Thresholds: {TUNING_MIN_FEEDBACK}+ total, {TUNING_MIN_APPROVED}+ approved, {TUNING_MIN_NEGATIVE}+ negative."
        )
    else:
        normalized_feature_maps = {
            record.topic_id: normalize_score_features(record.score_features if isinstance(record.score_features, dict) else None)
            for record in feedback_records
        }
        for feature in QUALITY_SCORE_FEATURES:
            active_records = [record for record in feedback_records if normalized_feature_maps[record.topic_id].get(feature)]
            inactive_records = [record for record in feedback_records if not normalized_feature_maps[record.topic_id].get(feature)]
            if len(active_records) < TUNING_MIN_FEATURE_SUPPORT or len(inactive_records) < TUNING_MIN_FEATURE_SUPPORT:
                continue

            active_approval_rate = sum(1 for record in active_records if approved_feedback(record)) / len(active_records)
            inactive_approval_rate = sum(1 for record in inactive_records if approved_feedback(record)) / len(inactive_records)
            lift = round(active_approval_rate - inactive_approval_rate, 3)
            delta = tuning_weight_delta(lift)
            if delta == 0.0:
                continue

            current_weight = QUALITY_SCORE_WEIGHTS[feature]
            recommendations.append(
                TopicScoreWeightRecommendation(
                    feature=feature,
                    current_weight=round(current_weight, 3),
                    recommended_weight=round(current_weight + delta, 3),
                    delta=round(delta, 3),
                    active_count=len(active_records),
                    inactive_count=len(inactive_records),
                    approval_rate_when_active=round(active_approval_rate, 3),
                    approval_rate_when_inactive=round(inactive_approval_rate, 3),
                    lift=lift,
                )
            )

        if not recommendations:
            notes.append("Feedback exists, but no feature crossed the current tuning thresholds.")

    high_score_negative = sorted(
        [record for record in negative_records if record.quality_score >= HIGH_SCORE_NEGATIVE_THRESHOLD],
        key=lambda record: (-record.quality_score, record.updated_at),
    )
    low_score_approved = sorted(
        [record for record in approved_records if record.quality_score <= LOW_SCORE_APPROVED_THRESHOLD],
        key=lambda record: (record.quality_score, record.updated_at),
    )

    return TopicScoreTuningReportResponse(
        generated_at=generated_at,
        days=days,
        source_category=source_category,
        category=category,
        totals=TopicScoreTuningTotals(
            feedback_count=len(feedback_records),
            approved_count=len(approved_records),
            negative_count=len(negative_records),
            eligible_for_recommendations=eligible,
            feedback_breakdown=feedback_breakdown(feedback_records),
        ),
        current_weights={key: round(value, 3) for key, value in QUALITY_SCORE_WEIGHTS.items()},
        recommendations=sorted(recommendations, key=lambda item: (-abs(item.delta), item.feature)),
        calibration_summary=TopicScoreTuningCalibrationSummary(
            high_score_negative_count=len(high_score_negative),
            low_score_approved_count=len(low_score_approved),
        ),
        mismatch_samples=TopicScoreTuningMismatchSamples(
            high_score_negative=[build_tuning_sample(record) for record in high_score_negative[:5]],
            low_score_approved=[build_tuning_sample(record) for record in low_score_approved[:5]],
        ),
        notes=notes,
    )


async def run_topic_analysis(
    db: AsyncSession,
    *,
    source_category: str | None = None,
    category: str | None = None,
    hours: int = 1,
    max_clusters: int | None = None,
) -> TopicAnalysisRunResult:
    window_end = utcnow()
    window_start = window_end - timedelta(hours=hours)
    articles = await get_recent_articles_for_analysis(
        db,
        source_category=source_category,
        hours=hours,
        window_end=window_end,
    )
    prepared_result = await build_prepared_articles(articles, category_filter=category)
    prepared_articles = prepared_result.prepared_articles
    analysis_rejections = list(prepared_result.rejections)
    candidate_clusters = build_candidate_clusters(prepared_articles)
    analysis_notes = [
        f"Analysis caps: max {settings.ANALYSIS_MAX_ARTICLES_PER_SOURCE} article(s) per source and {settings.ANALYSIS_MAX_ARTICLES_PER_RUN} article(s) overall."
    ]
    ollama_error: str | None = None
    shared_topics_generated = 0
    unique_topics_generated = 0
    rejected_unique_candidates = 0

    if not articles:
        analysis_notes.append("No articles matched the requested time window.")
        return TopicAnalysisRunResult(
            analysis_status="ok",
            window_start=window_start,
            window_end=window_end,
            articles=articles,
            prepared_articles=prepared_articles,
            candidate_clusters=candidate_clusters,
            rejections=analysis_rejections,
            topic_entries=[],
            notes=analysis_notes,
            shared_topics_generated=shared_topics_generated,
            unique_topics_generated=unique_topics_generated,
            rejected_unique_candidates=rejected_unique_candidates,
            total_unique_candidate_articles=0,
        )

    if not prepared_articles:
        analysis_notes.append("Articles were fetched, but none survived category or text preparation.")
        return TopicAnalysisRunResult(
            analysis_status="ok",
            window_start=window_start,
            window_end=window_end,
            articles=articles,
            prepared_articles=prepared_articles,
            candidate_clusters=candidate_clusters,
            rejections=analysis_rejections,
            topic_entries=[],
            notes=analysis_notes,
            shared_topics_generated=shared_topics_generated,
            unique_topics_generated=unique_topics_generated,
            rejected_unique_candidates=rejected_unique_candidates,
            total_unique_candidate_articles=0,
        )

    shared_clusters, unique_candidate_clusters, singleton_clusters = partition_clusters(
        prepared_articles,
        candidate_clusters,
    )
    unique_candidate_clusters = unique_candidate_clusters + singleton_clusters
    if shared_clusters:
        analysis_notes.append(f"{len(shared_clusters)} shared candidate cluster(s) qualified for merged topic generation.")
    if unique_candidate_clusters:
        analysis_notes.append(f"{len(unique_candidate_clusters)} unique cluster(s) qualified for single-topic prompt generation.")
    if singleton_clusters:
        analysis_notes.append(f"{len(singleton_clusters)} unclustered article(s) were converted into unique prompt candidates.")

    llm_analyzer = OllamaTopicAnalyzer()
    asset_resolver = VisualAssetResolver()
    analysis_status = "ok"
    llm_available = True
    topic_entries: list[TopicAnalysisEntry] = []

    for cluster in shared_clusters:
        visual_assets = await resolve_visual_assets_for_cluster(cluster, asset_resolver)
        llm_topics: list[dict[str, Any]] = []
        if llm_available:
            try:
                llm_topics = await llm_analyzer.analyze_cluster(cluster, visual_assets)
            except OllamaAnalysisError as exc:
                logger.warning("Ollama topic analysis degraded: %s", exc)
                llm_available = False
                analysis_status = "degraded"
                ollama_error = str(exc)
                analysis_notes.append(f"Ollama analysis failed: {exc}")
                llm_topics = []

        cluster_topics: list[TopicBrief] = []
        if llm_available and llm_topics:
            lookup = {str(item.article.id): item for item in cluster}
            cluster_topics = [
                topic
                for topic in (
                    build_topic_from_llm_payload(
                        lookup,
                        payload,
                        visual_assets,
                        aggregation_type="shared",
                    )
                    for payload in llm_topics
                )
                if topic is not None
            ]

        if cluster_topics:
            topic_entries.extend(make_topic_analysis_entry(topic, cluster=cluster) for topic in cluster_topics)
            shared_topics_generated += len(cluster_topics)
            continue

        fallback_topic = build_fallback_topic(cluster, visual_assets, aggregation_type="shared")
        if fallback_topic:
            analysis_status = "degraded"
            topic_entries.append(
                make_topic_analysis_entry(
                    fallback_topic,
                    cluster=cluster,
                    degraded_generation=True,
                )
            )
            shared_topics_generated += 1
            continue

        representative = cluster[0]
        analysis_rejections.append(
            make_rejection(
                "template_mismatch",
                stage="topic",
                title=representative.article.title,
                url=representative.article.url,
                source_slug=representative.source_slug,
                source_name=representative.source_name,
            )
        )

    for cluster in unique_candidate_clusters:
        rejection_reason = unique_candidate_rejection_reason(cluster)
        if rejection_reason:
            representative = cluster[0]
            analysis_rejections.append(
                make_rejection(
                    rejection_reason,
                    stage="unique_candidate",
                    title=representative.article.title,
                    url=representative.article.url,
                    source_slug=representative.source_slug,
                    source_name=representative.source_name,
                )
            )
            rejected_unique_candidates += 1
            continue

        visual_assets = await resolve_visual_assets_for_cluster(cluster, asset_resolver)
        unique_topic = build_fallback_topic(
            cluster,
            visual_assets,
            aggregation_type="unique",
        )
        if unique_topic:
            topic_entries.append(make_topic_analysis_entry(unique_topic, cluster=cluster))
            unique_topics_generated += 1
            continue

        representative = cluster[0]
        analysis_rejections.append(
            make_rejection(
                "low_signal_unique",
                stage="unique_candidate",
                title=representative.article.title,
                url=representative.article.url,
                source_slug=representative.source_slug,
                source_name=representative.source_name,
            )
        )
        rejected_unique_candidates += 1

    review_topic_count = sum(1 for entry in topic_entries if effective_prompt_visibility_status(entry) == "review")
    video_rejected_count = sum(1 for entry in topic_entries if entry.video_quality_status == "reject")
    rejected_articles = sum(1 for rejection in analysis_rejections if rejection.stage == "article")
    if not topic_entries:
        if unique_candidate_clusters:
            analysis_notes.append("Unique prompt candidates existed, but no topics survived quality evaluation.")
        if shared_clusters:
            analysis_notes.append("Shared clusters existed, but no shared topics were returned after model parsing.")
        if not shared_clusters and not unique_candidate_clusters:
            analysis_notes.append("Articles were fetched, but no promptable shared or unique topics could be formed.")
    else:
        if not shared_topics_generated and unique_topics_generated:
            analysis_notes.append("No shared topics were found, so the result contains only unique prompts.")
        if rejected_unique_candidates:
            analysis_notes.append(
                f"{rejected_unique_candidates} unique candidate(s) were rejected by quality guardrails before rendering."
            )
        if rejected_articles:
            analysis_notes.append(
                f"{rejected_articles} article(s) were filtered out before clustering because they looked non-news, stale, or malformed."
            )
        if review_topic_count:
            analysis_notes.append(
                f"{review_topic_count} topic(s) were flagged for review before publication."
            )
        if video_rejected_count:
            analysis_notes.append(
                f"{video_rejected_count} topic(s) were rejected by the video-quality validator."
            )

    return TopicAnalysisRunResult(
        analysis_status=analysis_status,
        window_start=window_start,
        window_end=window_end,
        articles=articles,
        prepared_articles=prepared_articles,
        candidate_clusters=candidate_clusters,
        rejections=analysis_rejections,
        topic_entries=topic_entries,
        notes=analysis_notes,
        ollama_error=ollama_error,
        shared_topics_generated=shared_topics_generated,
        unique_topics_generated=unique_topics_generated,
        rejected_unique_candidates=rejected_unique_candidates,
        total_unique_candidate_articles=sum(len(cluster) for cluster in unique_candidate_clusters),
    )


async def generate_topic_briefs(
    db: AsyncSession,
    *,
    source_category: str | None = None,
    category: str | None = None,
    hours: int = 1,
    limit_topics: int = 10,
    include_review: bool = False,
    include_debug: bool = False,
) -> TopicBriefsResponse:
    result = await run_topic_analysis(
        db,
        source_category=source_category,
        category=category,
        hours=hours,
        max_clusters=limit_topics + 3,
    )
    hydrated_topics, _ = await hydrate_topics_with_feedback(
        db,
        [entry.topic for entry in result.topic_entries],
    )
    return build_topic_briefs_response(
        result,
        topics=hydrated_topics,
        limit_topics=limit_topics,
        include_review=include_review,
        include_debug=include_debug,
    )


async def generate_topic_quality_report(
    db: AsyncSession,
    *,
    source_category: str | None = None,
    category: str | None = None,
    hours: int = 1,
) -> TopicQualityReportResponse:
    result = await run_topic_analysis(
        db,
        source_category=source_category,
        category=category,
        hours=hours,
    )
    feedback_records = await get_topic_feedback_records(
        db,
        [entry.topic.topic_id for entry in result.topic_entries],
    )
    return build_topic_quality_report_response(result, feedback_records=feedback_records)
