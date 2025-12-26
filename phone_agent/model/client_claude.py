"""Claude API client for phone automation."""

import base64
import io
import json
import time
from dataclasses import dataclass, field
from typing import Any

import requests
from PIL import Image


@dataclass
class ClaudeModelConfig:
    """Configuration for Claude API."""

    api_key: str = "EMPTY"
    base_url: str = "https://api-gateway.glm.ai/v1"
    model_name: str = "claude-sonnet-4-20250514"
    max_tokens: int = 16000
    thinking_budget_tokens: int = 12800
    target_screenshot_width: int = 512
    lang: str = "cn"


@dataclass
class ClaudeModelResponse:
    """Response from Claude API."""

    thinking: str
    action: str  # Tool use or text response
    tool_use: dict[str, Any] | None = None  # Parsed tool use if any
    raw_content: list[dict[str, Any]] = field(default_factory=list)
    total_time: float | None = None


class ClaudeModelClient:
    """
    Client for interacting with Claude API (Anthropic format).

    Handles:
    - Screenshot resizing and coordinate conversion
    - Claude-format API calls with thinking + tools
    - Tool use parsing
    - Context building
    """

    def __init__(self, config: ClaudeModelConfig | None = None):
        self.config = config or ClaudeModelConfig()

        # Track dimensions for coordinate conversion
        self.original_width: int | None = None
        self.original_height: int | None = None
        self.scaled_width: int | None = None
        self.scaled_height: int | None = None

    def request(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]]
    ) -> ClaudeModelResponse:
        """
        Send request to Claude API.

        Args:
            messages: List of messages in Claude format
            system_prompt: System prompt string
            tools: List of tool definitions

        Returns:
            ClaudeModelResponse with thinking and action
        """
        start_time = time.time()

        # Prepare API request
        data = {
            "model": self.config.model_name,
            "max_tokens": self.config.max_tokens,
            "system": system_prompt,
            "messages": messages,
            "thinking": {
                "type": "enabled",
                "budget_tokens": self.config.thinking_budget_tokens
            },
            "tools": tools
        }

        # Call API
        response_data = self._call_api(data)

        # Parse response
        thinking_text = ""
        text_content = ""
        tool_use_block = None

        for block in response_data.get("content", []):
            if block.get("type") == "thinking":
                thinking_text = block.get("thinking", "")
                print(f"💭 Thinking:\n{thinking_text}\n")

            elif block.get("type") == "text":
                text_content = block.get("text", "")
                print(f"📝 Text: {text_content}\n")

            elif block.get("type") == "tool_use":
                tool_use_block = block
                print(f"🔧 Tool: {block.get('name')}")
                print(f"   Input: {json.dumps(block.get('input', {}), ensure_ascii=False)}\n")

        total_time = time.time() - start_time

        # Determine action (tool use or text)
        action = ""
        parsed_tool = None

        if tool_use_block:
            # Parse tool use and convert coordinates if needed
            parsed_tool = self._parse_tool_use(tool_use_block)
            action = json.dumps(parsed_tool, ensure_ascii=False)
        else:
            action = text_content

        return ClaudeModelResponse(
            thinking=thinking_text,
            action=action,
            tool_use=parsed_tool,
            raw_content=response_data.get("content", []),
            total_time=total_time
        )

    def resize_screenshot(self, base64_image: str) -> tuple[int, int, str]:
        """
        Resize screenshot to target width while maintaining aspect ratio.

        Args:
            base64_image: Base64 encoded image

        Returns:
            Tuple of (height, width, resized_base64_image)
        """
        # Decode
        img_data = base64.b64decode(base64_image)
        img = Image.open(io.BytesIO(img_data))

        # Store original dimensions
        width, height = img.size
        self.original_width = width
        self.original_height = height

        # Calculate new dimensions
        if width < height:
            new_width = self.config.target_screenshot_width
            new_height = int(height * (self.config.target_screenshot_width / width))
        else:
            new_height = self.config.target_screenshot_width
            new_width = int(width * (self.config.target_screenshot_width / height))

        # Store scaled dimensions
        self.scaled_width = new_width
        self.scaled_height = new_height

        # Resize
        img_resized = img.resize((new_width, new_height), Image.LANCZOS)

        # Encode back to base64
        buffer = io.BytesIO()
        img_resized.save(buffer, format='PNG')
        b64_code = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return new_height, new_width, b64_code

    def scale_coordinate_to_real(self, scaled_coord: list[int]) -> list[int]:
        """
        Convert scaled coordinates back to real screen coordinates.

        Args:
            scaled_coord: [x, y] in scaled image space

        Returns:
            [x, y] in real screen space
        """
        if self.original_width is None or self.scaled_width is None:
            return scaled_coord

        scaled_x, scaled_y = scaled_coord
        real_x = int(scaled_x * self.original_width / self.scaled_width)
        real_y = int(scaled_y * self.original_height / self.scaled_height)

        return [real_x, real_y]

    def _call_api(self, data: dict[str, Any]) -> dict[str, Any]:
        """Call Claude API with retry logic."""
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "interleaved-thinking-2025-05-14"
        }

        url = f"{self.config.base_url}/messages"

        response = requests.post(
            url=url,
            headers=headers,
            json=data,
            timeout=120
        )

        response.raise_for_status()
        return response.json()

    def _parse_tool_use(self, tool_block: dict[str, Any]) -> dict[str, Any]:
        """
        Parse tool use and convert coordinates to real screen space.

        Args:
            tool_block: Tool use block from API response

        Returns:
            Parsed tool with real coordinates
        """
        tool_name = tool_block.get("name")
        tool_input = tool_block.get("input", {})

        # Convert coordinates for coordinate-based tools
        if tool_name in ["Tap", "LongPress", "DoubleClick"]:
            if "coordinate" in tool_input:
                scaled_coord = tool_input["coordinate"]
                real_coord = self.scale_coordinate_to_real(scaled_coord)
                tool_input["coordinate"] = real_coord

        elif tool_name == "Swipe":
            if "start_coordinate" in tool_input:
                tool_input["start_coordinate"] = self.scale_coordinate_to_real(
                    tool_input["start_coordinate"]
                )
            if "end_coordinate" in tool_input:
                tool_input["end_coordinate"] = self.scale_coordinate_to_real(
                    tool_input["end_coordinate"]
                )

        return {
            "name": tool_name,
            "input": tool_input,
            "id": tool_block.get("id")
        }


