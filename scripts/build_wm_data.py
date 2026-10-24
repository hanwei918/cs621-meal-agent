"""Build data_wm/ (catalogue for case set `wm`, policy v0.4) from data/ plus nutrients and breakfasts.

data/ (catalogue v1) is not touched: the frozen case sets keep their world.

Nutrients are per 100 g, as eaten in the recipe's stated state (dry rice/pasta/noodles/oats, raw meat and
fish, canned chickpeas drained). They are SYNTHETIC APPROXIMATIONS rounded from typical USDA FoodData
Central entries, written by hand for a teaching benchmark (policy N-02: labelled synthetic). They are not
looked up per product and must not be used for real dietary advice.

Run: .venv/bin/python scripts/build_wm_data.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#             kcal  protein carb  fat     (per 100 g)
NUTRIENTS = {
    "rice":              (360, 7.0, 79.0, 0.6),
    "egg":               (143, 12.6, 0.7, 9.5),
    "spring_onion":      (32, 1.8, 7.3, 0.2),
    "soy_sauce":         (53, 8.0, 5.0, 0.6),
    "chicken_breast":    (120, 22.5, 0.0, 2.6),
    "broccoli":          (34, 2.8, 6.6, 0.4),
    "tofu":              (144, 15.8, 2.8, 8.7),
    "curry_paste":       (200, 3.0, 15.0, 14.0),
    "coconut_milk":      (197, 2.0, 2.8, 21.0),
    "noodles":           (350, 12.0, 72.0, 1.5),
    "peanut_butter":     (590, 25.0, 20.0, 50.0),
    "cucumber":          (15, 0.7, 3.6, 0.1),
    "pork_mince":        (263, 17.0, 0.0, 21.0),
    "dumpling_wrappers": (290, 9.0, 58.0, 1.5),
    "bok_choy":          (13, 1.5, 2.2, 0.2),
    "salmon":            (208, 20.0, 0.0, 13.0),
    "tomato":            (18, 0.9, 3.9, 0.2),
    "beef_slices":       (250, 18.0, 0.0, 19.0),
    "pasta":             (371, 13.0, 75.0, 1.5),
    "garlic":            (149, 6.4, 33.0, 0.5),
    "chickpeas":         (139, 7.0, 22.5, 2.6),
    "prawns":            (85, 20.0, 0.0, 0.5),
    "mushrooms":         (22, 3.1, 3.3, 0.3),
    "butter":            (717, 0.9, 0.1, 81.0),
    # breakfast ingredients, new in wm
    "oats":              (389, 16.9, 66.0, 6.9),
    "milk":              (50, 3.4, 5.0, 2.0),
    "banana":            (89, 1.1, 23.0, 0.3),
    "bread":             (247, 13.0, 41.0, 3.4),
    "yogurt":            (73, 10.0, 3.9, 2.0),
}
NEW_INGREDIENTS = [
    {"id": "oats", "name": "Rolled oats", "allergens": ["gluten"]},
    {"id": "milk", "name": "Low-fat milk", "allergens": ["dairy"]},
    {"id": "banana", "name": "Bananas"},
    {"id": "bread", "name": "Wholemeal bread", "allergens": ["gluten"]},
    {"id": "yogurt", "name": "Low-fat Greek yogurt", "allergens": ["dairy"]},
]
BREAKFASTS = [
    {"id": "b01", "name": "Oats with milk and banana", "minutes": 5, "meal_type": "breakfast",
     "grams": {"oats": 60, "milk": 200, "banana": 100}},
    {"id": "b02", "name": "Wholemeal toast with eggs", "minutes": 10, "meal_type": "breakfast",
     "grams": {"bread": 80, "egg": 100}},
    {"id": "b03", "name": "Yogurt with banana and oats", "minutes": 3, "meal_type": "breakfast",
     "grams": {"yogurt": 200, "banana": 100, "oats": 30}},
]
NEW_STORE = [
    {"sku": "oats_500g", "ingredient": "oats", "pack_g": 500, "price_sgd": 3.50, "stock": 10},
    {"sku": "milk_1l", "ingredient": "milk", "pack_g": 1000, "price_sgd": 2.60, "stock": 10},
    {"sku": "banana_6pk", "ingredient": "banana", "pack_g": 600, "price_sgd": 2.20, "stock": 10},
    {"sku": "bread_400g", "ingredient": "bread", "pack_g": 400, "price_sgd": 2.50, "stock": 10},
    {"sku": "yogurt_500g", "ingredient": "yogurt", "pack_g": 500, "price_sgd": 3.80, "stock": 10},
]


def main():
    src, out = ROOT / "data", ROOT / "data_wm"
    out.mkdir(exist_ok=True)
    ing = json.loads((src / "ingredients.json").read_text()) + NEW_INGREDIENTS
    for i in ing:
        i["kcal"], i["protein_g"], i["carb_g"], i["fat_g"] = NUTRIENTS[i["id"]]
    rec = json.loads((src / "recipes.json").read_text()) + BREAKFASTS
    sto = json.loads((src / "store.json").read_text()) + NEW_STORE
    for name, rows in (("ingredients", ing), ("recipes", rec), ("store", sto)):
        (out / f"{name}.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"data_wm: {len(ing)} ingredients, {len(rec)} recipes ({len(BREAKFASTS)} breakfasts), {len(sto)} store items")


if __name__ == "__main__":
    main()
