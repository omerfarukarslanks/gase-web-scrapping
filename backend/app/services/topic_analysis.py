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
from typing import Any
from urllib.parse import urlparse

import httpx
import trafilatura
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.article import Article
from app.models.source import Source
from app.schemas.analysis import (
    AnalysisClusterDebug,
    AnalysisDebug,
    AnalysisRejectionDebug,
    AnalysisSourceDebug,
    RemotionStat,
    TopicBrief,
    TopicBriefsResponse,
    TopicGroup,
    TopicRepresentativeArticle,
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


class OllamaAnalysisError(RuntimeError):
    """Raised when Ollama analysis fails."""


@dataclass(slots=True)
class PreparedArticle:
    article: Article
    normalized_category: str
    analysis_text: str
    timestamp: datetime
    source_name: str
    source_slug: str
    tag_tokens: set[str] = field(default_factory=set)
    title_tokens: set[str] = field(default_factory=set)
    text_tokens: set[str] = field(default_factory=set)


@dataclass(slots=True)
class AnalysisRejection:
    reason: str
    stage: str
    title: str
    url: str


@dataclass(slots=True)
class PreparedArticlesResult:
    prepared_articles: list[PreparedArticle]
    rejections: list[AnalysisRejection] = field(default_factory=list)


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


def trim_words(value: str, max_words: int) -> str:
    words = compact_text(value).split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(",;:.") + "..."


def split_sentences(value: str) -> list[str]:
    compacted = compact_text(value)
    if not compacted:
        return []
    parts = re.split(r"(?<=[.!?])\s+", compacted)
    return [compact_text(part) for part in parts if compact_text(part)]


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


def clean_viewer_text(
    value: str | None,
    *,
    source_names: list[str] | None = None,
    max_sentences: int = 2,
    max_chars: int = 180,
) -> str:
    cleaned = remove_source_labels(value or "", source_names or [])
    if not cleaned:
        return ""
    sentences = dedupe_preserve_order(split_sentences(cleaned))
    if not sentences:
        sentences = [cleaned]
    merged = " ".join(sentences[:max_sentences])
    return truncate_text(compact_text(merged), max_chars)


def clean_viewer_points(
    values: list[str],
    *,
    source_names: list[str] | None = None,
    max_items: int = 2,
    max_chars: int = 96,
) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        normalized = clean_viewer_text(
            value,
            source_names=source_names,
            max_sentences=1,
            max_chars=max_chars,
        )
        if normalized:
            cleaned.append(normalized)
    return dedupe_preserve_order(cleaned)[:max_items]


def make_rejection(reason: str, *, stage: str, title: str, url: str) -> AnalysisRejection:
    normalized_reason = reason if reason in VALID_REJECTION_REASONS else "low_signal_unique"
    return AnalysisRejection(
        reason=normalized_reason,
        stage=stage,
        title=compact_text(title),
        url=compact_text(url),
    )


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
    summary: str,
    key_points: list[str],
    comparison_story: bool,
) -> str:
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


def article_eligibility_reason(article: Article, *, timestamp: datetime) -> str | None:
    raw_title = article.title or ""
    raw_summary = article.summary or article.content_snippet or ""
    clean_title = compact_text(raw_title)
    clean_summary = compact_text(raw_summary)

    if url_has_non_news_segment(article.url):
        last_segment = last_path_segment(article.url)
        if last_segment in {"video", "videos", "watch"}:
            return "non_news_url"
        return "utility_or_hub_page"
    if is_utility_title(clean_title):
        return "utility_or_hub_page"
    if looks_broken_title(clean_title):
        return "broken_title"
    if has_stale_year_signal(clean_title, timestamp):
        return "stale_or_evergreen"
    if has_html_artifact(raw_title) and looks_broken_title(clean_title):
        return "html_artifact"
    if not article.published_at and (not looks_news_like_url(article.url) or not has_minimum_story_signal(clean_title, clean_summary or clean_title)):
        return "stale_or_evergreen"
    return None


