"""
StaySweep — Main Orchestrator
==================================
Coordinates all agents in parallel:

  1. Query Parser Agent        — decompose user query
  2. Crawler Agents (parallel) — TripAdvisor, Google, Booking simultaneously
  3. Per-hotel analysis (parallel):
       a. Text Analyst Agent   — scan reviews
       b. Vision Analyst Agent — scan images
  4. Scorer Agent              — combine scores, generate summary
  5. Report                    — ranked output with evidence

Usage:
    python main.py --query "dark purple couch" --city "New York"
    python main.py --query "rooftop pool with mountain views" --city "Denver"
"""

import asyncio
import argparse
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from rich.console import Console

load_dotenv(Path(__file__).parent / ".env")
from rich.panel import Panel
from rich.table import Table
from rich import box
import aiosqlite

from db.database import init_db, upsert_hotel, insert_review, insert_image, save_analysis, DB_PATH
from agents.query_parser import parse_query
from agents.text_analyst import analyze_reviews
from agents.vision_analyst import analyze_images
from agents.scorer import score_and_summarize
from crawlers.tripadvisor import TripAdvisorCrawler
from crawlers.google_hotels import GoogleHotelsCrawler
from crawlers.booking import BookingCrawler
from crawlers.yelp import YelpCrawler
from crawlers.official_site import OfficialWebsiteCrawler
from utils.image_ranker import rank_and_filter_images, should_skip_vision

console = Console()


# ─── Step 1: Crawl all sources in parallel ───────────────────────────────────

async def crawl_all_sources(city: str, db) -> list[dict]:
    """Run all crawlers concurrently and merge results."""
    console.print(f"\n[bold]Step 1: Crawling all sources for [cyan]{city}[/]...[/]")

    crawlers = [
        TripAdvisorCrawler(),
        GoogleHotelsCrawler(),
        BookingCrawler(),
        YelpCrawler(),
    ]

    tasks = [crawler.crawl_city(city, db) for crawler in crawlers]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Close crawlers
    for c in crawlers:
        await c.close()

    # Flatten and deduplicate by hotel name (case-insensitive)
    all_hotels: dict[str, dict] = {}

    for source_results in raw_results:
        if isinstance(source_results, Exception):
            console.print(f"[red]Crawler error: {source_results}[/]")
            continue
        for hotel in source_results:
            key = hotel["name"].lower().strip()
            if key not in all_hotels:
                all_hotels[key] = {**hotel, "reviews": list(hotel.get("reviews", [])),
                                   "images": list(hotel.get("images", []))}
            else:
                # Merge reviews and images from multiple sources
                all_hotels[key]["reviews"].extend(hotel.get("reviews", []))
                all_hotels[key]["images"].extend(hotel.get("images", []))

    merged = list(all_hotels.values())
    console.print(f"[green]✓ Total unique hotels found:[/] {len(merged)}")
    return merged


# ─── Step 2: Persist to DB ───────────────────────────────────────────────────

async def persist_hotels(hotels: list[dict], db) -> dict[str, int]:
    """Save hotels, reviews, and images to DB. Returns name→hotel_id mapping."""
    name_to_id = {}
    for hotel in hotels:
        hotel_id = await upsert_hotel(
            db,
            name=hotel["name"],
            city=hotel["city"],
            source=hotel["source"],
            source_url=hotel["source_url"],
            address=hotel.get("address"),
            rating=hotel.get("rating"),
        )
        name_to_id[hotel["name"]] = hotel_id

        for review in hotel.get("reviews", []):
            await insert_review(
                db, hotel_id,
                source=review.get("source", "unknown"),
                text=review["text"],
                author=review.get("author"),
                rating=review.get("rating"),
                review_url=review.get("review_url"),
            )

        for image in hotel.get("images", []):
            await insert_image(
                db, hotel_id,
                url=image["url"],
                source=image.get("source", "unknown"),
                caption=image.get("caption"),
                image_type=image.get("image_type", "official"),
            )

    return name_to_id


# ─── Step 3: Analyze each hotel in parallel ──────────────────────────────────

