"""Optional LLM planner. Off by default and never needed for tests or evaluation.

Enable it with environment variables:
    GAP_USE_LLM=1
    GAP_LLM_BASE_URL   OpenAI-compatible API root (default: http://localhost:11434/v1, i.e. Ollama)
    GAP_LLM_MODEL      model name (default: llama3.1)
    GAP_LLM_API_KEY    optional bearer token

The LLM only turns a free-form goal into a task line. Its output is sent like
any other message, so it passes through the same guards as the rule-based planner.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Protocol

from .agents import RulePlanner

SYSTEM_PROMPT = (
    "You turn a warehouse goal into exactly one line in this format:\n"
    "move box <number> from shelf <capital letter> to dock <number>\n"
    "Reply with that line only, no other text."
)


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class OpenAICompatibleClient:
    """Minimal chat-completions client using only the standard library."""

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(f"{self.base_url}/chat/completions",
                                     data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.load(resp)
        return str(data["choices"][0]["message"]["content"])


def llm_enabled() -> bool:
    return os.environ.get("GAP_USE_LLM") == "1"


def client_from_env() -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        base_url=os.environ.get("GAP_LLM_BASE_URL", "http://localhost:11434/v1"),
        model=os.environ.get("GAP_LLM_MODEL", "llama3.1"),
        api_key=os.environ.get("GAP_LLM_API_KEY", ""),
    )


class LLMPlanner(RulePlanner):
    """A planner whose task text comes from an LLM instead of being given directly."""

    def __init__(self, agent_id: str, peer_id: str, key: bytes, goal: str, client: LLMClient) -> None:
        super().__init__(agent_id, peer_id, key, task="")
        self.goal = goal
        self.client = client

    def next_task(self) -> str:
        # No cleanup on purpose: whatever the model returns is checked by the guards.
        self.task = self.client.complete(SYSTEM_PROMPT, self.goal).strip()
        return self.task
