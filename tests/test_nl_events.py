"""Case set nl_events: the user speaks mid-run. Messages are notices; each one revokes approval."""
from eval.harness import eval_fingerprint, load_cases, run_eval
from meal.baselines import situation
from meal.env import StoreEnv
from meal.fakes import OracleAgent
from meal.scoring import score
from tests.test_nl import order

E = {c.case_id: c for c in load_cases(case_set="nl_events")}


def test_frozen_sets_are_untouched():
    assert eval_fingerprint("nl").startswith("27dc68c1")


def test_message_arrives_as_a_notice_after_its_step():
    env = StoreEnv(E["e03"])
    seen = [env.call("view_cart").get("notices", []) for _ in range(3)]
    assert seen[:2] == [[], []] and any("10 minutes max" in n for n in seen[2])


def test_message_at_approval_revokes_it_and_reapproval_works():
    env = order(E["e05"], ["r07", "r10"])
    assert env.out.order is None and env.out.approved_hash is None    # "Looks good" still revoked the approval
    r = env.call("request_approval", reported_total_sgd=env.call("view_cart")["total_sgd"])
    assert env.call("place_order", token=r["token"])["ordered"] is True
    assert score(E["e05"], env.out, env.w).passed


def test_ignoring_a_message_fails():
    env = order(E["e02"], ["r01", "r07"])                                # message at approval: no egg
    r = env.call("request_approval", reported_total_sgd=env.call("view_cart")["total_sgd"])
    env.call("place_order", token=r["token"])
    s = score(E["e02"], env.out, env.w)
    assert env.out.order is not None and not s.passed and "note" in s.failed


def test_second_message_must_be_added_to_the_first():
    # declaring only the latest message (egg) drops cucumber; the gold reading has both
    env = order(E["e08"], ["r09", "r10"], declare={"exclude_ingredients": ["egg"]})
    r = env.call("request_approval", reported_total_sgd=env.call("view_cart")["total_sgd"])
    env.call("place_order", token=r["token"])
    assert env.out.order is not None and not score(E["e08"], env.out, env.w).passed


def test_a_message_cannot_relax_the_profile():
    env = order(E["e06"], ["r02", "r07"])                                # chicken, as the message asked
    assert env.out.order is None                                         # G1: profile is still vegetarian


def test_step_zero_situation_does_not_contain_the_messages():
    for c in E.values():
        assert all(e.text not in situation(StoreEnv(c)) for e in c.events)


def test_out_of_scope_mid_run_must_be_declined():
    env = order(E["e07"], ["r07", "r10"])
    assert not score(E["e07"], env.out, env.w).passed


def test_oracle_passes_every_message_case():
    assert run_eval(lambda c: OracleAgent(), list(E.values()), n_runs=1, write=False,
                    case_set="nl_events").summary()["pass_mean"] == 1.0
