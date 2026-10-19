import pytest

from gap.scenarios import load_scenarios, run_scenario

SCENARIOS = load_scenarios()


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_scenario(sc):
    r = run_scenario(sc)
    if sc.get("known_limitation"):
        # A known miss must stay a miss; if it starts passing, update the scenario file.
        assert not r.as_expected, f"{r.name} now passes; remove known_limitation"
    else:
        assert r.as_expected, f"{r.name}: expected {r.expected}, got {r.actual} ({r.reason})"


def test_every_attack_type_is_covered():
    guards = {s["expect"].get("guard") for s in SCENARIOS if s["type"] == "attack"}
    assert {"protocol_order", "action_state", "safe_area", "auth", "injection"} <= guards
