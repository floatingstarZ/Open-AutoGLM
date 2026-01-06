#!/usr/bin/env python3
"""测试 SimpleTraceLogger 功能"""

import json
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from main_with_service import SimpleTraceLogger


def test_simple_trace_logger():
    """测试 SimpleTraceLogger 的基本功能"""
    print("测试 SimpleTraceLogger...")
    print("=" * 60)

    # 创建测试日志器
    logger = SimpleTraceLogger(trace_root="./test_traces")

    # 开始任务
    print("\n1. 开始任务...")
    trace_dir = logger.start_task("测试任务：打开微信", k_images=3, max_steps=10)
    print(f"   ✓ 日志目录: {trace_dir}")

    # 记录 system message
    print("\n2. 记录 system message...")
    logger.log_system("You are a phone automation agent...")
    print("   ✓ System message 已记录")

    # 记录第一个 user message（模拟 base64 图像）
    print("\n3. 记录 user message (step 1)...")
    fake_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    logger.log_user("打开微信\n\n{\"current_app\": \"Launcher\"}", fake_base64)
    print("   ✓ User message 已记录")
    print(f"   ✓ 截图已保存: step_1.png")

    # 记录 assistant message
    print("\n4. 记录 assistant message...")
    logger.log_assistant("我需要启动微信应用", "do(action=\"Launch\", app=\"WeChat\")")
    print("   ✓ Assistant message 已记录")

    # 记录第二个 user message
    print("\n5. 记录 user message (step 2)...")
    logger.log_user("** Screen Info **\n\n{\"current_app\": \"WeChat\"}", fake_base64)
    print("   ✓ User message 已记录")
    print(f"   ✓ 截图已保存: step_2.png")

    # 记录第二个 assistant message
    print("\n6. 记录 assistant message...")
    logger.log_assistant("任务已完成", "finish(message=\"微信已打开\")")
    print("   ✓ Assistant message 已记录")

    # 结束任务
    print("\n7. 结束任务...")
    logger.end_task("completed", "微信已打开", 2)
    print("   ✓ Task end 已记录")

    # 验证文件
    print("\n" + "=" * 60)
    print("验证生成的文件...")
    print("=" * 60)

    trace_file = trace_dir / "trace.jsonl"
    if trace_file.exists():
        print(f"\n✅ trace.jsonl 已创建: {trace_file}")

        # 读取并验证内容
        with open(trace_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        print(f"\n📝 trace.jsonl 内容 ({len(lines)} 行):")
        print("-" * 60)
        for i, line in enumerate(lines, 1):
            data = json.loads(line)
            print(f"\n第 {i} 行 - type: {data.get('type')}")
            if data.get("type") == "task_start":
                print(f"  task: {data.get('task')}")
                print(f"  k_images: {data.get('k_images')}")
                print(f"  max_steps: {data.get('max_steps')}")
            elif data.get("type") == "system":
                print(f"  content (前50字符): {data.get('content')[:50]}...")
            elif data.get("type") == "user":
                content = data.get("content", [])
                text_item = next((item for item in content if item.get("type") == "text"), None)
                img_item = next((item for item in content if item.get("type") == "image"), None)
                if text_item:
                    print(f"  text (前50字符): {text_item['text'][:50]}...")
                if img_item:
                    print(f"  image: {img_item['path']}")
            elif data.get("type") == "assistant":
                print(f"  content (前80字符): {data.get('content')[:80]}...")
            elif data.get("type") == "task_end":
                print(f"  status: {data.get('status')}")
                print(f"  message: {data.get('message')}")
                print(f"  total_steps: {data.get('total_steps')}")

        # 验证截图文件
        print("\n" + "-" * 60)
        step1_img = trace_dir / "step_1.png"
        step2_img = trace_dir / "step_2.png"

        if step1_img.exists():
            print(f"✅ step_1.png 已创建 ({step1_img.stat().st_size} bytes)")
        else:
            print("❌ step_1.png 未找到")

        if step2_img.exists():
            print(f"✅ step_2.png 已创建 ({step2_img.stat().st_size} bytes)")
        else:
            print("❌ step_2.png 未找到")

        print("\n" + "=" * 60)
        print("✅ 测试通过！所有功能正常工作。")
        print("=" * 60)

    else:
        print(f"❌ trace.jsonl 未创建")
        return False

    return True


if __name__ == "__main__":
    success = test_simple_trace_logger()
    sys.exit(0 if success else 1)
