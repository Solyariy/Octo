from typing import Literal

from pydantic import BaseModel, Field

MIN_INGREDIENTS = 3
MIN_STEPS = 1


class Ingredient(BaseModel):
    name: str = Field(min_length=1, description="Ingredient name in English")
    quantity: float | str | None = Field(
        default=None,
        description="Amount as a number, or a phrase like 'to taste'; null when not stated",
    )
    unit: str | None = Field(
        default=None,
        description="Unit in English (g, ml, tbsp, cup, pcs)",
    )
    notes: str | None = Field(
        default=None,
        description="Preparation note in English, e.g. 'diced'",
    )


class Temperature(BaseModel):
    value: float
    unit: Literal["C", "F"]


class Step(BaseModel):
    order: int = Field(ge=1)
    instruction: str = Field(min_length=1, description="What to do, in English")
    method: str | None = Field(
        default=None,
        description="Cooking method in English (bake, fry, boil, mix, air-fry, ...)",
    )
    temperature: Temperature | None = None
    duration_min: float | None = Field(default=None, ge=0)


class Recipe(BaseModel):
    title: str | None = None
    servings: int | None = Field(default=None, ge=1)
    ingredients: list[Ingredient] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    cooking_methods: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    total_time_min: float | None = Field(default=None, ge=0)

    def is_complete(self) -> bool:
        """Enough to skip audio/OCR. Quantities are optional and never counted."""
        return len(self.ingredients) >= MIN_INGREDIENTS and len(self.steps) >= MIN_STEPS


class Evidence(BaseModel):
    caption: str = ""
    transcript: str = ""
    overlay_text: list[str] = Field(default_factory=list)


ErrorKind = Literal["parse", "validation"]
ParsePath = Literal["caption", "av"]


class Attempt(BaseModel):
    raw_output: str
    error_kind: ErrorKind | None = None
    error: str | None = None
    seconds: float


class SlmRun(BaseModel):
    """One SLM stage (caption or combine) with all of its JSON attempts."""

    recipe: Recipe | None = None
    attempts: list[Attempt] = Field(default_factory=list)
    seconds: float = 0.0

    @property
    def json_errors(self) -> int:
        return sum(1 for a in self.attempts if a.error_kind is not None)

    @property
    def failed(self) -> bool:
        return self.recipe is None


class ParseResult(BaseModel):
    recipe: Recipe | None
    path: ParsePath
    evidence: Evidence
    caption_run: SlmRun | None = None
    combine_run: SlmRun | None = None
    stage_seconds: dict[str, float] = Field(default_factory=dict)
    models: dict[str, str] = Field(default_factory=dict)
