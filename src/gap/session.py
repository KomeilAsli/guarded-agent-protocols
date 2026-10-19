"""Wire up a protocol, a world, two agents and the mediator."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .agents import RulePlanner, RuleRobot
from .crypto import KeyRegistry
from .mediator import Mediator
from .protocol import load_protocol
from .world import GridWorld, load_world

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROTOCOL = ROOT / "protocols" / "task_delegation.yaml"
DEFAULT_WORLD = ROOT / "scenarios" / "world.yaml"

PLANNER_ID, ROBOT_ID = "planner-1", "robot-1"


@dataclass
class Session:
    mediator: Mediator
    planner: RulePlanner
    robot: RuleRobot
    registry: KeyRegistry


PlannerFactory = Callable[[str, str, bytes], RulePlanner]   # (agent_id, peer_id, key) -> planner


def build_session(task: str, world_overrides: dict[str, Any] | None = None,
                  make_planner: PlannerFactory | None = None,
                  protocol_path: Path = DEFAULT_PROTOCOL, world_path: Path = DEFAULT_WORLD) -> Session:
    """Create a fresh session. Pass `make_planner` to use another planner, for example the LLM one."""
    protocol = load_protocol(protocol_path)
    world = GridWorld(load_world(world_path, world_overrides))
    registry = KeyRegistry()
    pkey = registry.register(PLANNER_ID, "planner")
    rkey = registry.register(ROBOT_ID, "robot")
    if make_planner is None:
        planner = RulePlanner(PLANNER_ID, ROBOT_ID, pkey, task)
    else:
        planner = make_planner(PLANNER_ID, ROBOT_ID, pkey)
    robot = RuleRobot(ROBOT_ID, PLANNER_ID, rkey, world, protocol.content["REQUEST"]["task"])
    med = Mediator(protocol, registry, world)
    med.add_agent(planner)
    med.add_agent(robot)
    return Session(med, planner, robot, registry)
