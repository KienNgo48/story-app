import json

from app.services.ai_client import call_model, parse_json
from app.prompts import (
    BIBLE_EXTRACT_SYSTEM,
    BIBLE_EXTRACT_USER,
    BIBLE_UPDATE_SYSTEM,
    BIBLE_UPDATE_USER,
)


# The doc's original 3-5k word chunk size (Section 5) targets a chapter/scene at a
# time for extraction quality, assuming a provider with a smaller context window and
# no meaningful per-call rate limit. Gemini's free tier caps requests per model per
# day (see AI_QUOTA_NOTES in ai_client.py), so a 4k-word chunk would turn one ingest
# of a 100k+ word novel into ~30 sequential calls and exhaust the daily quota on a
# single upload. gemini-3.5-flash-lite's 1M-token input window comfortably fits an
# entire novel in one call, so we chunk only when text is larger than that.
DEFAULT_CHUNK_WORDS = 120_000
BIBLE_MAX_TOKENS = 16384


def chunk_text(text: str, target_words: int = DEFAULT_CHUNK_WORDS) -> list[str]:
    """Split on paragraph boundaries into ~target_words chunks."""
    paragraphs = text.split("\n\n")
    chunks, current, count = [], [], 0
    for p in paragraphs:
        words = len(p.split())
        if count + words > target_words and current:
            chunks.append("\n\n".join(current))
            current, count = [], 0
        current.append(p)
        count += words
    if current:
        chunks.append("\n\n".join(current))
    return chunks


async def build_bible(text: str) -> dict:
    """Map-reduce bible extraction across chunks. Most stories — even full novels — are one chunk."""
    chunks = chunk_text(text)
    bible = parse_json(await call_model(
        BIBLE_EXTRACT_SYSTEM,
        BIBLE_EXTRACT_USER.format(chunk_text=chunks[0]),
        json_mode=True,
        max_tokens=BIBLE_MAX_TOKENS,
    ))
    for chunk in chunks[1:]:
        bible = parse_json(await call_model(
            BIBLE_UPDATE_SYSTEM,
            BIBLE_UPDATE_USER.format(existing_bible_json=json.dumps(bible), newly_generated_text=chunk),
            json_mode=True,
            max_tokens=BIBLE_MAX_TOKENS,
        ))
    return bible
