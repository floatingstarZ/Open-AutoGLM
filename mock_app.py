import os
from PIL import Image
import subprocess
import uuid
import base64
from io import BytesIO
import requests
import json
import time
import argparse

# Note: Screen dimensions and scaling are now handled by the backend

# ==================== 默认配置 ====================
DEFAULT_BACKEND_URL = "http://127.0.0.1:8097"
DEFAULT_TASK = "小红书搜索旅游攻略"
DEFAULT_MAX_ITERATIONS = 100


def detect_and_set_adbkeyboard():
    result = subprocess.run(
        ["adb", "shell", "settings", "get", "secure", "default_input_method"],
        capture_output=True,
        text=True
    )
    output = result.stdout + result.stderr
    if "com.android.adbkeyboard/.AdbIME" not in output:
        os.system("adb shell ime set com.android.adbkeyboard/.AdbIME")


def get_current_app():
    result = os.popen("adb shell dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'")
    result = result.read()
    result = result.strip().split("\n")[-1]
    return result


def get_current_screenshot():
    temp_path = "/tmp/screenshot_" + str(uuid.uuid4()) + ".png"
    is_sensitive_screen = False

    try:
        # 执行截图命令并捕获输出
        result = subprocess.run(
            ["adb", "shell", "screencap", "-p", "/sdcard/tmp.png"],
            capture_output=True,
            text=True,
            timeout=5
        )

        # 检查是否截图失败（敏感页面，如支付页面、密码输入页面、登录页面、银行类应用等）
        output = result.stdout + result.stderr
        if "Status: -1" in output or "Failed" in output:
            print("⚠️  Screenshot failed - using black image as fallback")
            # 创建黑色图像
            black_img = Image.new('RGB', (1080, 2400), color='black')
            buffered = BytesIO()
            black_img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            return img_base64, is_sensitive_screen

        # 拉取截图文件到临时路径
        subprocess.run(
            ["adb", "pull", "/sdcard/tmp.png", temp_path],
            capture_output=True,
            text=True,
            timeout=5
        )

        # 检查文件是否成功拉取
        if not os.path.exists(temp_path):
            print("⚠️  Failed to pull screenshot - using black image as fallback")
            black_img = Image.new('RGB', (1080, 2400), color='black')
            buffered = BytesIO()
            black_img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            return img_base64, is_sensitive_screen

        # 读取图像并转换为base64编码
        img = Image.open(temp_path)
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # 删除临时文件
        os.remove(temp_path)

        return img_base64, is_sensitive_screen

    except Exception as e:
        print(f"⚠️  Exception occurred during screenshot: {e} - using black image as fallback")
        # 创建黑色图像作为后备
        black_img = Image.new('RGB', (1080, 2400), color='black')
        buffered = BytesIO()
        black_img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return img_base64, is_sensitive_screen


def execute_tool(tool_response, conversation_id, backend_url):
    """执行工具调用并返回是否需要继续"""
    tool_name = tool_response.get("name")
    tool_input = tool_response.get("input", {})

    print(f"\n🔧 执行工具: {tool_name}")
    print(f"参数: {json.dumps(tool_input, ensure_ascii=False, indent=2)}")

    if tool_name == "Launch":
        package_name = tool_input.get("package_name")
        print(f"   启动应用: {package_name}")
        os.system(f"adb shell monkey -p {package_name} -c android.intent.category.LAUNCHER 1")
        time.sleep(1.0)

    elif tool_name == "Tap":
        coordinate = tool_input.get("coordinate", [0, 0])
        x, y = coordinate

        print(f"   点击坐标: ({x}, {y})")
        os.system(f"adb shell input tap {x} {y}")
        time.sleep(0.5)

    elif tool_name == "Swipe":
        start = tool_input.get("start_coordinate", [0, 0])
        end = tool_input.get("end_coordinate", [0, 0])

        start_x, start_y = start
        end_x, end_y = end

        print(f"   滑动: ({start_x}, {start_y}) -> ({end_x}, {end_y})")
        os.system(f"adb shell input swipe {start_x} {start_y} {end_x} {end_y} 1000")
        time.sleep(0.5)

    elif tool_name == "Type":
        detect_and_set_adbkeyboard()
        text = tool_input.get("text", "")
        print(f"   输入文本: {text}")

        # 清空文本
        subprocess.run(
            ["adb", "shell", "am", "broadcast", "-a", "ADB_CLEAR_TEXT"],
            capture_output=True,
            text=True
        )

        # 使用base64编码输入
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
        coordinate = tool_input.get("coordinate", [0, 0])
        duration = tool_input.get("duration", 2.0)
        x, y = coordinate

        duration_ms = int(duration * 1000)
        print(f"   长按: ({x}, {y}), {duration}秒")
        os.system(f"adb shell input swipe {x} {y} {x} {y} {duration_ms}")
        time.sleep(0.5)

    elif tool_name == "DoubleClick":
        coordinate = tool_input.get("coordinate", [0, 0])
        x, y = coordinate

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

    # 执行完工具后,获取新截图并继续对话
    print("\n📸 获取执行后的截图...")
    screenshot, is_sensitive = get_current_screenshot()

    if is_sensitive:
        print("⚠️  检测到敏感页面")
        return False

    current_app_info = get_current_app()

    # 发送工具执行结果到后端
    payload = {
        "conversation_id": conversation_id,
        "screenshot": screenshot,
        "current_package_name": current_app_info
    }

    print("📤 发送工具执行结果到后端...")
    response = requests.post(
        url=f"{backend_url}/api/conversation",
        json=payload
    )

    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ 请求失败: {response.text}")
        return None


