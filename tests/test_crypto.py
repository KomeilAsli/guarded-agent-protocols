from dataclasses import replace

from gap.crypto import KeyRegistry, new_key, sign, verify
from gap.messages import Message


def _msg() -> Message:
    return Message("planner-1-1", "planner-1", "robot-1", "REQUEST",
                   {"task": "move box 3 from shelf A to dock 2"})


def test_sign_and_verify_roundtrip():
    key = new_key()
    assert verify(sign(_msg(), key), key)


def test_wrong_key_fails():
    assert not verify(sign(_msg(), new_key()), new_key())


def test_tampered_content_fails():
    key = new_key()
    signed = sign(_msg(), key)
    tampered = replace(signed, content={"task": "move box 3 from shelf A to dock 9"})
    assert not verify(tampered, key)


def test_tampered_sender_fails():
    key = new_key()
    signed = sign(_msg(), key)
    assert not verify(replace(signed, sender="robot-1"), key)


def test_canonical_encoding_ignores_key_order():
    a = Message("x", "a", "b", "REFUSE", {"reason": "r", "z": 1})
    b = Message("x", "a", "b", "REFUSE", {"z": 1, "reason": "r"})
    assert a.canonical() == b.canonical()


def test_registry_lookup():
    reg = KeyRegistry()
    key = reg.register("robot-1", "robot")
    assert reg.role_of("robot-1") == "robot"
    assert reg.key_of("robot-1") == key
    assert reg.role_of("ghost") is None
    assert "ghost" not in reg
