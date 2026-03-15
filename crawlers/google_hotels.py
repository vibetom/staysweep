"""
Google Hotels Crawler Agent
-----------------------------
Uses Google Places Text Search API to find hotels.
Falls back to scraping google.com/travel/hotels (heavily JS-gated).
Returns hotel names, addresses, ratings, and photo references.

Requires: GOOGLE_PLACES_API_KEY in environment (optional — uses stub without it)
"""

import os
from rich.console import Console
from .base import BaseCrawler

MAX_HOTELS = int(os.getenv("MAX_HOTELS_PER_SOURCE", "20"))

console = Console()

PLACES_API_BASE = "https://maps.googleapis.com/maps/api/place"
PLACES_PHOTO_BASE = "https://maps.googleapis.com/maps/api/place/photo"


class GoogleHotelsCrawler(BaseCrawler):
    source_name = "google_hotels"
    min_delay = 0.5   # API calls can be faster
    max_delay = 1.0

    def __init__(self):
        super().__init__()
        self.api_key = os.getenv("GOOGLE_PLACES_API_KEY")

    async def crawl_city(self, city: str, db) -> list[dict]:
        console.print(f"[bold blue]🕷 Google Hotels[/] crawling hotels in [italic]{city}[/]...")

        if not self.api_key:
            console.print("[yellow]⚠ No GOOGLE_PLACES_API_KEY — skipping Google Hotels[/]")
            return []

        return await self._crawl_via_api(city)

    async def _crawl_via_api(self, city: str) -> list[dict]:
        """Use Places Text Search API to find hotels."""
        data = await self.fetch_json(
            f"{PLACES_API_BASE}/textsearch/json",
            params={"query": f"hotels in {city}", "type": "lodging", "key": self.api_key}
        )

        if not data or data.get("status") not in ("OK", "ZERO_RESULTS"):
            console.print(f"[yellow]⚠ Google Places API error: {data.get('status', 'unknown')}[/]")
            return []

        results = []
        for place in data.get("results", [])[:MAX_HOTELS]:
            hotel = {
                "name": place.get("name", "Unknown"),
                "source": self.source_name,
                "source_url": f"https://www.google.com/maps/place/?q=place_id:{place['place_id']}",
                "city": city,
                "rating": place.get("rating"),
                "address": place.get("formatted_address"),
                "reviews": [],
                "images": [],
            }

            # Fetch photo URLs
            for photo in place.get("photos", [])[:5]:
                ref = photo.get("photo_reference", "")
                if ref:
                    url = (f"{PLACES_PHOTO_BASE}?maxwidth=800"
                           f"&photoreference={ref}&key={self.api_key}")
                    hotel["images"].append({
                        "url": url,
                        "source": self.source_name,
                        "image_type": "official",
                        "caption": "",
                    })

            # Fetch reviews via Place Details
            details = await self._fetch_place_details(place["place_id"])
            if details:
                for review in details.get("reviews", []):
                    hotel["reviews"].append({
                        "text": review.get("text", ""),
                        "source": self.source_name,
                        "author": review.get("author_name"),
                        "rating": review.get("rating"),
                        "review_url": hotel["source_url"],
                    })

            results.append(hotel)

        console.print(f"[green]✓ Google Hotels[/] found {len(results)} hotels")
        return results

    async def _fetch_place_details(self, place_id: str) -> dict | None:
        data = await self.fetch_json(
            f"{PLACES_API_BASE}/details/json",
            params={
                "place_id": place_id,
                "fields": "reviews,photos",
                "key": self.api_key
            }
        )
        if data and data.get("status") == "OK":
            return data.get("result", {})
        return None