def call_first_time(task, backend_url=DEFAULT_BACKEND_URL, max_iterations=DEFAULT_MAX_ITERATIONS):
    """测试首次调用后端API并执行工具调用"""
    print("=" * 60)
    print(f"🎯 任务: {task}")
    print(f"🌐 后端URL: {backend_url}")
    print("=" * 60)

    # 获取当前应用信息
    current_app_info = get_current_app()
    print(f"📱 当前应用: {current_app_info}")

    # 获取截图
    screenshot, is_sensitive = get_current_screenshot()

    if is_sensitive:
        print("⚠️  检测到敏感页面，无法截图")
        return

    if not screenshot:
        print("❌ 截图失败")
        return

    print(f"📸 截图大小: {len(screenshot)} 字符")

    # 创建会话ID
    conversation_id = str(uuid.uuid4())
    print(f"🔑 会话ID: {conversation_id}")

    # 构建请求
    payload = {
        "conversation_id": conversation_id,
        "screenshot": screenshot,
        "current_package_name": current_app_info,
        "prompt": task
    }

    # 发送请求
    print("\n📤 发送首次请求到后端...")
    response = requests.post(
        url=f"{backend_url}/api/conversation",
        json=payload
    )

    print(f"HTTP状态码: {response.status_code}")

    if response.status_code != 200:
        print(f"❌ 请求失败: {response.text}")
        return

    # 处理响应循环
    iteration = 0

    result = response.json()

    while iteration < max_iterations:
        iteration += 1
        print(f"\n{'=' * 60}")
        print(f"📍 第 {iteration} 轮")
        print(f"{'=' * 60}")
        print(json.dumps(result, ensure_ascii=False, indent=2))

        # 检查返回类型
        if result.get("return_type") == "tool_use":
            # 执行工具调用
            result = execute_tool(result, conversation_id, backend_url)
            if result is None:
                print("\n❌ 工具执行失败或被中断")
                break

        elif result.get("return_type") == "text":
            # 文本响应,任务结束
            print(f"\n{'=' * 60}")
            print(f"✅ 任务完成!")
            print(f"{'=' * 60}")
            print(f"📝 响应: {result.get('text')}")
            print(f"🏁 停止原因: {result.get('stop_reason')}")
            break

        else:
            print(f"\n⚠️  未知返回类型: {result.get('return_type')}")
            break

    if iteration >= max_iterations:
        print(f"\n⚠️  达到最大迭代次数 ({max_iterations})")

    print("\n" + "=" * 60)
    print("🎬 会话结束")
    print("=" * 60)


if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='Claude Phone Agent - Android Mock Client',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认配置
  python mock_app.py

  # 自定义任务
  python mock_app.py --task "打开淘宝，搜索手机"

  # 自定义后端地址
  python mock_app.py --backend-url http://192.168.1.100:8097

  # 限制最大迭代次数
  python mock_app.py --max-iterations 50

  # 组合使用
  python mock_app.py --task "打开美团外卖" --backend-url http://localhost:8020
        """
    )

    parser.add_argument('--task', type=str, default=DEFAULT_TASK,
                        help=f'任务描述 (默认: "{DEFAULT_TASK}")')
    parser.add_argument('--backend-url', type=str, default=DEFAULT_BACKEND_URL,
                        help=f'后端服务地址 (默认: {DEFAULT_BACKEND_URL})')
    parser.add_argument('--max-iterations', type=int, default=DEFAULT_MAX_ITERATIONS,
                        help=f'最大迭代次数 (默认: {DEFAULT_MAX_ITERATIONS})')

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("🤖 Claude Phone Agent - Android Mock Client")
    print("=" * 60)
    print(f"📝 任务: {args.task}")
    print(f"🌐 后端: {args.backend_url}")
    print(f"🔢 最大迭代: {args.max_iterations}")
    print("=" * 60 + "\n")

    # 执行任务
    call_first_time(
        task=args.task,
        backend_url=args.backend_url,
        max_iterations=args.max_iterations
    )
