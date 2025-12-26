"""
Claude Tools Definition for Phone Automation
Adapted from claude-for-phone tools/v0.py
"""

CLAUDE_TOOLS = [
    {
        "name": "Tap",
        "description": "Tap on a specific point on the screen. Use this to click buttons, select items, open apps from the home screen, or interact with any tappable UI element. The coordinate system starts from the top-left corner (0,0). After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "coordinate": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "(x, y): The x (pixels from the left edge) and y (pixels from the top edge) coordinates to tap."
                }
            },
            "required": ["coordinate"]
        }
    },
    {
        "name": "LongPress",
        "description": "Press and hold on a specific point on the screen for a specified duration. Use this to trigger context menus, select text, or activate long-press interactions. The coordinate system starts from the top-left corner (0,0). After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "coordinate": {
                    "type": "array",
                    "items": {"type": "number"},
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
        "name": "DoubleClick",
        "description": "Tap twice rapidly on a specific point on the screen. Use this to activate double-tap interactions like zooming, selecting text, or opening items. The coordinate system starts from the top-left corner (0,0). After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "coordinate": {
                    "type": "array",
                    "items": {"type": "number"},
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
        "description": "Directly launch an application using its app name. This is faster than navigating through the home screen. Only the following apps are allowed. After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "enum": [
                        "小红书", "美团", "大众点评", "高德地图", "抖音", "淘宝", "京东", "携程",
                        "bilibili", "微博", "快手", "去哪儿", "百度地图", "微信", "飞书",
                        "腾讯视频", "QQ音乐", "腾讯新闻", "keep", "汽水音乐", "爱奇艺", "芒果TV",
                        "红果短剧", "网易云音乐", "贝壳找房", "安居客", "七猫免费小说", "番茄免费小说",
                        "喜马拉雅", "QQ邮箱", "知乎", "拼多多", "饿了么", "淘宝闪购", "京东秒送",
                        "应用宝", "美柚", "今日头条", "滴滴出行", "优酷视频", "QQ", "快手极速版",
                        "肯德基", "豆瓣", "同花顺", "支付宝", "豆包", "星穹铁道", "恋与深空"
                    ],
                    "description": "The name of the application to launch."
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "Swipe",
        "description": "Perform a swipe gesture by dragging from start_coordinate to end_coordinate. Use this to scroll through content, navigate between screens, pull down notification shade, or perform gesture-based navigation. The coordinate system starts from the top-left corner (0,0). After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_coordinate": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "(x, y): The starting point where the swipe begins."
                },
                "end_coordinate": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "(x, y): The ending point where the swipe ends."
                }
            },
            "required": ["start_coordinate", "end_coordinate"]
        }
    },
    {
        "name": "Back",
        "description": "Navigate back to the previous screen or close the current dialog. Equivalent to pressing the Android back button. After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "Home",
        "description": "Return to the home screen. Equivalent to pressing the Android home button. After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "Type",
        "description": "Type text into the currently focused input field. IMPORTANT: The text box is AUTOMATICALLY cleared before your text is entered. Do NOT manually clear text. After this action completes, you will automatically receive a screenshot of the resulting state.",
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
        "description": "Wait for a specified duration. Use this to allow time for animations to complete, pages to load, or UI elements to appear. Maximum 30 seconds. IMPORTANT: There is already ~2 second delay between actions. If you need less than 2 seconds, DO NOT use this. After this action completes, you will automatically receive a screenshot of the resulting state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "duration": {
                    "type": "number",
                    "minimum": 0.5,
                    "maximum": 30,
                    "description": "The number of seconds to wait BEYOND the built-in ~2 second delay."
                }
            },
            "required": ["duration"]
        }
    },
    {
        "name": "TodoWrite",
        "description": "Create and manage a task list for the automation session. Use this to track progress and break down complex tasks.",
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
                                "description": "Imperative form of the task (e.g., 'Launch Instagram')"
                            },
                            "activeForm": {
                                "type": "string",
                                "description": "Present continuous form (e.g., 'Launching Instagram')"
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "Current status"
                            }
                        },
                        "required": ["content", "activeForm", "status"]
                    }
                }
            },
            "required": ["todos"]
        }
    }
]

# App name to package name mapping
APP_NAME_TO_PACKAGE = {
    "微信": "com.tencent.mm",
    "小红书": "com.xingin.xhs",
    "淘宝": "com.taobao.taobao",
    "高德地图": "com.autonavi.minimap",
    "美团": "com.sankuai.meituan",
    "大众点评": "com.dianping.v1",
    "携程": "ctrip.android.view",
    "铁路12306": "com.MobileTicket",
    "京东": "com.jingdong.app.mall",
    "饿了么": "me.ele",
    "拼多多": "com.xunmeng.pinduoduo",
    "去哪儿": "com.Qunar",
    "百度地图": "com.baidu.BaiduMap",
    "滴滴出行": "com.sdu.didi.psnger",
    "微博": "com.sina.weibo",
    "bilibili": "tv.danmaku.bili",
    "抖音": "com.ss.android.ugc.aweme",
    "肯德基": "com.yek.android.kfc.activitys",
    "网易云音乐": "com.netease.cloudmusic",
    "快手": "com.smile.gifmaker",
    "番茄小说": "com.dragon.read",
    "喜马拉雅": "com.ximalaya.ting.android",
    "飞书": "com.ss.android.lark",
    "豆包": "com.larus.nova",
    "腾讯视频": "com.tencent.qqlive",
    "keep": "com.gotokeep.keep",
    "爱奇艺": "com.qiyi.video",
    "QQ音乐": "com.tencent.qqmusic",
    "腾讯新闻": "com.tencent.news",
    "汽水音乐": "com.luna.music",
    "芒果TV": "com.hunantv.imgo.activity",
    "贝壳找房": "com.lianjia.beike",
    "安居客": "com.anjuke.android.app",
    "七猫免费小说": "com.kmxs.reader",
    "番茄免费小说": "com.dragon.read",
    "QQ邮箱": "com.tencent.androidqqmail",
    "知乎": "com.zhihu.android",
    "美柚": "com.lingan.seeyou",
    "今日头条": "com.ss.android.article.news",
    "优酷视频": "com.youku.phone",
    "QQ": "com.tencent.mobileqq",
    "同花顺": "com.hexin.plat.android",
    "豆瓣": "com.douban.frodo",
    "红果短剧": "com.phoenix.read",
    "星穹铁道": "com.miHoYo.hkrpg",
    "恋与深空": "com.papegames.lysk.cn"
}
