import os
import sys
from PIL import Image
import uuid
import base64
from io import BytesIO
import requests
import json
import time
import argparse

# 添加 Open-AutoGLM 路径到系统路径，以便导入 hdc 模块
# 注意：这个路径将在 main 函数中动态添加

# Note: Screen dimensions and scaling are now handled by the backend

# ==================== 默认配置 ====================
DEFAULT_AUTOGLM_PATH = "/Users/huangziyue/Open-AutoGLM"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8097"
DEFAULT_HDC_DEVICE_ID = None  # 如果只有一个设备，保持None；否则设置具体设备ID
DEFAULT_TASK = "外卖下单四杯蜜雪冰城（西罗园店）的奶昔"
DEFAULT_MAX_ITERATIONS = 100

# ==================== Android 包名到 HarmonyOS 应用名的映射 ====================
# Backend 返回的是 Android 包名，需要映射到 HarmonyOS 应用名
ANDROID_TO_HARMONYOS_APP_NAME = {
    # 社交通讯
    "com.tencent.mm": "微信",
    "com.tencent.mobileqq": "QQ",
    "com.sina.weibo": "微博",

    # 电商购物
    "com.taobao.taobao": "淘宝",
    "com.jingdong.app.mall": "京东",
    "com.xunmeng.pinduoduo": "拼多多",

    # 生活服务
    "com.xingin.xhs": "小红书",
    "com.zhihu.android": "知乎",

    # 地图导航
    "com.autonavi.minimap": "高德地图",
    "com.baidu.BaiduMap": "百度地图",

    # 美食外卖
    "com.sankuai.meituan": "美团",
    "me.ele": "美团外卖",  # 饿了么在 HarmonyOS 上可能叫美团外卖
    "com.dianping.v1": "大众点评",

    # 出行旅游
    "ctrip.android.view": "携程",
    "com.MobileTicket": "铁路12306",
    "com.sdu.didi.psnger": "滴滴出行",

    # 视频娱乐
    "tv.danmaku.bili": "bilibili",
    "com.ss.android.ugc.aweme": "抖音",
    "com.smile.gifmaker": "快手",
    "com.tencent.qqlive": "腾讯视频",
    "com.qiyi.video": "爱奇艺",
    "com.hunantv.imgo.activity": "芒果TV",

    # 音乐音频
    "com.tencent.qqmusic": "QQ音乐",
    "com.luna.music": "汽水音乐",
    "com.ximalaya.ting.android": "喜马拉雅",

    # 工作效率
    "com.ss.android.lark": "飞书",

    # AI工具
    "com.larus.nova": "豆包",

    # 其他常用
    "com.huawei.hmos.settings": "设置",
    "com.huawei.hmos.browser": "浏览器",
    "com.huawei.hmos.camera": "相机",
    "com.huawei.hmos.photos": "相册",
}


def check_hdc_connection(hdc_modules):
    """检查HDC设备连接状态"""
    print("\n" + "=" * 60)
    print("📱 检查 HDC 设备连接状态")
    print("=" * 60)

    devices = hdc_modules['list_devices']()
    if not devices:
        print("❌ 未检测到 HarmonyOS 设备")
        print("请确保：")
        print("  1. HarmonyOS 设备已通过 USB 连接或网络连接")
        print("  2. 设备已开启开发者模式和 USB 调试")
        print("  3. HDC 服务正在运行 (运行 'hdc list targets' 检查)")
        return False

    print(f"✅ 检测到 {len(devices)} 个设备:")
    for i, device in enumerate(devices, 1):
        print(f"   {i}. {device.device_id} ({device.connection_type.value})")

    print("=" * 60 + "\n")
    return True


def get_current_app_hdc(hdc_modules, device_id=None):
    """使用 HDC 获取当前应用信息"""
    try:
        app_name = hdc_modules['get_current_app'](device_id=device_id)
        return app_name
    except Exception as e:
        print(f"⚠️  获取当前应用失败: {e}")
        return "Unknown"


def get_current_screenshot_hdc(hdc_modules, device_id=None):
    """使用 HDC 获取当前屏幕截图"""
    try:
        screenshot_obj = hdc_modules['get_screenshot'](device_id=device_id)

        if screenshot_obj.is_sensitive:
            print("⚠️  检测到敏感页面")

        return screenshot_obj.base64_data, screenshot_obj.is_sensitive

    except Exception as e:
        print(f"⚠️  截图异常: {e} - 使用黑色图像作为后备")
        # 创建黑色图像作为后备
        black_img = Image.new('RGB', (1080, 2400), color='black')
        buffered = BytesIO()
        black_img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return img_base64, False


