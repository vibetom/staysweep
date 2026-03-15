"""
LLM Client Wrapper
-------------------
Thin abstraction over the AI model provider.
Currently uses Google Gemini 2.0 Flash (free tier: 15 RPM, 1M tokens/day).

All agent modules call these two functions instead of a provider SDK directly,
making it trivial to swap models in the future.
"""

import asyncio
import base64
import json
import os
import re

from google import genai
from google.genai import types

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set. Get a free key at https://aistudio.google.com/apikey")
        _client = genai.Client(api_key=api_key)
    return _client


MODEL = "gemini-2.0-flash"


def _clean_json(raw: str) -> str:
    """Strip markdown code fences that Gemini sometimes wraps around JSON."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


async def chat(system_prompt: str, user_content: str, max_tokens: int = 1000) -> str:
    """Text-only LLM call. Returns the model's text response."""
    client = _get_client()

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        max_output_tokens=max_tokens,
    )

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=MODEL,
        contents=user_content,
        config=config,
    )

    return _clean_json(response.text)


async def chat_with_images(
    system_prompt: str,
    images: list[tuple[bytes, str]],
    text_prompt: str,
    max_tokens: int = 1000,
) -> str:
    """
    Multimodal LLM call with images + text.

    Args:
        system_prompt: System instruction for the model.
        images: List of (raw_bytes, media_type) tuples, e.g. (b'...', 'image/jpeg').
        text_prompt: The text instruction that accompanies the images.
        max_tokens: Max output tokens.

    Returns the model's text response.
    """
    client = _get_client()

    parts = []
    for img_bytes, media_type in images:
        parts.append(types.Part.from_bytes(data=img_bytes, mime_type=media_type))
    parts.append(types.Part.from_text(text=text_prompt))

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        max_output_tokens=max_tokens,
    )

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=MODEL,
        contents=parts,
        config=config,
    )

    return _clean_json(response.text)
