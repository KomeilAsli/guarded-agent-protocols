from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def protocol_path() -> Path:
    return ROOT / "protocols" / "task_delegation.yaml"


@pytest.fixture
def world_path() -> Path:
    return ROOT / "scenarios" / "world.yaml"