def execute_tool(tool_response, conversation_id, hdc_modules, backend_url, device_id=None):
    """执行工具调用并返回是否需要继续"""
    tool_name = tool_response.get("name")
    tool_input = tool_response.get("input", {})

    print(f"\n🔧 执行工具: {tool_name}")
    print(f"参数: {json.dumps(tool_input, ensure_ascii=False, indent=2)}")

    try:
        if tool_name == "Launch":
            android_package_name = tool_input.get("package_name")
            print(f"   Android 包名: {android_package_name}")

            # 将 Android 包名映射为 HarmonyOS 应用名
            app_name = ANDROID_TO_HARMONYOS_APP_NAME.get(android_package_name)

            if app_name:
                print(f"   映射到 HarmonyOS 应用名: {app_name}")
                # launch_app 会在内部查找对应的 HarmonyOS bundle 和 ability
                success = hdc_modules['launch_app'](app_name, device_id=device_id)
                if not success:
                    print(f"   ⚠️  应用启动失败: {app_name} 可能未安装")
            else:
                print(f"   ⚠️  未找到包名映射: {android_package_name}")
                print(f"   提示：请在 ANDROID_TO_HARMONYOS_APP_NAME 中添加此应用的映射")
                success = False

            time.sleep(1.0)

        elif tool_name == "Tap":
            coordinate = tool_input.get("coordinate", [0, 0])
            x, y = coordinate

            print(f"   点击坐标: ({x}, {y})")
            hdc_modules['tap'](x, y, device_id=device_id)

        elif tool_name == "Swipe":
            start = tool_input.get("start_coordinate", [0, 0])
            end = tool_input.get("end_coordinate", [0, 0])

            start_x, start_y = start
            end_x, end_y = end

            print(f"   滑动: ({start_x}, {start_y}) -> ({end_x}, {end_y})")
            hdc_modules['swipe'](start_x, start_y, end_x, end_y, device_id=device_id)

        elif tool_name == "Type":
            text = tool_input.get("text", "")
            print(f"   输入文本: {text}")

            # 清空文本
            hdc_modules['clear_text'](device_id=device_id)
            time.sleep(0.2)

            # 输入文本
            hdc_modules['type_text'](text, device_id=device_id)
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
            hdc_modules['long_press'](x, y, duration_ms=duration_ms, device_id=device_id)

        elif tool_name == "DoubleClick":
            coordinate = tool_input.get("coordinate", [0, 0])
            x, y = coordinate

            print(f"   双击: ({x}, {y})")
            hdc_modules['double_tap'](x, y, device_id=device_id)

        elif tool_name == "Home":
            print(f"   返回主屏幕")
            hdc_modules['home'](device_id=device_id)

        elif tool_name == "Back":
            print(f"   返回上一页")
            hdc_modules['back'](device_id=device_id)

        else:
            print(f"   ⚠️  未知工具: {tool_name}")
            return False

    except Exception as e:
        print(f"   ❌ 工具执行出错: {e}")
        import traceback
        traceback.print_exc()
        return None

    # 执行完工具后,获取新截图并继续对话
    print("\n📸 获取执行后的截图...")
    screenshot, is_sensitive = get_current_screenshot_hdc(hdc_modules, device_id)

    if is_sensitive:
        print("⚠️  检测到敏感页面")
        return False

    current_app_info = get_current_app_hdc(hdc_modules, device_id)

    # 发送工具执行结果到后端
    payload = {
        "conversation_id": conversation_id,
        "screenshot": screenshot,
        "current_package_name": current_app_info
    }

    print("📤 发送工具执行结果到后端...")
    try:
        response = requests.post(
            url=f"{backend_url}/api/conversation",
            json=payload,
            timeout=120
        )
    except Exception as e:
        print(f"❌ 发送请求失败: {e}")
        return None

    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ 请求失败: {response.text}")
        return None


