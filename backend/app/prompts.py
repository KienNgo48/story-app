# Prompt templates — Section 6 of STORY_APP_PROJECT.md.
# Variables use {like_this} for str.format(); literal braces in JSON schemas
# are escaped as {{ and }}.

# --- 6.1 Story Bible Extraction --------------------------------------------

BIBLE_EXTRACT_SYSTEM = """You are a literary analyst building a structured reference document for a
ghostwriter who will continue this story. Extract only what is stated or
strongly implied by the text — do not invent details. Output valid JSON
matching the schema exactly. No prose outside the JSON."""

BIBLE_EXTRACT_USER = """Analyze the following story excerpt and extract a story bible.

<story_text>
{chunk_text}
</story_text>

Return JSON with this exact shape:

{{
  "pov": "string — narrative POV and tense, e.g. 'third limited, past tense'",
  "voice_notes": "string — 2-4 sentences on prose style: sentence length,
    dialogue density, formality, recurring devices",
  "characters": [
    {{
      "name": "string",
      "role": "protagonist | antagonist | supporting | minor",
      "traits": ["string"],
      "current_state": "string — what they know/want/feel as of the last
        scene in this excerpt",
      "relationships": [{{"to": "character name", "nature": "string"}}]
    }}
  ],
  "setting": {{
    "time_period": "string",
    "locations": ["string"]
  }},
  "established_facts": ["string — concrete facts the continuation must not
    contradict, e.g. 'Mara is left-handed', 'it is currently winter'"],
  "open_threads": ["string — unresolved questions or planted setups the
    reader will expect addressed"],
  "last_scene_summary": "string — 3-5 sentences on exactly where the text
    leaves off, ending mid-action if it does"
}}"""

# --- 6.2 Bible Update (incremental merge) -----------------------------------

BIBLE_UPDATE_SYSTEM = """You maintain a story bible for an ongoing narrative. You will be given the
current bible and a newly written passage. Update the bible to reflect the
new passage: add new characters/facts, update character states, close
resolved threads, add new open threads. Preserve everything still accurate.
Output the complete updated JSON — not a diff."""

BIBLE_UPDATE_USER = """<current_bible>
{existing_bible_json}
</current_bible>

<new_passage>
{newly_generated_text}
</new_passage>

Return the full updated story bible as JSON, same schema as before."""

# --- 6.3 Rolling Summary Update ---------------------------------------------

SUMMARY_UPDATE_SYSTEM = """You write concise running summaries of an ongoing story for an author's
own reference. Update the summary to incorporate the new passage. Keep it
under {max_words} words. Compress older events; keep recent events more
detailed. Write in plain prose, past tense, no headers."""

SUMMARY_UPDATE_USER = """<current_summary>
{existing_summary}
</current_summary>

<new_passage>
{newly_generated_text}
</new_passage>

Return only the updated summary text."""

# --- 6.4 Branch Options ------------------------------------------------------

BRANCH_OPTIONS_SYSTEM = """You are a plot consultant. Given the story so far, propose distinct
directions the narrative could take next. Each option must diverge from
the others in kind, not just detail — vary tone, pacing, and which
character drives the scene. Do not write the scene itself, only pitch it.
Output valid JSON only."""

BRANCH_OPTIONS_USER = """<story_bible>
{bible_json}
</story_bible>

<recent_summary>
{rolling_summary}
</recent_summary>

<last_2000_words>
{verbatim_recent_text}
</last_2000_words>

Propose exactly {n} possible directions for what happens next.
Each must use a different one of these approach types, matched to what best
fits the story:
- ESCALATE: raise stakes or introduce immediate conflict
- REVEAL: surface information the reader or a character didn't have
- QUIET: a character/relationship beat with low external action
- REVERSAL: subvert the direction the last passage seemed to set up

Return JSON:
{{
  "options": [
    {{
      "approach_type": "ESCALATE | REVEAL | QUIET | REVERSAL",
      "title": "string — 3-6 word label for the UI button",
      "pitch": "string — 2-3 sentences, written for the reader choosing,
        not as a scene draft",
      "characters_involved": ["string"],
      "tone_shift": "string — e.g. 'darker', 'unchanged', 'comic relief'"
    }}
  ]
}}"""

# --- 6.5 Continuation ---------------------------------------------------------

CONTINUATION_SYSTEM = """You are ghostwriting a continuation of an existing story. Match the
established voice exactly: {voice_notes}. Do not summarize, do not
break the fourth wall, do not add headers or scene labels. Write only the
continuation text, picking up immediately where the excerpt leaves off —
do not repeat or re-narrate the ending of the excerpt.

Hard constraints — do not contradict:
{established_facts}"""

CONTINUATION_USER = """<story_bible>
{bible_json}
</story_bible>

<recent_summary>
{rolling_summary}
</recent_summary>

<last_2000_words_verbatim>
{verbatim_recent_text}
</last_2000_words_verbatim>

The reader has chosen this direction for what happens next:
"{title}" — {pitch}

Write the next {target_length} of the story, continuing this direction.
Stay in {pov}. End the passage at a natural pause, not mid-sentence."""
