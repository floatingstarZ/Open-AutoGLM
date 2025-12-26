"""
Example of using Claude API with Phone Agent

This example demonstrates how to use the Claude model client for phone automation.
"""

import os
from datetime import datetime

from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.config.claude_prompt import get_claude_system_prompt
from phone_agent.config.claude_tools import CLAUDE_TOOLS
from phone_agent.context_manager import ContextManager
from phone_agent.model.client_claude import (
    ClaudeMessageBuilder,
    ClaudeModelClient,
    ClaudeModelConfig,
)
from phone_agent.trace_logger import get_trace_logger


def run_with_claude(task: str, max_steps: int = 100):
    """
    Run a task using Claude API.

    Args:
        task: Task description
        max_steps: Maximum number of steps
    """
    # Initialize Claude model client
    claude_config = ClaudeModelConfig(
        api_key=os.getenv("CLAUDE_API_KEY", "your-api-key-here"),
        base_url="https://api-gateway.glm.ai/v1",
        model_name="claude-sonnet-4-20250514",
        target_screenshot_width=512
    )

    claude_client = ClaudeModelClient(claude_config)

    # Initialize context
    context = []

    # Get Claude system prompt
    system_prompt = get_claude_system_prompt()

    # Initialize context manager
    context_manager = ContextManager(max_images=30)

    # Initialize trace logger
    trace_logger = get_trace_logger("./traces")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    task_id = f"claude_task_{timestamp}"
    trace_logger.start_task(task_id, task)

    print(f"📝 Task ID: {task_id}")
    print(f"📂 Trace directory: {trace_logger.task_dir.absolute()}\n")

    step_count = 0

    try:
        # First step: send task with screenshot
        from phone_agent.device_factory import get_device_factory

        device_factory = get_device_factory()
        screenshot = device_factory.get_screenshot()

        # Resize screenshot
        height, width, resized_base64 = claude_client.resize_screenshot(
            screenshot.base64_data
        )

        # Build first message
        current_app = device_factory.get_current_app()
        text = f"{task}\n\n当前app: {current_app}, Screenshot dimensions: ({width}x{height}, png)"

        first_message = ClaudeMessageBuilder.create_user_message_with_image(
            text=text,
            image_base64=resized_base64,
            image_width=width,
            image_height=height
        )

        context.append(first_message)

        # Call Claude API
        print("💭 Calling Claude API...\n")
        response = claude_client.request(
            messages=context,
            system_prompt=system_prompt,
            tools=CLAUDE_TOOLS
        )

        step_count += 1

        # Add assistant response to context
        context.append(
            ClaudeMessageBuilder.create_assistant_message(response.raw_content)
        )

        # Apply context engineering
        context = context_manager.apply_context_engineering(context)

        # Log step
        trace_logger.log_step(
            screenshot_base64=screenshot.base64_data,
            model_input=context[:-1],
            model_output=response.action,
            thinking=response.thinking,
            action=response.tool_use or {"text": response.action},
            current_app=current_app,
            screen_width=screenshot.width,
            screen_height=screenshot.height,
            raw_model_output=response.raw_content,
            format_model_output=context[-1]
        )

        # Check if we have a tool use
        if response.tool_use:
            print(f"🔧 Tool: {response.tool_use.get('name')}")
            print(f"   Input: {response.tool_use.get('input')}\n")

            # Execute tool (you would implement this based on your action handler)
            # For now, we just print the tool use
            print("✅ Tool executed (implementation needed)\n")

            # In a real scenario, you would:
            # 1. Execute the tool action on the device
            # 2. Get the result screenshot
            # 3. Build tool_result message
            # 4. Continue the loop

        else:
            # Text response
            print(f"📝 Text response: {response.action}\n")

        print(f"✅ Task completed after {step_count} steps")
        print(f"📊 Trace saved: {trace_logger.task_dir.absolute()}")

        trace_logger.reset()

    except Exception as e:
        trace_logger.reset()
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    # Example usage
    task = "打开微信"

    print("=" * 50)
    print("Claude Phone Agent Example")
    print("=" * 50)
    print(f"Task: {task}\n")

    run_with_claude(task)
