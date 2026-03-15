"""
Query Parser Agent
------------------
Takes a raw user query and uses the LLM to decompose it into:
  - visual_features: things to look for in images
  - text_keywords:   words/phrases to scan for in reviews
  - context:         where in the hotel (lobby, room, pool, etc.)
  - negative_signals: things that would disqualify a match
"""

import json
from rich.console import Console
from agents.llm_client import chat

console = Console()

SYSTEM_PROMPT = """You are a hotel search query parser. Your job is to decompose a user's
hotel feature request into structured search signals that will be used to:
1. Scan hotel review text for matching mentions
2. Analyze hotel photos using computer vision

Return ONLY valid JSON, no markdown, no explanation. Use this exact schema:
{
  "visual_features": [...],   // what to look for in images (be specific about color, shape, style)
  "text_keywords": [...],     // words and phrases to search for in review text
  "context": [...],           // where in the hotel this feature might be found
  "negative_signals": [...],  // things that would mean it's NOT a match
  "summary": "..."            // one-sentence plain English description of what we're looking for
}"""


async def parse_query(raw_query: str) -> dict:
    """
    Returns a structured dict like:
    {
      "visual_features": ["dark purple couch", "purple upholstered sofa"],
      "text_keywords":   ["purple couch", "dark purple sofa", "purple furniture"],
      "context":         ["lobby", "lounge", "common area", "room"],
      "negative_signals": [],
      "summary": "Looking for a hotel with a dark purple couch"
    }
    """
    console.print(f"[bold cyan]🧠 Query Parser Agent[/] parsing: [italic]{raw_query}[/]")

    raw = await chat(
        system_prompt=SYSTEM_PROMPT,
        user_content=f"Parse this hotel feature request: {raw_query}",
        max_tokens=1000,
    )

    parsed = json.loads(raw)

    console.print(f"[green]✓ Query parsed[/] → {len(parsed['visual_features'])} visual features, "
                  f"{len(parsed['text_keywords'])} text keywords")
    return parsed
