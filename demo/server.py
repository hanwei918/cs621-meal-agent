"""Demo + user-study app. A real person sets the profile, writes a note, picks the autonomy mode, approves
or declines carts, and can message the agent while it works. Every gate is the same code the evaluation uses.

Local:   .venv/bin/python demo/server.py            → http://127.0.0.1:8621
         (agent mode needs ANTHROPIC_API_KEY in this shell; "fixed" needs nothing)
Shared:  the same server in a container on Cloud Run behind Firebase Hosting (deploy/README.md).

Settings (environment):
  DEMO_PASSCODE       if set, every /api call needs it (header X-Passcode)
  DEMO_SESSION_CAP    US$ one run may spend before the agent is stopped (default 0.05)
  DEMO_TOTAL_CAP      US$ all runs together may spend; then new runs are refused (default 2.00)
  DEMO_MAX_LIVE       runs at the same time (default 3)
  DEMO_STORE          "file" (default: user-study/sessions/, git-ignored) or "firestore"
  HOST, PORT          bind address (default 127.0.0.1:8621; the container sets 0.0.0.0:$PORT)

Each participant has their own session id. A finished session, with the questionnaire, is stored once.
Synthetic store only. No real payments. Not nutrition or medical advice.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.pricing import cost_usd  # noqa: E402
from meal.checks import cart_total, violations  # noqa: E402
from meal.env import StoreEnv  # noqa: E402
from meal.schema import Case  # noqa: E402

SESSIONS = ROOT / "user-study" / "sessions"
PORT = int(os.environ.get("PORT", 8621))
HOST = os.environ.get("HOST", "127.0.0.1")
PASSCODE = os.environ.get("DEMO_PASSCODE", "")
SESSION_CAP = float(os.environ.get("DEMO_SESSION_CAP", 0.05))
TOTAL_CAP = float(os.environ.get("DEMO_TOTAL_CAP", 2.00))
MAX_LIVE = int(os.environ.get("DEMO_MAX_LIVE", 3))
APPROVAL_TIMEOUT_S = 15 * 60               # an unanswered cart is declined, so the agent thread ends
FORGET_AFTER_S = 3 * 3600                  # finished sessions are dropped from memory (already stored)


# ---------------------------------------------------------------- storage: local files or Firestore
class FileStore:
    def __init__(self, d: Path | None = None):
        self.d = d

    def _dir(self) -> Path:
        d = self.d or SESSIONS
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self, name: str, rec: dict) -> str:
        p = self._dir() / f"{name}.json"
        p.write_text(json.dumps(rec, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)

    def spent(self) -> float:
        p = self._dir() / "_spend.json"
        return json.loads(p.read_text())["usd"] if p.exists() else 0.0

    def add_spend(self, usd: float):
        p = self._dir() / "_spend.json"
        p.write_text(json.dumps({"usd": round(self.spent() + usd, 6)}))


class FirestoreStore:
    """Cloud Run instances are disposable: sessions and the running spend total live in Firestore."""

    def __init__(self):
        from google.cloud import firestore
        self.fs, self.db = firestore, firestore.Client()

    def save(self, name: str, rec: dict) -> str:
        self.db.collection("sessions").document(name).set(json.loads(json.dumps(rec, default=str)))
        return f"firestore:sessions/{name}"

    def spent(self) -> float:
        d = self.db.collection("meta").document("spend").get()
        return d.to_dict().get("usd", 0.0) if d.exists else 0.0

    def add_spend(self, usd: float):
        self.db.collection("meta").document("spend").set({"usd": self.fs.Increment(usd)}, merge=True)


STORE = FirestoreStore() if os.environ.get("DEMO_STORE") == "firestore" else FileStore()


# Weight-management sample people (policy v0.4). Synthetic: participants never enter body data.
PERSONAS = {
    "alex": {"label": "Alex · 30 · 175 cm · 80 kg → 72 kg · desk job",
             "body": dict(age_years=30, height_cm=175, weight_kg=80, equation_sex="male", activity="mostly_sedentary",
                          goal="weight_loss", target_weight_kg=72)},
    "bea": {"label": "Bea · 28 · 165 cm · 62 kg · keep weight · light exercise",
            "body": dict(age_years=28, height_cm=165, weight_kg=62, equation_sex="female", activity="lightly_active",
                         goal="maintenance")},
    "chloe": {"label": "Chloe · 45 · 160 cm · 58 kg → 52 kg · desk job",
              "body": dict(age_years=45, height_cm=160, weight_kg=58, equation_sex="female", activity="mostly_sedentary",
                           goal="weight_loss", target_weight_kg=52)},
}


def build_case(form: dict) -> Case:
    mode = form.get("mode", "confirm")
    persona = PERSONAS.get(form.get("persona") or "")
    auth = None
    if mode == "delegated":
        a = form.get("authorization") or {}
        auth = {"max_order_sgd": float(a.get("max_order_sgd", 30)), "max_period_sgd": float(a.get("max_period_sgd", 80)),
                "already_spent_sgd": float(a.get("already_spent_sgd", 0)), "valid_until": a.get("valid_until", "2026-12-31")}
    p = form["profile"]
    withheld = {}                                    # P-01: a blank field is missing; the agent must ask the person
    blank = lambda v: v is None or v == ""
    if blank(p.get("budget_sgd")):
        withheld["budget_sgd"] = None
    if blank(p.get("max_cook_minutes")):
        withheld["max_cook_minutes"] = None
    if p.get("allergies_unknown"):
        withheld["allergies"] = None
    profile = {"diet": p.get("diet", []), "allergies": [] if "allergies" in withheld else p.get("allergies", []),
               "budget_sgd": 0.0 if "budget_sgd" in withheld else float(p["budget_sgd"]),
               "days": int(p.get("days", 3)), "meals_per_day": 3 if persona else int(p.get("meals_per_day", 2)),
               "servings": int(p.get("servings", 1)),
               "max_cook_minutes": 0 if "max_cook_minutes" in withheld else int(p["max_cook_minutes"]),
               "pantry": {}, "note": (form.get("note") or "").strip()[:600] or None}
    return Case.model_validate({"case_id": "live", "profile": profile, "autonomy": mode, "authorization": auth,
                                "withheld": withheld,
                                **({"catalog": "wm", "body": persona["body"]} if persona else {}),
                                # Live authorizations expire on the Singapore calendar date, not a frozen eval date.
                                "today": datetime.now(timezone(timedelta(hours=8))).date().isoformat(),
                                "gold": {"feasible": True}, "tags": ["live"],
                                "derivation": "live demo session: there is no gold, a person judges the result"})


class Session:
    """One participant run. The agent thread blocks inside env.approver until the person answers."""

    def __init__(self, form: dict):
        self.sid = secrets.token_urlsafe(9)
        self.form, self.case = form, build_case(form)
        self.started = self.last_seen = time.time()
        self.steps: list[dict] = []
        self.status, self.error = "running", None
        self.pending_approval: dict | None = None
        self.approvals: list[dict] = []          # every ask: shown_at, seconds_to_decide, approved, comment
        self.messages_sent: list[dict] = []
        self.pending_question: dict | None = None
        self.questions: list[dict] = []          # every request_input that reached the person (E-04)
        self.presenter_events: list[dict] = []   # injected by a presenter: such sessions are not study data
        self._got_input = threading.Event()
        self._input: dict = {}
        self._answer = threading.Event()
        self._reply: tuple[bool, str] = (False, "")
        self.env = StoreEnv(self.case, approver=self._approve, answerer=self._ask)
        self._wrap_env()
        self.agent, self.model = self._make_agent(form.get("system", "agent"), form.get("model", "claude-haiku-5-5"))
        self.saved_to: str | None = None
        self._spend_booked = False
        threading.Thread(target=self._run, daemon=True).start()

    # ------------------------------------------------------------ agent side
    def _make_agent(self, system: str, model: str):
        if system == "fixed":
            from meal.baselines import FixedPlanner
            return FixedPlanner(), "none"
        from meal.agent import MealAgent
        if model not in ("claude-haiku-5-5", "claude-sonnet-5-5"):
            model = "claude-haiku-5-5"
        return MealAgent(model, max_cost_usd=SESSION_CAP), model

    def _wrap_env(self):
        call = self.env.call

        def logged(name, **args):
            res = call(name, **args)
            self.steps.append({"t": round(time.time() - self.started, 1), "tool": name, "args": args, "result": res})
            return res
        self.env.call = logged

    def _approve(self, request: dict) -> tuple[bool, str]:
        self._answer.clear()
        self.pending_approval = dict(request, shown_at=time.time())
        self.status = "awaiting_approval"
        if not self._answer.wait(APPROVAL_TIMEOUT_S):
            self._reply = (False, "no answer within 15 minutes")
        ok, comment = self._reply
        self.approvals.append({"shown_at": round(self.pending_approval["shown_at"] - self.started, 1),
                               "seconds_to_decide": round(time.time() - self.pending_approval["shown_at"], 1),
                               "total_sgd": request["total_sgd"], "approved": ok, "comment": comment,
                               "asked_because": request.get("asked_because")})
        self.pending_approval, self.status = None, "running"
        return ok, comment

    def _ask(self, fields: list, question: str) -> dict:
        self._got_input.clear()
        self.pending_question = {"fields": list(fields), "question": question, "shown_at": time.time()}
        self.status = "awaiting_input"
        self._got_input.wait(APPROVAL_TIMEOUT_S)
        answers = dict(self._input)
        self.questions.append({"fields": list(fields), "question": question, "answers": answers,
                               "seconds_to_answer": round(time.time() - self.pending_question["shown_at"], 1)})
        self.pending_question, self.status = None, "running"
        return answers

    def give_input(self, answers: dict):
        if self.pending_question is not None:
            self._input = {k: v for k, v in answers.items() if k in self.pending_question["fields"]}
            self._got_input.set()

    def inject(self, what: str) -> str:
        """Presenter controls. Each picks a target from the CURRENT cart so the change matters."""
        w, cart = self.env.w, self.env.out.cart
        biggest = max(cart, key=lambda s: cart[s] * w.store[s].price_sgd, default=None)
        if what == "sell_out":
            if biggest is None:
                return "the cart is empty: nothing to sell out yet"
            self.env.inject("out_of_stock", sku=biggest)
            msg = f"{w.ingredients[w.store[biggest].ingredient].name} ({biggest}) sells out"
        elif what == "price_up":
            if biggest is None:
                return "the cart is empty: nothing to reprice yet"
            new = round(w.store[biggest].price_sgd * 1.5, 2)
            self.env.inject("price_change", sku=biggest, price_sgd=new)
            msg = f"{biggest} now costs S${new:.2f}"
        elif what == "plan_only":
            self.env.inject("set_mode", mode="plan_only")
            msg = "the user switches to plan only"
        elif what == "timeout":
            self.env.inject("order_timeout", outcome="not_placed")
            msg = "the next order will time out (not created)"
        else:
            return "unknown control"
        self.presenter_events.append({"t": round(time.time() - self.started, 1), "what": what, "detail": msg})
        return msg

    def answer(self, ok: bool, comment: str):
        if self.pending_approval is not None:
            self._reply = (ok, comment)
            self._answer.set()

    def say(self, text: str):
        self.env.say(text)
        self.messages_sent.append({"t": round(time.time() - self.started, 1), "text": text})

    def _run(self):
        try:
            if self.model == "none" and self.env.withheld:      # the fixed planner has no way to ask
                raise RuntimeError("Fixed rules cannot ask questions, so they stop here. Fill in "
                                   + ", ".join(sorted(self.env.withheld)) + " or choose the agent.")
            self.agent.run(self.env)
            self.status = "done"
        except Exception as e:                   # surfaced in the UI; the session can still be saved
            self.status, self.error = "error", f"{type(e).__name__}: {e}"
            traceback.print_exc()
        finally:
            if not self._spend_booked:
                self._spend_booked = True
                STORE.add_spend(self.cost())

    @property
    def live(self) -> bool:
        return self.status in ("running", "awaiting_approval", "awaiting_input")

    # ------------------------------------------------------------ what the page shows
    def agent_text(self) -> list[str]:
        out = []
        for m in list(getattr(self.agent, "messages", [])):
            if m["role"] == "assistant":
                for b in m["content"]:
                    if getattr(b, "type", None) == "text" and b.text.strip():
                        out.append(b.text.strip())
        return out

    def cost(self) -> float:
        u = getattr(self.agent, "usage", None)
        return round(cost_usd(self.model, u.input_tokens, u.output_tokens, u.cache_write_tokens, u.cache_read_tokens), 4) if u else 0.0

    def state(self) -> dict:
        w, o = self.env.w, self.env.out
        names = {r.id: (r.name, r.minutes) for r in w.recipes.values()}
        plan = [{"day": m.day, "slot": m.slot, "recipe_id": m.recipe_id, "name": names[m.recipe_id][0],
                 "minutes": names[m.recipe_id][1], "portion": m.portion} for m in o.plan.meals if m.recipe_id in names]
        tg = w.targets
        if tg is not None:
            from meal.energy import day_totals
            day_kcal = {d: round(v["kcal"]) for d, v in day_totals(o.plan, w).items()}

        def line(s, n):
            it = w.store[s]
            return {"sku": s, "packs": n, "item": w.ingredients[it.ingredient].name, "pack_g": it.pack_g,
                    "price_sgd": it.price_sgd, "line_sgd": round(n * it.price_sgd, 2)}
        cart = [line(s, n) for s, n in o.cart.items() if s in w.store]
        checks = violations(o.plan, o.cart, w) if o.order is not None else []
        pa = self.pending_approval
        return {
            "sid": self.sid, "status": self.status, "error": self.error, "mode": self.case.autonomy, "model": self.model,
            "elapsed_s": round(time.time() - self.started, 1),
            "steps": [{"t": s["t"], "tool": s["tool"], "args": s["args"], "result": s["result"]} for s in list(self.steps)],
            "declared": o.declared, "plan": plan, "cart": cart, "total_sgd": cart_total(o.cart, w),
            "meals_per_day": w.profile.meals_per_day,
            "targets": None if tg is None else {k: (round(v) if isinstance(v, float) else v)
                                                for k, v in tg.items() if k in ("status", "reason", "target", "low",
                                                                                "high", "maintenance", "bmi")},
            "targets_seen": o.targets_seen, "day_kcal": day_kcal if tg is not None else None,
            "pending_approval": None if pa is None else {
                "total_sgd": pa["total_sgd"], "asked_because": pa.get("asked_because"),
                "plan": [dict(m, name=names[m["recipe_id"]][0], minutes=names[m["recipe_id"]][1]) for m in pa["plan"]],
                "day_kcal": day_kcal if tg is not None else None,
                "cart": [line(s, n) for s, n in pa["cart"].items()]},
            "result": {"review_status": o.review_status, "ordered": o.order is not None, "order_total_sgd": o.order_total_sgd, "approved_by": o.approved_by,
                       "submitted": o.submitted, "declined": o.declined, "decline_reason": o.decline_reason,
                       "infeasible": o.declared_infeasible, "binding": o.declared_binding,
                       "user_asks": o.user_asks, "unauthorized_attempts": o.unauthorized_attempts,
                       "stopped_for_cost": getattr(self.agent, "stopped_for_cost", False),
                       "violations_against_profile_and_declared": [f"{k}: {d}" for k, d in checks]},
            "pending_question": None if self.pending_question is None else {
                k: self.pending_question[k] for k in ("fields", "question")},
            "presenter_events": self.presenter_events,
            "burden": {"confirmations": o.user_asks, "questions": o.clarifications, "fields_asked": o.clarified_fields,
                       "avoidable_fields": o.avoidable_fields},
            "agent_text": self.agent_text(), "cost_usd": self.cost(), "saved_to": self.saved_to,
        }

    def save(self, survey: dict) -> str:
        if self.saved_to:
            return self.saved_to
        pid = "".join(c for c in str(self.form.get("participant", "P00")) if c.isalnum())[:8] or "P00"
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rec = {"participant": pid, "utc": ts, "form": self.form, "state": self.state(), "approvals": self.approvals,
               "messages_sent": self.messages_sent, "questions": self.questions,
               "presenter_events": self.presenter_events, "survey": survey, "code": _code_rev()}
        self.saved_to = STORE.save(f"{pid}_{self.case.autonomy}_{ts}_{self.sid[:4]}", rec)
        return self.saved_to


def _code_rev() -> str:
    if os.environ.get("CODE_REV"):                     # set at container build time
        return os.environ["CODE_REV"]
    import subprocess
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True).stdout.strip() or "unknown"
    except OSError:
        return "unknown"


SESSIONS_LIVE: dict[str, Session] = {}
_LOCK = threading.Lock()


def _gc():
    now = time.time()
    for sid, s in list(SESSIONS_LIVE.items()):
        if not s.live and now - s.last_seen > FORGET_AFTER_S:
            SESSIONS_LIVE.pop(sid, None)


def start_session(form: dict) -> tuple[Session | None, str | None]:
    with _LOCK:
        _gc()
        if sum(s.live for s in SESSIONS_LIVE.values()) >= MAX_LIVE:
            return None, "busy: too many people are testing right now, try again in a few minutes"
        if form.get("system") != "fixed" and STORE.spent() >= TOTAL_CAP:
            return None, "the demo's spending limit has been reached; please tell the organiser"
        s = Session(form)
        SESSIONS_LIVE[s.sid] = s
        return s, None


def catalog() -> dict:
    data = ROOT / "data_wm"                       # a superset of data/: names for every recipe in either catalogue
    return {"recipes": json.loads((data / "recipes.json").read_text()),
            "ingredients": json.loads((data / "ingredients.json").read_text())}


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = min(int(self.headers.get("Content-Length") or 0), 20_000)
        return json.loads(self.rfile.read(n) or b"{}")

    def _authorized(self) -> bool:
        return not PASSCODE or secrets.compare_digest(self.headers.get("X-Passcode", ""), PASSCODE)

    def _session(self, sid: str | None) -> Session | None:
        s = SESSIONS_LIVE.get(sid or "")
        if s:
            s.last_seen = time.time()
        return s

    def log_message(self, *a):                  # keep the terminal quiet during a session
        pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            body = (Path(__file__).parent / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == "/api/config":
            self._json({"passcode_required": bool(PASSCODE),
                        "personas": {k: v["label"] for k, v in PERSONAS.items()}})
        elif not self._authorized():
            self._json({"error": "wrong passcode"}, 401)
        elif u.path == "/api/catalog":
            self._json(catalog())
        elif u.path == "/api/state":
            s = self._session(parse_qs(u.query).get("sid", [None])[0])
            self._json(s.state() if s else {"status": "idle"})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._authorized():
            return self._json({"error": "wrong passcode"}, 401)
        try:
            b = self._body()
            if self.path == "/api/start":
                s, err = start_session(b)
                return self._json({"error": err}, 429) if err else self._json({"ok": True, "sid": s.sid})
            s = self._session(b.get("sid"))
            if s is None:
                return self._json({"error": "no such session"}, 409)
            if self.path == "/api/approve":
                s.answer(bool(b.get("approve")), str(b.get("comment", ""))[:500])
            elif self.path == "/api/answer":
                s.give_input(b.get("answers") or {})
            elif self.path == "/api/inject":
                if not s.live:
                    return self._json({"error": "the run has finished"}, 409)
                return self._json({"ok": True, "detail": s.inject(str(b.get("what", "")))})
            elif self.path == "/api/message":
                text = str(b.get("text", "")).strip()[:500]
                if text and s.live:
                    s.say(text)
            elif self.path == "/api/survey":
                return self._json({"ok": True, "saved_to": s.save(b.get("survey") or {})})
            else:
                return self._json({"error": "not found"}, 404)
            self._json({"ok": True})
        except Exception as e:
            self._json({"error": f"{type(e).__name__}: {e}"}, 400)


def serve(port: int = PORT, host: str = HOST) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    srv = serve()
    print(f"Meal agent demo on http://{HOST}:{PORT}  (Ctrl-C to stop)"
          f"{'  · passcode on' if PASSCODE else ''}  · caps US${SESSION_CAP}/run, US${TOTAL_CAP} total")
    srv.serve_forever()
