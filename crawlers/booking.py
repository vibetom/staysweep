"""
Booking.com Crawler Agent
--------------------------
Crawls Booking.com search results for a given city.
Extracts: hotel names, ratings, review snippets, photo URLs.

Booking.com is heavily JS-rendered — real crawling requires Playwright.
This prototype uses httpx with fallback to stub data.
A note on Playwright integration is included for production upgrade.
"""

import os
from urllib.parse import quote_plus
from rich.console import Console
from .base import BaseCrawler

MAX_HOTELS = int(os.getenv("MAX_HOTELS_PER_SOURCE", "20"))

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
            console.print("[yellow]⚠ Booking.com blocked — skipping[/]")
            return []

        # Booking.com renders hotel cards in JS — if we get a response,
        # try to parse SSR markup (sometimes present)
        cards = (soup.select('[data-testid="property-card"]') or
                 soup.select('.sr_property_block') or
                 soup.select('[data-hotelid]'))

        if not cards:
            console.print("[yellow]⚠ Booking.com: JS-gated page, no cards found — skipping[/]")
            return []

        results = []
        for card in cards[:MAX_HOTELS]:
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

