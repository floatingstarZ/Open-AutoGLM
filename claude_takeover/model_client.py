"""
Model Client for Claude API

Direct client for calling Claude API without backend server dependency.
Simplified version with local logging only.
"""

import os
import json
import time
import base64
import logging
from io import BytesIO
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from PIL import Image
import requests
import traceback
from claude_takeover.system_prompt import get_system_prompt
from claude_takeover.tools import TOOLS

logger = logging.getLogger(__name__)


class ModelClient:
    """
    Direct client for calling Claude API.

    Handles:
    - API communication with Claude
    - Image resizing and coordinate scaling
    - Context management
    - Local trace logging
    """

    # Default configuration
    DEFAULT_API_KEY = "sk-CJc3Kj313cPY3hsg28zIDGQ8vKkxhtXn"
    DEFAULT_BASE_URL = "https://api-gateway.glm.ai/v1"
    DEFAULT_MODEL_NAME = "claude-sonnet-4-5-20250929"

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

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
        target_width: int = 512,
        trace_dir: Optional[str] = None
    ):
        """
        Initialize Model Client.

        Args:
            api_key: Claude API key (defaults to env var or DEFAULT_API_KEY)
            api_url: Claude API URL (defaults to DEFAULT_BASE_URL/messages)
            model: Model name (defaults to DEFAULT_MODEL_NAME)
            target_width: Target width for image resizing (default: 512)
            trace_dir: Directory to save traces (default: traces/)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", self.DEFAULT_API_KEY)
        self.url = api_url or f'{self.DEFAULT_BASE_URL}/messages'
        self.model = model or self.DEFAULT_MODEL_NAME
        self.target_width = target_width
        self.trace_dir = trace_dir or "traces"

        # Coordinate scaling tracking
        self.original_width = None
        self.original_height = None
        self.scaled_width = None
        self.scaled_height = None

        # Create trace directory
        os.makedirs(self.trace_dir, exist_ok=True)

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
        img = Image.open(BytesIO(img_data))

        # Get original dimensions
        width, height = img.size
        self.original_width = width
        self.original_height = height

        # Calculate new dimensions
        if width < height:
            new_width = self.target_width
            new_height = int(height * (self.target_width / width))
        else:
            new_height = self.target_width
            new_width = int(width * (self.target_width / height))

        self.scaled_width = new_width
        self.scaled_height = new_height

        # Resize
        img_resized = img.resize((new_width, new_height), Image.LANCZOS)

        # Convert to base64
        buffer = BytesIO()
        img_resized.save(buffer, format='PNG')
        b64_code = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return new_height, new_width, b64_code

    def _scale_coordinate_to_real(self, scaled_coord: List[int]) -> List[int]:
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

    def _get_app_name_from_package(self, package_name: str) -> str:
        """Get app name from package name."""
        for app_name, pkg in self.APP_NAME_TO_PACKAGE.items():
            if pkg in package_name:
                return app_name
        return "系统桌面"

    def _get_tool_result_text(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Generate tool result text."""
        if tool_name == "Launch":
            app_name = tool_input.get("app_name", "app")
            return f"Launched {app_name}"
        elif tool_name == "Tap":
            coord = tool_input.get("coordinate", [0, 0])
            return f"Tapped at ({coord[0]}, {coord[1]})"
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
            coord = tool_input.get("coordinate", [0, 0])
            duration = tool_input.get("duration", 2.0)
            return f"Long pressed at ({coord[0]}, {coord[1]}) for {duration} seconds"
        elif tool_name == "DoubleClick":
            coord = tool_input.get("coordinate", [0, 0])
            return f"Double clicked at ({coord[0]}, {coord[1]})"
        else:
            return "Tool executed successfully"

    def call_model(
        self,
        context: List[Dict[str, Any]],
        screenshot_base64: Optional[str] = None,
        current_package_name: str = "",
        user_prompt: str = ""
    ) -> Dict[str, Any]:
        """
        Call Claude API and return parsed response.

        Args:
            context: Conversation context (will be modified in-place)
            screenshot_base64: Base64 encoded screenshot
            current_package_name: Current app package name
            user_prompt: User's prompt (for first message)

        Returns:
            Parsed response dict with keys:
                - return_type: "tool_use" or "text"
                - name: tool name (if tool_use)
                - input: tool input (if tool_use)
                - text: response text (if text)
                - stop_reason: stop reason (if text)
        """
        # Check if last message is tool_use (need tool_result)
        is_tool_result = False
        tool_use_id = None

        if len(context) > 0:
            last_msg = context[-1]
            if last_msg.get("role") == "assistant":
                for block in last_msg.get("content", []):
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        is_tool_result = True
                        tool_use_id = block.get("id")
                        break

        # Build message content
        if is_tool_result and tool_use_id:
            # Extract tool info
            tool_name = None
            tool_input = {}
            last_msg = context[-1]
            for block in last_msg.get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_name = block.get("name")
                    tool_input = block.get("input", {})
                    break

            # Build tool_result content
            tool_result_content = []
            result_text = self._get_tool_result_text(tool_name, tool_input)
            tool_result_content.append({"type": "text", "text": result_text})

            # Add screenshot if provided
            if screenshot_base64:
                h, w, resized_base64 = self._resize_screenshot(screenshot_base64)
                app_name = self._get_app_name_from_package(current_package_name)
                tool_result_content.append(
                    {"type": "text", "text": f"<system-reminder>当前app: {app_name}, Screenshot dimensions: ({w}x{h}, png)</system-reminder>"}
                )
                tool_result_content.append(
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": resized_base64}}
                )

            # Add tool_result to context
            context.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": tool_result_content
                }]
            })
        else:
            # Regular user message
            message_content = []

            if user_prompt:
                message_content.append({"type": "text", "text": user_prompt})

            if screenshot_base64:
                h, w, resized_base64 = self._resize_screenshot(screenshot_base64)
                app_name = self._get_app_name_from_package(current_package_name)
                message_content.append(
                    {"type": "text", "text": f"<system-reminder>当前app: {app_name}, Screenshot dimensions: ({w}x{h}, png)</system-reminder>"}
                )
                message_content.append(
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": resized_base64}}
                )

            if message_content:
                context.append({"role": "user", "content": message_content})

        # Prepare API request
        system_prompt = get_system_prompt()
        data = {
            "max_tokens": 16000,
            "system": system_prompt,
            "messages": context,
            "thinking": {"type": "enabled", "budget_tokens": 12800},
            "tools": TOOLS,
            "model": self.model
        }

        # Call API
        logger.info(f"Calling Claude API with model {self.model}...")
        response = self._call_api(data)

        # Parse response
        return self._parse_response(response, context)

    def _call_api(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Call Claude API with retry logic."""
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "interleaved-thinking-2025-05-14"
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open('data.json', 'wt+') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                with open('headers.json', 'wt+') as f:
                    json.dump(headers, f, ensure_ascii=False, indent=2)
                print('url:', self.url)
                # data_pth = '/Users/huangziyue/CodeGeeXProjects/claude-for-phone/data.json'
                # with open(data_pth, 'r') as f:
                #     data = json.load(f)
                #     print(f'loaded data from {data_pth}')
                # print(data)
                # print(headers)
                response = requests.post(
                    url=self.url,
                    headers=headers,
                    json=data,
                    timeout=120
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"API call failed (attempt {attempt + 1}/{max_retries}): {e}")
                traceback.print_exc()
                time.sleep(2)

    def _parse_response(self, response: Dict[str, Any], context: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse Claude API response."""
        thinking_block = {}
        text_block = {}
        tool_use_block = None

        # Parse response content
        for block in response.get("content", []):
            if block["type"] == "thinking":
                thinking_block = block.copy()
                logger.info(f"Thinking: {block.get('thinking', '')[:100]}...")
            elif block["type"] == "text":
                text_block = block.copy()
                logger.info(f"Text: {block.get('text', '')}")
            elif block["type"] == "tool_use":
                tool_use_block = block.copy()
                logger.info(f"Tool: {block.get('name')}, Input: {json.dumps(block.get('input', {}), ensure_ascii=False)}")

        # Build response
        if tool_use_block:
            # Add assistant message to context
            content = [thinking_block, tool_use_block] if thinking_block else [tool_use_block]
            context.append({"role": "assistant", "content": content})

            # Check for TodoWrite (handle internally)
            tool_name = tool_use_block.get("name")
            if tool_name == "TodoWrite":
                return self._handle_todo_write(tool_use_block, context)

            # Parse tool use
            return self._parse_tool_use(tool_use_block)
        else:
            # Text response
            content = [thinking_block, text_block] if thinking_block else [text_block]
            context.append({"role": "assistant", "content": content})

            text = text_block.get("text", "")
            stop_reason = self._parse_stop_reason(text)

            return {
                "return_type": "text",
                "text": text,
                "stop_reason": stop_reason
            }

    def _handle_todo_write(self, tool_block: Dict[str, Any], context: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Handle TodoWrite internally."""
        logger.info("Handling TodoWrite internally...")

        tool_id = tool_block.get("id")
        tool_input = tool_block.get("input", {})
        todos = json.dumps(tool_input.get("todos", []), ensure_ascii=False)

        # Add tool_result
        context.append({
            "role": "user",
            "content": [{
                "tool_use_id": tool_id,
                "type": "tool_result",
                "content": [{
                    "type": "text",
                    "text": f"Todos have been modified successfully. Ensure that you continue to use the todo list to track your progress. Please proceed with the current tasks if applicable\n\n<system-reminder>\nYour todo list has changed. DO NOT mention this explicitly to the user. Here are the latest contents of your todo list:{todos}</system-reminder>"
                }]
            }]
        })

        # Call model again
        system_prompt = get_system_prompt()
        data = {
            "max_tokens": 16000,
            "system": system_prompt,
            "messages": context,
            "thinking": {"type": "enabled", "budget_tokens": 12800},
            "tools": TOOLS,
            "model": self.model
        }

        response = self._call_api(data)
        return self._parse_response(response, context)

    def _parse_tool_use(self, tool_block: Dict[str, Any]) -> Dict[str, Any]:
        """Parse tool use block and return with real coordinates."""
        tool_name = tool_block.get("name")
        tool_input = tool_block.get("input", {})

        response = {
            "return_type": "tool_use",
            "name": tool_name,
            "input": {}
        }

        # Parse based on tool name
        if tool_name == "Launch":
            app_name = tool_input.get("app_name")
            package_name = self.APP_NAME_TO_PACKAGE.get(app_name, "")
            response["input"]["package_name"] = package_name

        elif tool_name in ["Tap", "LongPress", "DoubleClick"]:
            scaled_coord = tool_input.get("coordinate", [0, 0])
            scaled_coord = [int(scaled_coord[0]), int(scaled_coord[1])]
            real_coord = self._scale_coordinate_to_real(scaled_coord)
            response["input"]["coordinate"] = real_coord
            if tool_name == "LongPress":
                response["input"]["duration"] = float(tool_input.get("duration", 2.0))

        elif tool_name == "Wait":
            response["input"]["duration"] = float(tool_input.get("duration", 1.0))

        elif tool_name == "Type":
            response["input"]["text"] = tool_input.get("text", "")

        elif tool_name == "Swipe":
            scaled_start = tool_input.get("start_coordinate", [0, 0])
            scaled_end = tool_input.get("end_coordinate", [0, 0])
            scaled_start = [int(scaled_start[0]), int(scaled_start[1])]
            scaled_end = [int(scaled_end[0]), int(scaled_end[1])]
            real_start = self._scale_coordinate_to_real(scaled_start)
            real_end = self._scale_coordinate_to_real(scaled_end)
            response["input"]["start_coordinate"] = real_start
            response["input"]["end_coordinate"] = real_end

        return response

    def _parse_stop_reason(self, text: str) -> str:
        """Parse stop reason from text."""
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
            return "finish"
