from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from bs4 import BeautifulSoup

from app.scrapers.discovery_utils import (
    absolute_url,
    flatten_json_ld,
    load_json_safely,
    parse_datetime_to_utc_naive,
    same_host,
    strip_html_like_text,
    to_list,
)


ARTICLE_TYPES = {
    "article",
    "newsarticle",
    "blogposting",
    "reportagenewsarticle",
    "liveblogposting",
}

META_TITLE_KEYS = ("og:title", "twitter:title")
META_DESCRIPTION_KEYS = ("description", "og:description", "twitter:description")
META_IMAGE_KEYS = ("og:image", "twitter:image", "parsely-image-url")
META_AUTHOR_KEYS = ("author", "article:author", "parsely-author")
META_SECTION_KEYS = ("article:section", "parsely-section")
META_KEYWORDS_KEYS = ("news_keywords", "keywords")
META_PUBLISHED_KEYS = ("article:published_time", "og:published_time", "parsely-pub-date")


class ArticleMetadataExtractor:
    def extract_article_metadata(self, html: str, page_url: str | None = None) -> dict:
        soup = BeautifulSoup(html, "lxml")
        json_ld_article = self._find_article_json_ld(soup)
        metadata = self._extract_from_json_ld(json_ld_article)

        title = metadata.get("title") or self._find_meta_content(soup, META_TITLE_KEYS)
        summary = metadata.get("summary") or self._find_meta_content(soup, META_DESCRIPTION_KEYS)
        image_url = metadata.get("image_url") or self._find_meta_content(soup, META_IMAGE_KEYS)
        author = metadata.get("author") or self._find_meta_content(soup, META_AUTHOR_KEYS)
        category = metadata.get("category") or self._find_meta_content(soup, META_SECTION_KEYS)
        published_at = metadata.get("published_at") or parse_datetime_to_utc_naive(
            self._find_meta_content(soup, META_PUBLISHED_KEYS)
        )
        tags = metadata.get("tags") or self._parse_keywords(
            self._find_meta_content(soup, META_KEYWORDS_KEYS)
        )

        if not title and soup.title and soup.title.string:
            title = strip_html_like_text(soup.title.string)

        return {
            "title": strip_html_like_text(title),
            "summary": strip_html_like_text(summary),
            "author": strip_html_like_text(author),
            "published_at": published_at,
            "image_url": image_url,
            "category": strip_html_like_text(category),
            "tags": tags or None,
            "raw_metadata": {
                "page_url": page_url,
                "json_ld_detected": bool(json_ld_article),
            },
        }

    def extract_links_from_listing(
        self,
        html: str,
        base_url: str,
        *,
        exclude_url_substrings: Iterable[str] | None = None,
        require_date_path: bool = False,
    ) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        candidates: list[dict] = []
        excluded_parts = tuple(part.lower() for part in (exclude_url_substrings or []) if part)

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href")
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue

            url = absolute_url(base_url, href)
            if not same_host(url, base_url):
                continue
            if not self._looks_like_article_url(
                url,
                exclude_url_substrings=excluded_parts,
                require_date_path=require_date_path,
            ):
                continue

            title = strip_html_like_text(anchor.get_text(" ", strip=True))
            if not title or len(title) < 15:
                continue

            candidates.append({"url": url, "title": title})

        deduped: dict[str, dict] = {}
        for candidate in candidates:
            deduped.setdefault(candidate["url"], candidate)
        return list(deduped.values())

    def _find_article_json_ld(self, soup: BeautifulSoup) -> dict | None:
        for script in soup.find_all("script", attrs={"type": lambda value: value and "ld+json" in value}):
            payload = load_json_safely(script.get_text(strip=True))
            if payload is None:
                continue

            for node in flatten_json_ld(payload):
                node_type = node.get("@type")
                type_values = {str(value).lower() for value in to_list(node_type)}
                if ARTICLE_TYPES.intersection(type_values):
                    return node
        return None

    def _extract_from_json_ld(self, node: dict | None) -> dict:
        if not node:
            return {}

        image = node.get("image")
        image_url: str | None = None
        if isinstance(image, str):
            image_url = image
        elif isinstance(image, dict):
            image_url = image.get("url")
        elif isinstance(image, list):
            for item in image:
                if isinstance(item, str):
                    image_url = item
                    break
                if isinstance(item, dict) and item.get("url"):
                    image_url = item["url"]
                    break

        author = node.get("author")
        author_name: str | None = None
        if isinstance(author, str):
            author_name = author
        elif isinstance(author, dict):
            author_name = author.get("name")
        elif isinstance(author, list):
            names = [item.get("name") for item in author if isinstance(item, dict) and item.get("name")]
            if names:
                author_name = ", ".join(names)

        keywords = node.get("keywords")
        tags = self._parse_keywords(keywords)

        return {
            "title": node.get("headline") or node.get("name"),
            "summary": node.get("description"),
            "author": author_name,
            "published_at": parse_datetime_to_utc_naive(
                node.get("datePublished") or node.get("dateCreated")
            ),
            "image_url": image_url,
            "category": node.get("articleSection"),
            "tags": tags,
        }

    def _find_meta_content(self, soup: BeautifulSoup, names: tuple[str, ...]) -> str | None:
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return tag["content"]
        return None

    def _parse_keywords(self, raw_keywords: Any) -> list[str]:
        if raw_keywords is None:
            return []
        if isinstance(raw_keywords, list):
            return [strip_html_like_text(str(keyword)) for keyword in raw_keywords if strip_html_like_text(str(keyword))]
        return [
            keyword
            for keyword in (
                strip_html_like_text(part)
                for part in str(raw_keywords).replace("|", ",").split(",")
            )
            if keyword
        ]

    def _looks_like_article_url(
        self,
        url: str,
        *,
        exclude_url_substrings: tuple[str, ...] = (),
        require_date_path: bool = False,
    ) -> bool:
        lowered = url.lower()
        default_exclusions = (
            "/video/",
            "/videos/",
            "/live/",
            "/gallery/",
            "/tag/",
            "/tags/",
            "/authors/",
            "/author/",
            "/settings",
            "/news-alerts",
            "/sponsored",
            "/replay/",
            "/programs/",
        )
        if any(part in lowered for part in (*default_exclusions, *exclude_url_substrings)):
            return False

        path = lowered.split("://", 1)[-1].split("/", 1)[-1]
        segments = [segment for segment in path.split("/") if segment]
        if not segments:
            return False

        last_segment = segments[-1]
        has_slug = "-" in last_segment or len(last_segment) >= 18
        has_date_path = any(segment.isdigit() and len(segment) == 4 for segment in segments)
        if require_date_path:
            return has_date_path
        return has_slug or has_date_path
