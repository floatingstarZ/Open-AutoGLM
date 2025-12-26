#!/usr/bin/env python3
"""
Phone Agent CLI - AI-powered phone automation.

Usage:
    python main.py [OPTIONS]

Environment Variables:
    PHONE_AGENT_BASE_URL: Model API base URL (default: http://localhost:8000/v1)
    PHONE_AGENT_MODEL: Model name (default: autoglm-phone-9b)
    PHONE_AGENT_API_KEY: API key for model authentication (default: EMPTY)
    PHONE_AGENT_MAX_STEPS: Maximum steps per task (default: 100)
    PHONE_AGENT_DEVICE_ID: ADB device ID for multi-device setups
"""

import argparse
import os
import shutil
import subprocess
import sys
from urllib.parse import urlparse

from openai import OpenAI

from datetime import datetime

from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.actions.handler import do, finish, parse_action
from phone_agent.config import get_system_prompt
from phone_agent.config.apps import list_supported_apps
from phone_agent.config.apps_harmonyos import list_supported_apps as list_harmonyos_apps
from phone_agent.config.claude_prompt import get_claude_system_prompt
from phone_agent.config.claude_tools import CLAUDE_TOOLS, APP_NAME_TO_PACKAGE
from phone_agent.context_manager import ContextManager
from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.model import ModelConfig
from phone_agent.model.client import MessageBuilder
from phone_agent.model.client_claude import (
    ClaudeMessageBuilder,
    ClaudeModelClient,
    ClaudeModelConfig,
)
from phone_agent.trace_logger import get_trace_logger


