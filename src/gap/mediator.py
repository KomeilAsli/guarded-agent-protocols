"""The guarded channel between agents.

Agents never talk to each other or touch the world directly. Every message
goes through `send` and every action through `act`; both run the guards first.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from .crypto import KeyRegistry
from .guards import Decision, GuardSet, block, build_guards
from .messages import Action, Message
from .protocol import Protocol
from .world import GridWorld

if TYPE_CHECKING:
    from .agents import Agent


@dataclass(frozen=True)
class BlockedEvent:
    seq: int
    kind: str      # "message" or "action"
    guard: str
    actor: str
    detail: str
    state: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


class Mediator:
    def __init__(self, protocol: Protocol, registry: KeyRegistry, world: GridWorld,
                 guards: GuardSet | None = None) -> None:
        self.protocol = protocol
        self.registry = registry
        self.world = world
        self.guards = guards or build_guards(protocol, registry, world.spec)
        self.state = protocol.initial
        self.seen_ids: set[str] = set()
        self.queue: deque[Message] = deque()   # accepted messages waiting for delivery
        self.history: list[Message] = []       # all accepted messages
        self.blocked: list[BlockedEvent] = []
        self.trace: list[str] = []             # readable log of everything that happened
        self.agents: dict[str, Agent] = {}
        self._seq = 0
        self._actions_done = 0

    def add_agent(self, agent: Agent) -> None:
        self.agents[agent.agent_id] = agent

    # --- the two guarded entry points ---------------------------------------

    def send(self, msg: Message) -> Decision:
        d = self.guards.check_message(msg, self.state, self.seen_ids)
        desc = f"{msg.performative} {msg.content}" if msg.content else msg.performative
        if not d.allowed:
            self._record_block("message", msg.sender, desc, d)
            return d
        old = self.state
        self.state = self.guards.order.next_state(old, msg.performative)
        self.seen_ids.add(msg.msg_id)
        self.history.append(msg)
        self.queue.append(msg)
        self._log(f"{msg.sender} -> {msg.receiver}: {desc}  [{old} -> {self.state}]")
        return d

    def act(self, action: Action) -> Decision:
        desc = f"{action.name} {action.target or action.item}"
        d = self.guards.check_action(action, self.state, self.world.robot_pos)
        if d.allowed:
            ok, why = self.world.apply(action)
            if not ok:
                d = block("world", why)
        if not d.allowed:
            self._record_block("action", action.actor, desc, d)
            return d
        self._actions_done += 1
        self._log(f"{action.actor} {desc}")
        return d

    # --- running the session ------------------------------------------------

    def run(self, until: str | None = None, max_steps: int = 500) -> None:
        """Deliver messages and let agents act until the session ends, goes idle,
        or reaches the state `until` (used by scenarios to inject attacks)."""
        for _ in range(max_steps):
            if until is not None and self.state == until:
                return
            if self.queue:
                msg = self.queue.popleft()
                self.agents[msg.receiver].on_message(msg, self)
                continue
            if self.state in self.protocol.final:
                return
            before = self._activity()
            for agent in list(self.agents.values()):
                agent.tick(self)
            if self._activity() == before:
                return  # nobody did anything; stop instead of looping

    @property
    def finished(self) -> bool:
        return self.state in self.protocol.final

    # --- helpers ------------------------------------------------------------

    def _activity(self) -> tuple[int, int, int]:
        return (len(self.history), len(self.blocked), self._actions_done)

    def _record_block(self, kind: str, actor: str, detail: str, d: Decision) -> None:
        self._seq += 1
        ev = BlockedEvent(self._seq, kind, d.guard, actor, detail, self.state, d.reason)
        self.blocked.append(ev)
        self._log(f"BLOCKED [{d.guard}] {actor}: {detail} -- {d.reason}")

    def _log(self, line: str) -> None:
        self.trace.append(line)
