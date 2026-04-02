from __future__ import annotations

import uuid
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.schemas.analysis import VisualAsset


def compact_text(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def truncate_text(value: str, limit: int = 140) -> str:
    compacted = compact_text(value)
    if len(compacted) <= limit:
        return compacted
    return f"{compacted[: max(0, limit - 3)].rstrip()}..."


@dataclass(slots=True)
class VisualAssetCandidate:
    article_id: uuid.UUID
    article_url: str
    title: str
    source_name: str | None = None
    image_url: str | None = None


def normalize_image_url(url: str | None, *, page_url: str | None = None) -> str:
    candidate = compact_text(url)
    if not candidate:
        return ""
    if candidate.startswith("//"):
        candidate = f"https:{candidate}"
    elif page_url:
        candidate = urljoin(page_url, candidate)

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if not parsed.netloc:
        return ""
    return candidate


def extract_open_graph_image(html: str, *, page_url: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    selectors = [
        ("meta", "property", "og:image"),
        ("meta", "name", "og:image"),
        ("meta", "property", "twitter:image"),
        ("meta", "name", "twitter:image"),
        ("link", "rel", "image_src"),
    ]
    for tag_name, attribute_name, attribute_value in selectors:
        tag = soup.find(tag_name, attrs={attribute_name: attribute_value})
        if not tag:
            continue
        raw_url = tag.get("content") or tag.get("href")
        normalized = normalize_image_url(raw_url, page_url=page_url)
        if normalized:
            return normalized
    return ""


class VisualAssetResolver:
    async def resolve(self, candidates: list[VisualAssetCandidate]) -> list[VisualAsset]:
        results: list[VisualAsset] = []
        seen_urls: set[str] = set()
        max_assets = settings.VISUAL_ASSET_MAX_PER_TOPIC

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.VISUAL_ASSET_FETCH_TIMEOUT_SECONDS, connect=3.0),
            headers={"User-Agent": settings.USER_AGENT},
            follow_redirects=True,
        ) as client:
            for candidate in candidates:
                if len(results) >= max_assets:
                    break

                image_url = normalize_image_url(candidate.image_url)
                kind = "article_image"
                if not image_url:
                    image_url = await self._fetch_open_graph_image(client, candidate.article_url)
                    kind = "og_image"

                if not image_url or image_url in seen_urls:
                    continue

                seen_urls.add(image_url)
                results.append(
                    VisualAsset(
                        asset_id=f"asset-{len(results) + 1}",
                        url=image_url,
                        kind=kind,
                        source_article_id=candidate.article_id,
                        source_name=candidate.source_name,
                        alt_text=truncate_text(
                            f"{candidate.source_name or 'News'}: {candidate.title}",
                            140,
                        ),
                    )
                )

        return results

    async def _fetch_open_graph_image(self, client: httpx.AsyncClient, page_url: str) -> str:
        try:
            response = await client.get(page_url)
            response.raise_for_status()
        except Exception:
            return ""
        return extract_open_graph_image(response.text, page_url=page_url)
