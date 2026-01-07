#!/usr/bin/env python3
"""
Service-based Phone Agent CLI.

This version uses AgentService for inference while maintaining
full control over the execution loop and message history.

Key differences from main.py:
- Manages messages list externally
- Handles screenshot capture and base64 conversion
- Controls execution loop with service calls
- Supports K-image filtering for token optimization
"""

import argparse
import base64
import io
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image
from judge_tools import judge
from phone_agent.actions import ActionHandler
from phone_agent.agent_service import AgentService, InferenceConfig
from phone_agent.config import get_messages, get_system_prompt
from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.model import ModelConfig
from phone_agent.model.client import MessageBuilder

from judge_tools.judge_service import judge_model_output

# Import utility functions from original main.py
from main import (
    check_model_api,
    check_system_requirements,
    handle_device_commands,
    parse_args as original_parse_args,
)


class SimpleTraceLogger:
    """简单的实时日志记录器"""

    def __init__(self, trace_root="./traces", 
    task_id=None, task_dir=None, trace_file=None, step_count=0):
        self.trace_root = Path(trace_root)
        self.task_id = task_id
        self.task_dir = Path(task_dir)
        self.trace_file = Path(trace_file)
        self.step_count = step_count

    def start_task(self, task, k_images, max_steps):
        """开始任务，创建目录和文件"""
        if self.task_id is None:
            self.task_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.task_dir is None:
            self.task_dir = self.trace_root / self.task_id
            self.task_dir.mkdir(parents=True, exist_ok=True)
        if self.trace_file is None:
            self.trace_file = self.task_dir / "trace.jsonl"
        if self.step_count is None:
            self.step_count = 0

        # 写入第1行：task_start
        self._append(
            {
                "type": "task_start",
                "task_id": self.task_id,
                "task": task,
                "trace_dir": str(self.task_dir.absolute()),
                "k_images": k_images,
                "max_steps": max_steps,
                "timestamp": datetime.now().isoformat(),
            }
        )

        return self.task_dir

    def log_system(self, system_prompt, model_type=None):
        """记录 system message（第2行）"""
        self._append({"type": "system", "model_type": model_type, "content": system_prompt})

    def log_user(self, text, base64_image):
        """记录 user message，保存截图"""
        self.step_count += 1

        # 保存截图
        img_filename = f"step_{self.step_count}.png"
        self._save_image(base64_image, img_filename)

        # 写入 user message（图像用路径替换）
        self._append(
            {
                "type": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image", "path": img_filename},
                ],
            }
        )
    def log_debug_info(self, debug_info):
        """记录 external message"""
        self._append(
            {
                "type": "debug_info",
                "debug_info": debug_info,
            }
        )
    def save_debug(self, filename: str, data: dict[str, Any]):
        """Save debug data to file"""
        self.debug_dir = self.task_dir / "debug"
        self.debug_dir.mkdir(parents=True, exist_ok=True)

        debug_file = self.debug_dir / filename
        with open(debug_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"🐛 Debug saved to: {debug_file.absolute()}")

    def log_assistant(self, assistant_content):
        """记录 assistant message"""
        self._append(
            {
                "type": "assistant",
                "content": f"{assistant_content}",
            }
        )

    def log_judge_result(self, judge_result):
        """记录 judge 结果"""
        self._append(
            {
                "type": "judge_result",
                "step": self.step_count,
                "judge_result": judge_result,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def end_task(self, status, message, total_steps):
        """结束任务（最后一行）"""
        self._append(
            {
                "type": "task_end",
                "status": status,
                "message": message,
                "total_steps": total_steps,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _append(self, data):
        """追加一行到 trace.jsonl"""
        with open(self.trace_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

    def _save_image(self, base64_str, filename):
        """保存 base64 图像为 PNG 文件"""
        # 移除 data:image/png;base64, 前缀
        if "base64," in base64_str:
            base64_str = base64_str.split("base64,")[1]

        img_data = base64.b64decode(base64_str)
        img_path = self.task_dir / filename

        with open(img_path, "wb") as f:
            f.write(img_data)


def screenshot_to_base64(device_id: str | None = None) -> tuple[str, int, int]:
    """
    Capture screenshot and convert to base64.

    Args:
        device_id: Optional device ID for multi-device setups

    Returns:
        Tuple of (base64_string, width, height)
    """
    device_factory = get_device_factory()
    screenshot = device_factory.get_screenshot(device_id)

    return (
        screenshot.base64_data,
        screenshot.width,
        screenshot.height,
    )


def load_image_as_base64(
    image_path: Path, 
    target_width: int | None = None
) -> tuple[str | None, int | None, int | None]:
    """
    从文件路径加载图片并转换为 base64 字符串
    默认缩放：短边缩放到 target_width，保持宽高比

    Args:
        image_path: 图片文件路径
        target_width: 短边的目标宽度（None = 不缩放）

    Returns:
        (Base64 编码的图片字符串, 缩放后的宽度, 缩放后的高度)，失败返回 (None, None, None)
    """
    try:
        if not image_path.exists():
            print(f"[WARNING] Image file not found: {image_path}")
            return None, None, None

        with Image.open(image_path) as img:
            # 转换为 RGB 模式（如果需要）
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # 获取原始尺寸
            width, height = img.size

            # 缩放图片：短边缩放到 target_width，保持宽高比
            if target_width is not None and target_width > 0:
                if width < height:
                    new_width = target_width
                    new_height = int(height * (target_width / width))
                else:
                    new_height = target_width
                    new_width = int(width * (target_width / height))
            else:
                new_width, new_height = width, height
            
            img = img.resize((new_width, new_height), Image.LANCZOS)

            # 转换为 base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            b64_code = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return f"data:image/png;base64,{b64_code}", new_width, new_height
    except Exception as e:
        print(f"[ERROR] Failed to load image {image_path}: {e}")
        return None, None, None


def read_trace_and_organize_messages(
    trace_file: Path, 
    task_dir: Path, 
    k_images: int,
    target_width: int | None = None
) -> list[dict[str, Any]]:
    """
    读取 trace.jsonl 文件，组织消息（只有最后 K 对加载图片，其余不加载图片）

    Args:
        trace_file: trace.jsonl 文件路径
        task_dir: 任务目录（用于解析图片路径）
        k_images: 只有最后 K 对加载图片（超参数）
        target_width: 短边的目标宽度，保持宽高比（可选）

    Returns:
        组织好的消息列表，格式符合 judge_service 的要求
    """
    if not trace_file.exists():
        print(f"[WARNING] Trace file not found: {trace_file}")
        return []

    messages = []
    user_assistant_pairs = []  # 存储 (user, assistant) 对

    # 读取所有行
    with open(trace_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                msg_type = data.get("type")

                if msg_type == "user":
                    user_assistant_pairs.append({"user": data, "assistant": None})
                elif msg_type == "assistant":
                    if user_assistant_pairs:
                        user_assistant_pairs[-1]["assistant"] = data
                    else:
                        # 如果没有对应的 user，创建一个占位符
                        user_assistant_pairs.append({"user": None, "assistant": data})
            except json.JSONDecodeError as e:
                print(f"[WARNING] Failed to parse line: {e}")
                continue

    # 计算哪些对需要加载图片（最后 k_images 对）
    total_pairs = len(user_assistant_pairs)
    image_start_index = max(0, total_pairs - k_images) if k_images > 0 else total_pairs

    # 转换为 judge_service 需要的格式
    for idx, pair in enumerate(user_assistant_pairs):
        user_data = pair.get("user")
        assistant_data = pair.get("assistant")
        should_load_image = idx >= image_start_index

        # 处理 user 消息
        if user_data:
            user_content = user_data.get("content", [])
            if isinstance(user_content, list):
                # 构建新的 user 消息
                new_user_content = []
                for item in user_content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            new_user_content.append({"type": "text", "text": item.get("text", "")})
                        elif item.get("type") == "image":
                            # 只有最后 k_images 对加载图片
                            if should_load_image:
                                img_path = item.get("path")
                                if img_path:
                                    full_img_path = task_dir / img_path
                                    b64_img, _, _ = load_image_as_base64(full_img_path, target_width)
                                    if b64_img:
                                        new_user_content.append({
                                            "type": "image_url",
                                            "image_url": {"url": b64_img}
                                        })
                            # 如果不加载图片，则跳过图片项，只保留文本
                if new_user_content:
                    messages.append({
                        "role": "user",
                        "content": new_user_content
                    })
            else:
                # 如果 content 是字符串
                messages.append({
                    "role": "user",
                    "content": str(user_content)
                })

        # 处理 assistant 消息
        if assistant_data:
            assistant_content = assistant_data.get("content", "")
            messages.append({
                "role": "assistant",
                "content": str(assistant_content)
            })

    return messages


def save_final_messages(messages: list[dict[str, Any]], trace_dir: Path) -> None:
    """
    保存最后一轮的 user 和 assistant messages 到 final_messages.json

    Args:
        messages: 完整的 messages 列表
        trace_dir: trace 目录路径
    """
    # 找到最后一个 user 和 assistant message
    last_user = None
    last_assistant = None

    for msg in reversed(messages):
        if msg.get("role") == "assistant" and last_assistant is None:
            last_assistant = msg
        elif msg.get("role") == "user" and last_user is None:
            last_user = msg

        if last_user and last_assistant:
            break

    if last_user and last_assistant:
        final_data = {
            "user": last_user,
            "assistant": last_assistant,
        }

        final_file = trace_dir / "final_messages.json"
        with open(final_file, "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)

        print(f"💾 Test mode: Final messages saved to {final_file}")


def run_task_with_service(
    task: str,
    service: AgentService,
    action_handler: ActionHandler,
    max_steps: int,
    device_id: str | None,
    system_prompt: str,
    verbose: bool,
    lang: str,
    logger: SimpleTraceLogger | None = None,
    test_mode: bool = False,
    enable_judge: bool = False,
    judge_interval: int = 1,
    judge_k_images: int = 3,
    judge_target_width: int | None = None,
) -> dict[str, Any]:
    """
    Run a task using the service-based architecture.

    Args:
        task: User task description
        service: AgentService instance
        action_handler: ActionHandler instance
        max_steps: Maximum steps to execute
        device_id: Device ID for screenshots
        system_prompt: System prompt for first message
        verbose: Whether to print verbose output
        lang: Language for messages
        logger: Trace logger instance (default: None, trace logging is enabled by default)
        test_mode: Whether to save final user+assistant messages (default: False)
        enable_judge: Whether to enable judge evaluation (default: False)
        judge_interval: Judge evaluation interval in steps (default: 1, judge every step)
        judge_k_images: Number of recent images to load for judge evaluation (default: 3)
        judge_target_width: Target width for short edge of images in judge evaluation, maintains aspect ratio (optional)

    Returns:
        Dictionary with keys:
        - status: Status string ("completed", "max_steps_reached", "model_error", "interrupted_by_judge")
        - message: Result message (if applicable)
        - judge_result: Judge result dictionary (if interrupted by judge)
        - log_dir: Path to log directory (if trace logging enabled)
    """
    # Initialize trace logger task
    if logger:
        trace_dir = logger.start_task(
            task, service.inference_config.k_images, max_steps
        )
        if verbose:
            print(f"📊 Trace logging to: {trace_dir}")

    # Initialize messages list
    messages: list[dict[str, Any]] = []

    # Add system message
    messages.append(MessageBuilder.create_system_message(system_prompt))
    if logger:
        logger.log_system(system_prompt, model_type="service")

    # First step: Add user task with screenshot
    base64_img, width, height = screenshot_to_base64(device_id)
    device_factory = get_device_factory()
    current_app = device_factory.get_current_app(device_id)

    screen_info = MessageBuilder.build_screen_info(current_app)
    text_content = f"{task}\n\n{screen_info}"

    messages.append(
        MessageBuilder.create_user_message(text=text_content, image_base64=base64_img)
    )
    if logger:
        logger.log_user(text_content, base64_img)

    # Execute loop
    step_count = 0
    msgs = get_messages(lang)

    while step_count < max_steps:
        step_count += 1
        

        if verbose:
            print(f"\n{'='*50}")
            print(f"Step {step_count}/{max_steps}")
            print(f"{'='*50}")

        # Call service for inference
        try:
            if verbose:
                print("\n" + "=" * 50)
                print(f"💭 {msgs['thinking']}:")
                print("-" * 50)

            result = service.inference(messages)

            if verbose:
                print(result.thinking)
                print("-" * 50)
                print(f"🎯 {msgs['action']}:")
                print(json.dumps(result.raw_action, ensure_ascii=False, indent=2))
                print("=" * 50)

        except Exception as e:
            if verbose:
                print(f"Model error: {e}")
            error_message = f"Model error: {e}"
            return {
                "status": "model_error",
                "message": error_message,
                "log_dir": str(logger.task_dir.absolute()) if logger else None
            }

        # Add assistant message to context
        raw_action = result.raw_action
        assistant_content = f"<think>{result.thinking}</think><answer>{raw_action}</answer>"
        messages.append(MessageBuilder.create_assistant_message(assistant_content))
        if logger:
            logger.log_assistant(assistant_content)
        ######################## judge ########################
        # 读取当前 log，组织 message（加载最后 K 张图片），使用 judge_service 来评估
        # 只在启用 judge 且满足间隔条件时执行
        if enable_judge and logger and judge_k_images > 0 and step_count % judge_interval == 0:
            try:
                # 读取 trace 并组织消息
                conversation_history = read_trace_and_organize_messages(
                    trace_file=logger.trace_file,
                    task_dir=logger.task_dir,
                    k_images=judge_k_images,
                    target_width=judge_target_width
                )

                if conversation_history:
                    if verbose:
                        print(f"\n🔍 Judge evaluation (step {step_count}, loading last {judge_k_images} images)...")
                    
                    # 调用 judge_service 进行评估
                    judge_result = judge_model_output(
                        conversation_history=conversation_history
                    )

                    # 将 judge 结果写入 log
                    logger.log_judge_result(judge_result)

                    if verbose:
                        print(f"✅ Judge verdict: {judge_result.get('verdict', 'N/A')}")
                        print(f"   Scores: {judge_result.get('scores', 'N/A')}")
                        print(f"   Model score: {judge_result.get('model_score', 'N/A')}")
                        if judge_result.get('repair'):
                            print(f"   Repair: {judge_result.get('repair')}")
                        if judge_result.get('refined'):
                            print(f'   Refined: {judge_result.get('refined')}')
            except Exception as e:
                if verbose:
                    print(f"[WARNING] Judge evaluation failed: {e}")
                import traceback
                traceback.print_exc()
            judge_result['verdict'] = False
            if judge_result.get('verdict') == False:
                return {
                    "status": "interrupted_by_judge",
                    "judge_result": judge_result,
                    "log_dir": str(logger.task_dir.absolute()) if logger else None
                }
        ######################## judge ########################


        # Check if finished
        if result.is_finish:
            final_message = result.message or msgs.get("done", "Task completed")
            if logger:
                logger.end_task("completed", final_message, step_count)
            if test_mode and logger:
                save_final_messages(messages, logger.task_dir)
            if verbose:
                print(f"\n🎉 {'='*48}")
                print(f"✅ {msgs['task_completed']}: {final_message}")
                print("=" * 50)
                if logger:
                    print(f"📊 Trace saved: {logger.task_dir.absolute()}")
            return {
                "status": "completed",
                "message": final_message,
                "log_dir": str(logger.task_dir.absolute()) if logger else None
            }

        # Execute action
        try:
            action_result = action_handler.execute(result.action, width, height)
        except Exception as e:
            if verbose:
                print(f"Action execution error: {e}")
            # Continue anyway to next step

        # Check if action requested finish
        if action_result.should_finish:
            final_message = action_result.message or msgs.get("done", "Task completed")
            if logger:
                logger.end_task("completed", final_message, step_count)
            if test_mode and logger:
                save_final_messages(messages, logger.task_dir)
            if verbose:
                print(f"\n🎉 Action completed the task: {final_message}")
                if logger:
                    print(f"📊 Trace saved: {logger.task_dir.absolute()}")
            return {
                "status": "completed",
                "message": final_message,
                "log_dir": str(logger.task_dir.absolute()) if logger else None
            }

        # Capture new screenshot for next step
        base64_img, width, height = screenshot_to_base64(device_id)
        current_app = device_factory.get_current_app(device_id)
        screen_info = MessageBuilder.build_screen_info(current_app)
        text_content = f"** Screen Info **\n\n{screen_info}"

        messages.append(
            MessageBuilder.create_user_message(
                text=text_content, image_base64=base64_img
            )
        )
        if logger:
            logger.log_user(text_content, base64_img)

    # Max steps reached
    if logger:
        logger.end_task("max_steps_reached", "Max steps reached", step_count)
    if test_mode and logger:
        save_final_messages(messages, logger.task_dir)
    return {
        "status": "max_steps_reached",
        "message": "Max steps reached",
        "log_dir": str(logger.task_dir.absolute()) if logger else None
    }


def convert_backend_tool_to_action(tool_name: str, tool_input: dict) -> dict[str, Any]:
    """
    Convert Claude backend tool format to ActionHandler format.

    Backend format:
        {
            "return_type": "tool_use",
            "name": "Tap",
            "input": {"coordinate": [500, 800]}
        }

    ActionHandler format:
        {
            "_metadata": "do",
            "action": "Tap",
            "element": [500, 800]
        }

    Args:
        tool_name: Tool name from backend (e.g., "Tap", "Launch")
        tool_input: Tool input parameters from backend

    Returns:
        Action dictionary for ActionHandler
    """
    action = {
        "_metadata": "do",
        "action": tool_name
    }

    # Map backend parameters to ActionHandler parameters
    if tool_name == "Launch":
        # Backend: {"package_name": "com.tencent.mm"}
        # Handler: {"app": "微信"}
        # For now, use package_name as app name
        action["app"] = tool_input.get("package_name", "")

    elif tool_name == "Tap":
        # Backend: {"coordinate": [500, 800]}
        # Handler: {"element": [500, 800]}
        action["element"] = tool_input.get("coordinate", [0, 0])

    elif tool_name == "Swipe":
        # Backend: {"start_coordinate": [100, 500], "end_coordinate": [100, 1500]}
        # Handler: {"start": [100, 500], "end": [100, 1500]}
        action["start"] = tool_input.get("start_coordinate", [0, 0])
        action["end"] = tool_input.get("end_coordinate", [0, 0])

    elif tool_name == "Type":
        # Backend: {"text": "hello"}
        # Handler: {"text": "hello"}
        action["text"] = tool_input.get("text", "")

    elif tool_name == "Wait":
        # Backend: {"duration": 2.0}
        # Handler: {"duration": "2.0 seconds"}
        duration = tool_input.get("duration", 1.0)
        action["duration"] = f"{duration} seconds"

    elif tool_name == "LongPress":
        # Backend: {"coordinate": [500, 800], "duration": 2.0}
        # Handler: {"element": [500, 800]}
        action["action"] = "Long Press"
        action["element"] = tool_input.get("coordinate", [0, 0])

    elif tool_name == "DoubleClick":
        # Backend: {"coordinate": [500, 800]}
        # Handler: {"element": [500, 800]}
        action["action"] = "Double Tap"
        action["element"] = tool_input.get("coordinate", [0, 0])

    elif tool_name == "Home":
        # Backend: {}
        # Handler: {}
        pass

    elif tool_name == "Back":
        # Backend: {}
        # Handler: {}
        pass

    return action


def convert_absolute_to_relative(
    action: dict[str, Any],
    screen_width: int,
    screen_height: int
) -> dict[str, Any]:
    """
    Convert absolute pixel coordinates to relative coordinates (0-1000).

    Based on convert_format.py's coordinate transformation logic.

    Args:
        action: Action dict from ModelInterface (contains absolute coordinates)
        screen_width: Screen width in pixels
        screen_height: Screen height in pixels

    Returns:
        Action dict with relative coordinates for ActionHandler
    """
    action_copy = action.copy()

    # Remove coordinate conversion metadata
    action_copy.pop("original_size", None)
    action_copy.pop("scaled_size", None)

    # Calculate scaling factors: absolute -> relative (0-1000)
    scale_x = 1000.0 / screen_width
    scale_y = 1000.0 / screen_height

    action_name = action.get("action")

    # Convert coordinate fields (based on convert_format.py:389-410)
    if action_name in ["Tap", "LongPress", "DoubleClick"]:
        if "coordinate" in action:
            abs_coord = action["coordinate"]
            # Convert to relative coordinates
            rel_x = int(abs_coord[0] * scale_x)
            rel_y = int(abs_coord[1] * scale_y)
            action_copy["element"] = [rel_x, rel_y]
            action_copy.pop("coordinate", None)

        # Rename action to match ActionHandler expectations
        if action_name == "LongPress":
            action_copy["action"] = "Long Press"
        elif action_name == "DoubleClick":
            action_copy["action"] = "Double Tap"

    elif action_name == "Swipe":
        if "start" in action and "end" in action:
            abs_start = action["start"]
            abs_end = action["end"]

            # Convert start and end coordinates
            rel_start_x = int(abs_start[0] * scale_x)
            rel_start_y = int(abs_start[1] * scale_y)
            rel_end_x = int(abs_end[0] * scale_x)
            rel_end_y = int(abs_end[1] * scale_y)

            action_copy["start"] = [rel_start_x, rel_start_y]
            action_copy["end"] = [rel_end_x, rel_end_y]

    elif action_name == "Wait":
        # Convert duration: float -> "X seconds"
        if "duration" in action:
            duration = action["duration"]
            action_copy["duration"] = f"{duration} seconds"

    return action_copy


def run_task_with_claude_backend(
    task: str,
    action_handler: ActionHandler,
    max_steps: int,
    device_id: str | None,
    system_prompt: str,
    verbose: bool,
    lang: str,
    api_key: str = None,
    api_url: str = None,
    model: str = None,
    target_width: int = 512,
    logger: SimpleTraceLogger | None = None,
    test_mode: bool = False,
) -> dict[str, Any]:
    """
    Run a task using direct ModelInterface (Claude backend).

    This function manages context like run_task_with_service but uses
    ModelInterface instead of AgentService for inference.

    Args:
        task: User task description
        action_handler: ActionHandler instance
        max_steps: Maximum steps to execute
        device_id: Device ID for screenshots
        system_prompt: System prompt for the model
        verbose: Whether to print verbose output
        lang: Language for messages
        api_key: Claude API key (default: None, uses env var)
        api_url: Claude API URL (default: None, uses ModelInterface default)
        model: Claude model name (default: None, uses ModelInterface default)
        target_width: Target width for screenshot resizing (default: 512)
        logger: Trace logger instance (default: None, trace logging is enabled by default)
        test_mode: Whether to save final user+assistant messages (default: False)

    Returns:
        Dictionary with keys:
        - status: Status string ("completed", "max_steps_reached", "model_error")
        - message: Result message (if applicable)
        - log_dir: Path to log directory (if trace logging enabled)
    """
    # Initialize ModelInterface
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from backend.model_interface import ModelInterface

    model_interface = ModelInterface(
        api_key=api_key,
        api_url=api_url,
        model=model,
        target_width=target_width
    )

    # Initialize trace logger task
    if logger:
        trace_dir = logger.start_task(task, k_images=-1, max_steps=max_steps)
        if verbose:
            print(f"📊 Trace logging to: {trace_dir}")

    # Initialize context (Claude API format)
    context: list[dict[str, Any]] = []

    # Get initial screenshot
    base64_img, width, height = screenshot_to_base64(device_id)
    device_factory = get_device_factory()
    current_app = device_factory.get_current_app(device_id)

    # Log system prompt (for trace only)
    if logger:
        logger.log_system(system_prompt, model_type="claude_backend")

    # First call to ModelInterface
    screen_info = MessageBuilder.build_screen_info(current_app)
    user_prompt = f"{task}\n\n{screen_info}"

    # Log user message
    if logger:
        logger.log_user(user_prompt, base64_img)

    # Call ModelInterface
    try:
        result = model_interface.call_model(
            context=context,
            screenshot_base64=base64_img,
            current_app_name=current_app,
            user_prompt=user_prompt
        )
    except Exception as e:
        if verbose:
            print(f"Model error: {e}")
        return {
            "status": "model_error",
            "message": f"Model error: {e}",
            "log_dir": str(logger.task_dir.absolute()) if logger else None
        }

    # Main loop
    step_count = 0
    msgs = get_messages(lang)

    while step_count < max_steps:
        step_count += 1

        if verbose:
            print(f"\n{'='*50}")
            print(f"Step {step_count}/{max_steps}")
            print(f"{'='*50}")

        # Parse response
        response = result["response"]  # ActionHandler format + absolute coordinates
        thinking = result.get("thinking", "")

        if verbose:
            print(f"\n💭 {msgs['thinking']}:")
            print(thinking)
            print(f"\n🎯 {msgs['action']}:")
            print(json.dumps(response, ensure_ascii=False, indent=2))

        # Log assistant message
        if logger:
            assistant_content = f"<think>{thinking}</think><answer>{json.dumps(response, ensure_ascii=False)}</answer>"
            logger.log_assistant(assistant_content)

        # Check if finish
        if response.get("_metadata") == "finish":
            final_message = response.get("message", msgs.get("done", "Task completed"))
            if logger:
                logger.end_task("completed", final_message, step_count)
            if test_mode and logger:
                pass  # Cannot save final_messages without maintaining messages list
            if verbose:
                print(f"\n✅ {msgs['task_completed']}: {final_message}")
                if logger:
                    print(f"📊 Trace saved: {logger.task_dir.absolute()}")
            return {
                "status": "completed",
                "message": final_message,
                "log_dir": str(logger.task_dir.absolute()) if logger else None
            }

        # Execute action - convert coordinates
        try:
            action = convert_absolute_to_relative(response, width, height)
            action_result = action_handler.execute(action, width, height)
        except Exception as e:
            if verbose:
                print(f"Action execution error: {e}")

        # Check if action requested finish
        if action_result.should_finish:
            final_message = action_result.message or msgs.get("done", "Task completed")
            if logger:
                logger.end_task("completed", final_message, step_count)
            if test_mode and logger:
                pass
            if verbose:
                print(f"\n🎉 Action completed the task: {final_message}")
                if logger:
                    print(f"📊 Trace saved: {logger.task_dir.absolute()}")
            return {
                "status": "completed",
                "message": final_message,
                "log_dir": str(logger.task_dir.absolute()) if logger else None
            }

        # Get new screenshot
        base64_img, width, height = screenshot_to_base64(device_id)
        current_app = device_factory.get_current_app(device_id)

        screen_info = MessageBuilder.build_screen_info(current_app)
        text_content = f"** Screen Info **\n\n{screen_info}"

        # Log user message
        if logger:
            logger.log_user(text_content, base64_img)

        # Next call to ModelInterface
        try:
            result = model_interface.call_model(
                context=context,
                screenshot_base64=base64_img,
                current_app_name=current_app,
                user_prompt=""  # tool_result doesn't need additional prompt
            )
        except Exception as e:
            if verbose:
                print(f"Model error: {e}")
            if logger:
                logger.end_task("model_error", f"Model error: {e}", step_count)
            return {
                "status": "model_error",
                "message": f"Model error: {e}",
                "log_dir": str(logger.task_dir.absolute()) if logger else None
            }

    # Max steps reached
    if logger:
        logger.end_task("max_steps_reached", "Max steps reached", step_count)
    if verbose:
        print(f"\n⚠️  达到最大迭代次数 ({max_steps})")
    return {
        "status": "max_steps_reached",
        "message": "Max steps reached",
        "log_dir": str(logger.task_dir.absolute()) if logger else None
    }



def take_over_with_claude_backend(
    task: str,
    claude_context: list[dict[str, Any]],
    action_handler: ActionHandler,
    max_steps: int,
    device_id: str | None,
    system_prompt: str,
    verbose: bool,
    lang: str,
    api_key: str = None,
    api_url: str = None,
    model: str = None,
    target_width: int = 512,
    logger: SimpleTraceLogger | None = None,
    test_mode: bool = False,
) -> dict[str, Any]:
    """
    Run a task using direct ModelInterface (Claude backend).

    This function manages context like run_task_with_service but uses
    ModelInterface instead of AgentService for inference.

    Args:
        task: User task description
        action_handler: ActionHandler instance
        max_steps: Maximum steps to execute
        device_id: Device ID for screenshots
        system_prompt: System prompt for the model
        verbose: Whether to print verbose output
        lang: Language for messages
        api_key: Claude API key (default: None, uses env var)
        api_url: Claude API URL (default: None, uses ModelInterface default)
        model: Claude model name (default: None, uses ModelInterface default)
        target_width: Target width for screenshot resizing (default: 512)
        logger: Trace logger instance (default: None, trace logging is enabled by default)
        test_mode: Whether to save final user+assistant messages (default: False)

    Returns:
        Dictionary with keys:
        - status: Status string ("completed", "max_steps_reached", "model_error")
        - message: Result message (if applicable)
        - log_dir: Path to log directory (if trace logging enabled)
    """
    # Initialize ModelInterface
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from backend.model_interface import ModelInterface

    model_interface = ModelInterface(
        api_key=api_key,
        api_url=api_url,
        model=model,
        target_width=target_width
    )

    # Initialize trace logger task
    if logger and verbose:
        print(f"📊 Trace logging to: {logger.task_dir.absolute()}")

    # 初始化claude_context
    claude_context.append({
        "type": "text",
        "text": f"基于上下文，接下来你来继续完成任务：{task}"
    })
    # logger.save_debug(f"claude_context_01.json", {
    #     "claude_context": claude_context
    # })

    # Initialize context (Claude API format)
    context: list[dict[str, Any]] = []

    # Get initial screenshot
    base64_img, width, height = screenshot_to_base64(device_id)
    device_factory = get_device_factory()
    current_app = device_factory.get_current_app(device_id)

    # Log system prompt (for trace only)
    if logger:
        logger.log_system(system_prompt, model_type="claude_backend")

    # First call to ModelInterface

    # Call ModelInterface
    try:
        result = model_interface.call_model(
            context=context,
            screenshot_base64=base64_img,
            current_app_name=current_app,
            user_prompt=claude_context
        )
    except Exception as e:
        if verbose:
            print(f"Model error: {e}")
        return {
            "status": "model_error",
            "message": f"Model error: {e}",
            "log_dir": str(logger.task_dir.absolute()) if logger else None
        }

    # Main loop
    step_count = 0
    msgs = get_messages(lang)

    while step_count < max_steps:
        step_count += 1

        if verbose:
            print(f"\n{'='*50}")
            print(f"Step {step_count}/{max_steps}")
            print(f"{'='*50}")

        # Parse response
        response = result["response"]  # ActionHandler format + absolute coordinates
        thinking = result.get("thinking", "")

        if verbose:
            print(f"\n💭 {msgs['thinking']}:")
            print(thinking)
            print(f"\n🎯 {msgs['action']}:")
            print(json.dumps(response, ensure_ascii=False, indent=2))

        # Log assistant message
        if logger:
            assistant_content = f"<think>{thinking}</think><answer>{json.dumps(response, ensure_ascii=False)}</answer>"
            logger.log_assistant(assistant_content)

        # Check if finish
        if response.get("_metadata") == "finish":
            final_message = response.get("message", msgs.get("done", "Task completed"))
            if logger:
                logger.end_task("completed", final_message, step_count)
            if test_mode and logger:
                pass  # Cannot save final_messages without maintaining messages list
            if verbose:
                print(f"\n✅ {msgs['task_completed']}: {final_message}")
                if logger:
                    print(f"📊 Trace saved: {logger.task_dir.absolute()}")
            return {
                "status": "completed",
                "message": final_message,
                "log_dir": str(logger.task_dir.absolute()) if logger else None
            }

        # Execute action - convert coordinates
        try:
            action = convert_absolute_to_relative(response, width, height)
            action_result = action_handler.execute(action, width, height)
        except Exception as e:
            if verbose:
                print(f"Action execution error: {e}")

        # Check if action requested finish
        if action_result.should_finish:
            final_message = action_result.message or msgs.get("done", "Task completed")
            if logger:
                logger.end_task("completed", final_message, step_count)
            if test_mode and logger:
                pass
            if verbose:
                print(f"\n🎉 Action completed the task: {final_message}")
                if logger:
                    print(f"📊 Trace saved: {logger.task_dir.absolute()}")
            return {
                "status": "completed",
                "message": final_message,
                "log_dir": str(logger.task_dir.absolute()) if logger else None
            }

        # Get new screenshot
        base64_img, width, height = screenshot_to_base64(device_id)
        current_app = device_factory.get_current_app(device_id)

        screen_info = MessageBuilder.build_screen_info(current_app)
        text_content = f"** Screen Info **\n\n{screen_info}"

        # Log user message
        if logger:
            logger.log_user(text_content, base64_img)

        # Next call to ModelInterface
        try:
            result = model_interface.call_model(
                context=context,
                screenshot_base64=base64_img,
                current_app_name=current_app,
                user_prompt=""  # tool_result doesn't need additional prompt
            )
        except Exception as e:
            if verbose:
                print(f"Model error: {e}")
            if logger:
                logger.end_task("model_error", f"Model error: {e}", step_count)
            return {
                "status": "model_error",
                "message": f"Model error: {e}",
                "log_dir": str(logger.task_dir.absolute()) if logger else None
            }

    # Max steps reached
    if logger:
        logger.end_task("max_steps_reached", "Max steps reached", step_count)
    if verbose:
        print(f"\n⚠️  达到最大迭代次数 ({max_steps})")
    return {
        "status": "max_steps_reached",
        "message": "Max steps reached",
        "log_dir": str(logger.task_dir.absolute()) if logger else None
    }


def parse_args() -> argparse.Namespace:
    """Parse command line arguments with additional k_images parameter."""
    # First, extract our custom arguments
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--k-images",
        type=int,
        default=int(os.getenv("PHONE_AGENT_K_IMAGES", "3")),
        help="Number of recent images to keep (default: 3, -1 for all)",
    )
    parser.add_argument(
        "--enable-judge",
        action="store_true",
        help="Enable judge evaluation (default: False)",
    )
    parser.add_argument(
        "--judge-interval",
        type=int,
        default=int(os.getenv("PHONE_AGENT_JUDGE_INTERVAL", "1")),
        help="Judge evaluation interval in steps (default: 1, judge every step)",
    )
    parser.add_argument(
        "--judge-k-images",
        type=int,
        default=int(os.getenv("PHONE_AGENT_JUDGE_K_IMAGES", "3")),
        help="Number of recent images to load for judge evaluation (default: 3, 0 to disable)",
    )
    parser.add_argument(
        "--judge-target-width",
        type=int,
        default=None,
        help="Target width for short edge of images in judge evaluation, maintains aspect ratio (optional)",
    )
    parser.add_argument("--disable-trace", action="store_true")
    parser.add_argument("--trace-root", type=str)
    parser.add_argument(
        "--test",
        action="store_true",
        help="Enable test mode: save final user+assistant messages to trace directory",
    )
    parser.add_argument(
        "--claude-backend",
        action="store_true",
        help="Use Claude backend API instead of local service (default: False)",
    )
    parser.add_argument(
        "--claude-api-key",
        type=str,
        default=os.getenv("CLAUDE_API_KEY"),
        help="Claude API key (default: from CLAUDE_API_KEY env var)"
    )
    parser.add_argument(
        "--claude-api-url",
        type=str,
        default=None,
        help="Claude API URL (default: ModelInterface.DEFAULT_BASE_URL/messages)"
    )
    parser.add_argument(
        "--claude-model",
        type=str,
        default=None,
        help="Claude model name (default: ModelInterface.DEFAULT_MODEL_NAME)"
    )
    parser.add_argument(
        "--claude-target-width",
        type=int,
        default=512,
        help="Target width for screenshot resizing (default: 512)"
    )

    # Parse only our custom args, ignore unknown
    custom_args, remaining_argv = parser.parse_known_args()

    # Temporarily modify sys.argv to remove our custom args
    import sys

    original_argv = sys.argv[:]
    sys.argv = [sys.argv[0]] + remaining_argv

    try:
        # Parse using original parser
        args = original_parse_args()
    finally:
        # Restore original argv
        sys.argv = original_argv

    # Add our custom args to the result
    args.k_images = custom_args.k_images
    args.enable_judge = custom_args.enable_judge
    args.judge_interval = custom_args.judge_interval
    args.judge_k_images = custom_args.judge_k_images
    args.judge_target_width = custom_args.judge_target_width
    if custom_args.disable_trace:
        args.disable_trace = True
    elif not hasattr(args, "disable_trace"):
        args.disable_trace = False
    if custom_args.trace_root:
        args.trace_root = custom_args.trace_root
    elif not hasattr(args, "trace_root"):
        args.trace_root = os.getenv("PHONE_AGENT_TRACE_ROOT", "./traces")
    args.test = custom_args.test
    args.claude_backend = custom_args.claude_backend
    args.claude_api_key = custom_args.claude_api_key
    args.claude_api_url = custom_args.claude_api_url
    args.claude_model = custom_args.claude_model
    args.claude_target_width = custom_args.claude_target_width

    return args

def show_results(result: dict):
    if isinstance(result, dict):
        print(f"\nStatus: {result.get('status', 'unknown')}")
        if result.get('message'):
            print(f"Message: {result.get('message')}")
        if result.get('conversation_id'):
            print(f"Conversation ID: {result.get('conversation_id')}")
        if result.get('log_dir'):
            print(f"Log directory: {result.get('log_dir')}")
        if result.get('judge_result'):
            print(f"Judge result: {result.get('judge_result')}")
        print()
    else:
        print(f"\nResult: {result}\n")



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

    # Handle --list-apps
    if args.list_apps:
        if device_type == DeviceType.HDC:
            from phone_agent.config.apps_harmonyos import (
                list_supported_apps as list_harmonyos_apps,
            )

            print("Supported HarmonyOS apps:")
            apps = list_harmonyos_apps()
        else:
            from phone_agent.config.apps import list_supported_apps

            print("Supported Android apps:")
            apps = list_supported_apps()

        for app in apps:
            print(f"  - {app}")
        return

    # Handle device commands
    if handle_device_commands(args):
        return

    # Run system requirements check
    if not check_system_requirements(device_type):
        sys.exit(1)

    # Create action handler (needed for both modes)
    action_handler = ActionHandler(device_id=args.device_id)

    # Initialize variables for both modes
    service = None
    model_config = None
    inference_config = None
    system_prompt = get_system_prompt(args.lang)

    # Setup based on backend mode
    if args.claude_backend:
        # Claude backend mode: no need for model API or service
        print("\n🌐 Using Claude Backend API mode")
    else:
        # Local service mode: check API and create service
        if not check_model_api(args.base_url, args.model, args.apikey):
            sys.exit(1)

        # Create configurations
        model_config = ModelConfig(
            base_url=args.base_url,
            model_name=args.model,
            api_key=args.apikey,
            lang=args.lang,
        )

        inference_config = InferenceConfig(
            k_images=args.k_images,
            verbose=not args.quiet,
            lang=args.lang,
        )

        # Create service
        service = AgentService(model_config, inference_config)

    # Print header and configuration
    print("=" * 50)
    if args.claude_backend:
        print("Phone Agent (Claude Backend) - AI-powered phone automation")
    else:
        print("Phone Agent (Service-based) - AI-powered phone automation")
    print("=" * 50)
    print("\n📋 Configuration Parameters:")
    print("-" * 50)

    if args.claude_backend:
        # Claude Backend Configuration
        print("Backend Configuration:")
        print(f"  API Key: {args.claude_api_key[:10]}..." if args.claude_api_key else "  API Key: None")
        print(f"  API URL: {args.claude_api_url or 'Default (ModelInterface)'}")
        print(f"  Model: {args.claude_model or 'Default (claude-sonnet-4-5-20250929)'}")
        print(f"  Target Width: {args.claude_target_width}")
        print(f"  Language: {args.lang}")
        print(f"  Max Steps: {args.max_steps}")
        print(f"  Verbose: {not args.quiet}")
        print(f"  Test Mode: {args.test}")
    else:
        # Model Configuration
        print("Model Configuration:")
        print(f"  Base URL: {model_config.base_url}")
        print(f"  Model Name: {model_config.model_name}")
        print(f"  API Key: {model_config.api_key}")
        print(f"  Max Tokens: {model_config.max_tokens}")
        print(f"  Temperature: {model_config.temperature}")
        print(f"  Top P: {model_config.top_p}")
        print(f"  Frequency Penalty: {model_config.frequency_penalty}")
        print(f"  Language: {model_config.lang}")

        # Inference Configuration
        print("\nInference Configuration:")
        print(f"  K Images: {inference_config.k_images}")
        print(f"  Enable Judge: {args.enable_judge}")
        if args.enable_judge:
            print(f"  Judge Interval: {args.judge_interval}")
            print(f"  Judge K Images: {args.judge_k_images}")
            if args.judge_target_width:
                print(f"  Judge Image Target Width (short edge): {args.judge_target_width}")
        print(f"  Max Steps: {args.max_steps}")
        print(f"  Verbose: {inference_config.verbose}")
        print(f"  Test Mode: {args.test}")

    # Device Configuration
    print("\nDevice Configuration:")
    print(f"  Device Type: {args.device_type.upper()}")
    device_factory = get_device_factory()
    devices = device_factory.list_devices()
    if args.device_id:
        print(f"  Device ID: {args.device_id}")
    elif devices:
        print(f"  Device ID: {devices[0].device_id} (auto-detected)")
    else:
        print(f"  Device ID: None")

    print("=" * 50)

    # Run with provided task or enter interactive mode
    if args.task:
        print(f"\nTask: {args.task}\n")
        
        # Initialize logger (trace logging is enabled by default)
        # logger = None
        # if not args.disable_trace:
        #     trace_root = args.trace_root if hasattr(args, 'trace_root') and args.trace_root else "./traces"
        #     logger = SimpleTraceLogger(trace_root)
        
        ##################################################单元测试
        # if args.claude_backend:
        #     # Use Claude backend (ModelInterface)
        #     result = run_task_with_claude_backend(
        #         task=args.task,
        #         action_handler=action_handler,
        #         max_steps=args.max_steps,
        #         device_id=args.device_id,
        #         system_prompt=system_prompt,
        #         verbose=not args.quiet,
        #         lang=args.lang,
        #         api_key=args.claude_api_key,
        #         api_url=args.claude_api_url,
        #         model=args.claude_model,
        #         target_width=args.claude_target_width,
        #         logger=logger,
        #         test_mode=args.test,
        #     )
        # else:
        #     # Use local service
        #     result = run_task_with_service(
        #         task=args.task,
        #         service=service,
        #         action_handler=action_handler,
        #         max_steps=args.max_steps,
        #         device_id=args.device_id,
        #         system_prompt=system_prompt,
        #         verbose=not args.quiet,
        #         lang=args.lang,
        #         logger=logger,
        #         test_mode=args.test,
        #         enable_judge=args.enable_judge,
        #         judge_interval=args.judge_interval,
        #         judge_k_images=args.judge_k_images,
        #         judge_target_width=args.judge_target_width,
        #     )
        ##################################################单元测试
        # logger = None
        # if not args.disable_trace:
        #     trace_root = args.trace_root if hasattr(args, 'trace_root') and args.trace_root else "./traces"
        #     logger = SimpleTraceLogger(trace_root)
        # result = run_task_with_service(
        #         task=args.task,
        #         service=service,
        #         action_handler=action_handler,
        #         max_steps=args.max_steps,
        #         device_id=args.device_id,
        #         system_prompt=system_prompt,
        #         verbose=not args.quiet,
        #         lang=args.lang,
        #         logger=logger,
        #         test_mode=args.test,
        #         enable_judge=True,
        #         judge_interval=args.judge_interval,
        #         judge_k_images=args.judge_k_images,
        #         judge_target_width=args.judge_target_width,
        #     )
        # print(f'result: {result}')
        # status = result.get('status')
        # takeover_triggered = False
        # if status == 'completed':
        #     print(f'Task completed')
        # elif status == 'max_steps_reached':
        #     print(f'Max steps reached')
        # elif status == 'model_error':
        #     print(f'Model error')
        # elif status == 'interrupted_by_judge':
        #     print( f'*' * 100)
        #     print(f'Interrupted by judge, takeover by claude')
        #     takeover_triggered = True
        #     print(f'*' * 100)
        # ############
        # print(f'logger.trace_root: {logger.trace_root}')
        # print(f'logger.task_id: {logger.task_id}')
        # print(f'logger.task_dir: {logger.task_dir}')
        # print(f'logger.trace_file: {logger.trace_file}')
        # print(f'logger.step_count: {logger.step_count}')
        # exit()
        logger = SimpleTraceLogger(
            trace_root='traces',
            task_id='20260107_112701',
            task_dir='traces/20260107_112701',
            trace_file='traces/20260107_112701/trace.jsonl',
            step_count=5,
        )

        # conversation_history = read_trace_and_organize_messages(
        #             trace_file=logger.trace_file,
        #             task_dir=logger.task_dir,
        #             k_images=judge_k_images,
        #             target_width=judge_target_width
        #         )
        takeover_triggered = True
        ########### claude接管 ########################
        if takeover_triggered:
            # Initialize logger for claude backend (use claude_bac∂kend_traces as default)
            claude_logger = logger
            # 读取trace文件，组织claude_context
            conversation_history = read_trace_and_organize_messages(
                    trace_file=logger.trace_file,
                    task_dir=logger.task_dir,
                    k_images=20,
                    target_width=args.claude_target_width
                )
            claude_context = [
                {
                    "type": "text",
                    "text": f"以下为之前执行的上下文"
                }
            ]
            step_count = 0
            for message in conversation_history:
                role = message.get('role')
                content = message.get('content')
                if type(content) == str:
                    claude_context.append({
                        "type": "text",
                        "text": f'<{role}>, step {step_count}: {content}'
                    })
                elif type(content) == list:
                    for item in content:
                        if item['type'] == 'text':
                            claude_context.append({
                                "type": "text",
                                "text": f'<{role}>, step {step_count}: {item['text']}'
                            })
                        elif item['type'] == 'image_url':
                            raw_image_content = item['image_url']['url']
                            base64_image = raw_image_content[len('data:image/png;base64,'):]
                            claude_context.append({
                                "type": "image",
                                "source": {"type": "base64", "media_type": "image/png", "data": base64_image}
                            })
                else:
                    raise ValueError(f"Invalid content type: {type(content)}")
                step_count += 1
            
            result = take_over_with_claude_backend(
                task=args.task,
                claude_context=claude_context,
                action_handler=action_handler,
                max_steps=args.max_steps,
                device_id=args.device_id,
                system_prompt=system_prompt,
                verbose=not args.quiet,
                lang=args.lang,
                api_key=args.claude_api_key,
                api_url=args.claude_api_url,
                model=args.claude_model,
                target_width=args.claude_target_width,
                logger=claude_logger,
                test_mode=args.test,
            )
        

        show_results(result)
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
                
                # Initialize logger for interactive mode
                interactive_logger = None
                if not args.disable_trace:
                    if args.claude_backend:
                        trace_root = args.trace_root if hasattr(args, 'trace_root') and args.trace_root else "./claude_backend_traces"
                    else:
                        trace_root = args.trace_root if hasattr(args, 'trace_root') and args.trace_root else "./traces"
                    interactive_logger = SimpleTraceLogger(trace_root)
                
                if args.claude_backend:
                    # Use Claude backend (ModelInterface)
                    result = run_task_with_claude_backend(
                        task=task,
                        action_handler=action_handler,
                        max_steps=args.max_steps,
                        device_id=args.device_id,
                        system_prompt=system_prompt,
                        verbose=not args.quiet,
                        lang=args.lang,
                        api_key=args.claude_api_key,
                        api_url=args.claude_api_url,
                        model=args.claude_model,
                        target_width=args.claude_target_width,
                        logger=interactive_logger,
                        test_mode=args.test,
                    )
                else:
                    # Use local service
                    result = run_task_with_service(
                        task=task,
                        service=service,
                        action_handler=action_handler,
                        max_steps=args.max_steps,
                        device_id=args.device_id,
                        system_prompt=system_prompt,
                        verbose=not args.quiet,
                        lang=args.lang,
                        logger=interactive_logger,
                        test_mode=args.test,
                        enable_judge=args.enable_judge,
                        judge_interval=args.judge_interval,
                        judge_k_images=args.judge_k_images,
                        judge_target_width=args.judge_target_width,
                    )
                
                if isinstance(result, dict):
                    print(f"\nStatus: {result.get('status', 'unknown')}")
                    if result.get('message'):
                        print(f"Message: {result.get('message')}")
                    if result.get('conversation_id'):
                        print(f"Conversation ID: {result.get('conversation_id')}")
                    if result.get('log_dir'):
                        print(f"Log directory: {result.get('log_dir')}")
                    if result.get('judge_result'):
                        print(f"Judge result: {result.get('judge_result')}")
                    print()
                else:
                    print(f"\nResult: {result}\n")

            except KeyboardInterrupt:
                print("\n\nInterrupted. Goodbye!")
                break
            except Exception as e:
                print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
