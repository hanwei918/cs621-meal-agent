# Interfaces between the five workstreams

Status 2026-10-21 — ✅ done · ⬜ TODO (owner). Change a contract only with the group's agreement.

```
 ① data + cases + solver ─┐
                          ├─► runner.run_case ─► ② score ─► ② run_eval ─► ⑤ report
 ③ agent / ⑤ baselines ───┘   (acts only through ④ StoreEnv tools; events fire by step count)
```

| | Contract | Status |
|---|---|---|
| ① | `Case` (schema.py): profile, store_overrides, events, `gold.feasible` (+ `binding` if not), tags, `derivation` | ✅ schema, 3 examples · ⬜ 27 more cases (≥ 1/3 boundary) |
| ① | Catalogs `data/ingredients.json`, `recipes.json`, `store.json` | ✅ first version (extend as cases need) |
| ① | `solve(world) -> (plan, cart) or None`, `diagnose(world)`; must agree with every hand-written gold | ✅ |
| ② | `violations(plan, cart, world)` — the one definition of the hard constraints | ✅ |
| ② | `score(case, outcome, world) -> Score(passed, failed=[checks])` | ✅ |
| ② | `run_eval(make_agent, cases, n_runs=3) -> Report`; `runs/` + `ledger.csv` | ✅ |
| ③ | Agent: `run(env) -> AgentUsage`, acting only via `env.call(tool, **args)`; tools in `env.TOOL_SPECS` | ✅ `MealAgent` (fake-client tested; no live run yet) |
| ④ | `StoreEnv`: tools, G1 constraint check before approval, G2 approval revoked by any change or event, G3 order only with the current token | ✅ |
| ⑤ | Same Agent interface: `SingleCallBaseline`, `FixedPlanner` | ⬜ |

Pass rule — feasible case: an order exists, the ordered plan + cart violate nothing in the
post-event world, the reported total is exact, no refused order attempts. Infeasible case: no order,
infeasibility reported with the gold binding constraint.
