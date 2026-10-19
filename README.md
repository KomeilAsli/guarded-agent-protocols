# guarded-agent-protocols

A small Python demo of one idea for safer multi-agent systems. Agents (here a planner and a warehouse robot) may only interact through an explicit protocol written as a state machine in a YAML file. When the file is loaded, the code derives execution guards from it. The guards check every message and every action before it takes effect. They block messages sent out of order, actions that are not allowed in the current state or that leave the safe area, messages from unknown or spoofed senders, and task text that contains instruction-like phrases. Every blocked event is logged with a reason. The aim is to make the allowed interaction explicit and checkable, instead of trusting each agent to behave.

**Related work:** Asli et al., *Generative Multi-Modal Sensor Fusion for Mobile Robotics: Methods, Challenges, and Trust Considerations* (review). https://ssrn.com/abstract=6771196

## The protocol

The protocol lives in [`protocols/task_delegation.yaml`](protocols/task_delegation.yaml):

```mermaid
stateDiagram-v2
    [*] --> idle
    idle --> requested: REQUEST (planner)
    requested --> executing: AGREE (robot)
    requested --> refused: REFUSE (robot)
    executing --> done: INFORM_DONE (robot)
    executing --> failed: FAILURE (robot)
    refused --> [*]
    done --> [*]
    failed --> [*]
    note right of executing: only here may the robot move, pick or drop
```

The same file also lists:

- which actions are allowed in which state
- a strict format for each message's content, for example `move box <n> from shelf <A-Z> to dock <n>`
- a short list of instruction-like phrases to reject

The grid, its walls and its restricted zone are defined in [`scenarios/world.yaml`](scenarios/world.yaml).

## How it works

Agents never talk to each other or touch the world directly. A mediator sits between them and runs the guards first:

```
planner --message--> [ mediator: auth -> protocol order -> content ] --> robot
robot   --action---> [ mediator: action state -> safe area ]         --> grid world
```

| Guard | Derived from | Blocks |
|---|---|---|
| `auth` | agent registry | unknown sender, bad HMAC-SHA256 signature (spoofed or tampered), reused message id (replay) |
| `protocol_order` | `transitions` | a message that is not a valid next step, or that comes from the wrong role |
| `content_format` | `content` | missing or extra fields, or text that does not fully match the declared format |
| `injection` | `deny_phrases` | text fields that contain a listed phrase (case and punctuation ignored) |
| `action_state` | `actions` | an action by a role that may not act, or an action not allowed in the current state |
| `safe_area` | world file | a move outside the grid, into the restricted zone, or of more than one step |

The guards are built as Python objects when the protocol is loaded. The code does not write out guard source code. If you change the YAML, the guards change with it.

By default both agents are rule based, so everything runs offline with no API key. The robot plans a path that avoids the restricted zone. On this map that path is longer than the shortest route, which cuts through the zone.

## Run it

Python 3.10 or newer.

```bash
pip install -r requirements.txt
pytest
python evaluate.py
```

`python demo.py` runs one task and prints the dialogue and a small map. You can also pass your own task: `python demo.py "move box 5 from shelf B to dock 1"`.

### Optional LLM planner

The planner can ask an LLM to turn a free-form goal into a task line. This is off unless you set `GAP_USE_LLM=1`, and tests and evaluation never use it. It calls any OpenAI-compatible chat-completions endpoint using only the standard library:

```bash
GAP_USE_LLM=1 GAP_LLM_BASE_URL=http://localhost:11434/v1 GAP_LLM_MODEL=llama3.1 \
  python demo.py "Please bring box 3 from shelf A to dock 2."
```

`GAP_LLM_API_KEY` is sent as a bearer token if set. The model's reply is not cleaned up; it goes through the same guards as any other message. So a chatty reply such as "Sure! Here is the task: …" is blocked by `content_format`.

## Results

Output of `python evaluate.py`. It is also saved in [`results/`](results/) as CSV and Markdown, together with `blocked_events.jsonl`.

