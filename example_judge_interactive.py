"""
Example: Using PhoneAgent with Judge Mode

This example demonstrates how to use the judge feature:
1. enable_judge: Automatically evaluate each step using a judge model and apply refinements
2. full_context: Access the full conversation context with all images

Note: Interactive mode has been removed. Judge now automatically applies
      corrections when it detects incorrect actions.
"""

from phone_agent import PhoneAgent
from phone_agent.model import ModelConfig
from phone_agent.agent import AgentConfig


def example_with_judge(config: dict):
    """Example: Use judge with automatic action refinement"""
    print("\n" + "="*60)
    print("Example 1: Judge mode with auto-refinement")
    print("="*60)

    model_config = ModelConfig(
        base_url=config["base_url"],
        model_name=config["model_name"],
        api_key=config["api_key"],
    )

    agent_config = AgentConfig(
        device_id=config["device_id"],
        enable_judge=True,  # Judge is enabled by default
        judge_api_key=config["judge_api_key"],
        judge_base_url=config["judge_base_url"],
        judge_model_name=config["judge_model_name"],
        judge_history_images_k=config["judge_history_images_k"],
    )

    agent = PhoneAgent(model_config, agent_config)

    # Run the agent
    task = config["task"] or "打开微信"
    print(f"\nTask: {task}")
    result = agent.run(task)
    print(f"\nResult: {result}")

    # Access full context with all images
    full_context = agent.full_context
    print(f"\nFull context has {len(full_context)} messages")
    print(f"Context (no images) has {len(agent.context)} messages")


def example_without_judge(config: dict):
    """Example: Disable judge for faster execution"""
    print("\n" + "="*60)
    print("Example 2: Without judge (faster execution)")
    print("="*60)

    model_config = ModelConfig(
        base_url=config["base_url"],
        model_name=config["model_name"],
        api_key=config["api_key"],
    )

    agent_config = AgentConfig(
        device_id=config["device_id"],
        enable_judge=False,  # Disable judge for faster execution
    )

    agent = PhoneAgent(model_config, agent_config)

    # Run the agent - no judge evaluation, direct execution
    task = config["task"] or "打开微信"
    print(f"\nTask: {task}")
    result = agent.run(task)
    print(f"\nResult: {result}")


def example_step_by_step(config: dict):
    """Example: Use step() method for manual control"""
    print("\n" + "="*60)
    print("Example 3: Step-by-step execution with judge")
    print("="*60)

    model_config = ModelConfig(
        base_url=config["base_url"],
        model_name=config["model_name"],
        api_key=config["api_key"],
    )

    agent_config = AgentConfig(
        device_id=config["device_id"],
        enable_judge=True,  # Judge enabled
        judge_api_key=config["judge_api_key"],
        judge_base_url=config["judge_base_url"],
        judge_model_name=config["judge_model_name"],
        judge_history_images_k=config["judge_history_images_k"],
    )

    agent = PhoneAgent(model_config, agent_config)

    # First step
    task = config["task"] or "打开微信"
    print(f"\nTask: {task}")
    result = agent.step(task=task)
    print(f"\nStep 1 result: finished={result.finished}, message={result.message}")

    if not result.finished:
        # Second step
        result = agent.step()
        print(f"\nStep 2 result: finished={result.finished}, message={result.message}")

    # Access full context
    print(f"\nExecuted {agent.step_count} steps")
    print(f"Full context has {len(agent.full_context)} messages")


