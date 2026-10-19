"""Rule-based agents. They run offline and are fully deterministic."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .crypto import sign
from .messages import Action, Message
from .world import GridWorld

if TYPE_CHECKING:
    from .mediator import Mediator

FINAL_REPLIES = {"REFUSE", "INFORM_DONE", "FAILURE"}


class Agent:
    role = ""

    def __init__(self, agent_id: str, peer_id: str, key: bytes) -> None:
        self.agent_id = agent_id
        self.peer_id = peer_id
        self.key = key
        self._count = 0

    def make(self, performative: str, content: dict[str, Any] | None = None) -> Message:
        """Create a signed message to the peer, with a fresh message id."""
        self._count += 1
        msg = Message(f"{self.agent_id}-{self._count}", self.agent_id, self.peer_id,
                      performative, content or {})
        return sign(msg, self.key)

    def on_message(self, msg: Message, med: Mediator) -> None:
        pass

    def tick(self, med: Mediator) -> None:
        pass


class RulePlanner(Agent):
    """Sends one task, then waits for the outcome."""

    role = "planner"

    def __init__(self, agent_id: str, peer_id: str, key: bytes, task: str) -> None:
        super().__init__(agent_id, peer_id, key)
        self.task = task
        self.sent = False
        self.outcome: tuple[str, dict] | None = None

    def next_task(self) -> str:
        return self.task

    def tick(self, med: Mediator) -> None:
        if not self.sent:
            self.sent = True
            med.send(self.make("REQUEST", {"task": self.next_task()}))

    def on_message(self, msg: Message, med: Mediator) -> None:
        if msg.performative in FINAL_REPLIES:
            self.outcome = (msg.performative, dict(msg.content))


class RuleRobot(Agent):
    """Checks a task, agrees or refuses, then moves one step per tick along a safe path."""

    role = "robot"

    def __init__(self, agent_id: str, peer_id: str, key: bytes, world: GridWorld, task_pattern: str) -> None:
        super().__init__(agent_id, peer_id, key)
        self.world = world
        self.pattern = re.compile(task_pattern)
        self.job: tuple[str, str, str] | None = None   # (box, shelf, dock)
        self.plan: list[Action] | None = None
        self.active = False

    def on_message(self, msg: Message, med: Mediator) -> None:
        if msg.performative != "REQUEST":
            return
        problem = self._check_task(str(msg.content.get("task", "")))
        if problem:
            med.send(self.make("REFUSE", {"reason": problem}))
        elif med.send(self.make("AGREE")).allowed:
            self.active = True

    def tick(self, med: Mediator) -> None:
        if not self.active:
            return
        if self.plan is None:
            self.plan = self._make_plan()
            if self.plan is None:
                self._finish(med, "FAILURE", {"reason": "no safe path"})
                return
        if not self.plan:
            self._finish(med, "INFORM_DONE")
            return
        if not med.act(self.plan.pop(0)).allowed:
            self._finish(med, "FAILURE", {"reason": "action was blocked"})

    def _check_task(self, task: str) -> str | None:
        """Return a short refusal reason, or None if the task can be done."""
        m = self.pattern.fullmatch(task)
        if not m:
            return "task not understood"
        box, shelf, dock = m["box"], m["shelf"], m["dock"]
        spec = self.world.spec
        if shelf not in spec.shelves:
            return f"unknown shelf {shelf.lower()}"
        if dock not in spec.docks:
            return f"unknown dock {dock}"
        if self.world.box_at.get(box) != spec.shelves[shelf]:
            return f"box {box} is not on shelf {shelf.lower()}"
        self.job = (box, shelf, dock)
        return None

    def _make_plan(self) -> list[Action] | None:
        """Path to the shelf, pick, path to the dock, drop. Avoids the restricted zone."""
        assert self.job is not None
        box, shelf, dock = self.job
        spec = self.world.spec
        to_shelf = self.world.shortest_path(self.world.robot_pos, spec.shelves[shelf], spec.restricted)
        to_dock = self.world.shortest_path(spec.shelves[shelf], spec.docks[dock], spec.restricted)
        if to_shelf is None or to_dock is None:
            return None
        return ([Action(self.agent_id, "move", c) for c in to_shelf]
                + [Action(self.agent_id, "pick", item=box)]
                + [Action(self.agent_id, "move", c) for c in to_dock]
                + [Action(self.agent_id, "drop", item=box)])

    def _finish(self, med: Mediator, performative: str, content: dict | None = None) -> None:
        self.active = False
        med.send(self.make(performative, content))