def check_system_requirements(device_type: DeviceType = DeviceType.ADB) -> bool:
    """
    Check system requirements before running the agent.

    Checks:
    1. ADB/HDC tools installed
    2. At least one device connected
    3. ADB Keyboard installed on the device (for ADB only)

    Args:
        device_type: Type of device tool (ADB or HDC).

    Returns:
        True if all checks pass, False otherwise.
    """
    print("🔍 Checking system requirements...")
    print("-" * 50)

    all_passed = True

    # Determine tool name and command
    tool_name = "ADB" if device_type == DeviceType.ADB else "HDC"
    tool_cmd = "adb" if device_type == DeviceType.ADB else "hdc"

    # Check 1: Tool installed
    print(f"1. Checking {tool_name} installation...", end=" ")
    if shutil.which(tool_cmd) is None:
        print("❌ FAILED")
        print(f"   Error: {tool_name} is not installed or not in PATH.")
        print(f"   Solution: Install {tool_name}:")
        if device_type == DeviceType.ADB:
            print("     - macOS: brew install android-platform-tools")
            print("     - Linux: sudo apt install android-tools-adb")
            print(
                "     - Windows: Download from https://developer.android.com/studio/releases/platform-tools"
            )
        else:
            print("     - Download from HarmonyOS SDK or https://gitee.com/openharmony/docs")
            print("     - Add to PATH environment variable")
        all_passed = False
    else:
        # Double check by running version command
        try:
            version_cmd = [tool_cmd, "version"] if device_type == DeviceType.ADB else [tool_cmd, "-v"]
            result = subprocess.run(
                version_cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version_line = result.stdout.strip().split("\n")[0]
                print(f"✅ OK ({version_line})")
            else:
                print("❌ FAILED")
                print(f"   Error: {tool_name} command failed to run.")
                all_passed = False
        except FileNotFoundError:
            print("❌ FAILED")
            print(f"   Error: {tool_name} command not found.")
            all_passed = False
        except subprocess.TimeoutExpired:
            print("❌ FAILED")
            print(f"   Error: {tool_name} command timed out.")
            all_passed = False

    # If ADB is not installed, skip remaining checks
    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    # Check 2: Device connected
    print("2. Checking connected devices...", end=" ")
    try:
        if device_type == DeviceType.ADB:
            result = subprocess.run(
                ["adb", "devices"], capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split("\n")
            # Filter out header and empty lines, look for 'device' status
            devices = [line for line in lines[1:] if line.strip() and "\tdevice" in line]
        else:  # HDC
            result = subprocess.run(
                ["hdc", "list", "targets"], capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split("\n")
            devices = [line for line in lines if line.strip()]

        if not devices:
            print("❌ FAILED")
            print("   Error: No devices connected.")
            print("   Solution:")
            if device_type == DeviceType.ADB:
                print("     1. Enable USB debugging on your Android device")
                print("     2. Connect via USB and authorize the connection")
                print("     3. Or connect remotely: python main.py --connect <ip>:<port>")
            else:
                print("     1. Enable USB debugging on your HarmonyOS device")
                print("     2. Connect via USB and authorize the connection")
                print("     3. Or connect remotely: python main.py --device-type hdc --connect <ip>:<port>")
            all_passed = False
        else:
            if device_type == DeviceType.ADB:
                device_ids = [d.split("\t")[0] for d in devices]
            else:
                device_ids = [d.strip() for d in devices]
            print(f"✅ OK ({len(devices)} device(s): {', '.join(device_ids)})")
    except subprocess.TimeoutExpired:
        print("❌ FAILED")
        print(f"   Error: {tool_name} command timed out.")
        all_passed = False
    except Exception as e:
        print("❌ FAILED")
        print(f"   Error: {e}")
        all_passed = False

    # If no device connected, skip ADB Keyboard check
    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    # Check 3: ADB Keyboard installed (only for ADB)
    if device_type == DeviceType.ADB:
        print("3. Checking ADB Keyboard...", end=" ")
        try:
            result = subprocess.run(
                ["adb", "shell", "ime", "list", "-s"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ime_list = result.stdout.strip()

            if "com.android.adbkeyboard/.AdbIME" in ime_list:
                print("✅ OK")
            else:
                print("❌ FAILED")
                print("   Error: ADB Keyboard is not installed on the device.")
                print("   Solution:")
                print("     1. Download ADB Keyboard APK from:")
                print(
                    "        https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk"
                )
                print("     2. Install it on your device: adb install ADBKeyboard.apk")
                print(
                    "     3. Enable it in Settings > System > Languages & Input > Virtual Keyboard"
                )
                all_passed = False
        except subprocess.TimeoutExpired:
            print("❌ FAILED")
            print("   Error: ADB command timed out.")
            all_passed = False
        except Exception as e:
            print("❌ FAILED")
            print(f"   Error: {e}")
            all_passed = False
    else:
        # For HDC, skip keyboard check as it uses different input method
        print("3. Skipping keyboard check for HarmonyOS...", end=" ")
        print("✅ OK (using native input)")

    print("-" * 50)

    if all_passed:
        print("✅ All system checks passed!\n")
    else:
        print("❌ System check failed. Please fix the issues above.")

    return all_passed


def check_model_api(base_url: str, model_name: str, api_key: str = "EMPTY") -> bool:
    """
    Check if the model API is accessible and the specified model exists.

    Checks:
    1. Network connectivity to the API endpoint
    2. Model exists in the available models list

    Args:
        base_url: The API base URL
        model_name: The model name to check
        api_key: The API key for authentication

    Returns:
        True if all checks pass, False otherwise.
    """
    print("🔍 Checking model API...")
    print("-" * 50)

    all_passed = True

    # Check 1: Network connectivity using chat API
    print(f"1. Checking API connectivity ({base_url})...", end=" ")
    try:
        # Create OpenAI client
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=30.0)

        # Use chat completion to test connectivity (more universally supported than /models)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
            temperature=0.0,
            stream=False,
        )

        # Check if we got a valid response
        if response.choices and len(response.choices) > 0:
            print("✅ OK")
        else:
            print("❌ FAILED")
            print("   Error: Received empty response from API")
            all_passed = False

    except Exception as e:
        print("❌ FAILED")
        error_msg = str(e)

        # Provide more specific error messages
        if "Connection refused" in error_msg or "Connection error" in error_msg:
            print(f"   Error: Cannot connect to {base_url}")
            print("   Solution:")
            print("     1. Check if the model server is running")
            print("     2. Verify the base URL is correct")
            print(f"     3. Try: curl {base_url}/chat/completions")
        elif "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            print(f"   Error: Connection to {base_url} timed out")
            print("   Solution:")
            print("     1. Check your network connection")
            print("     2. Verify the server is responding")
        elif (
            "Name or service not known" in error_msg
            or "nodename nor servname" in error_msg
        ):
            print(f"   Error: Cannot resolve hostname")
            print("   Solution:")
            print("     1. Check the URL is correct")
            print("     2. Verify DNS settings")
        else:
            print(f"   Error: {error_msg}")

        all_passed = False

    print("-" * 50)

    if all_passed:
        print("✅ Model API checks passed!\n")
    else:
        print("❌ Model API check failed. Please fix the issues above.")

    return all_passed


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Phone Agent - AI-powered phone automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with default settings
    python main.py

    # Specify model endpoint
    python main.py --base-url http://localhost:8000/v1

    # Use API key for authentication
    python main.py --apikey sk-xxxxx

    # Run with specific device
    python main.py --device-id emulator-5554

    # Connect to remote device
    python main.py --connect 192.168.1.100:5555

    # List connected devices
    python main.py --list-devices

    # Enable TCP/IP on USB device and get connection info
    python main.py --enable-tcpip

    # List supported apps
    python main.py --list-apps
        """,
    )

    # Model options
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.getenv("PHONE_AGENT_BASE_URL", "http://172.18.69.252:2002/v1"),
        help="Model API base URL",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("PHONE_AGENT_MODEL", "glm-4.1v-base"),
        help="Model name",
    )

    parser.add_argument(
        "--apikey",
        type=str,
        default=os.getenv("PHONE_AGENT_API_KEY", "EMPTY"),
        help="API key for model authentication",
    )

    parser.add_argument(
        "--max-steps",
        type=int,
        default=int(os.getenv("PHONE_AGENT_MAX_STEPS", "100")),
        help="Maximum steps per task",
    )

    # Device options
    parser.add_argument(
        "--device-id",
        "-d",
        type=str,
        default=os.getenv("PHONE_AGENT_DEVICE_ID"),
        help="ADB device ID",
    )

    parser.add_argument(
        "--connect",
        "-c",
        type=str,
        metavar="ADDRESS",
        help="Connect to remote device (e.g., 192.168.1.100:5555)",
    )

    parser.add_argument(
        "--disconnect",
        type=str,
        nargs="?",
        const="all",
        metavar="ADDRESS",
        help="Disconnect from remote device (or 'all' to disconnect all)",
    )

    parser.add_argument(
        "--list-devices", action="store_true", help="List connected devices and exit"
    )

    parser.add_argument(
        "--enable-tcpip",
        type=int,
        nargs="?",
        const=5555,
        metavar="PORT",
        help="Enable TCP/IP debugging on USB device (default port: 5555)",
    )

    # Other options
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress verbose output"
    )

    parser.add_argument(
        "--list-apps", action="store_true", help="List supported apps and exit"
    )

    parser.add_argument(
        "--lang",
        type=str,
        choices=["cn", "en"],
        default=os.getenv("PHONE_AGENT_LANG", "cn"),
        help="Language for system prompt (cn or en, default: cn)",
    )

    parser.add_argument(
        "--coord-mode",
        type=str,
        choices=["relative", "absolute"],
        default=os.getenv("PHONE_AGENT_COORD_MODE", "relative"),
        help="Coordinate mode: 'relative' for relative coordinates (0-999), 'absolute' for absolute pixel coordinates (default: relative). Prompt is automatically switched based on this setting.",
    )

    parser.add_argument(
        "--screenshot-size",
        type=str,
        default=os.getenv("PHONE_AGENT_SCREENSHOT_SIZE"),
        help="Target screenshot size in format WIDTHxHEIGHT (e.g., '720x1280'). If not specified, original image size is used. Screenshots will be resized to this size before being sent to the model.",
    )

    parser.add_argument(
        "--device-type",
        type=str,
        choices=["adb", "hdc"],
        default=os.getenv("PHONE_AGENT_DEVICE_TYPE", "adb"),
        help="Device type: adb for Android, hdc for HarmonyOS (default: adb)",
    )

    parser.add_argument(
        "--disable-trace",
        action="store_true",
        help="Disable trace logging (enabled by default)",
    )

    parser.add_argument(
        "--trace-root",
        type=str,
        default=os.getenv("PHONE_AGENT_TRACE_ROOT", "./traces"),
        help="Directory to save trace logs (default: ./traces)",
    )

    # Claude-specific options
    parser.add_argument(
        "--use-claude",
        action="store_true",
        help="Use Claude API instead of OpenAI-compatible API",
    )

    parser.add_argument(
        "--claude-api-key",
        type=str,
        default=os.getenv("CLAUDE_API_KEY", "EMPTY"),
        help="API key for Claude API (default: from CLAUDE_API_KEY env var)",
    )

    parser.add_argument(
        "--claude-base-url",
        type=str,
        default=os.getenv("CLAUDE_BASE_URL", "https://api-gateway.glm.ai/v1"),
        help="Base URL for Claude API (default: https://api-gateway.glm.ai/v1)",
    )

    parser.add_argument(
        "--claude-model",
        type=str,
        default=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
        help="Claude model name (default: claude-sonnet-4-20250514)",
    )

    parser.add_argument(
        "--claude-screenshot-width",
        type=int,
        default=512,
        help="Target screenshot width for Claude (default: 512)",
    )

    parser.add_argument(
        "task",
        nargs="?",
        type=str,
        help="Task to execute (interactive mode if not provided)",
    )

    return parser.parse_args()


def run_task_with_claude(
    claude_client: ClaudeModelClient,
    agent_config: AgentConfig,
    task: str,
    device_id: str | None = None
) -> str:
    """
    Run a task using Claude API.

    Args:
        claude_client: ClaudeModelClient instance
        agent_config: Agent configuration
        task: Task description
        device_id: Device ID for device operations

    Returns:
        Final result message
    """
    # Initialize context
    context = []

    # Initialize context manager
    context_manager = ContextManager(max_images=30)

    # Get Claude system prompt
    system_prompt = get_claude_system_prompt()

    # Initialize trace logger if enabled
    trace_logger = None
    task_id = None
    if agent_config.enable_trace_logging:
        trace_logger = get_trace_logger(agent_config.trace_root)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        task_id = f"task_{timestamp}"
        trace_logger.start_task(task_id, task)
        if agent_config.verbose:
            print(f"\n📝 Trace logging enabled")
            print(f"   Task ID: {task_id}")
            print(f"   Trace directory: {trace_logger.task_dir.absolute()}\n")

    # Get device factory
    device_factory = get_device_factory()

    # Import action handler
    from phone_agent.actions import ActionHandler
    action_handler = ActionHandler(
        device_id=device_id,
        coord_mode=agent_config.coord_mode
    )

    step_count = 0
    max_steps = agent_config.max_steps

    try:
        # First step: send task with screenshot
        screenshot = device_factory.get_screenshot(device_id=device_id)
        current_app = device_factory.get_current_app(device_id)

        # Resize screenshot
        height, width, resized_base64 = claude_client.resize_screenshot(
            screenshot.base64_data
        )

        # Build first message
        text = f"{task}\n\n<system-reminder>当前app: {current_app}, Screenshot dimensions: ({width}x{height}, png)</system-reminder>"

        first_message = ClaudeMessageBuilder.create_user_message_with_image(
            text=text,
            image_base64=resized_base64,
            image_width=width,
            image_height=height
        )

        context.append(first_message)

        # Main loop
        while step_count < max_steps:
            step_count += 1

            # Call Claude API
            if agent_config.verbose:
                print("\n" + "=" * 50)
                print("💭 Calling Claude API...")
                print("-" * 50)

            response = claude_client.request(
                messages=context,
                system_prompt=system_prompt,
                tools=CLAUDE_TOOLS
            )

            # Add assistant response to context
            context.append(
                ClaudeMessageBuilder.create_assistant_message(response.raw_content)
            )

            # Apply context engineering
            context = context_manager.apply_context_engineering(context)

            # Log step
            if trace_logger and task_id:
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
                tool_name = response.tool_use.get("name")
                tool_input = response.tool_use.get("input", {})

                if agent_config.verbose:
                    print(f"\n🔧 Tool: {tool_name}")
                    print(f"   Input: {tool_input}\n")

                # Convert Launch app_name to package_name
                if tool_name == "Launch":
                    app_name = tool_input.get("app_name")
                    package_name = APP_NAME_TO_PACKAGE.get(app_name, "")
                    if not package_name:
                        return f"Error: Unknown app '{app_name}'"
                    tool_input["package_name"] = package_name
                    del tool_input["app_name"]

                # Build action dict for ActionHandler
                action_dict = do(action=tool_name, **tool_input)

                # Execute action
                result = action_handler.execute(
                    action_dict,
                    screenshot.original_width or screenshot.width,
                    screenshot.original_height or screenshot.height,
                    screenshot.width,
                    screenshot.height
                )

                # Check if finished
                if result.should_finish or action_dict.get("_metadata") == "finish":
                    if trace_logger:
                        trace_logger.reset()
                        if agent_config.verbose:
                            print(f"\n📊 Trace saved: {trace_logger.task_dir.absolute()}")
                    return result.message or "Task completed"

                # Get new screenshot for next iteration
                screenshot = device_factory.get_screenshot(device_id=device_id)
                current_app = device_factory.get_current_app(device_id)

                # Resize screenshot
                height, width, resized_base64 = claude_client.resize_screenshot(
                    screenshot.base64_data
                )

                # Build tool result message
                result_text = result.message or f"{tool_name} executed successfully"
                tool_result_msg = ClaudeMessageBuilder.create_tool_result(
                    tool_use_id=response.tool_use.get("id"),
                    result_text=f"{result_text}\n\n<system-reminder>当前app: {current_app}, Screenshot dimensions: ({width}x{height}, png)</system-reminder>",
                    image_base64=resized_base64,
                    image_width=width,
                    image_height=height
                )

                context.append(tool_result_msg)

                # Remove images from context to save space
                context = ClaudeMessageBuilder.remove_images_from_message(context[-2])

            else:
                # Text response - task finished or needs clarification
                if agent_config.verbose:
                    print(f"\n📝 Text response: {response.action}\n")

                if trace_logger:
                    trace_logger.reset()
                    if agent_config.verbose:
                        print(f"\n📊 Trace saved: {trace_logger.task_dir.absolute()}")

                return response.action

        # Max steps reached
        if trace_logger:
            trace_logger.reset()
            if agent_config.verbose:
                print(f"\n📊 Trace saved: {trace_logger.task_dir.absolute()}")
        return "Max steps reached"

    except Exception as e:
        if trace_logger:
            trace_logger.reset()
        raise


def run_task(agent: PhoneAgent, agent_config: AgentConfig, task: str) -> str:
    """
    Run a task using the agent with context management and trace logging.

    Args:
        agent: PhoneAgent instance
        agent_config: Agent configuration
        task: Task description

    Returns:
        Final result message
    """
    # Initialize context
    context = []

    # Add system message for first call
    if agent_config.system_prompt:
        context.append(MessageBuilder.create_system_message(agent_config.system_prompt))

    # Initialize context manager
    context_manager = ContextManager(max_images=30)

    # Initialize trace logger if enabled
    trace_logger = None
    task_id = None
    if agent_config.enable_trace_logging:
        trace_logger = get_trace_logger(agent_config.trace_root)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        task_id = f"task_{timestamp}"
        trace_logger.start_task(task_id, task)
        if agent_config.verbose:
            print(f"\n📝 Trace logging enabled")
            print(f"   Task ID: {task_id}")
            print(f"   Trace directory: {trace_logger.task_dir.absolute()}\n")

    step_count = 0

    try:
        # First step with user prompt
        result = agent.step(
            context=context,
            user_prompt=task
        )
        step_count += 1

        # Log first step if trace logging enabled
        if trace_logger and task_id:
            trace_logger.log_step(
                screenshot_base64=None,  # Agent captures internally
                model_input=context[:-1],
                model_output=result.action,
                thinking=result.thinking,
                action=result.action,
                current_app="",
                screen_width=1080,
                screen_height=1920,
                raw_model_output=result.action,
                format_model_output=context[-1] if context else {}
            )

        # Apply context engineering
        context = context_manager.apply_context_engineering(context)

        if result.finished:
            if trace_logger:
                trace_logger.reset()
            return result.message or "Task completed"

        # Continue until finished or max steps
        while step_count < agent_config.max_steps:
            result = agent.step(context=context)
            step_count += 1

            # Log step
            if trace_logger and task_id:
                trace_logger.log_step(
                    screenshot_base64=None,
                    model_input=context[:-1],
                    model_output=result.action,
                    thinking=result.thinking,
                    action=result.action,
                    current_app="",
                    screen_width=1080,
                    screen_height=1920,
                    raw_model_output=result.action,
                    format_model_output=context[-1] if context else {}
                )

            # Apply context engineering
            context = context_manager.apply_context_engineering(context)

            if result.finished:
                if trace_logger:
                    trace_logger.reset()
                    if agent_config.verbose:
                        print(f"\n📊 Trace saved: {trace_logger.task_dir.absolute()}")
                return result.message or "Task completed"

        # Max steps reached
        if trace_logger:
            trace_logger.reset()
            if agent_config.verbose:
                print(f"\n📊 Trace saved: {trace_logger.task_dir.absolute()}")
        return "Max steps reached"

    except Exception as e:
        if trace_logger:
            trace_logger.reset()
        raise


def handle_device_commands(args) -> bool:
    """
    Handle device-related commands.

    Returns:
        True if a device command was handled (should exit), False otherwise.
    """
    device_factory = get_device_factory()
    ConnectionClass = device_factory.get_connection_class()
    conn = ConnectionClass()

    # Handle --list-devices
    if args.list_devices:
        devices = device_factory.list_devices()
        if not devices:
            print("No devices connected.")
        else:
            print("Connected devices:")
            print("-" * 60)
            for device in devices:
                status_icon = "✓" if device.status == "device" else "✗"
                conn_type = device.connection_type.value
                model_info = f" ({device.model})" if device.model else ""
                print(
                    f"  {status_icon} {device.device_id:<30} [{conn_type}]{model_info}"
                )
        return True

    # Handle --connect
    if args.connect:
        print(f"Connecting to {args.connect}...")
        success, message = conn.connect(args.connect)
        print(f"{'✓' if success else '✗'} {message}")
        if success:
            # Set as default device
            args.device_id = args.connect
        return not success  # Continue if connection succeeded

    # Handle --disconnect
    if args.disconnect:
        if args.disconnect == "all":
            print("Disconnecting all remote devices...")
            success, message = conn.disconnect()
        else:
            print(f"Disconnecting from {args.disconnect}...")
            success, message = conn.disconnect(args.disconnect)
        print(f"{'✓' if success else '✗'} {message}")
        return True

    # Handle --enable-tcpip
    if args.enable_tcpip:
        port = args.enable_tcpip
        print(f"Enabling TCP/IP debugging on port {port}...")

        success, message = conn.enable_tcpip(port, args.device_id)
        print(f"{'✓' if success else '✗'} {message}")

        if success:
            # Try to get device IP
            ip = conn.get_device_ip(args.device_id)
            if ip:
                print(f"\nYou can now connect remotely using:")
                print(f"  python main.py --connect {ip}:{port}")
                print(f"\nOr via ADB directly:")
                print(f"  adb connect {ip}:{port}")
            else:
                print("\nCould not determine device IP. Check device WiFi settings.")
        return True

    return False


def main():
    """Main entry point."""
    args = parse_args()

    # Set device type globally based on args
    device_type = DeviceType.ADB if args.device_type == "adb" else DeviceType.HDC
    set_device_type(device_type)

    # Enable HDC verbose mode if using HDC
    if device_type == DeviceType.HDC:
        from phone_agent.hdc import set_hdc_verbose
        set_hdc_verbose(True)

    # Handle --list-apps (no system check needed)
    if args.list_apps:
        if device_type == DeviceType.HDC:
            print("Supported HarmonyOS apps:")
            apps = list_harmonyos_apps()
        else:
            print("Supported Android apps:")
            apps = list_supported_apps()

        for app in apps:
            print(f"  - {app}")
        return

    # Handle device commands (these may need partial system checks)
    if handle_device_commands(args):
        return

    # Run system requirements check before proceeding
    if not check_system_requirements(device_type):
        sys.exit(1)

    # Check model API connectivity (skip for Claude mode)
    if not args.use_claude:
        if not check_model_api(args.base_url, args.model, args.apikey):
            sys.exit(1)

    # Create configurations based on model type
    if args.use_claude:
        # Claude mode
        print("\n🤖 Using Claude API")
        claude_config = ClaudeModelConfig(
            api_key=args.claude_api_key,
            base_url=args.claude_base_url,
            model_name=args.claude_model,
            target_screenshot_width=args.claude_screenshot_width,
            lang=args.lang
        )
        claude_client = ClaudeModelClient(claude_config)
        system_prompt = get_claude_system_prompt()
    else:
        # OpenAI-compatible mode
        print("\n🤖 Using OpenAI-compatible API")
        model_config = ModelConfig(
            base_url=args.base_url,
            model_name=args.model,
            api_key=args.apikey,
            lang=args.lang,
        )
        # 根据参数获取对应的 system prompt
        system_prompt = get_system_prompt(lang=args.lang, prompt_type=args.coord_mode)

    # Parse screenshot size if provided (not used in Claude mode)
    screenshot_size = None
    if args.screenshot_size and not args.use_claude:
        try:
            width, height = args.screenshot_size.split('x')
            screenshot_size = (int(width), int(height))
        except ValueError:
            print(f"Warning: Invalid screenshot size format '{args.screenshot_size}'. Expected format: WIDTHxHEIGHT (e.g., '720x1280'). Using original size.")

    agent_config = AgentConfig(
        max_steps=args.max_steps,
        device_id=args.device_id,
        verbose=not args.quiet,
        lang=args.lang,
        system_prompt=system_prompt,
        enable_trace_logging=not args.disable_trace,
        trace_root=args.trace_root,
        screenshot_size=screenshot_size,
        coord_mode=args.coord_mode,
    )

    # Create agent (only for OpenAI-compatible mode)
    if not args.use_claude:
        agent = PhoneAgent(
            model_config=model_config,
            agent_config=agent_config,
        )

    # Print header and all configuration parameters
    print("=" * 50)
    print("Phone Agent - AI-powered phone automation")
    print("=" * 50)
    print("\n📋 Configuration Parameters:")
    print("-" * 50)

    # Model Configuration
    print("Model Configuration:")
    if args.use_claude:
        print(f"  Mode: Claude API")
        print(f"  Base URL: {claude_config.base_url}")
        print(f"  Model Name: {claude_config.model_name}")
        print(f"  API Key: {claude_config.api_key[:20]}...")
        print(f"  Max Tokens: {claude_config.max_tokens}")
        print(f"  Thinking Budget: {claude_config.thinking_budget_tokens}")
        print(f"  Screenshot Width: {claude_config.target_screenshot_width}")
        print(f"  Language: {claude_config.lang}")
    else:
        print(f"  Mode: OpenAI-compatible API")
        print(f"  Base URL: {model_config.base_url}")
        print(f"  Model Name: {model_config.model_name}")
        print(f"  API Key: {model_config.api_key}")
        print(f"  Max Tokens: {model_config.max_tokens}")
        print(f"  Temperature: {model_config.temperature}")
        print(f"  Top P: {model_config.top_p}")
        print(f"  Frequency Penalty: {model_config.frequency_penalty}")
        print(f"  Language: {model_config.lang}")

    # Agent Configuration
    print("\nAgent Configuration:")
    print(f"  Max Steps: {agent_config.max_steps}")
    print(f"  Language: {agent_config.lang}")
    print(f"  Coordinate Mode: {args.coord_mode}")
    print(f"  Screenshot Size: {f'{screenshot_size[0]}x{screenshot_size[1]}' if screenshot_size else 'Original'}")
    print(f"  Verbose: {agent_config.verbose}")
    print(f"  Enable Trace Logging: {agent_config.enable_trace_logging}")
    print(f"  Trace Root: {agent_config.trace_root}")

    # Device Configuration
    print("\nDevice Configuration:")
    print(f"  Device Type: {args.device_type.upper()}")
    device_factory = get_device_factory()
    devices = device_factory.list_devices()
    if agent_config.device_id:
        print(f"  Device ID: {agent_config.device_id}")
    elif devices:
        print(f"  Device ID: {devices[0].device_id} (auto-detected)")
    else:
        print(f"  Device ID: None")

    print("=" * 50)

    # Run with provided task or enter interactive mode
    if args.task:
        print(f"\nTask: {args.task}\n")
        if args.use_claude:
            result = run_task_with_claude(claude_client, agent_config, args.task, args.device_id)
        else:
            result = run_task(agent, agent_config, args.task)
        print(f"\nResult: {result}")
    else:
        # Interactive mode
        print("\nEntering interactive mode. Type 'quit' to exit.\n")

        while True:
            try:
                task = input("Enter your task: ").strip()

                if task.lower() in ("quit", "exit", "q"):
                    print("Goodbye!")
                    break

                if not task:
                    continue

                print()
                if args.use_claude:
                    result = run_task_with_claude(claude_client, agent_config, task, args.device_id)
                else:
                    result = run_task(agent, agent_config, task)
                    agent.reset()
                print(f"\nResult: {result}\n")

            except KeyboardInterrupt:
                print("\n\nInterrupted. Goodbye!")
                break
            except Exception as e:
                print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
