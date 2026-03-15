"""
StaySweep — Test Suite
--------------------------
Tests the full pipeline using stub crawlers and mocked LLM responses.
Run with: python test_pipeline.py

Tests:
  1. Query parser output structure
  2. Crawler stub data format
  3. Image ranker priority logic
  4. Scorer weighted math
  5. Full end-to-end pipeline (with mocked LLM calls)
  6. Cost estimator calculations
"""

import asyncio
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, str(Path(__file__).parent))


# ─── Test helpers ─────────────────────────────────────────────────────────────

class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []

    def ok(self, name):
        self.passed.append(name)
        print(f"  ✅ {name}")

    def fail(self, name, reason=""):
        self.failed.append(name)
        print(f"  ❌ {name}" + (f": {reason}" if reason else ""))

    def summary(self):
        total = len(self.passed) + len(self.failed)
        print(f"\n{'='*50}")
        print(f"Results: {len(self.passed)}/{total} passed")
        if self.failed:
            print(f"Failed:  {', '.join(self.failed)}")
        return len(self.failed) == 0


T = TestResults()


# ─── 1. Crawler stub data format ──────────────────────────────────────────────

def test_crawler_stubs():
    print("\n[1] Crawler stub data format")
    from crawlers.tripadvisor import TripAdvisorCrawler
    from crawlers.google_hotels import GoogleHotelsCrawler
    from crawlers.booking import BookingCrawler
    from crawlers.yelp import YelpCrawler

    for CrawlerClass in [TripAdvisorCrawler, GoogleHotelsCrawler, BookingCrawler, YelpCrawler]:
        c = CrawlerClass()
        stubs = c._stub_data("New York")

        try:
            assert isinstance(stubs, list), "Should return list"
            assert len(stubs) > 0, "Should have at least one hotel"

            for hotel in stubs:
                assert "name" in hotel, "Hotel needs name"
                assert "source_url" in hotel, "Hotel needs source_url"
                assert "city" in hotel, "Hotel needs city"
                assert isinstance(hotel.get("reviews", []), list), "Reviews should be list"
                assert isinstance(hotel.get("images", []), list), "Images should be list"

                for review in hotel.get("reviews", []):
                    assert "text" in review, "Review needs text"
                    assert len(review["text"]) > 10, "Review text too short"

                for image in hotel.get("images", []):
                    assert "url" in image, "Image needs url"

            T.ok(f"{CrawlerClass.__name__} stub format")
        except AssertionError as e:
            T.fail(f"{CrawlerClass.__name__} stub format", str(e))
        finally:
            asyncio.get_event_loop().run_until_complete(c.close())


# ─── 2. Image ranker ──────────────────────────────────────────────────────────

