import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Cache parsed robots.txt per domain
_cache: dict[str, RobotFileParser] = {}


async def fetch_robots_txt(domain: str) -> RobotFileParser:
    """Fetch and parse robots.txt for a domain."""
    if domain in _cache:
        return _cache[domain]

    rp = RobotFileParser()
    robots_url = f"https://{domain}/robots.txt"

    try:
        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": settings.USER_AGENT},
        ) as client:
            response = await client.get(robots_url)
            if response.status_code == 200:
                rp.parse(response.text.splitlines())
            else:
                # If no robots.txt, allow everything
                rp.allow_all = True
    except Exception as e:
        logger.warning(f"Could not fetch robots.txt for {domain}: {e}")
        rp.allow_all = True

    _cache[domain] = rp
    return rp


async def is_allowed(url: str) -> bool:
    """Check if the URL is allowed by robots.txt."""
    parsed = urlparse(url)
    rp = await fetch_robots_txt(parsed.netloc)
    return rp.can_fetch(settings.USER_AGENT, url)


def clear_cache():
    """Clear the robots.txt cache."""
    _cache.clear()
