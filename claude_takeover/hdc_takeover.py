"""
HDC Takeover Agent

Continues phone automation with Claude from existing context using HDC (HarmonyOS).
No backend server required - calls Claude API directly.
"""

import sys
import base64
import time
import json
import argparse
from io import BytesIO
from typing import List, Dict, Any, Optional
from PIL import Image

from claude_takeover.model_client import ModelClient

# Import HDC functions from phone_agent
try:
    from phone_agent.hdc import (
        get_screenshot,
        tap,
        swipe,
        back,
        home,
        double_tap,
        long_press,
        launch_app,
        type_text,
        clear_text,
        get_current_app,
        list_devices,
    )
except ImportError:
    print("❌ 无法导入 HDC 模块，请确保在 Open-AutoGLM 目录中运行")
    sys.exit(1)


# Android package name to HarmonyOS app name mapping
ANDROID_TO_HARMONYOS = {
    "com.tencent.mm": "微信",
    "com.tencent.mobileqq": "QQ",
    "com.sina.weibo": "微博",
    "com.taobao.taobao": "淘宝",
    "com.jingdong.app.mall": "京东",
    "com.xunmeng.pinduoduo": "拼多多",
    "com.xingin.xhs": "小红书",
    "com.zhihu.android": "知乎",
    "com.autonavi.minimap": "高德地图",
    "com.baidu.BaiduMap": "百度地图",
    "com.sankuai.meituan": "美团",
    "me.ele": "美团外卖",
    "com.dianping.v1": "大众点评",
    "ctrip.android.view": "携程",
    "com.MobileTicket": "铁路12306",
    "com.sdu.didi.psnger": "滴滴出行",
    "tv.danmaku.bili": "bilibili",
    "com.ss.android.ugc.aweme": "抖音",
    "com.smile.gifmaker": "快手",
    "com.tencent.qqlive": "腾讯视频",
    "com.qiyi.video": "爱奇艺",
    "com.hunantv.imgo.activity": "芒果TV",
    "com.tencent.qqmusic": "QQ音乐",
    "com.luna.music": "汽水音乐",
    "com.ximalaya.ting.android": "喜马拉雅",
    "com.ss.android.lark": "飞书",
    "com.larus.nova": "豆包",
}


