from agents import RunContextWrapper

from persistent_python_agent.app import AgentContext, build_agent, build_instructions


def test_instructions_render_runner_context(tmp_path):
    agent = build_agent(tmp_path)
    context = RunContextWrapper(
        context=AgentContext(
            instruction_data={
                "user_name": "Ada",
                "preferred_units": "metric",
            }
        )
    )

    instructions = build_instructions(context, agent)

    assert "user_name: \"Ada\"" in instructions
    assert "preferred_units: \"metric\"" in instructions
