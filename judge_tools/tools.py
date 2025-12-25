"""
Phone-Use Agent Tool Definitions v0
Defines all available tools for Android phone automation
迁移自 claude-for-phone 项目的 tools/v0.py
"""

TOOLS = [
    {
        "name": "Tap",
        "description": "Tap on a specific point on the screen. Use this to click buttons, select items, open apps from the home screen, or interact with any tappable UI element. The coordinate system starts from the top-left corner (0,0). After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "coordinate": {
                    "type": "array",
                    "items": {
                        "type": "number"
                    },
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "(x, y): The x (pixels from the left edge) and y (pixels from the top edge) coordinates to tap."
                }
            },
            "required": ["coordinate"]
        }
    },
    {
        "name": "Long Press",
        "description": "Press and hold on a specific point on the screen for a specified duration. Use this to trigger context menus, select text, or activate long-press interactions. The coordinate system starts from the top-left corner (0,0). After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "coordinate": {
                    "type": "array",
                    "items": {
                        "type": "number"
                    },
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "(x, y): The x (pixels from the left edge) and y (pixels from the top edge) coordinates to long press."
                },
                "duration": {
                    "type": "number",
                    "minimum": 0.5,
                    "maximum": 10,
                    "description": "The duration in seconds to hold the press. Typically 2 seconds for most long-press actions. Maximum 10 seconds."
                }
            },
            "required": ["coordinate", "duration"]
        }
    },
    {
        "name": "Double Tap",
        "description": "Tap twice rapidly on a specific point on the screen. Use this to activate double-tap interactions like zooming, selecting text, or opening items. The coordinate system starts from the top-left corner (0,0). After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "coordinate": {
                    "type": "array",
                    "items": {
                        "type": "number"
                    },
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "(x, y): The x (pixels from the left edge) and y (pixels from the top edge) coordinates to double click."
                }
            },
            "required": ["coordinate"]
        }
    },
    {
        "name": "Launch",
        "description": "Directly launch an application using its app name. This is faster than navigating through the home screen. Only the following apps are allowed to be launched. After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app": {
                    "type": "string",
                    "description": "The name of the application to launch. Common apps include: 小红书, 美团, 大众点评, 高德地图, 抖音, 淘宝, 京东, 携程, bilibili, 微博, 快手, 去哪儿, 百度地图, 微信, 飞书, 腾讯视频, QQ音乐, 腾讯新闻, keep, 汽水音乐, 爱奇艺, 芒果TV, 红果短剧, 网易云音乐, 贝壳找房, 安居客, 七猫免费小说, 番茄免费小说, 喜马拉雅, QQ邮箱, 知乎, 拼多多, 饿了么, 淘宝闪购, 京东秒送, 应用宝, 美柚, 今日头条, 滴滴出行, 优酷视频, QQ, 快手极速版, 肯德基, 豆瓣, 同花顺, 支付宝, 豆包, 星穹铁道, 恋与深空, 米游社, 淘宝主播, 小美"
                }
            },
            "required": ["app"]
        }
    },
    {
        "name": "Swipe",
        "description": "Perform a swipe gesture by dragging from start_coordinate to end_coordinate. Use this to scroll through content, navigate between screens, pull down notification shade, or perform gesture-based navigation. The coordinate system starts from the top-left corner (0,0). The swipe duration is automatically adjusted for natural movement. After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_coordinate": {
                    "type": "array",
                    "items": {
                        "type": "number"
                    },
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "(x, y): The starting point. The x (pixels from the left edge) and y (pixels from the top edge) coordinates where the swipe begins."
                },
                "end_coordinate": {
                    "type": "array",
                    "items": {
                        "type": "number"
                    },
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "(x, y): The ending point. The x (pixels from the left edge) and y (pixels from the top edge) coordinates where the swipe ends. The gesture will swipe FROM start_coordinate TO this end_coordinate."
                }
            },
            "required": ["start_coordinate", "end_coordinate"]
        }
    },
    {
        "name": "Back",
        "description": "Navigate back to the previous screen or close the current dialog. Equivalent to pressing the Android back button. Use this to return from a deeper screen, close pop-ups, or exit the current context. After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "Home",
        "description": "Return to the home screen. Equivalent to pressing the Android home button. Use this to exit the current app and return to the launcher, or to start a new task from a known state. After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "Type",
        "description": "Type text into the currently focused input field. Make sure an input field is focused (by tapping on it first) before using this action. The text will be entered as if typed on the keyboard. IMPORTANT: The phone may be using ADB Keyboard which does NOT occupy screen space like a normal keyboard. To verify the keyboard is activated, look for text like 'ADB Keyboard {ON}' at the bottom of the screen, or check if the input field appears active/highlighted. Do NOT rely solely on visual keyboard presence. AUTOMATIC TEXT CLEARING: When you use the Type action, any existing text in the input field (including both placeholder text and real input) will be AUTOMATICALLY cleared before your new text is entered. You do NOT need to manually clear text before typing - just use the Type action directly with your desired text. After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to type into the focused input field."
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "Wait",
        "description": "Wait for a specified duration. Use this to allow time for animations to complete, pages to load, or UI elements to appear. Maximum wait time is 30 seconds. IMPORTANT: There is already a ~2 second delay between actions due to API call processing time. If you need to wait less than 2 seconds, DO NOT use this action - the built-in delay is sufficient. If you need to wait more than 2 seconds, subtract 2 seconds from your desired wait time (e.g., if you need 5 seconds total, use duration=3). After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "duration": {
                    "type": "number",
                    "minimum": 0.5,
                    "maximum": 30,
                    "description": "The number of seconds to wait BEYOND the built-in ~2 second API processing delay. Maximum 30 seconds."
                }
            },
            "required": ["duration"]
        }
    },
    {
        "name": "TodoWrite",
        "description": "Create and manage a structured task list for the current automation session. Use this to track progress, break down complex tasks into steps, and demonstrate thoroughness. Essential for multi-step phone automation tasks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "The imperative form of the task (e.g., 'Launch Instagram', 'Search for user profile')"
                            },
                            "activeForm": {
                                "type": "string",
                                "description": "The present continuous form shown during execution (e.g., 'Launching Instagram', 'Searching for user profile')"
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "Current status of the task"
                            }
                        },
                        "required": ["content", "activeForm", "status"]
                    },
                    "description": "Array of task objects with content, activeForm, and status"
                }
            },
            "required": ["todos"]
        }
    }
]

