"""
Unified LLM calling for the agent pipeline. Groq (`openai/gpt-oss-120b`) is
primary -- fast enough (LPU inference) that a multi-agent debate with dozens
of sequential calls stays in the tens-of-seconds range rather than minutes.
Gemini is a fallback for when Groq errors (rate limit, outage, missing key),
not currently used for its long-context strength -- that's a later phase,
once full filings/transcripts are being fed to an agent.
"""

from __future__ import annotations

import json
import os
import re

from groq import Groq

GROQ_MODEL = "openai/gpt-oss-120b"
GEMINI_MODEL = "gemini-2.5-flash"

_groq_client: Groq | None = None


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        _groq_client = Groq(api_key=api_key)
    return _groq_client


def _call_groq(system: str, user: str) -> str:
    client = _get_groq_client()
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
        max_completion_tokens=600,
    )
    return completion.choices[0].message.content or ""


def _call_gemini(system: str, user: str) -> str:
    # Imported lazily so a missing/failed google-genai install doesn't break
    # Groq-only usage -- Gemini is a fallback, not a hard dependency.
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.4,
            response_mime_type="application/json",
        ),
    )
    return response.text or ""


def call_llm(system: str, user: str) -> str:
    """Groq first; falls back to Gemini if Groq errors for any reason.
    Raises only if both providers fail."""
    try:
        return _call_groq(system, user)
    except Exception as groq_error:
        try:
            return _call_gemini(system, user)
        except Exception as gemini_error:
            raise RuntimeError(
                f"Both LLM providers failed. Groq: {groq_error} | Gemini: {gemini_error}"
            ) from gemini_error


def parse_json_response(raw: str) -> dict:
    """Models occasionally wrap JSON in markdown fences despite
    instructions not to -- strip those before parsing rather than failing
    on well-formed-but-fenced output."""
    text = raw.strip()
    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    return json.loads(text)
