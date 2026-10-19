"""Execution guards derived from a protocol (and the world's safe area).

`build_guards` reads the protocol and turns it into checks:
  - the transition list becomes a lookup table (protocol order and sender role)
  - the per-state action list becomes an allow-list (action in current state)
  - the content rules become strict field parsers, plus a deny-phrase filter
The safe area (grid bounds and restricted cells) comes from the world file.
Guards only decide; the mediator applies the decision and writes the log.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .crypto import KeyRegistry, verify
from .messages import Action, Cell, Message
from .protocol import Protocol
from .world import WorldSpec


@dataclass(frozen=True)
class Decision:
    allowed: bool
    guard: str = ""
    reason: str = ""


ALLOW = Decision(True)


def block(guard: str, reason: str) -> Decision:
    return Decision(False, guard, reason)


class AuthGuard:
    """Known sender, valid HMAC signature, no reused message id."""

    def __init__(self, registry: KeyRegistry) -> None:
        self.registry = registry

    def check(self, msg: Message, seen_ids: set[str]) -> Decision:
        key = self.registry.key_of(msg.sender)
        if key is None:
            return block("auth", f"unknown sender '{msg.sender}'")
        if not verify(msg, key):
            return block("auth", f"invalid signature for '{msg.sender}' (spoofed or tampered)")
        if msg.msg_id in seen_ids:
            return block("auth", f"replayed message id '{msg.msg_id}'")
        if msg.receiver not in self.registry:
            return block("auth", f"unknown receiver '{msg.receiver}'")
        return ALLOW


class OrderGuard:
    """The message must be a valid next step of the state machine, from the right role."""

    def __init__(self, protocol: Protocol, registry: KeyRegistry) -> None:
        self.registry = registry
        self.final = protocol.final
        self.table = {(t.source, t.message): t for t in protocol.transitions}

    def check(self, msg: Message, state: str) -> Decision:
        if state in self.final:
            return block("protocol_order", f"session already ended in state '{state}'")
        t = self.table.get((state, msg.performative))
        if t is None:
            allowed = sorted(m for (s, m) in self.table if s == state)
            return block("protocol_order",
                         f"{msg.performative} not allowed in state '{state}' (allowed: {', '.join(allowed)})")
        role = self.registry.role_of(msg.sender)
        if role != t.sender:
            return block("protocol_order", f"{msg.performative} must come from {t.sender}, not {role}")
        if self.registry.role_of(msg.receiver) == role:
            return block("protocol_order", "receiver has the same role as sender")
        return ALLOW

    def next_state(self, state: str, performative: str) -> str:
        return self.table[(state, performative)].target


def _normalize(text: str) -> str:
    """Lowercase, turn punctuation into spaces, collapse whitespace."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


class ContentGuard:
    """Strict field formats, plus a simple filter for instruction-like phrases."""

    def __init__(self, protocol: Protocol) -> None:
        self.rules = {m: {f: re.compile(p) for f, p in fields.items()}
                      for m, fields in protocol.content.items()}
        self.deny = [_normalize(p) for p in protocol.deny_phrases]

    def check(self, msg: Message) -> Decision:
        # 1. Look for instruction-like phrases in any text field.
        for name, value in msg.content.items():
            if isinstance(value, str):
                text = f" {_normalize(value)} "
                for phrase in self.deny:
                    if f" {phrase} " in text:
                        return block("injection", f"field '{name}' contains instruction-like phrase '{phrase}'")
        # 2. Every field must be declared and fully match its pattern.
        rules = self.rules.get(msg.performative, {})
        extra = set(msg.content) - set(rules)
        missing = set(rules) - set(msg.content)
        if extra:
            return block("content_format", f"unexpected fields in {msg.performative}: {sorted(extra)}")
        if missing:
            return block("content_format", f"missing fields in {msg.performative}: {sorted(missing)}")
        for name, pattern in rules.items():
            value = msg.content[name]
            if not isinstance(value, str) or not pattern.fullmatch(value):
                return block("content_format", f"field '{name}' does not match the required format")
        return ALLOW


class ActionGuard:
    """The actor's role and the current state must allow the action; moves must stay in the safe area."""

    def __init__(self, protocol: Protocol, registry: KeyRegistry, world: WorldSpec) -> None:
        self.registry = registry
        self.actor_role = protocol.actor
        self.allowed = protocol.allowed_actions
        self.width, self.height = world.width, world.height
        self.restricted = set(world.restricted)

    def check(self, action: Action, state: str, position: Cell) -> Decision:
        role = self.registry.role_of(action.actor)
        if role != self.actor_role:
            return block("action_state", f"role '{role}' may not act on the world")
        if action.name not in self.allowed.get(state, frozenset()):
            return block("action_state", f"action '{action.name}' not allowed in state '{state}'")
        if action.name == "move":
            t = action.target
            if t is None:
                return block("safe_area", "move needs a target cell")
            if not (0 <= t[0] < self.width and 0 <= t[1] < self.height):
                return block("safe_area", f"target {t} is outside the grid")
            if t in self.restricted:
                return block("safe_area", f"target {t} is in the restricted zone")
            if abs(t[0] - position[0]) + abs(t[1] - position[1]) != 1:
                return block("safe_area", f"move from {position} to {t} is not a single step")
        return ALLOW


@dataclass
class GuardSet:
    auth: AuthGuard
    order: OrderGuard
    content: ContentGuard
    action: ActionGuard

    def check_message(self, msg: Message, state: str, seen_ids: set[str]) -> Decision:
        """Run message guards in order: who sent it, is it the right step, is the content clean."""
        decision = self.auth.check(msg, seen_ids)
        if decision.allowed:
            decision = self.order.check(msg, state)
        if decision.allowed:
            decision = self.content.check(msg)
        return decision

    def check_action(self, action: Action, state: str, position: Cell) -> Decision:
        return self.action.check(action, state, position)


def build_guards(protocol: Protocol, registry: KeyRegistry, world: WorldSpec) -> GuardSet:
    """Derive all guards from the protocol, the agent registry and the world's safe area."""
    return GuardSet(
        auth=AuthGuard(registry),
        order=OrderGuard(protocol, registry),
        content=ContentGuard(protocol),
        action=ActionGuard(protocol, registry, world),
    )
