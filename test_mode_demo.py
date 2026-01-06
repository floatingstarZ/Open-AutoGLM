#!/usr/bin/env python3
"""测试 test 模式功能"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from main_with_service import save_final_messages, SimpleTraceLogger


def test_save_final_messages():
    """测试保存最后一轮 messages 的功能"""
    print("=" * 60)
    print("测试 save_final_messages() 函数")
    print("=" * 60)

    # 创建模拟的 messages 列表
    messages = [
        {"role": "system", "content": "You are a phone automation agent..."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "打开微信\n\n{\"current_app\": \"Launcher\"}"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,iVBORw0..."},
                },
            ],
        },
        {
            "role": "assistant",
            "content": '<think>我需要启动微信应用</think><answer>do(action="Launch", app="WeChat")</answer>',
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "** Screen Info **\n\n{\"current_app\": \"WeChat\"}"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,iVBORw0..."},
                },
            ],
        },
        {
            "role": "assistant",
            "content": '<think>任务已完成</think><answer>finish(message="微信已打开")</answer>',
        },
    ]

    # 创建测试目录
    test_dir = Path("./test_traces/test_mode_demo")
    test_dir.mkdir(parents=True, exist_ok=True)

    # 保存最后一轮 messages
    print("\n保存最后一轮 messages...")
    save_final_messages(messages, test_dir)

    # 验证文件
    final_file = test_dir / "final_messages.json"
    if final_file.exists():
        print(f"\n✅ final_messages.json 已创建: {final_file}")

        with open(final_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        print("\n📝 文件内容:")
        print("-" * 60)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        print("-" * 60)

        # 验证内容
        assert "user" in data, "缺少 user 字段"
        assert "assistant" in data, "缺少 assistant 字段"
        assert data["user"]["role"] == "user", "user role 不正确"
        assert data["assistant"]["role"] == "assistant", "assistant role 不正确"

        # 检查是否是最后一轮
        user_text = None
        for item in data["user"]["content"]:
            if item.get("type") == "text":
                user_text = item["text"]
                break

        assert "Screen Info" in user_text, "不是最后一轮的 user message"
        assert "finish" in data["assistant"]["content"], "不是最后一轮的 assistant message"

        print("\n✅ 所有验证通过！")
        print("   - 保存了最后一轮的 user message")
        print("   - 保存了最后一轮的 assistant message")
        print("   - 内容格式正确")

        return True
    else:
        print("❌ final_messages.json 未创建")
        return False


if __name__ == "__main__":
    success = test_save_final_messages()
    sys.exit(0 if success else 1)
