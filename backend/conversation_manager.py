"""
Conversation Manager
Manages conversation contexts for multiple sessions
"""

import logging
from typing import Dict, List, Any
import copy

logger = logging.getLogger(__name__)


class ConversationManager:
    """
    Manages conversation contexts for multiple concurrent sessions.
    """

    def __init__(self):
        self.contexts: Dict[str, List[Dict[str, Any]]] = {}
        self.max_images_per_context = 30

    def get_or_create_context(self, conversation_id: str) -> List[Dict[str, Any]]:
        """
        Get existing context or create a new one.

        Args:
            conversation_id: Unique identifier for the conversation

        Returns:
            List of conversation messages
        """
        if conversation_id not in self.contexts:
            logger.info(f"Creating new context for conversation: {conversation_id}")
            self.contexts[conversation_id] = []

        return self.contexts[conversation_id]

    def update_context(self, conversation_id: str, context: List[Dict[str, Any]]):
        """
        Update the context for a conversation.

        Args:
            conversation_id: Unique identifier for the conversation
            context: Updated conversation context
        """
        # Apply context engineering before saving
        engineered_context = self._context_engineering(context)
        self.contexts[conversation_id] = engineered_context
        logger.debug(f"Updated context for conversation: {conversation_id}")

    def delete_context(self, conversation_id: str):
        """
        Delete a conversation context.

        Args:
            conversation_id: Unique identifier for the conversation
        """
        if conversation_id in self.contexts:
            del self.contexts[conversation_id]
            logger.info(f"Deleted context for conversation: {conversation_id}")

    def count_user_messages(self, context: List[Dict[str, Any]]) -> int:
        """
        Count the number of user messages in the context (excluding tool_result messages).

        Args:
            context: Conversation context

        Returns:
            Number of user messages
        """
        count = 0
        for message in context:
            if message.get("role") == "user":
                # Check if this is a regular user message (not a tool_result)
                count += 1
        return count

    def sync_context_with_step(self, conversation_id: str, context: List[Dict[str, Any]], client_step: int) -> List[Dict[str, Any]]:
        """
        Synchronize context with client's step count.
        If client_step < current context user message count, truncate context to match client_step.

        Args:
            conversation_id: Unique identifier for the conversation
            context: Current conversation context
            client_step: Expected number of user messages from client (excluding current round)

        Returns:
            Synchronized context
        """
        current_user_count = self.count_user_messages(context)

        if client_step < current_user_count:
            # Client is behind, need to truncate context
            logger.warning(f"Client step ({client_step}) < server user count ({current_user_count}). Truncating context.")

            truncated_context = []
            user_message_count = 0

            for message in context:
                if message.get("role") == "user":
                    # This is a regular user message
                    if user_message_count < client_step:
                        truncated_context.append(message)
                        user_message_count += 1
                    else:
                        # Reached client_step, stop including user messages
                        break
                else:
                    # Include assistant messages that come before we hit the limit
                    if user_message_count <= client_step:
                        truncated_context.append(message)

            # Update the stored context
            self.contexts[conversation_id] = truncated_context
            logger.info(f"Context truncated: {len(context)} -> {len(truncated_context)} messages, user messages: {current_user_count} -> {client_step}")
            return truncated_context

        elif client_step > current_user_count:
            # Client is ahead - this shouldn't happen normally
            logger.warning(f"Client step ({client_step}) > server user count ({current_user_count}). Using current context.")
            return context
        else:
            # Client and server are in sync
            logger.info(f"Client and server in sync (step={client_step})")
            return context

    def _context_engineering(self, context: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Context engineering to manage image count.
        If there are more than max_images_per_context images, remove the oldest one.

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

                    # Check images inside tool_result content
                    elif isinstance(item, dict) and item.get("type") == "tool_result":
                        tool_content = item.get("content", [])
                        if isinstance(tool_content, list):
                            for nested_idx, nested_item in enumerate(tool_content):
                                if isinstance(nested_item, dict) and nested_item.get("type") == "image":
                                    image_count += 1
                                    image_positions.append((msg_idx, content_idx, nested_idx))

        # If more than max_images_per_context images, remove the oldest one
        if image_count > self.max_images_per_context:
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

                if oldest_content_idx > 0:
                    prev_item = context[oldest_msg_idx]["content"][oldest_content_idx - 1]
                    if (isinstance(prev_item, dict) and
                        prev_item.get("type") == "text" and
                        "Screenshot dimensions:" in prev_item.get("text", "")):
                        del context[oldest_msg_idx]["content"][oldest_content_idx - 1]

            logger.info(f"Context engineering: Removed oldest image. Image count: {image_count} -> {image_count - 1}")

        return context
