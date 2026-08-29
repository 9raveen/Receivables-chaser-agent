"""
Day 8 — LLM structured-output utility.

Single provider: Gemini (free tier, gemini-2.5-flash — chosen over the
newer 3.x Flash models for API/rate-limit maturity, not capability; see
chat discussion). No Claude/Anthropic fallback — ANTHROPIC_API_KEY isn't
available for this build, so a fallback path that can never actually run
is worse than no fallback (it'd silently KeyError if ever hit, not
degrade gracefully). If real resilience against Gemini's free-tier RPM
ceiling becomes necessary later, the honest option is a second FREE
provider (gemini-2.5-flash-lite as a separate quota bucket on the same
account, or a different provider like Groq's free tier) — not built here
since it hasn't been asked for.

Needs GEMINI_API_KEY in .env.
"""

from __future__ import annotations

import os
import re
import time
from typing import TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv()

T = TypeVar("T", bound=BaseModel)

GEMINI_MODEL = "gemini-3.6-flash"  # gemini-2.5-flash returned 404 (no longer
                                     # available to new API projects, per
                                     # Google's own error message pointing
                                     # here) — swapped after hitting that
                                     # in testing, not a design change

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        api_key = os.environ["GEMINI_API_KEY"]
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _strip_code_fences(text: str) -> str:
    """
    Gemini's JSON mode is generally clean, but defensively strip markdown
    code fences in case a ```json ... ``` wrapper slips through — cheap
    insurance, not a sign anything's broken if it never triggers.
    """
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return match.group(1) if match else text


def _call_gemini(prompt: str, response_model: type[BaseModel]) -> str:
    from google.genai import types

    client = _get_gemini_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_model,
        ),
    )
    return response.text


def call_with_structured_output(
    prompt: str,
    response_model: type[T],
    max_retries: int = 2,
    retry_backoff_seconds: float = 2.0,
) -> T:
    """
    Calls Gemini, validates the response against response_model, retries
    with the validation error appended to the prompt on failure — the
    model can see exactly what it got wrong rather than blindly retrying
    the same prompt.

    Also retries (with backoff) on rate-limit errors (HTTP 429) separately
    from validation errors — free-tier RPM ceilings are tight enough
    (~15 RPM on gemini-2.5-flash) that a burst of calls (e.g. the Day 10
    persona eval harness) can realistically hit this, unlike validation
    failures which are a model-output problem, not a quota problem.
    """
    current_prompt = prompt
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            raw_text = _call_gemini(current_prompt, response_model)
        except Exception as e:
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            last_error = e
            if is_rate_limit and attempt < max_retries:
                time.sleep(retry_backoff_seconds * (2 ** attempt))
                continue
            if attempt < max_retries:
                time.sleep(retry_backoff_seconds)
                continue
            raise RuntimeError(
                f"LLM call failed after {max_retries + 1} attempts: {e}"
            ) from e

        cleaned = _strip_code_fences(raw_text)
        try:
            return response_model.model_validate_json(cleaned)
        except ValidationError as e:
            last_error = e
            current_prompt = (
                f"{prompt}\n\n"
                f"Your previous response was:\n{cleaned}\n\n"
                f"That failed validation with this error:\n{e}\n\n"
                f"Return ONLY valid JSON matching the required schema, no other text."
            )

    raise RuntimeError(
        f"Structured output failed validation after {max_retries + 1} attempts: {last_error}"
    )