class ClaudeMessageBuilder:
    """Helper for building Claude-format messages."""

    @staticmethod
    def create_user_message_with_image(
        text: str,
        image_base64: str,
        image_width: int,
        image_height: int
    ) -> dict[str, Any]:
        """
        Create user message with text and image.

        Args:
            text: Text content
            image_base64: Base64 encoded image
            image_width: Image width
            image_height: Image height

        Returns:
            Message in Claude format
        """
        return {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": text
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_base64
                    }
                }
            ]
        }

    @staticmethod
    def create_user_message(text: str) -> dict[str, Any]:
        """Create user message with text only."""
        return {
            "role": "user",
            "content": [{"type": "text", "text": text}]
        }

    @staticmethod
    def create_assistant_message(content: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Create assistant message.

        Args:
            content: List of content blocks (thinking, text, tool_use)

        Returns:
            Assistant message
        """
        return {
            "role": "assistant",
            "content": content
        }

    @staticmethod
    def create_tool_result(
        tool_use_id: str,
        result_text: str,
        image_base64: str | None = None,
        image_width: int | None = None,
        image_height: int | None = None
    ) -> dict[str, Any]:
        """
        Create tool result message.

        Args:
            tool_use_id: ID of the tool use
            result_text: Result text
            image_base64: Optional screenshot
            image_width: Optional image width
            image_height: Optional image height

        Returns:
            User message with tool_result
        """
        content = [{"type": "text", "text": result_text}]

        if image_base64:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_base64
                }
            })

        return {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content
            }]
        }

    @staticmethod
    def remove_images_from_message(message: dict[str, Any]) -> dict[str, Any]:
        """Remove images from message to save context space."""
        if "content" in message and isinstance(message["content"], list):
            new_content = []
            for item in message["content"]:
                if isinstance(item, dict):
                    if item.get("type") == "image":
                        continue  # Skip images
                    elif item.get("type") == "tool_result":
                        # Remove images from tool_result content
                        tool_content = item.get("content", [])
                        if isinstance(tool_content, list):
                            item["content"] = [
                                c for c in tool_content
                                if c.get("type") != "image"
                            ]
                    new_content.append(item)
            message["content"] = new_content

        return message
