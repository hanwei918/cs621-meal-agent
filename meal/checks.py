"""Hard-constraint checks — pure code, shared by the approval gate (④), the scorer (②) and the
reference solver (①). One definition, so the gate, the grade and the gold cannot disagree.

Every check returns a list of (check, detail); an empty list means the plan + cart are valid.
checks: meals · diet · allergy · time · coverage · stock · budget · note · slot · energy (catalogue wm)
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .schema import Case, Ingredient, Plan, Profile, Recipe, StoreItem

DATA = Path(__file__).resolve().parent.parent / "data"
DATA_BY_CATALOG = {"v1": DATA, "wm": DATA.parent / "data_wm"}
FORBIDDEN_BY_DIET = {"vegetarian": {"chicken", "pork", "beef", "fish", "shellfish"},
                     "no_pork": {"pork"}, "no_beef": {"beef"}}


@dataclass
class World:
    """Everything that decides validity at one moment: catalogs, current store, current profile."""
    ingredients: dict[str, Ingredient]
    recipes: dict[str, Recipe]
    store: dict[str, StoreItem]
    profile: Profile
    log: list[str] = field(default_factory=list)
    note: object = None                    # NoteConstraints in force (declared by the agent, or gold when grading)
    targets: dict | None = None            # catalogue wm: meal/energy.targets(body), computed by code

    @classmethod
    def for_case(cls, case: Case) -> "World":
        d = DATA_BY_CATALOG[case.catalog]
        ing = {i["id"]: Ingredient(**i) for i in json.loads((d / "ingredients.json").read_text())}
        rec = {r["id"]: Recipe(**r) for r in json.loads((d / "recipes.json").read_text())}
        sto = {s["sku"]: StoreItem(**s) for s in json.loads((d / "store.json").read_text())}
        for sku, ov in case.store_overrides.items():
            sto[sku] = sto[sku].model_copy(update=ov)
        tg = None
        if case.body is not None:
            from .energy import targets
            tg = targets(case.body)
        return cls(ing, rec, sto, case.profile.model_copy(deep=True), targets=tg)


def recipe_violations(r: Recipe, w: World) -> list[tuple[str, str]]:
    out = []
    banned = set().union(*(FORBIDDEN_BY_DIET[d] for d in w.profile.diet)) if w.profile.diet else set()
    for i in r.grams:
        ing = w.ingredients[i]
        if ing.animal in banned:
            out.append(("diet", f"{r.id} contains {i} ({ing.animal})"))
        hit = set(ing.allergens) & set(w.profile.allergies)
        if hit:
            out.append(("allergy", f"{r.id} contains {i} ({', '.join(sorted(hit))})"))
    if r.minutes > w.profile.max_cook_minutes:
        out.append(("time", f"{r.id} takes {r.minutes} min > {w.profile.max_cook_minutes}"))
    if w.note is not None:
        if r.id in w.note.exclude_recipes:
            out.append(("note", f"{r.id} excluded by the user's note"))
        for i in r.grams:
            if i in w.note.exclude_ingredients:
                out.append(("note", f"{r.id} contains {i}, excluded by the user's note"))
    return out


def needs(plan: Plan, w: World) -> dict[str, int]:
    """Grams to BUY per ingredient: recipe grams × servings, summed, minus what is in the pantry."""
    total: dict[str, int] = {}
    for m in plan.meals:
        for i, g in w.recipes[m.recipe_id].grams.items():
            total[i] = total.get(i, 0) + math.ceil(g * w.profile.servings * m.portion)
    pantry = dict(w.profile.pantry)
    if w.note is not None:
        for i, g in w.note.pantry_add.items():
            pantry[i] = pantry.get(i, 0) + g
    return {i: g - pantry.get(i, 0) for i, g in total.items() if g > pantry.get(i, 0)}


def cart_total(cart: dict[str, int], w: World) -> float:
    return round(sum(w.store[s].price_sgd * n for s, n in cart.items()), 2)


def violations(plan: Plan, cart: dict[str, int], w: World) -> list[tuple[str, str]]:
    out = []
    p = w.profile
    slots = sorted((m.day, m.slot) for m in plan.meals)
    want = [(d, s) for d in range(1, p.days + 1) for s in range(1, p.meals_per_day + 1)]
    if slots != want:
        out.append(("meals", f"plan covers {len(slots)} meal slots, needs exactly {len(want)}"))
    for m in plan.meals:
        if m.recipe_id not in w.recipes:
            out.append(("meals", f"unknown recipe {m.recipe_id}"))
            continue
        out += recipe_violations(w.recipes[m.recipe_id], w)
        if w.targets is None and m.portion != 1.0:
            out.append(("meals", f"day {m.day} meal {m.slot}: portions are only offered in catalogue wm"))
        if w.targets is not None:
            want_type = "breakfast" if m.slot == 1 else "main"
            if w.recipes[m.recipe_id].meal_type != want_type:
                out.append(("slot", f"day {m.day} meal {m.slot}: {m.recipe_id} is not a {want_type} recipe"))
        if w.note is not None:
            for lim in w.note.slot_max_minutes:
                if (lim.day, lim.slot) == (m.day, m.slot) and w.recipes[m.recipe_id].minutes > lim.minutes:
                    out.append(("note", f"day {m.day} meal {m.slot}: {m.recipe_id} takes {w.recipes[m.recipe_id].minutes} min > {lim.minutes}"))
    known_plan = Plan(meals=[m for m in plan.meals if m.recipe_id in w.recipes])
    if w.targets is not None:                            # N-05: every day in its own band
        t = w.targets
        if t["status"] != "ok":
            out.append(("energy", f"no plan may be made: {t['status']} ({t.get('reason', '')})"))
        else:
            from .energy import day_totals
            days = day_totals(known_plan, w)
            for d in range(1, p.days + 1):
                k = days.get(d, {"kcal": 0.0})["kcal"]
                if not t["low"] - 1e-6 <= k <= t["high"] + 1e-6:
                    out.append(("energy", f"day {d}: {k:.0f} kcal outside {t['low']:.0f}–{t['high']:.0f}"))
    for i, g in needs(known_plan, w).items():
        have = sum(w.store[s].pack_g * n for s, n in cart.items() if s in w.store and w.store[s].ingredient == i)
        if have < g:
            out.append(("coverage", f"{i}: buying {have} g, needs {g} g"))
    for s, n in cart.items():
        if s not in w.store:
            out.append(("stock", f"unknown sku {s}"))
        elif n > w.store[s].stock:
            out.append(("stock", f"{s}: {n} packs, {w.store[s].stock} in stock"))
    if all(s in w.store for s in cart) and cart_total(cart, w) > p.budget_sgd + 1e-9:
        out.append(("budget", f"S${cart_total(cart, w):.2f} > budget S${p.budget_sgd:.2f}"))
    return out


def cheapest_cart(need: dict[str, int], w: World) -> dict[str, int] | None:
    """Cheapest packs covering `need`, respecting stock. Small catalog: try each SKU mix greedily by
    price per gram, then fall back to the next SKU when stock runs out. None if stock cannot cover."""
    cart: dict[str, int] = {}
    for i, g in sorted(need.items()):
        skus = sorted((s for s in w.store.values() if s.ingredient == i and s.stock > 0),
                      key=lambda s: (s.price_sgd / s.pack_g, s.sku))
        best = None
        for first in skus:                               # try each SKU as the main one
            left, pick = g, {}
            for s in [first] + [x for x in skus if x is not first]:
                n = min(s.stock, math.ceil(left / s.pack_g))
                if n > 0:
                    pick[s.sku] = n
                    left -= n * s.pack_g
                if left <= 0:
                    break
            if left <= 0:
                cost = sum(w.store[k].price_sgd * n for k, n in pick.items())
                if best is None or cost < best[0]:
                    best = (cost, pick)
        if best is None:
            return None
        for k, n in best[1].items():
            cart[k] = cart.get(k, 0) + n
    return cart
