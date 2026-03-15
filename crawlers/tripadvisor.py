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

import re
from urllib.parse import urljoin, quote_plus
from rich.console import Console
from .base import BaseCrawler

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
            console.print("[yellow]⚠ TripAdvisor blocked or unreachable — using prototype stub data[/]")
            return self._stub_data(city)

        # Try to parse real listing cards
        cards = soup.select('[data-automation="hotel-card-title"]') or \
                soup.select('.listing_title') or \
                soup.select('a[href*="/Hotel_Review"]')

        if not cards:
            console.print("[yellow]⚠ TripAdvisor: no cards found (likely JS-gated) — using prototype stub[/]")
            return self._stub_data(city)

        for card in cards[:8]:
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

    def _stub_data(self, city: str) -> list[dict]:
        """
        Prototype stub data — returns realistic-looking hotels for testing
        the analysis pipeline end-to-end when the crawler is blocked.
        """
        return [
            {
                "name": "The Grand Luxe Hotel",
                "source": self.source_name,
                "source_url": f"https://www.tripadvisor.com/Hotel_Review-stub-grand-luxe-{city.lower().replace(' ','_')}",
                "city": city,
                "rating": 4.5,
                "reviews": [
                    {"text": "The lobby was stunning with its dark purple velvet couches. I spent hours reading there. Very moody and atmospheric.",
                     "source": "tripadvisor", "review_url": "https://www.tripadvisor.com/stub1"},
                    {"text": "Rooms were clean and modern. The bar area had interesting purple accent furniture.",
                     "source": "tripadvisor", "review_url": "https://www.tripadvisor.com/stub2"},
                    {"text": "Nice hotel overall. Breakfast was excellent. The lounge has deep plum colored seating.",
                     "source": "tripadvisor", "review_url": "https://www.tripadvisor.com/stub3"},
                ],
                "images": [
                    {"url": "https://media-cdn.tripadvisor.com/stub/lobby1.jpg", "source": "tripadvisor",
                     "image_type": "official", "caption": "Hotel lobby with purple seating"},
                    {"url": "https://media-cdn.tripadvisor.com/stub/lounge1.jpg", "source": "tripadvisor",
                     "image_type": "guest", "caption": "The cozy lounge area"},
                ],
            },
            {
                "name": "Hotel Metropolitan",
                "source": self.source_name,
                "source_url": f"https://www.tripadvisor.com/Hotel_Review-stub-metropolitan-{city.lower().replace(' ','_')}",
                "city": city,
                "rating": 4.2,
                "reviews": [
                    {"text": "Standard business hotel. Clean rooms, nothing special about the decor.",
                     "source": "tripadvisor", "review_url": "https://www.tripadvisor.com/stub4"},
                    {"text": "Good location downtown. The conference rooms have modern furniture.",
                     "source": "tripadvisor", "review_url": "https://www.tripadvisor.com/stub5"},
                ],
                "images": [
                    {"url": "https://media-cdn.tripadvisor.com/stub/metro1.jpg", "source": "tripadvisor",
                     "image_type": "official", "caption": "Standard hotel room"},
                ],
            },
            {
                "name": "Boutique Inn & Suites",
                "source": self.source_name,
                "source_url": f"https://www.tripadvisor.com/Hotel_Review-stub-boutique-{city.lower().replace(' ','_')}",
                "city": city,
                "rating": 4.7,
                "reviews": [
                    {"text": "Absolutely loved this place. The sitting room off the lobby had the most amazing furniture — rich purple sofas and brass accents. Very instagrammable!",
                     "source": "tripadvisor", "review_url": "https://www.tripadvisor.com/stub6"},
                    {"text": "The decor is something else. Every room has unique pieces. Our suite had a gorgeous dark purple chesterfield sofa.",
                     "source": "tripadvisor", "review_url": "https://www.tripadvisor.com/stub7"},
                    {"text": "Best boutique hotel in the city. The owner clearly has a thing for deep jewel tones — lots of purple and emerald throughout.",
                     "source": "tripadvisor", "review_url": "https://www.tripadvisor.com/stub8"},
                ],
                "images": [
                    {"url": "https://media-cdn.tripadvisor.com/stub/boutique_lobby.jpg", "source": "tripadvisor",
                     "image_type": "official", "caption": "Boutique lobby with jewel-toned furniture"},
                    {"url": "https://media-cdn.tripadvisor.com/stub/boutique_suite.jpg", "source": "tripadvisor",
                     "image_type": "official", "caption": "Suite interior"},
                    {"url": "https://media-cdn.tripadvisor.com/stub/boutique_lounge.jpg", "source": "tripadvisor",
                     "image_type": "guest", "caption": "The lounge — that couch!"},
                ],
            },
        ]
