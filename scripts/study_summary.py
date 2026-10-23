"""Summarise user-study sessions (user-study/sessions/*.json, written by demo/server.py).

Prints counts only from what was recorded: no imputation, no invented participants. With no sessions it
says so. Run: .venv/bin/python scripts/study_summary.py
"""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSIONS = ROOT / "user-study" / "sessions"
LIKERT = ["understood", "knew_cart", "approve_easy", "trust_mode", "saves_time"]


def load(d: Path = SESSIONS) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))
            if not p.name.startswith("_")]                         # _spend.json is the demo's spend counter


def summary(recs: list[dict]) -> dict:
    presented = [r for r in recs if r.get("presenter_events")]          # demo-day runs, not study data
    recs = [r for r in recs if not r.get("presenter_events") and not r["participant"].startswith("ZZTEST")]
    by_mode = defaultdict(list)
    for r in recs:
        by_mode[r["form"].get("mode", "?")].append(r)
    out = {"sessions": len(recs), "participants": len({r["participant"] for r in recs}),
           "excluded_presenter_sessions": len(presented), "by_mode": {}}
    for mode, rs in sorted(by_mode.items()):
        res = [r["state"]["result"] for r in rs]
        dec = [a for r in rs for a in r["approvals"]]
        m = {"sessions": len(rs),
             "ordered": sum(x["ordered"] for x in res), "submitted": sum(x["submitted"] for x in res),
             "declined_by_agent": sum(x["declined"] for x in res), "infeasible": sum(x["infeasible"] for x in res),
             "orders_breaking_profile_or_declared": sum(bool(x["violations_against_profile_and_declared"]) for x in res),
             "unauthorized_attempts": sum(x["unauthorized_attempts"] for x in res),
             "user_asks_per_session": round(st.mean(x["user_asks"] for x in res), 2),
             "carts_declined_by_person": sum(not a["approved"] for a in dec),
             "median_seconds_to_decide": st.median(a["seconds_to_decide"] for a in dec) if dec else None,
             "messages_sent": sum(len(r["messages_sent"]) for r in rs),
             "questions_to_person": sum(len(r.get("questions", [])) for r in rs),
             "reading": dict(Counter(r["survey"].get("reading") or "—" for r in rs))}
        for k in LIKERT:
            v = [r["survey"].get(k) for r in rs if r["survey"].get(k)]
            m[k] = f"{st.median(v)} (n={len(v)})" if v else "—"
        out["by_mode"][mode] = m
    out["preferred_mode"] = dict(Counter(r["survey"].get("preferred_mode") or "—" for r in recs))
    mins = [r["survey"]["minutes_per_week_now"] for r in recs if r["survey"].get("minutes_per_week_now") is not None]
    out["self_reported_minutes_per_week_now"] = {"median": st.median(mins), "n": len(mins)} if mins else None
    out["missed"] = [r["survey"]["missed"] for r in recs if r["survey"].get("missed")]
    out["would_delegate_if"] = [r["survey"]["would_delegate_if"] for r in recs if r["survey"].get("would_delegate_if")]
    return out


if __name__ == "__main__":
    recs = load(Path(sys.argv[1]) if len(sys.argv) > 1 else SESSIONS)
    if not recs:
        sys.exit(f"no sessions in {SESSIONS} yet — run demo/server.py with participants first")
    print(json.dumps(summary(recs), indent=2, ensure_ascii=False))
