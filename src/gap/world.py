"""A small warehouse grid world with shelves, docks, boxes, walls and a restricted zone."""
from __future__ import annotations

import copy
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .messages import Action, Cell


@dataclass
class WorldSpec:
    width: int
    height: int
    robot_start: Cell
    shelves: dict[str, Cell]
    docks: dict[str, Cell]
    boxes: dict[str, str]                         # box id -> shelf name
    walls: set[Cell] = field(default_factory=set)
    restricted: set[Cell] = field(default_factory=set)


def _cell(v: Any) -> Cell:
    return (int(v[0]), int(v[1]))


def load_world(path: str | Path, overrides: dict[str, Any] | None = None) -> WorldSpec:
    """Load a world file. `overrides` lets a scenario change the start, boxes or walls."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    data = copy.deepcopy(data)
    o = overrides or {}
    if "robot_start" in o:
        data["robot_start"] = o["robot_start"]
    if "boxes" in o:
        data["boxes"] = o["boxes"]
    walls = [*data.get("walls", []), *o.get("extra_walls", [])]
    return WorldSpec(
        width=int(data["width"]),
        height=int(data["height"]),
        robot_start=_cell(data["robot_start"]),
        shelves={str(k): _cell(v) for k, v in data["shelves"].items()},
        docks={str(k): _cell(v) for k, v in data["docks"].items()},
        boxes={str(k): str(v) for k, v in data["boxes"].items()},
        walls={_cell(w) for w in walls},
        restricted={_cell(r) for r in data.get("restricted", [])},
    )


class GridWorld:
    """World state. `apply` enforces physics (walls, one step per move), not safety rules."""

    def __init__(self, spec: WorldSpec) -> None:
        self.spec = spec
        self.robot_pos: Cell = spec.robot_start
        self.carrying: str | None = None
        # Where each box is; None while the robot carries it.
        self.box_at: dict[str, Cell | None] = {b: spec.shelves[s] for b, s in spec.boxes.items()}

    def in_bounds(self, c: Cell) -> bool:
        return 0 <= c[0] < self.spec.width and 0 <= c[1] < self.spec.height

    def neighbors(self, c: Cell) -> list[Cell]:
        x, y = c
        return [n for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
                if self.in_bounds(n) and n not in self.spec.walls]

    def shortest_path(self, start: Cell, goal: Cell, avoid: set[Cell] | None = None) -> list[Cell] | None:
        """Breadth-first search. Returns cells after `start` up to `goal`, or None."""
        avoid = avoid or set()
        prev: dict[Cell, Cell | None] = {start: None}
        todo = deque([start])
        while todo:
            cur = todo.popleft()
            if cur == goal:
                path = []
                while cur != start:
                    path.append(cur)
                    cur = prev[cur]  # type: ignore[assignment]
                return path[::-1]
            for n in self.neighbors(cur):
                if n not in prev and n not in avoid:
                    prev[n] = cur
                    todo.append(n)
        return None

    def apply(self, action: Action) -> tuple[bool, str]:
        """Change the world. Returns (ok, reason)."""
        if action.name == "move":
            t = action.target
            if t is None or not self.in_bounds(t) or t in self.spec.walls:
                return False, f"cannot move to {t}"
            if abs(t[0] - self.robot_pos[0]) + abs(t[1] - self.robot_pos[1]) != 1:
                return False, "move must be one step"
            self.robot_pos = t
            return True, "moved"
        if action.name == "pick":
            if self.carrying is not None:
                return False, "already carrying a box"
            if action.item not in self.box_at or self.box_at[action.item] != self.robot_pos:
                return False, f"box {action.item} is not here"
            self.box_at[action.item] = None
            self.carrying = action.item
            return True, "picked"
        if action.name == "drop":
            if self.carrying != action.item:
                return False, f"not carrying box {action.item}"
            self.box_at[action.item] = self.robot_pos
            self.carrying = None
            return True, "dropped"
        return False, f"unknown action '{action.name}'"