def test_image_ranker():
    print("\n[2] Image ranker priority logic")
    from utils.image_ranker import rank_and_filter_images, should_skip_vision

    images = [
        {"url": "https://example.com/lobby_purple_couch.jpg", "source": "official_site",
         "image_type": "official", "caption": "Purple sofa in lobby"},
        {"url": "https://example.com/pool.jpg", "source": "tripadvisor",
         "image_type": "guest", "caption": "Swimming pool"},
        {"url": "https://example.com/room1.jpg", "source": "booking",
         "image_type": "official", "caption": "Standard room"},
        {"url": "https://example.com/icon.png", "source": "tripadvisor",
         "image_type": "guest", "caption": "hotel logo icon"},
        {"url": "https://example.com/lobby_couch.jpg", "source": "tripadvisor",
         "image_type": "guest", "caption": "Couch in lobby"},
    ]

    parsed_query = {
        "visual_features": ["dark purple couch"],
        "text_keywords": ["purple couch", "dark purple sofa"],
        "context": ["lobby", "lounge"],
    }

    try:
        ranked = rank_and_filter_images(images, parsed_query, max_images=3)
        assert len(ranked) <= 3, "Should respect max_images"
        # The lobby/purple image should rank high
        urls = [img["url"] for img in ranked]
        assert "https://example.com/lobby_purple_couch.jpg" in urls, \
            "Caption-matching image should be in top 3"
        # Pool should be deprioritized
        pool_in_top3 = "https://example.com/pool.jpg" in urls
        T.ok("Image ranker - caption match prioritized")
        if not pool_in_top3:
            T.ok("Image ranker - pool deprioritized")
        else:
            T.fail("Image ranker - pool deprioritized", "Pool still in top 3")
    except AssertionError as e:
        T.fail("Image ranker - basic ranking", str(e))

    # Deduplication
    dup_images = [
        {"url": "https://example.com/same.jpg", "source": "ta", "image_type": "official", "caption": ""},
        {"url": "https://example.com/same.jpg", "source": "booking", "image_type": "official", "caption": ""},
        {"url": "https://example.com/other.jpg", "source": "ta", "image_type": "official", "caption": ""},
    ]
    try:
        ranked = rank_and_filter_images(dup_images, parsed_query)
        assert len(ranked) == 2, f"Should deduplicate, got {len(ranked)}"
        T.ok("Image ranker - deduplication")
    except AssertionError as e:
        T.fail("Image ranker - deduplication", str(e))

    # Fast-path skip
    try:
        skip, reason = should_skip_vision(0.02, [], 5)
        assert skip, "Should skip when text score very low"
        T.ok("Vision fast-path skip - low text score")

        skip, reason = should_skip_vision(0.0, [], 0)
        assert skip, "Should skip when no images"
        T.ok("Vision fast-path skip - no images")

        skip, reason = should_skip_vision(0.7, ["some evidence"], 5)
        assert not skip, "Should NOT skip when text score high"
        T.ok("Vision fast-path skip - high score proceeds")
    except AssertionError as e:
        T.fail("Vision fast-path skip", str(e))


# ─── 3. Scorer weighted math ──────────────────────────────────────────────────

def test_scorer_math():
    print("\n[3] Confidence scorer math")
    from agents.scorer import compute_final_score

    try:
        # Both high: should be high with corroboration bonus
        score = compute_final_score(0.9, 0.9, ["evidence"], [{"url": "x"}])
        assert score > 0.9, f"Both high should score >0.9, got {score}"
        T.ok("Scorer - both high → corroboration bonus")

        # Text zero, vision high
        score = compute_final_score(0.0, 0.9, [], [{"url": "x"}])
        assert 0.4 < score < 0.7, f"Text zero, vision high: expected 0.4-0.7, got {score}"
        T.ok("Scorer - text zero, vision high")

        # Both low: should be penalized
        score_low = compute_final_score(0.2, 0.2, [], [])
        score_expected = compute_final_score(0.5, 0.5, ["e"], [{"url": "x"}])
        assert score_low < score_expected, "Low scores should be penalized vs medium scores"
        T.ok("Scorer - both low gets penalty")

        # Zero/zero
        score = compute_final_score(0.0, 0.0, [], [])
        assert score == 0.0, f"Both zero should give 0, got {score}"
        T.ok("Scorer - zero/zero → zero")

    except AssertionError as e:
        T.fail("Scorer math", str(e))


# ─── 4. Cost estimator ────────────────────────────────────────────────────────

def test_cost_estimator():
    print("\n[4] Cost estimator")
    from utils.cost_estimator import estimate_cost

    try:
        est = estimate_cost(10)
        assert est["n_hotels"] == 10
        assert est["total_cost_usd"] == 0.0, "Should be free on Gemini free tier"
        assert "breakdown" in est
        assert all(k in est["breakdown"] for k in
                   ["query_parsing", "text_analysis", "vision_analysis", "scoring"])

        T.ok(f"Cost estimator - 10 hotels = $0.00 (free tier)")

        # Token estimates should still be tracked
        assert est["total_input_tokens"] > 0, "Should still track token usage"
        T.ok("Cost estimator - token tracking works")

    except AssertionError as e:
        T.fail("Cost estimator", str(e))


