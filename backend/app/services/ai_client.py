import asyncio
import json
import re
import httpx
from app.config import settings

GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)


class AIError(Exception):
    pass


async def call_model(system: str, user: str, json_mode: bool = False, max_tokens: int = 8192) -> str:
    """Single entry point for all LLM calls. Returns the model's text output.
    Swap this function's body to change providers — every caller keeps this signature."""
    if not settings.ai_api_key:
        raise AIError("AI_API_KEY is not set in .env")

    # This model always spends some of maxOutputTokens on hidden reasoning (it
    # returns a "thoughtSignature" even when unrequested); trying to disable that
    # via generationConfig.thinkingConfig gets a 400 INVALID_ARGUMENT on this model,
    # so the mitigation is just a generous max_tokens rather than turning it off.
    body: dict = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    # Gemini occasionally returns 429/503 under transient load — retry with backoff.
    attempts = 5
    for attempt in range(attempts):
        async with httpx.AsyncClient(timeout=240.0) as client:
            response = await client.post(GEMINI_URL, params={"key": settings.ai_api_key}, json=body)

        if response.status_code == 200:
            break
        if response.status_code in (429, 503) and attempt < attempts - 1:
            await asyncio.sleep(3 * (2 ** attempt))
            continue
        raise AIError(f"Model API error {response.status_code}: {response.text}")

    data = response.json()
    try:
        candidate = data["candidates"][0]
        text = candidate["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise AIError(f"Unexpected model response shape: {data}") from e

    if candidate.get("finishReason") == "MAX_TOKENS":
        raise AIError(
            f"Response truncated at max_tokens={max_tokens} before finishing — raise max_tokens for this call."
        )
    return text


def parse_json(text: str) -> dict:
    """Strip code fences and parse. Use for JSON-mode calls."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)
