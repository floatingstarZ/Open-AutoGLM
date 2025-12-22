"""Trace logger for recording agent execution steps with screenshots."""

import base64
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TraceLogger:
    """
    Logger for recording agent execution traces.

    Records each step with:
    - Screenshot (saved to file)
    - Model input/output
    - Thinking process
    - Action executed
    - Metadata (timestamp, step index, etc.)
    """

    def __init__(self, trace_root: str | None = None):
        """
        Initialize trace logger.

        Args:
            trace_root: Root directory for trace files (default: ./traces)
        """
        self.trace_root = Path(trace_root or "traces").resolve()
        self.trace_root.mkdir(parents=True, exist_ok=True)

        # Current task tracking
        self.task_id: str | None = None
        self.task_dir: Path | None = None
        self.trace_file: Path | None = None
        self.step_index = 0

    def start_task(self, task_id: str, task_description: str) -> None:
        """
        Start recording a new task.

        Args:
            task_id: Unique identifier for the task
            task_description: Natural language description of the task
        """
        self.task_id = task_id
        self.step_index = 0

        # Create task directory
        self.task_dir = self.trace_root / task_id
        self.task_dir.mkdir(parents=True, exist_ok=True)

        # Create trace file
        self.trace_file = self.task_dir / "trace.jsonl"

        # Record task metadata
        metadata = {
            "type": "task_start",
            "task_id": task_id,
            "task_description": task_description,
            "timestamp": datetime.now().isoformat(),
        }

        self._append_to_trace(metadata)
        logger.info(f"Started recording task: {task_id}")
        logger.info(f"Trace directory: {self.task_dir.absolute()}")
        logger.info(f"Trace file: {self.trace_file.absolute()}")

    def log_step(
        self,
        screenshot_base64: str,
        model_input: list[dict[str, Any]],
        model_output: str,
        thinking: str,
        action: dict[str, Any],
        current_app: str | None = None,
        screen_width: int | None = None,
        screen_height: int | None = None,
        raw_model_output = None,
        format_model_output = None,
    ) -> None:
        """
        Log a single execution step.

        Args:
            screenshot_base64: Base64 encoded screenshot
            model_input: Messages sent to model
            model_output: Raw output from model
            thinking: Extracted thinking process
            action: Parsed action to execute
            current_app: Current app package name
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            raw_model_output: Raw model output
            format_model_output: Formatted model output
        """
        if not self.task_id or not self.task_dir:
            logger.warning("Cannot log step: task not started")
            return

        self.step_index += 1

        # Save screenshot to file
        screenshot_path = self.task_dir / f"step_{self.step_index}.png"
        try:
            image_data = base64.b64decode(screenshot_base64)
            with open(screenshot_path, "wb") as f:
                f.write(image_data)
            logger.info(f"Screenshot saved: {screenshot_path.absolute()}")
        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")
            screenshot_path = None

        # Create step record
        step_data = {
            "type": "step",
            "task_id": self.task_id,
            "step_index": self.step_index,
            "timestamp": datetime.now().isoformat(),
            "screenshot_path": str(screenshot_path.relative_to(self.trace_root)) if screenshot_path else None,
            "current_app": current_app,
            "screen_size": {
                "width": screen_width,
                "height": screen_height,
            } if screen_width and screen_height else None,
            "model_input": self._sanitize_model_input(model_input),
            "model_output": model_output,
            "thinking": thinking,
            "action": action,
            "raw_model_output": raw_model_output,
            "format_model_output": format_model_output,
        }

        self._append_to_trace(step_data)
        logger.info(f"Logged step {self.step_index} for task {self.task_id}")
        logger.info(f"Step data appended to: {self.trace_file.absolute()}")

    def reset(self) -> None:
        """Reset logger state after task completion."""
        if self.task_id and self.task_dir:
            logger.info(f"Task {self.task_id} completed with {self.step_index} steps")
            logger.info(f"Complete trace saved in: {self.task_dir.absolute()}")
            logger.info(f"  - Trace file: {self.trace_file.absolute()}")
            logger.info(f"  - Screenshots: {self.task_dir.absolute()}/step_*.png")

        # Reset state
        self.task_id = None
        self.task_dir = None
        self.trace_file = None
        self.step_index = 0

    def _append_to_trace(self, data: dict[str, Any]) -> None:
        """Append data to trace file as JSON line."""
        if not self.trace_file:
            return

        try:
            with open(self.trace_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to write to trace file: {e}")

    def _sanitize_model_input(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Remove base64 image data from model input to reduce file size.

        Replaces image data with placeholder indicating image was present.
        """
        sanitized = []
        for msg in messages:
            msg_copy = msg.copy()

            # Handle content that might contain images
            if "content" in msg_copy:
                content = msg_copy["content"]

                # String content - no images
                if isinstance(content, str):
                    sanitized.append(msg_copy)
                    continue

                # List content - may contain images
                if isinstance(content, list):
                    new_content = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "image":
                            # Replace image data with placeholder
                            new_content.append({
                                "type": "image",
                                "placeholder": "<image_removed_from_trace>"
                            })
                        else:
                            new_content.append(item)
                    msg_copy["content"] = new_content

            sanitized.append(msg_copy)

        return sanitized


# Global trace logger instance
_trace_logger: TraceLogger | None = None


def get_trace_logger(trace_root: str | None = None) -> TraceLogger:
    """
    Get or create global trace logger instance.

    Args:
        trace_root: Root directory for trace files

    Returns:
        TraceLogger instance
    """
    global _trace_logger
    if _trace_logger is None:
        _trace_logger = TraceLogger(trace_root)
    return _trace_logger
