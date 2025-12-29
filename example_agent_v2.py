"""Example usage of PhoneAgentV2 with image scaling and context management."""

from phone_agent.agent_v2 import PhoneAgentV2, AgentConfig
from phone_agent.model import ModelConfig


def example_with_image_scaling():
    """Example: Using image scaling to reduce token usage."""
    print("=== Example 1: Image Scaling ===\n")

    # Configure agent with image scaling
    # Resize screenshots to 720x1280 instead of original 1080x2400
    # This reduces token usage while maintaining usability
    agent_config = AgentConfig(
        screenshot_size=(720, 1280),  # Scaled down from typical 1080x2400
        verbose=True,
        enable_trace_logging=True
    )

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model="glm-4v-flash"
    )

    agent = PhoneAgentV2(
        model_config=model_config,
        agent_config=agent_config
    )

    # Run task - images will be automatically scaled
    result = agent.run("打开微信")
    print(f"\nResult: {result}")


def example_with_external_context():
    """Example: Managing context externally for custom control."""
    print("\n=== Example 2: External Context Management ===\n")

    agent_config = AgentConfig(
        screenshot_size=(720, 1280),
        verbose=True,
        enable_trace_logging=False  # Disable for this example
    )

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model="glm-4v-flash"
    )

    agent = PhoneAgentV2(
        model_config=model_config,
        agent_config=agent_config
    )

    # Create and manage context externally
    context = []

    # Run first task with external context
    result = agent.run_with_context("打开微信", context)
    print(f"\nTask 1 Result: {result}")
    print(f"Context length: {len(context)} messages")

    # Continue with same context for related task
    # This maintains conversation history across multiple tasks
    result = agent.run_with_context("查看最新消息", context)
    print(f"\nTask 2 Result: {result}")
    print(f"Context length: {len(context)} messages")


def example_step_by_step():
    """Example: Step-by-step execution with external context."""
    print("\n=== Example 3: Step-by-Step Execution ===\n")

    agent_config = AgentConfig(
        screenshot_size=(720, 1280),
        verbose=True
    )

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model="glm-4v-flash"
    )

    agent = PhoneAgentV2(
        model_config=model_config,
        agent_config=agent_config
    )

    # Manual step-by-step control
    context = []

    # First step
    print("Step 1:")
    result = agent.step_with_context(context, user_prompt="打开设置")
    print(f"Finished: {result.finished}\n")

    if not result.finished:
        # Second step
        print("Step 2:")
        result = agent.step_with_context(context)
        print(f"Finished: {result.finished}\n")

    # Can inspect or modify context here
    print(f"Final context length: {len(context)} messages")


def example_context_reuse():
    """Example: Reusing context across different agent instances."""
    print("\n=== Example 4: Context Reuse ===\n")

    agent_config = AgentConfig(
        screenshot_size=(720, 1280),
        verbose=True
    )

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model="glm-4v-flash"
    )

    # First agent builds up context
    agent1 = PhoneAgentV2(
        model_config=model_config,
        agent_config=agent_config
    )

    context = []
    agent1.run_with_context("打开微信", context, enable_trace=True)

    # Save context for later use
    saved_context = context.copy()
    print(f"\nSaved context with {len(saved_context)} messages")

    # Later, create new agent and reuse context
    agent2 = PhoneAgentV2(
        model_config=model_config,
        agent_config=agent_config
    )

    # Continue from saved context
    agent2.run_with_context("发送消息给张三", saved_context, enable_trace=True)
    print(f"\nFinal context with {len(saved_context)} messages")


def example_comparison():
    """Example: Comparing with and without image scaling."""
    print("\n=== Example 5: Image Scaling Comparison ===\n")

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model="glm-4v-flash"
    )

    # Without scaling (original size)
    agent_original = PhoneAgentV2(
        model_config=model_config,
        agent_config=AgentConfig(
            screenshot_size=None,  # Original size
            verbose=False
        )
    )

    # With scaling
    agent_scaled = PhoneAgentV2(
        model_config=model_config,
        agent_config=AgentConfig(
            screenshot_size=(720, 1280),  # Scaled
            verbose=False
        )
    )

    # Get screenshots to compare sizes
    screenshot_orig = agent_original._get_screenshot()
    screenshot_scaled = agent_scaled._get_screenshot()

    print(f"Original screenshot: {screenshot_orig.width}x{screenshot_orig.height}")
    print(f"Scaled screenshot: {screenshot_scaled.width}x{screenshot_scaled.height}")
    print(f"Size reduction: {(1 - len(screenshot_scaled.base64_data) / len(screenshot_orig.base64_data)) * 100:.1f}%")


if __name__ == "__main__":
    # Run examples
    # Uncomment the ones you want to test

    # example_with_image_scaling()
    # example_with_external_context()
    # example_step_by_step()
    # example_context_reuse()
    example_comparison()