def unique_candidate_rejection_reason(cluster: list[PreparedArticle]) -> str | None:
    if not cluster:
        return "low_signal_unique"

    representative = cluster[0].article
    titles = [compact_text(item.article.title) for item in cluster if compact_text(item.article.title)]
    summaries = [
        compact_text(item.article.summary) or compact_text(item.article.content_snippet)
        for item in cluster
    ]
    headline = min(titles, key=len) if titles else compact_text(representative.title)
    summary = " ".join([value for value in summaries if value][:2]) or headline
    category = cluster[0].normalized_category

    if not looks_news_like_url(representative.url):
        return "non_news_url"
    if is_utility_title(headline):
        return "utility_or_hub_page"
    if looks_broken_title(headline):
        return "broken_title"
    if has_stale_year_signal(headline, cluster[0].timestamp):
        return "stale_or_evergreen"
    if any(has_html_artifact(item.article.title) or has_html_artifact(item.article.summary) for item in cluster) and not has_minimum_story_signal(headline, summary):
        return "html_artifact"
    if not has_minimum_story_signal(headline, summary):
        return "low_signal_unique"

    subtype = infer_story_subtype(
        category=category,
        headline=headline,
        summary=summary,
        key_points=titles[:2],
        comparison_story=is_comparison_story(
            category=category,
            headline=headline,
            summary=summary,
            key_points=titles[:2],
            score=extract_score([headline, summary, *titles[:2]]),
        ),
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


def build_why_it_matters_line(category: str) -> str:
    mapping = {
        "sports": "The result can shape the momentum heading into the next game.",
        "business": "The move could influence near-term market expectations.",
        "science": "The development could shape the next phase of research or missions.",
        "technology": "The next product or policy response could quickly shift the story.",
        "world": "The next official response will shape how the situation develops.",
        "politics": "The next official response will determine the immediate political impact.",
        "general": "The next confirmed update will likely shape where the story goes next.",
    }
    return mapping.get(category, mapping["general"])


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
) -> int:
    complexity = classify_story_complexity(summary, key_points)
    if category == "sports" and not comparison_story:
        if complexity == "short":
            return 1
        if complexity == "medium" and len(dedupe_preserve_order(key_points)) <= 2:
            return 1
    if complexity == "short":
        return 1
    if complexity == "medium":
        return 2
    return 3


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


def truncate_text(value: str, limit: int = 84) -> str:
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


def truncate_for_prompt(value: str, limit: int = 68) -> str:
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
        "top_key_point": truncate_for_prompt(key_points[0], 96) if key_points else "",
        "supporting_key_points": [truncate_for_prompt(point, 96) for point in key_points[1:3]],
    }


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


async def extract_article_text(
    url: str,
    client: httpx.AsyncClient,
    cache: dict[str, str],
) -> str:
    if url in cache:
        return cache[url]

    try:
        response = await client.get(url)
        response.raise_for_status()
        extracted = trafilatura.extract(
            response.text,
            output_format="txt",
            include_comments=False,
            include_tables=False,
        )
        cache[url] = compact_text(extracted)[: settings.ANALYSIS_TEXT_CHAR_LIMIT]
    except Exception as exc:  # noqa: BLE001
        logger.debug("Article body extraction failed for %s: %s", url, exc)
        cache[url] = ""

    return cache[url]


