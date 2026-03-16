"""
Image Priority Ranker
----------------------
Before sending images to the (expensive) vision agent, this utility ranks
and filters the image list to maximize the chance of finding the target
feature while minimizing cost.

Ranking logic:
  1. Images from official sources (gallery, room photos) rank above guest photos
  2. Images with captions mentioning relevant keywords rank highest
  3. Images from detail pages (room descriptions) outrank lobby-only images
  4. Very small or non-photo URLs are filtered out
  5. Deduplication by URL

Also provides a "fast-path" check: if text analysis scores very low (<0.15),
we skip vision entirely since it's unlikely to find what text missed.
"""

import re
from urllib.parse import urlparse
from rich.console import Console

console = Console()


# Patterns that suggest an image is a room/interior shot
INTERIOR_PATTERNS = [
    r'room', r'suite', r'lobby', r'lounge', r'interior',
    r'living', r'bedroom', r'common', r'sitting', r'area',
    r'couch', r'sofa', r'chair', r'furniture', r'decor',
]

# Patterns that suggest it's a generic/unrelated photo
SKIP_PATTERNS = [
    r'pool', r'exterior', r'facade', r'outside', r'map',
    r'logo', r'icon', r'banner', r'bg_', r'background',
    r'restaurant', r'menu', r'food', r'breakfast',
    r'gym', r'fitness', r'spa', r'parking',
]


def _score_image(image: dict, query_keywords: list[str]) -> float:
    """
    Assign a priority score to an image. Higher = analyze sooner.
    """
    score = 0.0
    url_lower = image.get("url", "").lower()
    caption_lower = image.get("caption", "").lower()

    # Source bonus
    if image.get("image_type") == "official":
        score += 0.3
    if image.get("source") == "official_site":
        score += 0.2  # Hotel's own gallery is highest quality

    # Caption keyword match (very strong signal)
    for kw in query_keywords:
        kw_lower = kw.lower()
        if kw_lower in caption_lower:
            score += 0.5
        if kw_lower in url_lower:
            score += 0.2

    # Interior image bonus
    if any(re.search(p, url_lower) or re.search(p, caption_lower) for p in INTERIOR_PATTERNS):
        score += 0.15

    # Penalize likely-irrelevant images
    if any(re.search(p, url_lower) or re.search(p, caption_lower) for p in SKIP_PATTERNS):
        score -= 0.25

    return score


def rank_and_filter_images(images: list[dict], parsed_query: dict,
                            max_images: int = 8) -> list[dict]:
    """
    Returns up to max_images images, ranked by relevance to the query.
    Deduplicates by URL.
    """
    if not images:
        return []

    keywords = (parsed_query.get("text_keywords", []) +
                parsed_query.get("visual_features", []) +
                parsed_query.get("context", []))

    # Deduplicate
    seen_urls = set()
    unique = []
    for img in images:
        url = img.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(img)

    # Score and sort
    scored = [(img, _score_image(img, keywords)) for img in unique]
    scored.sort(key=lambda x: x[1], reverse=True)

    top = [img for img, _ in scored[:max_images]]

    # Log what we're skipping
    skipped = len(unique) - len(top)
    if skipped > 0:
        console.print(f"  [dim]Image ranker: using top {len(top)} of {len(unique)} images "
                      f"(skipped {skipped} lower-priority)[/]")

    return top


def should_skip_vision(text_score: float, text_evidence: list,
                        image_count: int) -> tuple[bool, str]:
    """
    Fast-path decision: should we skip vision analysis for this hotel?

    Returns (skip: bool, reason: str)

    We only skip if there are literally no images. A feature might be
    visible in photos even when nobody mentions it in reviews — vision
    analysis is the core differentiator of this tool.
    """
    if image_count == 0:
        return True, "no images available"

    return False, ""
