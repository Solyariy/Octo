"""Cheap caption gate: does the description look like it contains a recipe?

English and Ukrainian only (never Russian). A pass only means the SLM gets to parse the
caption; whether that parse is enough is decided by `Recipe.is_complete`.
"""

import re
from dataclasses import dataclass, field

GATE_THRESHOLD = 4

_HEADER_RE = re.compile(
    r"\b(ingredients?|you(?:'ll)? need|instructions|directions|method|steps|recipe)\b"
    r"|(інгредієнти|складники|продукти|нам знадобиться|вам знадобиться|рецепт|приготування|спосіб приготування)",
    re.IGNORECASE,
)
_UNIT = (
    r"(g|gr|grams?|kg|ml|l|liters?|litres?|tbsp|tsp|tablespoons?|teaspoons?|cups?|oz|lbs?|pcs|"
    r"cloves?|pinch|"
    r"г|гр|грам[іа]?|кг|мл|л|ст\.?\s?л\.?|ч\.?\s?л\.?|склянк[аиу]|шт|зубч[икиів]+|пучок|дрібк[аи])"
)
_QUANTITY_RE = re.compile(
    rf"(?<![\w])(\d+(?:[.,]\d+)?|\d+/\d+|½|¼|¾)\s?{_UNIT}(?![\w])",
    re.IGNORECASE,
)
_TEMPERATURE_RE = re.compile(r"\d{2,3}\s?(°\s?[CF]?|градус\w*|degrees?)", re.IGNORECASE)
_DURATION_RE = re.compile(
    r"\d+\s?(min(ute)?s?|hours?|hrs?|хв\w*|год\w*)\b",
    re.IGNORECASE,
)
_LIST_LINE_RE = re.compile(r"^\s*([-•*▪️✅🔸🔹]|\d+[.)])\s*\S", re.MULTILINE)
_VERB_RE = re.compile(
    r"\b(bake|fry|boil|simmer|mix|whisk|stir|chop|roast|grill|saute|sauté|knead|season)\b"
    r"|(запік\w*|випік\w*|смаж\w*|вар\w*|змішай\w*|змішати|перемішай\w*|наріж\w*|збий\w*|додай\w*)",
    re.IGNORECASE,
)


@dataclass
class CaptionSignal:
    score: int
    hits: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.score >= GATE_THRESHOLD


def caption_signal(text: str | None) -> CaptionSignal:
    """Score the caption; each signal contributes a capped number of points."""
    if not text or not text.strip():
        return CaptionSignal(score=0)

    hits = {
        "header": len(_HEADER_RE.findall(text)),
        "quantity": len(_QUANTITY_RE.findall(text)),
        "temperature": len(_TEMPERATURE_RE.findall(text)),
        "duration": len(_DURATION_RE.findall(text)),
        "list_line": len(_LIST_LINE_RE.findall(text)),
        "verb": len(_VERB_RE.findall(text)),
    }
    caps = {
        "header": 2,
        "quantity": 3,
        "temperature": 1,
        "duration": 1,
        "list_line": 3,
        "verb": 2,
    }
    score = sum(min(hits[key], cap) for key, cap in caps.items())
    return CaptionSignal(score=score, hits=hits)
