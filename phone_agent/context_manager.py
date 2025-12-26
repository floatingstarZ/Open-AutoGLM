"""
Context Manager for conversation management
Handles context engineering and image management
"""

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ContextManager:
    """
    Manages conversation context with automatic image management.

    Features:
    - Automatic removal of oldest images when limit exceeded
    - Deep copy to avoid side effects
    """

    def __init__(self, max_images: int = 30):
        """
        Initialize context manager.

        Args:
            max_images: Maximum number of images to keep in context
        """
        self.max_images = max_images

    def apply_context_engineering(
        self, context: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Apply context engineering to manage image count.

        If there are more than max_images images, removes the oldest one.

        Args:
            context: The conversation context

        Returns:
            Engineered context with managed image count
        """
        # Count total images in context
        image_count = 0
        image_positions = []  # Store (msg_idx, content_idx, nested_idx) for each image

        for msg_idx, message in enumerate(context):
            if "content" in message and isinstance(message["content"], list):
                for content_idx, item in enumerate(message["content"]):
                    # Check direct images (user messages with screenshots)
                    if isinstance(item, dict) and item.get("type") == "image":
                        image_count += 1
                        image_positions.append((msg_idx, content_idx, None))

                    # Check image_url type (OpenAI format)
                    elif isinstance(item, dict) and item.get("type") == "image_url":
                        image_count += 1
                        image_positions.append((msg_idx, content_idx, None))

                    # Check images inside tool_result content (Claude format)
                    elif isinstance(item, dict) and item.get("type") == "tool_result":
                        tool_content = item.get("content", [])
                        if isinstance(tool_content, list):
                            for nested_idx, nested_item in enumerate(tool_content):
                                if isinstance(nested_item, dict) and nested_item.get("type") == "image":
                                    image_count += 1
                                    image_positions.append((msg_idx, content_idx, nested_idx))

        # If more than max_images, remove the oldest one
        if image_count > self.max_images:
            # Get the position of the oldest image (first in the list)
            oldest_msg_idx, oldest_content_idx, oldest_nested_idx = image_positions[0]

            # Make a deep copy to avoid modifying the original
            context = copy.deepcopy(context)

            if oldest_nested_idx is not None:
                # Image is inside a tool_result content array
                tool_result = context[oldest_msg_idx]["content"][oldest_content_idx]
                tool_content = tool_result["content"]

                # Remove the image
                del tool_content[oldest_nested_idx]

                # Also remove the associated system-reminder if it exists right before the image
                if oldest_nested_idx > 0:
                    prev_item = tool_content[oldest_nested_idx - 1]
                    if (isinstance(prev_item, dict) and
                        prev_item.get("type") == "text" and
                        "Screenshot dimensions:" in prev_item.get("text", "")):
                        # Remove the system-reminder as well
                        del tool_content[oldest_nested_idx - 1]
            else:
                # Image is directly in message content
                del context[oldest_msg_idx]["content"][oldest_content_idx]

                # Check if there's a preceding text with dimension info
                if oldest_content_idx > 0:
                    prev_item = context[oldest_msg_idx]["content"][oldest_content_idx - 1]
                    if (isinstance(prev_item, dict) and
                        prev_item.get("type") == "text" and
                        ("Screenshot dimensions:" in prev_item.get("text", "") or
                         "当前app:" in prev_item.get("text", ""))):
                        del context[oldest_msg_idx]["content"][oldest_content_idx - 1]

            logger.info(f"Context engineering: Removed oldest image. Image count: {image_count} -> {image_count - 1}")

        return context

    def count_images(self, context: list[dict[str, Any]]) -> int:
        """
        Count total images in context.

        Args:
            context: The conversation context

        Returns:
            Number of images
        """
        image_count = 0

        for message in context:
            if "content" in message and isinstance(message["content"], list):
                for item in message["content"]:
                    if isinstance(item, dict):
                        if item.get("type") in ["image", "image_url"]:
                            image_count += 1
                        elif item.get("type") == "tool_result":
                            tool_content = item.get("content", [])
                            if isinstance(tool_content, list):
                                for nested_item in tool_content:
                                    if isinstance(nested_item, dict) and nested_item.get("type") == "image":
                                        image_count += 1

        return image_count
