from gap.messages import Action
from gap.world import GridWorld, load_world


def test_loads_world(world_path):
    spec = load_world(world_path)
    assert spec.shelves["A"] == (2, 1)
    assert spec.docks["2"] == (7, 5)
    assert spec.boxes["3"] == "A"
    assert (5, 3) in spec.restricted


def test_safe_path_avoids_restricted_zone(world_path):
    w = GridWorld(load_world(world_path))
    unsafe = w.shortest_path((2, 1), (7, 5))
    safe = w.shortest_path((2, 1), (7, 5), avoid=w.spec.restricted)
    assert unsafe is not None and safe is not None
    assert set(unsafe) & w.spec.restricted          # the short way is unsafe
    assert not set(safe) & w.spec.restricted
    assert len(safe) > len(unsafe)


def test_path_none_when_blocked(world_path):
    spec = load_world(world_path, {"extra_walls": [[6, 5], [7, 4]]})
    w = GridWorld(spec)
    assert w.shortest_path((0, 0), (7, 5), avoid=spec.restricted) is None


def test_move_pick_drop(world_path):
    w = GridWorld(load_world(world_path, {"robot_start": [2, 0]}))
    assert w.apply(Action("robot-1", "move", (2, 1))) == (True, "moved")
    assert w.apply(Action("robot-1", "pick", item="3"))[0]
    assert w.carrying == "3"
    assert w.apply(Action("robot-1", "drop", item="3"))[0]
    assert w.box_at["3"] == (2, 1)


def test_physics_rejects_bad_moves(world_path):
    w = GridWorld(load_world(world_path))
    assert not w.apply(Action("robot-1", "move", (2, 0)))[0]   # two steps
    w2 = GridWorld(load_world(world_path, {"robot_start": [3, 1]}))
    assert not w2.apply(Action("robot-1", "move", (4, 1)))[0]  # wall
