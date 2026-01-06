"""
Service module for single-step agent inference.

This module provides a stateless inference service that:
1. Accepts messages list with images
2. Filters to K most recent images
3. Performs model inference
4. Returns action and metadata
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from phone_agent.actions.handler import finish, parse_action
from phone_agent.model import ModelClient, ModelConfig


@dataclass
class InferenceConfig:
    """Configuration for inference service."""

    k_images: int = 1  # Number of recent images to keep
    verbose: bool = True
    lang: str = "cn"


@dataclass
class InferenceResult:
    """Result from a single inference step."""

    # Core outputs
    action: dict[str, Any]  # Parsed action dict with _metadata
    raw_action: dict# raw action
    thinking: str  # Model's reasoning process
    raw_response: str  # Raw model output

    # Metadata
    is_finish: bool  # Whether this is a finish action
    message: str | None = None  # Message from finish action

    # Performance metrics
    time_to_first_token: float | None = None
    time_to_thinking_end: float | None = None
    total_time: float | None = None


class AgentService:
    """
    Stateless inference service for agent actions.

    Performs single-step inference without maintaining state.
    Expects messages to already contain base64 images.
    Filters to K most recent images before sending to model.

    Args:
        model_config: Configuration for the model client
        inference_config: Configuration for inference behavior

    Example:
        >>> service = AgentService(model_config, InferenceConfig(k_images=3))
        >>> messages = [...]  # Messages with base64 images
        >>> result = service.inference(messages)
        >>> print(result.action, result.thinking)
    """

    def __init__(
        self,
        model_config: ModelConfig,
        inference_config: InferenceConfig | None = None,
    ):
        self.model_config = model_config
        self.inference_config = inference_config or InferenceConfig()
        self.model_client = ModelClient(model_config)

    def inference(self, messages: list[dict[str, Any]]) -> InferenceResult:
        """
        Perform single-step inference.

        Args:
            messages: Full conversation history with base64 images

        Returns:
            InferenceResult with action, thinking, and metadata

        Raises:
            ValueError: If model output cannot be parsed
        """
        # Filter to K most recent images
        filtered_messages = self._filter_k_images(
            messages, self.inference_config.k_images
        )

        # Call model
        response = self.model_client.request(filtered_messages)

        # Parse action
        try:
            action = parse_action(response.action)
        except ValueError:
            # Fallback to finish if parsing fails
            action = finish(message=response.action)

        # Determine if this is a finish action
        is_finish = action.get("_metadata") == "finish"
        message = action.get("message") if is_finish else None

        return InferenceResult(
            action=action,
            raw_action=response.action,
            thinking=response.thinking,
            raw_response=response.raw_content,
            is_finish=is_finish,
            message=message,
            time_to_first_token=response.time_to_first_token,
            time_to_thinking_end=response.time_to_thinking_end,
            total_time=response.total_time,
        )

    def _filter_k_images(
        self, messages: list[dict[str, Any]], k: int
    ) -> list[dict[str, Any]]:
        """
        Filter messages to keep only K most recent images.

        Algorithm:
        1. Iterate messages in REVERSE order (newest first)
        2. Count images encountered
        3. Keep first K images, remove rest
        4. Preserve all text content

        Args:
            messages: Original messages list
            k: Number of images to keep (0 = remove all, -1 = keep all)

        Returns:
            New messages list with filtered images
        """
        if k < 0:  # -1 means keep all images
            return messages

        # Deep copy to avoid modifying original
        filtered = deepcopy(messages)

        # Track images seen (counting backwards)
        images_seen = 0

        # Iterate in reverse to find K most recent images
        for i in range(len(filtered) - 1, -1, -1):
            msg = filtered[i]

            # Only process user messages with content lists
            if msg.get("role") != "user":
                continue

            content = msg.get("content")
            if not isinstance(content, list):
                continue

            # Filter content items
            new_content = []
            for item in content:
                if item.get("type") == "image_url":
                    images_seen += 1
                    if images_seen <= k:
                        # Keep this image (it's in the K most recent)
                        new_content.append(item)
                    # else: skip this image (beyond K limit)
                else:
                    # Always keep non-image content (text)
                    new_content.append(item)

            filtered[i]["content"] = new_content

        return filtered
