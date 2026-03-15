"""
Booking.com Crawler Agent
--------------------------
Crawls Booking.com search results for a given city.
Extracts: hotel names, ratings, review snippets, photo URLs.

Booking.com is heavily JS-rendered — real crawling requires Playwright.
This prototype uses httpx with fallback to stub data.
A note on Playwright integration is included for production upgrade.
"""

from urllib.parse import quote_plus
from rich.console import Console
from .base import BaseCrawler

console = Console()

BOOKING_BASE = "https://www.booking.com"


class BookingCrawler(BaseCrawler):
    source_name = "booking"
    min_delay = 2.5
    max_delay = 5.0

    async def crawl_city(self, city: str, db) -> list[dict]:
        console.print(f"[bold blue]🕷 Booking.com[/] crawling hotels in [italic]{city}[/]...")

        # Try real crawl first
        url = f"{BOOKING_BASE}/searchresults.html?ss={quote_plus(city)}&atype=1"
        soup = await self.fetch_html(url)

        if soup is None:
            console.print("[yellow]⚠ Booking.com blocked — using prototype stub data[/]")
            return self._stub_data(city)

        # Booking.com renders hotel cards in JS — if we get a response,
        # try to parse SSR markup (sometimes present)
        cards = (soup.select('[data-testid="property-card"]') or
                 soup.select('.sr_property_block') or
                 soup.select('[data-hotelid]'))

        if not cards:
            console.print("[yellow]⚠ Booking.com: JS-gated page, no cards found — using stub[/]")
            return self._stub_data(city)

        results = []
        for card in cards[:8]:
            name_el = (card.select_one('[data-testid="title"]') or
                       card.select_one('.sr-hotel__name') or
                       card.select_one('span.sr-hotel__name'))
            name = name_el.get_text(strip=True) if name_el else "Unknown"

            link_el = card.select_one('a[href*="/hotel/"]')
            href = link_el["href"] if link_el else ""
            if href and not href.startswith("http"):
                href = BOOKING_BASE + href

            rating_el = card.select_one('[data-testid="review-score"]')
            rating = None
            if rating_el:
                try:
                    rating = float(rating_el.get_text(strip=True).split()[0])
                except Exception:
                    pass

            results.append({
                "name": name,
                "source": self.source_name,
                "source_url": href,
                "city": city,
                "rating": rating,
                "reviews": [],
                "images": [],
            })

        console.print(f"[green]✓ Booking.com[/] found {len(results)} hotels")
        return results

    def _stub_data(self, city: str) -> list[dict]:
        return [
            {
                "name": "Boutique Inn & Suites",
                "source": self.source_name,
                "source_url": f"https://www.booking.com/hotel/stub/boutique-inn-{city.lower().replace(' ', '-')}.html",
                "city": city,
                "rating": 9.2,
                "reviews": [
                    {"text": "The hotel is decorated with the most lush, dark purple velvet couches I have ever seen in a lobby. Absolute vibe.",
                     "source": "booking", "review_url": "https://booking.com/stub/r1"},
                    {"text": "Rooms are tastefully decorated. The lounge area is particularly impressive with its purple and gold color scheme.",
                     "source": "booking", "review_url": "https://booking.com/stub/r2"},
                ],
                "images": [
                    {"url": "https://cf.bstatic.com/xdata/stub/boutique_main.jpg",
                     "source": "booking", "image_type": "official", "caption": "Hotel lobby"},
                    {"url": "https://cf.bstatic.com/xdata/stub/boutique_couch.jpg",
                     "source": "booking", "image_type": "official", "caption": "Seating area"},
                ],
            },
            {
                "name": "The Grand Luxe Hotel",
                "source": self.source_name,
                "source_url": f"https://www.booking.com/hotel/stub/grand-luxe-{city.lower().replace(' ', '-')}.html",
                "city": city,
                "rating": 8.8,
                "reviews": [
                    {"text": "Excellent stay. Stunning lobby with dramatic purple furniture.",
                     "source": "booking", "review_url": "https://booking.com/stub/r3"},
                ],
                "images": [
                    {"url": "https://cf.bstatic.com/xdata/stub/grand_luxe_lobby.jpg",
                     "source": "booking", "image_type": "official", "caption": "Grand lobby"},
                ],
            },
        ]
