"""Configuration module for Phone Agent."""

from phone_agent.config.apps import APP_PACKAGES
from phone_agent.config.i18n import get_message, get_messages
from phone_agent.config.prompts import ABSOLUTE_COORD_SYSTEM_PROMPT
from phone_agent.config.prompts_en import SYSTEM_PROMPT as SYSTEM_PROMPT_EN
from phone_agent.config.prompts_zh import SYSTEM_PROMPT as SYSTEM_PROMPT_ZH
from phone_agent.config.timing import (
    TIMING_CONFIG,
    ActionTimingConfig,
    ConnectionTimingConfig,
    DeviceTimingConfig,
    TimingConfig,
    get_timing_config,
    update_timing_config,
)


def get_system_prompt(lang: str = "cn", prompt_type: str = "relative") -> str:
    """
    Get system prompt by language and prompt type.

    Args:
        lang: Language code, 'cn' for Chinese, 'en' for English.
        prompt_type: Prompt type, 'relative' for relative coordinates (0-999),
                    'absolute' for absolute pixel coordinates.

    Returns:
        System prompt string.
    """
    # 目前只有中文版本支持绝对坐标
    if prompt_type == "absolute" and lang == "cn":
        return ABSOLUTE_COORD_SYSTEM_PROMPT
    
    # 默认使用相对坐标
    if lang == "en":
        return SYSTEM_PROMPT_EN
    return SYSTEM_PROMPT_ZH


# Default to Chinese for backward compatibility
SYSTEM_PROMPT = SYSTEM_PROMPT_ZH

__all__ = [
    "APP_PACKAGES",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_ZH",
    "SYSTEM_PROMPT_EN",
    "get_system_prompt",
    "get_messages",
    "get_message",
    "TIMING_CONFIG",
    "TimingConfig",
    "ActionTimingConfig",
    "DeviceTimingConfig",
    "ConnectionTimingConfig",
    "get_timing_config",
    "update_timing_config",
]
