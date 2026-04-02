from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from urllib.parse import urljoin, urlparse

from dateutil import parser as dateparser

from app.scrapers.utils.deduplication import normalize_url


def dedupe_articles(articles: list[dict]) -> list[dict]:
    by_url: dict[str, dict] = {}

    for article in articles:
        normalized = normalize_url(article.get("url", ""))
        if not normalized:
            continue

        current = by_url.get(normalized)
        if current is None:
            cloned = dict(article)
            cloned["url"] = normalized
            by_url[normalized] = cloned
            continue

        for key, value in article.items():
            if key == "url":
                continue
            if current.get(key) in (None, "", [], {}):
                current[key] = value

    return list(by_url.values())


def parse_datetime_to_utc_naive(value: Any) -> datetime | None:
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = dateparser.parse(str(value))
        except (TypeError, ValueError, OverflowError):
            return None

    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def strip_html_like_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("name", "headline", "title", "description", "text", "value"):
            if key in value:
                return strip_html_like_text(value.get(key))
        return None
    if isinstance(value, (list, tuple, set)):
        parts = [strip_html_like_text(item) for item in value]
        joined = " ".join(part for part in parts if part)
        return " ".join(joined.split()) or None
    return " ".join(str(value).split()) or None


def to_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def flatten_json_ld(payload: Any) -> list[dict]:
    items: list[dict] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if "@graph" in node:
                visit(node["@graph"])
            else:
                items.append(node)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload)
    return items


def load_json_safely(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def same_host(candidate_url: str, base_url: str) -> bool:
    candidate_host = urlparse(candidate_url).netloc
    base_host = urlparse(base_url).netloc
    return bool(candidate_host and base_host and candidate_host.endswith(base_host))


def absolute_url(base_url: str, href: str) -> str:
    return normalize_url(urljoin(base_url, href))
