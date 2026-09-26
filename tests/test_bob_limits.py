from pathlib import Path

from roadmap_canary.rescue import BobRescueAgent


def test_bob_command_has_cost_turn_and_isolation_limits(tmp_path: Path) -> None:
    agent = BobRescueAgent(
        bob_binary="bob",
        max_turns=5,
        max_cost=0.25,
        disable_mcp=True,
        disable_subagents=True,
    )

    command = agent._build_command(tmp_path, "demo prompt")

    assert command[:2] == ["bob", "run"]
    assert command[command.index("--workspace") + 1] == str(tmp_path)
    assert command[command.index("--max-turns") + 1] == "5"
    assert command[command.index("--max-cost") + 1] == "0.25"
    assert "--disable-mcp" in command
    assert "--disable-subagents" in command
    assert command[-1] == "demo prompt"
