from gap.session import build_session

TASK = "move box 3 from shelf A to dock 2"


def test_normal_task_completes():
    s = build_session(TASK)
    s.mediator.run()
    assert s.mediator.state == "done"
    assert s.mediator.blocked == []
    assert s.robot.world.box_at["3"] == (7, 5)
    assert s.planner.outcome == ("INFORM_DONE", {})


def test_robot_never_enters_restricted_zone():
    s = build_session(TASK)
    seen = []
    original = s.robot.world.apply

    def spy(action):
        ok, why = original(action)
        seen.append(s.robot.world.robot_pos)
        return ok, why

    s.robot.world.apply = spy
    s.mediator.run()
    assert not set(seen) & s.robot.world.spec.restricted


def test_missing_box_is_refused():
    s = build_session("move box 9 from shelf A to dock 2")
    s.mediator.run()
    assert s.mediator.state == "refused"
    assert s.planner.outcome == ("REFUSE", {"reason": "box 9 is not on shelf a"})


def test_blocked_path_reports_failure():
    s = build_session(TASK, {"extra_walls": [[6, 5], [7, 4]]})
    s.mediator.run()
    assert s.mediator.state == "failed"
    assert s.planner.outcome == ("FAILURE", {"reason": "no safe path"})


def test_run_until_stops_at_state():
    s = build_session(TASK)
    s.mediator.run(until="executing")
    assert s.mediator.state == "executing"
    assert s.robot.world.robot_pos == (0, 0)   # agreed, but has not moved yet
