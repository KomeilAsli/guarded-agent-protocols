import copy

import pytest
import yaml

from gap.protocol import ProtocolError, load_protocol, parse_protocol


@pytest.fixture
def raw(protocol_path) -> dict:
    return yaml.safe_load(protocol_path.read_text())


def test_loads_example_protocol(protocol_path):
    p = load_protocol(protocol_path)
    assert p.initial == "idle"
    assert p.final == {"done", "failed", "refused"}
    assert p.states == {"idle", "requested", "executing", "done", "failed", "refused"}
    assert p.messages == {"REQUEST", "AGREE", "REFUSE", "INFORM_DONE", "FAILURE"}
    assert p.allowed_actions["executing"] == {"move", "pick", "drop"}


def test_rejects_unknown_sender_role(raw):
    bad = copy.deepcopy(raw)
    bad["transitions"][0]["sender"] = "intruder"
    with pytest.raises(ProtocolError, match="unknown sender"):
        parse_protocol(bad)


def test_rejects_nondeterministic_protocol(raw):
    bad = copy.deepcopy(raw)
    bad["transitions"].append({"from": "idle", "message": "REQUEST", "sender": "planner", "to": "done"})
    with pytest.raises(ProtocolError, match="duplicate"):
        parse_protocol(bad)


def test_rejects_transition_out_of_final_state(raw):
    bad = copy.deepcopy(raw)
    bad["transitions"].append({"from": "done", "message": "REQUEST", "sender": "planner", "to": "requested"})
    with pytest.raises(ProtocolError, match="final state"):
        parse_protocol(bad)


def test_rejects_unreachable_state(raw):
    bad = copy.deepcopy(raw)
    bad["final"].append("orphan")
    with pytest.raises(ProtocolError, match="unreachable"):
        parse_protocol(bad)


def test_rejects_bad_regex(raw):
    bad = copy.deepcopy(raw)
    bad["content"]["REQUEST"]["task"] = "^(unclosed"
    with pytest.raises(ProtocolError, match="bad regex"):
        parse_protocol(bad)
