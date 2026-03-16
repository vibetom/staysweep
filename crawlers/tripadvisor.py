"""
TripAdvisor Crawler Agent
--------------------------
Crawls TripAdvisor hotel listings for a given city.
Extracts: hotel names, URLs, ratings, review snippets, photo URLs.

NOTE: TripAdvisor actively fights scraping. This crawler uses:
  - Polite delays
  - Real browser user-agents
  - Graceful fallback when blocked (returns mock data in prototype mode)
"""

import os
import re
from urllib.parse import urljoin, quote_plus
from rich.console import Console
from .base import BaseCrawler

MAX_HOTELS = int(os.getenv("MAX_HOTELS_PER_SOURCE", "20"))

console = Console()

TRIPADVISOR_BASE = "https://www.tripadvisor.com"


class TripAdvisorCrawler(BaseCrawler):
    source_name = "tripadvisor"
    min_delay = 2.0
    max_delay = 5.0

    async def crawl_city(self, city: str, db) -> list[dict]:
        console.print(f"[bold blue]🕷 TripAdvisor[/] crawling hotels in [italic]{city}[/]...")
        results = []

        search_url = f"{TRIPADVISOR_BASE}/Search?q={quote_plus(city + ' hotels')}&searchSessionId=x"
        soup = await self.fetch_html(search_url)

        if soup is None:
            console.print("[yellow]⚠ TripAdvisor blocked or unreachable — skipping[/]")
            return []

        # Try to parse real listing cards
        cards = soup.select('[data-automation="hotel-card-title"]') or \
                soup.select('.listing_title') or \
                soup.select('a[href*="/Hotel_Review"]')

        if not cards:
            console.print("[yellow]⚠ TripAdvisor: no cards found (likely JS-gated) — skipping[/]")
            return []

        for card in cards[:MAX_HOTELS]:
            href = card.get("href", "")
            if not href.startswith("http"):
                href = urljoin(TRIPADVISOR_BASE, href)
            name = card.get_text(strip=True) or "Unknown Hotel"
            results.append({
                "name": name,
                "source": self.source_name,
                "source_url": href,
                "city": city,
                "rating": None,
                "reviews": [],
                "images": [],
            })

        # For prototype: try fetching first hotel's detail page for reviews/images
        if results:
            await self._enrich_hotel(results[0])

        console.print(f"[green]✓ TripAdvisor[/] found {len(results)} hotels")
        return results

    async def _enrich_hotel(self, hotel: dict):
        """Fetch detail page to get reviews and images."""
        soup = await self.fetch_html(hotel["source_url"])
        if not soup:
            return

        # Reviews
        review_els = soup.select('[data-test-target="review-body"]') or \
                     soup.select('.partial_entry') or \
                     soup.select('.review-container .entry')
        for el in review_els[:10]:
            text = el.get_text(strip=True)
            if len(text) > 30:
                hotel["reviews"].append({
                    "text": text,
                    "source": self.source_name,
                    "review_url": hotel["source_url"],
                })

        # Images
        img_els = soup.select('img[src*="media-cdn.tripadvisor"]') or \
                  soup.select('img[data-src*="tripadvisor"]')
        for img in img_els[:15]:
            src = img.get("src") or img.get("data-src", "")
            if src and "media-cdn" in src:
                hotel["images"].append({
                    "url": src,
                    "source": self.source_name,
                    "image_type": "official",
                    "caption": img.get("alt", ""),
                })

