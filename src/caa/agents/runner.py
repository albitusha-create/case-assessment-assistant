"""Call a Foundry agent and loop over its function calls until it answers.

Each turn: send input to the agent (by name, latest version), run any function
calls it makes, and send their outputs back on the same response chain.
"""

from collections.abc import Callable
from typing import Any

MAX_TURNS = 8


def agent_reference(name: str) -> dict[str, Any]:
    return {"agent_reference": {"name": name, "type": "agent_reference"}}


def run_agent(
    openai: Any,
    agent_name: str,
    user_input: str,
    run_tool: Callable[[str, str], str],
) -> str:
    """Return the agent's final text. `run_tool(name, arguments_json)` runs a tool."""
    response = openai.responses.create(input=user_input, extra_body=agent_reference(agent_name))
    for _ in range(MAX_TURNS):
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            return str(response.output_text)
        outputs = [
            {
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": run_tool(call.name, call.arguments),
            }
            for call in calls
        ]
        response = openai.responses.create(
            input=outputs,
            previous_response_id=response.id,
            extra_body=agent_reference(agent_name),
        )
    raise RuntimeError(f"{agent_name} did not finish within {MAX_TURNS} turns")
