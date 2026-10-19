"""HMAC signing of messages and a registry of known agents.

Each agent has its own secret key, shared only with the mediator. This is a
simulation: keys live in memory and there is no key exchange or rotation.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from .messages import Message


def new_key() -> bytes:
    return secrets.token_bytes(32)


def sign(msg: Message, key: bytes) -> Message:
    """Return a copy of msg with an HMAC-SHA256 signature."""
    digest = hmac.new(key, msg.canonical(), hashlib.sha256).hexdigest()
    return msg.with_signature(digest)


def verify(msg: Message, key: bytes) -> bool:
    expected = hmac.new(key, msg.canonical(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, msg.signature)


@dataclass(frozen=True)
class AgentRecord:
    role: str
    key: bytes


class KeyRegistry:
    """Maps agent ids to their role and secret key."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentRecord] = {}

    def register(self, agent_id: str, role: str, key: bytes | None = None) -> bytes:
        key = key or new_key()
        self._agents[agent_id] = AgentRecord(role, key)
        return key

    def role_of(self, agent_id: str) -> str | None:
        rec = self._agents.get(agent_id)
        return rec.role if rec else None

    def key_of(self, agent_id: str) -> bytes | None:
        rec = self._agents.get(agent_id)
        return rec.key if rec else None

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._agents