async def analyze_hotel(hotel: dict, parsed_query: dict, raw_query: str,
                         on_result=None) -> dict:
    """
    Run text + vision analysis in parallel for a single hotel.
    Text runs first; if it scores very low we skip the vision pass.
    Returns a scored result dict.
    """
    hotel_name = hotel["name"]
    images = hotel.get("images", [])

    # Run text analysis first (it's cheap and a good gating signal)
    text_result = await analyze_reviews(hotel_name, hotel.get("reviews", []), parsed_query)

    # Smart gate: skip vision if text strongly negative and no images
    skip, reason = should_skip_vision(
        text_result.get("score", 0.0),
        text_result.get("evidence", []),
        len(images),
    )

    if skip:
        console.print(f"  [dim]Skipping vision for {hotel_name}: {reason}[/]")
        vision_result = {"score": 0.0, "matching_images": [], "reasoning": reason}
    else:
        vision_result = await analyze_images(hotel_name, images, parsed_query)

    result = await score_and_summarize(
        hotel_name=hotel_name,
        hotel_url=hotel.get("source_url", ""),
        hotel_rating=hotel.get("rating"),
        query=raw_query,
        text_result=text_result,
        vision_result=vision_result,
    )

    # Notify callback with individual result (for streaming to web UI)
    if on_result:
        await on_result(result)

    return result


async def analyze_all_hotels_parallel(hotels: list[dict], parsed_query: dict,
                                       raw_query: str, on_result=None) -> list[dict]:
    """
    Analyze all hotels concurrently — each hotel gets its own text+vision agents.
    Semaphore limits to 3 parallel analyses to respect Gemini free tier rate limits.
    """
    console.print(f"\n[bold]Step 3: Running parallel analysis on {len(hotels)} hotels...[/]")

    sem = asyncio.Semaphore(3)

    async def bounded_analyze(hotel):
        async with sem:
            return await analyze_hotel(hotel, parsed_query, raw_query, on_result=on_result)

    tasks = [bounded_analyze(hotel) for hotel in hotels]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    clean = []
    for r in results:
        if isinstance(r, Exception):
            console.print(f"[red]Analysis error: {r}[/]")
        else:
            clean.append(r)

    return sorted(clean, key=lambda x: x["final_score"], reverse=True)


# ─── Step 4: Save results + print report ─────────────────────────────────────

async def save_results(results: list[dict], name_to_id: dict, raw_query: str, db):
    for r in results:
        hotel_id = name_to_id.get(r["hotel_name"])
        if hotel_id:
            await save_analysis(
                db, hotel_id, raw_query,
                r["text_score"], r["vision_score"], r["final_score"],
                r["evidence_text"], r["evidence_images"], r["summary"]
            )


def print_report(results: list[dict], raw_query: str, city: str):
    console.print()
    console.print(Panel(
        f"[bold]StaySweep Results[/]\n"
        f"Query: [italic cyan]{raw_query}[/]\n"
        f"City: [italic]{city}[/]",
        box=box.DOUBLE_EDGE,
        style="bold"
    ))

    matches = [r for r in results if r["final_score"] > 0.1]
    total = len(results)

    # Search summary
    console.print(f"\n[bold]Search Summary:[/] {total} hotels searched, "
                  f"{len(matches)} potential match{'es' if len(matches) != 1 else ''}")

    if not matches:
        console.print("[yellow]No hotels found with a match score above 10%.[/]")
        console.print(f"\n[dim]Hotels searched: {', '.join(r['hotel_name'] for r in results[:20])}[/]")
        return

    top = matches[:5]

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Rank", width=4)
    table.add_column("Hotel", min_width=24)
    table.add_column("Match", width=7)
    table.add_column("Text", width=6)
    table.add_column("Vision", width=7)
    table.add_column("Rating", width=7)

    for i, r in enumerate(top, 1):
        score_color = "green" if r["final_score"] > 0.6 else "yellow" if r["final_score"] > 0.3 else "red"
        table.add_row(
            str(i),
            r["hotel_name"],
            f"[{score_color}]{r['final_score']*100:.0f}%[/]",
            f"{r['text_score']*100:.0f}%",
            f"{r['vision_score']*100:.0f}%",
            f"{r['hotel_rating']:.1f}" if r.get("hotel_rating") else "—",
        )

    console.print(table)

    console.print("\n[bold]Top Match Details:[/]\n")
    for i, r in enumerate(top[:3], 1):
        console.print(f"[bold cyan]#{i} {r['hotel_name']}[/]")
        console.print(f"   {r['summary']}")
        if r["evidence_text"]:
            console.print(f"   [dim]Review evidence:[/] {r['evidence_text'][0][:120]}...")
        if r["evidence_images"]:
            console.print(f"   [dim]Photo evidence:[/] {r['evidence_images'][0]['description']}")
            console.print(f"   [dim]Image URL:[/] {r['evidence_images'][0]['url']}")
        console.print(f"   [dim]Source:[/] {r['hotel_url']}")
        console.print()

    # Save JSON report
    report_path = Path(__file__).parent / "output" / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "query": raw_query,
            "city": city,
            "timestamp": datetime.now().isoformat(),
            "results": results,
        }, f, indent=2)
    console.print(f"[dim]Full results saved to: {report_path}[/]")


