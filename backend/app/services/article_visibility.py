from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.sql import Select

from app.models.article import Article
from app.models.source import Source


DEFAULT_HIDDEN_URL_SUBSTRINGS = (
    "/video/",
    "/videos/",
    "/audio/",
    "/podcast/",
    "/live/",
)


def _normalize_parts(parts: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for part in parts or ():
        value = str(part or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def get_hidden_url_substrings_for_source(source: Source | None) -> list[str]:
    config = (source.config or {}) if source is not None else {}
    combined = list(DEFAULT_HIDDEN_URL_SUBSTRINGS)
    combined.extend(config.get("exclude_url_substrings") or [])
    combined.extend(config.get("skip_detail_url_substrings") or [])
    return _normalize_parts(combined)


def article_is_visible(article: Article) -> bool:
    source = article.source
    if source is None or not source.is_active:
        return False

    lowered_url = (article.url or "").lower()
    return not any(part in lowered_url for part in get_hidden_url_substrings_for_source(source))


def apply_article_visibility_filters(query: Select) -> Select:
    filtered = query.where(Source.is_active.is_(True))
    for part in DEFAULT_HIDDEN_URL_SUBSTRINGS:
        filtered = filtered.where(~Article.url.ilike(f"%{part}%"))
    return filtered
