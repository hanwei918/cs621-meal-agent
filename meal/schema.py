"""Data contracts every workstream plugs into (owner: ①; changes need the group's agreement).

Catalogs shared by all cases (data/): Ingredient, Recipe, StoreItem.
One case (cases/cNN.json): a user Profile, store overrides, events injected mid-run, and the gold
answer to "is there a feasible plan at all?" — written by the case author, cross-checked by the
reference solver, never taken from an agent run.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

DIETS = ("vegetarian", "no_pork", "no_beef")
ANIMALS = ("chicken", "pork", "beef", "fish", "shellfish")


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Ingredient(_M):
    id: str
    name: str
    allergens: list[str] = []              # peanut, shellfish, egg, dairy, soy, gluten
    animal: Optional[Literal["chicken", "pork", "beef", "fish", "shellfish"]] = None


class Recipe(_M):
    id: str
    name: str
    minutes: int
    grams: dict[str, int]                  # ingredient id → grams for ONE serving


class StoreItem(_M):
    sku: str
    ingredient: str
    pack_g: int
    price_sgd: float
    stock: int                             # packs available


class Profile(_M):
    diet: list[Literal["vegetarian", "no_pork", "no_beef"]] = []
    allergies: list[str] = []
    budget_sgd: float
    days: int = 3
    meals_per_day: int = 2
    servings: int = 1
    max_cook_minutes: int
    pantry: dict[str, int] = {}            # ingredient id → grams already at home


class Event(_M):
    after_step: int                        # fires once the agent has made this many tool calls
    kind: Literal["out_of_stock", "price_change", "preference"]
    sku: Optional[str] = None
    price_sgd: Optional[float] = None
    add_diet: Optional[Literal["vegetarian", "no_pork", "no_beef"]] = None
    add_allergy: Optional[str] = None


class Gold(_M):
    feasible: bool                         # after all events
    binding: Optional[Literal["budget", "diet", "time", "stock"]] = None   # for infeasible cases


class Case(_M):
    case_id: str
    synthetic: Literal[True] = True
    profile: Profile
    store_overrides: dict[str, dict] = {}  # sku → {"stock": n} and/or {"price_sgd": x}
    events: list[Event] = []
    gold: Gold
    tags: list[str]
    boundary: bool = False
    derivation: str = Field(min_length=20)  # how the gold was worked out, by hand

    @model_validator(mode="after")
    def _ok(self):
        if not self.gold.feasible and self.gold.binding is None:
            raise ValueError("an infeasible case must name the binding constraint")
        return self


# ---------------------------------------------------------------- what an agent produces

class Meal(_M):
    day: int                               # 1..days
    slot: int                              # 1..meals_per_day
    recipe_id: str


class Plan(_M):
    meals: list[Meal] = []


class Outcome(_M):
    """Filled in by the environment as the agent works — the agent never writes it directly."""
    plan: Plan = Plan()
    cart: dict[str, int] = {}              # sku → packs
    approved_hash: Optional[str] = None
    order: Optional[dict[str, int]] = None
    order_total_sgd: Optional[float] = None
    reported_total_sgd: Optional[float] = None
    declared_infeasible: bool = False
    declared_binding: Optional[str] = None
    unauthorized_attempts: int = 0         # place_order calls the gate refused
    steps: int = 0
