"""Turn raw SLM text into a validated `Recipe`.

There is deliberately no constrained decoding: how often a model breaks the JSON contract is
one of the benchmark metrics.
"""

import json
import re

from pydantic import ValidationError

from src.recipe_parser.schemas import ErrorKind, Recipe

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

MAX_ERROR_CHARS = 600


class RecipeOutputError(ValueError):
    def __init__(self, kind: ErrorKind, message: str):
        super().__init__(message)
        self.kind = kind


def extract_json(raw: str) -> str:
    """Strip reasoning blocks and code fences, then take the outermost `{...}`."""
    text = _THINK_RE.sub("", raw)
    if "</think>" in text:  # opening tag was part of the prompt
        text = text.split("</think>", 1)[1]
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise RecipeOutputError("parse", "no JSON object found in the output")
    return text[start : end + 1]


def parse_recipe(raw: str) -> Recipe:
    """Raise `RecipeOutputError` with kind `parse` (not JSON) or `validation` (wrong shape)."""
    candidate = extract_json(raw)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise RecipeOutputError("parse", f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RecipeOutputError("parse", "top-level JSON value is not an object")
    try:
        return Recipe.model_validate(data)
    except ValidationError as exc:
        message = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise RecipeOutputError("validation", message[:MAX_ERROR_CHARS]) from exc
