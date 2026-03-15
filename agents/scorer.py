"""
Confidence Scorer & Reporter Agent
------------------------------------
Takes text + vision analysis results for a hotel and produces:
  - A final weighted confidence score
  - A human-readable summary with linked evidence
  - A structured result dict for the output report
"""

import anthropic
import json
from rich.console import Console

console = Console()
client = anthropic.Anthropic()


def compute_final_score(text_score: float, vision_score: float,
                         text_evidence: list, vision_matches: list) -> float:
    """
    Weighted combination:
    - Text carries 40%, vision carries 60%
    - Bonus for having both types of evidence
    - Penalize if one source is completely absent
    """
    has_text = len(text_evidence) > 0
    has_vision = len(vision_matches) > 0

    weighted = (text_score * 0.40) + (vision_score * 0.60)

    # Corroboration bonus: both text and vision agree
    if has_text and has_vision:
        weighted = min(1.0, weighted * 1.15)

    # Penalize if both scores are low but non-zero (could be hallucination)
    if text_score < 0.3 and vision_score < 0.3:
        weighted *= 0.7

    return round(weighted, 3)


async def generate_summary(hotel_name: str, query: str, final_score: float,
                            text_result: dict, vision_result: dict) -> str:
    """Uses Claude to write a concise, evidence-backed summary for the result."""
    if final_score < 0.1:
        return f"No evidence found that {hotel_name} has this feature."

    evidence_text = text_result.get("evidence", [])
    matching_images = vision_result.get("matching_images", [])

    prompt_data = {
        "hotel": hotel_name,
        "query": query,
        "confidence": f"{final_score*100:.0f}%",
        "text_evidence": evidence_text[:3],
        "vision_evidence": [m["description"] for m in matching_images[:3]],
        "text_reasoning": text_result.get("reasoning", ""),
        "vision_reasoning": vision_result.get("reasoning", ""),
    }

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system="""Write a concise, helpful 2-3 sentence summary for a hotel match result.
Be specific about the evidence. Mention what reviewers said and/or what was seen in photos.
Don't be generic. Start with the confidence level naturally woven in.""",
        messages=[{
            "role": "user",
            "content": f"Write a match summary for: {json.dumps(prompt_data)}"
        }]
    )

    return response.content[0].text.strip()


async def score_and_summarize(hotel_name: str, hotel_url: str, hotel_rating: float | None,
                               query: str, text_result: dict, vision_result: dict) -> dict:
    """
    Main entry point. Returns a complete result dict.
    """
    text_score = text_result.get("score", 0.0)
    vision_score = vision_result.get("score", 0.0)
    evidence_text = text_result.get("evidence", [])
    matching_images = vision_result.get("matching_images", [])

    final_score = compute_final_score(text_score, vision_score, evidence_text, matching_images)

    summary = await generate_summary(hotel_name, query, final_score, text_result, vision_result)

    return {
        "hotel_name": hotel_name,
        "hotel_url": hotel_url,
        "hotel_rating": hotel_rating,
        "query": query,
        "final_score": final_score,
        "text_score": text_score,
        "vision_score": vision_score,
        "evidence_text": evidence_text,
        "evidence_images": matching_images,
        "summary": summary,
    }
