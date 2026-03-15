"""
Base crawler with shared utilities: polite rate limiting,
rotating user agents, and HTML/JSON fetching.
"""

import asyncio
import random
import httpx
from bs4 import BeautifulSoup
from rich.console import Console

console = Console()

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class BaseCrawler:
    source_name = "base"
    min_delay = 1.5   # seconds between requests
    max_delay = 3.5

    def __init__(self):
        self.headers = {**BASE_HEADERS, "User-Agent": random.choice(USER_AGENTS)}
        self.client = httpx.AsyncClient(
            headers=self.headers,
            timeout=20.0,
            follow_redirects=True,
        )

    async def polite_sleep(self):
        delay = random.uniform(self.min_delay, self.max_delay)
        await asyncio.sleep(delay)

    async def fetch_html(self, url: str) -> BeautifulSoup | None:
        try:
            await self.polite_sleep()
            resp = await self.client.get(url)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except httpx.HTTPStatusError as e:
            console.print(f"[yellow]⚠ {self.source_name} HTTP {e.response.status_code} for {url}[/]")
            return None
        except Exception as e:
            console.print(f"[red]✗ {self.source_name} fetch error: {e}[/]")
            return None

    async def fetch_json(self, url: str, params: dict = None) -> dict | None:
        try:
            await self.polite_sleep()
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            console.print(f"[red]✗ {self.source_name} JSON fetch error: {e}[/]")
            return None

    async def close(self):
        await self.client.aclose()

    async def crawl_city(self, city: str, db) -> list[dict]:
        """
        Override in subclasses. Should return a list of dicts:
        [{ "name", "address", "source_url", "rating", "reviews": [...], "images": [...] }]
        """
        raise NotImplementedError