def call_first_time(task, hdc_modules, backend_url=DEFAULT_BACKEND_URL, device_id=None, max_iterations=DEFAULT_MAX_ITERATIONS):
    """测试首次调用后端API并执行工具调用"""
    print("=" * 60)
    print(f"🎯 任务: {task}")
    print(f"🌐 后端URL: {backend_url}")
    print("=" * 60)

    # 获取当前应用信息
    current_app_info = get_current_app_hdc(hdc_modules, device_id)
    print(f"📱 当前应用: {current_app_info}")

    # 获取截图
    screenshot, is_sensitive = get_current_screenshot_hdc(hdc_modules, device_id)

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
    try:
        response = requests.post(
            url=f"{backend_url}/api/conversation",
            json=payload,
            timeout=120
        )
    except Exception as e:
        print(f"❌ 网络错误: {e}")
        return

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
            result = execute_tool(result, conversation_id, hdc_modules, backend_url, device_id)
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
        description='Claude Phone Agent - HarmonyOS/HDC Mock Client',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认配置
  python mock_app_hdc.py

  # 自定义任务
  python mock_app_hdc.py --task "打开美团外卖，搜索附近美食"

  # 自定义后端地址
  python mock_app_hdc.py --backend-url http://192.168.1.100:8097

  # 指定设备ID（多设备场景）
  python mock_app_hdc.py --device-id "192.168.1.100:5555"

  # 自定义 Open-AutoGLM 路径
  python mock_app_hdc.py --autoglm-path /path/to/Open-AutoGLM

  # 组合使用
  python mock_app_hdc.py --task "打开小红书，搜索旅行攻略" \\
                         --backend-url http://localhost:8020 \\
                         --max-iterations 50
        """
    )

    parser.add_argument('--task', type=str, default=DEFAULT_TASK,
                        help=f'任务描述 (默认: "{DEFAULT_TASK}")')
    parser.add_argument('--backend-url', type=str, default=DEFAULT_BACKEND_URL,
                        help=f'后端服务地址 (默认: {DEFAULT_BACKEND_URL})')
    parser.add_argument('--device-id', type=str, default=DEFAULT_HDC_DEVICE_ID,
                        help='HDC设备ID，多设备时使用 (默认: None，使用第一个设备)')
    parser.add_argument('--autoglm-path', type=str, default=DEFAULT_AUTOGLM_PATH,
                        help=f'Open-AutoGLM 项目路径 (默认: {DEFAULT_AUTOGLM_PATH})')
    parser.add_argument('--max-iterations', type=int, default=DEFAULT_MAX_ITERATIONS,
                        help=f'最大迭代次数 (默认: {DEFAULT_MAX_ITERATIONS})')

    args = parser.parse_args()

    # 动态添加 Open-AutoGLM 路径
    if args.autoglm_path not in sys.path:
        sys.path.insert(0, args.autoglm_path)

    # 动态导入 HDC 模块
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

        # 创建 HDC 模块字典
        hdc_modules = {
            'get_screenshot': get_screenshot,
            'tap': tap,
            'swipe': swipe,
            'back': back,
            'home': home,
            'double_tap': double_tap,
            'long_press': long_press,
            'launch_app': launch_app,
            'type_text': type_text,
            'clear_text': clear_text,
            'get_current_app': get_current_app,
            'list_devices': list_devices,
        }

    except ImportError as e:
        print(f"\n❌ 无法导入 HDC 模块: {e}")
        print(f"请确保 Open-AutoGLM 在正确的路径: {args.autoglm_path}")
        print("或使用 --autoglm-path 参数指定正确的路径")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("🤖 Claude Phone Agent - HarmonyOS/HDC Mock Client")
    print("=" * 70)
    print(f"📝 任务: {args.task}")
    print(f"🌐 后端: {args.backend_url}")
    print(f"📱 设备ID: {args.device_id if args.device_id else '自动检测'}")
    print(f"🔢 最大迭代: {args.max_iterations}")
    print(f"📦 AutoGLM路径: {args.autoglm_path}")
    print("=" * 70 + "\n")

    # 检查 HDC 设备连接
    if not check_hdc_connection(hdc_modules):
        print("\n❌ 设备未连接，程序退出")
        print("请运行 'hdc list targets' 检查设备连接状态")
        sys.exit(1)

    # 执行任务
    call_first_time(
        task=args.task,
        hdc_modules=hdc_modules,
        backend_url=args.backend_url,
        device_id=args.device_id,
        max_iterations=args.max_iterations
    )