# ─── Pipeline runner (used by both CLI and web) ──────────────────────────────

async def run_pipeline(raw_query: str, city: str, on_progress=None, on_result=None):
    """
    Core pipeline logic. Accepts optional callbacks:
      on_progress(event_dict) — called at each step for status updates
      on_result(result_dict)  — called when each hotel analysis completes
    Returns the sorted list of results.
    """
    async def progress(step, message, **extra):
        if on_progress:
            await on_progress({"step": step, "message": message, **extra})

    await progress("init", f"Starting search: '{raw_query}' in {city}")

    # Init DB
    await init_db()

    async with aiosqlite.connect(DB_PATH) as db:
        # Step 1: Parse query
        await progress("parsing", "Parsing your query with AI...")
        parsed_query = await parse_query(raw_query)
        await progress("parsed", "Query parsed",
                        keywords=parsed_query.get("text_keywords", []),
                        visual=parsed_query.get("visual_features", []))

        # Step 2: Crawl all sources in parallel
        await progress("crawling", f"Crawling hotel sources for {city}...")
        hotels = await crawl_all_sources(city, db)
        await progress("crawled", f"Found {len(hotels)} unique hotels",
                        hotel_count=len(hotels))

        # Step 3: Persist to DB
        await progress("persisting", "Saving hotel data...")
        name_to_id = await persist_hotels(hotels, db)

        # Step 3b: Official website enrichment
        await progress("enriching", "Checking official hotel websites...")
        official_crawler = OfficialWebsiteCrawler()
        enrich_tasks = [official_crawler.enrich_hotel_with_official_photos(h) for h in hotels]
        enrich_results = await asyncio.gather(*enrich_tasks, return_exceptions=True)
        for hotel, extra_images in zip(hotels, enrich_results):
            if isinstance(extra_images, list) and extra_images:
                hotel["images"].extend(extra_images)
                async with aiosqlite.connect(DB_PATH) as db2:
                    hotel_id = name_to_id.get(hotel["name"])
                    if hotel_id:
                        for img in extra_images:
                            await insert_image(db2, hotel_id, img["url"], img["source"],
                                               img.get("caption"), img.get("image_type", "official"))
        await official_crawler.close()

        # Step 3c: Rank images
        for hotel in hotels:
            hotel["images"] = rank_and_filter_images(hotel["images"], parsed_query, max_images=8)

        # Step 4: Parallel analysis
        await progress("analyzing", f"Analyzing {len(hotels)} hotels with AI (text + vision)...",
                        hotel_count=len(hotels))
        results = await analyze_all_hotels_parallel(hotels, parsed_query, raw_query,
                                                     on_result=on_result)

        # Step 5: Save analysis results
        await save_results(results, name_to_id, raw_query, db)

    await progress("complete", f"Search complete — {len(results)} hotels analyzed")
    return results


# ─── CLI entry point ─────────────────────────────────────────────────────────

async def run(raw_query: str, city: str):
    """CLI wrapper around run_pipeline that prints rich output."""
    console.print(Panel(
        f"[bold cyan]🏨 StaySweep[/]\n"
        f"Finding: [italic]{raw_query}[/]\n"
        f"City: [italic]{city}[/]",
        box=box.ROUNDED
    ))

    results = await run_pipeline(raw_query, city)
    print_report(results, raw_query, city)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StaySweep — Find specific features in hotels")
    parser.add_argument("--query", "-q", required=True,
                        help='Feature to search for, e.g. "dark purple couch"')
    parser.add_argument("--city", "-c", required=True,
                        help='City to search in, e.g. "New York"')
    args = parser.parse_args()

    asyncio.run(run(args.query, args.city))
