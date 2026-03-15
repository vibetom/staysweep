"""
LLM Client Wrapper
-------------------
Thin abstraction over the AI model provider.
Uses Google Gemini free tier with automatic retry and model fallback.

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

# Models to try in order — if one hits quota, fall back to the next
MODELS = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
]

MAX_RETRIES = 3
RETRY_BASE_DELAY = 5  # seconds


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set. Get a free key at https://aistudio.google.com/apikey")
        _client = genai.Client(api_key=api_key)
    return _client


def _clean_json(raw: str) -> str:
    """Strip markdown code fences that Gemini sometimes wraps around JSON."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


async def _call_with_retry(generate_fn):
    """
    Call a Gemini generate function with retry logic and model fallback.
    generate_fn takes a model name and returns the response.
    """
    last_error = None

    for model in MODELS:
        for attempt in range(MAX_RETRIES):
            try:
                response = await asyncio.to_thread(generate_fn, model)
                return _clean_json(response.text)
            except Exception as e:
                last_error = e
                error_str = str(e)

                # If quota exhausted or model unavailable, try next model
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "404" in error_str or "NOT_FOUND" in error_str:
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_BASE_DELAY * (attempt + 1)
                        await asyncio.sleep(delay)
                        continue
                    else:
                        # Exhausted retries for this model, try next
                        break
                else:
                    # Non-quota error, raise immediately
                    raise

    raise RuntimeError(
        f"All Gemini models exhausted. Last error: {last_error}\n"
        f"Tried models: {MODELS}\n"
        f"Fix: Go to https://aistudio.google.com/apikey and ensure your API key "
        f"has the Generative Language API enabled with free tier quota."
    )


async def chat(system_prompt: str, user_content: str, max_tokens: int = 1000) -> str:
    """Text-only LLM call. Returns the model's text response."""
    client = _get_client()

    def generate(model):
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=max_tokens,
        )
        return client.models.generate_content(
            model=model,
            contents=user_content,
            config=config,
        )

    return await _call_with_retry(generate)


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

    def generate(model):
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=max_tokens,
        )
        return client.models.generate_content(
            model=model,
            contents=parts,
            config=config,
        )

    return await _call_with_retry(generate)
