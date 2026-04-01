import hashlib
import re


def normalize_url(url: str) -> str:
    """Normalize URL for consistent hashing."""
    url = url.strip().rstrip("/")
    # Remove common tracking parameters
    if "?" in url:
        base, params = url.split("?", 1)
        tracking_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_content",
            "utm_term", "ref", "fbclid", "gclid", "mc_cid", "mc_eid",
        }
        filtered = "&".join(
            p for p in params.split("&")
            if p.split("=")[0].lower() not in tracking_params
        )
        url = f"{base}?{filtered}" if filtered else base
    # Remove fragment
    url = url.split("#")[0]
    return url


def hash_url(url: str) -> str:
    """Generate SHA256 hash of normalized URL."""
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()


def normalize_title(title: str) -> str:
    """Normalize title for similarity comparison."""
    title = title.lower().strip()
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title


def titles_are_similar(title1: str, title2: str, threshold: float = 0.85) -> bool:
    """Check if two titles are similar using simple token overlap."""
    t1 = set(normalize_title(title1).split())
    t2 = set(normalize_title(title2).split())

    if not t1 or not t2:
        return False

    intersection = t1 & t2
    union = t1 | t2
    jaccard = len(intersection) / len(union)
    return jaccard >= threshold
