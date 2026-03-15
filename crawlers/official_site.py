"""
Official Hotel Website Crawler Agent
--------------------------------------
Given a hotel name and city, attempts to:
  1. Find the hotel's official website (via Google search or known patterns)
  2. Crawl the gallery/photos page for high-res official images
  3. Crawl the "rooms" or "amenities" page for room-level images

These are the highest-quality images — official photography with intentional
staging, which makes visual feature detection more reliable.

Strategy:
  - Try common URL patterns first (e.g. marriott.com/hotels/...)
  - Fall back to fetching the homepage and finding gallery links
  - Extract <img> tags from gallery pages, filter by size/quality heuristics
"""

import re
from urllib.parse import urljoin, urlparse
from rich.console import Console
from .base import BaseCrawler

console = Console()

# Common gallery page path patterns to try
GALLERY_PATHS = [
    "/photos", "/gallery", "/photo-gallery", "/photos-videos",
    "/rooms-suites/photos", "/accommodations/gallery",
    "/hotel/gallery", "/media/photos",
]

# Minimum image dimension hint from URL (skip thumbnails)
THUMBNAIL_PATTERNS = [
    r'thumb', r'tn_', r'_sm', r'_xs', r'50x', r'100x', r'150x',
    r'placeholder', r'icon', r'logo',
]


def looks_like_real_photo(url: str) -> bool:
    """Heuristically filter out logos, icons, and thumbnails."""
    url_lower = url.lower()
    return not any(re.search(p, url_lower) for p in THUMBNAIL_PATTERNS)


def extract_images_from_soup(soup, base_url: str, source_name: str, limit=20) -> list[dict]:
    """Extract all qualifying image URLs from a parsed page."""
    images = []
    seen = set()

    # Standard img tags
    for img in soup.select("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
        if not src:
            continue
        if not src.startswith("http"):
            src = urljoin(base_url, src)
        if src in seen:
            continue
        seen.add(src)

        if not looks_like_real_photo(src):
            continue

        # Only include images that appear to be photos (jpg, webp, jpeg)
        if not re.search(r'\.(jpg|jpeg|webp|png)(\?|$)', src, re.IGNORECASE):
            continue

        images.append({
            "url": src,
            "source": source_name,
            "image_type": "official",
            "caption": img.get("alt", "").strip(),
        })

        if len(images) >= limit:
            break

    return images


class OfficialWebsiteCrawler(BaseCrawler):
    source_name = "official_site"
    min_delay = 1.5
    max_delay = 3.0

    async def crawl_city(self, city: str, db) -> list[dict]:
        """
        For the official site crawler, we don't do city-wide search.
        Instead, enrich_hotel() is called per-hotel from the orchestrator
        after other crawlers have found the hotels.

        This method is a no-op for city-level crawling.
        """
        console.print(f"[dim]Official site crawler: skipping city-level crawl "
                      f"(called per-hotel during enrichment)[/]")
        return []

    async def enrich_hotel_with_official_photos(self, hotel: dict) -> list[dict]:
        """
        Given a hotel dict with name and city, try to find and crawl the
        official website for gallery images.

        Returns a list of image dicts.
        """
        hotel_name = hotel["name"]
        city = hotel["city"]

        console.print(f"  [cyan]🌐 Official site[/] crawling for {hotel_name}...")

        # Step 1: Attempt to construct likely official URL
        # (In production, use Google Search API: "site:hotelname.com gallery")
        candidate_urls = self._guess_official_urls(hotel_name, city)

        # Step 2: Try to find gallery page from homepage
        for base_url in candidate_urls:
            homepage = await self.fetch_html(base_url)
            if not homepage:
                continue

            # Look for gallery links on the homepage
            gallery_url = self._find_gallery_link(homepage, base_url)
            if gallery_url:
                gallery_soup = await self.fetch_html(gallery_url)
                if gallery_soup:
                    images = extract_images_from_soup(gallery_soup, gallery_url,
                                                       self.source_name, limit=15)
                    if images:
                        console.print(f"  [green]✓ Official site[/] found {len(images)} images "
                                      f"for {hotel_name}")
                        return images

            # Try gallery path patterns directly
            for path in GALLERY_PATHS:
                gallery_url = base_url.rstrip("/") + path
                gallery_soup = await self.fetch_html(gallery_url)
                if gallery_soup:
                    images = extract_images_from_soup(gallery_soup, gallery_url,
                                                       self.source_name, limit=15)
                    if images:
                        console.print(f"  [green]✓ Official site ({path})[/] found "
                                      f"{len(images)} images for {hotel_name}")
                        return images

        console.print(f"  [dim]Official site: no images found for {hotel_name}[/]")
        return []

    def _guess_official_urls(self, hotel_name: str, city: str) -> list[str]:
        """
        Generate candidate official URLs from the hotel name.
        Very rough heuristic — works for independents and small chains.
        Production version should use Google Custom Search API.
        """
        # Normalize name to URL slug
        slug = re.sub(r'[^a-z0-9]+', '-', hotel_name.lower()).strip('-')
        city_slug = re.sub(r'[^a-z0-9]+', '-', city.lower()).strip('-')

        candidates = [
            f"https://www.{slug}.com",
            f"https://{slug}.com",
            f"https://www.{slug}hotel.com",
            f"https://www.hotel{slug}.com",
        ]

        # Known major chain patterns
        chain_patterns = {
            "marriott": f"https://www.marriott.com/hotels/travel/{city_slug[:3]}-",
            "hilton": f"https://www.hilton.com/en/hotels/",
            "hyatt": f"https://www.hyatt.com/en-US/hotel/",
            "westin": f"https://www.marriott.com/hotels/travel/",
            "sheraton": f"https://www.marriott.com/hotels/travel/",
            "intercontinental": f"https://www.ihg.com/intercontinental/hotels/",
        }

        for keyword, base in chain_patterns.items():
            if keyword in hotel_name.lower():
                candidates.insert(0, base + slug)

        return candidates[:3]  # Try at most 3 to keep it fast

    def _find_gallery_link(self, soup, base_url: str) -> str | None:
        """Look for a gallery/photos link in the site navigation."""
        gallery_keywords = ["gallery", "photos", "photo", "images", "pictures", "media"]
        for a in soup.select("a[href]"):
            href = a.get("href", "").lower()
            text = a.get_text(strip=True).lower()
            if any(kw in href or kw in text for kw in gallery_keywords):
                full = a["href"] if a["href"].startswith("http") else urljoin(base_url, a["href"])
                return full
        return None
