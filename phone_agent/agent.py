"""Main PhoneAgent class for orchestrating phone automation."""

import json
import traceback
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from phone_agent.actions import ActionHandler
from phone_agent.actions.handler import do, finish, parse_action
from phone_agent.config import get_messages, get_system_prompt
from phone_agent.device_factory import get_device_factory
from phone_agent.model import ModelClient, ModelConfig
from phone_agent.model.client import MessageBuilder
from phone_agent.trace_logger import TraceLogger, get_trace_logger


@dataclass
class AgentConfig:
    """Configuration for the PhoneAgent."""

    max_steps: int = 100
    device_id: str | None = None
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True
    enable_trace_logging: bool = True
    trace_root: str | None = None
    screenshot_size: tuple[int, int] | None = None  # (width, height) or None for original size
    coord_mode: str = "relative"  # "relative" for 0-999 coords, "absolute" for pixel coords

    def __post_init__(self):
        if self.system_prompt is None:
            self.system_prompt = get_system_prompt(self.lang)


@dataclass
class StepResult:
    """Result of a single agent step."""

    success: bool
    finished: bool
    action: dict[str, Any] | None
    thinking: str
    message: str | None = None


class PhoneAgent:
    """
    AI-powered agent for automating Android phone interactions.

    The agent uses a vision-language model to understand screen content
    and decide on actions to complete user tasks.

    Args:
        model_config: Configuration for the AI model.
        agent_config: Configuration for the agent behavior.
        confirmation_callback: Optional callback for sensitive action confirmation.
        takeover_callback: Optional callback for takeover requests.

    Example:
        >>> from phone_agent import PhoneAgent
        >>> from phone_agent.model import ModelConfig
        >>>
        >>> model_config = ModelConfig(base_url="http://localhost:8000/v1")
        >>> agent = PhoneAgent(model_config)
        >>> agent.run("Open WeChat and send a message to John")
    """

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        agent_config: AgentConfig | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        self.model_config = model_config or ModelConfig()
        self.agent_config = agent_config or AgentConfig()

        self.model_client = ModelClient(self.model_config)
        self.action_handler = ActionHandler(
            device_id=self.agent_config.device_id,
            coord_mode=self.agent_config.coord_mode,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )

        self._step_count = 0

    def step(
        self,
        context: list[dict[str, Any]],
        screenshot_base64: str | None = None,
        current_app: str | None = None,
        user_prompt: str | None = None
    ) -> StepResult:
        """
        Execute a single step with external context.

        Args:
            context: External conversation context (will be modified)
            screenshot_base64: Optional screenshot
            current_app: Optional current app name
            user_prompt: Optional user prompt (for first message)

        Returns:
            StepResult with step details
        """
        self._step_count += 1

        # Capture screenshot if not provided
        if screenshot_base64 is None:
            device_factory = get_device_factory()
            screenshot = device_factory.get_screenshot(
                device_id=self.agent_config.device_id,
                target_size=self.agent_config.screenshot_size
            )
            screenshot_base64 = screenshot.base64_data
            screen_width = screenshot.original_width or screenshot.width
            screen_height = screenshot.original_height or screenshot.height
        else:
            # Use provided screenshot, assume dimensions from device
            device_factory = get_device_factory()
            screen_width = 1080  # Default, should be passed in
            screen_height = 1920  # Default, should be passed in

        # Get current app if not provided
        if current_app is None:
            device_factory = get_device_factory()
            current_app = device_factory.get_current_app(self.agent_config.device_id)

        # Build dimension reminder for absolute coordinate mode
        dimension_reminder = ""
        if self.agent_config.coord_mode == "absolute":
            dimension_reminder = f"\nScreenshot dimensions: ({screen_width}x{screen_height}, png)"

        # Build message
        if user_prompt:
            # First message with user prompt
            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = f"{user_prompt}\n\n{screen_info}{dimension_reminder}"
            context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot_base64
                )
            )
        else:
            # Continuation message
            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = f"** Screen Info **\n\n{screen_info}{dimension_reminder}"
            context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot_base64
                )
            )

        # Get model response
        try:
            msgs = get_messages(self.agent_config.lang)
            print("\n" + "=" * 50)
            print(f"💭 {msgs['thinking']}:")
            print("-" * 50)
            response = self.model_client.request(context)
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking="",
                message=f"Model error: {e}",
            )

        # Parse action
        try:
            action = parse_action(response.action)
        except ValueError:
            if self.agent_config.verbose:
                traceback.print_exc()
            action = finish(message=response.action)

        if self.agent_config.verbose:
            print("-" * 50)
            print(f"🎯 {msgs['action']}:")
            print(json.dumps(action, ensure_ascii=False, indent=2))
            print("=" * 50 + "\n")

        # Remove image from context to save space
        context[-1] = MessageBuilder.remove_images_from_message(context[-1])

        # Execute action
        try:
            result = self.action_handler.execute(
                action, screen_width, screen_height,
                screen_width, screen_height  # Assume no resizing for now
            )
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            result = self.action_handler.execute(
                finish(message=str(e)), screen_width, screen_height,
                screen_width, screen_height
            )

        # Add assistant response to context
        context.append(
            MessageBuilder.create_assistant_message(
                f"<think>{response.thinking}</think><answer>{response.action}</answer>"
            )
        )

        # Check if finished
        finished = action.get("_metadata") == "finish" or result.should_finish

        if finished and self.agent_config.verbose:
            msgs = get_messages(self.agent_config.lang)
            print("\n" + "🎉 " + "=" * 48)
            print(
                f"✅ {msgs['task_completed']}: {result.message or action.get('message', msgs['done'])}"
            )
            print("=" * 50 + "\n")

        return StepResult(
            success=result.success,
            finished=finished,
            action=action,
            thinking=response.thinking,
            message=result.message or action.get("message"),
        )

    def reset(self) -> None:
        """Reset the agent state for a new task."""
        self._step_count = 0

    @property
    def step_count(self) -> int:
        """Get the current step count."""
        return self._step_count