async def build_prepared_articles(
    articles: list[Article],
    *,
    category_filter: str | None = None,
) -> PreparedArticlesResult:
    text_cache: dict[str, str] = {}

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=5.0),
        headers={"User-Agent": settings.USER_AGENT},
        follow_redirects=True,
    ) as client:
        prepared = await asyncio.gather(
            *[
                _build_prepared_article(
                    article,
                    client=client,
                    cache=text_cache,
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
    client: httpx.AsyncClient,
    cache: dict[str, str],
    category_filter: str | None,
) -> PreparedArticle | AnalysisRejection | None:
    normalized_category = normalize_analysis_category(article.category, article.source_category)
    if category_filter and normalized_category != category_filter:
        return None

    timestamp = get_article_timestamp(article)
    rejection_reason = article_eligibility_reason(article, timestamp=timestamp)
    if rejection_reason:
        return make_rejection(
            rejection_reason,
            stage="article",
            title=article.title,
            url=article.url,
        )

    base_text = compact_text(article.summary) or compact_text(article.content_snippet)
    if not base_text:
        base_text = await extract_article_text(article.url, client, cache)

    analysis_text = base_text[: settings.ANALYSIS_TEXT_CHAR_LIMIT] if base_text else article.title
    source_name = article.source.name if article.source else "Unknown Source"
    source_slug = article.source.slug if article.source else "unknown"

    return PreparedArticle(
        article=article,
        normalized_category=normalized_category,
        analysis_text=analysis_text,
        timestamp=timestamp,
        source_name=source_name,
        source_slug=source_slug,
        tag_tokens={compact_text(str(tag)).lower() for tag in (article.tags or []) if compact_text(str(tag))},
        title_tokens=tokenize(article.title),
        text_tokens=tokenize(analysis_text, max_tokens=80),
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
        prompt = self._build_prompt(cluster, visual_assets or [])
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise OllamaAnalysisError(str(exc)) from exc

        body = response.json()
        raw_response = compact_text(body.get("response"))
        parsed = self._parse_json(raw_response)
        topics = parsed.get("topics", [])
        if not isinstance(topics, list):
            raise OllamaAnalysisError("Ollama response did not contain a valid topics list")
        return [topic for topic in topics if isinstance(topic, dict)]

    def _build_prompt(self, cluster: list[PreparedArticle], visual_assets: list[VisualAsset]) -> str:
        articles_payload = [
            {
                "article_id": str(item.article.id),
                "source_name": item.source_name,
                "source_slug": item.source_slug,
                "published_at": item.timestamp.isoformat(),
                "category": item.normalized_category,
                "title": item.article.title,
                "image_url": item.article.image_url,
                "tags": sorted(item.tag_tokens),
                "analysis_text": item.analysis_text[:700],
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
                    "headline_tr": "Kısa ve çarpıcı Türkçe başlık, 12 kelimeyi geçmesin",
                    "summary_tr": "2-3 cümle Türkçe özet, ne oldu kısa ve net",
                    "key_points_tr": ["Ana gelişme 1", "Gelişme 2", "Gelişme 3"],
                    "why_it_matters_tr": "Neden önemli, 1 cümle",
                    "confidence": 0.84,
                    "video_prompt_en": "English creative brief for video production",
                    "video_prompt_parts": {
                        "format_hint": "Format or creative direction",
                        "story_angle": "English story angle",
                        "visual_brief": "English visual brief",
                        "motion_treatment": "How motion should feel",
                        "transition_style": "How transitions should behave",
                        "scene_sequence": ["Scene 1", "Scene 2", "Scene 3"],
                        "tone": "Urgent and factual",
                        "design_keywords": ["keyword 1", "keyword 2"],
                        "must_include": ["Fact 1", "Fact 2"],
                        "avoid": ["Logos", "Watermarks"],
                        "duration_seconds": 18,
                    },
                    "video_plan": {
                        "title": "Short English title for the master video",
                        "audience_mode": "sound_off_first",
                        "master_format": "16:9",
                        "duration_seconds": 18,
                        "pacing_hint": "fast",
                        "source_visibility": "none",
                        "scenes": [
                            {
                                "scene_id": "scene-1",
                                "purpose": "hook",
                                "duration_seconds": 8,
                                "layout_hint": "headline",
                                "headline": "Short scene headline",
                                "body": "1-2 short factual sentences that appear on screen",
                                "supporting_points": ["Point 1", "Point 2"],
                                "key_figures": ["Name 1", "Name 2"],
                                "key_data": "Single key number or fact",
                                "visual_direction": "How this scene should look",
                                "motion_direction": "How this scene should move",
                                "transition_from_previous": "How it should arrive",
                                "source_line": "Optional subtle source line",
                                "asset_ids": ["asset-1"],
                            }
                        ],
                    },
                }
            ]
        }

        return (
            "You are analyzing news coverage gathered in the last hour from multiple publishers.\n"
            "Group only articles that describe the same concrete event or development.\n"
            "If the candidate cluster actually contains different stories, split it into separate topics.\n"
            "Do not include groups backed by fewer than two unique sources.\n"
            "Write headline_tr, summary_tr, key_points_tr, and why_it_matters_tr in Turkish.\n"
            "Write video_prompt_en, video_prompt_parts, and video_plan in English.\n\n"
            "CRITICAL — video_plan:\n"
            "- This is the actual master-video plan that another renderer will follow.\n"
            "- Decide the number of scenes yourself. Use 1 to 4 scenes.\n"
            "- The total duration must be between 8 and 30 seconds.\n"
            "- The video is for YouTube / Instagram style distribution, but should be planned as one reusable 16:9 master video.\n"
            "- The video must be sound-off first: viewers should understand it clearly without voiceover.\n"
            "- If the story is short and clear, prefer 1 scene.\n"
            "- Do not add extra scenes just to force a hook/explain/takeaway structure.\n"
            "- Only show information directly related to the topic. Do not overload the viewer.\n"
            "- Each scene must add a genuinely new piece of information or a new visual perspective.\n"
            "- Choose purpose values from: hook, explain, detail, context, comparison, takeaway, close.\n"
            "- Choose layout_hint values from: headline, split, stat, timeline, quote, comparison, minimal, full-bleed.\n"
            "- source_visibility should be none, subtle, or contextual.\n"
            "- Default source_visibility to none. Source lines are optional and should almost always stay empty.\n"
            "- Do not mention publisher names in scene headlines, bodies, or supporting points.\n"
            "- visual_direction and motion_direction should help the renderer create a pleasing scene, but must remain grounded in the topic.\n"
            "- Use asset_ids only from the available_assets list below. Use [] if no asset is needed.\n"
            "- For very short videos, reusing one strong hero image is often enough.\n"
            "- Prefer concise, readable on-screen copy. Avoid vague filler like 'important developments' or 'key moments' without specifics.\n\n"
            "CRITICAL — video_prompt_en:\n"
            "- This is a creative brief for humans, not the literal on-screen text.\n"
            "- It should describe the tone, look, motion language, and editorial intent of the master video.\n\n"
            "For sports, mention score and decisive player or moment. For business, mention trigger and visible impact. "
            "For world/general news, emphasize event sequence and immediate public implication.\n"
            "Return JSON only. Follow this shape exactly:\n"
            f"{json.dumps(schema, ensure_ascii=True)}\n"
            "If no shared story exists, return {\"topics\": []}.\n"
            f"Available assets:\n{json.dumps(assets_payload, ensure_ascii=True)}\n"
            f"Articles:\n{json.dumps(articles_payload, ensure_ascii=True)}"
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
    entities = build_prompt_entities(
        cluster,
        headline=headline,
        summary=summary,
        key_points=key_points,
    )
    sources = entities["sources"]
    representative_titles = [truncate_for_prompt(item.article.title, 70) for item in cluster[:3]]
    score = entities["score"]
    matchup = entities["matchup"]
    focus_entity = entities["focus_entity"]
    numeric_phrase = entities["numeric_phrase"]
    top_key_point = entities["top_key_point"] or truncate_for_prompt(summary, 96)
    supporting_key_points = entities["supporting_key_points"]
    focus_names = entities["names"]
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
        summary=summary,
        key_points=key_points,
        comparison_story=comparison_story,
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
                f"Turn {matchup or truncate_for_prompt(headline, 72)} into a sharp, emotionally readable sports moment"
                f"{f' with the {score} result visible throughout' if score else ''}"
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
                f"Open on a bold scoreboard lockup for {matchup or truncate_for_prompt(headline, 56)}"
                f"{f' with {score} anchored in the center' if score else ''}.",
                f"Punch into the decisive moment with a player-led spotlight"
                f"{f' on {focus_entity}' if focus_entity else ''} and short on-screen language around: {top_key_point}.",
                "Finish on a momentum-rich result card that feels like the final beat of a highlight package, not a newsroom recap.",
            ]
            design_keywords = ["broadcast polish", "kinetic typography", "score bug", "stadium glow", "snap zooms"]
        else:
            format_hint = "Premium social-first sports update"
            focal_phrase = focus_entity or truncate_for_prompt(headline, 48)
            if story_subtype == "schedule":
                story_angle = (
                    f"Turn {truncate_for_prompt(headline, 76)} into a clear schedule-driven sports update centered on {focal_phrase}, "
                    "using date and venue information without forcing a matchup recap."
                )
            elif story_subtype == "odds":
                story_angle = (
                    f"Explain {truncate_for_prompt(headline, 76)} as a betting-and-expectations sports update centered on {focal_phrase}, "
                    "without pretending a game result already happened."
                )
            elif story_subtype == "admin":
                story_angle = (
                    f"Tell {truncate_for_prompt(headline, 76)} as an off-field sports development centered on {focal_phrase}, "
                    "with editorial clarity instead of scoreboard energy."
                )
            else:
                story_angle = (
                    f"Tell {truncate_for_prompt(headline, 76)} as a short, human sports update"
                    f"{f' centered on {focus_entity}' if focus_entity else ''}, without forcing a matchup or scoreboard framing."
                )
            story_angle = (
                story_angle
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
                f"Open on a strong portrait or training visual with the headline {truncate_for_prompt(headline, 58)}.",
                f"Add one short support beat that explains the update clearly: {top_key_point}.",
                "Only add a final beat if it introduces genuinely new context, otherwise let the first image and headline carry the story.",
            ]
            design_keywords = ["editorial sports", "hero portrait", "clean typography", "subtle stadium texture", "calm motion"]
        must_include = dedupe_preserve_order(
            ([matchup] if matchup else [])
            + ([score] if score else [])
            + ([focus_entity] if focus_entity else [])
            + representative_titles[:2]
        )
        tone = "High-energy, premium, and emotionally clear"
    elif category == "business":
        if story_subtype == "market":
            format_hint = "Editorial financial explainer with premium motion graphics"
            story_angle = (
                f"Frame {truncate_for_prompt(headline, 78)} as a crisp market narrative with one clear trigger and one clear consequence"
                f"{f', centering {numeric_phrase} as the most visible data point' if numeric_phrase else ''}."
            )
            visual_brief = (
                "Use elegant dark-finance UI panels, glowing charts, restrained glass surfaces, and clean directional arrows. "
                "It should feel closer to a premium Bloomberg-style promo than a static market card."
            )
            motion_treatment = "Smooth value-counting, layered chart parallax, sliding data panes, and restrained camera drift."
            transition_style = "Glass panel wipes, soft chart morphs, ticker pulls, and clean numeric snap-ins."
            scene_sequence = [
                "Open with a single commanding market card that states the move and the tension immediately.",
                f"Show the trigger and the reaction as a clear visual chain, led by: {top_key_point}.",
                f"Close on a poised outlook board hinting at what traders or observers watch next: {truncate_for_prompt(why_it_matters, 96)}.",
            ]
            design_keywords = ["glassmorphism", "market UI", "chart glow", "directional arrows", "editorial finance"]
            tone = "Analytical, premium, and composed"
        else:
            format_hint = "Editorial business explainer with restrained motion graphics"
            story_angle = (
                f"Explain {truncate_for_prompt(headline, 78)} as a direct business update focused on the main actor, the immediate development, "
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
                f"Add the clearest supporting detail with a labeled explainer card: {top_key_point}.",
                f"Close on the practical implication or next decision to watch: {truncate_for_prompt(why_it_matters, 96)}.",
            ]
            design_keywords = ["editorial business", "clean panels", "newsroom typography", "restrained motion", "clear labels"]
            tone = "Clear, premium, and informative"
        must_include = dedupe_preserve_order(
            focus_names[:2] + ([numeric_phrase] if numeric_phrase and story_subtype == "market" else []) + representative_titles[:2]
        )
    elif category == "science":
        format_hint = "Cinematic editorial science explainer"
        story_angle = (
            f"Treat {truncate_for_prompt(headline, 80)} as a milestone story with wonder, clarity, and technical confidence."
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
    elif category in {"world", "politics", "general"}:
        format_hint = "Editorial breaking-news short with strong typography"
        story_angle = (
            f"Deliver {truncate_for_prompt(headline, 82)} as an editorial news short that feels urgent, human, and visually disciplined."
        )
        visual_brief = (
            "Use bold typography, cropped documentary-style framing, editorial color fields, and scene cards that make the event readable without relying on logos or source screenshots."
        )
        motion_treatment = "Measured push-ins, kinetic headline swaps, subtle tilt, and crisp card choreography."
        transition_style = "Editorial wipes, iris reveals, typography pushes, and restrained whip transitions."
        scene_sequence = [
            "Open with the main development and the most important actor or location in one bold headline panel.",
            f"Lay out the event sequence in two or three factual cards, anchored by: {top_key_point}.",
            f"Close with the immediate implication and what to watch next, staying human and clear: {truncate_for_prompt(why_it_matters, 96)}.",
        ]
        design_keywords = ["editorial typography", "news texture", "headline cards", "measured motion", "documentary framing"]
        must_include = dedupe_preserve_order(focus_names[:3] + supporting_key_points[:1] + representative_titles[:2])
        tone = "Urgent, human, and highly legible"
    else:
        format_hint = "Modern motion-graphics explainer"
        story_angle = (
            f"Explain {truncate_for_prompt(headline, 80)} with a clean headline-led structure, one supporting detail panel, "
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
            f"Close with why it matters and the next thing to watch, based on {truncate_for_prompt(why_it_matters, 90)}.",
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

    return VideoPromptParts(
        format_hint=format_hint,
        story_angle=story_angle,
        visual_brief=visual_brief,
        motion_treatment=motion_treatment,
        transition_style=transition_style,
        scene_sequence=scene_sequence[:4],
        tone=tone,
        design_keywords=design_keywords[:6],
        must_include=must_include[:5] or representative_titles[:3],
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
    entities = build_prompt_entities(
        cluster,
        headline=headline,
        summary=summary,
        key_points=key_points,
    )
    source_names = unique_source_names(cluster)
    clean_headline = trim_words(
        clean_viewer_text(headline, source_names=source_names, max_sentences=1, max_chars=88) or headline,
        10,
    )
    clean_summary = clean_viewer_text(summary, source_names=source_names, max_sentences=2, max_chars=150)
    clean_points = clean_viewer_points(key_points, source_names=source_names, max_items=2, max_chars=88)
    clean_why = clean_viewer_text(
        why_it_matters,
        source_names=source_names,
        max_sentences=1,
        max_chars=120,
    ) or build_why_it_matters_line(category)
    key_figures = entities["names"][:4]
    key_data = entities["score"] or entities["numeric_phrase"] or ""
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
        summary=clean_summary or summary,
        key_points=clean_points,
        comparison_story=comparison_story,
    )
    comparison_story = story_subtype == "matchup"
    duration_seconds = clamp_video_duration(prompt_parts.duration_seconds)
    scene_count = suggest_scene_count(
        clean_summary or summary,
        clean_points,
        category=category,
        comparison_story=comparison_story,
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
            body=clean_summary,
            supporting_points=[],
            key_figures=key_figures[:3],
            key_data=key_data,
            visual_direction=truncate_text(prompt_parts.visual_brief, 120),
            motion_direction=truncate_text(prompt_parts.motion_treatment, 120),
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

    if scene_count >= 2:
        explain_layout = default_layout_for_scene(
            category=category,
            purpose="explain",
            key_data=key_data,
            key_figures=key_figures,
            comparison_story=comparison_story,
            has_visual_assets=bool(visual_assets),
        )
        explain_headline = trim_words(
            clean_points[0] if clean_points else (clean_why if clean_why.lower() != clean_headline.lower() else clean_summary),
            10,
        )
        explain_body = (
            clean_points[1]
            if len(clean_points) > 1
            else (clean_why if clean_why.lower() != clean_summary.lower() else "")
        )
        scenes.append(
            VideoPlanScene(
                scene_id="scene-2",
                purpose="explain",
                duration_seconds=scene_durations[1],
                layout_hint=explain_layout,
                headline=explain_headline,
                body=explain_body,
                supporting_points=clean_points[:2],
                key_figures=key_figures[:3],
                key_data=key_data if explain_layout == "stat" else "",
                visual_direction=truncate_text(prompt_parts.visual_brief, 120),
                motion_direction=truncate_text(prompt_parts.motion_treatment, 120),
                transition_from_previous=truncate_text(prompt_parts.transition_style, 80),
                source_line="",
                asset_ids=default_asset_ids_for_scene(
                    index=1,
                    scene_count=scene_count,
                    layout_hint=explain_layout,
                    visual_assets=visual_assets,
                ),
            )
        )

    if scene_count >= 3:
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
                headline=trim_words(clean_why, 10),
                body=clean_why,
                supporting_points=[],
                key_figures=key_figures[:2],
                key_data="",
                visual_direction=truncate_text(prompt_parts.visual_brief, 120),
                motion_direction=truncate_text(prompt_parts.motion_treatment, 120),
                transition_from_previous=truncate_text(prompt_parts.transition_style, 80),
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
        title=truncate_text(clean_headline, 88),
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
            summary=summary,
            key_points=key_points,
            comparison_story=comparison_story,
        )
        == "matchup"
    )

    for index, item in enumerate(raw_scenes[:4]):
        if not isinstance(item, dict):
            continue
        purpose = compact_text(str(item.get("purpose", ""))).lower()
        layout_hint = compact_text(str(item.get("layout_hint", ""))).lower()
        headline_value = trim_words(
            clean_viewer_text(
                str(item.get("headline", "")),
                source_names=source_names,
                max_sentences=1,
                max_chars=84,
            ),
            10,
        )
        if purpose not in VALID_VIDEO_PLAN_PURPOSES or layout_hint not in VALID_VIDEO_PLAN_LAYOUTS or not headline_value:
            continue
        supporting_points = clean_viewer_points(
            coerce_list(item.get("supporting_points")),
            source_names=source_names,
            max_items=2,
            max_chars=88,
        )
        body_value = clean_viewer_text(
            str(item.get("body", "")),
            source_names=source_names,
            max_sentences=2,
            max_chars=150,
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
                supporting_points=supporting_points,
                key_figures=coerce_list(item.get("key_figures"))[:4],
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


def build_video_content_from_plan(plan: VideoPlan) -> VideoContent:
    narrative = dedupe_preserve_order(
        [
            clean_viewer_text(scene.body or scene.headline, max_sentences=1, max_chars=120)
            for scene in plan.scenes
            if compact_text(scene.body or scene.headline)
        ]
    )[:3]
    key_figures = dedupe_preserve_order(
        [figure for scene in plan.scenes for figure in scene.key_figures]
    )[:4]
    key_data = next((compact_text(scene.key_data) for scene in plan.scenes if compact_text(scene.key_data)), "")

    return VideoContent(
        headline=plan.title,
        narrative=narrative,
        key_figures=key_figures,
        key_data=key_data,
        source_line="",
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
    representative_titles = [truncate_text(item.article.title, 72) for item in cluster[:4]]
    facts = dedupe_preserve_order(
        ([entities["score"]] if entities["score"] else [])
        + entities["names"][:3]
        + [truncate_text(item, 28) for item in prompt_parts.must_include[:3]]
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
            truncate_text(prompt_parts.format_hint, 80),
            truncate_text(prompt_parts.visual_brief, 80),
            truncate_text(prompt_parts.motion_treatment, 80),
            truncate_text(prompt_parts.transition_style, 80),
        ],
        stats=stats[:4],
        article_count=len(cluster),
        video_plan=video_plan,
        video_content=build_video_content_from_plan(video_plan),
        visual_assets=visual_assets,
    )
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

    # Pick the shortest, most direct title as headline
    titles = [item.article.title for item in cluster if item.article.title]
    headline_tr = clean_viewer_text(min(titles, key=len) if titles else representative.article.title, source_names=source_names, max_sentences=1, max_chars=88)
    headline_tr = trim_words(headline_tr or representative.article.title, 10)

    cleaned_summaries = dedupe_preserve_order(
        [
            clean_viewer_text(
                compact_text(item.article.summary) or compact_text(item.article.title),
                source_names=source_names,
                max_sentences=1,
                max_chars=140,
            )
            for item in cluster[:3]
        ]
    )
    summary_tr = " ".join(cleaned_summaries[:2]) or headline_tr

    key_points_tr = clean_viewer_points(
        [item.article.title for item in cluster[:3]],
        source_names=source_names,
        max_items=2,
        max_chars=96,
    )
    why_it_matters_tr = build_why_it_matters_line(category)

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
    video_content = build_video_content_from_plan(video_plan)
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
        return fallback_topic
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

    return AnalysisDebug(
        fetched_articles=len(articles),
        prepared_articles=len(prepared_articles),
        rejected_articles=sum(1 for rejection in (rejections or []) if rejection.stage == "article"),
        candidate_clusters=len(candidate_clusters),
        multi_source_clusters=multi_source_clusters,
        single_source_clusters=single_source_clusters,
        shared_topics_generated=shared_topics_generated,
        unique_topics_generated=unique_topics_generated,
        rejected_unique_candidates=rejected_unique_candidates,
        dropped_unique_articles=dropped_unique_articles,
        source_breakdown=source_breakdown,
        cluster_previews=cluster_previews,
        rejection_breakdown=[
            AnalysisRejectionDebug(reason=reason, count=count)
            for reason, count in sorted(rejection_counts.items(), key=lambda item: (-item[1], item[0]))
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
    headline_tr = clean_viewer_text(str(payload.get("headline_tr", "")), source_names=unique_sources, max_sentences=1, max_chars=88) or cluster[0].article.title
    headline_tr = trim_words(headline_tr, 10)
    summary_tr = clean_viewer_text(str(payload.get("summary_tr", "")), source_names=unique_sources, max_sentences=2, max_chars=150) or (
        fallback_topic.summary_tr if fallback_topic else cluster[0].article.title
    )
    key_points_tr = clean_viewer_points(
        coerce_list(payload.get("key_points_tr")),
        source_names=unique_sources,
        max_items=2,
        max_chars=96,
    ) or clean_viewer_points(
        [item.article.title for item in cluster[:3]],
        source_names=unique_sources,
        max_items=2,
        max_chars=96,
    )
    why_it_matters_tr = clean_viewer_text(
        str(payload.get("why_it_matters_tr", "")),
        source_names=unique_sources,
        max_sentences=1,
        max_chars=120,
    ) or (
        build_why_it_matters_line(cluster[0].normalized_category)
    )
    category = cluster[0].normalized_category
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
    video_content = build_video_content_from_plan(video_plan)

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


def sort_topics(topics: list[TopicBrief]) -> list[TopicBrief]:
    return sorted(
        topics,
        key=lambda topic: (
            1 if topic.aggregation_type == "shared" else 0,
            max((article.published_at or datetime.min) for article in topic.representative_articles),
            topic.article_count,
            topic.confidence,
            topic.source_count,
        ),
        reverse=True,
    )


async def generate_topic_briefs(
    db: AsyncSession,
    *,
    source_category: str | None = None,
    category: str | None = None,
    hours: int = 1,
    limit_topics: int = 10,
    include_debug: bool = False,
) -> TopicBriefsResponse:
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
    debug_notes: list[str] = []
    ollama_error: str | None = None
    shared_topics_generated = 0
    unique_topics_generated = 0
    rejected_unique_candidates = 0
    dropped_unique_articles = 0
    if include_debug:
        debug_notes.append(
            f"Analysis caps: max {settings.ANALYSIS_MAX_ARTICLES_PER_SOURCE} article(s) per source and {settings.ANALYSIS_MAX_ARTICLES_PER_RUN} article(s) overall."
        )

    if not articles:
        if not articles:
            debug_notes.append("No articles matched the requested time window.")
        return TopicBriefsResponse(
            analysis_status="ok",
            generated_at=window_end,
            window_start=window_start,
            window_end=window_end,
            groups=[],
            debug=build_analysis_debug(
                articles=articles,
                prepared_articles=prepared_articles,
                candidate_clusters=candidate_clusters,
                rejections=analysis_rejections,
                notes=debug_notes,
                shared_topics_generated=shared_topics_generated,
                unique_topics_generated=unique_topics_generated,
                rejected_unique_candidates=rejected_unique_candidates,
                dropped_unique_articles=dropped_unique_articles,
            )
            if include_debug
            else None,
        )

    if not prepared_articles:
        debug_notes.append("Articles were fetched, but none survived category or text preparation.")
        return TopicBriefsResponse(
            analysis_status="ok",
            generated_at=window_end,
            window_start=window_start,
            window_end=window_end,
            groups=[],
            debug=build_analysis_debug(
                articles=articles,
                prepared_articles=prepared_articles,
                candidate_clusters=candidate_clusters,
                rejections=analysis_rejections,
                notes=debug_notes,
                shared_topics_generated=shared_topics_generated,
                unique_topics_generated=unique_topics_generated,
                rejected_unique_candidates=rejected_unique_candidates,
                dropped_unique_articles=dropped_unique_articles,
            )
            if include_debug
            else None,
        )

    shared_clusters, unique_candidate_clusters, singleton_clusters = partition_clusters(
        prepared_articles,
        candidate_clusters,
    )
    unique_candidate_clusters = unique_candidate_clusters + singleton_clusters

    if include_debug:
        if shared_clusters:
            debug_notes.append(f"{len(shared_clusters)} shared candidate cluster(s) qualified for merged topic generation.")
        if unique_candidate_clusters:
            debug_notes.append(f"{len(unique_candidate_clusters)} unique cluster(s) qualified for single-topic prompt generation.")
        if singleton_clusters:
            debug_notes.append(f"{len(singleton_clusters)} unclustered article(s) were converted into unique prompt candidates.")

    llm_analyzer = OllamaTopicAnalyzer()
    asset_resolver = VisualAssetResolver()
    analysis_status = "ok"
    llm_available = True
    topics: list[TopicBrief] = []

    for cluster in shared_clusters:
        visual_assets = await resolve_visual_assets_for_cluster(cluster, asset_resolver)

        if llm_available:
            try:
                llm_topics = await llm_analyzer.analyze_cluster(cluster, visual_assets)
            except OllamaAnalysisError as exc:
                logger.warning("Ollama topic analysis degraded: %s", exc)
                llm_available = False
                analysis_status = "degraded"
                ollama_error = str(exc)
                debug_notes.append(f"Ollama analysis failed: {exc}")
                llm_topics = []
        else:
            llm_topics = []

        if llm_available and llm_topics:
            lookup = {str(item.article.id): item for item in cluster}
            cluster_topics = [
                build_topic_from_llm_payload(
                    lookup,
                    payload,
                    visual_assets,
                    aggregation_type="shared",
                )
                for payload in llm_topics
            ]
            cluster_topics = [topic for topic in cluster_topics if topic is not None]
            if cluster_topics:
                topics.extend(cluster_topics)
                shared_topics_generated += len(cluster_topics)
                continue
            fallback_topic = build_fallback_topic(cluster, visual_assets, aggregation_type="shared")
            if fallback_topic:
                analysis_status = "degraded"
                topics.append(fallback_topic)
                shared_topics_generated += 1
                continue

        if not llm_available:
            fallback_topic = build_fallback_topic(cluster, visual_assets, aggregation_type="shared")
            if fallback_topic:
                topics.append(fallback_topic)
                shared_topics_generated += 1
            continue

    for cluster in unique_candidate_clusters:
        rejection_reason = unique_candidate_rejection_reason(cluster)
        if rejection_reason:
            representative = cluster[0].article
            analysis_rejections.append(
                make_rejection(
                    rejection_reason,
                    stage="unique_candidate",
                    title=representative.title,
                    url=representative.url,
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
            topics.append(unique_topic)
            unique_topics_generated += 1
        else:
            representative = cluster[0].article
            analysis_rejections.append(
                make_rejection(
                    "low_signal_unique",
                    stage="unique_candidate",
                    title=representative.title,
                    url=representative.url,
                )
            )
            rejected_unique_candidates += 1

    total_unique_candidate_articles = sum(len(cluster) for cluster in unique_candidate_clusters)

    topics = sort_topics(topics)
    limited_topics = topics[:limit_topics]
    returned_unique_articles = sum(
        topic.article_count
        for topic in limited_topics
        if topic.aggregation_type == "unique"
    )
    dropped_unique_articles = max(0, total_unique_candidate_articles - returned_unique_articles)
    topics = limited_topics

    groups_by_category: dict[str, list[TopicBrief]] = defaultdict(list)
    for topic in topics:
        groups_by_category[topic.category].append(topic)

    groups = [
        TopicGroup(category=group_category, topics=sort_topics(group_topics))
        for group_category, group_topics in groups_by_category.items()
    ]
    groups.sort(key=lambda group: len(group.topics), reverse=True)

    if not topics:
        if unique_candidate_clusters:
            debug_notes.append("Unique prompt candidates existed, but no unique topics were returned after processing.")
        if shared_clusters and llm_available:
            debug_notes.append(
                "Shared clusters existed, but no shared topics were returned after model parsing."
            )
        if not shared_clusters and not unique_candidate_clusters:
            debug_notes.append(
                "Articles were fetched, but no promptable shared or unique topics could be formed."
            )
    else:
        if not shared_topics_generated and unique_topics_generated:
            debug_notes.append("No shared topics were found, so the response contains only unique prompts.")
        if dropped_unique_articles:
            debug_notes.append(
                f"{dropped_unique_articles} unique article(s) were omitted from the final response after applying limit_topics={limit_topics}."
            )
        if rejected_unique_candidates:
            debug_notes.append(
                f"{rejected_unique_candidates} unique candidate(s) were rejected by quality guardrails before rendering."
            )
        rejected_articles = sum(1 for rejection in analysis_rejections if rejection.stage == "article")
        if rejected_articles:
            debug_notes.append(
                f"{rejected_articles} article(s) were filtered out before clustering because they looked non-news, stale, or malformed."
            )

    return TopicBriefsResponse(
        analysis_status=analysis_status,
        generated_at=window_end,
        window_start=window_start,
        window_end=window_end,
        groups=groups,
        debug=build_analysis_debug(
            articles=articles,
            prepared_articles=prepared_articles,
            candidate_clusters=candidate_clusters,
            rejections=analysis_rejections,
            notes=debug_notes,
            ollama_error=ollama_error,
            shared_topics_generated=shared_topics_generated,
            unique_topics_generated=unique_topics_generated,
            rejected_unique_candidates=rejected_unique_candidates,
            dropped_unique_articles=dropped_unique_articles,
        )
        if include_debug
        else None,
    )
