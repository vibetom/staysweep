# 🏨 Hotel Hunter

Find hyper-specific hotel features — things no search engine can find — by crawling
reviews and photos across TripAdvisor, Google Hotels, Booking.com, and official hotel
websites, then using AI to analyze text and images for exact matches.

**Example:** "Find a hotel in New York with a dark purple couch"

---

## Architecture

```
User Query
    │
    ▼
Query Parser Agent (Claude)
    │  Extracts: visual features, text keywords, context areas
    │
    ▼
Parallel Crawlers ──────────────────────────────────────────
    ├── TripAdvisor Crawler    (reviews + guest photos)
    ├── Google Hotels Crawler  (Places API or scrape)
    └── Booking.com Crawler    (reviews + official photos)
    │
    ▼
Data Aggregator (SQLite)
    │  Deduplicates hotels across sources
    │
    ▼
Parallel Hotel Analysis (one set of agents per hotel, all hotels concurrently)
    ├── Text Analyst Agent (Claude)    — scans review text
    └── Vision Analyst Agent (Claude) — analyzes photos via vision
    │
    ▼
Confidence Scorer + Reporter Agent (Claude)
    │  Weighted score: text 40% + vision 60%
    │  Corroboration bonus when both agree
    │
    ▼
Ranked Results with Evidence
    hotel name | match % | review snippet | image URL | hotel link
```

### Why multiple agents?

Each agent is an expert at one thing:
- **Query Parser**: turns natural language into structured search signals
- **Text Analyst**: reads 25+ reviews per hotel, looking only for text evidence
- **Vision Analyst**: downloads and examines up to 8 images per hotel
- **Scorer**: combines signals with weighted confidence math, writes human summaries

All hotels are analyzed in parallel (bounded to 5 concurrent to respect API rate limits).
Within each hotel, text and vision run concurrently — so a 10-hotel search with 8 images
each doesn't take 10× longer than a 1-hotel search.

---

## Setup

```bash
cd hotel_hunter
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

## Run

```bash
python main.py --query "dark purple couch" --city "New York"
python main.py --query "rooftop pool with mountain views" --city "Denver"
python main.py --query "fireplace in the room" --city "Aspen"
python main.py -q "pink neon sign in lobby" -c "Las Vegas"
```

---

## Prototype vs Production

### What works now (prototype mode)
- Full multi-agent pipeline with parallel execution
- Query parsing, text analysis, vision analysis, scoring
- SQLite persistence of all data
- JSON report output
- Stub data for all crawlers (so the pipeline runs end-to-end without keys)

### What requires real crawling
The crawlers detect when they're blocked and fall back to stub data.
Real crawling at scale requires:

| Issue | Solution |
|-------|----------|
| TripAdvisor JS-gates content | Use Playwright with headless Chromium |
| Booking.com blocks bots | Use Playwright + proxy rotation |
| Google Hotels is JS-only | Use Google Places API (free tier) |
| Rate limiting | Implement exponential backoff + proxy pools |
| Terms of Service | Check each site's ToS before production use |

### Cost per search (estimate)
With real data at 10 hotels × 8 images + 25 reviews each:
- Query parsing: ~$0.001
- Text analysis (10 × 25 reviews): ~$0.05
- Vision analysis (10 × 8 images): ~$0.20
- Scoring (10 × summary): ~$0.02
- **Total: ~$0.27 per search query**

### Upgrade path
1. **Add Playwright** for JS-heavy sites: `pip install playwright && playwright install chromium`
2. **Add Google Places API key** for real hotel data + photos
3. **Add Yelp Fusion API** for Yelp reviews (free tier available)
4. **Add proxy pool** for production crawling at scale
5. **Add Redis** for caching crawl results across queries

---

## Output

Results are saved to `output/results_YYYYMMDD_HHMMSS.json` and printed to console:

```
#1 Boutique Inn & Suites  — 87% match
   Strong evidence across text and photos. Multiple reviewers specifically mention
   the "dark purple velvet couches" in the lobby. One official photo shows a
   distinctly dark purple upholstered sofa in the lounge area.
   Review: "The lobby was stunning with its dark purple velvet couches..."
   Photo:  https://...
   Source: https://www.booking.com/...

#2 The Grand Luxe Hotel   — 54% match
   ...
```

---

## Known Limitations

1. **Stub data accuracy**: The prototype stubs are designed to exercise the pipeline,
   not reflect real hotels. Real results depend on real crawling.

2. **Vision hallucination**: Claude vision occasionally misidentifies colors, especially
   in low-resolution images or images with unusual lighting. High-confidence vision
   scores need human verification.

3. **Review language**: Text analysis works best in English. Non-English reviews are
   currently not handled.

4. **Image availability**: Many hotel images are served behind CDN authentication
   (especially TripAdvisor). These will fail to load for vision analysis.

5. **Crawling legality**: Always review each site's Terms of Service before deploying
   in production. The Google Places API is the cleanest path for production data.
