"""
Text Analysis Agent
-------------------
Given a hotel's reviews and a parsed query, uses Claude to:
  1. Scan all review text for mentions of the target feature
  2. Score the confidence of a match (0.0 - 1.0)
  3. Extract the most compelling evidence snippets

Designed to run concurrently across multiple hotels via asyncio.gather().
"""

import anthropic
import json
from rich.console import Console

console = Console()
client = anthropic.Anthropic()


async def analyze_reviews(hotel_name: str, reviews: list[dict], parsed_query: dict) -> dict:
    """
    Returns:
    {
      "score": 0.0-1.0,
      "evidence": ["snippet1", "snippet2", ...],
      "reasoning": "Brief explanation of score"
    }
    """
    if not reviews:
        return {"score": 0.0, "evidence": [], "reasoning": "No reviews available"}

    # Bundle reviews into a single prompt (max ~4000 chars to keep cost low)
    review_text = "\n\n".join([
        f"[Review {i+1} from {r.get('source','unknown')}]: {r['text']}"
        for i, r in enumerate(reviews[:25])  # cap at 25 reviews per hotel
    ])

    # Truncate if too long
    if len(review_text) > 6000:
        review_text = review_text[:6000] + "\n...[truncated]"

    query_context = json.dumps({
        "looking_for": parsed_query.get("summary", ""),
        "keywords": parsed_query.get("text_keywords", []),
        "context_areas": parsed_query.get("context", []),
        "negative_signals": parsed_query.get("negative_signals", []),
    })

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        system="""You are a hotel review analyst. Your job is to carefully read hotel reviews
and determine if they contain evidence of a specific feature the user is looking for.

Be generous in matching — if a review mentions something that's clearly the same feature
even with different wording (e.g. "deep plum sofa" matches "dark purple couch"), count it.

Return ONLY valid JSON, no markdown:
{
  "score": <float 0.0 to 1.0>,
  "evidence": ["exact quote or paraphrase from review 1", "..."],
  "reasoning": "1-2 sentence explanation of why you gave this score"
}

Score guide:
0.0  = No mention at all
0.2  = Vague or tangentially related mention
0.5  = Clear mention but not a direct match
0.8  = Strong match with good evidence
1.0  = Exact or near-exact match with multiple confirmations""",
        messages=[{
            "role": "user",
            "content": f"""Hotel: {hotel_name}

What we're looking for:
{query_context}

Hotel reviews:
{review_text}

Does this hotel have the feature described? Score it and extract evidence."""
        }]
    )

    raw = response.content[0].text.strip()
    result = json.loads(raw)

    score = result.get("score", 0.0)
    evidence = result.get("evidence", [])
    console.print(f"  [{'green' if score > 0.5 else 'yellow' if score > 0.2 else 'dim'}]"
                  f"Text score for {hotel_name}: {score:.2f}[/] "
                  f"({len(evidence)} evidence snippet{'s' if len(evidence) != 1 else ''})")
    return result