if __name__ == "__main__":
    import argparse
    import os
    from phone_agent.device_factory import DeviceType, set_device_type

    parser = argparse.ArgumentParser(
        description="Phone Agent Judge Mode Examples",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with judge (auto-refinement enabled)
    python example_judge_interactive.py 1

    # Run without judge (faster execution)
    python example_judge_interactive.py 2

    # Run step-by-step with judge
    python example_judge_interactive.py 3

    # Run with specific device
    python example_judge_interactive.py 1 --device-id emulator-5554

    # Run with custom task
    python example_judge_interactive.py 1 --task "打开抖音"

    # Run with HarmonyOS device using HDC
    python example_judge_interactive.py 1 --device-type hdc --device-id <device_id>

    # Run with custom judge settings
    python example_judge_interactive.py 1 --task "发送消息" --judge-api-key sk-xxx --judge-model-name gpt-4
        """,
    )

    parser.add_argument(
        "example",
        type=str,
        choices=["1", "2", "3"],
        help="Example number: 1=With Judge, 2=Without Judge, 3=Step-by-step",
    )

    # Device options
    parser.add_argument(
        "--device-id",
        "-d",
        type=str,
        default=os.getenv("PHONE_AGENT_DEVICE_ID"),
        help="Device ID (ADB or HDC)",
    )

    parser.add_argument(
        "--device-type",
        type=str,
        choices=["adb", "hdc"],
        default=os.getenv("PHONE_AGENT_DEVICE_TYPE", "adb"),
        help="Device type: adb for Android, hdc for HarmonyOS (default: adb)",
    )

    # Model options
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.getenv("PHONE_AGENT_BASE_URL", "http://localhost:8000/v1"),
        help="Model API base URL",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("PHONE_AGENT_MODEL", "autoglm-phone-9b"),
        help="Model name",
    )

    parser.add_argument(
        "--apikey",
        type=str,
        default=os.getenv("PHONE_AGENT_API_KEY", "EMPTY"),
        help="API key for model authentication",
    )

    # Judge options
    parser.add_argument(
        "--judge-api-key",
        type=str,
        default=os.getenv("JUDGE_API_KEY", "sk-CJc3Kj313cPY3hsg28zIDGQ8vKkxhtXn"),
        help="API key for judge model",
    )

    parser.add_argument(
        "--judge-base-url",
        type=str,
        default=os.getenv("JUDGE_BASE_URL", "https://api-gateway.glm.ai/v1"),
        help="Base URL for judge model API",
    )

    parser.add_argument(
        "--judge-model-name",
        type=str,
        # default=os.getenv("JUDGE_MODEL_NAME", "claude-sonnet-4-5-20250929"),
        default=os.getenv("JUDGE_MODEL_NAME", "doubao-1.5-thinking-pro-vision-250415"),
        help="Judge model name",
    )

    parser.add_argument(
        "--judge-history-images-k",
        type=int,
        default=int(os.getenv("JUDGE_HISTORY_IMAGES_K", "5")),
        help="Number of historical screenshots for judge (default: 5)",
    )

    parser.add_argument(
        "--task",
        "-t",
        type=str,
        help="Task to execute (optional, uses default task for each example if not provided)",
    )

    args = parser.parse_args()

    # Set device type globally
    device_type = DeviceType.ADB if args.device_type == "adb" else DeviceType.HDC
    set_device_type(device_type)

    # Enable HDC verbose mode if using HDC
    if device_type == DeviceType.HDC:
        from phone_agent.hdc import set_hdc_verbose
        set_hdc_verbose(True)

    # Update global config variables for examples to use
    GLOBAL_CONFIG = {
        "base_url": args.base_url,
        "model_name": args.model,
        "api_key": args.apikey,
        "device_id": args.device_id,
        "judge_api_key": args.judge_api_key,
        "judge_base_url": args.judge_base_url,
        "judge_model_name": args.judge_model_name,
        "judge_history_images_k": args.judge_history_images_k,
        "task": args.task,
    }

    # Print configuration
    print("=" * 60)
    print("Phone Agent Judge Mode Examples")
    print("=" * 60)
    print(f"Device Type: {args.device_type.upper()}")
    print(f"Device ID: {args.device_id or 'auto-detect'}")
    print(f"Model: {args.model}")
    print(f"Base URL: {args.base_url}")
    if args.example in ["1", "3"]:
        print(f"Judge Model: {args.judge_model_name}")
    print("=" * 60)
    print()

    if args.example == "1":
        example_with_judge(GLOBAL_CONFIG)
    elif args.example == "2":
        example_without_judge(GLOBAL_CONFIG)
    elif args.example == "3":
        example_step_by_step(GLOBAL_CONFIG)
