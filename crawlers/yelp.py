"""
Yelp Crawler Agent
-------------------
Uses the Yelp Fusion API to search for hotels and retrieve reviews + photos.

Yelp Fusion API (free tier):
  - 500 calls/day
  - Business search: returns name, address, rating, photos
  - Business reviews: returns up to 3 reviews per business (free tier limit)

Requires: YELP_API_KEY in environment.
Without it, falls back to stub data.

API docs: https://docs.developer.yelp.com/docs/fusion-intro
"""

import os
from rich.console import Console
from .base import BaseCrawler

console = Console()

YELP_API_BASE = "https://api.yelp.com/v3"


class YelpCrawler(BaseCrawler):
    source_name = "yelp"
    min_delay = 0.5
    max_delay = 1.2

    def __init__(self):
        super().__init__()
        self.api_key = os.getenv("YELP_API_KEY")
        if self.api_key:
            self.client.headers.update({"Authorization": f"Bearer {self.api_key}"})

    async def crawl_city(self, city: str, db) -> list[dict]:
        console.print(f"[bold blue]🕷 Yelp[/] crawling hotels in [italic]{city}[/]...")

        if not self.api_key:
            console.print("[yellow]⚠ No YELP_API_KEY — using prototype stub data[/]")
            return self._stub_data(city)

        return await self._crawl_via_api(city)

    async def _crawl_via_api(self, city: str) -> list[dict]:
        # Search for hotels
        data = await self.fetch_json(
            f"{YELP_API_BASE}/businesses/search",
            params={
                "term": "hotels",
                "location": city,
                "categories": "hotels",
                "limit": 10,
                "sort_by": "rating",
            }
        )

        if not data or "businesses" not in data:
            console.print(f"[yellow]⚠ Yelp API error — using stub data[/]")
            return self._stub_data(city)

        results = []
        for biz in data["businesses"][:8]:
            hotel = {
                "name": biz.get("name", "Unknown"),
                "source": self.source_name,
                "source_url": biz.get("url", ""),
                "city": city,
                "rating": biz.get("rating"),
                "address": ", ".join(biz.get("location", {}).get("display_address", [])),
                "reviews": [],
                "images": [],
            }

            # Add photos (Yelp returns up to 3 per business on free tier)
            for photo_url in biz.get("photos", []):
                hotel["images"].append({
                    "url": photo_url,
                    "source": self.source_name,
                    "image_type": "official",
                    "caption": "",
                })

            # Fetch reviews for this business
            biz_id = biz.get("id", "")
            if biz_id:
                reviews = await self._fetch_reviews(biz_id, hotel["source_url"])
                hotel["reviews"].extend(reviews)

            results.append(hotel)

        console.print(f"[green]✓ Yelp[/] found {len(results)} hotels")
        return results

    async def _fetch_reviews(self, biz_id: str, biz_url: str) -> list[dict]:
        data = await self.fetch_json(f"{YELP_API_BASE}/businesses/{biz_id}/reviews")
        reviews = []
        if data and "reviews" in data:
            for r in data["reviews"]:
                text = r.get("text", "")
                if len(text) > 20:
                    reviews.append({
                        "text": text,
                        "source": self.source_name,
                        "author": r.get("user", {}).get("name"),
                        "rating": r.get("rating"),
                        "review_url": biz_url,
                    })
        return reviews

    def _stub_data(self, city: str) -> list[dict]:
        return [
            {
                "name": "The Grand Luxe Hotel",
                "source": self.source_name,
                "source_url": f"https://www.yelp.com/biz/grand-luxe-{city.lower().replace(' ', '-')}",
                "city": city,
                "rating": 4.5,
                "address": f"123 Main Street, {city}",
                "reviews": [
                    {
                        "text": "Wow the lobby decor is something else. Those deep purple couches are iconic — "
                                "everyone takes photos on them.",
                        "source": "yelp", "author": "SarahM.", "rating": 5,
                        "review_url": "https://www.yelp.com/biz/stub1",
                    },
                ],
                "images": [
                    {
                        "url": "https://s3-media1.fl.yelpcdn.com/bphoto/stub/grand_luxe_lobby.jpg",
                        "source": "yelp", "image_type": "official", "caption": "",
                    },
                ],
            },
            {
                "name": "Boutique Inn & Suites",
                "source": self.source_name,
                "source_url": f"https://www.yelp.com/biz/boutique-inn-{city.lower().replace(' ', '-')}",
                "city": city,
                "rating": 4.8,
                "address": f"789 Design District, {city}",
                "reviews": [
                    {
                        "text": "This place is a photographer's dream. The sitting area has this incredible "
                                "dark purple velvet sofa that looks amazing.",
                        "source": "yelp", "author": "MikeR.", "rating": 5,
                        "review_url": "https://www.yelp.com/biz/stub2",
                    },
                    {
                        "text": "Unique boutique hotel with very specific design choices. "
                                "Love the purple and gold color palette in the common areas.",
                        "source": "yelp", "author": "TravelBlog22", "rating": 4,
                        "review_url": "https://www.yelp.com/biz/stub3",
                    },
                ],
                "images": [
                    {
                        "url": "https://s3-media1.fl.yelpcdn.com/bphoto/stub/boutique_lounge.jpg",
                        "source": "yelp", "image_type": "guest", "caption": "",
                    },
                ],
            },
        ]