class HDCTakeover:
    """
    HarmonyOS phone takeover agent using HDC.

    Continues automation from existing context without backend server.
    """

    def __init__(
        self,
        context: Optional[List[Dict[str, Any]]] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        target_width: int = 512,
        max_iterations: int = 100,
        device_id: Optional[str] = None,
        trace_dir: Optional[str] = None
    ):
        """
        Initialize HDC Takeover Agent.

        Args:
            context: Existing conversation context (empty list if starting fresh)
            api_key: Claude API key
            model: Model name
            target_width: Image resize width
            max_iterations: Max iteration count
            device_id: HDC device ID (None = auto-detect)
            trace_dir: Directory to save traces
        """
        self.context = context if context is not None else []
        self.max_iterations = max_iterations
        self.device_id = device_id
        self.iteration = 0

        # Initialize model client
        self.model_client = ModelClient(
            api_key=api_key,
            model=model,
            target_width=target_width,
            trace_dir=trace_dir
        )

        # Check HDC connection
        devices = list_devices()
        if not devices:
            print("❌ 未检测到 HarmonyOS 设备")
            sys.exit(1)

        print(f"✅ 检测到 {len(devices)} 个设备:")
        for i, device in enumerate(devices, 1):
            print(f"   {i}. {device.device_id} ({device.connection_type.value})")

    def get_current_app_info(self) -> str:
        """Get current app name."""
        try:
            app_name = get_current_app(device_id=self.device_id)
            return app_name
        except Exception as e:
            print(f"⚠️  获取当前应用失败: {e}")
            return "Unknown"

    def get_screenshot_base64(self) -> Optional[str]:
        """
        Get current screenshot as base64.

        Returns:
            Base64 encoded screenshot, or None if failed
        """
        try:
            screenshot_obj = get_screenshot(device_id=self.device_id)

            if screenshot_obj.is_sensitive:
                print("⚠️  检测到敏感页面")

            return screenshot_obj.base64_data

        except Exception as e:
            print(f"⚠️  截图异常: {e}")
            # Return black image as fallback
            black_img = Image.new('RGB', (1080, 2400), color='black')
            buffered = BytesIO()
            black_img.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def execute_tool(self, tool_response: Dict[str, Any]) -> bool:
        """
        Execute tool action.

        Args:
            tool_response: Tool response dict with 'name' and 'input'

        Returns:
            True if successful, False otherwise
        """
        tool_name = tool_response.get("name")
        tool_input = tool_response.get("input", {})

        print(f"\n🔧 执行工具: {tool_name}")
        print(f"参数: {json.dumps(tool_input, ensure_ascii=False, indent=2)}")

        try:
            if tool_name == "Launch":
                android_package = tool_input.get("package_name")
                print(f"   Android 包名: {android_package}")

                # Map to HarmonyOS app name
                app_name = ANDROID_TO_HARMONYOS.get(android_package)

                if app_name:
                    print(f"   映射到 HarmonyOS 应用名: {app_name}")
                    success = launch_app(app_name, device_id=self.device_id)
                    if not success:
                        print(f"   ⚠️  应用启动失败: {app_name}")
                else:
                    print(f"   ⚠️  未找到包名映射: {android_package}")
                    success = False

                time.sleep(1.0)

            elif tool_name == "Tap":
                x, y = tool_input.get("coordinate", [0, 0])
                print(f"   点击坐标: ({x}, {y})")
                tap(x, y, device_id=self.device_id)

            elif tool_name == "Swipe":
                start_x, start_y = tool_input.get("start_coordinate", [0, 0])
                end_x, end_y = tool_input.get("end_coordinate", [0, 0])
                print(f"   滑动: ({start_x}, {start_y}) -> ({end_x}, {end_y})")
                swipe(start_x, start_y, end_x, end_y, device_id=self.device_id)

            elif tool_name == "Type":
                text = tool_input.get("text", "")
                print(f"   输入文本: {text}")

                # Clear text
                clear_text(device_id=self.device_id)
                time.sleep(0.2)

                # Input text
                type_text(text, device_id=self.device_id)
                time.sleep(1.0)

            elif tool_name == "Wait":
                duration = tool_input.get("duration", 1.0)
                print(f"   等待: {duration}秒")
                time.sleep(duration)

            elif tool_name == "LongPress":
                x, y = tool_input.get("coordinate", [0, 0])
                duration = tool_input.get("duration", 2.0)
                duration_ms = int(duration * 1000)
                print(f"   长按: ({x}, {y}), {duration}秒")
                long_press(x, y, duration_ms=duration_ms, device_id=self.device_id)

            elif tool_name == "DoubleClick":
                x, y = tool_input.get("coordinate", [0, 0])
                print(f"   双击: ({x}, {y})")
                double_tap(x, y, device_id=self.device_id)

            elif tool_name == "Home":
                print(f"   返回主屏幕")
                home(device_id=self.device_id)

            elif tool_name == "Back":
                print(f"   返回上一页")
                back(device_id=self.device_id)

            else:
                print(f"   ⚠️  未知工具: {tool_name}")
                return False

            return True

        except Exception as e:
            print(f"   ❌ 工具执行出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run(self, task: Optional[str] = None) -> str:
        """
        Run the takeover agent.

        Args:
            task: Task description (only needed if starting fresh)

        Returns:
            Final message from agent
        """
        print("=" * 60)
        print(f"🤖 HDC Takeover Agent")
        print(f"🔢 最大迭代: {self.max_iterations}")
        print(f"📝 已有上下文: {len(self.context)} 条消息")
        print("=" * 60)

        # Get initial state
        current_app = self.get_current_app_info()
        screenshot = self.get_screenshot_base64()

        print(f"📱 当前应用: {current_app}")

        # First call to model
        if len(self.context) == 0 and task:
            # Starting fresh with a task
            user_prompt = task
        else:
            # Continuing from context
            user_prompt = ""

        # Call model
        try:
            response = self.model_client.call_model(
                context=self.context,
                screenshot_base64=screenshot,
                current_package_name=current_app,
                user_prompt=user_prompt
            )
        except Exception as e:
            print(f"❌ 模型调用失败: {e}")
            return f"Error: {e}"

        # Main loop
        while self.iteration < self.max_iterations:
            self.iteration += 1
            print(f"\n{'=' * 60}")
            print(f"📍 第 {self.iteration} 轮")
            print(f"{'=' * 60}")
            print(json.dumps(response, ensure_ascii=False, indent=2))

            # Check response type
            if response.get("return_type") == "tool_use":
                # Execute tool
                success = self.execute_tool(response)
                if not success:
                    print("\n❌ 工具执行失败")
                    break

                # Get new state
                print("\n📸 获取执行后的截图...")
                screenshot = self.get_screenshot_base64()
                current_app = self.get_current_app_info()

                # Call model again
                try:
                    response = self.model_client.call_model(
                        context=self.context,
                        screenshot_base64=screenshot,
                        current_package_name=current_app,
                        user_prompt=""
                    )
                except Exception as e:
                    print(f"❌ 模型调用失败: {e}")
                    break

            elif response.get("return_type") == "text":
                # Task finished
                print(f"\n{'=' * 60}")
                print(f"✅ 任务完成!")
                print(f"{'=' * 60}")
                print(f"📝 响应: {response.get('text')}")
                print(f"🏁 停止原因: {response.get('stop_reason')}")
                return response.get("text", "")

            else:
                print(f"\n⚠️  未知返回类型: {response.get('return_type')}")
                break

        if self.iteration >= self.max_iterations:
            print(f"\n⚠️  达到最大迭代次数 ({self.max_iterations})")

        print("\n" + "=" * 60)
        print("🎬 会话结束")
        print("=" * 60)

        return "Max iterations reached"


def main():
    """Command line interface."""
    parser = argparse.ArgumentParser(
        description='HDC Takeover Agent - Continue Claude automation without backend',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从头开始新任务
  python -m claude_takeover.hdc_takeover --task "打开美团外卖，搜索附近美食"

  # 从已有上下文继续（需要加载 context.json）
  python -m claude_takeover.hdc_takeover --context context.json

  # 指定设备ID（多设备场景）
  python -m claude_takeover.hdc_takeover --task "打开小红书" --device-id "192.168.1.100:5555"

  # 自定义配置
  python -m claude_takeover.hdc_takeover --task "打开淘宝" --max-iterations 50
        """
    )

    parser.add_argument('--task', type=str, default=None,
                        help='任务描述（从头开始时使用）')
    parser.add_argument('--context', type=str, default=None,
                        help='上下文文件路径（JSON格式）')
    parser.add_argument('--device-id', type=str, default=None,
                        help='HDC设备ID（多设备时使用）')
    parser.add_argument('--api-key', type=str, default=None,
                        help='Claude API key')
    parser.add_argument('--model', type=str, default=None,
                        help='模型名称')
    parser.add_argument('--max-iterations', type=int, default=100,
                        help='最大迭代次数 (默认: 100)')
    parser.add_argument('--target-width', type=int, default=512,
                        help='截图缩放宽度 (默认: 512)')
    parser.add_argument('--trace-dir', type=str, default=None,
                        help='Trace保存目录 (默认: traces/)')

    args = parser.parse_args()

    # Load context if provided
    context = []
    if args.context:
        try:
            with open(args.context, 'r', encoding='utf-8') as f:
                context = json.load(f)
            print(f"✅ 加载上下文: {len(context)} 条消息")
        except Exception as e:
            print(f"❌ 加载上下文失败: {e}")
            sys.exit(1)

    # Create agent
    agent = HDCTakeover(
        context=context,
        api_key=args.api_key,
        model=args.model,
        target_width=args.target_width,
        max_iterations=args.max_iterations,
        device_id=args.device_id,
        trace_dir=args.trace_dir
    )

    # Run
    result = agent.run(task=args.task)
    print(f"\n最终结果: {result}")


if __name__ == "__main__":
    main()
