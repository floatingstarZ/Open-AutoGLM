"""System prompt package for phone-use agent"""

from .v0 import (
    get_system_prompt,
    get_system_prompt_as_list,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_LIST
)

__all__ = [
    'get_system_prompt',
    'get_system_prompt_as_list',
    'SYSTEM_PROMPT',
    'SYSTEM_PROMPT_LIST'
]