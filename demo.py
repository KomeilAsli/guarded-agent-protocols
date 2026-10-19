"""Run one task end to end and print the guarded dialogue.

    python demo.py
    python demo.py "move box 5 from shelf B to dock 1"

With GAP_USE_LLM=1 the argument is a free-form goal for the LLM planner (see src/gap/llm.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from gap.llm import LLMPlanner, client_from_env, llm_enabled  # noqa: E402
from gap.session import build_session  # noqa: E402
from gap.world import GridWorld  # noqa: E402


def draw(world: GridWorld, visited: set[tuple[int, int]]) -> str:
    """ASCII map: # wall, R restricted, A/B shelves, 1/2 docks, * path, @ robot."""
    spec = world.spec
    labels = {c: s for s, c in spec.shelves.items()} | {c: d for d, c in spec.docks.items()}
    rows = []
    for y in range(spec.height):
        row = []
        for x in range(spec.width):
            c = (x, y)
            ch = "#" if c in spec.walls else "R" if c in spec.restricted else labels.get(c, ".")
            if c in visited and ch == ".":
                ch = "*"
            if c == world.robot_pos:
                ch = "@"
            row.append(ch)
        rows.append(" ".join(row))
    return "\n".join(rows)


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else None
    if llm_enabled():
        # The argument is a free-form goal; the LLM turns it into a task line.
        goal = text or "Please bring box 3 from shelf A to dock 2."
        client = client_from_env()
        print(f"LLM planner on ({client.model} at {client.base_url})\nGoal: {goal}")
        session = build_session("", make_planner=lambda a, p, k: LLMPlanner(a, p, k, goal, client))
    else:
        session = build_session(text or "move box 3 from shelf A to dock 2")
    med = session.mediator

    visited = {med.world.robot_pos}
    apply = med.world.apply

    def tracking_apply(action):          # record cells the robot visits, for the map
        result = apply(action)
        visited.add(med.world.robot_pos)
        return result

    med.world.apply = tracking_apply
    try:
        med.run()
    except OSError as e:  # network problems on the optional LLM path
        sys.exit(f"LLM call failed: {e}")

    print(f"Task: {session.planner.task}\n")
    for line in med.trace:
        print("  " + line)
    print(f"\nFinal state: {med.state}   blocked events: {len(med.blocked)}\n")
    print(draw(med.world, visited))


if __name__ == "__main__":
    main()
