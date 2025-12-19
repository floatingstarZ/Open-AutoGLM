#!/usr/bin/env python3
"""
Example: Using Trace Logging

This example demonstrates how to use the trace logging feature
to record agent execution steps and screenshots.
"""

from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig


def main():
    """Run agent with trace logging enabled."""

    # Configure model
    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b",
    )

    # Configure agent with trace logging enabled
    agent_config = AgentConfig(
        max_steps=10,
        verbose=True,
        enable_trace_logging=True,  # Enable trace logging
        trace_root="./traces",  # Directory to save traces (default: ./traces)
    )

    # Create agent
    agent = PhoneAgent(
        model_config=model_config,
        agent_config=agent_config,
    )

    # Run task - trace will be automatically recorded
    result = agent.run("打开微信")
    print(f"\nTask result: {result}")

    # After execution, check the traces directory:
    # traces/
    #   task_<id>/
    #     trace.jsonl          # JSON lines file with execution trace
    #     step_1.png           # Screenshot from step 1
    #     step_2.png           # Screenshot from step 2
    #     ...

    print("\n" + "=" * 60)
    print("Trace files saved in ./traces directory")
    print("=" * 60)


def disable_trace_logging():
    """Example: Disable trace logging."""

    agent_config = AgentConfig(
        enable_trace_logging=False,  # Disable trace logging
    )

    agent = PhoneAgent(agent_config=agent_config)
    result = agent.run("打开微信")
    print(f"Task result (no trace): {result}")


def custom_trace_directory():
    """Example: Use custom trace directory."""

    agent_config = AgentConfig(
        enable_trace_logging=True,
        trace_root="/path/to/custom/traces",  # Custom directory
    )

    agent = PhoneAgent(agent_config=agent_config)
    result = agent.run("打开微信")
    print(f"Task result: {result}")
    print(f"Traces saved in: /path/to/custom/traces")


if __name__ == "__main__":
    print("Running trace logging example...")
    main()
