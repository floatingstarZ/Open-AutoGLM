"""
ADB Takeover Agent

Continues phone automation with Claude from existing context using ADB (Android).
No backend server required - calls Claude API directly.
"""

import os
import sys
import uuid
import base64
import subprocess
import time
import json
import argparse
from io import BytesIO
from typing import List, Dict, Any, Optional
from PIL import Image

from claude_takeover.model_client import ModelClient


class ADBTakeover:
    """
    Android phone takeover agent using ADB.

    Continues automation from existing context without backend server.
    """

    def __init__(
        self,
        context: Optional[List[Dict[str, Any]]] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        target_width: int = 512,
        max_iterations: int = 100,
        trace_dir: Optional[str] = None
    ):
        """
        Initialize ADB Takeover Agent.

        Args:
            context: Existing conversation context (empty list if starting fresh)
            api_key: Claude API key
            model: Model name
            target_width: Image resize width
            max_iterations: Max iteration count
            trace_dir: Directory to save traces
        """
        self.context = context if context is not None else []
        self.max_iterations = max_iterations
        self.iteration = 0

        # Initialize model client
        self.model_client = ModelClient(
            api_key=api_key,
            model=model,
            target_width=target_width,
            trace_dir=trace_dir
        )

    def get_current_app(self) -> str:
        """Get current app package name."""
        result = os.popen("adb shell dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'")
        output = result.read().strip()
        if output:
            return output.split("\n")[-1]
        return "Unknown"

    def get_screenshot(self) -> Optional[str]:
        """
        Get current screenshot as base64.

        Returns:
            Base64 encoded screenshot, or None if failed
        """
        temp_path = f"/tmp/screenshot_{uuid.uuid4()}.png"

        try:
            # Take screenshot
            result = subprocess.run(
                ["adb", "shell", "screencap", "-p", "/sdcard/tmp.png"],
                capture_output=True,
                text=True,
                timeout=5
            )

            # Check for sensitive screen
            output = result.stdout + result.stderr
            if "Status: -1" in output or "Failed" in output:
                print("⚠️  Screenshot failed - using black image")
                black_img = Image.new('RGB', (1080, 2400), color='black')
                buffered = BytesIO()
                black_img.save(buffered, format="PNG")
                return base64.b64encode(buffered.getvalue()).decode('utf-8')

            # Pull screenshot
            subprocess.run(
                ["adb", "pull", "/sdcard/tmp.png", temp_path],
                capture_output=True,
                timeout=5
            )

            if not os.path.exists(temp_path):
                print("⚠️  Failed to pull screenshot")
                black_img = Image.new('RGB', (1080, 2400), color='black')
                buffered = BytesIO()
                black_img.save(buffered, format="PNG")
                return base64.b64encode(buffered.getvalue()).decode('utf-8')

            # Read and encode
            img = Image.open(temp_path)
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            # Cleanup
            os.remove(temp_path)

            return img_base64

        except Exception as e:
            print(f"⚠️  Screenshot exception: {e}")
            black_img = Image.new('RGB', (1080, 2400), color='black')
            buffered = BytesIO()
            black_img.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def detect_and_set_adbkeyboard(self):
        """Ensure ADB keyboard is set."""
        result = subprocess.run(
            ["adb", "shell", "settings", "get", "secure", "default_input_method"],
            capture_output=True,
            text=True
        )
        output = result.stdout + result.stderr
        if "com.android.adbkeyboard/.AdbIME" not in output:
            os.system("adb shell ime set com.android.adbkeyboard/.AdbIME")

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
                package_name = tool_input.get("package_name")
                print(f"   启动应用: {package_name}")
                os.system(f"adb shell monkey -p {package_name} -c android.intent.category.LAUNCHER 1")
                time.sleep(1.0)

            elif tool_name == "Tap":
                x, y = tool_input.get("coordinate", [0, 0])
                print(f"   点击坐标: ({x}, {y})")
                os.system(f"adb shell input tap {x} {y}")
                time.sleep(0.5)

            elif tool_name == "Swipe":
                start_x, start_y = tool_input.get("start_coordinate", [0, 0])
                end_x, end_y = tool_input.get("end_coordinate", [0, 0])
                print(f"   滑动: ({start_x}, {start_y}) -> ({end_x}, {end_y})")
                os.system(f"adb shell input swipe {start_x} {start_y} {end_x} {end_y} 1000")
                time.sleep(0.5)

            elif tool_name == "Type":
                self.detect_and_set_adbkeyboard()
                text = tool_input.get("text", "")
                print(f"   输入文本: {text}")

                # Clear text
                subprocess.run(
                    ["adb", "shell", "am", "broadcast", "-a", "ADB_CLEAR_TEXT"],
                    capture_output=True,
                    text=True
                )

                # Input text
                encoded_text = base64.b64encode(text.encode('utf-8')).decode('utf-8')
                subprocess.run(
                    ["adb", "shell", "am", "broadcast", "-a", "ADB_INPUT_B64",
                     "--es", "msg", encoded_text],
                    capture_output=True,
                    text=True
                )
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
                os.system(f"adb shell input swipe {x} {y} {x} {y} {duration_ms}")
                time.sleep(0.5)

            elif tool_name == "DoubleClick":
                x, y = tool_input.get("coordinate", [0, 0])
                print(f"   双击: ({x}, {y})")
                os.system(f"adb shell input tap {x} {y}")
                time.sleep(0.1)
                os.system(f"adb shell input tap {x} {y}")
                time.sleep(0.5)

            elif tool_name == "Home":
                print(f"   返回主屏幕")
                os.system(f"adb shell input keyevent KEYCODE_HOME")
                time.sleep(1.0)

            elif tool_name == "Back":
                print(f"   返回上一页")
                os.system("adb shell input keyevent 4")
                time.sleep(1.0)

            else:
                print(f"   ⚠️  未知工具: {tool_name}")
                return False

            return True

        except Exception as e:
            print(f"   ❌ 工具执行出错: {e}")
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
        print(f"🤖 ADB Takeover Agent")
        print(f"🔢 最大迭代: {self.max_iterations}")
        print(f"📝 已有上下文: {len(self.context)} 条消息")
        print("=" * 60)

        # Get initial state
        current_app = self.get_current_app()
        screenshot = self.get_screenshot()

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
                screenshot = self.get_screenshot()
                current_app = self.get_current_app()

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
        description='ADB Takeover Agent - Continue Claude automation without backend',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从头开始新任务
  python -m claude_takeover.adb_takeover --task "打开淘宝，搜索手机"

  # 从已有上下文继续（需要加载 context.json）
  python -m claude_takeover.adb_takeover --context context.json

  # 自定义配置
  python -m claude_takeover.adb_takeover --task "打开美团" --max-iterations 50
        """
    )

    parser.add_argument('--task', type=str, default=None,
                        help='任务描述（从头开始时使用）')
    parser.add_argument('--context', type=str, default=None,
                        help='上下文文件路径（JSON格式）')
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
    agent = ADBTakeover(
        context=context,
        api_key=args.api_key,
        model=args.model,
        target_width=args.target_width,
        max_iterations=args.max_iterations,
        trace_dir=args.trace_dir
    )

    # Run
    result = agent.run(task=args.task)
    print(f"\n最终结果: {result}")


if __name__ == "__main__":
    main()
