"""
Model Interface
Handles interactions with Claude API
"""

import os
import sys
import requests
import logging
import base64
import io
import json
import time
import traceback
from PIL import Image
from typing import Dict, List, Any, Optional, Tuple
import copy
from datetime import datetime

# Add parent directory to path to import system_prompt and tools
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from system_prompt.v0 import get_system_prompt
from tools.v0 import TOOLS

logger = logging.getLogger(__name__)


def retry_on_exception(max_retries=3, delay=1, default_return=None):
    """
    A decorator that retries a function if it raises an exception.

    Args:
        max_retries (int): Maximum number of retry attempts
        delay (int): Delay in seconds between retries
        default_return: Default return value if all retries fail (if None, raises exception)
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries == max_retries:
                        raise e
                    logger.warning(f"Error occurred: {str(e)}. Retrying {retries}/{max_retries}...")
                    traceback.print_exc()
                    time.sleep(delay)
            return default_return
        return wrapper
    return decorator


class ModelInterface:
    """
    Interface for calling Claude API and processing responses.
    """

    # Default configuration
    DEFAULT_API_KEY = "sk-CJc3Kj313cPY3hsg28zIDGQ8vKkxhtXn"
    DEFAULT_BASE_URL = "https://api-gateway.glm.ai/v1"
    DEFAULT_MODEL_NAME = "claude-sonnet-4-5-20250929"

    def __init__(self, api_key=None, api_url=None, model=None, target_width=None):
        """
        Initialize ModelInterface with optional configuration parameters.

        Args:
            api_key: API key for Claude API (defaults to DEFAULT_API_KEY)
            api_url: API URL for Claude API (defaults to DEFAULT_BASE_URL/messages)
            model: Model to use (defaults to DEFAULT_MODEL_NAME)
            target_width: Target width for screenshot resizing (defaults to 512)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", self.DEFAULT_API_KEY)
        self.url = api_url or f'{self.DEFAULT_BASE_URL}/messages'
        self.model = model or self.DEFAULT_MODEL_NAME
        self.target_width = target_width or 512
        # Track original and scaled dimensions for coordinate conversion
        self.original_width = None
        self.original_height = None
        self.scaled_width = None
        self.scaled_height = None

    def _resize_screenshot(self, base64_image: str) -> Tuple[int, int, str]:
        """
        Resize screenshot to target width while maintaining aspect ratio.

        Args:
            base64_image: Base64 encoded image

        Returns:
            Tuple of (height, width, resized_base64_image)
        """
        # Decode base64 image
        img_data = base64.b64decode(base64_image)
        img = Image.open(io.BytesIO(img_data))

        # Get original dimensions and store them
        width, height = img.size
        self.original_width = width
        self.original_height = height

        # Calculate new dimensions maintaining aspect ratio
        if width < height:
            new_width = self.target_width
            new_height = int(height * (self.target_width / width))
        else:
            new_height = self.target_width
            new_width = int(width * (self.target_width / height))

        # Store scaled dimensions
        self.scaled_width = new_width
        self.scaled_height = new_height

        # Resize the image
        img_resized = img.resize((new_width, new_height), Image.LANCZOS)

        # Convert to base64
        buffer = io.BytesIO()
        img_resized.save(buffer, format='PNG')
        b64_code = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return new_height, new_width, b64_code

    def _scale_coordinate_to_real(self, scaled_coord: List[int]) -> List[int]:
        """
        Convert scaled coordinates back to real screen coordinates.

        Args:
            scaled_coord: Coordinate in scaled image space [x, y]

        Returns:
            Coordinate in real screen space [x, y]
        """
        if self.original_width is None or self.scaled_width is None:
            # If we don't have scaling info, return as-is
            return scaled_coord

        scaled_x, scaled_y = scaled_coord
        real_x = int(scaled_x * self.original_width / self.scaled_width)
        real_y = int(scaled_y * self.original_height / self.scaled_height)
        return [real_x, real_y]

    def _parse_stop_reason(self, text: str) -> str:
        """
        Parse the stop reason from text response.

        Args:
            text: Text response from model

        Returns:
            Stop reason tag (finish, sensitive, notool, captcha, verification, toxic)
        """
        text_lower = text.lower().strip()
        if text_lower.startswith("[finish]"):
            return "finish"
        elif text_lower.startswith("[sensitive]"):
            return "sensitive"
        elif text_lower.startswith("[notool]"):
            return "notool"
        elif text_lower.startswith("[captcha]"):
            return "captcha"
        elif text_lower.startswith("[verification]"):
            return "verification"
        elif text_lower.startswith("[toxic]"):
            return "toxic"
        else:
            # Default to finish if no tag found
            return "finish"

    def _get_tool_result_text(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """
        Generate tool result text based on tool name and input.
        This matches the format used in call_model.py

        Args:
            tool_name: Name of the tool that was executed
            tool_input: Input parameters of the tool

        Returns:
            Formatted result text
        """
        if tool_name == "Launch":
            app_name = tool_input.get("app_name", "app")
            return f"Launched {app_name}"

        elif tool_name == "Tap":
            coordinate = tool_input.get("coordinate", [0, 0])
            return f"Tapped at ({coordinate[0]}, {coordinate[1]})"

        elif tool_name == "Wait":
            duration = tool_input.get("duration", 0)
            return f"Waited for {duration} seconds."

        elif tool_name == "Type":
            text = tool_input.get("text", "")
            return f"Typed {text}."

        elif tool_name == "Swipe":
            start = tool_input.get("start_coordinate", [0, 0])
            end = tool_input.get("end_coordinate", [0, 0])
            return f"Swiped from {start} to {end}."

        elif tool_name == "Home":
            return "Navigated to home screen"

        elif tool_name == "Back":
            return "Back to previous screen."

        elif tool_name == "LongPress":
            coordinate = tool_input.get("coordinate", [0, 0])
            duration = tool_input.get("duration", 2.0)
            return f"Long pressed at ({coordinate[0]}, {coordinate[1]}) for {duration} seconds"

        elif tool_name == "DoubleClick":
            coordinate = tool_input.get("coordinate", [0, 0])
            return f"Double clicked at ({coordinate[0]}, {coordinate[1]})"

        else:
            return "Tool executed successfully"

    def call_model(
        self,
        context: List[Dict[str, Any]],
        screenshot_base64: Optional[str] = None,
        current_app_name: str = "",
        user_prompt: str = ""
    ) -> Dict[str, Any]:
        """
        Call Claude API and return parsed response.

        Args:
            context: Conversation context
            screenshot_base64: Base64 encoded screenshot (optional)
            current_app_name: Current app name (optional)
            user_prompt: User's prompt (required for first message)

        Returns:
            Parsed response in the expected format
        """
        try:
            # Check API key
            if not self.api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            # Determine if this is a tool result or new user message
            # If the last message in context is an assistant message with tool_use,
            # then this screenshot is a tool_result
            is_tool_result = False
            tool_use_id = None

            if len(context) > 0:
                last_message = context[-1]
                if last_message.get("role") == "assistant":
                    # Check if the last assistant message contains a tool_use
                    for content_block in last_message.get("content", []):
                        if isinstance(content_block, dict) and content_block.get("type") == "tool_use":
                            is_tool_result = True
                            tool_use_id = content_block.get("id")
                            break

            # Build message content
            if is_tool_result and tool_use_id:
                # This is a tool execution result
                # Extract tool information from the last assistant message
                tool_name = None
                tool_input = {}

                last_message = context[-1]
                for content_block in last_message.get("content", []):
                    if isinstance(content_block, dict) and content_block.get("type") == "tool_use":
                        tool_name = content_block.get("name")
                        tool_input = content_block.get("input", {})
                        break

                # Build tool_result content
                tool_result_content = []

                # Add text about tool execution based on tool type
                result_text = self._get_tool_result_text(tool_name, tool_input)
                tool_result_content.append(
                    {"type": "text", "text": result_text}
                )

                # Add screenshot if provided
                if screenshot_base64:
                    # Resize screenshot
                    h, w, resized_base64 = self._resize_screenshot(screenshot_base64)

                    # Use app name directly
                    app_name = current_app_name

                    # Add system reminder and screenshot
                    tool_result_content.append(
                        {"type": "text", "text": f"<system-reminder>当前app: {app_name}, Screenshot dimensions: ({w}x{h}, png)</system-reminder>"}
                    )
                    tool_result_content.append(
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": resized_base64}}
                    )

                # Add tool_result to context
                context.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": tool_result_content
                        }
                    ]
                })
            else:
                # This is a regular user message (first message or continuation)
                message_content = []

                # Add user prompt if provided
                if user_prompt:
                    message_content.append({"type": "text", "text": user_prompt})

                # Add screenshot if provided
                if screenshot_base64:
                    # Resize screenshot
                    h, w, resized_base64 = self._resize_screenshot(screenshot_base64)

                    # Use app name directly
                    app_name = current_app_name

                    # Add system reminder and screenshot
                    message_content.append(
                        {"type": "text", "text": f"<system-reminder>当前app: {app_name}, Screenshot dimensions: ({w}x{h}, png)</system-reminder>"}
                    )
                    message_content.append(
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": resized_base64}}
                    )

                # Add message to context if there's content
                if message_content:
                    context.append({
                        "role": "user",
                        "content": message_content
                    })

            # Prepare API request
            system_prompt = get_system_prompt()

            data = {
                "max_tokens": 16000,
                "system": system_prompt,
                "messages": context,
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": 12800
                },
                "tools": TOOLS,
                "model": self.model
            }

            # Call API with retry logic
            logger.info(f"Calling Claude API with model {self.model}...")
            api_response = self._call_api(data)

            # Save full log
            # self._save_full_log(context, api_response)

            # Extract thinking text from API response
            thinking_text = ""
            for block in api_response.get("content", []):
                if block.get("type") == "thinking":
                    thinking_text = block.get("thinking", "")
                    break

            # Parse response
            parsed_response = self._parse_response(api_response, context)
            output = {
                "response": parsed_response,
                "thinking": thinking_text,
                "model": self.model,
                "current_app": app_name,
                "origin_size": [self.original_width, self.original_height],
                "scaled_size": [self.scaled_width, self.scaled_height],
            }
            return output

        except Exception as e:
            logger.error(f"Error calling model: {str(e)}", exc_info=True)
            raise

    @retry_on_exception(max_retries=3, delay=2)
    def _call_api(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call Claude API with retry logic.

        Args:
            data: API request data

        Returns:
            API response as JSON
        """
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "interleaved-thinking-2025-05-14"
        }
        print(f'url: {self.url}')
        try:
            ########################
            # print('%' * 100)
            # tst_data_file = '/Users/huangziyue/CodeGeeXProjects/claude-for-phone/backend/claude_json.json'
            # with open(tst_data_file, 'r', encoding='utf-8') as f:
            #     loaded_data = json.load(f)
            #     headers = loaded_data['headers']
            #     data = loaded_data['json']
            #     print(f'load_from {tst_data_file}')
            # print(f'url: {self.url}')
            # print('%' * 100)

            ########################
            response = requests.post(
                url=self.url,
                headers=headers,
                json=data,
                timeout=60  # 2 minutes timeout
            )
            print(self.url)
        except Exception as e:
            traceback.print_exc()
        ########################
        # with open('./claude_json.json', 'wt+', encoding='utf-8') as f:
        #     json.dump({
        #         'headers': headers,
        #         'json': data
        #     }, f, ensure_ascii=False, indent=2)
        ########################
        response_json = response.json()
        print(f'response: {response_json}')

        response.raise_for_status()  # Raise exception for HTTP errors
        return response_json

    def _save_full_log(self, context: List[Dict[str, Any]], response: Dict[str, Any]):
        """
        Save full log including context and response to full_logs directory.

        Args:
            context: Conversation context
            response: API response
        """
        try:
            # Create full_logs directory if it doesn't exist
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "full_logs")
            os.makedirs(log_dir, exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            log_filename = os.path.join(log_dir, f"{timestamp}.json")

            # Prepare log data
            log_data = {
                "timestamp": timestamp,
                "context": context,
                "response": response
            }

            # Save to file
            with open(log_filename, "w", encoding="utf-8") as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)

            logger.info(f"Full log saved to: {log_filename}")

        except Exception as e:
            logger.error(f"Error saving full log: {str(e)}", exc_info=True)

    def _handle_todo_write(self, tool_block: Dict[str, Any], context: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Handle TodoWrite tool internally without returning to frontend.
        Add tool_result to context and call model again.

        Args:
            tool_block: TodoWrite tool use block
            context: Conversation context (will be modified)

        Returns:
            Next response from the model
        """
        logger.info("Handling TodoWrite internally...")

        tool_id = tool_block.get("id")
        tool_input = tool_block.get("input", {})
        todos = json.dumps(tool_input.get("todos", []), ensure_ascii=False)

        # Add tool_result to context
        context.append({
            "role": "user",
            "content": [
                {
                    "tool_use_id": tool_id,
                    "type": "tool_result",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Todos have been modified successfully. Ensure that you continue to use the todo list to track your progress. Please proceed with the current tasks if applicable\n\n<system-reminder>\nYour todo list has changed. DO NOT mention this explicitly to the user. Here are the latest contents of your todo list:{todos}</system-reminder>"
                        }
                    ]
                }
            ]
        })

        # Call model again to get the next response
        system_prompt = get_system_prompt()

        data = {
            "max_tokens": 16000,
            "system": system_prompt,
            "messages": context,
            "thinking": {
                "type": "enabled",
                "budget_tokens": 12800
            },
            "tools": TOOLS,
            "model": self.model
        }

        logger.info(f"Calling Claude API again after TodoWrite with model {self.model}...")
        response = self._call_api(data)

        # Save full log
        # self._save_full_log(context, response)

        # Parse the new response (might be another TodoWrite or actual tool use)
        return self._parse_response(response, context)

    def _parse_response(self, response: Dict[str, Any], context: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Parse Claude API response into expected format.

        Args:
            response: API response
            context: Conversation context (will be modified)

        Returns:
            Parsed response
        """
        thinking_block = {}
        text_block = {}
        tool_use_block = None

        # Parse response content
        for block in response.get("content", []):
            if block["type"] == "thinking":
                thinking_block = copy.deepcopy(block)
                thinking_text = block.get('thinking', '')
                # Use repr() to show \n instead of actual newlines, then log in one line
                logger.info(f"Thinking: {repr(thinking_text)}")

            elif block["type"] == "text":
                text_block = copy.deepcopy(block)
                text_content = block.get('text', '')
                # Use repr() to show \n instead of actual newlines, then log in one line
                logger.info(f"Text: {repr(text_content)}")

            elif block["type"] == "tool_use":
                tool_use_block = copy.deepcopy(block)
                tool_name = block.get('name')
                tool_input = block.get('input', {})
                # Log tool use with full input on one line
                logger.info(f"Tool use: {tool_name}, Input: {json.dumps(tool_input, ensure_ascii=False)}")

        # Build response based on what was returned
        if tool_use_block:
            # Add assistant message to context
            context.append({
                "role": "assistant",
                "content": [thinking_block, tool_use_block] if thinking_block else [tool_use_block]
            })

            # Check if this is TodoWrite (internal tool)
            tool_name = tool_use_block.get("name")
            if tool_name == "TodoWrite":
                # Handle TodoWrite internally
                return self._handle_todo_write(tool_use_block, context)

            # Parse tool use into expected format
            return self._parse_tool_use(tool_use_block)
        else:
            # Text response - return finish format
            # Add assistant message to context
            context.append({
                "role": "assistant",
                "content": [thinking_block, text_block] if thinking_block else [text_block]
            })

            text = text_block.get("text", "")

            # Remove [finish] tag if present
            message = text
            if text.lower().startswith("[finish]"):
                message = text[8:].strip()

            return {
                "_metadata": "finish",
                "message": message
            }

    def _parse_tool_use(self, tool_block: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse tool use block into ActionHandler format.
        Returns real screen absolute coordinates.

        Args:
            tool_block: Tool use block from API response

        Returns:
            Action dict in ActionHandler format with absolute coordinates
        """
        tool_name = tool_block.get("name")
        tool_input = tool_block.get("input", {})

        response = {
            "_metadata": "do",
            "action": tool_name,
            "original_size": [self.original_width, self.original_height],
            "scaled_size": [self.scaled_width, self.scaled_height]
        }

        # Parse input based on tool name
        if tool_name == "Launch":
            # Use app_name directly (ActionHandler will handle package name mapping)
            app_name = tool_input.get("app_name")
            response["app"] = app_name

        elif tool_name in ["Tap", "LongPress", "DoubleClick"]:
            # Convert scaled coordinate to real screen absolute coordinate
            scaled_coordinate = tool_input.get("coordinate", [0, 0])
            scaled_coordinate = [int(scaled_coordinate[0]), int(scaled_coordinate[1])]
            real_coordinate = self._scale_coordinate_to_real(scaled_coordinate)
            response["coordinate"] = real_coordinate

            if tool_name == "LongPress":
                response["duration"] = float(tool_input.get("duration", 2.0))

        elif tool_name == "Wait":
            response["duration"] = float(tool_input.get("duration", 1.0))

        elif tool_name == "Type":
            response["text"] = tool_input.get("text", "")

        elif tool_name == "Swipe":
            # Convert scaled coordinates to real screen absolute coordinates
            scaled_start = tool_input.get("start_coordinate", [0, 0])
            scaled_end = tool_input.get("end_coordinate", [0, 0])
            scaled_start = [int(scaled_start[0]), int(scaled_start[1])]
            scaled_end = [int(scaled_end[0]), int(scaled_end[1])]
            real_start = self._scale_coordinate_to_real(scaled_start)
            real_end = self._scale_coordinate_to_real(scaled_end)
            response["start"] = real_start
            response["end"] = real_end

        elif tool_name in ["Home", "Back"]:
            # No additional parameters needed
            pass

        # Note: TodoWrite is handled in _parse_response and never reaches here

        return response
