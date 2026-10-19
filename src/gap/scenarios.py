"""Run normal and attack scenarios and compare the outcome with what was expected."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from .crypto import new_key, sign
from .guards import Decision
from .messages import Action, Message
from .session import ROOT, Session, build_session

DEFAULT_SCENARIOS = ROOT / "scenarios" / "scenarios.yaml"


@dataclass
class Result:
    name: str
    type: str
    expected: str
    actual: str
    decision: str          # "blocked" or "allowed"
    guard: str
    reason: str
    as_expected: bool
    known_limitation: bool
    blocked_events: list[dict]


def load_scenarios(path: str | Path = DEFAULT_SCENARIOS) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _inject(s: Session, spec: dict[str, Any]) -> Decision:
    med = s.mediator
    kind = spec["kind"]
    if kind == "action":
        target = tuple(spec["target"]) if "target" in spec else None
        return med.act(Action(spec["actor"], spec["action"], target, spec.get("item")))
    if kind == "replay":
        return med.send(med.history[spec.get("index", 0)])
    if kind == "message":
        sender = spec["sender"]
        receiver = spec.get("receiver", "robot-1" if sender != "robot-1" else "planner-1")
        msg = Message(f"injected-{sender}", sender, receiver, spec["performative"], dict(spec.get("content") or {}))
        key = s.registry.key_of(sender) if spec.get("sign_with", "own") == "own" else None
        msg = sign(msg, key or new_key())
        if "tamper_content" in spec:          # change content after signing
            msg = replace(msg, content=dict(spec["tamper_content"]))
        return med.send(msg)
    raise ValueError(f"unknown inject kind: {kind}")


def _describe(decision: str, guard: str, state: str | None) -> str:
    if decision == "blocked":
        return f"blocked by {guard}" if guard else "blocked"
    return f"allowed, ends in {state}" if state else "allowed"


def run_scenario(sc: dict[str, Any]) -> Result:
    s = build_session(sc["task"], sc.get("world"))
    med = s.mediator
    until = sc.get("run_until")
    med.run(until=until)
    if until is not None and med.state != until:
        raise RuntimeError(f"{sc['name']}: never reached state '{until}' (got '{med.state}')")
    if "inject" in sc:
        _inject(s, sc["inject"])

    # The first blocked event decides the outcome.
    first = med.blocked[0] if med.blocked else None
    decision = "blocked" if first else "allowed"
    guard = first.guard if first else ""
    reason = first.reason if first else "-"

    exp = sc["expect"]
    ok = (decision == exp["decision"]
          and exp.get("guard", guard) == guard
          and exp.get("final_state", med.state) == med.state)
    return Result(
        name=sc["name"],
        type=sc.get("type", ""),
        expected=_describe(exp["decision"], exp.get("guard", ""), exp.get("final_state")),
        actual=_describe(decision, guard, med.state if "final_state" in exp else None),
        decision=decision,
        guard=guard,
        reason=reason,
        as_expected=ok,
        known_limitation=bool(sc.get("known_limitation")),
        blocked_events=[{"scenario": sc["name"], **e.to_dict()} for e in med.blocked],
    )


def run_all(path: str | Path = DEFAULT_SCENARIOS) -> list[Result]:
    return [run_scenario(sc) for sc in load_scenarios(path)]
