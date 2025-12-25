#!/usr/bin/env python3
"""
convert_format.py 使用示例

展示如何在Claude格式和当前格式之间进行转换
"""

import json
from judge_tools.convert_format import current_to_claude, claude_to_current

def example_1_basic_conversion():
    """示例1: 基本转换（不带坐标缩放）"""
    print("=" * 80)
    print("示例1: 基本转换")
    print("=" * 80)

    # 当前格式的消息
    current_messages = [
        {
            "role": "system",
            "content": "你是一个智能助手，帮助用户完成手机操作任务。"
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "打开抖音应用"
                }
            ]
        },
        {
            "role": "assistant",
            "content": "<think>用户想要打开抖音应用，我需要使用Launch操作。</think><answer>do(action=\"Launch\", app=\"抖音\")</answer>"
        }
    ]

    # 转换为Claude格式
    claude_messages = current_to_claude(current_messages)

    print("\n转换为Claude格式:")
    for i, msg in enumerate(claude_messages):
        print(f"\n消息 {i} ({msg['role']}):")
        if msg['role'] == 'assistant':
            print(json.dumps(msg['content'], indent=2, ensure_ascii=False))
        else:
            print(f"  content type: {type(msg['content'])}")

    # 转换回当前格式
    back_to_current = claude_to_current(claude_messages)

    print("\n转换回当前格式:")
    for i, msg in enumerate(back_to_current):
        print(f"\n消息 {i} ({msg['role']}):")
        if msg['role'] == 'assistant':
            print(f"  {msg['content']}")


def example_2_coordinate_scaling():
    """示例2: 带坐标缩放的转换"""
    print("\n" + "=" * 80)
    print("示例2: 带坐标缩放的转换")
    print("=" * 80)

    # 当前格式使用相对坐标(0-999)
    current_messages = [
        {
            "role": "assistant",
            "content": "<think>点击屏幕中央的搜索按钮</think><answer>do(action=\"Tap\", element=[500, 500])</answer>"
        },
        {
            "role": "assistant",
            "content": "<think>向下滑动查看更多内容</think><answer>do(action=\"Swipe\", start=[500, 700], end=[500, 300])</answer>"
        }
    ]

    # Claude图像分辨率
    claude_image_scale = [1084, 2412]

    print(f"\n当前格式坐标范围: 0-999 (相对坐标)")
    print(f"Claude图像分辨率: {claude_image_scale}")

    # 转换为Claude格式（相对坐标 -> 绝对坐标）
    claude_messages = current_to_claude(
        current_messages,
        claude_image_scale=claude_image_scale
    )

    print("\nClaude格式（绝对坐标）:")
    for msg in claude_messages:
        for block in msg['content']:
            if block['type'] == 'tool_use':
                print(f"  {block['name']}: {block['input']}")

    # 转换回当前格式（绝对坐标 -> 相对坐标）
    back_to_current = claude_to_current(
        claude_messages,
        claude_image_scale=claude_image_scale
    )

    print("\n转换回当前格式（相对坐标）:")
    for msg in back_to_current:
        content = msg['content']
        # 提取action部分
        import re
        answer_match = re.search(r'<answer>(.*?)</answer>', content)
        if answer_match:
            print(f"  {answer_match.group(1)}")

    print("\n注意: 由于浮点数舍入，坐标可能有1-2像素的误差")


def example_3_real_data():
    """示例3: 使用真实数据进行转换"""
    print("\n" + "=" * 80)
    print("示例3: 使用真实数据")
    print("=" * 80)

    # 加载Claude格式数据
    claude_file = '/Users/huangziyue/CodeGeeXProjects/claude-for-phone/full_logs/20251224142941.json'

    try:
        with open(claude_file, 'r', encoding='utf-8') as f:
            claude_messages = json.load(f)

        print(f"\n加载了 {len(claude_messages)} 条Claude格式消息")

        # 提取图像分辨率（从system-reminder或使用默认值）
        image_scale = [1084, 2412]  # 默认值

        # 只转换前3条消息作为示例
        sample_messages = claude_messages[:3]

        # 转换为当前格式
        current_messages = claude_to_current(
            sample_messages,
            claude_image_scale=image_scale
        )

        print(f"\n转换为当前格式后有 {len(current_messages)} 条消息")

        # 显示assistant消息
        for i, msg in enumerate(current_messages):
            if msg['role'] == 'assistant':
                print(f"\n消息 {i}:")
                content = msg['content']
                if len(content) > 150:
                    print(f"  {content[:150]}...")
                else:
                    print(f"  {content}")

    except FileNotFoundError:
        print(f"\n文件未找到: {claude_file}")
    except Exception as e:
        print(f"\n处理数据时出错: {e}")


if __name__ == '__main__':
    example_1_basic_conversion()
    example_2_coordinate_scaling()
    example_3_real_data()

    print("\n" + "=" * 80)
    print("完成所有示例")
    print("=" * 80)
