"""Main PhoneAgent class for orchestrating phone automation."""

import json
import traceback
import uuid
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from phone_agent.actions import ActionHandler
from phone_agent.actions.handler import do, finish, parse_action
from phone_agent.config import get_messages, get_system_prompt
from phone_agent.device_factory import get_device_factory
from phone_agent.model import ModelClient, ModelConfig
from phone_agent.model.client import MessageBuilder
from phone_agent.trace_logger import TraceLogger, get_trace_logger

# Import judge functionality
try:
    from judge_tools.judge import judge_model_output
except ImportError:
    judge_model_output = None


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
    # Judge configuration
    enable_judge: bool = False
    judge_api_key: str = "sk-CJc3Kj313cPY3hsg28zIDGQ8vKkxhtXn"
    judge_base_url: str = "https://api-gateway.glm.ai/v1"
    judge_model_name: str = "claude-sonnet-4-5-20250929"
    judge_history_images_k: int = 5
    # Interactive mode
    enable_interactive: bool = False

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
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )

        # Initialize trace logger if enabled
        self.trace_logger: TraceLogger | None = None
        if self.agent_config.enable_trace_logging:
            self.trace_logger = get_trace_logger(self.agent_config.trace_root)

        self._context: list[dict[str, Any]] = []
        self._full_context: list[dict[str, Any]] = []  # Keep all images
        self._step_count = 0
        self._current_task_id: str | None = None

    def run(self, task: str) -> str:
        """
        Run the agent to complete a task.

        Args:
            task: Natural language description of the task.

        Returns:
            Final message from the agent.
        """
        self._context = []
        self._full_context = []
        self._step_count = 0

        # Start trace logging
        if self.trace_logger:
            self._current_task_id = f"task_{uuid.uuid4().hex[:8]}"
            self.trace_logger.start_task(self._current_task_id, task)
            if self.agent_config.verbose:
                print(f"\n📝 Trace logging enabled")
                print(f"   Task ID: {self._current_task_id}")
                print(f"   Trace directory: {self.trace_logger.task_dir.absolute()}\n")

        try:
            # First step with user prompt
            result = self._execute_step(task, is_first=True)

            if result.finished:
                final_message = result.message or "Task completed"
                if self.trace_logger:
                    self.trace_logger.reset()
                return final_message

            # Continue until finished or max steps reached
            while self._step_count < self.agent_config.max_steps:
                result = self._execute_step(is_first=False)

                if result.finished:
                    final_message = result.message or "Task completed"
                    if self.trace_logger:
                        self.trace_logger.reset()
                    return final_message

            # Max steps reached
            if self.trace_logger:
                self.trace_logger.reset()
                if self.agent_config.verbose:
                    print(f"\n📊 Trace saved: {self.trace_logger.task_dir.absolute()}")
            return "Max steps reached"

        except Exception as e:
            # Reset trace logger on error
            if self.trace_logger:
                self.trace_logger.reset()
            raise

    def step(self, task: str | None = None) -> StepResult:
        """
        Execute a single step of the agent.

        Useful for manual control or debugging.

        Args:
            task: Task description (only needed for first step).

        Returns:
            StepResult with step details.
        """
        is_first = len(self._context) == 0

        if is_first and not task:
            raise ValueError("Task is required for the first step")

        return self._execute_step(task, is_first)

    def reset(self) -> None:
        """Reset the agent state for a new task."""
        self._context = []
        self._full_context = []
        self._step_count = 0
        self._current_task_id = None

    def _judge_step(
        self,
        screenshot_base64: str,
        screenshot_path: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Use judge model to evaluate the current step.

        Args:
            screenshot_base64: Base64-encoded screenshot.
            screenshot_path: Path to screenshot file (for trace).

        Returns:
            Judge result dictionary or None if judge is disabled/failed.
        """
        if not self.agent_config.enable_judge:
            return None

        if judge_model_output is None:
            if self.agent_config.verbose:
                print("\n⚠️  Judge功能未启用：judge_tools.judge 模块无法导入")
            return None

        try:
            import base64
            import tempfile
            import os
            from pathlib import Path

            # Prepare format_model_output
            format_model_output = self._full_context[-1] if self._full_context else {}

            # Get trace file path if logging is enabled
            trace_file_path = None
            if self.trace_logger and self._current_task_id:
                trace_file_path = str(self.trace_logger.task_dir / "trace.jsonl")

            # Save screenshot to file if not already saved
            temp_screenshot = None
            if screenshot_path and os.path.exists(screenshot_path):
                actual_screenshot_path = screenshot_path
            else:
                # Create temporary screenshot file
                temp_screenshot = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                screenshot_data = base64.b64decode(screenshot_base64)
                temp_screenshot.write(screenshot_data)
                temp_screenshot.close()
                actual_screenshot_path = temp_screenshot.name

            # Call judge
            if self.agent_config.verbose:
                print("\n" + "=" * 50)
                print("🔍 正在评估当前步骤...")
                print("=" * 50)

            judge_result = judge_model_output(
                model_input=self._full_context[:-1],  # Exclude last assistant message
                screenshot_path=actual_screenshot_path,
                format_model_output=format_model_output,
                trace_file_path=trace_file_path,
                history_images_k=self.agent_config.judge_history_images_k,
                api_key=self.agent_config.judge_api_key,
                base_url=self.agent_config.judge_base_url,
                model_name=self.agent_config.judge_model_name,
            )

            # Clean up temporary file
            if temp_screenshot:
                try:
                    os.unlink(temp_screenshot.name)
                except:
                    pass

            if self.agent_config.verbose:
                print("\n📊 Judge评估结果:")
                print(f"  verdict: {judge_result.get('verdict', 'N/A')}")
                print(f"  model_score: {judge_result.get('model_score', 'N/A')}")
                print(f"  model_confidence: {judge_result.get('model_confidence', 'N/A')}")
                if not judge_result.get('verdict', True):
                    print(f"  repair_suggestions: {judge_result.get('repair_suggestions', 'N/A')}")
                print("=" * 50)

            return judge_result

        except Exception as e:
            if self.agent_config.verbose:
                print(f"\n⚠️  Judge评估失败: {e}")
                traceback.print_exc()
            return None

    def _refine_action(
        self,
        judge_result: dict[str, Any],
        original_response,
        screenshot,
        current_app: str,
    ) -> tuple[dict[str, Any], Any]:
        """
        Refine the action based on judge suggestions.

        Args:
            judge_result: Judge evaluation result.
            original_response: Original model response.
            screenshot: Screenshot object.
            current_app: Current app name.

        Returns:
            Tuple of (refined_action, refined_response).
        """
        try:
            # Build refine prompt with judge suggestions
            repair_suggestions = judge_result.get('repair_suggestions', '')
            correct_action = judge_result.get('correct_action', '')

            refine_prompt = f"""上一步的动作被判定为不合理。

评估结果：
- 评分: {judge_result.get('model_score', 'N/A')}/100
- 置信度: {judge_result.get('model_confidence', 'N/A')}%

修复建议：
{repair_suggestions}

"""
            if correct_action:
                refine_prompt += f"""建议的正确动作：
{correct_action}

"""
            refine_prompt += "请根据上述建议，重新思考并生成正确的动作。"

            # Add refine message to context (temporarily)
            screen_info = MessageBuilder.build_screen_info(current_app)
            refine_text = f"{refine_prompt}\n\n{screen_info}"

            refine_msg = MessageBuilder.create_user_message(
                text=refine_text, image_base64=screenshot.base64_data
            )

            # Create temporary context for refinement
            temp_context = deepcopy(self._full_context)
            temp_context.append(refine_msg)

            if self.agent_config.verbose:
                print("\n" + "=" * 50)
                print("🔄 正在根据Judge建议重新生成动作...")
                print("=" * 50)

            # Get refined response
            refined_response = self.model_client.request(temp_context)

            # Parse refined action
            try:
                refined_action = parse_action(refined_response.action)
            except ValueError:
                refined_action = finish(message=refined_response.action)

            if self.agent_config.verbose:
                msgs = get_messages(self.agent_config.lang)
                print("\n" + "=" * 50)
                print(f"🔄 {msgs['action']} (Refined):")
                print(json.dumps(refined_action, ensure_ascii=False, indent=2))
                print("=" * 50 + "\n")

            return refined_action, refined_response

        except Exception as e:
            if self.agent_config.verbose:
                print(f"\n⚠️  Refine失败: {e}")
                traceback.print_exc()
            # Return original action if refine fails
            original_action = parse_action(original_response.action)
            return original_action, original_response

    def _handle_user_interaction(
        self,
        judge_result: dict[str, Any] | None,
        original_action: dict[str, Any],
        refined_action: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Handle user interaction based on judge result.

        Args:
            judge_result: Judge evaluation result (None if judge disabled).
            original_action: Original action from model.
            refined_action: Refined action (if available).

        Returns:
            Selected action to execute.
        """
        if not self.agent_config.enable_interactive:
            # If interactive mode is disabled, use refined action if available
            if refined_action is not None and judge_result and not judge_result.get('verdict', True):
                return refined_action
            return original_action

        print("\n" + "=" * 50)
        print("⏸️  等待用户输入")
        print("=" * 50)

        # Show options based on judge result
        if judge_result and not judge_result.get('verdict', True):
            # Judge thinks the step is incorrect
            print("\n⚠️  Judge认为当前步骤存在问题")
            print(f"评分: {judge_result.get('model_score', 'N/A')}/100")
            print(f"置信度: {judge_result.get('model_confidence', 'N/A')}%")
            print(f"\n建议: {judge_result.get('repair_suggestions', 'N/A')}")

            print("\n请选择:")
            print("  1. 使用原始动作")
            if refined_action:
                print("  2. 使用修正后的动作")
                print("  3. 跳过此步骤")
                print("  q. 退出任务")
            else:
                print("  2. 跳过此步骤")
                print("  q. 退出任务")
        else:
            # Judge thinks the step is OK (or judge is disabled)
            if judge_result:
                print("\n✅ Judge认为当前步骤合理")
                print(f"评分: {judge_result.get('model_score', 'N/A')}/100")
                print(f"置信度: {judge_result.get('model_confidence', 'N/A')}%")
            print("\n请选择:")
            print("  1. 继续执行")
            print("  2. 跳过此步骤")
            print("  q. 退出任务")

        while True:
            try:
                choice = input("\n请输入选项 (1/2/3/q): ").strip().lower()

                if choice == 'q':
                    print("\n用户选择退出任务")
                    return finish(message="用户中断任务")

                if judge_result and not judge_result.get('verdict', True):
                    if choice == '1':
                        print("\n使用原始动作")
                        return original_action
                    elif choice == '2' and refined_action:
                        print("\n使用修正后的动作")
                        return refined_action
                    elif choice == '2' and not refined_action:
                        print("\n跳过此步骤")
                        return finish(message="用户跳过此步骤")
                    elif choice == '3':
                        print("\n跳过此步骤")
                        return finish(message="用户跳过此步骤")
                    else:
                        print("无效选项，请重新输入")
                        continue
                else:
                    if choice == '1':
                        print("\n继续执行")
                        return original_action
                    elif choice == '2':
                        print("\n跳过此步骤")
                        return finish(message="用户跳过此步骤")
                    else:
                        print("无效选项，请重新输入")
                        continue

            except (KeyboardInterrupt, EOFError):
                print("\n\n用户中断任务")
                return finish(message="用户中断任务")

    def _execute_step(
        self, user_prompt: str | None = None, is_first: bool = False
    ) -> StepResult:
        """Execute a single step of the agent loop."""
        self._step_count += 1

        # Capture current screen state
        device_factory = get_device_factory()
        screenshot = device_factory.get_screenshot(self.agent_config.device_id)
        current_app = device_factory.get_current_app(self.agent_config.device_id)

        # Build messages
        if is_first:
            system_msg = MessageBuilder.create_system_message(self.agent_config.system_prompt)
            self._context.append(system_msg)
            self._full_context.append(deepcopy(system_msg))

            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = f"{user_prompt}\n\n{screen_info}"

            user_msg = MessageBuilder.create_user_message(
                text=text_content, image_base64=screenshot.base64_data
            )
            self._context.append(user_msg)
            self._full_context.append(deepcopy(user_msg))
        else:
            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = f"** Screen Info **\n\n{screen_info}"

            user_msg = MessageBuilder.create_user_message(
                text=text_content, image_base64=screenshot.base64_data
            )
            self._context.append(user_msg)
            self._full_context.append(deepcopy(user_msg))

        # Get model response
        try:
            msgs = get_messages(self.agent_config.lang)
            print("\n" + "=" * 50)
            print(f"💭 {msgs['thinking']}:")
            print("-" * 50)
            response = self.model_client.request(self._context)
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

        # Parse action from response
        try:
            action = parse_action(response.action)
        except ValueError:
            if self.agent_config.verbose:
                traceback.print_exc()
            action = finish(message=response.action)

        if self.agent_config.verbose:
            # Print thinking process
            print("-" * 50)
            print(f"🎯 {msgs['action']}:")
            print(json.dumps(action, ensure_ascii=False, indent=2))
            print("=" * 50 + "\n")

        # Save full context (with images) for judge
        # Remove image from _context to save space, but keep in _full_context
        self._context[-1] = MessageBuilder.remove_images_from_message(self._context[-1])

        # Add assistant response to context
        assistant_msg = MessageBuilder.create_assistant_message(
            f"<think>{response.thinking}</think><answer>{response.action}</answer>"
        )
        self._context.append(assistant_msg)
        self._full_context.append(deepcopy(assistant_msg))
        format_model_output = deepcopy(assistant_msg)

        # Judge and refine if enabled
        judge_result = None
        refined_action = None
        screenshot_path = None

        if self.trace_logger and self._current_task_id:
            screenshot_path = str(self.trace_logger.task_dir / f"step_{self._step_count}.png")

        if self.agent_config.enable_judge or self.agent_config.enable_interactive:
            judge_result = self._judge_step(
                screenshot_base64=screenshot.base64_data,
                screenshot_path=screenshot_path,
            )

            # If judge thinks the step is incorrect, try to refine
            if judge_result and not judge_result.get('verdict', True):
                refined_action, refined_response = self._refine_action(
                    judge_result=judge_result,
                    original_response=response,
                    screenshot=screenshot,
                    current_app=current_app,
                )

        # Handle user interaction if enabled
        if self.agent_config.enable_interactive or (
            self.agent_config.enable_judge and judge_result and not judge_result.get('verdict', True)
        ):
            action = self._handle_user_interaction(
                judge_result=judge_result,
                original_action=action,
                refined_action=refined_action,
            )

        # Execute action
        try:
            result = self.action_handler.execute(
                action, screenshot.width, screenshot.height
            )
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            result = self.action_handler.execute(
                finish(message=str(e)), screenshot.width, screenshot.height
            )

        # Log this step
        if self.trace_logger and self._current_task_id:
            self.trace_logger.log_step(
                screenshot_base64=screenshot.base64_data,
                model_input=self._context[:-1],  # Context before assistant response
                model_output=response.action,
                thinking=response.thinking,
                action=action,
                current_app=current_app,
                screen_width=screenshot.width,
                screen_height=screenshot.height,
                raw_model_output=response.raw_content,
                format_model_output=format_model_output,
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

            # Show trace location if logging is enabled
            if self.trace_logger and self._current_task_id:
                print(f"📊 Trace saved: {self.trace_logger.task_dir.absolute()}")

        return StepResult(
            success=result.success,
            finished=finished,
            action=action,
            thinking=response.thinking,
            message=result.message or action.get("message"),
        )

    @property
    def context(self) -> list[dict[str, Any]]:
        """Get the current conversation context (without images)."""
        return self._context.copy()

    @property
    def full_context(self) -> list[dict[str, Any]]:
        """Get the full conversation context (with all images)."""
        return self._full_context.copy()

    @property
    def step_count(self) -> int:
        """Get the current step count."""
        return self._step_count
