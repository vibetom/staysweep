"""
Vision Analysis Agent
---------------------
Given a hotel's image URLs and a parsed query, uses Claude vision to:
  1. Download and analyze each image
  2. Score each image for presence of the target feature
  3. Return the best-matching images with descriptions

Runs concurrently across hotels. Images are fetched and base64-encoded
before sending to Claude (avoids URL-loading issues with some CDNs).
"""

import asyncio
import base64
import httpx
import anthropic
import json
from rich.console import Console

console = Console()
client = anthropic.Anthropic()

# Max images to analyze per hotel — controls cost
MAX_IMAGES_PER_HOTEL = 8

# Min bytes for an image to be worth analyzing (skip tiny thumbnails)
MIN_IMAGE_BYTES = 5_000


async def fetch_image_as_base64(url: str) -> tuple[str, str] | None:
    """Returns (base64_data, media_type) or None if fetch fails."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client_http:
            resp = await client_http.get(url, follow_redirects=True,
                                          headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/jpeg")
            media_type = content_type.split(";")[0].strip()
            if media_type not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
                media_type = "image/jpeg"  # default fallback
            if len(resp.content) < MIN_IMAGE_BYTES:
                return None
            b64 = base64.standard_b64encode(resp.content).decode("utf-8")
            return b64, media_type
    except Exception as e:
        return None


async def analyze_images(hotel_name: str, images: list[dict], parsed_query: dict) -> dict:
    """
    Returns:
    {
      "score": 0.0-1.0,
      "matching_images": [{"url": "...", "description": "...", "confidence": 0.9}, ...],
      "reasoning": "..."
    }
    """
    if not images:
        return {"score": 0.0, "matching_images": [], "reasoning": "No images available"}

    # Prioritize official images then guest photos, cap at MAX_IMAGES
    sorted_images = sorted(images, key=lambda x: 0 if x.get("image_type") == "official" else 1)
    to_analyze = sorted_images[:MAX_IMAGES_PER_HOTEL]

    console.print(f"  [cyan]👁 Vision[/] analyzing {len(to_analyze)} images for {hotel_name}...")

    # Fetch all images concurrently
    fetch_tasks = [fetch_image_as_base64(img["url"]) for img in to_analyze]
    fetched = await asyncio.gather(*fetch_tasks)

    # Build vision message content
    content = []
    valid_images = []

    for i, (img_data, img_meta) in enumerate(zip(to_analyze, fetched)):
        if img_meta is None:
            continue
        b64_data, media_type = img_meta
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64_data,
            }
        })
        valid_images.append({
            "index": len(valid_images) + 1,
            "url": img_data["url"],
            "type": img_data.get("image_type", "unknown"),
            "caption": img_data.get("caption", ""),
        })

    if not valid_images:
        console.print(f"  [yellow]⚠ Vision: no loadable images for {hotel_name}[/]")
        return {"score": 0.0, "matching_images": [], "reasoning": "Images could not be loaded"}

    # Add the instruction text
    visual_features = parsed_query.get("visual_features", [])
    context_areas = parsed_query.get("context", [])

    content.append({
        "type": "text",
        "text": f"""You are analyzing hotel photos for a very specific feature.

Hotel: {hotel_name}
Feature to find: {parsed_query.get('summary', '')}
Visual characteristics to look for: {', '.join(visual_features)}
Expected location in hotel: {', '.join(context_areas) if context_areas else 'anywhere'}

I've provided {len(valid_images)} hotel image(s). Analyze each one carefully.

Return ONLY valid JSON:
{{
  "score": <0.0 to 1.0 overall confidence this hotel has the feature>,
  "image_results": [
    {{
      "image_number": <1-{len(valid_images)}>,
      "has_feature": <true/false>,
      "confidence": <0.0 to 1.0>,
      "description": "What you see relevant to the feature"
    }}
  ],
  "reasoning": "Overall conclusion in 1-2 sentences"
}}

Be precise. If you see a couch that is clearly dark purple/plum/violet colored, mark it as a match.
If the couch is blue, grey, or any other color, it is NOT a match."""
    })

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": content}]
        )

        raw = response.content[0].text.strip()
        result = json.loads(raw)

        score = result.get("score", 0.0)
        image_results = result.get("image_results", [])

        # Build matching images list
        matching = []
        for ir in image_results:
            if ir.get("has_feature") and ir.get("confidence", 0) > 0.4:
                idx = ir.get("image_number", 1) - 1
                if 0 <= idx < len(valid_images):
                    matching.append({
                        "url": valid_images[idx]["url"],
                        "description": ir.get("description", ""),
                        "confidence": ir.get("confidence", 0.5),
                    })

        color = 'green' if score > 0.5 else 'yellow' if score > 0.2 else 'dim'
        console.print(f"  [{color}]Vision score for {hotel_name}: {score:.2f}[/] "
                      f"({len(matching)} matching image{'s' if len(matching) != 1 else ''})")
        return {
            "score": score,
            "matching_images": matching,
            "reasoning": result.get("reasoning", ""),
        }

    except json.JSONDecodeError:
        console.print(f"  [red]✗ Vision: JSON parse error for {hotel_name}[/]")
        return {"score": 0.0, "matching_images": [], "reasoning": "Analysis failed"}
    except Exception as e:
        console.print(f"  [red]✗ Vision error for {hotel_name}: {e}[/]")
        return {"score": 0.0, "matching_images": [], "reasoning": f"Error: {e}"}
