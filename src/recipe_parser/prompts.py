import json

from src.recipe_parser.schemas import Evidence, Recipe

Message = dict[str, str]

_SCHEMA = json.dumps(Recipe.model_json_schema(), ensure_ascii=False)

SYSTEM_PROMPT = f"""You extract cooking recipes from Instagram reels into JSON.
Sources are in English or Ukrainian. Every value you output (title, ingredient names, units,
notes, instructions, methods, equipment) MUST be written in English; translate Ukrainian.

Rules:
- Output exactly one JSON object matching this JSON Schema, and nothing else:
{_SCHEMA}
- Use only facts present in the sources. Never invent quantities, temperatures or times:
  use null when they are not stated. Quantities are optional.
- quantity is a number when one is stated (convert fractions: 1/2 -> 0.5), otherwise a short
  phrase like "to taste" or null.
- Temperature unit is "C" or "F". duration_min is in minutes.
- steps are ordered from 1. cooking_methods lists the distinct methods used (e.g. "bake").
- No markdown, no comments, no text before or after the JSON."""

CAPTION_TEMPLATE = """Extract the recipe from this Instagram reel description.

DESCRIPTION:
{caption}"""

COMBINE_TEMPLATE = """Extract the recipe from this Instagram cooking reel. The sources below
may overlap or contain noise (speech recognition errors, repeated on-screen text). Merge them
into one recipe.

DESCRIPTION:
{caption}

SPEECH TRANSCRIPT:
{transcript}

ON-SCREEN TEXT:
{overlay}"""

RETRY_TEMPLATE = """Your previous answer was rejected: {error}
Reply again with only the corrected JSON object."""

OCR_PROMPT = (
    "Transcribe all text visible in this video frame (subtitles, captions, ingredient lists, "
    "labels, oven or appliance displays) exactly as written, one line per text block. "
    "If there is no text, reply with an empty line."
)
PADDLE_OCR_PROMPT = "OCR:"

# Whisper language hints: speech is English or Ukrainian only.
ASR_LANGUAGES = ("en", "uk")


def caption_messages(caption: str) -> list[Message]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": CAPTION_TEMPLATE.format(caption=caption.strip())},
    ]


def combine_messages(evidence: Evidence) -> list[Message]:
    overlay = "\n".join(evidence.overlay_text) or "(none)"
    content = COMBINE_TEMPLATE.format(
        caption=evidence.caption.strip() or "(none)",
        transcript=evidence.transcript.strip() or "(none)",
        overlay=overlay,
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def retry_messages(
    messages: list[Message],
    raw_output: str,
    error: str,
) -> list[Message]:
    return [
        *messages,
        {"role": "assistant", "content": raw_output},
        {"role": "user", "content": RETRY_TEMPLATE.format(error=error)},
    ]
