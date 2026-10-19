"""Messages exchanged between agents, and actions agents take in the world."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any

Cell = tuple[int, int]


@dataclass(frozen=True)
class Message:
    msg_id: str          # unique per message; used for replay detection
    sender: str          # agent id, e.g. "planner-1"
    receiver: str        # agent id
    performative: str    # message type, e.g. REQUEST
    content: dict[str, Any] = field(default_factory=dict)
    signature: str = ""  # hex HMAC over the canonical body

    def body(self) -> dict[str, Any]:
        """Everything except the signature."""
        return {
            "msg_id": self.msg_id,
            "sender": self.sender,
            "receiver": self.receiver,
            "performative": self.performative,
            "content": self.content,
        }

    def canonical(self) -> bytes:
        """Stable byte encoding of the body, so sender and verifier sign the same bytes."""
        return json.dumps(self.body(), sort_keys=True, separators=(",", ":")).encode("utf-8")

    def with_signature(self, signature: str) -> "Message":
        return replace(self, signature=signature)


@dataclass(frozen=True)
class Action:
    actor: str                 # agent id
    name: str                  # move, pick or drop
    target: Cell | None = None # destination cell for move
    item: str | None = None    # box id for pick and drop
