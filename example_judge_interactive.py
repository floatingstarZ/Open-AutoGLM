"""
Example: Using PhoneAgent with Judge and Interactive Mode

This example demonstrates how to use the new judge and interactive features:
1. enable_judge: Automatically evaluate each step using a judge model
2. enable_interactive: Wait for user input after each step
3. full_context: Access the full conversation context with all images
"""

from phone_agent import PhoneAgent
from phone_agent.model import ModelConfig
from phone_agent.agent import AgentConfig


def example_with_judge_only():
    """Example: Enable judge only (no user interaction)"""
    print("\n" + "="*60)
    print("Example 1: Judge-only mode")
    print("="*60)

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b",
    )

    agent_config = AgentConfig(
        enable_judge=True,  # Enable judge
        enable_interactive=False,  # No user interaction
        judge_api_key="sk-CJc3Kj313cPY3hsg28zIDGQ8vKkxhtXn",
        judge_base_url="https://api-gateway.glm.ai/v1",
        judge_model_name="claude-sonnet-4-5-20250929",
        judge_history_images_k=5,  # Use last 5 screenshots for judge
    )

    agent = PhoneAgent(model_config, agent_config)

    # Run the agent
    result = agent.run("打开微信")
    print(f"\nResult: {result}")

    # Access full context with all images
    full_context = agent.full_context
    print(f"\nFull context has {len(full_context)} messages")
    print(f"Context (no images) has {len(agent.context)} messages")


def example_with_interactive_only():
    """Example: Enable interactive mode only (no judge)"""
    print("\n" + "="*60)
    print("Example 2: Interactive-only mode")
    print("="*60)

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b",
    )

    agent_config = AgentConfig(
        enable_judge=False,  # No judge
        enable_interactive=True,  # Enable user interaction
    )

    agent = PhoneAgent(model_config, agent_config)

    # Run the agent - will wait for user input after each step
    result = agent.run("打开微信")
    print(f"\nResult: {result}")


def example_with_both():
    """Example: Enable both judge and interactive mode"""
    print("\n" + "="*60)
    print("Example 3: Judge + Interactive mode")
    print("="*60)

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b",
    )

    agent_config = AgentConfig(
        enable_judge=True,  # Enable judge
        enable_interactive=True,  # Enable user interaction
        judge_api_key="sk-CJc3Kj313cPY3hsg28zIDGQ8vKkxhtXn",
        judge_base_url="https://api-gateway.glm.ai/v1",
        judge_model_name="claude-sonnet-4-5-20250929",
        judge_history_images_k=5,
    )

    agent = PhoneAgent(model_config, agent_config)

    # Run the agent
    # - Judge will evaluate each step
    # - If judge thinks step is incorrect, it will:
    #   1. Show judge evaluation (verdict, score, suggestions)
    #   2. Attempt to refine the action based on suggestions
    #   3. Ask user to choose: original action, refined action, or skip
    # - If judge thinks step is correct, it will:
    #   1. Show positive evaluation
    #   2. Ask user to choose: continue or skip
    result = agent.run("打开微信并发送消息给张三")
    print(f"\nResult: {result}")


def example_step_by_step():
    """Example: Use step() method for manual control"""
    print("\n" + "="*60)
    print("Example 4: Step-by-step execution with judge")
    print("="*60)

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b",
    )

    agent_config = AgentConfig(
        enable_judge=True,
        enable_interactive=True,
    )

    agent = PhoneAgent(model_config, agent_config)

    # First step
    result = agent.step(task="打开微信")
    print(f"\nStep 1 result: finished={result.finished}, message={result.message}")

    if not result.finished:
        # Second step
        result = agent.step()
        print(f"\nStep 2 result: finished={result.finished}, message={result.message}")

    # Access full context
    print(f"\nExecuted {agent.step_count} steps")
    print(f"Full context has {len(agent.full_context)} messages")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python example_judge_interactive.py <example_number>")
        print("\nAvailable examples:")
        print("  1 - Judge-only mode (auto refine if step fails)")
        print("  2 - Interactive-only mode (manual control)")
        print("  3 - Judge + Interactive mode (full features)")
        print("  4 - Step-by-step execution")
        sys.exit(1)

    example_num = sys.argv[1]

    if example_num == "1":
        example_with_judge_only()
    elif example_num == "2":
        example_with_interactive_only()
    elif example_num == "3":
        example_with_both()
    elif example_num == "4":
        example_step_by_step()
    else:
        print(f"Unknown example number: {example_num}")
        sys.exit(1)
