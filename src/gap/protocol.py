"""Load and validate an interaction protocol written in YAML."""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ProtocolError(ValueError):
    """Raised when a protocol file is malformed."""


@dataclass(frozen=True)
class Transition:
    source: str
    message: str
    sender: str
    target: str


@dataclass(frozen=True)
class Protocol:
    name: str
    roles: tuple[str, ...]
    initial: str
    final: frozenset[str]
    transitions: tuple[Transition, ...]
    actor: str                                   # role allowed to act on the world
    allowed_actions: dict[str, frozenset[str]]   # state -> allowed action names
    content: dict[str, dict[str, str]]           # message -> {field: regex}
    deny_phrases: tuple[str, ...]

    @property
    def states(self) -> set[str]:
        states = {self.initial, *self.final}
        for t in self.transitions:
            states.update((t.source, t.target))
        return states

    @property
    def messages(self) -> set[str]:
        return {t.message for t in self.transitions}


def load_protocol(path: str | Path) -> Protocol:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return parse_protocol(data)


def parse_protocol(data: dict[str, Any]) -> Protocol:
    """Build a Protocol from a dict and check that it is well formed."""
    if not isinstance(data, dict):
        raise ProtocolError("protocol must be a mapping")
    for key in ("name", "roles", "initial", "final", "transitions"):
        if key not in data:
            raise ProtocolError(f"missing key: {key}")

    roles = tuple(data["roles"])
    if len(roles) < 2 or len(set(roles)) != len(roles):
        raise ProtocolError("roles must be at least two unique names")

    transitions = []
    seen: set[tuple[str, str]] = set()
    for i, raw in enumerate(data["transitions"]):
        try:
            t = Transition(str(raw["from"]), str(raw["message"]), str(raw["sender"]), str(raw["to"]))
        except (KeyError, TypeError) as e:
            raise ProtocolError(f"transition {i} needs from, message, sender and to") from e
        if t.sender not in roles:
            raise ProtocolError(f"transition {i}: unknown sender role '{t.sender}'")
        if (t.source, t.message) in seen:
            raise ProtocolError(f"transition {i}: duplicate ({t.source}, {t.message}); protocol must be deterministic")
        seen.add((t.source, t.message))
        transitions.append(t)

    final = frozenset(data["final"])
    for t in transitions:
        if t.source in final:
            raise ProtocolError(f"final state '{t.source}' must not have outgoing transitions")

    actions = data.get("actions", {}) or {}
    actor = str(actions.get("actor", roles[-1]))
    if actor not in roles:
        raise ProtocolError(f"unknown actor role '{actor}'")
    allowed = {str(s): frozenset(a) for s, a in (actions.get("allowed_in") or {}).items()}

    content: dict[str, dict[str, str]] = {}
    for msg, fields in (data.get("content") or {}).items():
        content[str(msg)] = {}
        for name, pattern in (fields or {}).items():
            try:
                re.compile(pattern)
            except re.error as e:
                raise ProtocolError(f"bad regex for {msg}.{name}: {e}") from e
            content[str(msg)][str(name)] = str(pattern)

    deny = tuple(str(p).lower() for p in (data.get("deny_phrases") or []))

    proto = Protocol(
        name=str(data["name"]),
        roles=roles,
        initial=str(data["initial"]),
        final=final,
        transitions=tuple(transitions),
        actor=actor,
        allowed_actions=allowed,
        content=content,
        deny_phrases=deny,
    )

    # Cross-checks that need the full protocol.
    unknown_states = set(allowed) - proto.states
    if unknown_states:
        raise ProtocolError(f"actions refer to unknown states: {sorted(unknown_states)}")
    unknown_msgs = set(content) - proto.messages
    if unknown_msgs:
        raise ProtocolError(f"content rules for unknown messages: {sorted(unknown_msgs)}")
    unreachable = proto.states - _reachable(proto)
    if unreachable:
        raise ProtocolError(f"unreachable states: {sorted(unreachable)}")
    return proto


def _reachable(proto: Protocol) -> set[str]:
    """States reachable from the initial state (breadth-first)."""
    seen, todo = {proto.initial}, deque([proto.initial])
    while todo:
        state = todo.popleft()
        for t in proto.transitions:
            if t.source == state and t.target not in seen:
                seen.add(t.target)
                todo.append(t.target)
    return seen