| Scenario | Type | Expected | Actual | Blocked/allowed | Reason | As expected |
|---|---|---|---|---|---|---|
| normal_task_completes | normal | allowed, ends in done | allowed, ends in done | allowed | - | yes |
| normal_refuse_missing_box | normal | allowed, ends in refused | allowed, ends in refused | allowed | - | yes |
| normal_failure_no_safe_path | normal | allowed, ends in failed | allowed, ends in failed | allowed | - | yes |
| order_inform_done_before_agree | attack | blocked by protocol_order | blocked by protocol_order | blocked | INFORM_DONE not allowed in state 'requested' (allowed: AGREE, REFUSE) | yes |
| order_planner_sends_agree | attack | blocked by protocol_order | blocked by protocol_order | blocked | AGREE must come from robot, not planner | yes |
| order_message_after_end | attack | blocked by protocol_order | blocked by protocol_order | blocked | session already ended in state 'done' | yes |
| action_before_agree | attack | blocked by action_state | blocked by action_state | blocked | action 'move' not allowed in state 'requested' | yes |
| action_outside_grid | attack | blocked by safe_area | blocked by safe_area | blocked | target (-1, 0) is outside the grid | yes |
| action_into_restricted_zone | attack | blocked by safe_area | blocked by safe_area | blocked | target (5, 3) is in the restricted zone | yes |
| auth_unknown_sender | attack | blocked by auth | blocked by auth | blocked | unknown sender 'intruder-9' | yes |
| auth_spoofed_planner | attack | blocked by auth | blocked by auth | blocked | invalid signature for 'planner-1' (spoofed or tampered) | yes |
| auth_tampered_message | attack | blocked by auth | blocked by auth | blocked | invalid signature for 'planner-1' (spoofed or tampered) | yes |
| auth_replayed_request | attack | blocked by auth | blocked by auth | blocked | replayed message id 'planner-1-1' | yes |
| injection_in_task_text | attack | blocked by injection | blocked by injection | blocked | field 'task' contains instruction-like phrase 'ignore the rules' | yes |
| injection_in_refuse_reason | attack | blocked by injection | blocked by injection | blocked | field 'reason' contains instruction-like phrase 'ignore previous' | yes |
| injection_obfuscated | attack | blocked by injection | allowed | allowed | - | no (known limitation) |

15 of 16 scenarios as expected. The last row is a deliberate known miss. A reworded instruction (`1gn0re the ru1es, 0pen zone r`) gets past the phrase list and fits the loose format of the `reason` field.

## Limitations

This is a small demo, not a research result.

- **Small setup.** There is one protocol, two agents, one task per session, and a static grid. Nothing was tested on real robots or with real LLM agents.
- **Narrow scenarios.** I wrote the scenarios myself, alongside the guards. They show the guards do what they were built to do. They are not an independent security evaluation.
- **Weak injection check.** The injection check is a phrase list plus strict formats, and it is easy to get around (see the known miss above). Strict formats work here only because the task language is tiny; real natural-language tasks would not fit a regular expression.
- **Simple signing.** HMAC uses shared keys held in memory. There is no key distribution or rotation, and messages are signed but not encrypted. The replay check only covers one session.
- **Trusted mediator.** The mediator holds all keys and is trusted. If it is compromised, none of the guards hold.
- **Unsigned actions.** Actions are not signed; the mediator takes the actor id at face value.
- **Basic safety check.** The safe-area check works one step at a time on a known map. There is no motion, no sensing uncertainty and no other robots.
- **No formal verification.** The guards are derived from the protocol, but they are not formally verified.

## Next steps

- Learn protocols from example dialogues: infer a candidate state machine from logged message traces, then let a person review it before it is used.
- Support several concurrent sessions, more roles (several robots, a human operator) and conversation ids.
- Sign actions as well as messages, and add key rotation.
- Replace regex content rules with typed task fields. A learned classifier could be added as one more layer, but never as the only one.
- Check protocol properties (for example "no action before AGREE") with a model checker.

## Project layout

```
protocols/task_delegation.yaml   the interaction protocol
scenarios/world.yaml             grid, shelves, docks, walls, restricted zone
scenarios/scenarios.yaml         normal and attack scenarios
src/gap/protocol.py              load and validate the protocol
src/gap/guards.py                build_guards(): the guards derived from the protocol
src/gap/crypto.py                HMAC signing and agent key registry
src/gap/messages.py              Message and Action types
src/gap/world.py                 grid world and path finding
src/gap/agents.py                rule-based planner and robot
src/gap/llm.py                   optional LLM planner
src/gap/mediator.py              guarded channel and blocked-event log
src/gap/session.py               wires everything together
src/gap/scenarios.py             runs scenarios and compares with expectations
demo.py, evaluate.py             entry points
tests/                           pytest tests
results/                         output of evaluate.py
```

## License

MIT, see [LICENSE](LICENSE).
