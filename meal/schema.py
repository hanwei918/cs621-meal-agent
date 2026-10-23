"""Data contracts every workstream plugs into (owner: ①; changes need the group's agreement).

Catalogs shared by all cases (data/): Ingredient, Recipe, StoreItem.
One case (cases/cNN.json): a user Profile, store overrides, events injected mid-run, and the gold
answer to "is there a feasible plan at all?" — written by the case author, cross-checked by the
reference solver, never taken from an agent run.
"""
from __future__ import annotations

from datetime import date
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
    description: Optional[str] = None      # store text shown to the agent — untrusted data (policy A-02)


class Profile(_M):
    diet: list[Literal["vegetarian", "no_pork", "no_beef"]] = []
    allergies: list[str] = []
    budget_sgd: float
    days: int = 3
    meals_per_day: int = 2
    servings: int = 1
    max_cook_minutes: int
    pantry: dict[str, int] = {}            # ingredient id → grams already at home
    note: Optional[str] = None             # the user's own words (case set nl); the agent must interpret it


AUTONOMY = ("plan_only", "confirm", "delegated")


class StandingAuthorization(_M):
    """Mode ③: what the user lets the agent buy without asking (policy O-02). Enforced in code."""
    max_order_sgd: float                   # one order may not exceed this
    max_period_sgd: float                  # all orders in the current period together
    already_spent_sgd: float = 0.0         # spent earlier in this period
    valid_until: date                      # compared with Case.today
    revoked: bool = False


class Event(_M):
    on: Literal["step", "approval"] = "step"   # step: after the agent's Nth tool call;
                                               # approval: the moment the user first approves a cart
    after_step: int = 0
    kind: Literal["out_of_stock", "price_change", "preference", "revoke_authorization", "user_message"]
    sku: Optional[str] = None
    price_sgd: Optional[float] = None
    add_diet: Optional[Literal["vegetarian", "no_pork", "no_beef"]] = None
    add_allergy: Optional[str] = None
    text: Optional[str] = None                 # user_message: what the user says mid-run, in their own words;
                                               # Gold.note is the author's reading of the note AND every message


class SlotLimit(_M):
    day: int
    slot: int
    minutes: int


class NoteConstraints(_M):
    """What a user's free-text note means, as code-checkable constraints. The agent declares its reading
    (declare_constraints, enforced by the gate); the case author writes the gold reading (Gold.note)."""
    exclude_ingredients: list[str] = []
    exclude_recipes: list[str] = []
    slot_max_minutes: list[SlotLimit] = []
    pantry_add: dict[str, int] = {}        # food the user says is already at home (grams)


class Witness(_M):
    """A plan the case author chose by hand that proves feasibility; its cart is the cheapest cover
    of that plan's needs. Tests check it passes every hard constraint in the post-event world."""
    recipes: list[str]                     # cycled over the day × meal slots in order
    meals: Optional[list[str]] = None      # or: one recipe per slot, in day/slot order (for slot limits)
    cart: dict[str, int]


class Gold(_M):
    feasible: bool                         # after all events
    binding: Optional[Literal["budget", "diet", "time", "stock"]] = None   # for infeasible cases
    witness: Optional[Witness] = None      # for feasible cases
    within_scope: Optional[bool] = None    # mode ③ only: can a valid plan be ordered WITHOUT asking the user?
    note: Optional[NoteConstraints] = None # case set nl: the author's reading of Profile.note
    out_of_scope: bool = False             # policy P-02: the request must be declined, not planned


class Case(_M):
    case_id: str
    synthetic: Literal[True] = True
    profile: Profile
    autonomy: Literal["plan_only", "confirm", "delegated"] = "confirm"   # ① ② ③; case set v1 is all ②
    authorization: Optional[StandingAuthorization] = None                # required for ③
    today: date = date(2026, 10, 25)       # the simulated date, for authorization expiry
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
        if self.autonomy == "plan_only" and any(e.on == "approval" for e in self.events):
            raise ValueError("plan-only (①) cases never reach approval, so cannot have approval events")
        if self.autonomy == "delegated" and self.authorization is None:
            raise ValueError("a delegated (③) case needs a standing authorization")
        if self.autonomy == "delegated" and self.gold.feasible and self.gold.within_scope is None:
            raise ValueError("a feasible delegated case must say whether it fits the authorization")
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
    unauthorized_attempts: int = 0         # order/approval calls the gate refused (incl. outside the mode)
    steps: int = 0
    submitted: bool = False                # mode ①: a plan + list was submitted and passed the checks
    approved_by: Optional[Literal["user", "standing"]] = None   # who approved the cart that was ordered
    user_asks: int = 0                     # times the user had to be asked — the burden metric
    declared: Optional[dict] = None        # the agent's reading of the note (declare_constraints)
    declined: bool = False                 # decline_request was called (policy P-02)
    decline_reason: Optional[str] = None
