"""Baselines (owner: ⑤). TODO — same runner.Agent interface, same cases, same model.

SingleCallBaseline — recipes + store + profile in ONE prompt → one JSON answer (plan + cart), then
                     set_plan / add_to_cart / request_approval / place_order are applied by code. It
                     cannot react to events; its final cart is judged against the post-event state.
FixedPlanner       — rule-based: filter recipes by profile, pick the cheapest combination, buy packs,
                     request approval, order. No LLM, no re-planning after events.
"""
from __future__ import annotations


class SingleCallBaseline:  # TODO(⑤)
    def __init__(self, model: str, client=None):
        raise NotImplementedError


class FixedPlanner:  # TODO(⑤)
    def __init__(self):
        raise NotImplementedError