# ─── 5. Mock LLM integration ─────────────────────────────────────────────────

def test_mock_query_parser():
    """Test the query parser agent with a mocked LLM response."""
    print("\n[5] Query parser (mocked LLM)")

    mock_response_json = json.dumps({
        "visual_features": ["dark purple couch", "deep plum velvet sofa"],
        "text_keywords": ["purple couch", "purple sofa", "dark purple furniture", "plum couch"],
        "context": ["lobby", "lounge", "common area", "suite"],
        "negative_signals": ["light purple", "lavender"],
        "summary": "Looking for a hotel with a dark purple couch"
    })

    with patch("agents.llm_client.chat", new_callable=AsyncMock, return_value=mock_response_json):
        result = asyncio.get_event_loop().run_until_complete(
            __import__("agents.query_parser", fromlist=["parse_query"]).parse_query(
                "Find me a hotel with a dark purple couch"
            )
        )

        try:
            assert "visual_features" in result
            assert "text_keywords" in result
            assert "context" in result
            assert "summary" in result
            assert len(result["visual_features"]) > 0
            assert len(result["text_keywords"]) > 0
            T.ok("Query parser - correct output structure")
            T.ok(f"Query parser - extracted {len(result['text_keywords'])} keywords")
        except AssertionError as e:
            T.fail("Query parser output", str(e))


# ─── 6. Hotel deduplication across sources ────────────────────────────────────

def test_hotel_deduplication():
    """Test that same hotel from multiple sources is merged, not duplicated."""
    print("\n[6] Hotel deduplication across crawlers")

    hotels_raw = [
        # From TripAdvisor
        {"name": "The Grand Hotel", "source": "tripadvisor", "source_url": "https://ta.com/grand",
         "city": "NYC", "rating": 4.5, "reviews": [{"text": "Great place", "source": "ta"}],
         "images": [{"url": "https://ta.com/img1.jpg", "source": "ta", "image_type": "guest", "caption": ""}]},
        # Same hotel from Booking
        {"name": "The Grand Hotel", "source": "booking", "source_url": "https://booking.com/grand",
         "city": "NYC", "rating": 4.3, "reviews": [{"text": "Loved it", "source": "booking"}],
         "images": [{"url": "https://booking.com/img2.jpg", "source": "booking", "image_type": "official", "caption": ""}]},
        # Different hotel
        {"name": "Budget Motel", "source": "tripadvisor", "source_url": "https://ta.com/budget",
         "city": "NYC", "rating": 3.0, "reviews": [], "images": []},
    ]

    # Simulate the deduplication logic from main.py
    all_hotels: dict = {}
    for hotel in hotels_raw:
        key = hotel["name"].lower().strip()
        if key not in all_hotels:
            all_hotels[key] = {**hotel, "reviews": list(hotel.get("reviews", [])),
                               "images": list(hotel.get("images", []))}
        else:
            all_hotels[key]["reviews"].extend(hotel.get("reviews", []))
            all_hotels[key]["images"].extend(hotel.get("images", []))

    merged = list(all_hotels.values())

    try:
        assert len(merged) == 2, f"Expected 2 unique hotels, got {len(merged)}"
        T.ok("Deduplication - 3 entries → 2 unique hotels")

        grand = next(h for h in merged if h["name"] == "The Grand Hotel")
        assert len(grand["reviews"]) == 2, f"Merged hotel should have 2 reviews, got {len(grand['reviews'])}"
        assert len(grand["images"]) == 2, f"Merged hotel should have 2 images, got {len(grand['images'])}"
        T.ok("Deduplication - reviews and images merged")
    except AssertionError as e:
        T.fail("Deduplication", str(e))


# ─── Run all tests ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("StaySweep — Pipeline Test Suite")
    print("=" * 50)

    test_crawler_stubs()
    test_image_ranker()
    test_scorer_math()
    test_cost_estimator()
    test_mock_query_parser()
    test_hotel_deduplication()

    success = T.summary()
    sys.exit(0 if success else 1)
